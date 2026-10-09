/**
 * لوحة التركيز الجانبية لجدول الأسعار (PB-2): اضغط اسم صنف أو رأس مورد فتفتح
 * حقول تعديله + العروض مرتَّبة.
 *
 * - الصنف: عروضه من الأرخص (بعملة الأساس) مع فرق كل عرض عن الأرخص.
 * - المورد: كل ما قدّمه وترتيبه في كل صنف (i/n).
 * - الحذف خطوتان داخل اللوحة (لا window.confirm): ضغطة تُسلِّح، والثانية تنفّذ.
 * يُعاد تركيب المحتوى بمفتاح الهدف فتُبنى المسوّدة من جديد عند تبديل الهدف.
 */
import React, { useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { KitSidePanel } from "../../../kit/KitSidePanel";
import { KitAutocomplete, type KitAutocompleteOption } from "../../../kit/KitAutocomplete";
import { PriceBoardSupplierForm } from "./PriceBoardSupplierForm";
import type {
  PriceBoardDetailDto,
  PriceBoardItemDto,
  PriceBoardItemWrite,
  PriceBoardSupplierDto,
  PriceBoardSupplierWrite,
} from "../../../../services/priceBoardApi";
import type { Item } from "../../../../types/product";
import type { Supplier } from "../../../../types/supplier";
import {
  formatBoardPrice,
  offersForItem,
  rankOffers,
  supplierRankInItem,
} from "../../../../utils/priceBoard";
import { formatNumber } from "../../../../utils/formatNumber";
import { formatDateValue } from "../../../../utils/formatDate";

export type PanelTarget =
  | { type: "item"; id: number }
  | { type: "supplier"; id: number }
  | { type: "new-supplier" };

interface Props {
  target: PanelTarget | null;
  board: PriceBoardDetailDto;
  products: Item[];
  suppliers: Supplier[];
  onClose: () => void;
  onSaveItem: (id: number, patch: Partial<PriceBoardItemWrite>) => Promise<void>;
  onDeleteItem: (id: number) => Promise<void>;
  onAddSupplier: (body: PriceBoardSupplierWrite) => Promise<void>;
  onSaveSupplier: (id: number, body: PriceBoardSupplierWrite) => Promise<void>;
  onDeleteSupplier: (id: number) => Promise<void>;
}

const fieldLabel = "text-xs ktra-text-soft";

/** حذفٌ بخطوتين داخل الصفحة: الأولى تُسلِّح وتشرح ما سيضيع، والثانية تنفّذ. */
const TwoStepDelete: React.FC<{ label: string; warning: string; onConfirm: () => Promise<void> }> = ({
  label, warning, onConfirm,
}) => {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر الحذف");
      setArmed(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 border-t border-[var(--ktra-line)] pt-3">
      {armed && <p className="text-xs text-[var(--ktra-danger)]" role="alert">{warning}</p>}
      {error && <p className="text-xs text-[var(--ktra-danger)]" role="alert">{error}</p>}
      <div className="flex justify-end gap-2">
        {armed && (
          <button type="button" className="ktra-btn" disabled={busy} onClick={() => setArmed(false)}>تراجع</button>
        )}
        <button
          type="button"
          disabled={busy}
          className={`rounded border border-[var(--ktra-danger)] px-3 py-1 text-xs font-semibold disabled:opacity-50 ${
            armed ? "bg-[var(--ktra-danger)] text-white" : "text-[var(--ktra-danger)]"
          }`}
          onClick={() => { if (armed) void run(); else setArmed(true); }}
        >
          {busy ? <Loader2 className="inline h-3 w-3 animate-spin" /> : armed ? "اضغط مرة أخرى للتأكيد" : label}
        </button>
      </div>
    </div>
  );
};

const ItemPanel: React.FC<{
  item: PriceBoardItemDto;
  board: PriceBoardDetailDto;
  products: Item[];
  onSave: Props["onSaveItem"];
  onDelete: Props["onDeleteItem"];
}> = ({ item, board, products, onSave, onDelete }) => {
  const [name, setName] = useState(item.name);
  const [product, setProduct] = useState<number | null>(item.product);
  const [unit, setUnit] = useState(item.unit_of_measure ?? "");
  const [quantity, setQuantity] = useState(item.quantity == null ? "" : formatNumber(item.quantity, { maxDecimals: 4 }));
  const [note, setNote] = useState(item.note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const productOptions = useMemo<KitAutocompleteOption[]>(
    () => products.map((p) => ({ id: p.id, label: p.name, sub: p.modelNumber || p.categoryName || undefined })),
    [products],
  );
  const supplierById = useMemo(() => new Map(board.suppliers.map((s) => [s.id, s])), [board.suppliers]);
  const ranked = useMemo(() => rankOffers(offersForItem(board.prices, item.id)), [board.prices, item.id]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("اسم الصنف مطلوب");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(item.id, {
        name: name.trim(),
        product,
        unit_of_measure: unit.trim(),
        quantity: quantity.trim() || null,
        note: note.trim(),
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "تعذّر حفظ الصنف");
    } finally {
      setSaving(false);
    }
  };

  const best = ranked[0]?.base;

  return (
    <div className="flex flex-col gap-3">
      <form className="flex flex-col gap-3" onSubmit={(e) => { void save(e); }}>
        <div className="flex flex-col gap-1">
          <span className={fieldLabel}>الصنف — اكتب للبحث في منتجات النظام أو أبقِه نصّاً حراً</span>
          <KitAutocomplete
            value={name}
            options={productOptions}
            placeholder="اسم الصنف…"
            onPick={(id) => {
              const picked = products.find((p) => String(p.id) === String(id));
              setProduct(Number(id));
              if (picked) setName(picked.name);
            }}
            onFreeText={(text) => { setProduct(null); setName(text); }}
            createLabel={(text) => `إبقاء «${text}» نصّاً حراً (بلا ربط بمنتج)`}
            // كالمنتقي في العرض: النص لا يضيع بلا اختيار، لكن منتجاً مرتبطاً لا يُفكّ
            // الربط عنه بحرفٍ يُكتب بحثاً عن بديل.
            onTextChange={product == null ? (text) => setName(text) : undefined}
          />
          <span className="text-[11px]">
            <span className={`rounded px-1.5 py-px font-semibold ${
              product != null ? "bg-[var(--ktra-accent-bg)] text-[var(--ktra-accent)]" : "bg-[var(--ktra-panel)] ktra-text-soft"
            }`}>
              {product != null ? "منتج في النظام" : "نص حر"}
            </span>
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>الوحدة</span>
            <input className="ktra-input" value={unit} onChange={(e) => setUnit(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={fieldLabel}>الكمية المطلوبة</span>
            <input className="ktra-input" inputMode="decimal" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={fieldLabel}>ملاحظة</span>
          <input className="ktra-input" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {error && <p className="text-xs text-[var(--ktra-danger)]" role="alert">{error}</p>}
        <div className="flex justify-end">
          <button type="submit" className="ktra-btn-primary px-4 py-1.5 text-sm font-semibold disabled:opacity-50" disabled={saving}>
            {saving ? <Loader2 className="inline h-4 w-4 animate-spin" /> : "حفظ التعديلات"}
          </button>
        </div>
      </form>

      <div className="flex flex-col gap-1">
        <span className={fieldLabel}>العروض على هذا الصنف، من الأرخص (بـ{board.base_currency_code})</span>
        {ranked.length === 0 ? (
          <p className="text-sm ktra-text-soft">لم يقدّم أي مورد سعراً لهذا الصنف بعد.</p>
        ) : (
          <ul className="overflow-hidden rounded border border-[var(--ktra-line)]">
            {ranked.map((r) => {
              const sup = supplierById.get(r.offer.board_supplier);
              const win = r.rank === 1 && ranked.length > 1;
              const over = best && best > 0 && r.rank > 1 ? Math.round(((r.base - best) / best) * 100) : null;
              return (
                <li
                  key={r.offer.id}
                  className={`grid grid-cols-[2rem_1fr_auto] items-center gap-2 border-b border-[var(--ktra-line)] px-2 py-1.5 text-sm last:border-b-0 ${
                    win ? "bg-[var(--ktra-ok-bg)]" : ""
                  }`}
                >
                  <span className="text-xs ktra-text-soft tabular-nums">{formatNumber(r.rank)}</span>
                  <span className="min-w-0">
                    {sup?.supplier_name ?? "—"}
                    <small className="block truncate text-[11px] ktra-text-soft">{r.offer.note || sup?.terms || ""}</small>
                  </span>
                  <span className="text-end font-semibold tabular-nums">
                    {formatBoardPrice(r.base)} {board.base_currency_code}
                    {sup && sup.currency_code !== board.base_currency_code && (
                      <small className="block text-[11px] font-normal ktra-text-soft">
                        {formatBoardPrice(r.offer.unit_price)} {sup.currency_code}
                      </small>
                    )}
                    {over !== null && (
                      <small className="block text-[11px] font-normal ktra-text-soft">{over === 0 ? "+أقل من 1%" : `+${formatNumber(over)}%`}</small>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <TwoStepDelete
        label="حذف الصنف"
        warning={`سيُحذف الصنف مع ${formatNumber(board.prices.filter((p) => p.item === item.id).length)} سعر مسجَّل عليه.`}
        onConfirm={() => onDelete(item.id)}
      />
    </div>
  );
};

const SupplierPanel: React.FC<{
  supplier: PriceBoardSupplierDto;
  board: PriceBoardDetailDto;
  suppliers: Supplier[];
  onSave: Props["onSaveSupplier"];
  onDelete: Props["onDeleteSupplier"];
}> = ({ supplier, board, suppliers, onSave, onDelete }) => {
  const rows = useMemo(() => {
    const itemById = new Map(board.items.map((i) => [i.id, i]));
    return board.prices
      .filter((p) => p.board_supplier === supplier.id)
      .map((p) => ({
        price: p,
        item: itemById.get(p.item),
        rank: supplierRankInItem(board.prices, p.item, supplier.id),
      }))
      .filter((r) => r.item);
  }, [board.items, board.prices, supplier.id]);
  const wins = rows.filter((r) => r.rank && r.rank.rank === 1 && r.rank.total > 1).length;
  const differs = supplier.currency_code !== board.base_currency_code;

  return (
    <div className="flex flex-col gap-3">
      <PriceBoardSupplierForm
        mode="edit"
        initial={supplier}
        baseCurrencyCode={board.base_currency_code}
        suppliers={suppliers}
        onSubmit={(body) => onSave(supplier.id, body)}
      />
      <div className="flex flex-col gap-1">
        <span className={fieldLabel}>
          ما قدّمه: {formatNumber(rows.length)} صنف · الأرخص في {formatNumber(wins)}
          {supplier.offer_date ? ` · عرض ${formatDateValue(supplier.offer_date)}` : ""}
        </span>
        {rows.length === 0 ? (
          <p className="text-sm ktra-text-soft">لم تُسجَّل أسعار لهذا المورد بعد. اضغط خانات عموده في الجدول لكتابتها.</p>
        ) : (
          <ul className="overflow-hidden rounded border border-[var(--ktra-line)]">
            {rows.map((r) => {
              const win = r.rank !== null && r.rank.rank === 1 && r.rank.total > 1;
              return (
                <li
                  key={r.price.id}
                  className={`grid grid-cols-[3rem_1fr_auto] items-center gap-2 border-b border-[var(--ktra-line)] px-2 py-1.5 text-sm last:border-b-0 ${
                    win ? "bg-[var(--ktra-ok-bg)]" : ""
                  }`}
                >
                  <span className="text-xs ktra-text-soft tabular-nums">
                    {r.rank ? `${formatNumber(r.rank.rank)}/${formatNumber(r.rank.total)}` : "—"}
                  </span>
                  <span className="min-w-0">
                    {r.item?.name}
                    <small className="block truncate text-[11px] ktra-text-soft">{r.price.note}</small>
                  </span>
                  <span className="text-end font-semibold tabular-nums">
                    {formatBoardPrice(r.price.unit_price)} {supplier.currency_code}
                    {differs && (
                      <small className="block text-[11px] font-normal ktra-text-soft">
                        ≈ {formatBoardPrice(r.price.unit_price_base)} {board.base_currency_code}
                      </small>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <TwoStepDelete
        label="حذف المورد"
        warning={`سيُحذف عمود المورد مع ${formatNumber(rows.length)} سعر قدّمه.`}
        onConfirm={() => onDelete(supplier.id)}
      />
    </div>
  );
};

export const PriceBoardFocusPanel: React.FC<Props> = (props) => {
  const { target, board, onClose } = props;
  if (!target) return null;

  let title = "مورد جديد";
  let body: React.ReactNode = null;
  if (target.type === "new-supplier") {
    body = (
      <PriceBoardSupplierForm
        mode="create"
        baseCurrencyCode={board.base_currency_code}
        suppliers={props.suppliers}
        onSubmit={props.onAddSupplier}
      />
    );
  } else if (target.type === "item") {
    const item = board.items.find((i) => i.id === target.id);
    if (!item) return null;
    title = `الصنف: ${item.name}`;
    body = (
      <ItemPanel
        key={`item-${item.id}`}
        item={item}
        board={board}
        products={props.products}
        onSave={props.onSaveItem}
        onDelete={props.onDeleteItem}
      />
    );
  } else {
    const supplier = board.suppliers.find((s) => s.id === target.id);
    if (!supplier) return null;
    title = `المورد: ${supplier.supplier_name}`;
    body = (
      <SupplierPanel
        key={`supplier-${supplier.id}`}
        supplier={supplier}
        board={board}
        suppliers={props.suppliers}
        onSave={props.onSaveSupplier}
        onDelete={props.onDeleteSupplier}
      />
    );
  }

  return (
    <KitSidePanel open onClose={onClose} title={title} width={440}>
      {body}
    </KitSidePanel>
  );
};
