/**
 * N5-T7 — PriceOfferForm (F5) — Aseel-style مع 4 أنواع
 * المرجع: العروض والطلبيات.txt:4-9
 * القالب: SalesInvoiceEditor.tsx
 */
import React, { useState, useEffect, useCallback } from "react";
import { PriceOffer, PriceOfferItem, PriceOfferStatus, PriceOfferType, Supplier, Item } from "../../../types";
import {
  AseelDocumentShell,
  AseelGrid,
  useAseelKeymap,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../../aseel";
import { Plus, Save, X, Loader2, AlertCircle, CheckCircle2, Trash2 } from "lucide-react";

// 4 أنواع العروض والطلبيات
const OFFER_TYPES = [
  { v: "incoming_offer", l: "عرض سعر وارد (من مورد)" },
  { v: "outgoing_offer", l: "عرض سعر صادر (للعميل)" },
  { v: "incoming_order", l: "طلبية واردة (من عميل)" },
  { v: "outgoing_order", l: "طلبية صادرة (للمورد)" },
];

const STATUS_LABELS: Record<string, string> = {
  initial: "مسودة", pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة", approved_for_shipping: "معتمد للشحن", rejected: "مرفوض",
};

type LineItem = PriceOfferItem & { key: string };
const newLineKey = () => `ln-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
const blankLine = (): LineItem => ({
  key: newLineKey(),
  id: "", itemId: "", name: "",
  categoryId: "", categoryName: "",
  specifications: "", imageUrls: [],
  hsCodePrimary: "",
  quantity: 0, unitPrice: 0, totalPrice: 0,
});

interface Props {
  offer: Partial<PriceOffer>;
  items: Item[];
  suppliers: Supplier[];
  isReadOnly?: boolean;
  saving?: boolean;
  onSave: (offer: Partial<PriceOffer>) => void | Promise<void>;
  onCancel: () => void;
  onStatusChangeRequest?: (offer: Partial<PriceOffer>, newStatus: PriceOfferStatus) => void;
}

const fld = (label: string, node: React.ReactNode, span?: number) => (
  <label className="aseel-field" style={span ? { gridColumn: `span ${span}` } : {}}>
    <span className="aseel-field-label">{label}</span>
    {node}
  </label>
);

const fmt = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const PriceOfferForm: React.FC<Props> = ({
  offer, items, suppliers, isReadOnly = false, saving = false,
  onSave, onCancel, onStatusChangeRequest,
}) => {
  const [offerNumber, setOfferNumber] = useState(offer.offerNumber || "");
  const [supplierId, setSupplierId] = useState(offer.supplierId || "");
  const [factoryName, setFactoryName] = useState(offer.factoryName || "");
  const [offerDate, setOfferDate] = useState(
    offer.offerDate || new Date().toISOString().slice(0, 10)
  );
  const [validUntil, setValidUntil] = useState(offer.validUntil || "");
  const [offerType, setOfferType] = useState<PriceOfferType>(offer.offerType || "incoming_offer");
  const [status, setStatus] = useState<PriceOfferStatus>(offer.status || "initial");
  const [currency, setCurrency] = useState(offer.currency || "USD");
  const [exchangeRate, setExchangeRate] = useState(String(offer.exchangeRate ?? 1));
  const [shippingMethod, setShippingMethod] = useState(offer.shippingMethod || "");
  const [paymentMethod, setPaymentMethod] = useState(offer.paymentMethod || "");
  const [deliveryDays, setDeliveryDays] = useState(String(offer.deliveryDays ?? ""));
  const [internalNotes, setInternalNotes] = useState(offer.internalNotes || "");
  const [taxRate, setTaxRate] = useState(String(offer.taxRate ?? 0));
  const [discountAmount, setDiscountAmount] = useState(String(offer.discountAmount ?? 0));
  const [lines, setLines] = useState<LineItem[]>(() =>
    offer.items?.length
      ? offer.items.map((it) => ({ ...it, key: newLineKey() }))
      : [blankLine()]
  );
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [lastKey, setLastKey] = useState("—");

  // إعادة تحميل عند تغيير offer prop
  useEffect(() => {
    setOfferNumber(offer.offerNumber || "");
    setSupplierId(offer.supplierId || "");
    setFactoryName(offer.factoryName || "");
    setOfferDate(offer.offerDate || new Date().toISOString().slice(0, 10));
    setValidUntil(offer.validUntil || "");
    setOfferType(offer.offerType || "incoming_offer");
    setCurrency(offer.currency || "USD");
    setExchangeRate(String(offer.exchangeRate ?? 1));
    setStatus(offer.status || "initial");
    setShippingMethod(offer.shippingMethod || "");
    setPaymentMethod(offer.paymentMethod || "");
    setDeliveryDays(String(offer.deliveryDays ?? ""));
    setInternalNotes(offer.internalNotes || "");
    setTaxRate(String(offer.taxRate ?? 0));
    setDiscountAmount(String(offer.discountAmount ?? 0));
    setLines(offer.items?.length ? offer.items.map((it) => ({ ...it, key: newLineKey() })) : [blankLine()]);
  }, [offer.id]);

  // حساب الإجماليات
  const subtotal = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unitPrice) || 0), 0);
  const disc = Number(discountAmount) || 0;
  const afterDiscount = Math.max(0, subtotal - disc);
  const tax = afterDiscount * (Number(taxRate) || 0) / 100;
  const grandTotal = afterDiscount + tax;

  const selectedSupplier = suppliers.find((s) => s.id === supplierId);

  const buildPayload = useCallback((): Partial<PriceOffer> => ({
    ...offer,
    offerNumber,
    supplierId,
    factoryName,
    offerType,
    offerDate,
    validUntil: validUntil || undefined,
    currency,
    exchangeRate: Number(exchangeRate) || 1,
    status,
    shippingMethod,
    paymentMethod,
    deliveryDays: deliveryDays ? Number(deliveryDays) : undefined,
    internalNotes,
    taxRate: Number(taxRate) || 0,
    discountAmount: Number(discountAmount) || 0,
    subtotal,
    taxAmount: tax,
    grandTotal,
    items: lines.map(({ key: _k, ...rest }) => ({ ...rest, totalPrice: (Number(rest.quantity) || 0) * (Number(rest.unitPrice) || 0) })),
    updatedAt: new Date().toISOString(),
    createdAt: offer.createdAt || new Date().toISOString(),
    createdBy: offer.createdBy || "user",
  }), [offer, offerNumber, supplierId, factoryName, offerType, offerDate, validUntil,
    currency, exchangeRate, status, shippingMethod, paymentMethod,
    deliveryDays, internalNotes, taxRate, discountAmount, subtotal, tax, grandTotal, lines]);

  const handleSave = async () => {
    if (!supplierId) { setErr("اختر المورد."); return; }
    setErr(null); setMsg(null);
    try {
      await onSave(buildPayload());
      setMsg("تم الحفظ.");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    }
  };

  const addLine = () => setLines((prev) => [...prev, blankLine()]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const updateLine = (key: string, patch: Partial<LineItem>) =>
    setLines((prev) => prev.map((l) => l.key === key ? { ...l, ...patch } : l));

  useAseelKeymap({
    F12: () => { setLastKey("F12 حفظ"); if (!saving && !isReadOnly) void handleSave(); },
    Escape: () => { setLastKey("Esc إلغاء"); onCancel(); },
    CtrlIns: () => { setLastKey("Ctrl+Ins سطر"); addLine(); },
  }, { enabled: true });

  const toolbarActions: AseelToolbarAction[] = [
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: !isReadOnly && !saving ? () => void handleSave() : undefined,
      disabled: isReadOnly || saving },
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: onCancel, danger: true, separatorBefore: true },
    { key: "print", label: "طباعة", icon: <Save />, onClick: () => window.print() },
  ];

  // ── أعمدة جدول البنود ──
  const gridColumns: AseelGridColumn<LineItem>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "name", header: "بيان الصنف", width: "35%" },
    { key: "specifications", header: "مواصفات", width: "20%" },
    { key: "hsCodePrimary", header: "كود HS", width: "110px" },
    { key: "quantity", header: "الكمية", width: "90px", align: "center", type: "number" },
    { key: "unitPrice", header: "سعر الوحدة", width: "110px", align: "center", type: "number" },
    { key: "total", header: "الإجمالي", width: "110px", align: "center", readOnly: true },
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const gridGetCell = (row: LineItem, key: string): string | number => {
    const idx = lines.findIndex((l) => l.key === row.key);
    if (key === "seq") return idx + 1;
    if (key === "name") return row.name;
    if (key === "specifications") return row.specifications || "";
    if (key === "hsCodePrimary") return row.hsCodePrimary || "";
    if (key === "quantity") return String(row.quantity);
    if (key === "unitPrice") return String(row.unitPrice);
    if (key === "total") return fmt((Number(row.quantity) || 0) * (Number(row.unitPrice) || 0));
    return "";
  };

  const gridOnChange = (rowIdx: number, key: string, val: string) => {
    const row = lines[rowIdx];
    if (!row) return;
    const patch: Partial<LineItem> = {};
    if (key === "name") patch.name = val;
    else if (key === "specifications") patch.specifications = val;
    else if (key === "hsCodePrimary") patch.hsCodePrimary = val;
    else if (key === "quantity") patch.quantity = Number(val) || 0;
    else if (key === "unitPrice") patch.unitPrice = Number(val) || 0;
    updateLine(row.key, patch);
  };

  gridColumns[gridColumns.length - 1].render = (row: LineItem) =>
    isReadOnly ? null : (
      <button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => removeLine(row.key)}>
        <Trash2 className="h-3 w-3" />
      </button>
    );

  const banner = (err || msg) ? (
    <div className={`aseel-banner ${err ? "aseel-banner--err" : "aseel-banner--ok"}`}>
      {err ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{err || msg}</span>
    </div>
  ) : null;

  const notesTab = (
    <div style={{ padding: "8px 4px" }}>
      <textarea className="aseel-input" rows={4} style={{ width: "100%" }}
        disabled={isReadOnly} value={internalNotes}
        onChange={(e) => setInternalNotes(e.target.value)}
        placeholder="ملاحظات داخلية…" />
    </div>
  );

  const shippingTab = (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, padding: "8px 4px" }}>
      {fld("طريقة الشحن", <input className="aseel-input" disabled={isReadOnly}
        value={shippingMethod} onChange={(e) => setShippingMethod(e.target.value)} />)}
      {fld("طريقة الدفع", <input className="aseel-input" disabled={isReadOnly}
        value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} />)}
      {fld("مدة التسليم (يوم)", <input className="aseel-input" type="number" min="0" disabled={isReadOnly}
        value={deliveryDays} onChange={(e) => setDeliveryDays(e.target.value)} />)}
    </div>
  );

  return (
    <div dir="rtl">
      <AseelDocumentShell
        title="عرض سعر / طلبية"
        state={`${STATUS_LABELS[status]} — ${OFFER_TYPES.find((t) => t.v === offerType)?.l ?? offerType}`}
        actions={toolbarActions}
        header={
          <>
            {fld("رقم العرض", <input className="aseel-input aseel-input--hl" disabled={isReadOnly}
              value={offerNumber} onChange={(e) => setOfferNumber(e.target.value)} placeholder="تلقائي" />)}
            {fld("التاريخ", <input className="aseel-input" type="date" disabled={isReadOnly}
              value={offerDate} onChange={(e) => setOfferDate(e.target.value)} />)}
            {fld("صالح حتى", <input className="aseel-input" type="date" disabled={isReadOnly}
              value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />)}
            {fld("نوع العرض", <select className="aseel-input" disabled={isReadOnly}
              value={offerType} onChange={(e) => setOfferType(e.target.value as PriceOfferType)}>
              {OFFER_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
            </select>)}
            {fld("المورد / الحساب", <select className="aseel-input" disabled={isReadOnly}
              value={supplierId} onChange={(e) => {
                setSupplierId(e.target.value);
                const s = suppliers.find((x) => x.id === e.target.value);
                if (s) setFactoryName(s.name);
              }}>
              <option value="">— اختر المورد —</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>)}
            {fld("الاسم", <input className="aseel-input" readOnly value={selectedSupplier?.name ?? factoryName} />)}
            {fld("العملة", <select className="aseel-input" disabled={isReadOnly}
              value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="ILS">ILS</option>
            </select>)}
            {fld("سعر العملة", <input className="aseel-input" type="number" min="0" step="0.001"
              disabled={isReadOnly} value={exchangeRate} onChange={(e) => setExchangeRate(e.target.value)} />)}
            {fld("الحالة", <select className="aseel-input" disabled={isReadOnly}
              value={status} onChange={(e) => setStatus(e.target.value as PriceOfferStatus)}>
              {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>)}
          </>
        }
        tabs={[
          { key: "notes", label: "الملاحظات", content: notesTab },
          { key: "shipping", label: "بيانات الشحن", content: shippingTab },
        ]}
        totals={
          <>
            <div className="aseel-total-row">
              <span>مجموع البنود</span>
              <span className="aseel-total-value">{fmt(subtotal)}</span>
            </div>
            <div className="aseel-total-row">
              <span>الخصم</span>
              <input className="aseel-input aseel-total-input" type="number" step="0.01" min="0"
                disabled={isReadOnly} value={discountAmount}
                onChange={(e) => setDiscountAmount(e.target.value)} />
            </div>
            <div className="aseel-total-row">
              <span>بعد الخصم</span>
              <span className="aseel-total-value">{fmt(afterDiscount)}</span>
            </div>
            <div className="aseel-total-row">
              <span>نسبة الضريبة %</span>
              <input className="aseel-input aseel-total-input" type="number" step="0.01" min="0"
                disabled={isReadOnly} value={taxRate}
                onChange={(e) => setTaxRate(e.target.value)} />
            </div>
            <div className="aseel-total-row">
              <span>الضريبة</span>
              <span className="aseel-total-value">{fmt(tax)}</span>
            </div>
            <div className="aseel-total-row aseel-total-row--grand">
              <span>إجمالي العرض</span>
              <span className="aseel-total-value">{fmt(grandTotal)} {currency}</span>
            </div>
          </>
        }
        status={
          <>
            <span className="aseel-status-item">عدد الأصناف <b>{lines.length}</b></span>
            <span className="aseel-status-item">آخر مفتاح <b>{lastKey}</b></span>
            {isReadOnly && <span className="aseel-status-item">للقراءة فقط</span>}
          </>
        }
      >
        {banner}
        <AseelGrid<LineItem>
          columns={gridColumns}
          rows={lines}
          getCell={gridGetCell}
          getRowKey={(l) => l.key}
          onChange={isReadOnly ? undefined : gridOnChange}
          onAddRow={isReadOnly ? undefined : addLine}
          emptyHint="لا توجد بنود — أضف صنفاً"
        />
        {!isReadOnly && (
          <button type="button" className="aseel-addrow" onClick={addLine}>
            <Plus className="h-3 w-3" /> إضافة سطر
          </button>
        )}
      </AseelDocumentShell>
    </div>
  );
};
