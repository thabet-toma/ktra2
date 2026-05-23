import React, { useState, useEffect, useCallback } from "react";
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
  AseelDocumentShell,
  useRecordNavigation,
  useAseelKeymap,
  AseelIndexPicker,
  AseelGrid,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../../aseel";
import {
  itemsService,
  suppliersService,
} from "../../../services/firestoreService";
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
} from "lucide-react";
import { BasicInfoSection } from "@/components/forms/shared/BasicInfoSection";
import { DealStageControl } from "@/components/forms/deal-parts/DealStageControl";
import { DealPaymentList } from "@/components/forms/deal-parts/DealPaymentList";
import { ItemSearchModal } from "../price-offers/ItemSearchModal";
import { ImagePreviewModal } from "../price-offers/ImagePreviewModal";
import { TermsAndShippingSection } from "@/components/forms/shared/TermsAndShippingSection";
import { AttachmentsSection } from "@/components/forms/shared/AttachmentsSection";
import { dealsService } from "../../../services/dealsService";
import { ActivityLog } from "./ActivityLog";
import { InstallmentManager } from "./InstallmentManager";
import { PaymentProgress } from "./PaymentProgress";
import { SupplierViewModal } from "@/components/common/SupplierViewModal";
import { DealPrintView } from "./DealPrintView";
import { maxPaymentPrincipalForDeal } from "@/utils/dealPaymentLimits";
import { resolvePaymentForSwiftInstallment } from "@/utils/dealPaymentMatch";

type OperationalStatus =
  | "initial"
  | "manufacturing_started"
  | "production_completed"
  | "shipping_preparation"
  | "shipping_in_progress"
  | "shipped"
  | "cancelled";

type PaymentStatus =
  | "not_paid"
  | "claim_raised"
  | "payment_pending_confirmation"
  | "partially_paid"
  | "paid";

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
  const [formData, setFormData] = useState<Partial<Deal>>(deal || {});
  const [items, setItems] = useState<DealItem[]>(deal?.items || []);
  const [activities, setActivities] = useState<DealActivity[]>([]);
  const [installments, setInstallments] = useState<DealInstallment[]>(deal?.installments || []);
  const [installmentPlanEnabled, setInstallmentPlanEnabled] = useState(deal?.installmentPlanEnabled || false);
  const [installmentValidationError, setInstallmentValidationError] = useState("");
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [allDbItems, setAllDbItems] = useState<Item[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [dealsList, setDealsList] = useState<Deal[]>([]);
  const [showSupplierPicker, setShowSupplierPicker] = useState(false);

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
          console.error('Error loading deal:', err);
        }
      }
    },
  });

  useAseelKeymap({
    F2: () => window.print(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"], [name="supplierName"]');
      el?.focus();
    },
    F12: () => { if (!saving) handleFinalSave(); },
    Escape: () => {
      if (showSupplierPicker) { setShowSupplierPicker(false); return; }
      onCancel();
    },
    plus: () => {
      const ae = document.activeElement;
      if (ae?.getAttribute?.('data-aseel-key') === '1') {
        setShowSupplierPicker(true);
      }
    },
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => handleNewDeal(),
  }, { enabled: !showSupplierPicker });

  const handleNewDeal = () => {
    setFormData({});
    setItems([]);
    setInstallments([]);
    setInstallmentPlanEnabled(false);
  };

  useEffect(() => {
    const unsub = dealsService.subscribeToDeals((fetchedDeals: Deal[]) => {
      setDealsList(fetchedDeals);
    });
    return () => unsub();
  }, []);

  const [showItemSearch, setShowItemSearch] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [showPrintView, setShowPrintView] = useState(false);
  const [viewSupplierId, setViewSupplierId] = useState<string | null>(null);
  const selectedSupplier = suppliers.find(s => s.id === formData.supplierId);

  const validateInstallments = (): boolean => {
    if (!installmentPlanEnabled) { setInstallmentValidationError(""); return true; }
    if (installments.length === 0) { setInstallmentValidationError("❌ يجب إضافة دفعة واحدة على الأقل"); return false; }
    const totalPercentage = installments.reduce((sum, i) => sum + (i.percentage || 0), 0);
    if (Math.abs(totalPercentage - 100) > 0.01) { setInstallmentValidationError(`❌ مجموع النسب يجب أن يكون 100%، الحالي: ${totalPercentage.toFixed(2)}%`); return false; }
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
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
    const unsubItems = itemsService.subscribeToItems(setAllDbItems);
    return () => { unsubSuppliers(); unsubItems(); };
  }, []);

  useEffect(() => {
    if (deal?.id) {
      (async () => {
        try { await loadAndSetDealData(deal.id!); await loadActivities(); }
        catch (error) { console.error("❌ Error loading deal:", error); alert("حدث خطأ في تحميل بيانات الصفقة"); }
      })();
    }
  }, [deal?.id]);

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
    const taxableBase = afterDiscount + validShipping;
    let taxAmount = 0;
    if (currentData.taxType === 'amount') { taxAmount = currentData.taxAmount || 0; }
    else { taxAmount = taxableBase * ((currentData.taxRate || 0) / 100); }
    const grandTotal = taxableBase + taxAmount;
    setItems(newItems);
    setFormData((prev) => ({ ...prev, ...updatedFields, items: newItems, subtotal: itemsSubtotal, taxAmount, totalAmount: grandTotal }));
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
    if (!formData.id) { alert("يرجى حفظ الصفقة أولاً"); return; }
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
          const capAdd = maxPaymentPrincipalForDeal(formData);
          if (addAmt > capAdd + 1e-6) { alert(`لا يُسمح بدفع يتجاوز قيمة الصفقة. الأقصى المتاح: $${capAdd.toLocaleString()}`); setLoading(false); return; }
          await dealsService.addPayment(formData.id, { ...cleanData(data), type: paymentType, id: `payment_${Date.now()}`, paymentDate: new Date().toISOString(), confirmedBySupplier: false }, currentUser.id, currentUser.name, currentUser.role || "user");
          break;
        }
        case "claim": {
          const claimAmt = Number(data?.amount ?? 0);
          const capClaim = maxPaymentPrincipalForDeal(formData);
          if (claimAmt > capClaim + 1e-6) { alert(`لا يُسمح بدفع يتجاوز قيمة الصفقة. الأقصى المتاح لتسجيل مطالبة: $${capClaim.toLocaleString()}`); setLoading(false); return; }
          await dealsService.addPayment(formData.id, { ...cleanData(data), type: paymentType, id: `payment_${Date.now()}`, paymentDate: new Date().toISOString(), confirmedBySupplier: false }, currentUser.id, currentUser.name, currentUser.role || "user");
          const nextSt = suggestStatusAfterClaim(formData, data.installmentNumber);
          if (nextSt) { try { await dealsService.updateDealStatus(formData.id, nextSt, currentUser.id, currentUser.name, currentUser.role || "user", "رفع مطالبة — جاهز لمسار الدفع"); } catch (e) { console.warn("updateDealStatus after claim:", e); } }
          break;
        }
        case "swift": {
          const instNum = data?.installmentNumber != null && Number.isFinite(Number(data.installmentNumber)) ? Number(data.installmentNumber) : undefined;
          const resolved = resolvePaymentForSwiftInstallment(formData.payments, paymentType, instNum, paymentId ?? null);
          if (resolved.rejectReason) { alert(`❌ ${resolved.rejectReason}`); setLoading(false); return; }
          let payment = resolved.payment;
          let swiftPaymentId = payment?.id != null ? String(payment.id) : undefined;
          if (!swiftPaymentId) {
            if (!payment) {
              const swiftAmt = Number(data.amount ?? 0);
              const capSwift = maxPaymentPrincipalForDeal(formData);
              if (swiftAmt > capSwift + 1e-6) { alert(`لا يُسمح بدفع يتجاوز قيمة الصفقة. الأقصى المتاح: $${capSwift.toLocaleString()}`); setLoading(false); return; }
              await dealsService.addPayment(formData.id, { type: paymentType, amount: swiftAmt, paymentDate: data.paymentDate || new Date().toISOString(), usdToIls: Number(data.usdToIls ?? 0), transferCost: Number(data.transferCost ?? data.transferFee ?? 0), notes: data.notes || "", installmentId: data.installmentId, installmentNumber: data.installmentNumber, confirmedBySupplier: false, alibabaClaimImage: undefined } as Omit<DealPayment, "id">, currentUser.id, currentUser.name, currentUser.role || "user");
              const fresh = await dealsService.getDeal(formData.id);
              const again = resolvePaymentForSwiftInstallment(fresh.payments, paymentType, instNum, null);
              if (again.rejectReason) { alert(`❌ ${again.rejectReason}`); setLoading(false); return; }
              payment = again.payment; swiftPaymentId = payment?.id != null ? String(payment.id) : undefined;
            } else { swiftPaymentId = String(payment.id); }
          }
          if (!swiftPaymentId) { alert("تعذر إنشاء أو العثور على سجل الدفعة"); setLoading(false); return; }
          if (!data.cashBoxId) { alert("يجب اختيار صندوق مالي لتنفيذ عملية الدفع"); setLoading(false); return; }
          if (!data.bankSwiftImage) { alert("يجب رفع صورة السليب أولاً"); setLoading(false); return; }
          const swiftPrincipal = Number(data.amount ?? 0);
          const capSwiftEdit = maxPaymentPrincipalForDeal(formData, swiftPaymentId);
          if (swiftPrincipal > capSwiftEdit + 1e-6) { alert(`لا يُسمح بمبلغ يتجاوز قيمة الصفقة. الأقصى المسموح لهذه العملية: $${capSwiftEdit.toLocaleString()}`); setLoading(false); return; }
          const totalPayment = (data.amount || 0) + (data.transferCost || 0);
          if (!window.confirm(`هل أنت متأكد من خصم ${totalPayment.toLocaleString()} من الصندوق المحدد؟`)) { setLoading(false); return; }
          try {
            await dealsService.updatePaymentWithSwift(formData.id, swiftPaymentId, cleanData({ ...data, dealNumber: formData.dealNumber }), currentUser.id, currentUser.name, currentUser.role || "user", data.cashBoxId);
            const postTry = await dealsService.tryAutoPostDealPaymentAccounting(formData.id, swiftPaymentId, { cashBoxExternalId: data.cashBoxId ? String(data.cashBoxId).trim() : undefined });
            if (postTry.posted && postTry.journalId != null) swiftAutoPostJournalId = postTry.journalId;
          } catch (error: any) { if (error.message.includes('الرصيد غير كافي')) { alert(`❌ ${error.message}`); throw error; } throw error; }
          break;
        }
        case "confirm":
          if (paymentId) {
            lastConfirmPaymentId = paymentId;
            const paymentToConfirm = formData.payments?.find(p => p.id === paymentId);
            if (paymentToConfirm) {
              if (paymentToConfirm.bankSwiftImage && !paymentToConfirm.cashBoxId) { alert("⚠️ هذه الدفعة تحتوي على سليب ولكن لم يتم خصمها من الصندوق بعد"); setLoading(false); return; }
              if (paymentToConfirm.cashBoxId && !paymentToConfirm.bankSwiftImage) { alert("️ تم خصم المبلغ من الصندوق ولكن لم يتم رفع صورة السليب"); setLoading(false); return; }
            }
            confirmAccountingMeta = await dealsService.confirmPayment(formData.id, paymentId, currentUser.id, currentUser.name, currentUser.role || "user", data.supplierConfirmationImage, data.supplierNotes, data.paymentConfirmationDate, data.cashBoxId);
          }
          break;
        case "unpost":
          if (String(currentUser.role || "").toLowerCase() !== "manager") { alert("هذا الإجراء متاح للمدير فقط من الواجهة."); setLoading(false); return; }
          if (!paymentId || !formData.id) { setLoading(false); return; }
          unpostAccountingMeta = await dealsService.unpostDealPayment(formData.id, paymentId);
          break;
        case "cancel":
          if (paymentId) await dealsService.cancelPayment(formData.id, paymentId, currentUser.id, currentUser.name, currentUser.role || "user");
          break;
        case "linkJournal": {
          if (!paymentId) { setLoading(false); return; }
          const jid = Number(data?.journalId);
          if (!Number.isFinite(jid) || jid <= 0) { alert("رقم القيد غير صالح."); setLoading(false); return; }
          await dealsService.linkDealPaymentJournal(String(formData.id), String(paymentId), jid);
          break;
        }
      }
      const loadedAfterPay = await loadAndSetDealData(formData.id);
      await loadActivities();
      switch (operation) {
        case "swift":
          if (swiftAutoPostJournalId != null) {
            alert("✅ تم تنفيذ الدفع ورفع السليب، وتم إنشاء قيد المحاسبة وربطه بالدفعة.");
            onOpenAccountingJournal?.(swiftAutoPostJournalId, { dealId: formData.id!, dealNumber: formData.dealNumber || "", displayName: [formData.dealNumber, formData.dealDescription || formData.originalOfferNumber || formData.factoryName || ""].filter(Boolean).join(" — ") });
          } else { alert("✅ تم تنفيذ الدفع ورفع السليب بنجاح"); }
          break;
        case "claim": alert("✅ تم رفع المطالبة. يمكنك الآن تسجيل الدفع من تبويب «تسجيل الدفع» في أي وقت."); break;
        case "confirm": {
          const pid = lastConfirmPaymentId;
          const row = pid ? loadedAfterPay?.payments?.find((x) => String(x.id) === String(pid)) : undefined;
          const jid = confirmAccountingMeta?.journalId ?? row?.journalId;
          alert(formatSupplierConfirmAlertText({ posted: Boolean(row?.isPosted), journalId: jid, openManualJournal: confirmAccountingMeta?.openManualJournal, meta: confirmAccountingMeta ?? undefined }));
          if (confirmAccountingMeta?.openManualJournal || (confirmAccountingMeta?.journalId != null && Number(confirmAccountingMeta.journalId) > 0)) {
            const j = Number(confirmAccountingMeta.journalId);
            const dealDesc = formData.dealDescription || formData.originalOfferNumber || formData.factoryName || selectedSupplier?.tradeName || "";
            onOpenAccountingJournal?.(confirmAccountingMeta?.openManualJournal ? null : j, { dealId: formData.id!, dealNumber: formData.dealNumber || '', displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(' — ') });
          }
          break;
        }
        case "cancel": alert("✅ تم إلغاء الدفعة من سجل الصفقة"); break;
        case "unpost": {
          const rj = unpostAccountingMeta?.reversal_journal_id;
          const vj = unpostAccountingMeta?.voided_journal_id;
          const note = unpostAccountingMeta?.accounting_note || "";
          alert(`تم إلغاء ترحيل الدفعة محاسبياً.\n\n• قيد عكسي مرحّل: ${rj != null ? `#${rj}` : "—"}\n• القيد الأصلي أصبح غير مرحّل: ${vj != null ? `#${vj}` : "—"}\n\nالدفعة أصبحت قابلة للحذف من «حذف من السجل».\n${note ? `\n${note}` : ""}`);
          break;
        }
        case "linkJournal": alert("✅ تم ربط الدفعة بالقيد. سيظهر «فتح في المحاسبة» في سجل المدفوعات بعد التحديث."); break;
        default: alert("تم حفظ العملية بنجاح");
      }
    } catch (error: any) { console.error("Payment Operation Error:", error); alert(`❌ ${error.message || "حدث خطأ أثناء حفظ العملية"}`); }
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
      alert(formatSupplierConfirmAlertText({ posted: Boolean(row?.isPosted), journalId: jid, openManualJournal: acc.openManualJournal, meta: acc }));
      if (acc.openManualJournal || (acc.journalId != null && Number(acc.journalId) > 0)) {
        const j = Number(acc.journalId);
        const dealDesc = formData.dealDescription || formData.originalOfferNumber || formData.factoryName || selectedSupplier?.tradeName || "";
        onOpenAccountingJournal?.(acc.openManualJournal ? null : j, { dealId: formData.id!, dealNumber: formData.dealNumber || '', displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(' — ') });
      }
    } catch (error: any) {
      console.error("Error confirming payment:", error);
      let diag = "";
      try {
        if (formData.id && confirmationData.paymentId) {
          const d = await dealsService.getPaymentPostingDiagnostics(formData.id, String(confirmationData.paymentId));
          if (d.blockers?.length) diag = "\n\n— تشخيص من الخادم —\n" + d.blockers.map((b, i) => `${i + 1}. ${b}`).join("\n");
        }
      } catch { /* ignore */ }
      alert(`حدث خطأ في تأكيد الدفعة${error?.message ? `:\n${error.message}` : ""}${diag}`);
    } finally { setLoading(false); }
  };

  const handleStatusChange = async (newStatus: DealStatus, notes?: string) => {
    if (!formData.id) return;
    try {
      setLoading(true);
      await dealsService.updateDealStatus(formData.id, newStatus, currentUser.id, currentUser.name, currentUser.role || "user", notes);
      await loadAndSetDealData(formData.id); await loadActivities();
      alert(`تم تغيير حالة الصفقة إلى: ${newStatus}`);
    } catch (error) { console.error("Error changing status:", error); alert("حدث خطأ في تغيير الحالة"); }
    finally { setLoading(false); }
  };

  const handleShippingWorkflowChange = async (code: ShippingWorkflowStatus) => {
    if (!formData.id) return;
    try {
      setLoading(true);
      await dealsService.patchShippingWorkflow(formData.id, code);
      await loadAndSetDealData(formData.id); await loadActivities();
      alert("تم حفظ مرحلة الشحن والتصنيع");
    } catch (error) { console.error("shipping workflow:", error); alert("تعذر حفظ مرحلة الشحن"); }
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
    if (installmentPlanEnabled && !validateInstallments()) { alert("يرجى تصحيح أخطاء نظام الدفعات قبل الحفظ"); return; }
    const invoiceToCheck = formData.supplierInvoiceNumber?.trim() || undefined;
    const linkToCheck = formData.alibabaOrderLink?.trim() || undefined;
    if (invoiceToCheck || linkToCheck) {
      setSaving(true);
      try {
        const checkResult = await dealsService.checkDealUniqueness(invoiceToCheck, linkToCheck, formData.id);
        if (!checkResult.isUnique) {
          setSaving(false);
          if (checkResult.errorField === 'invoice') alert(`⚠️ تنبيه خطير!\n\nرقم الفاتورة: "${invoiceToCheck}"\nمستخدم بالفعل في الصفقة رقم: (${checkResult.existingDealNumber})\n\n⛔ يمنع تكرار رقم الفاتورة في النظام بالكامل.`);
          else if (checkResult.errorField === 'link') alert(`⚠️ تنبيه خطير!\n\nرابط علي بابا هذا مستخدم بالفعل في الصفقة رقم: (${checkResult.existingDealNumber})\n\n⛔ يمنع تكرار نفس الطلب (الرابط) لصفقتين مختلفتين.`);
          return;
        }
      } catch (error) { console.error("Uniqueness check failed", error); }
    }
    setSaving(true);
    try {
      const finalFormData: Partial<Deal> = { ...formData, items, subtotal: formData.subtotal, taxAmount: formData.taxAmount, totalAmount: formData.totalAmount, updatedAt: new Date().toISOString(), updatedBy: currentUser.id };
      if (installmentPlanEnabled) { finalFormData.installments = installments; finalFormData.installmentPlanEnabled = true; }
      else { finalFormData.installments = []; finalFormData.installmentPlanEnabled = false; }
      const isExistingDeal = deal?.id || formData.id;
      if (isExistingDeal) {
        const dealId = deal?.id || formData.id!;
        const { payments: _paymentsOmitted, ...dealUpdateWithoutPayments } = finalFormData;
        await handleUpdateDeal(dealUpdateWithoutPayments, "تحديث بيانات الصفقة", "تم تحديث بيانات الصفقة (البنود والحقول؛ سجل الدفعات دون تغيير من هذا الزر)");
        const updatedDeal = await dealsService.getDeal(dealId);
        setFormData(updatedDeal); setItems(updatedDeal.items || []); setInstallments(updatedDeal.installments || []); setInstallmentPlanEnabled(updatedDeal.installmentPlanEnabled || false);
        alert("✅ تم تحديث الصفقة بنجاح!");
      } else {
        if (!window.confirm("هل أنت متأكد من إنشاء الصفقة الجديدة؟")) { setSaving(false); return; }
        const createData: any = {
          supplierId: formData.supplierId || "", factoryName: formData.factoryName || "", items, payments: [],
          totalAmount: finalFormData.totalAmount || 0, subtotal: finalFormData.subtotal || 0,
          shippingCost: finalFormData.shippingCost || 0, shippingIncluded: finalFormData.shippingIncluded || false,
          discountAmount: finalFormData.discountAmount || 0, taxRate: finalFormData.taxRate || 0,
          taxAmount: finalFormData.taxAmount || 0, dealDate: formData.dealDate || new Date().toISOString().split("T")[0],
          createdBy: currentUser.id, updatedBy: currentUser.id, status: "initial",
          installments: finalFormData.installments || [], installmentPlanEnabled: finalFormData.installmentPlanEnabled || false,
        };
        const optionalFields = ["priceOfferId", "dealDescription", "originalOfferNumber", "alibabaOrderLink", "internalNotes", "notes", "invoiceLink", "supplierInvoiceNumber", "supplierName", "shippingMethod", "productionDays", "deliveryDays", "quoteImages", "quotePdfs", "quote_images", "quote_pdfs", "productionTime", "paymentMethod", "deliveryTime", "warrantyDuration", "certificates", "shipping_method_id", "shippingMethodCode", "shippingMethodName", "shipmentNotes", "totalWeight", "totalVolume", "isReadyStock", "shippingDetails", "productionPath"];
        optionalFields.forEach((field) => { if (formData[field as keyof Deal] !== undefined && formData[field as keyof Deal] !== null) createData[field] = formData[field as keyof Deal]; });
        const dealId = await dealsService.createDeal(createData);
        const createdDeal = await dealsService.getDeal(dealId);
        setFormData(createdDeal); setItems(createdDeal.items || []); setInstallments(createdDeal.installments || []); setInstallmentPlanEnabled(createdDeal.installmentPlanEnabled || false);
        await loadActivities();
        alert(`✅ تم إنشاء الصفقة بنجاح برقم: ${createdDeal.dealNumber}`);
      }
    } catch (e: any) { console.error("❌ Save Error:", e); alert(`❌ فشل الحفظ: ${e.message}`); }
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

  const calculateTaxAmount = (): number => {
    const subtotal = calculateSubtotal();
    const netAfterDiscount = Math.max(0, subtotal - (formData.discountAmount || 0));
    if (formData.taxType === 'amount') return formData.taxAmount || 0;
    return netAfterDiscount * ((formData.taxRate || 0) / 100);
  };

  const calculateGrandTotal = (): number => {
    const subtotal = calculateSubtotal();
    const netAfterDiscount = Math.max(0, subtotal - (formData.discountAmount || 0));
    const shipping = formData.shippingIncluded ? 0 : (formData.shippingCost || 0);
    const taxableBase = netAfterDiscount + shipping;
    let taxAmount = 0;
    if (formData.taxType === 'amount') { taxAmount = formData.taxAmount || 0; }
    else { taxAmount = taxableBase * ((formData.taxRate || 0) / 100); }
    return taxableBase + taxAmount;
  };

  const validateForm = (): boolean => {
    if (!formData.supplierId) { alert("يرجى اختيار المورد أولاً"); return false; }
    if (items.length === 0) { alert("يرجى إضافة منتجات على الأقل"); return false; }
    return true;
  };

  const getOperationalStatus = (status: DealStatus): OperationalStatus => {
    if (status === "manufacturing_started") return "manufacturing_started";
    if (status === "production_completed") return "production_completed";
    if (status === "shipping_preparation") return "shipping_preparation";
    if (status === "shipping_in_progress") return "shipping_in_progress";
    if (status === "shipped") return "shipped";
    if (status === "cancelled") return "cancelled";
    return "initial";
  };

  const getOperationalStatusText = (status: OperationalStatus): string => {
    const m: Record<OperationalStatus, string> = { initial: "أولية", manufacturing_started: "قيد التصنيع", production_completed: "تم التصنيع", shipping_preparation: "تجهيز الشحن", shipping_in_progress: "جاري الشحن", shipped: "تم الشحن", cancelled: "ملغاة" };
    return m[status] || status;
  };

  const getOperationalStatusStyles = (status: OperationalStatus): string => {
    const s: Record<OperationalStatus, string> = { initial: "aseel-bg-panel aseel-text-ink aseel-border-soft", manufacturing_started: "aseel-bg-accent-bg aseel-text-accent aseel-border-accent", production_completed: "bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]", shipping_preparation: "aseel-bg-panel aseel-text-ink aseel-border-soft", shipping_in_progress: "bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]", shipped: "bg-green-50 text-green-700 aseel-border-soft", cancelled: "aseel-bg-panel aseel-text-state aseel-border-soft" };
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
    const s: Record<PaymentStatus, string> = { not_paid: "aseel-bg-panel aseel-text-state aseel-border-soft", claim_raised: "aseel-bg-panel aseel-text-ink aseel-border-soft", payment_pending_confirmation: "aseel-bg-accent-bg aseel-text-accent aseel-border-accent", partially_paid: "aseel-bg-panel aseel-text-ink aseel-border-soft", paid: "aseel-bg-panel aseel-text-ink aseel-border-soft" };
    return s[status] || s["not_paid"];
  };

  const dealStats = {
    totalAmount: calculateGrandTotal(),
    itemsCount: items.length,
    paidAmount: formData.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0,
    remainingAmount: calculateGrandTotal() - (formData.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0),
    paymentPercentage: calculateGrandTotal() > 0 ? ((formData.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0) / calculateGrandTotal()) * 100 : 0
  };

  const fmt = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const fld = (label: string, node: React.ReactNode) => (
    <label className="aseel-field">
      <span className="aseel-field-label">{label}</span>
      {node}
    </label>
  );

  /* ───────────── أعمدة جدول البنود ───────────── */
  const itemColumns: AseelGridColumn<DealItem>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "itemId", header: "رقم الصنف", width: "100px" },
    { key: "name", header: "اسم الصنف", width: "25%" },
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
    <button type="button" className="aseel-cell-picker" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} data-aseel-key="1" onClick={() => setShowItemSearch(true)} title="اختر صنفاً (+ فهرس الأصناف)">
      {row.itemId ? `#${row.itemId}` : "— اختر صنفاً —"}
    </button>
  );

  const renderDeleteCell = (row: DealItem) =>
    formData.status === 'shipped' || formData.status === 'cancelled' ? null : (
      <button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => removeRow(row.id)} title="حذف السطر"><Trash2 className="h-3 w-3" /></button>
    );

  itemColumns[1].render = renderItemIdCell;
  itemColumns[7].render = renderDeleteCell;

  /* ───────────── تبويبات ───────────── */
  const notesTab = (
    <textarea className="aseel-input" rows={3} style={{ width: "100%" }} disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.notes || formData.internalNotes || ""} onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))} />
  );

  const otherTab = (
    <div className="aseel-other">
      <label className="aseel-field aseel-field--inline">
        <input type="checkbox" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} checked={formData.shippingIncluded || false} onChange={(e) => setFormData(prev => ({ ...prev, shippingIncluded: e.target.checked }))} />
        <span className="aseel-field-label" style={{ flex: "unset" }}>الأسعار تشمل الشحن</span>
      </label>
      <p className="aseel-hint">حالة الصفقة: {getOperationalStatusText(getOperationalStatus(formData.status as DealStatus))} — الدفع: {getPaymentStatusText(getPaymentStatusFromPayments(formData as Deal))}</p>
    </div>
  );

  const basicInfoTab = (
    <div className="aseel-legacy-tab">
      <BasicInfoSection
        data={formData}
        setData={setFormData}
        suppliers={suppliers}
        isDeal={true}
        dealsService={dealsService}
        items={items}
        readOnly={formData.status === 'shipped' || formData.status === 'cancelled'}
      />
    </div>
  );

  const termsAndShippingTab = (
    <div className="aseel-legacy-tab">
      <TermsAndShippingSection
        data={formData}
        setData={setFormData}
        readOnly={formData.status === 'shipped' || formData.status === 'cancelled'}
      />
    </div>
  );

  const paymentsTab = (
    <div className="aseel-legacy-tab" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
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
        readOnly={formData.status === 'shipped' || formData.status === 'cancelled'}
      />
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
        readOnly={formData.status === "shipped" || formData.status === "cancelled"}
      />
      {formData.id ? (
        <DealPaymentList
          deal={formData}
          currentUser={currentUser}
          onPaymentOperation={handlePaymentOperation}
          onConfirmSupplier={handlePaymentConfirmation}
          onOpenAccountingJournal={onOpenAccountingJournal}
        />
      ) : null}
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
    <div className="aseel-legacy-tab">
      <AttachmentsSection
        data={formData}
        setData={setFormData}
      />
    </div>
  );

  const activityTab = (
    <div className="aseel-legacy-tab">
      {formData.id && activities.length > 0 ? (
        <ActivityLog activities={activities} />
      ) : (
        <p className="aseel-hint">لا يوجد سجل نشاطات بعد.</p>
      )}
    </div>
  );

  const toolbarActions: AseelToolbarAction[] = [
    { key: "new", label: "إضافة", icon: <Plus />, onClick: handleNewDeal },
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)", icon: <Save />, onClick: !saving ? () => void handleFinalSave() : undefined, disabled: saving },
    { key: "print", label: "طباعة (F2)", icon: <Printer />, onClick: () => window.print(), separatorBefore: true },
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: onCancel, danger: true, separatorBefore: true },
  ];

  return (
    <div id="deal-print" dir="rtl" style={{ height: "calc(100vh - 13rem)", minHeight: 560 }}>
      <AseelDocumentShell
        title="صفقة استيراد"
        state={formData.id ? `صفقة ${formData.dealNumber || `#${formData.id}`}` : "صفقة جديدة"}
        nav={nav}
        actions={toolbarActions}
        header={
          <>
            {fld("رقم الصفقة", <input className="aseel-input" readOnly value={formData.id ? `#${formData.dealNumber || formData.id}` : "— جديدة —"} />)}
            {fld("التاريخ", <input className="aseel-input" type="date" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.dealDate || ""} onChange={(e) => setFormData(prev => ({ ...prev, dealDate: e.target.value }))} />)}
            {fld("تاريخ الاستحقاق", <input className="aseel-input" type="date" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.dueDate || ""} onChange={(e) => setFormData(prev => ({ ...prev, dueDate: e.target.value }))} />)}
            {fld("رقم المستند", <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.supplierInvoiceNumber || ""} onChange={(e) => setFormData(prev => ({ ...prev, supplierInvoiceNumber: e.target.value }))} placeholder="رقم فاتورة المورد" />)}
            {fld("المورد", <div className="aseel-pickfield">
              <input className="aseel-input aseel-input--hl" data-aseel-field="supplier" data-aseel-key="1" readOnly disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={selectedSupplier ? `#${selectedSupplier.id}` : ""} placeholder="+ للفهرس" onClick={() => { if (formData.status !== 'shipped' && formData.status !== 'cancelled') setShowSupplierPicker(true); }} />
              <button type="button" className="aseel-ellipsis" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} onClick={() => setShowSupplierPicker(true)} title="فهرس الموردين (+)">…</button>
            </div>)}
            {fld("الاسم", <input className="aseel-input" readOnly value={selectedSupplier?.tradeName || formData.factoryName || ""} />)}
            {fld("رقم العرض", <input className="aseel-input" readOnly value={formData.originalOfferNumber || ""} />)}
            {fld("مشتغل مرخص", <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.licensedDealerNo || ""} onChange={(e) => setFormData(prev => ({ ...prev, licensedDealerNo: e.target.value }))} placeholder="رقم المشتغل المرخص" />)}
            {fld("وصف الصفقة", <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.dealDescription || ""} onChange={(e) => setFormData(prev => ({ ...prev, dealDescription: e.target.value }))} placeholder="وصف مختصر" />)}
            {fld("رابط علي بابا", <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.alibabaOrderLink || ""} onChange={(e) => setFormData(prev => ({ ...prev, alibabaOrderLink: e.target.value }))} placeholder="https://…" />)}
            {fld("طريقة الشحن", <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} value={formData.shippingMethod || ""} onChange={(e) => setFormData(prev => ({ ...prev, shippingMethod: e.target.value }))} placeholder="بحري / جوي / بري" />)}
            <label className="aseel-field aseel-field--inline">
              <input type="checkbox" disabled={formData.status === 'shipped' || formData.status === 'cancelled'} checked={formData.shippingIncluded || false} onChange={(e) => setFormData(prev => ({ ...prev, shippingIncluded: e.target.checked }))} />
              <span className="aseel-field-label" style={{ flex: "unset" }}>الأسعار تشمل الشحن</span>
            </label>
          </>
        }
        tabs={[
          { key: "basic", label: "البيانات الأساسية", content: basicInfoTab },
          { key: "terms", label: "الشروط والشحن", content: termsAndShippingTab },
          { key: "payments", label: "الدفعات والمراحل", content: paymentsTab },
          { key: "notes", label: "الملاحظات", content: notesTab },
          { key: "attachments", label: "المرفقات", content: attachmentsTab },
          { key: "activity", label: "سجل النشاطات", content: activityTab },
          { key: "other", label: "بيانات أخرى", content: otherTab },
        ]}
        totals={
          <>
            <div className="aseel-total-row"><span>مجموع البنود (قبل الخصم)</span><span className="aseel-total-value">{fmt(calculateSubtotal())}</span></div>
            {(formData.discountAmount || 0) > 0 && <div className="aseel-total-row"><span>الخصم</span><span className="aseel-total-value">{fmt(formData.discountAmount || 0)}</span></div>}
            <div className="aseel-total-row"><span>المجموع قبل الضريبة</span><span className="aseel-total-value">{fmt(Math.max(0, calculateSubtotal() - (formData.discountAmount || 0)) + (formData.shippingIncluded ? 0 : (formData.shippingCost || 0)))}</span></div>
            <div className="aseel-total-row"><span>الضريبة</span><span className="aseel-total-value">{fmt(calculateTaxAmount())}</span></div>
            <div className="aseel-total-row aseel-total-row--grand"><span>مبلغ الصفقة الإجمالي</span><span className="aseel-total-value">{fmt(calculateGrandTotal())}</span></div>
            <div className="aseel-total-row"><span>المدفوع</span><span className="aseel-total-value">{fmt(dealStats.paidAmount)}</span></div>
            <div className="aseel-total-row"><span>المتبقي</span><span className="aseel-total-value">{fmt(dealStats.remainingAmount)}</span></div>
          </>
        }
        status={
          <>
            <span className="aseel-status-item">المستخدم <b>{currentUser?.name || "—"}</b></span>
            <span className="aseel-status-item">الحالة <b>{getOperationalStatusText(getOperationalStatus(formData.status as DealStatus))}</b></span>
            <span className="aseel-status-item">الدفع <b>{getPaymentStatusText(getPaymentStatusFromPayments(formData as Deal))}</b></span>
            {formData.dealNumber && <span className="aseel-status-item">رقم الصفقة <b>{formData.dealNumber}</b></span>}
            <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="aseel-status-item">{formData.status === 'shipped' || formData.status === 'cancelled' ? "للقراءة فقط" : "قابل للتعديل ✓"}</span>
          </>
        }
      >
        {/* تفاصيل تجارية ظاهرة دائماً — مضمونة الظهور بدون أي header overflow */}
        <div className="aseel-commercial-band">
          <div className="aseel-commercial-band__title">تفاصيل تجارية</div>
          <div className="aseel-commercial-band__grid">
            <label className="aseel-field">
              <span className="aseel-field-label">وصف الصفقة</span>
              <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={formData.dealDescription || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, dealDescription: e.target.value }))}
                placeholder="وصف مختصر للصفقة" />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">رابط علي بابا</span>
              <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={formData.alibabaOrderLink || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, alibabaOrderLink: e.target.value }))}
                placeholder="https://alibaba.com/…" />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">طريقة الشحن</span>
              <select className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={formData.shippingMethod || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, shippingMethod: e.target.value }))}>
                <option value="">— اختر —</option>
                <option value="sea">بحري</option>
                <option value="air">جوي</option>
                <option value="land">بري</option>
                <option value="express">إكسبرس</option>
              </select>
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">رقم العرض</span>
              <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={formData.originalOfferNumber || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, originalOfferNumber: e.target.value }))}
                placeholder="رقم العرض الأصلي" />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">طريقة الدفع</span>
              <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={(formData as any).paymentMethod || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, paymentMethod: e.target.value }) as any)}
                placeholder="T/T / L/C / …" />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">مدة الإنتاج (أيام)</span>
              <input className="aseel-input" type="number" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={(formData as any).productionDays ?? ""}
                onChange={(e) => setFormData(prev => ({ ...prev, productionDays: e.target.value === "" ? null : Number(e.target.value) }) as any)} />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">مدة التوصيل (أيام)</span>
              <input className="aseel-input" type="number" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={(formData as any).deliveryDays ?? ""}
                onChange={(e) => setFormData(prev => ({ ...prev, deliveryDays: e.target.value === "" ? null : Number(e.target.value) }) as any)} />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">الضمان</span>
              <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={(formData as any).warrantyDuration || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, warrantyDuration: e.target.value }) as any)}
                placeholder="مدة الضمان" />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">الشهادات</span>
              <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={(formData as any).certificates || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, certificates: e.target.value }) as any)}
                placeholder="CE / FCC / ISO …" />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">رابط الفاتورة</span>
              <input className="aseel-input" disabled={formData.status === 'shipped' || formData.status === 'cancelled'}
                value={(formData as any).invoiceLink || ""}
                onChange={(e) => setFormData(prev => ({ ...prev, invoiceLink: e.target.value }) as any)}
                placeholder="رابط أو رقم الفاتورة الأصلية" />
            </label>
          </div>
          <p className="aseel-hint" style={{ marginTop: 6 }}>
            هذه الحقول تُعرض هنا دائماً للوصول السريع — كما يَتم الحفظ على نفس الحقول
            في تبويب «البيانات الأساسية» و«الشروط والشحن».
          </p>
        </div>

        <AseelGrid<DealItem>
          columns={itemColumns}
          rows={items}
          getCell={itemGetCell}
          getRowKey={(r) => r.id}
          onChange={formData.status === 'shipped' || formData.status === 'cancelled' ? undefined : itemOnChange}
          onAddRow={formData.status === 'shipped' || formData.status === 'cancelled' ? undefined : addRow}
          emptyHint="لا توجد بنود — أضف صنفاً (+ فهرس الأصناف)"
        />
        {formData.status !== 'shipped' && formData.status !== 'cancelled' && (
          <button type="button" className="aseel-addrow" onClick={addRow}><Plus className="h-3 w-3" /> إضافة سطر</button>
        )}
      </AseelDocumentShell>

      {/* فهرس الموردين */}
      <AseelIndexPicker<Supplier>
        open={showSupplierPicker}
        title="فهرس الموردين"
        rows={suppliers}
        columns={[
          { key: "id", header: "الرقم", width: "70px", value: (r) => r.id },
          { key: "tradeName", header: "الاسم التجاري", value: (r) => r.tradeName || "" },
          { key: "city", header: "المدينة", value: (r) => r.city || "" },
        ]}
        getRowKey={(r) => r.id}
        searchValue={(r) => `${r.id} ${r.tradeName || ""} ${r.city || ""}`}
        onSelect={(r) => { setFormData({ ...formData, supplierId: r.id, supplierName: r.tradeName || r.alias || "" }); setShowSupplierPicker(false); }}
        onClose={() => setShowSupplierPicker(false)}
      />

      {showItemSearch && (
        <ItemSearchModal isOpen={showItemSearch} onClose={() => setShowItemSearch(false)} onSelectItem={(item, price) => { handleAddItemFromModal(item, price); }} items={allDbItems} supplierId={formData.supplierId} />
      )}

      {previewImage && <ImagePreviewModal url={previewImage} onClose={() => setPreviewImage(null)} />}

      <SupplierViewModal isOpen={!!viewSupplierId} supplierId={viewSupplierId} onClose={() => setViewSupplierId(null)} />

      {showPrintView && (
        <div className="fixed inset-0 z-[100] aseel-bg-field overflow-y-auto">
          <DealPrintView deal={formData as Deal} currentUser={currentUser} supplier={selectedSupplier} onClose={() => setShowPrintView(false)} onEdit={() => setShowPrintView(false)} />
        </div>
      )}
    </div>
  );
};
