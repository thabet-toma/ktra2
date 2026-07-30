/**
 * N5-T7 — PriceOfferForm (F5) — Aseel-style مع 4 أنواع
 * المرجع: العروض والطلبيات.txt:4-9
 * القالب: SalesInvoiceEditor.tsx
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { PriceOffer, PriceOfferItem, PriceOfferStatus, PriceOfferType, Supplier, Item } from "../../../types";
import type { PriceOfferAttachment } from "../../../types/offer";
import type { PriceOfferScope } from "../../../services/firestoreService";
import {
  AseelAutocomplete,
  useAseelKeymap,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../../aseel";
import {
  Save, X, Loader2, AlertCircle, CheckCircle2, Trash2, Search, Info,
  FileText, Upload, Link2,
} from "lucide-react";
import { ItemSearchModal, productToItem } from "./ItemSearchModal";
import { ItemQuickCreateModal } from "../../items/ItemQuickCreateModal";
import { ProductCardModal } from "../../shared/ProductCardModal";
import { FilePreviewModal } from "../../shared/FilePreviewModal";
import { cloudinaryService } from "../../../services/cloudinaryService";
import { usePasteImageUpload } from "../../../utils/clipboardImage";
import {
  CommercialDocumentEditor,
  type CommercialHeaderField,
} from "../../shared/CommercialDocumentEditor";

// مستندا دورة الشراء؛ اتجاه العميل يخص شاشة البيع المنفصلة.
const OFFER_TYPES = [
  { v: "incoming_offer", l: "عرض سعر من مورد" },
  { v: "outgoing_order", l: "طلبية إلى مورد" },
];

const STATUS_LABELS: Record<string, string> = {
  initial: "مسودة", pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة", approved_for_shipping: "معتمد للشحن", rejected: "مرفوض",
};

/**
 * T-IMPOFFER — في الاستيراد يُقرأ العرض كقرار ملاءمة: «ملائم» تعني أنه صالح
 * للتحويل إلى صفقة، و«غير ملائم» تلزمها كتابة السبب. نفس المفاتيح، لغة أصدق.
 */
const IMPORT_STATUS_LABELS: Record<string, string> = {
  initial: "مسودة", pending_info: "بانتظار معلومات",
  under_discussion: "قيد المناقشة", approved_for_shipping: "ملائم", rejected: "غير ملائم",
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
  scope?: PriceOfferScope;
  isReadOnly?: boolean;
  saving?: boolean;
  onSave: (offer: Partial<PriceOffer>) => void | Promise<void>;
  onCancel: () => void;
  onStatusChangeRequest?: (offer: Partial<PriceOffer>, newStatus: PriceOfferStatus) => void;
}

import { formatMoney, formatNumber } from "@/utils/formatNumber";
const fmt = (n: number) => formatMoney(n);

export const PriceOfferForm: React.FC<Props> = ({
  offer, items, suppliers, isReadOnly = false, saving = false,
  scope = "purchase", onSave, onCancel, onStatusChangeRequest,
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
  // T-IMPOFFER: مبلغ الشحن كان مُخزَّناً في الخادم ومُمرَّراً في الطرفين لكن بلا
  // أي حقل إدخال في هذه الشاشة — «فش مبلغ الشحن» حرفياً.
  const [shippingCost, setShippingCost] = useState(String(offer.shippingCost ?? 0));
  const [shippingIncluded, setShippingIncluded] = useState(Boolean(offer.shippingIncluded));
  const [alibabaLink, setAlibabaLink] = useState(offer.alibabaLink || "");
  const [supplierContact, setSupplierContact] = useState(offer.supplierContact || "");
  const [decisionReason, setDecisionReason] = useState(offer.decisionReason || "");
  const [attachments, setAttachments] = useState<PriceOfferAttachment[]>(offer.attachments || []);
  const [uploading, setUploading] = useState(false);
  const [previewFile, setPreviewFile] = useState<PriceOfferAttachment | null>(null);
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
  const [itemPickerLineKey, setItemPickerLineKey] = useState<string | null>(null);
  const [availableItems, setAvailableItems] = useState<Item[]>(items);
  // T-IMPOFFER: نفس مسار الإدخال المعتمد في باقي المنصة (فاتورة الشراء/الصفقة):
  // إكمال تلقائي داخل الخلية، إنشاء صنف من النص الحر، وبطاقة الصنف عبر (i).
  const [inlineCreate, setInlineCreate] = useState<{ lineKey: string; name: string } | null>(null);
  const [cardProductId, setCardProductId] = useState<number | null>(null);

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
    setShippingCost(String(offer.shippingCost ?? 0));
    setShippingIncluded(Boolean(offer.shippingIncluded));
    setAlibabaLink(offer.alibabaLink || "");
    setSupplierContact(offer.supplierContact || "");
    setDecisionReason(offer.decisionReason || "");
    setAttachments(offer.attachments || []);
    setInternalNotes(offer.internalNotes || "");
    setTaxRate(String(offer.taxRate ?? 0));
    setDiscountAmount(String(offer.discountAmount ?? 0));
    setLines(offer.items?.length ? offer.items.map((it) => ({ ...it, key: newLineKey() })) : [blankLine()]);
  }, [offer.id]);

  useEffect(() => {
    setAvailableItems(items);
  }, [items]);

  // حساب الإجماليات — نفس قاعدة الخادم (`SupplierQuotationSerializer._recalculate`):
  // الشحن يُضاف إلى الإجمالي إلا إذا كانت الأسعار تشمله، وإلا لاختلف الرقم
  // المعروض عن الرقم المحفوظ.
  const subtotal = lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unitPrice) || 0), 0);
  const disc = Number(discountAmount) || 0;
  const afterDiscount = Math.max(0, subtotal - disc);
  const tax = afterDiscount * (Number(taxRate) || 0) / 100;
  const shipping = shippingIncluded ? 0 : (Number(shippingCost) || 0);
  const grandTotal = afterDiscount + tax + shipping;

  const selectedSupplier = suppliers.find((s) => s.id === supplierId);
  const supplierAddress = selectedSupplier
    ? [selectedSupplier.street, selectedSupplier.city, selectedSupplier.country].filter(Boolean).join(", ")
    : "";

  const buildPayload = useCallback((): Partial<PriceOffer> => ({
    ...offer,
    offerNumber,
    supplierId,
    factoryName: selectedSupplier?.tradeName || factoryName,
    offerType,
    offerDate,
    validUntil: validUntil || undefined,
    currency,
    exchangeRate: Number(exchangeRate) || 1,
    status,
    shippingMethod,
    paymentMethod,
    shippingCost: Number(shippingCost) || 0,
    shippingIncluded,
    alibabaLink: alibabaLink.trim(),
    supplierContact: supplierContact.trim(),
    decisionReason: status === "rejected" ? decisionReason.trim() : "",
    attachments,
    deliveryDays: deliveryDays ? Number(deliveryDays) : undefined,
    internalNotes,
    taxRate: Number(taxRate) || 0,
    discountAmount: Number(discountAmount) || 0,
    subtotal,
    taxAmount: tax,
    grandTotal,
    items: lines
      .filter((line) => line.itemId)
      .map(({ key: _k, ...rest }) => ({
        ...rest,
        totalPrice: (Number(rest.quantity) || 0) * (Number(rest.unitPrice) || 0),
      })),
    supplierSnapshot: selectedSupplier ? {
      tradeName: selectedSupplier.tradeName,
      alias: selectedSupplier.alias,
      address: supplierAddress,
      salesRepName: selectedSupplier.salesRepName,
      salesRepPhone: selectedSupplier.salesRepPhone,
    } : offer.supplierSnapshot,
    updatedAt: new Date().toISOString(),
    createdAt: offer.createdAt || new Date().toISOString(),
    createdBy: offer.createdBy || "user",
  }), [offer, offerNumber, supplierId, factoryName, selectedSupplier, supplierAddress, offerType, offerDate, validUntil,
    currency, exchangeRate, status, shippingMethod, paymentMethod, shippingCost, shippingIncluded,
    alibabaLink, supplierContact, decisionReason, attachments,
    deliveryDays, internalNotes, taxRate, discountAmount, subtotal, tax, grandTotal, lines]);

  const handleSave = async () => {
    if (!supplierId) { setErr("اختر المورد."); return; }
    if (!lines.some((line) => line.itemId && Number(line.quantity) > 0)) {
      setErr("اختر صنفاً واحداً على الأقل وحدد كميته.");
      return;
    }
    // T-IMPOFFER: «غير ملائم» بلا سبب لا يُحفظ في نطاق الاستيراد — الخادم يرفضه
    // أيضاً، والتحقّق هنا يوفّر رحلة شبكة ويضع الرسالة قرب الحقل. الشراء المحلي
    // لم يُطلب تغييره فيبقى السبب اختيارياً فيه.
    if (scope === "import" && status === "rejected" && !decisionReason.trim()) {
      setErr("اذكر سبب اعتبار العرض غير ملائم.");
      return;
    }
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

  /** تعبئة سطر من صنف مختار — مشتركة بين الإكمال التلقائي والمنتقي والإنشاء السريع. */
  const fillLineWithItem = useCallback((lineKey: string, item: Item, lastPrice?: number) => {
    setLines((prev) => prev.map((line) => line.key === lineKey ? {
      ...line,
      id: line.id || crypto.randomUUID(),
      itemId: item.id,
      name: item.name,
      categoryId: item.categoryId,
      categoryName: item.categoryName,
      specifications: item.specifications || "",
      imageUrls: item.imageUrls || [],
      hsCodePrimary: item.hsCodePrimary || "",
      modelNumber: item.modelNumber,
      unitPrice: lastPrice ?? item.salePrice ?? line.unitPrice ?? 0,
    } : line));
  }, []);

  const itemOptions = useMemo(
    () => availableItems.map((item) => ({
      id: item.id,
      label: item.name,
      sub: item.modelNumber || item.categoryName || undefined,
    })),
    [availableItems],
  );

  /** T-IMPOFFER: رفع ملف عرض السعر — روابط مستضافة عبر نفس خدمة الوسائط. */
  const uploadAttachmentFiles = async (files: File[]) => {
    if (files.length === 0) return;
    setUploading(true);
    setErr(null);
    try {
      const uploaded: PriceOfferAttachment[] = [];
      for (const file of files) {
        const url = await cloudinaryService.uploadFile(file);
        uploaded.push({ name: file.name, url, type: file.type, size: file.size });
      }
      setAttachments((prev) => [...prev, ...uploaded]);
    } catch (cause) {
      setErr(cause instanceof Error ? cause.message : "فشل رفع الملف");
    } finally {
      setUploading(false);
    }
  };

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files: File[] = Array.from(event.target.files ?? []) as File[];
    event.target.value = "";
    await uploadAttachmentFiles(files);
  };

  // لصق صورة من الحافظة (Ctrl+V) بدل رفعها كملف.
  usePasteImageUpload((files) => { void uploadAttachmentFiles(files); }, !uploading);

  const removeAttachment = (index: number) =>
    setAttachments((prev) => prev.filter((_, i) => i !== index));

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
  /**
   * T-IMPOFFER — «طريقة اختيار المنتجات خطأ، لازم زي باقي المنصة».
   *
   * كانت الخلية زرّاً يفتح `ItemSearchModal` العريض: مسار مختلف عن كل شاشة أخرى
   * (فاتورة الشراء، الصفقة، فاتورة البيع) التي تكتب اسم الصنف داخل الخلية.
   * الآن نفس المكوّن المشترك `AseelAutocomplete`: كتابة ← قائمة مرشَّحة ←
   * «إضافة كصنف جديد» للنص الحر، مع (i) لبطاقة الصنف. المنتقي العريض باقٍ خلف
   * أيقونة البحث لمن يريد الفهرس الكامل.
   */
  gridColumns[1].render = (row: LineItem) => (
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <AseelAutocomplete
        value={row.name || ""}
        options={itemOptions}
        disabled={isReadOnly}
        placeholder="اكتب اسم الصنف…"
        onPick={(id) => {
          const item = availableItems.find((candidate) => String(candidate.id) === String(id));
          if (item) fillLineWithItem(row.key, item);
        }}
        onInfo={(id) => { const pid = Number(id); if (pid) setCardProductId(pid); }}
        onFreeText={(text) => setInlineCreate({ lineKey: row.key, name: text.trim() })}
      />
      {row.itemId && (
        <button
          type="button"
          className="aseel-ellipsis"
          onClick={() => setCardProductId(Number(row.itemId))}
          title="بطاقة الصنف"
        ><Info className="h-3.5 w-3.5" /></button>
      )}
      {!isReadOnly && (
        <button
          type="button"
          className="aseel-ellipsis"
          onClick={() => setItemPickerLineKey(row.key)}
          title="فهرس الأصناف الكامل"
        ><Search className="h-3.5 w-3.5" /></button>
      )}
    </div>
  );

  const banner = (err || msg) ? (
    <div className={`aseel-banner ${err ? "aseel-banner--err" : "aseel-banner--ok"}`}>
      {err ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{err || msg}</span>
    </div>
  ) : null;

  const notesTab = (
    <div className="px-1 py-2">
      <textarea className="aseel-input w-full" rows={4}
        disabled={isReadOnly} value={internalNotes}
        onChange={(e) => setInternalNotes(e.target.value)}
        placeholder="ملاحظات داخلية…" />
    </div>
  );

  const shippingTab = (
    <div className="grid grid-cols-1 gap-2 px-1 py-2 md:grid-cols-3">
      <label className="aseel-field">
        <span className="aseel-field-label">طريقة الشحن</span>
        <input className="aseel-input" disabled={isReadOnly}
          value={shippingMethod} onChange={(e) => setShippingMethod(e.target.value)} />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">طريقة الدفع</span>
        <input className="aseel-input" disabled={isReadOnly}
          value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">مدة التسليم (يوم)</span>
        <input className="aseel-input" type="number" min="0" disabled={isReadOnly}
          value={deliveryDays} onChange={(e) => setDeliveryDays(e.target.value)} />
      </label>
      {/* T-IMPOFFER: مبلغ الشحن المقدَّر — كان غائباً عن الشاشة كلياً. */}
      <label className="aseel-field">
        <span className="aseel-field-label">مبلغ الشحن المقدَّر</span>
        <input className="aseel-input" type="number" min="0" step="0.01"
          disabled={isReadOnly || shippingIncluded}
          value={shippingCost} onChange={(e) => setShippingCost(e.target.value)} />
      </label>
      <label className="aseel-field aseel-field--inline">
        <input type="checkbox" disabled={isReadOnly}
          checked={shippingIncluded}
          onChange={(e) => setShippingIncluded(e.target.checked)} />
        <span className="aseel-field-label" style={{ flex: "unset" }}>
          الأسعار تشمل الشحن
        </span>
      </label>
    </div>
  );

  /** T-IMPOFFER: مصدر العرض — رابط علي بابا ورقم التواصل مع مندوب المورد. */
  const sourceTab = (
    <div className="grid grid-cols-1 gap-2 px-1 py-2 md:grid-cols-2">
      <label className="aseel-field">
        <span className="aseel-field-label">رابط علي بابا / المصدر</span>
        <input className="aseel-input" dir="ltr" disabled={isReadOnly}
          value={alibabaLink} onChange={(e) => setAlibabaLink(e.target.value)}
          placeholder="https://www.alibaba.com/product-detail/…" />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">رقم التواصل مع المورد</span>
        <input className="aseel-input" dir="ltr" disabled={isReadOnly}
          value={supplierContact} onChange={(e) => setSupplierContact(e.target.value)}
          placeholder="+86 138 0000 0000" />
      </label>
      {alibabaLink.trim() && (
        <a className="aseel-hint flex items-center gap-1 hover:underline md:col-span-2"
          href={alibabaLink.trim()} target="_blank" rel="noopener noreferrer">
          <Link2 className="h-3.5 w-3.5" />
          <span>افتح صفحة المنتج عند المورد</span>
        </a>
      )}
    </div>
  );

  /**
   * T-IMPOFFER: ملفات عرض السعر. النقر على الملف يفتح معاينة **وسط الصفحة**
   * (`FilePreviewModal`) بدل تبويب جديد كما في `AttachmentsSection`.
   */
  const attachmentsTab = (
    <div className="space-y-2 px-1 py-2">
      {!isReadOnly && (
        <div>
          <input id="price-offer-file" type="file" multiple className="hidden"
            accept=".pdf,image/*"
            disabled={uploading} onChange={(e) => void handleUpload(e)} />
          <label htmlFor="price-offer-file"
            className="flex h-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-[var(--color-border)] text-xs hover:bg-[var(--color-surface-2)]">
            {uploading
              ? <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
              : <Upload className="h-5 w-5 text-[var(--color-text-muted)]" />}
            <span className="text-[var(--color-text-muted)]">
              {uploading ? "جاري الرفع…" : "اضغط لرفع ملف عرض السعر (PDF أو صورة)"}
            </span>
          </label>
        </div>
      )}
      {attachments.length === 0 ? (
        <p className="aseel-hint text-center">لا توجد ملفات مرفوعة لهذا العرض</p>
      ) : (
        <ul className="space-y-1">
          {attachments.map((file, index) => (
            <li key={`${file.url}-${index}`}
              className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5">
              <button type="button"
                className="flex min-w-0 flex-1 items-center gap-2 text-right text-xs font-semibold hover:text-blue-600"
                onClick={() => setPreviewFile(file)}
                title="عرض الملف في نافذة وسط الشاشة">
                <FileText className="h-4 w-4 shrink-0 text-red-500" />
                <span className="truncate">{file.name || file.url}</span>
                {file.size ? (
                  <span className="shrink-0 text-[10px] aseel-text-soft">
                    {formatNumber(file.size / 1024, { maxDecimals: 1 })} KB
                  </span>
                ) : null}
              </button>
              {!isReadOnly && (
                <button type="button" className="aseel-iconbtn aseel-iconbtn--danger"
                  onClick={() => removeAttachment(index)} title="إزالة الملف">
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  /** T-IMPOFFER: قرار الملاءمة وسببه — يُقرأ داخل العرض لا في القائمة وحدها. */
  const decisionTab = (
    <div className="space-y-2 px-1 py-2">
      <p className="aseel-hint">
        {status === "rejected"
          ? "هذا العرض غير ملائم — سيظهر مشطوباً في القائمة."
          : status === "approved_for_shipping"
            ? "هذا العرض ملائم — يمكن تحويله إلى صفقة استيراد من قائمة العروض."
            : "لم يُتَّخذ قرار الملاءمة بعد."}
      </p>
      <label className="aseel-field">
        <span className="aseel-field-label">
          سبب عدم الملاءمة {status === "rejected" ? "*" : ""}
        </span>
        <textarea className="aseel-input w-full" rows={3}
          disabled={isReadOnly || status !== "rejected"}
          value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)}
          placeholder="مثال: السعر أعلى من السوق بـ20% / مدة التسليم 90 يوماً" />
      </label>
    </div>
  );

  const statusLabels = scope === "import" ? IMPORT_STATUS_LABELS : STATUS_LABELS;

  const headerFields: CommercialHeaderField[] = [
    {
      key: "number",
      label: "رقم العرض",
      control: <input className="aseel-input aseel-input--hl" disabled={isReadOnly}
        value={offerNumber} onChange={(e) => setOfferNumber(e.target.value)} placeholder="تلقائي" />,
    },
    {
      key: "date",
      label: "التاريخ",
      control: <input className="aseel-input" type="date" disabled={isReadOnly}
        value={offerDate} onChange={(e) => setOfferDate(e.target.value)} />,
    },
    {
      key: "validUntil",
      label: "صالح حتى",
      control: <input className="aseel-input" type="date" disabled={isReadOnly}
        value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />,
    },
    {
      key: "type",
      label: "نوع العرض",
      control: (
        <select className="aseel-input" disabled={isReadOnly}
          value={offerType} onChange={(e) => setOfferType(e.target.value as PriceOfferType)}>
          {OFFER_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
        </select>
      ),
    },
    {
      key: "party",
      label: "المورد / الحساب",
      control: (
        <select className="aseel-input" disabled={isReadOnly}
          value={supplierId} onChange={(e) => {
            setSupplierId(e.target.value);
            const supplier = suppliers.find((item) => item.id === e.target.value);
            if (supplier) setFactoryName(supplier.tradeName);
          }}>
          <option value="">— اختر المورد —</option>
          {suppliers.map((supplier) => (
            <option key={supplier.id} value={supplier.id}>{supplier.tradeName}</option>
          ))}
        </select>
      ),
    },
    {
      key: "partyName",
      label: "الاسم",
      control: <input className="aseel-input" readOnly value={selectedSupplier?.tradeName ?? factoryName} />,
    },
    {
      key: "currency",
      label: "العملة",
      control: (
        <select className="aseel-input" disabled={isReadOnly}
          value={currency} onChange={(e) => setCurrency(e.target.value)}>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
          <option value="ILS">ILS</option>
        </select>
      ),
    },
    {
      key: "exchangeRate",
      label: "سعر العملة",
      control: <input className="aseel-input" type="number" min="0" step="0.001"
        disabled={isReadOnly} value={exchangeRate} onChange={(e) => setExchangeRate(e.target.value)} />,
    },
    {
      key: "status",
      label: scope === "import" ? "قرار الملاءمة" : "الحالة",
      control: (
        <select className="aseel-input" disabled={isReadOnly}
          value={status} onChange={(e) => setStatus(e.target.value as PriceOfferStatus)}>
          {Object.entries(statusLabels).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      ),
    },
  ];

  return (
    <CommercialDocumentEditor<LineItem>
      title={scope === "import" ? "عرض / طلبية استيراد" : "عرض سعر / طلبية شراء"}
      state={`${statusLabels[status]} — ${OFFER_TYPES.find((t) => t.v === offerType)?.l ?? offerType}`}
      actions={toolbarActions}
      headerFields={headerFields}
      lines={lines}
      lineColumns={gridColumns}
      getLineCell={gridGetCell}
      getLineKey={(line) => line.key}
      onLineChange={gridOnChange}
      onAddLine={addLine}
      readOnly={isReadOnly}
      banner={banner}
      tabs={[
        { key: "notes", label: "الملاحظات", content: notesTab },
        { key: "shipping", label: "بيانات الشحن", content: shippingTab },
        { key: "source", label: "مصدر العرض", content: sourceTab },
        {
          key: "attachments",
          label: attachments.length ? `الملفات (${attachments.length})` : "الملفات",
          content: attachmentsTab,
        },
        { key: "decision", label: "قرار الملاءمة", content: decisionTab },
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
          disabled={isReadOnly || scope === "import"} value={scope === "import" ? "0" : taxRate}
              onChange={(e) => setTaxRate(e.target.value)} />
          </div>
          <div className="aseel-total-row">
            <span>الضريبة</span>
            <span className="aseel-total-value">{fmt(tax)}</span>
          </div>
          {/* T-IMPOFFER: الشحن ظاهر في الإجماليات لا مخفياً في تبويب. */}
          <div className="aseel-total-row">
            <span>{shippingIncluded ? "الشحن (مشمول بالأسعار)" : "الشحن المقدَّر"}</span>
            <span className="aseel-total-value">{fmt(shipping)}</span>
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
      overlay={<>
        <ItemSearchModal
          isOpen={itemPickerLineKey !== null}
          onClose={() => setItemPickerLineKey(null)}
          items={availableItems}
          supplierId={supplierId}
          onItemCreated={(item) => {
            setAvailableItems((prev) => prev.some((row) => row.id === item.id) ? prev : [...prev, item]);
          }}
          onSelectItem={(item, lastPrice) => {
            if (!itemPickerLineKey) return;
            fillLineWithItem(itemPickerLineKey, item, lastPrice);
            setItemPickerLineKey(null);
          }}
        />
        {/* النص الحر يُنشئ صنفاً فعلياً (Product) بدل سطر بلا itemId يُحذف عند الحفظ. */}
        {inlineCreate && (
          <ItemQuickCreateModal
            isOpen
            initialName={inlineCreate.name}
            onClose={() => setInlineCreate(null)}
            onSaved={(newProduct) => {
              const item = productToItem(newProduct);
              setAvailableItems((prev) => prev.some((row) => row.id === item.id) ? prev : [...prev, item]);
              fillLineWithItem(inlineCreate.lineKey, item);
              setInlineCreate(null);
            }}
          />
        )}
        {cardProductId != null && (
          <ProductCardModal
            productId={cardProductId}
            onClose={() => setCardProductId(null)}
          />
        )}
        <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
      </>}
    />
  );
};
