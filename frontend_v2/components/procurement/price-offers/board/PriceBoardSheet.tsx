/**
 * جدول أسعار الاستيراد (PB-2): الأصناف صفوف والموردون أعمدة، والخلية سعر المورد
 * للصنف. مبنيّ كمكوّن مخصَّص لا فوق `KitGrid` لثلاثة أسباب:
 *   1) أعمدة `KitGrid` مصفوفة أعمدة نصّية بحقل إدخال دائم في كل خلية، والموردون
 *      هنا أعمدة ديناميكية برأسٍ غنيّ (عملة/تاريخ/ملف) وخلاياها عرضٌ بتحريرٍ عند
 *      النقر لا إدخالٌ دائم؛
 *   2) تنقّل لوحة المفاتيح في `KitGrid` يفترض مفاتيح أعمدة ثابتة (product/qty/price)
 *      بينما هنا Enter = الصفّ التالي في العمود نفسه وTab = المورد التالي؛
 *   3) يلزم عمود الصنف والرأس والخلاصة لاصقة داخل حاوية تتمرّر وحدها.
 *
 * حفظ الخلية فوري: ما يكتبه المستخدم يظهر في الخلية حالاً (طبقة `overlay`)،
 * ولا يدخل بيانات الجدول (ولا المقارنة والتظليل) إلا بعد تأكيد الخادم — فسعر
 * الأساس يحسبه الخادم وحده ولا نخمّنه هنا. فشل الحفظ يُبقي ما كُتب أحمر مع إعادة
 * المحاولة.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Loader2, Plus } from "lucide-react";
import { KitAutocomplete, type KitAutocompleteOption } from "../../../kit/KitAutocomplete";
import { KitErrorState, KitSpinner } from "../../../kit/KitStates";
import { useToast } from "../../../../contexts/ToastContext";
import {
  addPriceBoardItems,
  addPriceBoardSupplier,
  deletePriceBoardItem,
  deletePriceBoardSupplier,
  getPriceBoard,
  setPriceBoardCell,
  updatePriceBoardItem,
  updatePriceBoardSupplier,
  type PriceBoardDetailDto,
  type PriceBoardItemWrite,
  type PriceBoardPriceDto,
  type PriceBoardSupplierWrite,
} from "../../../../services/priceBoardApi";
import type { Item } from "../../../../types/product";
import type { Supplier } from "../../../../types/supplier";
import {
  cheapestSupplierIds,
  formatBoardPrice,
  isHttpUrl,
  offersForItem,
  parseAmount,
  parseCellInput,
  parsePastedItems,
  rankOffers,
  searchBoard,
  spreadPercent,
  winsPerSupplier,
  type CellInput,
  type RankedOffer,
} from "../../../../utils/priceBoard";
import { formatNumber } from "../../../../utils/formatNumber";
import { formatDateValue } from "../../../../utils/formatDate";
import { PriceBoardFocusPanel, type PanelTarget } from "./PriceBoardFocusPanel";

/** نافذة حوار صغيرة (RTL) — تُغلق بـEsc أو بالنقر على الخلفية. */
export const BoardDialog: React.FC<{ title: string; onClose: () => void; children: React.ReactNode }> = ({
  title, onClose, children,
}) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      dir="rtl"
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="flex w-full max-w-lg flex-col gap-3 rounded-lg border border-[var(--ktra-border)] bg-[var(--ktra-panel)] p-4 shadow-xl"
      >
        <h3 className="text-base font-bold">{title}</h3>
        {children}
      </div>
    </div>
  );
};

interface CellOverlay {
  raw: string;
  price: string | null;
  note: string;
  status: "pending" | "failed";
  message?: string;
  seq: number;
}

const cellKey = (itemId: number, supplierId: number) => `${itemId}|${supplierId}`;

/** السعر للتحرير: بلا أصفار زائدة، ثم «, الملاحظة» إن وُجدت. */
const editText = (price: string, note: string) =>
  `${formatNumber(price, { maxDecimals: 6 })}${note ? `, ${note}` : ""}`;

const CellEditor: React.FC<{
  initial: string;
  onCommit: (raw: string, move: "down" | "next" | "prev" | null) => void;
  onCancel: () => void;
}> = ({ initial, onCommit, onCancel }) => {
  const [value, setValue] = useState(initial);
  const [invalid, setInvalid] = useState(false);
  const done = useRef(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);

  const commit = (move: "down" | "next" | "prev" | null) => {
    if (parseCellInput(value).kind === "invalid") {
      setInvalid(true);
      return;
    }
    done.current = true;
    onCommit(value, move);
  };

  return (
    <>
      <input
        ref={ref}
        dir="auto"
        inputMode="decimal"
        value={value}
        aria-invalid={invalid}
        aria-label="السعر وملاحظة بعد فاصلة"
        placeholder="السعر, ملاحظة"
        className={`h-[3.25rem] w-full bg-[var(--ktra-grid-bg)] px-2.5 text-sm outline-2 -outline-offset-2 ${
          invalid ? "outline-[var(--ktra-danger)]" : "outline-[var(--ktra-accent)]"
        }`}
        onChange={(e) => { setValue(e.target.value); setInvalid(false); }}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); commit("down"); }
          else if (e.key === "Tab") { e.preventDefault(); commit(e.shiftKey ? "prev" : "next"); }
          else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done.current = true; onCancel(); }
        }}
        onBlur={() => {
          if (done.current) return;
          // خروج بنص غير صالح = تراجع (لا حفظ ولا بقاء محرّر مفتوح بلا تركيز).
          if (parseCellInput(value).kind === "invalid") { done.current = true; onCancel(); return; }
          commit(null);
        }}
      />
      {invalid && (
        <span className="absolute inset-x-0 top-full z-30 bg-[var(--ktra-danger-bg)] px-2 py-0.5 text-[11px] text-[var(--ktra-danger)]" role="alert">
          اكتب السعر رقماً (1180 أو 1,180)، ثم ملاحظة بعد فاصلة ومسافة: 4.2, MOQ 500
        </span>
      )}
    </>
  );
};

interface Props {
  boardId: number;
  /** منتجات النظام لربط الأصناف. */
  products: Item[];
  /** الموردون الدوليون (مع غير المصنَّفين). */
  suppliers: Supplier[];
  onBack: () => void;
}

const th = "border-b border-s border-[var(--ktra-line)] p-0 text-start align-middle";

export const PriceBoardSheet: React.FC<Props> = ({ boardId, products, suppliers, onBack }) => {
  const toast = useToast();
  const [board, setBoard] = useState<PriceBoardDetailDto | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [search, setSearch] = useState("");
  const [onlyOffered, setOnlyOffered] = useState(false);
  const [editing, setEditing] = useState<{ item: number; supplier: number } | null>(null);
  const [overlay, setOverlay] = useState<Record<string, CellOverlay>>({});
  const [target, setTarget] = useState<PanelTarget | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pasteBusy, setPasteBusy] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);

  const boardRef = useRef<PriceBoardDetailDto | null>(null);
  boardRef.current = board;
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const seqRef = useRef(0);
  const latestSeq = useRef(new Map<string, number>());
  const gridRef = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    setBoard(null);
    setLoadError(null);
    getPriceBoard(boardId)
      .then((detail) => { if (active) setBoard(detail); })
      .catch((cause) => {
        if (active) setLoadError(cause instanceof Error ? cause.message : "تعذّر تحميل الجدول");
      });
    return () => { active = false; };
  }, [boardId, reloadKey]);

  // بعد إغلاق محرّر الخلية بلوحة المفاتيح يعود التركيز إلى الخلية نفسها.
  useEffect(() => {
    if (editing === null && pendingFocus.current) {
      const key = pendingFocus.current;
      pendingFocus.current = null;
      gridRef.current?.querySelector<HTMLElement>(`[data-cell="${key}"]`)?.focus();
    }
  }, [editing]);

  const patchBoard = useCallback(
    (fn: (b: PriceBoardDetailDto) => PriceBoardDetailDto) => setBoard((prev) => (prev ? fn(prev) : prev)),
    [],
  );

  // ───────────────────────── مشتقّات القراءة ─────────────────────────
  const prices = board?.prices ?? [];
  const items = board?.items ?? [];
  const boardSuppliers = board?.suppliers ?? [];
  const baseCode = board?.base_currency_code ?? "";

  const priceByCell = useMemo(() => {
    const map = new Map<string, PriceBoardPriceDto>();
    for (const p of prices) map.set(cellKey(p.item, p.board_supplier), p);
    return map;
  }, [prices]);

  const analysis = useMemo(() => {
    const map = new Map<number, { ranked: RankedOffer<PriceBoardPriceDto>[]; cheapest: Set<number>; spread: number | null }>();
    for (const item of items) {
      const offers = offersForItem<PriceBoardPriceDto>(prices, item.id);
      map.set(item.id, { ranked: rankOffers<PriceBoardPriceDto>(offers), cheapest: cheapestSupplierIds(offers), spread: spreadPercent(offers) });
    }
    return map;
  }, [items, prices]);

  const wins = useMemo(() => winsPerSupplier(items.map((i) => i.id), prices), [items, prices]);

  const pricesPerSupplier = useMemo(() => {
    const map = new Map<number, number>();
    for (const p of prices) map.set(p.board_supplier, (map.get(p.board_supplier) ?? 0) + 1);
    return map;
  }, [prices]);

  const supplierName = useMemo(() => new Map(boardSuppliers.map((s) => [s.id, s.supplier_name])), [boardSuppliers]);

  const visibility = useMemo(
    () => searchBoard(
      items.map((i) => ({ id: i.id, name: i.name })),
      boardSuppliers.map((s) => ({ id: s.id, supplier_name: s.supplier_name })),
      prices,
      search,
      onlyOffered,
    ),
    [items, boardSuppliers, prices, search, onlyOffered],
  );
  const rows = useMemo(() => items.filter((i) => visibility.visibleItemIds.has(i.id)), [items, visibility]);
  const withoutFile = boardSuppliers.filter((s) => !s.attachments.some((a) => isHttpUrl(a.url))).length;

  const productOptions = useMemo<KitAutocompleteOption[]>(
    () => products.map((p) => ({ id: p.id, label: p.name, sub: p.modelNumber || p.categoryName || undefined })),
    [products],
  );

  // ───────────────────────── حفظ الخلايا ─────────────────────────
  const sendCell = useCallback(
    async (itemId: number, supplierId: number, parsed: Exclude<CellInput, { kind: "invalid" }>, raw: string) => {
      const key = cellKey(itemId, supplierId);
      const seq = ++seqRef.current;
      latestSeq.current.set(key, seq);
      const isSet = parsed.kind === "set";
      setOverlay((prev) => ({
        ...prev,
        [key]: { raw, price: isSet ? parsed.price : null, note: isSet ? parsed.note : "", status: "pending", seq },
      }));
      try {
        const result = await setPriceBoardCell(boardId, {
          item: itemId,
          board_supplier: supplierId,
          unit_price: isSet ? parsed.price : null,
          ...(isSet ? { note: parsed.note } : {}),
        });
        // ردّ قديم لخلية كُتبت بعده قيمة أحدث: يُتجاهل كلياً.
        if (latestSeq.current.get(key) !== seq) return;
        patchBoard((b) => {
          const others = b.prices.filter((p) => !(p.item === itemId && p.board_supplier === supplierId));
          return "deleted" in result ? { ...b, prices: others } : { ...b, prices: [...others, result] };
        });
        setOverlay((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      } catch (cause) {
        if (latestSeq.current.get(key) !== seq) return;
        const message = cause instanceof Error ? cause.message : "تعذّر حفظ السعر";
        setOverlay((prev) => (prev[key] ? { ...prev, [key]: { ...prev[key], status: "failed", message } } : prev));
      }
    },
    [boardId, patchBoard],
  );

  const commitCell = (itemId: number, supplierId: number, raw: string) => {
    const parsed = parseCellInput(raw);
    if (parsed.kind === "invalid") return;
    const key = cellKey(itemId, supplierId);
    const current = boardRef.current?.prices.find((p) => p.item === itemId && p.board_supplier === supplierId);
    const hasOverlay = Boolean(overlayRef.current[key]);
    // لا طلب لما لم يتغيّر: Enter على خلية دون تعديل لا يُرسل شيئاً.
    if (!hasOverlay) {
      if (parsed.kind === "delete" && !current) return;
      if (
        parsed.kind === "set" && current
        && parseAmount(current.unit_price) === parseAmount(parsed.price)
        && (current.note ?? "") === parsed.note
      ) return;
    }
    void sendCell(itemId, supplierId, parsed, raw);
  };

  const handleCommit = (itemId: number, supplierId: number, raw: string, move: "down" | "next" | "prev" | null) => {
    commitCell(itemId, supplierId, raw);
    const rowIndex = rows.findIndex((r) => r.id === itemId);
    const colIndex = boardSuppliers.findIndex((s) => s.id === supplierId);
    let next: { item: number; supplier: number } | null = null;
    if (move === "down") {
      const r = rows[rowIndex + 1];
      if (r) next = { item: r.id, supplier: supplierId };
    } else if (move === "next" || move === "prev") {
      const s = boardSuppliers[colIndex + (move === "next" ? 1 : -1)];
      if (s) next = { item: itemId, supplier: s.id };
    }
    if (move && !next) pendingFocus.current = cellKey(itemId, supplierId);
    setEditing(next);
  };

  const retryCell = (itemId: number, supplierId: number) => {
    const ov = overlayRef.current[cellKey(itemId, supplierId)];
    if (!ov) return;
    const parsed = parseCellInput(ov.raw);
    if (parsed.kind !== "invalid") void sendCell(itemId, supplierId, parsed, ov.raw);
  };

  const discardOverlay = (itemId: number, supplierId: number) => {
    const key = cellKey(itemId, supplierId);
    latestSeq.current.delete(key);
    setOverlay((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  // ───────────────────────── الأصناف والموردون ─────────────────────────
  const addItems = async (entries: PriceBoardItemWrite[]) => {
    const result = await addPriceBoardItems(boardId, entries);
    patchBoard((b) => ({
      ...b,
      items: [...b.items, ...result.created.filter((c) => !b.items.some((i) => i.id === c.id))],
    }));
    return result;
  };

  const addOneItem = async (entry: PriceBoardItemWrite) => {
    try {
      const result = await addItems([entry]);
      if (result.skipped_duplicates > 0) toast(`تم تجاهل ${formatNumber(result.skipped_duplicates)} مكرّر`, "info");
    } catch (cause) {
      toast(cause instanceof Error ? cause.message : "تعذّرت إضافة الصنف", "error");
    }
  };

  const pastePreview = useMemo(
    () => parsePastedItems(pasteText, items.map((i) => i.name)),
    [pasteText, items],
  );

  const submitPaste = async () => {
    if (pastePreview.names.length === 0) {
      setPasteError(pastePreview.duplicates > 0
        ? `تم تجاهل ${formatNumber(pastePreview.duplicates)} مكرّر — لا أصناف جديدة للإضافة.`
        : "الصق سطراً واحداً على الأقل.");
      return;
    }
    setPasteBusy(true);
    setPasteError(null);
    try {
      const result = await addItems(pastePreview.names.map((name) => ({ name })));
      const ignored = pastePreview.duplicates + result.skipped_duplicates;
      toast(
        `أُضيف ${formatNumber(result.created.length)} صنف${ignored ? ` — تم تجاهل ${formatNumber(ignored)} مكرّر` : ""}`,
        "success",
      );
      setPasteOpen(false);
      setPasteText("");
    } catch (cause) {
      setPasteError(cause instanceof Error ? cause.message : "تعذّرت إضافة الأصناف");
    } finally {
      setPasteBusy(false);
    }
  };

  const saveItem = async (id: number, patch: Partial<PriceBoardItemWrite>) => {
    const saved = await updatePriceBoardItem(boardId, id, patch);
    patchBoard((b) => ({ ...b, items: b.items.map((i) => (i.id === id ? saved : i)) }));
    toast("تم حفظ الصنف", "success");
  };

  const deleteItem = async (id: number) => {
    await deletePriceBoardItem(boardId, id);
    patchBoard((b) => ({
      ...b,
      items: b.items.filter((i) => i.id !== id),
      prices: b.prices.filter((p) => p.item !== id),
    }));
    setTarget(null);
  };

  const addSupplier = async (body: PriceBoardSupplierWrite) => {
    const created = await addPriceBoardSupplier(boardId, body);
    patchBoard((b) => ({ ...b, suppliers: [...b.suppliers, created] }));
    setTarget(null);
    toast("أُضيف عمود المورد", "success");
    requestAnimationFrame(() => {
      const el = gridRef.current;
      if (el) el.scrollLeft = -el.scrollWidth;
    });
  };

  const saveSupplier = async (id: number, body: PriceBoardSupplierWrite) => {
    const before = boardRef.current?.suppliers.find((s) => s.id === id);
    const saved = await updatePriceBoardSupplier(boardId, id, body);
    patchBoard((b) => ({ ...b, suppliers: b.suppliers.map((s) => (s.id === id ? saved : s)) }));
    toast("تم حفظ المورد", "success");
    // تغيّر العملة أو السعر يعيد حساب أسعار الأساس في الخادم — نقرأها منه لا نحسبها هنا.
    if (before && (before.currency !== saved.currency || parseAmount(before.exchange_rate) !== parseAmount(saved.exchange_rate))) {
      const fresh = await getPriceBoard(boardId);
      setBoard(fresh);
    }
  };

  const deleteSupplier = async (id: number) => {
    await deletePriceBoardSupplier(boardId, id);
    patchBoard((b) => ({
      ...b,
      suppliers: b.suppliers.filter((s) => s.id !== id),
      prices: b.prices.filter((p) => p.board_supplier !== id),
    }));
    setTarget(null);
  };

  // ───────────────────────── العرض ─────────────────────────
  if (loadError) {
    return (
      <div dir="rtl" className="flex flex-col gap-2 p-2">
        <button type="button" className="ktra-btn self-start" onClick={onBack}>
          <ChevronRight className="inline h-4 w-4" /> الجداول
        </button>
        <KitErrorState message={loadError} onRetry={() => setReloadKey((k) => k + 1)} />
      </div>
    );
  }
  if (!board) {
    return <KitSpinner label="جاري تحميل الجدول…" />;
  }

  const startEdit = (itemId: number, supplierId: number) => setEditing({ item: itemId, supplier: supplierId });

  return (
    <div dir="rtl" className="flex min-w-0 flex-col gap-3 p-2">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="ktra-btn" onClick={onBack}>
              <ChevronRight className="inline h-4 w-4" /> الجداول
            </button>
            <h2 className="text-lg font-bold">{board.title}</h2>
            {board.is_archived && <span className="ktra-badge-neutral">مؤرشف</span>}
          </div>
          {board.notes && <p className="max-w-[70ch] text-sm ktra-text-soft">{board.notes}</p>}
        </div>
        <div className="flex flex-wrap gap-4 text-sm ktra-text-soft">
          <span><b className="tabular-nums text-[var(--ktra-ink)]">{formatNumber(items.length)}</b> صنف</span>
          <span><b className="tabular-nums text-[var(--ktra-ink)]">{formatNumber(boardSuppliers.length)}</b> مورد</span>
          <span><b className="tabular-nums text-[var(--ktra-ink)]">{formatNumber(prices.length)}</b> سعر مسجّل</span>
          {withoutFile > 0 && (
            <span className="text-[var(--ktra-warn-fg)]">
              <b className="tabular-nums">{formatNumber(withoutFile)}</b> مورد بلا ملف
            </span>
          )}
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          className="ktra-input w-60 max-w-full"
          placeholder="ابحث في الأصناف أو الموردين…"
          aria-label="بحث في الأصناف والموردين"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="w-64 max-w-full">
          <KitAutocomplete
            value=""
            options={productOptions}
            placeholder="+ صنف: ابحث في المنتجات أو اكتب نصاً حراً"
            onPick={(id) => {
              const picked = products.find((p) => String(p.id) === String(id));
              if (picked) void addOneItem({ name: picked.name, product: Number(id) });
            }}
            onFreeText={(text) => { void addOneItem({ name: text }); }}
            createLabel={(text) => `إضافة «${text}» كصنف نصّي حر`}
          />
        </div>
        <button type="button" className="ktra-btn" onClick={() => { setPasteError(null); setPasteOpen(true); }}>
          لصق قائمة أصناف
        </button>
        <button type="button" className="ktra-btn" onClick={() => setTarget({ type: "new-supplier" })}>
          <Plus className="inline h-3.5 w-3.5" /> مورد
        </button>
        <label className="flex cursor-pointer select-none items-center gap-1.5 rounded-full border border-[var(--ktra-line)] px-3 py-1 text-xs">
          <input type="checkbox" checked={onlyOffered} onChange={(e) => setOnlyOffered(e.target.checked)} />
          الأصناف التي عليها عروض فقط
        </label>
      </div>

      <div
        ref={gridRef}
        className="max-h-[calc(100vh-17rem)] min-h-80 overflow-auto rounded-lg border border-[var(--ktra-line)] bg-[var(--ktra-grid-bg)]"
      >
        <table className="w-max min-w-full border-separate border-spacing-0 text-sm tabular-nums">
          <thead>
            <tr>
              <th scope="col" className={`${th} sticky start-0 top-0 z-30 min-w-56 max-w-72 border-s-2 bg-[var(--ktra-grid-head)]`}>
                <div className="flex flex-col gap-0.5 px-2.5 py-2">
                  <span className="font-semibold">الصنف</span>
                  <span className="text-[11px] font-normal ktra-text-soft">{formatNumber(items.length)} صنف</span>
                </div>
              </th>
              {boardSuppliers.map((s) => {
                const file = s.attachments.find((a) => isHttpUrl(a.url));
                const dim = visibility.dimSupplierIds.has(s.id);
                return (
                  <th
                    key={s.id}
                    scope="col"
                    className={`${th} sticky top-0 z-20 min-w-40 max-w-48 bg-[var(--ktra-grid-head)] ${dim ? "opacity-30" : ""}`}
                  >
                    <div
                      role="button"
                      tabIndex={0}
                      aria-label={`المورد ${s.supplier_name}`}
                      className="flex cursor-pointer flex-col gap-0.5 px-2.5 py-2 hover:bg-[var(--ktra-accent-bg)]"
                      onClick={() => setTarget({ type: "supplier", id: s.id })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && e.target === e.currentTarget) setTarget({ type: "supplier", id: s.id });
                      }}
                    >
                      <span className="font-semibold leading-snug">{s.supplier_name}</span>
                      <span className="text-[11px] font-normal ktra-text-soft">
                        {s.currency_code} · {s.offer_date ? formatDateValue(s.offer_date) : "بلا تاريخ"}
                      </span>
                      <span className="flex flex-wrap items-center gap-x-2 text-[11px] font-normal">
                        {file ? (
                          <a
                            className="ktra-text-accent font-semibold hover:underline"
                            href={file.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                          >
                            فتح ملف العرض ↗{s.attachments.length > 1 ? ` (+${formatNumber(s.attachments.length - 1)})` : ""}
                          </a>
                        ) : (
                          <span className="text-[var(--ktra-warn-fg)]">لا ملف مرفق</span>
                        )}
                        <span className="ktra-text-soft">{formatNumber(pricesPerSupplier.get(s.id) ?? 0)} سعر</span>
                      </span>
                    </div>
                  </th>
                );
              })}
              <th scope="col" className={`${th} sticky top-0 z-20 min-w-28 bg-[var(--ktra-grid-head)] text-center`}>
                <button type="button" className="ktra-btn m-2" onClick={() => setTarget({ type: "new-supplier" })}>
                  + مورد
                </button>
              </th>
              <th scope="col" className={`${th} sticky end-0 top-0 z-30 min-w-40 border-e-2 bg-[var(--ktra-grid-head)]`}>
                <div className="flex flex-col gap-0.5 px-2.5 py-2">
                  <span className="font-semibold">الخلاصة</span>
                  <span className="text-[11px] font-normal ktra-text-soft">أفضل سعر ({baseCode}) / الفرق</span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={boardSuppliers.length + 3} className="p-6 text-center text-sm ktra-text-soft">
                  {items.length === 0
                    ? "الجدول فارغ — أضف أصنافاً (أو الصق قائمة) وأضف موردين ثم اكتب الأسعار."
                    : "لا أصناف تطابق البحث أو الفلتر."}
                </td>
              </tr>
            )}
            {rows.map((item) => {
              const info = analysis.get(item.id);
              const best = info?.ranked[0];
              const tied = info ? info.ranked.filter((r) => r.rank === 1) : [];
              return (
                <tr key={item.id}>
                  <th scope="row" className={`${th} sticky start-0 z-10 min-w-56 max-w-72 border-s-2 bg-[var(--ktra-grid-bg)] font-normal`}>
                    <button
                      type="button"
                      className="flex w-full flex-col items-start gap-0.5 px-2.5 py-2 text-start hover:bg-[var(--ktra-accent-bg)]"
                      onClick={() => setTarget({ type: "item", id: item.id })}
                    >
                      <span className="font-medium leading-snug">{item.name}</span>
                      <span className="flex flex-wrap items-center gap-1.5 text-[11px] ktra-text-soft">
                        <span className={`rounded px-1.5 py-px font-semibold ${
                          item.product != null ? "bg-[var(--ktra-accent-bg)] text-[var(--ktra-accent)]" : "bg-[var(--ktra-panel)]"
                        }`}>
                          {item.product != null ? "منتج في النظام" : "نص حر"}
                        </span>
                        {item.unit_of_measure}
                        {item.quantity ? ` · ${formatNumber(item.quantity, { maxDecimals: 4, group: true })}` : ""}
                      </span>
                    </button>
                  </th>
                  {boardSuppliers.map((s) => {
                    const key = cellKey(item.id, s.id);
                    const srv = priceByCell.get(key);
                    const ov = overlay[key];
                    const dim = visibility.isCellDim(item.id, s.id);
                    const isEditing = editing?.item === item.id && editing.supplier === s.id;

                    let shownPrice: string | null = srv?.unit_price ?? null;
                    let shownNote = srv?.note ?? "";
                    if (ov && ov.price !== null) {
                      shownPrice = ov.price;
                      shownNote = ov.note;
                    } else if (ov) {
                      // حذفٌ معلَّق أو فاشل: لا يُعرض السعر القديم بجانب «تعذّر الحفظ» كأنه باقٍ.
                      shownPrice = null;
                      shownNote = "";
                    }
                    const isBest = !ov && Boolean(srv) && Boolean(info?.cheapest.has(s.id));
                    const failed = ov?.status === "failed";
                    const showBase = !ov && srv && s.currency_code !== baseCode;

                    return (
                      <td
                        key={s.id}
                        data-cell={key}
                        tabIndex={isEditing ? -1 : 0}
                        title={failed ? ov?.message : undefined}
                        className={`relative h-[3.25rem] min-w-40 cursor-cell border-b border-s border-[var(--ktra-line)] p-0 align-middle hover:outline hover:outline-1 hover:-outline-offset-1 hover:outline-[var(--ktra-accent)] ${
                          failed
                            ? "bg-[var(--ktra-danger-bg)] outline outline-1 -outline-offset-1 outline-[var(--ktra-danger)]"
                            : isBest ? "bg-[var(--ktra-ok-bg)]" : ""
                        } ${dim ? "opacity-30" : ""} ${ov?.status === "pending" ? "opacity-60" : ""}`}
                        onClick={() => { if (!isEditing) startEdit(item.id, s.id); }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !isEditing && e.target === e.currentTarget) {
                            e.preventDefault();
                            startEdit(item.id, s.id);
                          }
                        }}
                      >
                        {isEditing ? (
                          <CellEditor
                            initial={ov ? ov.raw : srv ? editText(srv.unit_price, srv.note ?? "") : ""}
                            onCommit={(raw, move) => handleCommit(item.id, s.id, raw, move)}
                            onCancel={() => { pendingFocus.current = key; setEditing(null); }}
                          />
                        ) : (
                          <div className="flex flex-col gap-px px-2.5 py-1.5">
                            {isBest && (
                              <span className="absolute start-1.5 top-0.5 text-[10px] font-bold text-[var(--ktra-ok)]">الأرخص</span>
                            )}
                            {shownPrice === null ? (
                              <span className="ktra-text-soft">—</span>
                            ) : (
                              <>
                                <span className={`font-semibold ${isBest ? "text-[var(--ktra-ok)]" : ""}`}>
                                  {formatBoardPrice(shownPrice)}
                                </span>
                                {showBase && srv && (
                                  <span className="text-[11px] ktra-text-soft">≈ {formatBoardPrice(srv.unit_price_base)} {baseCode}</span>
                                )}
                                {shownNote && (
                                  <span className="max-w-40 truncate text-[11px] ktra-text-soft" title={shownNote}>{shownNote}</span>
                                )}
                              </>
                            )}
                            {ov?.status === "pending" && <Loader2 className="absolute end-1.5 top-1.5 h-3 w-3 animate-spin ktra-text-soft" />}
                            {failed && (
                              <span className="flex items-center gap-2 text-[11px] text-[var(--ktra-danger)]">
                                تعذّر الحفظ
                                <button
                                  type="button"
                                  className="font-semibold underline"
                                  onClick={(e) => { e.stopPropagation(); retryCell(item.id, s.id); }}
                                >
                                  إعادة
                                </button>
                                <button
                                  type="button"
                                  className="underline"
                                  onClick={(e) => { e.stopPropagation(); discardOverlay(item.id, s.id); }}
                                >
                                  تجاهل
                                </button>
                              </span>
                            )}
                          </div>
                        )}
                      </td>
                    );
                  })}
                  <td className="border-b border-s border-[var(--ktra-line)]" />
                  <td className="sticky end-0 z-10 min-w-40 border-b border-e-2 border-s border-[var(--ktra-line)] bg-[var(--ktra-grid-head)] p-0 align-middle">
                    <div className="flex flex-col gap-px px-2.5 py-1.5 text-xs">
                      {best ? (
                        <>
                          <b className="text-sm tabular-nums">{formatBoardPrice(best.base)} {baseCode}</b>
                          <span className="ktra-text-soft">
                            {tied.map((r) => supplierName.get(r.offer.board_supplier) ?? "—").join(" / ")}
                          </span>
                          <span className="ktra-text-soft">
                            {formatNumber(info?.ranked.length ?? 0)} عروض
                            {info?.spread != null
                              ? info.spread === 0 ? " · فرق أقل من 1%" : ` · أغلى بـ ${formatNumber(info.spread)}%`
                              : ""}
                          </span>
                        </>
                      ) : (
                        <span className="ktra-text-soft">لا عروض بعد</span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr>
              <td className="sticky bottom-0 start-0 z-20 min-w-56 border-s-2 border-t border-[var(--ktra-line)] bg-[var(--ktra-grid-head)] px-2.5 py-2 text-xs ktra-text-soft">
                عدد الأصناف التي هو الأرخص فيها
              </td>
              {boardSuppliers.map((s) => (
                <td key={s.id} className="sticky bottom-0 z-10 border-s border-t border-[var(--ktra-line)] bg-[var(--ktra-grid-head)] px-2.5 py-2">
                  <b>{formatNumber(wins.get(s.id) ?? 0)}</b>
                </td>
              ))}
              <td className="sticky bottom-0 z-10 border-s border-t border-[var(--ktra-line)] bg-[var(--ktra-grid-head)]" />
              <td className="sticky bottom-0 end-0 z-20 border-e-2 border-s border-t border-[var(--ktra-line)] bg-[var(--ktra-grid-head)]" />
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-xs ktra-text-soft">
        Enter ينزل للصف التالي، وTab ينتقل للمورد التالي، وEsc يلغي. اترك الخلية فارغة لحذف السعر. اكتب ملاحظة بعد
        فاصلة: <b>4.2, MOQ 500</b>. المقارنة بين الموردين بعملة الأساس ({baseCode}).
      </p>

      {pasteOpen && (
        <BoardDialog title="لصق قائمة أصناف" onClose={() => { if (!pasteBusy) setPasteOpen(false); }}>
          <p className="text-xs ktra-text-soft">
            الصق عموداً من Excel أو من ملف المورد، سطر لكل صنف (يؤخذ العمود الأول). المكرّر لاسمٍ موجود يُتجاهل.
          </p>
          <textarea
            autoFocus
            className="ktra-input min-h-44"
            placeholder={"بلاط 60×60 بيج\nخلاط مطبخ ستانلس\n…"}
            value={pasteText}
            onChange={(e) => { setPasteText(e.target.value); setPasteError(null); }}
          />
          <p className="text-xs ktra-text-soft">
            سيُضاف {formatNumber(pastePreview.names.length)} صنف
            {pastePreview.duplicates > 0 ? ` — سيُتجاهل ${formatNumber(pastePreview.duplicates)} مكرّر` : ""}
          </p>
          {pasteError && <p className="text-xs text-[var(--ktra-danger)]" role="alert">{pasteError}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" className="ktra-btn" disabled={pasteBusy} onClick={() => setPasteOpen(false)}>إلغاء</button>
            <button type="button" className="ktra-btn-primary px-4 py-1.5 text-sm font-semibold disabled:opacity-50" disabled={pasteBusy} onClick={() => { void submitPaste(); }}>
              {pasteBusy ? <Loader2 className="inline h-4 w-4 animate-spin" /> : "إضافة"}
            </button>
          </div>
        </BoardDialog>
      )}

      <PriceBoardFocusPanel
        target={target}
        board={board}
        products={products}
        suppliers={suppliers}
        onClose={() => setTarget(null)}
        onSaveItem={saveItem}
        onDeleteItem={deleteItem}
        onAddSupplier={addSupplier}
        onSaveSupplier={saveSupplier}
        onDeleteSupplier={deleteSupplier}
      />
    </div>
  );
};
