import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Deal,
  DealPayment,
  PriceOffer,
  User,
  DealItem,
  Item,
  Supplier,
  DealStatus,
  DealActivity,
  DealInstallment,
  ShippingWorkflowStatus,
} from "../../../types";
import {
  KitDocumentShell,
  KitDocumentView,
  KitViewTable,
  useRecordNavigation,
  useKitKeymap,
  KitGrid,
  KitAutocomplete,
  KitDateInput,
  type KitGridColumn,
  type KitToolbarAction,
} from "../../kit";
import {
  itemsService,
  suppliersService,
} from "../../../services/firestoreService";
import { purchaseInvoiceApi } from "../../../services/purchaseInvoiceApi";
import { formatMoney, formatNumber, formatQuantity } from "../../../utils/formatNumber";
import { getShippingWorkflowLabel } from "../../../utils/shippingWorkflowLabels";
import {
  Save,
  X,
  Plus,
  Trash2,
  Printer,
  FileText,
  Info,
  CreditCard,
  Package,
  AlertCircle,
  Factory,
  CheckCircle2,
  Clock,
  AlertTriangle,
  CheckCircle,
  Activity,
  Pencil,
} from "lucide-react";
import { BasicInfoSection } from "@/components/forms/shared/BasicInfoSection";
import { DealStageControl } from "@/components/forms/deal-parts/DealStageControl";
import { DealPaymentList } from "@/components/forms/deal-parts/DealPaymentList";
import { ItemSearchModal, productToItem } from "../price-offers/ItemSearchModal";
import { ItemQuickCreateModal } from "../../items/ItemQuickCreateModal";
import { ImagePreviewModal } from "../price-offers/ImagePreviewModal";
import { TermsAndShippingSection } from "@/components/forms/shared/TermsAndShippingSection";
import { AttachmentsSection } from "@/components/forms/shared/AttachmentsSection";
import { DocumentPaymentsTab } from "@/components/shared/DocumentPaymentsTab";
import { EntityActivityLog } from "@/components/activity/EntityActivityLog";
import { dealsService } from "../../../services/dealsService";
import { ActivityLog } from "./ActivityLog";
import { InstallmentManager } from "./InstallmentManager";
import { PaymentProgress } from "./PaymentProgress";
import { SupplierViewModal } from "@/components/common/SupplierViewModal";
import { useToast } from "@/contexts/ToastContext";
import { useConfirm } from "@/contexts/ConfirmContext";
import { usePermissions } from "@/contexts/PermissionsContext";
import { IMPORT_FILE_TAB } from "@/components/import-flow/importJourneyGuidance";
import { DealPrintView } from "./DealPrintView";
import { resolvePaymentForSwiftInstallment } from "@/utils/dealPaymentMatch";
import { mergeSupplier } from "@/utils/supplierList";
import { BANK_SWIFT_IMAGE_REQUIRED } from "@/utils/dealPaymentFlow";
import { formatDateLocalized } from "../../../utils/formatDate";
import { openInNewTab } from "@/utils/openInNewTab";
import { useSearchParams } from "react-router-dom";

type OperationalStatus =
  | "initial"
  | "manufacturing_started"
  | "production_completed"
  | "shipping_preparation"
  | "shipping_in_progress"
  | "shipped"
  | "completed"
  | "cancelled";

type PaymentStatus =
  | "not_paid"
  | "claim_raised"
  | "payment_pending_confirmation"
  | "partially_paid"
  | "paid";

/* THA-114: لوحة «ملف الاستيراد» — وحدة مرخّصة. كسولة خلف حارس عَلَم الوحدة:
   التبويب نفسه لا يُبنى لشركة غير مرخّصة، فلا يُطلب chunkه أصلاً. */
const ImportFilePanel = React.lazy(() =>
  import("@/components/import-file/ImportFilePanel").then((m) => ({ default: m.ImportFilePanel })),
);

interface DealFormProps {
  deal: Partial<Deal> | null;
  priceOffers: PriceOffer[];
  currentUser: User;
  onCancel: () => void;
  onSave?: () => void;
  compactMode?: boolean;
  onOpenAccountingJournal?: (
    journalId: number | null,
    dealRef?: { dealId: string; dealNumber: string; displayName: string }
  ) => void;
}

function suggestStatusAfterClaim(deal: Partial<Deal>, installmentNumber?: number): DealStatus | null {
  const n = installmentNumber ?? 1;
  const st = deal.status as DealStatus | undefined;
  if (!st) return null;
  if (n === 1) {
    if (st === "initial" || st === "manufacturing_started") return "first_payment_pending";
  }
  if (n === 2) {
    if (st === "production_completed" || st === "first_payment_confirmed") return "second_payment_pending";
  }
  return null;
}

function formatSupplierConfirmAlertText(args: {
  posted: boolean;
  journalId?: number;
  openManualJournal?: boolean;
  meta?: {
    message?: string;
    postingBlockers?: string[];
    openManualJournal?: boolean;
  };
}): string {
  const { posted, journalId, openManualJournal, meta } = args;
  if (posted || journalId) {
    const jLine = journalId
      ? `رقم قيد اليومية: ${journalId}`
      : posted
        ? "تم ترحيل القيد محاسبياً."
        : meta?.message || "";
    return `✅ تم تأكيد المورد وحفظ التاريخ.\n${jLine}`;
  }
  const manual = openManualJournal ?? meta?.openManualJournal;
  if (manual) {
    return `✅ ${meta?.message || "تم حفظ تأكيد المورد. انتقل إلى قيد اليومية لإكمال الترحيل يدوياً."}`;
  }
  const bullets =
    meta?.postingBlockers && meta.postingBlockers.length > 0
      ? meta.postingBlockers.map((b, i) => `${i + 1}. ${b}`).join("\n")
      : "— لم يُسترجَع تشخيص تفصيلي (تحقق من تشغيل الخادم ومسار واجهة التشخيص).";
  return (
    `✅ تم حفظ تأكيد المورد.\n\n` +
    `⚠️ لم يُنشأ قيد أو لم يظهر بعد. ما يمنع الترحيل التلقائي (حسب الخادم):\n\n${bullets}` +
    (meta?.message ? `\n\n(${meta.message})` : "") +
    `\n\nبعد المعالجة أعد فتح الصفقة أو اضغط «شرح عدم الترحيل» في سجل المدفوعات.`
  );
}

export const DealForm: React.FC<DealFormProps> = ({
  deal,
  priceOffers,
  currentUser,
  onCancel,
  onSave,
  compactMode = false,
  onOpenAccountingJournal,
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  /* THA-114: ترخيص وحدة «ملف الاستيراد» — يفشل مغلقاً (غياب العَلَم = مطفأة). */
  const { modules: licensedModules } = usePermissions();
  /* مرشد الاستيراد يقود إلى تبويب بعينه (`/deals/7?tab=payments`) — بدون هذا
     كان الرابط يفتح الصفقة على «البيانات الأساسية» ويترك المستخدم يبحث. */
  const [dealSearchParams] = useSearchParams();
  const requestedTab = dealSearchParams.get("tab") || undefined;
  /** حوار معلومات بزر واحد — بديل alert للرسائل الطويلة (نتائج المحاسبة). */
  const notify = (title: string, message: string) =>
    void confirm({ title, message, danger: false, hideCancel: true, confirmText: "حسناً" });

  /* نمط الفواتير: الصفقة الجديدة تبدأ بصف بنود جاهز للكتابة فوراً —
     الصفوف الفارغة تُصفّى عند الحفظ. */
  const makeEmptyItem = (): DealItem => ({
    id: crypto.randomUUID(), itemId: "", name: "", categoryId: "", categoryName: "",
    specifications: "", imageUrls: [], quantity: 1, unitPrice: 0, totalPrice: 0,
  });

  const [formData, setFormData] = useState<Partial<Deal>>(deal || {});
  /* THA-114: معرّف الصفقة رقماً — `Deal.id` نصّ، ونقطة الملف ترسو على PK رقمي. */
  const importFileDealId = Number(formData.id);
  const importFileEnabled =
    licensedModules.import_file === true && Number.isInteger(importFileDealId) && importFileDealId > 0;
  const [items, setItems] = useState<DealItem[]>(
    deal?.items?.length ? deal.items : deal?.id ? [] : [makeEmptyItem()]
  );
  const [activities, setActivities] = useState<DealActivity[]>([]);
  const [installments, setInstallments] = useState<DealInstallment[]>(deal?.installments || []);
  const [installmentPlanEnabled, setInstallmentPlanEnabled] = useState(deal?.installmentPlanEnabled || false);
  const [installmentValidationError, setInstallmentValidationError] = useState("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [allDbItems, setAllDbItems] = useState<Item[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [dealsList, setDealsList] = useState<Deal[]>([]);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  // G1: «إضافة كمنتج جديد» يفتح إنشاء منتج سريع يُنشئ Product فعلياً ويربط
  // product_id في السطر — بدل ترك سطر حر بلا itemId يُرفض بـ {"product":[...]}.
  const [inlineCreate, setInlineCreate] = useState<{ rowId: string; name: string } | null>(null);

  const nav = useRecordNavigation<Deal>({
    items: dealsList,
    getId: (d) => d.id || '',
    currentId: formData.id || null,
    onSelect: async (id) => {
      if (id === null) {
        handleNewDeal();
      } else {
        try {
          const loaded = await dealsService.getDeal(String(id));
          setFormData(loaded);
          setItems(loaded.items || []);
          setInstallments(loaded.installments || []);
          setInstallmentPlanEnabled(loaded.installmentPlanEnabled || false);
        } catch (err) {
          // console suppressed
        }
      }
    },
  });

  useKitKeymap({
    F2: () => setShowPrintView(true),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-ktra-field="search"], [name="supplierName"]');
      el?.focus();
    },
    F12: () => { if (!saving) handleFinalSave(); },
    Escape: () => { onCancel(); },
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => handleNewDeal(),
  });

  const handleNewDeal = () => {
    setFormData({});
    setItems([makeEmptyItem()]);
    setInstallments([]);
    setInstallmentPlanEnabled(false);
  };

  useEffect(() => {
    const unsub = dealsService.subscribeToDeals((fetchedDeals: Deal[]) => {
      setDealsList(fetchedDeals);
    });
    return () => unsub();
  }, []);

  const [purchasePriceMap, setPurchasePriceMap] = useState<
    Map<number, { price: string; label: string; prices?: any[] }>
  >(new Map());
  useEffect(() => {
    let cancelled = false;
    purchaseInvoiceApi
      .priceList()
      .then((rows) => {
        if (cancelled) return;
        const m = new Map<number, { price: string; label: string; prices?: any[] }>();
        for (const r of rows) {
          if (r.unit_price != null && Number(r.unit_price) > 0) {
            m.set(r.product_id, { price: r.unit_price, label: r.source_label, prices: r.prices });
          }
        }
        setPurchasePriceMap(m);
      })
      .catch(() => { /* ignore */ });
    return () => { cancelled = true; };
  }, []);

  const [showItemSearch, setShowItemSearch] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [showPrintView, setShowPrintView] = useState(false);
  /** الصفقة تُفتح على العرض المستندي، والتحرير من زر «تحرير» في شريط الأدوات.
      كانت تفتح على نموذج التحرير مباشرة بلا وضع عرض إطلاقاً. */
  const [viewMode, setViewMode] = useState<boolean>(!!deal?.id);
  const [viewSupplierId, setViewSupplierId] = useState<string | null>(null);
  const selectedSupplier = suppliers.find(s => s.id === formData.supplierId);

  /* ج7: «تم الشحن» و«بانتظار التخليص» مراحل في مسار حي — لا تقفل النموذج.
     القفل فقط عند الإلغاء أو التحويل لفاتورة (sw_released) أو الإغلاق القديم. */
  const isDealLocked =
    formData.status === 'cancelled' ||
    (formData.status === 'completed' && !formData.shippingWorkflowStatus);

  const validateInstallments = (): boolean => {
    if (!installmentPlanEnabled) { setInstallmentValidationError(""); return true; }
    if (installments.length === 0) { setInstallmentValidationError("❌ يجب إضافة دفعة واحدة على الأقل"); return false; }
    const totalPercentage = installments.reduce((sum, i) => sum + (i.percentage || 0), 0);
    if (Math.abs(totalPercentage - 100) > 0.01) { setInstallmentValidationError(`❌ مجموع النسب يجب أن يكون 100%، الحالي: ${formatNumber(totalPercentage, { maxDecimals: 2 })}%`); return false; }
    const hasZeroPercentage = installments.some(i => (i.percentage || 0) <= 0);
    if (hasZeroPercentage) { setInstallmentValidationError("❌ جميع الدفعات يجب أن يكون لها نسبة أكبر من 0%"); return false; }
    const grandTotal = calculateGrandTotal();
    const hasMismatchedAmounts = installments.some(i => {
      const expectedAmount = ((i.percentage || 0) / 100) * grandTotal;
      return Math.abs(expectedAmount - (i.amount || 0)) > 0.01;
    });
    if (hasMismatchedAmounts) { setInstallmentValidationError("❌ عدم تطابق بين النسب والمبالغ"); return false; }
    setInstallmentValidationError("");
    return true;
  };

  useEffect(() => {
    if (installmentPlanEnabled && installments.length > 0) {
      const grandTotal = calculateGrandTotal();
      setInstallments(installments.map(i => ({ ...i, amount: Math.round(((i.percentage || 0) / 100) * grandTotal * 100) / 100 })));
    }
  }, [formData.totalAmount, formData.subtotal, formData.discountAmount, formData.taxRate, formData.shippingCost]);

  useEffect(() => { if (formData.id) loadActivities(); }, [formData.id]);

  const loadActivities = async () => {
    if (!formData.id) return;
    try { setActivities(await dealsService.getDealActivities(formData.id)); }
    catch (error) { console.error("Error loading activities:", error); }
  };

  useEffect(() => {
    // T-IMPOFFER: الصفقة استيراد بطبيعتها — الموردون الدوليون (ومعهم غير
    // المصنَّفين) دون المحليين.
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers, undefined, "international");
    const unsubItems = itemsService.subscribeToItems(setAllDbItems);
    return () => { unsubSuppliers(); unsubItems(); };
  }, []);

  const toggleInstallmentPlan = (enabled: boolean) => {
    setInstallmentPlanEnabled(enabled);
    if (enabled && installments.length === 0) {
      const defaultInstallment: DealInstallment = {
        id: crypto.randomUUID(), installmentNumber: 1, percentage: 100,
        amount: calculateGrandTotal(), status: 'unpaid', notes: 'دفعة واحدة',
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString()
      };
      setInstallments([defaultInstallment]);
      setFormData(prev => ({ ...prev, installments: [defaultInstallment], installmentPlanEnabled: true }));
    }
    if (!enabled) {
      setInstallments([]); setInstallmentValidationError("");
      setFormData(prev => ({ ...prev, installments: [], installmentPlanEnabled: false }));
    }
  };

  const recalculateTotals = (newItems: DealItem[] = items, updatedFields: Partial<Deal> = {}) => {
    const currentData = { ...formData, ...updatedFields };
    const itemsSubtotal = newItems.reduce((sum, item) => sum + (item.totalPrice || 0), 0);
    const validShipping = currentData.shippingIncluded ? 0 : currentData.shippingCost || 0;
    const afterDiscount = Math.max(0, itemsSubtotal - (currentData.discountAmount || 0));
    // ج8: الصفقة الدولية بلا ضريبة — الضريبة تُدفع بالتخليص. الإجمالي (سقف دفعات
    // المورد) = بضاعة − خصم + شحن داخل الصين.
    const grandTotal = afterDiscount + validShipping;
    setItems(newItems);
    setFormData((prev) => ({ ...prev, ...updatedFields, items: newItems, subtotal: itemsSubtotal, taxAmount: 0, totalAmount: grandTotal }));
  };

  const handleAddItemFromModal = (item: Item, lastPrice?: number) => {
    const dealItem: DealItem = {
      id: crypto.randomUUID(), itemId: item.id, name: item.name, categoryId: item.categoryId,
      categoryName: item.categoryName, specifications: item.specifications || item.modelNumber || "",
      hsCodePrimary: item.hsCodePrimary, modelNumber: item.modelNumber, imageUrls: item.imageUrls || [],
      quantity: 1, unitPrice: lastPrice || 0, totalPrice: lastPrice || 0, factoryImageUrl: item.imageUrls?.[0],
    };
    recalculateTotals([...items, dealItem]);
    setShowItemSearch(false);
  };

  const handleUpdateItem = (index: number, field: string, value: any) => {
    const updatedItems = [...items];
    const item = { ...updatedItems[index], [field]: value };
    if (field === "quantity" || field === "unitPrice") {
      item.totalPrice = (Number(item.quantity) || 0) * (Number(item.unitPrice) || 0);
    }
    updatedItems[index] = item;
    recalculateTotals(updatedItems);
  };

  const handleRemoveItem = (index: number) => { recalculateTotals(items.filter((_, i) => i !== index)); };

  const handlePaymentOperation = async (
    operation: "claim" | "swift" | "add" | "confirm" | "cancel" | "unpost" | "linkJournal",
    paymentType: string, data: any, paymentId?: string
  ) => {
    if (!formData.id) { toast("يرجى حفظ الصفقة أولاً", "info"); return; }
    try {
      setLoading(true);
      if (operation !== "unpost" && operation !== "linkJournal") {
        try {
          await dealsService.updateDeal(formData.id, {
            items, installments: installmentPlanEnabled ? installments : [], installmentPlanEnabled,
            totalAmount: formData.totalAmount, subtotal: formData.subtotal, taxAmount: formData.taxAmount,
            discountAmount: formData.discountAmount, shippingCost: formData.shippingCost,
            shippingIncluded: formData.shippingIncluded,
          }, currentUser.id, currentUser.name, currentUser.role || "user", "", "");
        } catch (err) { console.error("Auto-save failed:", err); }
      }
      const cleanData = (d: any): any => Object.fromEntries(Object.entries(d).filter(([_, v]) => v !== undefined));
      let confirmAccountingMeta: { journalId?: number; message: string; openManualJournal?: boolean; postingBlockers?: string[] } | undefined;
      let lastConfirmPaymentId: string | undefined;
      let unpostAccountingMeta: { reversal_journal_id?: number; voided_journal_id?: number; accounting_note?: string } | undefined;
      let swiftAutoPostJournalId: number | undefined;
      switch (operation) {
        case "add": {
          const addAmt = Number(data?.amount ?? 0);
          await dealsService.addPayment(formData.id, { ...cleanData(data), type: paymentType, id: `payment_${Date.now()}`, paymentDate: new Date().toISOString(), confirmedBySupplier: false }, currentUser.id, currentUser.name, currentUser.role || "user");
          break;
        }
        case "claim": {
          const claimAmt = Number(data?.amount ?? 0);
          await dealsService.addPayment(formData.id, { ...cleanData(data), type: paymentType, id: `payment_${Date.now()}`, paymentDate: new Date().toISOString(), confirmedBySupplier: false }, currentUser.id, currentUser.name, currentUser.role || "user");
          const nextSt = suggestStatusAfterClaim(formData, data.installmentNumber);
          if (nextSt) { try { await dealsService.updateDealStatus(formData.id, nextSt, currentUser.id, currentUser.name, currentUser.role || "user", "رفع مطالبة — جاهز لمسار الدفع"); } catch (e) { console.warn("updateDealStatus after claim:", e); } }
          break;
        }
        case "swift": {
          const instNum = data?.installmentNumber != null && Number.isFinite(Number(data.installmentNumber)) ? Number(data.installmentNumber) : undefined;
          const resolved = resolvePaymentForSwiftInstallment(formData.payments, paymentType, instNum, paymentId ?? null);
          if (resolved.rejectReason) { toast(resolved.rejectReason, "error"); setLoading(false); return; }
          let payment = resolved.payment;
          let swiftPaymentId = payment?.id != null ? String(payment.id) : undefined;
          if (!swiftPaymentId) {
            if (!payment) {
              const swiftAmt = Number(data.amount ?? 0);
              await dealsService.addPayment(formData.id, { type: paymentType, amount: swiftAmt, paymentDate: data.paymentDate || new Date().toISOString(), usdToIls: Number(data.usdToIls ?? 0), transferCost: Number(data.transferCost ?? data.transferFee ?? 0), notes: data.notes || "", installmentId: data.installmentId, installmentNumber: data.installmentNumber, confirmedBySupplier: false, alibabaClaimImage: undefined } as Omit<DealPayment, "id">, currentUser.id, currentUser.name, currentUser.role || "user");
              const fresh = await dealsService.getDeal(formData.id);
              const again = resolvePaymentForSwiftInstallment(fresh.payments, paymentType, instNum, null);
              if (again.rejectReason) { toast(again.rejectReason, "error"); setLoading(false); return; }
              payment = again.payment; swiftPaymentId = payment?.id != null ? String(payment.id) : undefined;
            } else { swiftPaymentId = String(payment.id); }
          }
          if (!swiftPaymentId) { toast("تعذر إنشاء أو العثور على سجل الدفعة", "error"); setLoading(false); return; }
          if (!data.cashBoxId) { toast("يجب اختيار صندوق مالي لتنفيذ عملية الدفع", "error"); setLoading(false); return; }
          if (BANK_SWIFT_IMAGE_REQUIRED && !data.bankSwiftImage) { toast("يجب رفع صورة السليب أولاً", "error"); setLoading(false); return; }
          const swiftPrincipal = Number(data.amount ?? 0);
          const totalPayment = (data.amount || 0) + (data.transferCost || 0);
          if (!(await confirm({ title: "تنفيذ الدفع", message: `هل أنت متأكد من خصم $${formatMoney(totalPayment)} من الصندوق المحدد؟`, danger: false, confirmText: "تنفيذ الدفع" }))) { setLoading(false); return; }
          try {
            await dealsService.updatePaymentWithSwift(formData.id, swiftPaymentId, cleanData({ ...data, dealNumber: formData.dealNumber }), currentUser.id, currentUser.name, currentUser.role || "user", data.cashBoxId);
            const postTry = await dealsService.tryAutoPostDealPaymentAccounting(formData.id, swiftPaymentId, { cashBoxExternalId: data.cashBoxId ? String(data.cashBoxId).trim() : undefined });
            if (postTry.posted && postTry.journalId != null) swiftAutoPostJournalId = postTry.journalId;
          } catch (error: any) { if (error.message.includes('الرصيد غير كافي')) { toast(error.message, "error"); throw error; } throw error; }
          break;
        }
        case "confirm":
          if (paymentId) {
            lastConfirmPaymentId = paymentId;
            const paymentToConfirm = formData.payments?.find(p => p.id === paymentId);
            if (paymentToConfirm) {
              if (paymentToConfirm.bankSwiftImage && !paymentToConfirm.cashBoxId) { toast("هذه الدفعة تحتوي على سليب ولكن لم يتم خصمها من الصندوق بعد", "info"); setLoading(false); return; }
              if (BANK_SWIFT_IMAGE_REQUIRED && paymentToConfirm.cashBoxId && !paymentToConfirm.bankSwiftImage) { toast("تم خصم المبلغ من الصندوق ولكن لم يتم رفع صورة السليب", "info"); setLoading(false); return; }
            }
            confirmAccountingMeta = await dealsService.confirmPayment(formData.id, paymentId, currentUser.id, currentUser.name, currentUser.role || "user", data.supplierConfirmationImage, data.supplierNotes, data.paymentConfirmationDate, data.cashBoxId);
          }
          break;
        case "unpost":
          if (String(currentUser.role || "").toLowerCase() !== "manager") { toast("هذا الإجراء متاح للمدير فقط من الواجهة.", "error"); setLoading(false); return; }
          if (!paymentId || !formData.id) { setLoading(false); return; }
          unpostAccountingMeta = await dealsService.unpostDealPayment(formData.id, paymentId);
          break;
        case "cancel":
          if (paymentId) await dealsService.cancelPayment(formData.id, paymentId, currentUser.id, currentUser.name, currentUser.role || "user");
          break;
        case "linkJournal": {
          if (!paymentId) { setLoading(false); return; }
          const jid = Number(data?.journalId);
          if (!Number.isFinite(jid) || jid <= 0) { toast("رقم القيد غير صالح.", "error"); setLoading(false); return; }
          await dealsService.linkDealPaymentJournal(String(formData.id), String(paymentId), jid);
          break;
        }
      }
      const loadedAfterPay = await loadAndSetDealData(formData.id);
      await loadActivities();
      switch (operation) {
        case "swift":
          if (swiftAutoPostJournalId != null) {
            toast("تم تنفيذ الدفع ورفع السليب، وتم إنشاء قيد المحاسبة وربطه بالدفعة.", "success");
            onOpenAccountingJournal?.(swiftAutoPostJournalId, { dealId: formData.id!, dealNumber: formData.dealNumber || "", displayName: [formData.dealNumber, formData.dealDescription || formData.originalOfferNumber || formData.factoryName || ""].filter(Boolean).join(" — ") });
          } else { toast("تم تنفيذ الدفع ورفع السليب بنجاح", "success"); }
          break;
        case "claim": toast("تم رفع المطالبة. يمكنك الآن تسجيل الدفع من تبويب «تسجيل الدفع» في أي وقت.", "success"); break;
        case "confirm": {
          const pid = lastConfirmPaymentId;
          const row = pid ? loadedAfterPay?.payments?.find((x) => String(x.id) === String(pid)) : undefined;
          const jid = confirmAccountingMeta?.journalId ?? row?.journalId;
          notify("تأكيد المورد", formatSupplierConfirmAlertText({ posted: Boolean(row?.isPosted), journalId: jid, openManualJournal: confirmAccountingMeta?.openManualJournal, meta: confirmAccountingMeta ?? undefined }));
          if (confirmAccountingMeta?.openManualJournal || (confirmAccountingMeta?.journalId != null && Number(confirmAccountingMeta.journalId) > 0)) {
            const j = Number(confirmAccountingMeta.journalId);
            const dealDesc = formData.dealDescription || formData.originalOfferNumber || formData.factoryName || selectedSupplier?.tradeName || "";
            onOpenAccountingJournal?.(confirmAccountingMeta?.openManualJournal ? null : j, { dealId: formData.id!, dealNumber: formData.dealNumber || '', displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(' — ') });
          }
          break;
        }
        case "cancel": toast("تم إلغاء الدفعة من سجل الصفقة", "success"); break;
        case "unpost": {
          const rj = unpostAccountingMeta?.reversal_journal_id;
          const vj = unpostAccountingMeta?.voided_journal_id;
          const note = unpostAccountingMeta?.accounting_note || "";
          notify("إلغاء ترحيل الدفعة", `تم إلغاء ترحيل الدفعة محاسبياً.\n\n• قيد عكسي مرحّل: ${rj != null ? `#${rj}` : "—"}\n• القيد الأصلي أصبح غير مرحّل: ${vj != null ? `#${vj}` : "—"}\n\nالدفعة أصبحت قابلة للحذف من «حذف من السجل».\n${note ? `\n${note}` : ""}`);
          break;
        }
        case "linkJournal": toast("تم ربط الدفعة بالقيد. سيظهر «فتح في المحاسبة» في سجل المدفوعات بعد التحديث.", "success"); break;
        default: toast("تم حفظ العملية بنجاح", "success");
      }
    } catch (error: any) { console.error("Payment Operation Error:", error); toast(error.message || "حدث خطأ أثناء حفظ العملية", "error"); }
    finally { setLoading(false); }
  };

  const handlePaymentConfirmation = async (confirmationData: any) => {
    if (!formData.id || !confirmationData.paymentId) return;
    try {
      setLoading(true);
      const acc = await dealsService.confirmPayment(formData.id, confirmationData.paymentId, currentUser.id, currentUser.name, currentUser.role || "user", confirmationData.supplierConfirmationImage, confirmationData.supplierNotes, confirmationData.paymentConfirmationDate, confirmationData.cashBoxId);
      const loaded = await loadAndSetDealData(formData.id);
      await loadActivities();
      const row = loaded?.payments?.find((x) => String(x.id) === String(confirmationData.paymentId));
      const jid = acc.journalId ?? row?.journalId;
      notify("تأكيد المورد", formatSupplierConfirmAlertText({ posted: Boolean(row?.isPosted), journalId: jid, openManualJournal: acc.openManualJournal, meta: acc }));
      if (acc.openManualJournal || (acc.journalId != null && Number(acc.journalId) > 0)) {
        const j = Number(acc.journalId);
        const dealDesc = formData.dealDescription || formData.originalOfferNumber || formData.factoryName || selectedSupplier?.tradeName || "";
        onOpenAccountingJournal?.(acc.openManualJournal ? null : j, { dealId: formData.id!, dealNumber: formData.dealNumber || '', displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(' — ') });
      }
    } catch (error: any) {
      // console suppressed
      let diag = "";
      try {
        if (formData.id && confirmationData.paymentId) {
          const d = await dealsService.getPaymentPostingDiagnostics(formData.id, String(confirmationData.paymentId));
          if (d.blockers?.length) diag = "\n\n— تشخيص من الخادم —\n" + d.blockers.map((b, i) => `${i + 1}. ${b}`).join("\n");
        }
      } catch { /* ignore */ }
      notify("خطأ في تأكيد الدفعة", `حدث خطأ في تأكيد الدفعة${error?.message ? `:\n${error.message}` : ""}${diag}`);
    } finally { setLoading(false); }
  };

  const handleStatusChange = async (newStatus: DealStatus, notes?: string) => {
    if (!formData.id) return;
    try {
      setLoading(true);
      await dealsService.updateDealStatus(formData.id, newStatus, currentUser.id, currentUser.name, currentUser.role || "user", notes);
      await loadAndSetDealData(formData.id); await loadActivities();
      toast(`تم تغيير حالة الصفقة إلى: ${newStatus}`, "success");
    } catch (error) { console.error("Error changing status:", error); toast("حدث خطأ في تغيير الحالة", "error"); }
    finally { setLoading(false); }
  };

  const handleShippingWorkflowChange = async (code: ShippingWorkflowStatus) => {
    if (!formData.id) return;
    setWorkflowError(null);
    try {
      setLoading(true);
      await dealsService.patchShippingWorkflow(formData.id, code);
      await loadAndSetDealData(formData.id); await loadActivities();
      toast("تم حفظ مرحلة الشحن والتصنيع", "success");
    } catch (error: unknown) { setWorkflowError(error instanceof Error ? error.message : "تعذر حفظ مرحلة الشحن"); }
    finally { setLoading(false); }
  };

  const handleUpdateDeal = async (updates: Partial<Deal>, action: string, details?: string) => {
    if (!formData.id) return;
    try {
      await dealsService.updateDeal(formData.id, updates, currentUser.id, currentUser.name, currentUser.role || "user", action, details);
      const updatedDeal = await loadAndSetDealData(formData.id);
      await loadActivities();
      return updatedDeal;
    } catch (error) { console.error(" Error updating deal:", error); throw error; }
  };

  const handleFinalSave = async () => {
    if (!validateForm()) return;
    if (installmentPlanEnabled && !validateInstallments()) { toast("يرجى تصحيح أخطاء نظام الدفعات قبل الحفظ", "error"); return; }
    const invoiceToCheck = formData.supplierInvoiceNumber?.trim() || undefined;
    const linkToCheck = formData.alibabaOrderLink?.trim() || undefined;
    if (invoiceToCheck || linkToCheck) {
      setSaving(true);
      try {
        const checkResult = await dealsService.checkDealUniqueness(invoiceToCheck, linkToCheck, formData.id);
        if (!checkResult.isUnique) {
          setSaving(false);
          if (checkResult.errorField === 'invoice') notify("تكرار رقم الفاتورة", `رقم الفاتورة: "${invoiceToCheck}"\nمستخدم بالفعل في الصفقة رقم: (${checkResult.existingDealNumber})\n\nيمنع تكرار رقم الفاتورة في النظام بالكامل.`);
          else if (checkResult.errorField === 'link') notify("تكرار رابط علي بابا", `رابط علي بابا هذا مستخدم بالفعل في الصفقة رقم: (${checkResult.existingDealNumber})\n\nيمنع تكرار نفس الطلب (الرابط) لصفقتين مختلفتين.`);
          return;
        }
      } catch (error) { console.error("Uniqueness check failed", error); }
    }
    setSaving(true);
    try {
      const finalFormData: Partial<Deal> = { ...formData, items: nonEmptyItems(), subtotal: formData.subtotal, taxAmount: formData.taxAmount, totalAmount: formData.totalAmount, updatedAt: new Date().toISOString(), updatedBy: currentUser.id };
      if (installmentPlanEnabled) { finalFormData.installments = installments; finalFormData.installmentPlanEnabled = true; }
      else { finalFormData.installments = []; finalFormData.installmentPlanEnabled = false; }
      const isExistingDeal = deal?.id || formData.id;
      if (isExistingDeal) {
        const dealId = deal?.id || formData.id!;
        const { payments: _paymentsOmitted, ...dealUpdateWithoutPayments } = finalFormData;
        const savedDeal = await handleUpdateDeal(dealUpdateWithoutPayments, "تحديث بيانات الصفقة", "تم تحديث بيانات الصفقة (البنود والحقول؛ سجل الدفعات دون تغيير من هذا الزر)");
        if (savedDeal?.linkedShipment?.id) {
          const reconciliation = await purchaseInvoiceApi.recalculateLandedCost({
            shipment_id: savedDeal.linkedShipment.id,
            auto_repost: true,
          });
          if (reconciliation.reconciliation?.left_draft) {
            toast(reconciliation.reconciliation.warnings.join(" · "), "info");
          }
        }
        const updatedDeal = await dealsService.getDeal(dealId);
        setFormData(updatedDeal); setItems(updatedDeal.items || []); setInstallments(updatedDeal.installments || []); setInstallmentPlanEnabled(updatedDeal.installmentPlanEnabled || false);
        toast("تم تحديث الصفقة بنجاح!", "success");
      } else {
        if (!(await confirm({ title: "إنشاء صفقة", message: "هل أنت متأكد من إنشاء الصفقة الجديدة؟", danger: false, confirmText: "إنشاء" }))) { setSaving(false); return; }
        const createData: any = {
          supplierId: formData.supplierId || "", factoryName: formData.factoryName || "", items: nonEmptyItems(), payments: [],
          totalAmount: finalFormData.totalAmount || 0, subtotal: finalFormData.subtotal || 0,
          shippingCost: finalFormData.shippingCost || 0, shippingIncluded: finalFormData.shippingIncluded || false,
          discountAmount: finalFormData.discountAmount || 0, taxRate: finalFormData.taxRate || 0,
          taxAmount: finalFormData.taxAmount || 0, dealDate: formData.dealDate || new Date().toISOString().split("T")[0],
          createdBy: currentUser.id, updatedBy: currentUser.id, status: "initial",
          installments: finalFormData.installments || [], installmentPlanEnabled: finalFormData.installmentPlanEnabled || false,
        };
        // T113-2: العرض المصدر وعملته يُرسَلان مع الإنشاء — بدونهما تُحفظ الصفقة
        // بلا نسبٍ إلى عرضها وبالعملة الأولى مهما كانت عملة العرض.
        const optionalFields = ["sourceQuotationId", "currencyId", "currencyRate", "incoterms", "totalWeightKg", "priceOfferId", "dealDescription", "originalOfferNumber", "alibabaOrderLink", "internalNotes", "notes", "invoiceLink", "supplierInvoiceNumber", "supplierName", "shippingMethod", "productionDays", "deliveryDays", "quoteImages", "quotePdfs", "quote_images", "quote_pdfs", "productionTime", "paymentMethod", "deliveryTime", "warrantyDuration", "certificates", "shipping_method_id", "shippingMethodCode", "shippingMethodName", "shipmentNotes", "totalWeight", "totalVolume", "isReadyStock", "shippingDetails", "productionPath"];
        optionalFields.forEach((field) => { if (formData[field as keyof Deal] !== undefined && formData[field as keyof Deal] !== null) createData[field] = formData[field as keyof Deal]; });
        const dealId = await dealsService.createDeal(createData);
        const createdDeal = await dealsService.getDeal(dealId);
        setFormData(createdDeal); setItems(createdDeal.items || []); setInstallments(createdDeal.installments || []); setInstallmentPlanEnabled(createdDeal.installmentPlanEnabled || false);
        await loadActivities();
        // الصفقة المولودة من عرض: الرسالة تسمّي الطرفين، فيُغلَق مسار «حوّلت ولا
        // أرى أثراً» بلا فتح شاشة أخرى للتأكد.
        toast(
          createdDeal.sourceQuotationId && createdDeal.originalOfferNumber
            ? `تم إنشاء الصفقة ${createdDeal.dealNumber} من العرض ${createdDeal.originalOfferNumber}`
            : `تم إنشاء الصفقة بنجاح برقم: ${createdDeal.dealNumber}`,
          "success",
        );
      }
    } catch (e: any) {
      console.error("❌ Save Error:", e);
      // رسالة الخادم عن العرض المصدر («محوَّل بالفعل إلى الصفقة D-…») تُعرض كما
      // هي: هي وحدها التي تقول أين ذهب العرض، وتصديرها بـ«فشل الحفظ» يُخفيها.
      const serverMessage = String(e?.message || "").trim();
      toast(
        formData.sourceQuotationId && serverMessage
          ? serverMessage
          : `فشل الحفظ: ${e.message}`,
        "error",
      );
    }
    finally { setSaving(false); }
  };

  const calculateSubtotal = (): number => items.reduce((sum, item) => sum + ((item.quantity || 0) * (item.unitPrice || 0)), 0);

  const loadAndSetDealData = async (dealId: string) => {
    try {
      const loadedDeal = await dealsService.getDeal(dealId);
      setFormData(loadedDeal); setItems(loadedDeal.items || []); setInstallments(loadedDeal.installments || []); setInstallmentPlanEnabled(loadedDeal.installmentPlanEnabled || false);
      return loadedDeal;
    } catch (error) { console.error(" خطأ في تحميل بيانات الصفقة:", error); throw error; }
  };

  // ج8: الصفقة الدولية بلا ضريبة (تُدفع بالتخليص). الإجمالي = بضاعة − خصم + شحن داخل الصين.
  const calculateGrandTotal = (): number => {
    const subtotal = calculateSubtotal();
    const netAfterDiscount = Math.max(0, subtotal - (formData.discountAmount || 0));
    const shipping = formData.shippingIncluded ? 0 : (formData.shippingCost || 0);
    return netAfterDiscount + shipping;
  };

  /** الصفوف ذات المحتوى فقط — الصف الفارغ الجاهز لا يُحفظ ولا يُحتسب */
  const nonEmptyItems = () => items.filter((i) => i.itemId || (i.name || "").trim());

  const validateForm = (): boolean => {
    if (!formData.supplierId) { toast("يرجى اختيار المورد أولاً", "error"); return false; }
    if (nonEmptyItems().length === 0) { toast("يرجى إضافة منتجات على الأقل", "error"); return false; }
    // G1: امنع الحفظ إن وُجد بند بلا منتج مربوط (itemId رقمي) — يكافئ رفض الخادم
    // {"product":["هذا الحقل مطلوب."]} برسالة عربية واضحة بدل JSON خام.
    const unlinked = nonEmptyItems().filter((i) => !(i.itemId && /^\d+$/.test(String(i.itemId))));
    if (unlinked.length > 0) { toast("يوجد بند بلا منتج مربوط — اختر منتجاً من القائمة أو «إضافة كمنتج جديد»", "error"); return false; }
    return true;
  };

  const getOperationalStatus = (status: DealStatus): OperationalStatus => {
    if (status === "manufacturing_started") return "manufacturing_started";
    if (status === "production_completed") return "production_completed";
    if (status === "shipping_preparation") return "shipping_preparation";
    if (status === "shipping_in_progress") return "shipping_in_progress";
    if (status === "shipped") return "shipped";
    if (status === "completed") return "completed";
    if (status === "cancelled") return "cancelled";
    return "initial";
  };

  const getOperationalStatusText = (status: OperationalStatus): string => {
    const m: Record<OperationalStatus, string> = { initial: "أولية", manufacturing_started: "قيد التصنيع", production_completed: "تم التصنيع", shipping_preparation: "تجهيز الشحن", shipping_in_progress: "جاري الشحن", shipped: "تم الشحن", completed: "مكتملة — مفرج عنها", cancelled: "ملغاة" };
    return m[status] || status;
  };

  const getOperationalStatusStyles = (status: OperationalStatus): string => {
    const s: Record<OperationalStatus, string> = { initial: "ktra-bg-panel ktra-text-ink ktra-border-soft", manufacturing_started: "ktra-bg-accent-bg ktra-text-accent ktra-border-accent", production_completed: "bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]", shipping_preparation: "ktra-bg-panel ktra-text-ink ktra-border-soft", shipping_in_progress: "bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]", shipped: "bg-green-50 text-green-700 ktra-border-soft", completed: "bg-green-50 text-green-700 ktra-border-soft", cancelled: "ktra-bg-panel ktra-text-state ktra-border-soft" };
    return s[status] || s["initial"];
  };

  const getPaymentStatusFromPayments = (d: Deal): PaymentStatus => {
    const total = d.totalAmount || 0;
    const paid = d.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0;
    if (total === 0) return "not_paid";
    const percentage = (paid / total) * 100;
    const payments = d.payments || [];
    const paymentsWithClaimOnly = payments.filter(p => p.alibabaClaimImage && !p.bankSwiftImage && !p.confirmedBySupplier);
    const paymentsWithSwiftUnconfirmed = payments.filter(p => p.bankSwiftImage && !p.confirmedBySupplier);
    const confirmedPayments = payments.filter(p => p.confirmedBySupplier);
    if (paymentsWithClaimOnly.length > 0 && paymentsWithSwiftUnconfirmed.length === 0) return "claim_raised";
    if (paymentsWithSwiftUnconfirmed.length > 0) return "payment_pending_confirmation";
    if (confirmedPayments.length > 0) { if (payments.length === confirmedPayments.length) { if (percentage === 100) return "paid"; if (percentage > 0 && percentage < 100) return "partially_paid"; } return "partially_paid"; }
    if (percentage === 0) return "not_paid";
    if (percentage > 0 && percentage < 100) return "partially_paid";
    if (percentage === 100) return "paid";
    return "not_paid";
  };

  const getPaymentStatusText = (status: PaymentStatus): string => {
    const m: Record<PaymentStatus, string> = { not_paid: "غير مدفوعة", claim_raised: "تم رفع مطالبة", payment_pending_confirmation: "بانتظار تأكيد", partially_paid: "مدفوعة جزئياً", paid: "مدفوعة كلياً" };
    return m[status] || status;
  };

  const getPaymentStatusStyles = (status: PaymentStatus): string => {
    const s: Record<PaymentStatus, string> = { not_paid: "ktra-bg-panel ktra-text-state ktra-border-soft", claim_raised: "ktra-bg-panel ktra-text-ink ktra-border-soft", payment_pending_confirmation: "ktra-bg-accent-bg ktra-text-accent ktra-border-accent", partially_paid: "ktra-bg-panel ktra-text-ink ktra-border-soft", paid: "ktra-bg-panel ktra-text-ink ktra-border-soft" };
    return s[status] || s["not_paid"];
  };

  const dealStats = {
    totalAmount: calculateGrandTotal(),
    itemsCount: items.length,
    paidAmount: Number(formData.postedPaidAmount) || 0,
    unpostedAmount: Number(formData.unpostedRegisteredAmount) || 0,
    remainingAmount: Math.max(0, Number(formData.amountOutstanding) || calculateGrandTotal() - (Number(formData.postedPaidAmount) || 0)),
    supplierAdvance: Math.max(0, Number(formData.supplierAdvance) || 0),
    paymentPercentage: calculateGrandTotal() > 0 ? ((Number(formData.postedPaidAmount) || 0) / calculateGrandTotal()) * 100 : 0
  };

  const fmt = (v: number) => formatMoney(v);

  const fld = (label: string, node: React.ReactNode) => (
    <label className="ktra-field">
      <span className="ktra-field-label">{label}</span>
      {node}
    </label>
  );

  /* ───────────── أعمدة جدول البنود ───────────── */
  const itemColumns: KitGridColumn<DealItem>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "itemId", header: "رقم المنتج", width: "100px" },
    { key: "name", header: "اسم المنتج", width: "25%" },
    { key: "specifications", header: "بيان", width: "20%" },
    { key: "quantity", header: "الكمية", width: "80px", align: "center", type: "number" },
    { key: "unitPrice", header: "سعر الوحدة", width: "100px", align: "center", type: "number" },
    { key: "totalPrice", header: "الإجمالي", width: "100px", align: "center", readOnly: true },
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const itemGetCell = (row: DealItem, key: string): string | number => {
    const idx = items.indexOf(row);
    switch (key) {
      case "seq": return idx + 1;
      case "itemId": return row.itemId || "";
      case "name": return row.name || "";
      case "specifications": return row.specifications || "";
      case "quantity": return row.quantity || 0;
      case "unitPrice": return row.unitPrice || 0;
      case "totalPrice": return row.totalPrice || 0;
      default: return "";
    }
  };

  const itemOnChange = (rowIndex: number, key: string, value: string) => {
    const updatedItems = [...items];
    const item = { ...updatedItems[rowIndex] };
    if (key === "quantity") { item.quantity = Number(value) || 0; item.totalPrice = item.quantity * (item.unitPrice || 0); }
    else if (key === "unitPrice") { item.unitPrice = Number(value) || 0; item.totalPrice = (item.quantity || 0) * item.unitPrice; }
    updatedItems[rowIndex] = item;
    recalculateTotals(updatedItems);
  };

  const addRow = () => {
    const newItem: DealItem = { id: crypto.randomUUID(), itemId: "", name: "", categoryId: "", categoryName: "", specifications: "", imageUrls: [], quantity: 1, unitPrice: 0, totalPrice: 0 };
    recalculateTotals([...items, newItem]);
  };

  const removeRow = (key: string) => { recalculateTotals(items.filter((i) => i.id !== key)); };

  const renderItemIdCell = (row: DealItem) => (
    <button type="button" className="ktra-cell-picker" disabled={isDealLocked} data-ktra-key="1" onClick={() => setShowItemSearch(true)} title="فهرس المنتجات الكامل (+)">
      {row.itemId ? `#${row.itemId}` : "…"}
    </button>
  );

  const renderDeleteCell = (row: DealItem) =>
    isDealLocked ? null : (
      <button type="button" className="ktra-iconbtn ktra-iconbtn--danger" onClick={() => removeRow(row.id)} title="حذف السطر"><Trash2 className="h-3 w-3" /></button>
    );

  /* task13 M5: منتقي مدمج في خلية اسم المنتج — الكتابة تفلتر فورياً وتعبئ
     السطر نفسه (المودال القديم كان يضيف سطراً جديداً دائماً ويأكل الشاشة).
     زر «#» في عمود رقم المنتج يبقى فاتحاً الفهرس الكامل كمسار ثانوي. */
  const itemOptions = useMemo(
    () => allDbItems.map((it) => {
      const pp = purchasePriceMap.get(Number(it.id));
      return {
        id: it.id,
        label: it.name,
        price: pp ? formatMoney(Number(pp.price)) : undefined,
        priceLabel: pp ? pp.label : "بدون سعر",
        prices: pp?.prices?.map((p: any) => ({
          label: p.source_label || p.label,
          value: formatMoney(Number(p.unit_price)),
          link: p.document_id ? `/purchase-invoices/${p.document_id}` : undefined,
        })),
      };
    }),
    [allDbItems, purchasePriceMap],
  );

  const fillRowWithItem = (rowId: string, item: Item) => {
    const idx = items.findIndex((i) => i.id === rowId);
    if (idx < 0) return;
    const updated = [...items];
    const prev = updated[idx];
    const quantity = prev.quantity || 1;
    const unitPrice = prev.unitPrice || 0;
    updated[idx] = {
      ...prev, itemId: item.id, name: item.name, categoryId: item.categoryId,
      categoryName: item.categoryName,
      specifications: item.specifications || item.modelNumber || prev.specifications || "",
      hsCodePrimary: item.hsCodePrimary, modelNumber: item.modelNumber,
      imageUrls: item.imageUrls || [], factoryImageUrl: item.imageUrls?.[0],
      quantity, unitPrice, totalPrice: quantity * unitPrice,
    };
    recalculateTotals(updated);
  };

  const renderItemNameCell = (row: DealItem) => (
    <KitAutocomplete
      value={row.name || ""}
      options={itemOptions}
      disabled={isDealLocked}
      placeholder="اكتب اسم المنتج…"
      onPick={(id) => {
        const it = allDbItems.find((x) => String(x.id) === String(id));
        if (it) fillRowWithItem(row.id, it);
      }}
      onFreeText={(t) => setInlineCreate({ rowId: row.id, name: t.trim() })}
    />
  );

  itemColumns[1].render = renderItemIdCell;
  itemColumns[2].render = renderItemNameCell;
  itemColumns[7].render = renderDeleteCell;

  /* ───────────── تبويبات ───────────── */
  const notesTab = (
    <textarea className="ktra-input" rows={3} style={{ width: "100%" }} disabled={isDealLocked} value={formData.notes || formData.internalNotes || ""} onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))} />
  );

  const otherTab = (
    <div className="ktra-other">
      {/* G5: حقول كانت في الشبكة العلوية المحذوفة — نُقلت هنا كي لا تُفقد. */}
      {fld("الساعة", <input className="ktra-input" type="time" disabled={isDealLocked} value={(formData as any).transactionTime || ""} onChange={(e) => setFormData(prev => ({ ...prev, transactionTime: e.target.value }) as any)} />)}
      {fld("تاريخ ثاني", <KitDateInput disabled={isDealLocked} value={(formData as any).secondDate || ""} onChange={(v) => setFormData(prev => ({ ...prev, secondDate: v }) as any)} />)}
      {fld("تاريخ الاستحقاق", <KitDateInput disabled={isDealLocked} value={formData.dueDate || ""} onChange={(v) => setFormData(prev => ({ ...prev, dueDate: v }))} />)}
      {fld("مشتغل مرخص", <input className="ktra-input" disabled={isDealLocked} value={formData.licensedDealerNo || ""} onChange={(e) => setFormData(prev => ({ ...prev, licensedDealerNo: e.target.value }))} placeholder="رقم المشتغل المرخص" />)}
      {fld("رابط الفاتورة", <input className="ktra-input" disabled={isDealLocked} value={(formData as any).invoiceLink || ""} onChange={(e) => setFormData(prev => ({ ...prev, invoiceLink: e.target.value }) as any)} placeholder="الفاتورة الأصلية" />)}
      <label className="ktra-field ktra-field--inline">
        <input type="checkbox" disabled={isDealLocked} checked={formData.shippingIncluded || false} onChange={(e) => setFormData(prev => ({ ...prev, shippingIncluded: e.target.checked }))} />
        <span className="ktra-field-label" style={{ flex: "unset" }}>الأسعار تشمل الشحن داخل الصين</span>
      </label>
      <p className="ktra-hint">حالة الصفقة: {getOperationalStatusText(getOperationalStatus(formData.status as DealStatus))} — الدفع: {getPaymentStatusText(getPaymentStatusFromPayments(formData as Deal))}</p>
    </div>
  );

  const basicInfoTab = (
    <div className="ktra-legacy-tab">
      <BasicInfoSection
        data={formData}
        setData={setFormData}
        suppliers={suppliers}
        isDeal={true}
        dealsService={dealsService}
        items={items}
        readOnly={isDealLocked}
        onSupplierAdded={(savedSupplier) => setSuppliers((current) => mergeSupplier(current, savedSupplier))}
      />
    </div>
  );

  const termsAndShippingTab = (
    <div className="ktra-legacy-tab">
      <TermsAndShippingSection
        data={formData}
        setData={setFormData}
        readOnly={isDealLocked}
      />
    </div>
  );

  /* ج8: تبويب دفعات واحد متدرّج — بدل تكديس ثلاثة أسطح متساوية (خطة/تقدّم/سجل)
     كانت تستهلك الشاشة وتكرّر الملخّص. السطح الأساسي = مسار الأقساط (claim→دفع
     →تأكيد→قيد)؛ إعداد الخطة والسجل المحاسبي المفصّل داخل أقسام قابلة للطي. */
  const paymentsStarted = (formData.payments?.length || 0) > 0;
  const paymentsTab = (
    <div className="ktra-legacy-tab" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <details open={!paymentsStarted}>
        <summary
          style={{ cursor: "pointer", fontWeight: 700, padding: "6px 2px", userSelect: "none" }}
        >
          إعداد خطة الأقساط {paymentsStarted ? "(بدأ الدفع — للاطلاع)" : ""}
        </summary>
        <div style={{ marginTop: 8 }}>
          <InstallmentManager
            installments={installments}
            grandTotal={calculateGrandTotal()}
            onUpdateInstallments={(newInstallments) => {
              setInstallments(newInstallments);
              setFormData(prev => ({ ...prev, installments: newInstallments }));
            }}
            validationError={installmentValidationError}
            installmentPlanEnabled={installmentPlanEnabled}
            onTogglePlan={toggleInstallmentPlan}
            deal={formData}
            readOnly={isDealLocked}
          />
        </div>
      </details>

      <PaymentProgress
        installments={
          formData.installments && formData.installments.length > 0
            ? formData.installments
            : installments
        }
        deal={formData}
        currentUser={currentUser}
        onPaymentOperation={handlePaymentOperation}
        onConfirmSupplier={handlePaymentConfirmation}
        onOpenAccountingJournal={onOpenAccountingJournal}
        readOnly={isDealLocked}
      />

      {formData.id && paymentsStarted ? (
        <details>
          <summary
            style={{ cursor: "pointer", fontWeight: 700, padding: "6px 2px", userSelect: "none" }}
          >
            السجل المحاسبي المفصّل (قيود، إلغاء ترحيل، حذف)
          </summary>
          <div style={{ marginTop: 8 }}>
            <DealPaymentList
              deal={formData}
              currentUser={currentUser}
              onPaymentOperation={handlePaymentOperation}
              onConfirmSupplier={handlePaymentConfirmation}
              onOpenAccountingJournal={onOpenAccountingJournal}
            />
          </div>
        </details>
      ) : null}
    </div>
  );

  /* المراحل والشحن فُصلت عن الدفعات — كانت مكدّسة في تبويب واحد يستهلك الشاشة */
  const stagesTab = (
    <div className="ktra-legacy-tab" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {workflowError && (
        <div style={{ color: 'var(--ktra-err, #c0392b)', fontSize: '12px', padding: '4px 8px', marginBottom: '4px', background: 'var(--ktra-err-bg, #fde8e8)', borderRadius: '4px' }}>
          {workflowError}
        </div>
      )}
      <DealStageControl
        data={formData}
        setData={setFormData}
        currentUser={currentUser}
        onStatusChange={handleStatusChange}
        onShippingWorkflowChange={handleShippingWorkflowChange}
      />
    </div>
  );

  const attachmentsTab = (
    <div className="ktra-legacy-tab">
      <AttachmentsSection
        data={formData}
        setData={setFormData}
      />
    </div>
  );

  const activityTab = (
    <div className="ktra-legacy-tab">
      {formData.id && activities.length > 0 ? (
        <ActivityLog activities={activities} />
      ) : (
        <p className="ktra-hint">لا يوجد سجل نشاطات بعد.</p>
      )}
    </div>
  );

  /* ───────────── العرض المستندي للصفقة ─────────────
     الصفقة أغنى من الفاتورة (تنبيه المالك): أقساط، دفعات بمراحلها، قياسات
     CBM/وزن، شحنة مرتبطة، شهادات. لذلك تُعرض كأقسام مستقلة أسفل المستند بدل
     حشرها في قالب فاتورة. */
  const dealMoney = (n: number) => `${fmt(n)} USD`;
  const filledDealItems = items.filter((i) => i.itemId || (i.name || "").trim());
  const dealPayments = formData.payments || [];
  const dealInstallments = formData.installments || [];

  const dealDocumentView = (
    <KitDocumentView<DealItem>
      title="صفقة استيراد"
      subtitle="IMPORT DEAL"
      documentNumber={formData.dealNumber || (formData.id ? `#${formData.id}` : "جديدة")}
      status={{
        label: String(formData.status || "initial"),
        tone:
          formData.status === "completed"
            ? "ok"
            : formData.status === "cancelled"
              ? "danger"
              : "warn",
      }}
      metrics={[
        { label: "إجمالي الصفقة", value: dealMoney(dealStats.totalAmount), tone: "info" },
        { label: "المدفوع والمرحّل", value: dealMoney(dealStats.paidAmount), tone: "ok" },
        dealStats.supplierAdvance > 0
          ? { label: "دفعة مقدمة على هذه الصفقة", value: dealMoney(dealStats.supplierAdvance), tone: "info" }
          : { label: "المتبقي", value: dealMoney(dealStats.remainingAmount), tone: "warn" },
        { label: "مسجّل بانتظار الترحيل", value: dealMoney(dealStats.unpostedAmount) },
      ]}
      parties={[
        {
          title: "المورد",
          icon: <Factory size={14} />,
          fields: [
            { label: "الاسم", value: selectedSupplier?.tradeName || "—" },
            { label: "المصنع", value: formData.factoryName || "—" },
            ...(formData.supplierInvoiceNumber
              ? [{ label: "رقم فاتورة المورد", value: formData.supplierInvoiceNumber }]
              : []),
          ],
        },
        ...(formData.linkedShipment
          ? [
              {
                title: "الشحنة المرتبطة",
                icon: <Package size={14} />,
                fields: [
                  { label: "رقم الشحنة", value: formData.linkedShipment.shipmentNumber },
                  { label: "اسم الشحنة", value: formData.linkedShipment.shipmentName || "—" },
                  {
                    label: "مرحلة الشحن",
                    value: getShippingWorkflowLabel(formData.shippingWorkflowStatus || undefined),
                  },
                ],
              },
            ]
          : []),
      ]}
      meta={[
        { label: "تاريخ الصفقة", value: formData.dealDate || "—" },
        {
          label: "رقم العرض الأصلي",
          /* T113-2: الصفقة المولودة من عرض تفتح عرضها بنقرة — الرقم وحده كان
             يُلزم المستخدم بالبحث عنه يدوياً في شاشة العروض. */
          value: formData.sourceQuotationId && formData.originalOfferNumber ? (
            <button
              type="button"
              className="ktra-text-accent hover:underline"
              title={`فتح عرض السعر المصدر ${formData.originalOfferNumber}`}
              onClick={() => openInNewTab(`/price-offers?doc=quote-${formData.sourceQuotationId}`)}
            >
              ← {formData.originalOfferNumber}
            </button>
          ) : (formData.originalOfferNumber || "—"),
        },
        { label: "طريقة الشحن", value: formData.shippingMethod || "—" },
        { label: "أيام الإنتاج", value: formData.productionDays ? String(formData.productionDays) : "—" },
        { label: "أيام التسليم", value: formData.deliveryDays ? String(formData.deliveryDays) : "—" },
      ]}
      columns={[
        {
          key: "name",
          header: "المنتج",
          render: (r) => (
            <div>
              <span className="font-semibold">{r.name || "—"}</span>
              {r.specifications && (
                <span className="block text-[11px] text-[var(--color-text-muted)]">{r.specifications}</span>
              )}
            </div>
          ),
        },
        { key: "model", header: "الموديل", width: "110px", render: (r) => r.modelNumber || "—" },
        { key: "hs", header: "HS", width: "90px", align: "center", render: (r) => r.hsCodePrimary || "—" },
        { key: "qty", header: "الكمية", width: "80px", align: "center", numeric: true, render: (r) => formatQuantity(r.quantity) },
        { key: "price", header: "سعر الوحدة", width: "110px", align: "left", numeric: true, render: (r) => fmt(r.unitPrice) },
        { key: "total", header: "الإجمالي", width: "120px", align: "left", numeric: true, render: (r) => <b>{fmt(r.totalPrice)}</b> },
      ]}
      rows={filledDealItems}
      rowKey={(r) => r.id}
      emptyRowsHint="لا توجد منتجات في الصفقة"
      /* ملخّص كامل داخل المستند (يُرفع لأعلى بدل دوك سفلي عالق) — طلب المالك. */
      totals={[
        { label: "مجموع البنود", value: dealMoney(calculateSubtotal()) },
        ...((formData.discountAmount || 0) > 0
          ? [{ label: "الخصم", value: dealMoney(formData.discountAmount || 0) }]
          : []),
        ...(!formData.shippingIncluded && (formData.shippingCost || 0) > 0
          ? [{ label: "شحن داخل الصين", value: dealMoney(formData.shippingCost || 0) }]
          : []),
        { label: "إجمالي الصفقة (للمورد)", value: dealMoney(calculateGrandTotal()), emphasis: true },
        { label: "المدفوع والمرحّل", value: dealMoney(dealStats.paidAmount) },
        { label: "مسجّل بانتظار الترحيل", value: dealMoney(dealStats.unpostedAmount) },
        {
          label: dealStats.supplierAdvance > 0 ? "دفعة مقدمة على هذه الصفقة" : "المتبقي",
          value: dealMoney(dealStats.supplierAdvance > 0 ? dealStats.supplierAdvance : dealStats.remainingAmount),
          tone: dealStats.supplierAdvance > 0 ? "info" : "warn",
        },
        { label: "رصيد المورد قبل دفعات هذه الصفقة (بالعملة الأساسية)", value: fmt(Number(formData.supplierBalanceBeforeDealPayments) || 0) },
        { label: "رصيد المورد الحالي بعد الدفعات المرحّلة (بالعملة الأساسية)", value: fmt(Number(formData.supplierBalanceAfterDealPayments) || 0), emphasis: true },
      ]}
      sections={[
        ...(dealInstallments.length > 0
          ? [
              {
                key: "installments",
                title: `خطة الأقساط (${dealInstallments.length})`,
                content: (
                  <KitViewTable<DealInstallment>
                    columns={[
                      { key: "no", header: "القسط", width: "70px", align: "center", render: (r) => `#${r.installmentNumber}` },
                      { key: "pct", header: "النسبة", width: "80px", align: "center", numeric: true, render: (r) => `${formatMoney(r.percentage)}%` },
                      { key: "amt", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (r) => fmt(r.amount) },
                      { key: "due", header: "الاستحقاق", width: "110px", align: "center", render: (r) => formatDateLocalized(r.dueDate) || "—" },
                      { key: "st", header: "الحالة", width: "100px", align: "center", render: (r) => String(r.status) },
                    ]}
                    rows={dealInstallments}
                    rowKey={(r) => r.id}
                    showIndex={false}
                    emptyHint="لا توجد أقساط"
                  />
                ),
              },
            ]
          : []),
        ...(dealPayments.length > 0
          ? [
              {
                key: "payments",
                title: `الدفعات (${dealPayments.length})`,
                content: (
                  <KitViewTable<DealPayment>
                    columns={[
                      { key: "date", header: "التاريخ", width: "110px", align: "center", render: (r) => (r.paymentDate || "").slice(0, 10) || "—" },
                      { key: "amt", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (r) => fmt(r.amount) },
                      { key: "rate", header: "سعر الصرف", width: "100px", align: "left", numeric: true, render: (r) => (r.usdToIls ? formatMoney(r.usdToIls) : "—") },
                      { key: "fee", header: "عمولة التحويل", width: "110px", align: "left", numeric: true, render: (r) => fmt(r.transferCost || 0) },
                      {
                        key: "posted",
                        header: "الترحيل",
                        width: "100px",
                        align: "center",
                        render: (r) => r.isPosted ? "مرحّلة" : "غير مرحّلة",
                      },
                      {
                        key: "conf",
                        header: "تأكيد المورد",
                        width: "100px",
                        align: "center",
                        render: (r) =>
                          r.confirmedBySupplier ? (
                            <span className="font-semibold text-emerald-700">مؤكّدة</span>
                          ) : (
                            <span className="text-amber-700">معلّقة</span>
                          ),
                      },
                      { key: "jr", header: "القيد", width: "90px", align: "center", render: (r) => (r.journalId ? `#${r.journalId}` : "—") },
                    ]}
                    rows={dealPayments}
                    rowKey={(r) => r.id}
                    showIndex={false}
                    emptyHint="لا توجد دفعات"
                  />
                ),
              },
            ]
          : []),
        ...(formData.totalVolume || formData.totalWeightKg || formData.totalWeight || formData.certificates || formData.warrantyDuration
          ? [
              {
                key: "measures",
                title: "القياسات والشهادات",
                content: (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <div>
                      <span className="block text-[11px] text-[var(--color-text-muted)]">الحجم (CBM)</span>
                      <b>{formData.totalVolume ? formatQuantity(formData.totalVolume) : "—"}</b>
                    </div>
                    <div>
                      <span className="block text-[11px] text-[var(--color-text-muted)]">الوزن (كغ)</span>
                      <b>{formatQuantity(formData.totalWeightKg ?? formData.totalWeight ?? 0) || "—"}</b>
                    </div>
                    <div>
                      <span className="block text-[11px] text-[var(--color-text-muted)]">الضمان</span>
                      <b>{formData.warrantyDuration ? `${formData.warrantyDuration} شهر` : "—"}</b>
                    </div>
                    <div>
                      <span className="block text-[11px] text-[var(--color-text-muted)]">الشهادات</span>
                      <b>{formData.certificates || "—"}</b>
                    </div>
                  </div>
                ),
              },
            ]
          : []),
        ...(formData.internalNotes || formData.shipmentNotes
          ? [
              {
                key: "notes",
                title: "ملاحظات",
                content: (
                  <div className="space-y-1">
                    {formData.internalNotes && (
                      <p>
                        <span className="text-[var(--color-text-muted)]">داخلية: </span>
                        {formData.internalNotes}
                      </p>
                    )}
                    {formData.shipmentNotes && (
                      <p>
                        <span className="text-[var(--color-text-muted)]">الشحنة: </span>
                        {formData.shipmentNotes}
                      </p>
                    )}
                  </div>
                ),
              },
            ]
          : []),
      ]}
    />
  );

  const toolbarActions: KitToolbarAction[] = [
    { key: "new", label: "إضافة", icon: <Plus />, onClick: handleNewDeal },
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)", icon: <Save />, onClick: !saving ? () => void handleFinalSave() : undefined, disabled: saving },
    ...(viewMode ? [{ key: "edit", label: "تحرير", icon: <Pencil />, onClick: () => setViewMode(false), separatorBefore: true } as KitToolbarAction] : []),
    { key: "print", label: "طباعة (F2)", icon: <Printer />, onClick: () => setShowPrintView(true), separatorBefore: true },
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: onCancel, danger: true, separatorBefore: true },
  ];

  return (
    <div id="deal-print" dir="rtl">
      <KitDocumentShell
        gridFitContent={viewMode}
        title="صفقة استيراد"
        state={formData.id ? `صفقة ${formData.dealNumber || `#${formData.id}`}` : "صفقة جديدة"}
        nav={nav}
        actions={toolbarActions}
        initialTab={requestedTab}
        tabs={viewMode ? [] : [
          { key: "basic", label: "البيانات الأساسية", content: basicInfoTab },
          { key: "terms", label: "الشروط والشحن", content: termsAndShippingTab },
          { key: "payments", label: "الدفعات", content: paymentsTab },
          { key: "stages", label: "المراحل والشحن", content: stagesTab },
          /* الملف ملف صفقة محفوظة: الصفقة الجديدة بلا معرّف لا ملف لها بعد،
             ونقطة الخادم ترسو على `deals/{id}/file/` — فمعرّفٌ غير رقمي يعني
             نداءً يرتدّ 404 بلا سبب مفهوم، ولا تبويب أفضل من تبويبٍ يفشل. */
          ...(importFileEnabled ? [{
            key: IMPORT_FILE_TAB,
            label: "ملف الاستيراد",
            content: (
              <div className="ktra-legacy-tab">
                <React.Suspense fallback={<p className="ktra-hint">جارٍ تحميل ملف الاستيراد…</p>}>
                  <ImportFilePanel dealId={importFileDealId} />
                </React.Suspense>
              </div>
            ),
          }] : []),
          { key: "notes", label: "الملاحظات", content: notesTab },
          { key: "attachments", label: "المرفقات", content: attachmentsTab },
          { key: "activity", label: "سجل النشاطات", content: activityTab },
          { key: "other", label: "بيانات أخرى", content: otherTab },
          ...(formData.id ? [{
            key: "financial_movements",
            label: "الحركات المالية المرتبطة",
            content: (
              <DocumentPaymentsTab
                referenceType="DEAL"
                referenceId={formData.id}
                searchQuery={formData.dealNumber || ""}
              />
            ),
          }] : []),
          ...(formData.id ? [{
            key: "user_activity_log",
            label: "سجل نشاط المستخدمين",
            content: <EntityActivityLog entityType="deal" entityId={formData.id} defaultOpen />,
          }] : []),
        ]}
        totals={viewMode ? undefined : (
          <>
            {/* ج8: الصفقة دولية = بضاعة المورد + شحن داخل الصين − خصم. الضريبة
                تُدفع بالتخليص (لا تدخل إجمالي الصفقة ولا سقف دفعات المورد). */}
            <div className="ktra-total-row"><span>مجموع البنود (قبل الخصم)</span><span className="ktra-total-value">{fmt(calculateSubtotal())}</span></div>
            {/* الخصم والشحن حقلا إدخال لا عرضاً: refactor سابق أسقط
                `onUpdateFinancial` مع `ItemsTableSection`، فبقيت المعادلة أعلاه
                تقرؤهما بلا نقطة كتابة واحدة — أي صفراً أبداً. يُكتبان عبر
                `recalculateTotals` كبقية الحقول ليبقى الإجمالي مشتقّاً لا مُدخَلاً. */}
            <div className="ktra-total-row">
              <span>الخصم</span>
              <input className="ktra-total-value" data-testid="deal-discount-input" type="number" min={0} step="0.01"
                disabled={isDealLocked} placeholder="0" value={formData.discountAmount || ""}
                onChange={(e) => recalculateTotals(items, { discountAmount: Math.max(0, parseFloat(e.target.value) || 0) })} />
            </div>
            {!formData.shippingIncluded && (
              <div className="ktra-total-row">
                <span>شحن داخل الصين</span>
                <input className="ktra-total-value" data-testid="deal-china-freight-input" type="number" min={0} step="0.01"
                  disabled={isDealLocked} placeholder="0" value={formData.shippingCost || ""}
                  onChange={(e) => recalculateTotals(items, { shippingCost: Math.max(0, parseFloat(e.target.value) || 0) })} />
              </div>
            )}
            <div className="ktra-total-row ktra-total-row--grand"><span>مبلغ الصفقة الإجمالي (للمورد)</span><span className="ktra-total-value">{fmt(calculateGrandTotal())}</span></div>
            <div className="ktra-total-row"><span>المدفوع والمرحّل</span><span className="ktra-total-value">{fmt(dealStats.paidAmount)}</span></div>
            <div className="ktra-total-row"><span>مسجّل بانتظار الترحيل</span><span className="ktra-total-value">{fmt(dealStats.unpostedAmount)}</span></div>
            <div className="ktra-total-row">
              <span>{dealStats.supplierAdvance > 0 ? "دفعة مقدمة على هذه الصفقة" : "المتبقي"}</span>
              <span className="ktra-total-value">{fmt(dealStats.supplierAdvance > 0 ? dealStats.supplierAdvance : dealStats.remainingAmount)}</span>
            </div>
          </>
        )}
        status={
          <>
            <span className="ktra-status-item">المستخدم <b>{currentUser?.name || "—"}</b></span>
            <span className="ktra-status-item">الحالة <b>{getOperationalStatusText(getOperationalStatus(formData.status as DealStatus))}</b></span>
            <span className="ktra-status-item">الدفع <b>{getPaymentStatusText(getPaymentStatusFromPayments(formData as Deal))}</b></span>
            {formData.dealNumber && <span className="ktra-status-item">رقم الصفقة <b>{formData.dealNumber}</b></span>}
            <span className="ktra-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="ktra-status-item">{isDealLocked ? "للقراءة فقط" : "قابل للتعديل ✓"}</span>
          </>
        }
      >
        {/* وضع القراءة: مستند مُنسَّق بدل شبكة الإدخال المعطّلة. */}
        {viewMode && dealDocumentView}
        {!viewMode && (
        <KitGrid<DealItem>
          columns={itemColumns}
          rows={items}
          getCell={itemGetCell}
          getRowKey={(r) => r.id}
          onChange={isDealLocked ? undefined : itemOnChange}
          onAddRow={isDealLocked ? undefined : addRow}
          emptyHint="لا توجد بنود — أضف منتجاً (+ فهرس المنتجات)"
        />
        )}
        {!viewMode && !isDealLocked && (
          <button type="button" className="ktra-addrow" onClick={addRow}><Plus className="h-3 w-3" /> إضافة سطر</button>
        )}
      </KitDocumentShell>

      {/* G5: فهرس الموردين المنبثق + مودال الإضافة أُزيلا مع الشبكة العلوية —
          اختيار/إضافة المورد الآن عبر SupplierSearch داخل تبويب «البيانات الأساسية». */}

      {showItemSearch && (
        <ItemSearchModal isOpen={showItemSearch} onClose={() => setShowItemSearch(false)} onSelectItem={(item, price) => { handleAddItemFromModal(item, price); }} items={allDbItems} supplierId={formData.supplierId} />
      )}

      {inlineCreate && (
        <ItemQuickCreateModal
          isOpen
          initialName={inlineCreate.name}
          onClose={() => setInlineCreate(null)}
          onSaved={(newProduct) => {
            const item = productToItem(newProduct);
            setAllDbItems((prev) =>
              prev.some((p) => String(p.id) === String(item.id)) ? prev : [item, ...prev]
            );
            fillRowWithItem(inlineCreate.rowId, item);
            setInlineCreate(null);
          }}
        />
      )}

      {previewImage && <ImagePreviewModal url={previewImage} onClose={() => setPreviewImage(null)} />}

      <SupplierViewModal isOpen={!!viewSupplierId} supplierId={viewSupplierId} onClose={() => setViewSupplierId(null)} />

      {showPrintView && (
        <div className="fixed inset-0 z-[100] ktra-bg-field overflow-y-auto">
          <DealPrintView deal={formData as Deal} currentUser={currentUser} supplier={selectedSupplier} onClose={() => setShowPrintView(false)} onEdit={() => setShowPrintView(false)} />
        </div>
      )}
    </div>
  );
};
