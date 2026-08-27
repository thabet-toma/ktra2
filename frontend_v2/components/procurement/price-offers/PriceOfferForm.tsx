/**
 * N5-T7 — PriceOfferForm (F5) — Kit-style مع 4 أنواع
 * المرجع: العروض والطلبيات.txt:4-9
 * القالب: SalesInvoiceEditor.tsx
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { PriceOffer, PriceOfferItem, PriceOfferStatus, PriceOfferType, Supplier, Item } from "../../../types";
import type { PriceOfferAttachment, PriceOfferNote } from "../../../types/offer";
import type { PriceOfferScope } from "../../../services/firestoreService";
import {
  KitAutocomplete,
  useKitKeymap,
  type KitGridColumn,
  type KitToolbarAction,
} from "../../kit";
import {
  Save, X, Loader2, AlertCircle, CheckCircle2, Trash2, Search, Info,
  FileText, Link2, Plus, Pencil, Share2,
} from "lucide-react";
import { formatDateValue } from "../../../utils/formatDate";
import { ItemSearchModal } from "./ItemSearchModal";
import { ProductCardModal } from "../../shared/ProductCardModal";
import { ItemQuickEditModal } from "../../items/ItemQuickEditModal";
import { FilePreviewModal } from "../../shared/FilePreviewModal";
import { ShareDocumentModal } from "../../shared/ShareDocumentModal";
import { cloudinaryService } from "../../../services/cloudinaryService";
import { FileDropZone } from "../../ui/FileDropZone";
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

/**
 * T-OFFERSTATE: حالتان لا تكفيهما التسمية — «غير ملائم» تلزمها **لماذا**،
 * و«بانتظار معلومات» تلزمها **بانتظار ماذا**. نفس قاعدة الخادم
 * (`SupplierQuotationSerializer.validate`) كي لا تختلف الواجهة عنه.
 */
const STATUS_NEEDS_DETAIL: PriceOfferStatus[] = ["rejected", "pending_info"];

const STATUS_DETAIL_LABEL: Partial<Record<PriceOfferStatus, string>> = {
  rejected: "سبب عدم الملاءمة",
  pending_info: "بانتظار ماذا؟",
};

const STATUS_DETAIL_PLACEHOLDER: Partial<Record<PriceOfferStatus, string>> = {
  rejected: "مثال: السعر أعلى من السوق بـ20% / مدة التسليم 90 يوماً",
  pending_info: "مثال: بانتظار شهادة المنشأ / عيّنة من المصنع / سعر الشحن",
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
}

import { formatMoney, formatNumber } from "@/utils/formatNumber";
const fmt = (n: number) => formatMoney(n);

export const PriceOfferForm: React.FC<Props> = ({
  offer, items, suppliers, isReadOnly = false, saving = false,
  scope = "purchase", onSave, onCancel,
}) => {
  const [offerNumber, setOfferNumber] = useState(offer.offerNumber || "");
  const [showShareModal, setShowShareModal] = useState(false);
  const [orderName, setOrderName] = useState(offer.orderName || "");
  const [orderDescription, setOrderDescription] = useState(offer.orderDescription || "");
  const [supplierId, setSupplierId] = useState(offer.supplierId || "");
  // T-DRAFTPARTY: مورد مبدئي مكتوب بالنص — لا شريك في الدفاتر حتى التحويل.
  const [supplierDraftName, setSupplierDraftName] = useState(offer.supplierDraftName || "");
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
  // T-OFFERSTATE: دفتر ملاحظات مؤرَّخ — ملاحظة واحدة تُدهس لا تكفي متابعةَ مورد.
  const [notesLog, setNotesLog] = useState<PriceOfferNote[]>(offer.notesLog || []);
  const [newNote, setNewNote] = useState("");
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
  // إكمال تلقائي داخل الخلية، ونص حرّ يبقى في العرض، وبطاقة المنتج عبر (i).
  const [cardProductId, setCardProductId] = useState<number | null>(null);
  // T-PRODUCT M4: هذه الشاشة وحدها كانت بلا طريق تعديلٍ للمنتج — بطاقةٌ تُقرأ ولا
  // تُكتب. الآن نفس قلم فاتورتَي البيع والشراء، وبنفس معالِج الانتشار.
  const [quickEditProductId, setQuickEditProductId] = useState<number | null>(null);

  // إعادة تحميل عند تغيير offer prop
  useEffect(() => {
    setOfferNumber(offer.offerNumber || "");
    setOrderName(offer.orderName || "");
    setOrderDescription(offer.orderDescription || "");
    setSupplierId(offer.supplierId || "");
    setSupplierDraftName(offer.supplierDraftName || "");
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
    setNotesLog(offer.notesLog || []);
    setNewNote("");
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
    orderName: orderName.trim(),
    orderDescription: orderDescription.trim(),
    supplierId,
    supplierDraftName: supplierId ? "" : supplierDraftName.trim(),
    factoryName: selectedSupplier?.tradeName || supplierDraftName.trim() || factoryName,
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
    // T-OFFERSTATE: التفصيل يلزم حالتين — «غير ملائم» (لماذا) و«بانتظار معلومات»
    // (بانتظار ماذا)؛ وما عداهما يُمحى كي لا يبقى تفصيل حالة سابقة معلّقاً.
    decisionReason: STATUS_NEEDS_DETAIL.includes(status) ? decisionReason.trim() : "",
    attachments,
    notesLog,
    deliveryDays: deliveryDays ? Number(deliveryDays) : undefined,
    internalNotes,
    taxRate: Number(taxRate) || 0,
    discountAmount: Number(discountAmount) || 0,
    subtotal,
    taxAmount: tax,
    grandTotal,
    // T-DRAFTPARTY: البند المكتوب يدوياً (بلا itemId) يبقى في العرض — كان يُحذف
    // صامتاً عند الحفظ، فيختفي ما كتبه المستخدم.
    items: lines
      .filter((line) => line.itemId || line.name.trim())
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
  }), [offer, offerNumber, orderName, orderDescription, supplierId, supplierDraftName, factoryName, selectedSupplier, supplierAddress, offerType, offerDate, validUntil,
    currency, exchangeRate, status, shippingMethod, paymentMethod, shippingCost, shippingIncluded,
    alibabaLink, supplierContact, decisionReason, attachments,
    deliveryDays, internalNotes, taxRate, discountAmount, subtotal, tax, grandTotal, lines]);

  const handleSave = async () => {
    // T-DRAFTPARTY: مورد مسجَّل **أو** اسم مبدئي؛ وكذلك البنود: منتج مختار أو اسم
    // مكتوب. الطلبية والصفقة تبقيان ملزمتين بالمسجَّل (يمنعهما مسار الحفظ نفسه).
    const isDraftDocument = offerType === "incoming_offer";
    if (!supplierId && !supplierDraftName.trim()) {
      setErr("اختر مورداً مسجَّلاً أو اكتب اسم المورد.");
      return;
    }
    if (!supplierId && !isDraftDocument) {
      setErr("الطلبية تلزمها مورد مسجَّل — المورد المبدئي متاح في عرض السعر فقط.");
      return;
    }
    const usableLines = lines.filter(
      (line) => (line.itemId || line.name.trim()) && Number(line.quantity) > 0,
    );
    if (usableLines.length === 0) {
      setErr("أضف منتجاً واحداً على الأقل (باختياره أو بكتابة اسمه) وحدد كميته.");
      return;
    }
    if (!isDraftDocument && usableLines.some((line) => !line.itemId)) {
      setErr("الطلبية تلزمها منتجات مسجَّلة — اختر المنتج من القائمة.");
      return;
    }
    // T-IMPOFFER: «غير ملائم» بلا سبب لا يُحفظ في نطاق الاستيراد — الخادم يرفضه
    // أيضاً، والتحقّق هنا يوفّر رحلة شبكة ويضع الرسالة قرب الحقل. الشراء المحلي
    // لم يُطلب تغييره فيبقى السبب اختيارياً فيه.
    // T-OFFERSTATE: و«بانتظار معلومات» تلزمها كتابة ما يُنتظَر — نفس القاعدة.
    if (scope === "import" && needsDetail && !decisionReason.trim()) {
      setErr(status === "rejected"
        ? "اذكر سبب اعتبار العرض غير ملائم."
        : "اذكر ما تنتظره من المورد.");
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

  /**
   * T-PRODUCT M4 — نفس عقد فاتورة الشراء: سطر العرض يلتقط الاسم نسخةً عند
   * الاختيار، فلا يكفي ترقيع الكتالوج وحده.
   */
  const applyProductUpdate = (updated: Record<string, unknown>) => {
    const id = Number(updated.id);
    if (!id) return;
    const name = String(updated.display_name ?? updated.name_ar ?? updated.name_en ?? "");
    setAvailableItems((prev) => prev.map((it) => (
      String(it.id) === String(id) ? { ...it, name } : it
    )));
    setLines((prev) => prev.map((l) => (
      String(l.itemId) === String(id) && l.name !== name ? { ...l, name } : l
    )));
  };

  const addLine = () => setLines((prev) => [...prev, blankLine()]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const updateLine = (key: string, patch: Partial<LineItem>) =>
    setLines((prev) => prev.map((l) => l.key === key ? { ...l, ...patch } : l));

  /** تعبئة سطر من منتج مختار — مشتركة بين الإكمال التلقائي والمنتقي والإنشاء السريع. */
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

  const supplierOptions = useMemo(
    () => suppliers.map((supplier) => ({
      id: supplier.id,
      label: supplier.tradeName,
      sub: supplier.alias || supplier.country || undefined,
    })),
    [suppliers],
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

  // الاختيار والسحب واللصق (Ctrl+V) صارت كلها داخل `FileDropZone` في تبويب الملفات.

  const removeAttachment = (index: number) =>
    setAttachments((prev) => prev.filter((_, i) => i !== index));

  useKitKeymap({
    F12: () => { setLastKey("F12 حفظ"); if (!saving && !isReadOnly) void handleSave(); },
    Escape: () => { setLastKey("Esc إلغاء"); onCancel(); },
    CtrlIns: () => { setLastKey("Ctrl+Ins سطر"); addLine(); },
  }, { enabled: true });

  const toolbarActions: KitToolbarAction[] = [
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: !isReadOnly && !saving ? () => void handleSave() : undefined,
      disabled: isReadOnly || saving },
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: onCancel, danger: true, separatorBefore: true },
    { key: "print", label: "طباعة", icon: <Save />, onClick: () => window.print() },
    // DOC-SHARE: العرض يعود إلى المورّد الذي كتبه — تأكيدُ ما اتُّفق عليه.
    // ويلزمه عرضٌ محفوظ: الرابط يشير إلى صفٍّ في القاعدة لا إلى مسوّدة ذاكرة.
    {
      key: "share",
      label: "مشاركة",
      icon: <Share2 />,
      disabled: offer.id == null,
      onClick: () => setShowShareModal(true),
    },
  ];

  // ── أعمدة جدول البنود ──
  const gridColumns: KitGridColumn<LineItem>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "name", header: "وصف المنتج", width: "35%" },
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
      <button type="button" className="ktra-iconbtn ktra-iconbtn--danger" onClick={() => removeLine(row.key)}>
        <Trash2 className="h-3 w-3" />
      </button>
    );
  /**
   * T-IMPOFFER — «طريقة اختيار المنتجات خطأ، لازم زي باقي المنصة».
   *
   * كانت الخلية زرّاً يفتح `ItemSearchModal` العريض: مسار مختلف عن كل شاشة أخرى
   * (فاتورة الشراء، الصفقة، فاتورة البيع) التي تكتب اسم المنتج داخل الخلية.
   * الآن نفس المكوّن المشترك `KitAutocomplete`: كتابة ← قائمة مرشَّحة ←
   * «إضافة كمنتج جديد» للنص الحر، مع (i) لبطاقة المنتج. المنتقي العريض باقٍ خلف
   * أيقونة البحث لمن يريد الفهرس الكامل.
   *
   * T-DRAFTPARTY: النص الحر لم يعد يفتح نافذة إنشاء منتج — يبقى **اسماً داخل
   * العرض**. العرض قد لا يُقبل أصلاً، فلا يجوز أن يترك منتجات في الفهرس؛
   * المنتج يُنشأ (أو يُطابَق بالاسم) لحظة تحويل العرض إلى صفقة/طلبية/فاتورة.
   */
  gridColumns[1].render = (row: LineItem) => (
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <KitAutocomplete
        value={row.name || ""}
        options={itemOptions}
        disabled={isReadOnly}
        placeholder="اكتب اسم المنتج…"
        onPick={(id) => {
          const item = availableItems.find((candidate) => String(candidate.id) === String(id));
          if (item) fillLineWithItem(row.key, item);
        }}
        onInfo={(id) => { const pid = Number(id); if (pid) setCardProductId(pid); }}
        onEdit={isReadOnly ? undefined : (id) => { const pid = Number(id); if (pid) setQuickEditProductId(pid); }}
        onFreeText={(text) => updateLine(row.key, {
          id: row.id || crypto.randomUUID(),
          itemId: "",
          name: text.trim(),
        })}
        createLabel={(text) => `إبقاء «${text}» كبند نصّي في العرض`}
      />
      {row.itemId && (
        <button
          type="button"
          className="ktra-ellipsis"
          onClick={() => setCardProductId(Number(row.itemId))}
          title="بطاقة المنتج"
        ><Info className="h-3.5 w-3.5" /></button>
      )}
      {row.itemId && !isReadOnly && (
        <button
          type="button"
          className="ktra-ellipsis"
          onClick={() => setQuickEditProductId(Number(row.itemId))}
          title="تعديل سريع للمنتج"
        ><Pencil className="h-3.5 w-3.5" /></button>
      )}
      {!isReadOnly && (
        <button
          type="button"
          className="ktra-ellipsis"
          onClick={() => setItemPickerLineKey(row.key)}
          title="فهرس المنتجات الكامل"
        ><Search className="h-3.5 w-3.5" /></button>
      )}
    </div>
  );

  const banner = (err || msg) ? (
    <div className={`ktra-banner ${err ? "ktra-banner--err" : "ktra-banner--ok"}`}>
      {err ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{err || msg}</span>
    </div>
  ) : null;

  /**
   * T-OFFERSTATE: الملاحظات كانت مربّعاً واحداً قصيراً يُدهس عند كل تعديل.
   * الآن: ملاحظة عامة أطول + **دفتر ملاحظات مؤرَّخ** يُضاف إليه بلا حدّ —
   * متابعة المورد سلسلةُ أحداث لا سطرٌ أخير.
   */
  const addNote = () => {
    const text = newNote.trim();
    if (!text) return;
    // بلا تاريخ هنا: الخادم يختمه عند الحفظ (ساعة المتصفح ليست مصدراً موثوقاً).
    setNotesLog((current) => [...current, { text }]);
    setNewNote("");
  };

  const notesTab = (
    <div className="space-y-3 px-1 py-2">
      <label className="ktra-field">
        <span className="ktra-field-label">ملاحظة عامة على العرض</span>
        <textarea className="ktra-input w-full" rows={6}
          disabled={isReadOnly} value={internalNotes}
          onChange={(e) => setInternalNotes(e.target.value)}
          placeholder="ملاحظات داخلية…" />
      </label>

      <div className="space-y-2">
        <span className="ktra-field-label">
          دفتر الملاحظات {notesLog.length > 0 && `(${notesLog.length})`}
        </span>
        {!isReadOnly && (
          <div className="flex items-start gap-2">
            <textarea className="ktra-input w-full" rows={3}
              value={newNote} onChange={(e) => setNewNote(e.target.value)}
              placeholder="أضف ملاحظة جديدة… (تُحفظ بتاريخها)" />
            <button type="button" className="ktra-btn shrink-0"
              disabled={!newNote.trim()} onClick={addNote}
              title="إضافة ملاحظة مؤرَّخة">
              <Plus className="h-4 w-4" /> إضافة
            </button>
          </div>
        )}
        {notesLog.length === 0 ? (
          <p className="ktra-hint">لا ملاحظات بعد — أضف ملاحظة لتبقى مؤرَّخة في سجل العرض.</p>
        ) : (
          <ul className="space-y-1.5">
            {notesLog.map((note, index) => (
              <li key={`${note.at || "new"}-${index}`}
                className="flex items-start justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5">
                <div className="min-w-0 flex-1">
                  <div className="whitespace-pre-wrap break-words text-xs ktra-text-ink">{note.text}</div>
                  <div className="mt-0.5 text-[10px] ktra-text-soft">
                    {note.at ? formatDateValue(note.at) : "ستُؤرَّخ عند الحفظ"}
                    {note.by ? ` · ${note.by}` : ""}
                  </div>
                </div>
                {!isReadOnly && (
                  <button type="button" className="ktra-iconbtn ktra-iconbtn--danger"
                    onClick={() => setNotesLog((current) => current.filter((_, i) => i !== index))}
                    title="حذف الملاحظة">
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );

  const shippingTab = (
    <div className="grid grid-cols-1 gap-2 px-1 py-2 md:grid-cols-3">
      <label className="ktra-field">
        <span className="ktra-field-label">طريقة الشحن</span>
        <input className="ktra-input" disabled={isReadOnly}
          value={shippingMethod} onChange={(e) => setShippingMethod(e.target.value)} />
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">طريقة الدفع</span>
        <input className="ktra-input" disabled={isReadOnly}
          value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)} />
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">مدة التسليم (يوم)</span>
        <input className="ktra-input" type="number" min="0" disabled={isReadOnly}
          value={deliveryDays} onChange={(e) => setDeliveryDays(e.target.value)} />
      </label>
      {/* T-IMPOFFER: مبلغ الشحن المقدَّر — كان غائباً عن الشاشة كلياً. */}
      <label className="ktra-field">
        <span className="ktra-field-label">مبلغ الشحن المقدَّر</span>
        <input className="ktra-input" type="number" min="0" step="0.01"
          disabled={isReadOnly || shippingIncluded}
          value={shippingCost} onChange={(e) => setShippingCost(e.target.value)} />
      </label>
      <label className="ktra-field ktra-field--inline">
        <input type="checkbox" disabled={isReadOnly}
          checked={shippingIncluded}
          onChange={(e) => setShippingIncluded(e.target.checked)} />
        <span className="ktra-field-label" style={{ flex: "unset" }}>
          الأسعار تشمل الشحن
        </span>
      </label>
    </div>
  );

  /** T-IMPOFFER: مصدر العرض — رابط علي بابا ورقم التواصل مع مندوب المورد. */
  const sourceTab = (
    <div className="grid grid-cols-1 gap-2 px-1 py-2 md:grid-cols-2">
      <label className="ktra-field">
        <span className="ktra-field-label">رابط علي بابا / المصدر</span>
        <input className="ktra-input" dir="ltr" disabled={isReadOnly}
          value={alibabaLink} onChange={(e) => setAlibabaLink(e.target.value)}
          placeholder="https://www.alibaba.com/product-detail/…" />
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">رقم التواصل مع المورد</span>
        <input className="ktra-input" dir="ltr" disabled={isReadOnly}
          value={supplierContact} onChange={(e) => setSupplierContact(e.target.value)}
          placeholder="+86 138 0000 0000" />
      </label>
      {alibabaLink.trim() && (
        <a className="ktra-hint flex items-center gap-1 hover:underline md:col-span-2"
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
        <FileDropZone
          onFiles={(files) => { void uploadAttachmentFiles(files); }}
          accept="image-pdf"
          multiple
          busy={uploading}
          variant="compact"
          hint="اضغط لرفع ملف عرض السعر، اسحبه إلى هنا، أو الصق صورة (Ctrl+V)"
          subHint="PDF أو صورة"
        />
      )}
      {attachments.length === 0 ? (
        <p className="ktra-hint text-center">لا توجد ملفات مرفوعة لهذا العرض</p>
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
                  <span className="shrink-0 text-[10px] ktra-text-soft">
                    {formatNumber(file.size / 1024, { maxDecimals: 1 })} KB
                  </span>
                ) : null}
              </button>
              {!isReadOnly && (
                <button type="button" className="ktra-iconbtn ktra-iconbtn--danger"
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

  /**
   * T-IMPOFFER: حالة العرض وتفصيلها — تُقرأ داخل العرض لا في القائمة وحدها.
   * T-OFFERSTATE: صارت «الحالة» لا «القرار»: الانتظار والمناقشة حالتان قبل أي
   * قرار، و«بانتظار معلومات» تلزمها كتابة ما يُنتظَر كي يظهر في القائمة.
   */
  const needsDetail = STATUS_NEEDS_DETAIL.includes(status);
  const decisionTab = (
    <div className="space-y-2 px-1 py-2">
      <p className="ktra-hint">
        {status === "rejected"
          ? "هذا العرض غير ملائم — سيظهر مشطوباً في القائمة."
          : status === "approved_for_shipping"
            ? "هذا العرض ملائم — يمكن تحويله إلى صفقة استيراد من قائمة العروض."
            : status === "pending_info"
              ? "العرض موقوف بانتظار معلومات — اكتب ما تنتظره ليظهر بجانب الحالة في القائمة."
              : status === "under_discussion"
                ? "العرض قيد المناقشة مع المورد — لم يُتَّخذ قرار بعد."
                : "لم تُحدَّد حالة العرض بعد."}
      </p>
      <label className="ktra-field">
        <span className="ktra-field-label">
          {STATUS_DETAIL_LABEL[status] || "تفصيل الحالة"} {needsDetail ? "*" : ""}
        </span>
        <textarea className="ktra-input w-full" rows={4}
          disabled={isReadOnly || !needsDetail}
          value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)}
          placeholder={STATUS_DETAIL_PLACEHOLDER[status]
            || "يُكتب عند «غير ملائم» أو «بانتظار معلومات»"} />
      </label>
    </div>
  );

  const statusLabels = scope === "import" ? IMPORT_STATUS_LABELS : STATUS_LABELS;

  const headerFields: CommercialHeaderField[] = [
    {
      key: "number",
      label: "رقم العرض",
      control: <input className="ktra-input ktra-input--hl" disabled={isReadOnly}
        value={offerNumber} onChange={(e) => setOfferNumber(e.target.value)} placeholder="تلقائي" />,
    },
    {
      key: "orderName",
      label: "اسم الطلبية",
      control: <input className="ktra-input" disabled={isReadOnly}
        value={orderName} onChange={(e) => setOrderName(e.target.value)}
        maxLength={200} placeholder="مثال: طلبية أثاث مكتبي" />,
    },
    {
      key: "orderDescription",
      label: "وصف الطلبية",
      control: <textarea className="ktra-input min-h-16 resize-y" disabled={isReadOnly}
        value={orderDescription} onChange={(e) => setOrderDescription(e.target.value)}
        placeholder="وصف مختصر يوضح محتوى الطلبية والغرض منها" />,
    },
    {
      key: "date",
      label: "التاريخ",
      control: <input className="ktra-input" type="date" disabled={isReadOnly}
        value={offerDate} onChange={(e) => setOfferDate(e.target.value)} />,
    },
    {
      key: "validUntil",
      label: "صالح حتى",
      control: <input className="ktra-input" type="date" disabled={isReadOnly}
        value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />,
    },
    {
      key: "type",
      label: "نوع العرض",
      control: (
        <select className="ktra-input" disabled={isReadOnly}
          value={offerType} onChange={(e) => setOfferType(e.target.value as PriceOfferType)}>
          {OFFER_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
        </select>
      ),
    },
    {
      key: "party",
      label: "المورد / الحساب",
      /**
       * T-DRAFTPARTY: القائمة المنسدلة كانت تحصر العرض بموردٍ مسجَّل، فيُسجَّل
       * مورد وهمي لكل عرض استكشافي. الآن مربّع بحث كفواتير البيع: أول حرف يقترح
       * المشابه، والاسم الجديد يبقى **مبدئياً** حتى التحويل.
       */
      control: (
        <KitAutocomplete
          value={selectedSupplier?.tradeName || supplierDraftName}
          options={supplierOptions}
          disabled={isReadOnly}
          placeholder="اكتب اسم المورد…"
          onPick={(id) => {
            const supplier = suppliers.find((item) => String(item.id) === String(id));
            setSupplierId(String(id));
            setSupplierDraftName("");
            if (supplier) setFactoryName(supplier.tradeName);
          }}
          onFreeText={(text) => {
            setSupplierId("");
            setSupplierDraftName(text);
            setFactoryName(text);
          }}
          createLabel={(text) => `إبقاء «${text}» كمورد مبدئي (بلا تسجيله)`}
        />
      ),
    },
    {
      key: "partyName",
      label: "الاسم",
      control: (
        <input
          className="ktra-input"
          readOnly
          value={
            selectedSupplier?.tradeName
            ?? (supplierDraftName ? `${supplierDraftName} — مبدئي` : factoryName)
          }
        />
      ),
    },
    {
      key: "currency",
      label: "العملة",
      control: (
        <select className="ktra-input" disabled={isReadOnly}
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
      control: <input className="ktra-input" type="number" min="0" step="0.001"
        disabled={isReadOnly} value={exchangeRate} onChange={(e) => setExchangeRate(e.target.value)} />,
    },
    {
      key: "status",
      // T-OFFERSTATE: «الحالة» لا «القرار» — الانتظار والمناقشة حالتان قبل القرار.
      label: "الحالة",
      control: (
        <select className="ktra-input" disabled={isReadOnly}
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
        { key: "decision", label: "الحالة", content: decisionTab },
      ]}
      totals={
        <>
          <div className="ktra-total-row">
            <span>مجموع البنود</span>
            <span className="ktra-total-value">{fmt(subtotal)}</span>
          </div>
          <div className="ktra-total-row">
            <span>الخصم</span>
            <input className="ktra-input ktra-total-input" type="number" step="0.01" min="0"
              disabled={isReadOnly} value={discountAmount}
              onChange={(e) => setDiscountAmount(e.target.value)} />
          </div>
          <div className="ktra-total-row">
            <span>بعد الخصم</span>
            <span className="ktra-total-value">{fmt(afterDiscount)}</span>
          </div>
          <div className="ktra-total-row">
            <span>نسبة الضريبة %</span>
            <input className="ktra-input ktra-total-input" type="number" step="0.01" min="0"
          disabled={isReadOnly || scope === "import"} value={scope === "import" ? "0" : taxRate}
              onChange={(e) => setTaxRate(e.target.value)} />
          </div>
          <div className="ktra-total-row">
            <span>الضريبة</span>
            <span className="ktra-total-value">{fmt(tax)}</span>
          </div>
          {/* T-IMPOFFER: الشحن ظاهر في الإجماليات لا مخفياً في تبويب. */}
          <div className="ktra-total-row">
            <span>{shippingIncluded ? "الشحن (مشمول بالأسعار)" : "الشحن المقدَّر"}</span>
            <span className="ktra-total-value">{fmt(shipping)}</span>
          </div>
          <div className="ktra-total-row ktra-total-row--grand">
            <span>إجمالي العرض</span>
            <span className="ktra-total-value">{fmt(grandTotal)} {currency}</span>
          </div>
        </>
      }
      status={
        <>
          <span className="ktra-status-item">عدد المنتجات <b>{lines.length}</b></span>
          <span className="ktra-status-item">آخر مفتاح <b>{lastKey}</b></span>
          {isReadOnly && <span className="ktra-status-item">للقراءة فقط</span>}
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
        {cardProductId != null && (
          <ProductCardModal
            productId={cardProductId}
            onProductSaved={applyProductUpdate}
            onClose={() => setCardProductId(null)}
          />
        )}
        {quickEditProductId != null && (
          <ItemQuickEditModal
            productId={quickEditProductId}
            onClose={() => setQuickEditProductId(null)}
            onSaved={applyProductUpdate}
          />
        )}
        <FilePreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
        {offer.id != null && (
          <ShareDocumentModal
            open={showShareModal}
            onClose={() => setShowShareModal(false)}
            docType="supplier_quotation"
            docId={Number(offer.id)}
            docLabel={`عرض سعر ${offerNumber || `#${offer.id}`}`}
            partyName={selectedSupplier?.tradeName || supplierDraftName}
          />
        )}
      </>}
    />
  );
};
