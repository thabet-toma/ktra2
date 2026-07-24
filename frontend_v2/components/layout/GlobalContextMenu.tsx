import React, { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import {
  Home,
  RefreshCw,
  Printer,
  ArrowRight,
  Calculator,
  Copy,
  Scissors,
  ClipboardPaste,
  TextCursorInput,
  UserRound,
  FilePlus2,
  ReceiptText,
  FileText,
  ShoppingCart,
  HandCoins,
  Package,
  Coins,
} from "lucide-react";
import { AppView, User } from "../../types";
import { clientLogger } from "../../services/logger";
import { buildQuickActionGroups, visibleQuickActionGroups, QuickAction } from "./quickActions";
import { AseelCalculatorPopover } from "../aseel/AseelCalculatorPopover";
import {
  PartnerContext,
  ItemContext,
  calcSeedFromRawValue,
  formatCalcResult,
  readEditableValue,
  writeEditableValue,
  resolveEditableTarget,
  resolvePartnerContextFromTarget,
  resolveItemContextFromTarget,
} from "../../utils/contextMenuTargets";

/**
 * قائمة زر الفأرة اليمنى العامّة — تعمل في كامل الموقع ومحتواها **حسب الحالة**.
 *
 * تلتقط `contextmenu` على مستوى المستند في مرحلة الفقاعة، فأي قائمة موضعية
 * (كشجرة المنتجات) توقف الانتشار أو تستدعي preventDefault تفوز ولا تظهر هذه.
 * أي عنصر يحمل `data-no-global-context-menu` يُبقي منيو المتصفح الأصلي (نسخ/لصق).
 *
 * المحتوى حسب هدف النقرة:
 *  - داخل حقل نصّي  ⇒ حاسبة (تُبذَر بقيمة الحقل وتعيد الناتج إليه) + حافظة (نسخ/قص/لصق/تحديد الكل).
 *  - فوق اسم شريك   ⇒ إجراءاته (بطاقة/فاتورة/سند قبض أو صرف/كشف) عبر `data-ctx-partner-*`.
 *  - دائماً         ⇒ إجراءات الصفحة (رجوع/الرئيسية/تحديث/طباعة) + الإجراءات السريعة المُرشَّحة بالدور.
 */
interface Props {
  user: User;
  onNavigate: (view: AppView, targetId?: string) => void;
}

type MenuEntry =
  | { kind: "sep" }
  | { kind: "item"; key: string; label: string; icon: React.ReactNode; onClick: () => void; danger?: boolean };

type MenuState = {
  x: number;
  y: number;
  editable: HTMLElement | null;
  selStart: number | null;
  selEnd: number | null;
  partner: PartnerContext | null;
  item: ItemContext | null;
};

type CalcState = {
  x: number;
  y: number;
  el: HTMLElement;
  seed: string;
  anchorRect: { x: number; y: number; width: number; height: number };
};

const MENU_WIDTH = 220;
const ROW_H = 32;
const ICON = "w-3.5 h-3.5";

export const GlobalContextMenu: React.FC<Props> = ({ user, onNavigate }) => {
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [calc, setCalc] = useState<CalcState | null>(null);
  const navigate = useNavigate();

  const close = useCallback(() => setMenu(null), []);

  useEffect(() => {
    const onContextMenu = (e: MouseEvent) => {
      // قائمة موضعية تعاملت معه (preventDefault) ⇒ لا نتدخّل.
      if (e.defaultPrevented) return;
      const target = e.target as HTMLElement | null;
      // استثناء صريح ⇒ أبقِ منيو المتصفح الأصلي (نسخ/لصق/تحديد).
      if (target && typeof target.closest === "function" && target.closest("[data-no-global-context-menu]")) {
        return;
      }
      const editable = resolveEditableTarget(e.target);
      const partner = resolvePartnerContextFromTarget(e.target);
      const item = resolveItemContextFromTarget(e.target);
      e.preventDefault();
      let selStart: number | null = null;
      let selEnd: number | null = null;
      if (editable instanceof HTMLInputElement || editable instanceof HTMLTextAreaElement) {
        selStart = editable.selectionStart;
        selEnd = editable.selectionEnd;
      }
      // تثبيت داخل الشاشة (لا يخرج المنيو من الحافة).
      const x = Math.min(e.clientX, window.innerWidth - MENU_WIDTH - 8);
      const y = Math.min(e.clientY, window.innerHeight - 8);
      setMenu({ x: Math.max(8, x), y: Math.max(8, y), editable, selStart, selEnd, partner, item });
      clientLogger.info("app.context_menu_open");
    };
    document.addEventListener("contextmenu", onContextMenu);
    return () => document.removeEventListener("contextmenu", onContextMenu);
  }, []);

  useEffect(() => {
    if (!menu) return;
    const onScroll = () => close();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("click", close);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu, close]);

  if (!menu) {
    // الحاسبة قد تبقى مفتوحة بعد إغلاق المنيو.
    return calc
      ? createPortal(
          <AseelCalculatorPopover
            initialValue={calc.seed}
            x={calc.x}
            y={calc.y}
            anchorRect={calc.anchorRect}
            onConfirm={(val) => {
              writeEditableValue(calc.el, formatCalcResult(val));
              clientLogger.info("app.context_calc_confirm");
              setCalc(null);
            }}
            onClose={() => setCalc(null)}
          />,
          document.body,
        )
      : null;
  }

  const run = (fn: () => void) => () => { fn(); close(); };
  const go = (view: AppView, id?: string) => run(() => onNavigate(view, id));
  const goUrl = (url: string) => run(() => navigate(url));

  // ————— حاسبة داخل الحقل: تُبذَر بقيمته الحالية وتعيد الناتج إليه —————
  const openCalculator = () => {
    if (!menu.editable) return;
    const seed = calcSeedFromRawValue(readEditableValue(menu.editable));
    const r = menu.editable.getBoundingClientRect();
    setCalc({
      x: menu.x,
      y: menu.y,
      el: menu.editable,
      seed,
      anchorRect: { x: r.x, y: r.y, width: r.width, height: r.height },
    });
    close();
  };

  // ————— حافظة الحقل (Ctrl+C/V/X لا يتأثران — نلمس contextmenu فقط) —————
  const copyField = async () => {
    const el = menu.editable;
    if (!el) return;
    let text = "";
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      const s = menu.selStart ?? 0;
      const e = menu.selEnd ?? 0;
      text = e > s ? el.value.slice(s, e) : el.value;
    } else {
      text = window.getSelection()?.toString() || el.textContent || "";
    }
    try { await navigator.clipboard.writeText(text); } catch { clientLogger.warn("app.context_copy_failed"); }
  };

  const cutField = async () => {
    await copyField();
    const el = menu.editable;
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      const s = menu.selStart ?? 0;
      const e = menu.selEnd ?? 0;
      if (e > s) {
        writeEditableValue(el, el.value.slice(0, s) + el.value.slice(e));
        el.setSelectionRange(s, s);
      }
    }
  };

  const pasteField = async () => {
    const el = menu.editable;
    if (!el) return;
    try {
      const text = await navigator.clipboard.readText();
      if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
        const s = menu.selStart ?? el.value.length;
        const e = menu.selEnd ?? el.value.length;
        writeEditableValue(el, el.value.slice(0, s) + text + el.value.slice(e));
        const caret = s + text.length;
        el.focus();
        el.setSelectionRange(caret, caret);
      } else {
        el.focus();
        document.execCommand?.("insertText", false, text);
      }
    } catch { clientLogger.warn("app.context_paste_failed"); }
  };

  const selectAllField = () => {
    const el = menu.editable;
    if (!el) return;
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      el.focus();
      el.select();
    } else {
      const range = document.createRange();
      range.selectNodeContents(el);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
    }
  };

  // ————— إجراءات الشريك (كرت مُعبّأ مسبقاً — روابط الكرت تدعمها أصلاً) —————
  const openPartnerModal = (p: PartnerContext, action: "receipt" | "payment") => {
    try { sessionStorage.setItem("ktra_partner_action", action); } catch { /* وضع خاص */ }
    clientLogger.info("app.context_partner_action");
    navigate(`/partners/${p.id}`);
  };

  const partnerEntries = (p: PartnerContext): MenuEntry[] => {
    if (p.kind === "customer") {
      return [
        { kind: "item", key: "p-card", label: `بطاقة: ${p.name || "العميل"}`, icon: <UserRound className={ICON} />, onClick: goUrl(`/partners/${p.id}`) },
        { kind: "item", key: "p-invoice", label: "فاتورة مبيعات", icon: <FilePlus2 className={ICON} />, onClick: goUrl(`/sales/invoices/new?customer_id=${p.id}`) },
        { kind: "item", key: "p-receipt", label: "سند قبض", icon: <ReceiptText className={ICON} />, onClick: run(() => openPartnerModal(p, "receipt")) },
        { kind: "item", key: "p-quote", label: "عرض سعر", icon: <FileText className={ICON} />, onClick: goUrl(`/sales/quotations?action=new&customer_id=${p.id}`) },
        { kind: "item", key: "p-statement", label: "كشف حساب", icon: <FileText className={ICON} />, onClick: goUrl(`/partners/${p.id}`) },
      ];
    }
    return [
      { kind: "item", key: "p-card", label: `بطاقة: ${p.name || "المورد"}`, icon: <UserRound className={ICON} />, onClick: goUrl(`/partners/${p.id}`) },
      { kind: "item", key: "p-purchase", label: "فاتورة شراء", icon: <ShoppingCart className={ICON} />, onClick: goUrl(`/purchase-invoices/new`) },
      { kind: "item", key: "p-payment", label: "سند صرف", icon: <HandCoins className={ICON} />, onClick: run(() => openPartnerModal(p, "payment")) },
      { kind: "item", key: "p-statement", label: "كشف حساب", icon: <FileText className={ICON} />, onClick: goUrl(`/partners/${p.id}`) },
    ];
  };

  // ————— إجراءات الصنف (بطاقة الصنف + تكلفته — روابط موجودة أصلاً) —————
  const itemEntries = (it: ItemContext): MenuEntry[] => [
    { kind: "item", key: "i-card", label: `بطاقة الصنف${it.name ? `: ${it.name}` : ""}`, icon: <Package className={ICON} />, onClick: goUrl(`/products/${it.id}`) },
    { kind: "item", key: "i-cost", label: "تكلفة الصنف", icon: <Coins className={ICON} />, onClick: goUrl(`/product-cost?product=${it.id}`) },
  ];

  // إجراءات الصفحة العامّة (متاحة دائماً).
  const pageActions: MenuEntry[] = [
    { kind: "item", key: "back", label: "رجوع", icon: <ArrowRight className={ICON} />, onClick: run(() => window.history.back()) },
    { kind: "item", key: "home", label: "الرئيسية", icon: <Home className={ICON} />, onClick: go("dashboard") },
    { kind: "item", key: "refresh", label: "تحديث الصفحة", icon: <RefreshCw className={ICON} />, onClick: run(() => window.location.reload()) },
    { kind: "item", key: "print", label: "طباعة", icon: <Printer className={ICON} />, onClick: run(() => { clientLogger.info("app.print_requested"); window.print(); }) },
  ];

  // الإجراءات السريعة (نفس تعريف الشريط، مُرشَّحة بالدور).
  const quickGroups = visibleQuickActionGroups(buildQuickActionGroups(user, (view, id) => go(view, id)));
  const quickEntries: MenuEntry[] = [];
  quickGroups.forEach((group: QuickAction[], gi) => {
    if (gi > 0) quickEntries.push({ kind: "sep" });
    group.forEach((a) =>
      quickEntries.push({ kind: "item", key: a.key, label: a.label, icon: a.icon, onClick: a.onClick }),
    );
  });

  // بناء القائمة حسب السياق: (حاسبة+حافظة) ثم (شريك) ثم (صفحة) ثم (سريعة).
  const editableEntries: MenuEntry[] = menu.editable
    ? [
        { kind: "item", key: "calc", label: "حاسبة", icon: <Calculator className={ICON} />, onClick: openCalculator },
        { kind: "item", key: "copy", label: "نسخ", icon: <Copy className={ICON} />, onClick: run(() => void copyField()) },
        { kind: "item", key: "cut", label: "قص", icon: <Scissors className={ICON} />, onClick: run(() => void cutField()) },
        { kind: "item", key: "paste", label: "لصق", icon: <ClipboardPaste className={ICON} />, onClick: run(() => void pasteField()) },
        { kind: "item", key: "select-all", label: "تحديد الكل", icon: <TextCursorInput className={ICON} />, onClick: run(selectAllField) },
      ]
    : [];

  // الترتيب: السياقي أولاً (حاسبة/حافظة ← شريك ← سريعة) والعامّ أخيراً (رجوع/الرئيسية/تحديث/طباعة).
  // نُدمج المجموعات غير الفارغة بفاصل بينها فقط — بلا فواصل بادئة/زائدة/مكرّرة.
  const groups: MenuEntry[][] = [
    editableEntries,
    menu.partner ? partnerEntries(menu.partner) : [],
    menu.item ? itemEntries(menu.item) : [],
    quickEntries,
    pageActions,
  ].filter((g) => g.length > 0);
  const entries: MenuEntry[] = [];
  groups.forEach((group, gi) => {
    if (gi > 0) entries.push({ kind: "sep" });
    entries.push(...group);
  });

  return createPortal(
    <>
      <div
        dir="rtl"
        role="menu"
        style={{
          position: "fixed", left: menu.x, top: menu.y, zIndex: 100000,
          minWidth: MENU_WIDTH, maxHeight: "80vh", overflowY: "auto",
          background: "#ffffff", border: "1px solid #b9c4cf", borderRadius: 6,
          boxShadow: "0 6px 20px rgba(0,0,0,.18)", padding: 3,
          fontFamily: "inherit", fontSize: 13, color: "#333426",
        }}
        onClick={(e) => e.stopPropagation()}
        onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); }}
      >
        {entries.map((en, i) =>
          en.kind === "sep" ? (
            <div key={`sep-${i}`} style={{ height: 1, background: "#e3e0d4", margin: "3px 6px" }} />
          ) : (
            <button
              key={en.key}
              type="button"
              role="menuitem"
              onClick={en.onClick}
              style={{
                display: "flex", alignItems: "center", gap: 8, width: "100%",
                height: ROW_H, padding: "0 10px", border: 0, background: "transparent",
                cursor: "pointer", fontSize: 13, textAlign: "start", borderRadius: 5,
                color: en.danger ? "#dc2626" : "#333426",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "#eef2f7"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
            >
              <span style={{ width: 16, display: "inline-flex", justifyContent: "center", color: "#5b6472" }}>{en.icon}</span>
              <span>{en.label}</span>
            </button>
          ),
        )}
      </div>
      {calc && (
        <AseelCalculatorPopover
          initialValue={calc.seed}
          x={calc.x}
          y={calc.y}
          onConfirm={(val) => {
            writeEditableValue(calc.el, formatCalcResult(val));
            clientLogger.info("app.context_calc_confirm");
            setCalc(null);
          }}
          onClose={() => setCalc(null)}
        />
      )}
    </>,
    document.body,
  );
};

export default GlobalContextMenu;
