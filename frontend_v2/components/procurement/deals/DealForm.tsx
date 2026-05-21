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
} from "../../aseel";
import {
  itemsService,
  suppliersService,
} from "../../../services/firestoreService";
import {
  Save,
  X,
  FileText,
  History,
  AlertCircle,
  Info,
  CreditCard,
  LayoutList,
  Package,
  Paperclip,
  Truck,
  DollarSign,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Layers,
  Wallet,
  Factory,
  CheckCircle2,
  Clock,
  Edit,
  Eye,
  Calculator,
  Percent,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  AlertTriangle,
  Download,
  Upload,
  Calendar,
  User as UserIcon,
  Phone,
  Mail,
  Globe,
  MapPin,
  Package2,
  Scale,
  Box,
  Truck as TruckIcon,
  Shield,
  FileCheck,
  ClipboardList,
  BarChart3,
  Target,
  Sparkles,
  Zap,
  Activity,
  RefreshCw,
  Plus,
  Trash2,
  Printer,
  FileDown,
} from "lucide-react";
import { BasicInfoSection } from "@/components/forms/shared/BasicInfoSection";
import { DealStageControl } from "@/components/forms/deal-parts/DealStageControl";
import { ItemsTableSection } from "@/components/forms/shared/ItemsTableSection";
import { DealPaymentList } from "@/components/forms/deal-parts/DealPaymentList";
import { ItemSearchModal } from "../price-offers/ItemSearchModal";
import { ImagePreviewModal } from "../price-offers/ImagePreviewModal";
import { TermsAndShippingSection } from "@/components/forms/shared/TermsAndShippingSection";
import { AttachmentsSection } from "@/components/forms/shared/AttachmentsSection";
import { dealsService } from "../../../services/dealsService";
import { ActivityLog } from "./ActivityLog";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { InstallmentManager } from "./InstallmentManager";
import { PaymentProgress } from "./PaymentProgress";
import { SupplierViewModal } from "@/components/common/SupplierViewModal";
import { DealPrintView } from "./DealPrintView";
import { maxPaymentPrincipalForDeal } from "@/utils/dealPaymentLimits";
import { resolvePaymentForSwiftInstallment } from "@/utils/dealPaymentMatch";

// تعريف أنواع الحالات
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
  /** null = قيد يومية جديد (بعد تأكيد المورد — ترحيل يدوي) */
  onOpenAccountingJournal?: (
    journalId: number | null,
    dealRef?: { dealId: string; dealNumber: string; displayName: string }
  ) => void;
}

/** بعد رفع المطالبة: ترقية حالة الصفقة إلى «بانتظار الدفع» عندما تكون الحالة الحالية منطقية */
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
  // --- State Management ---
  const [formData, setFormData] = useState<Partial<Deal>>(deal || {});
  const [items, setItems] = useState<DealItem[]>(deal?.items || []);
  const [activities, setActivities] = useState<DealActivity[]>([]);

  const [installments, setInstallments] = useState<DealInstallment[]>(
    deal?.installments || []
  );
  const [installmentPlanEnabled, setInstallmentPlanEnabled] = useState(
    deal?.installmentPlanEnabled || false
  );
  const [installmentValidationError, setInstallmentValidationError] = useState("");

  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [allDbItems, setAllDbItems] = useState<Item[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  // Aseel Navigation State
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

  // M3-T1: Aseel keyboard shortcuts — real handlers (no placeholders).
  useAseelKeymap({
    F2: () => window.print(),
    F6: () => {
      // Focus the first searchable field (supplier name) for quick lookup.
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"], [name="supplierName"]');
      el?.focus();
    },
    F12: () => { if (!saving) handleFinalSave(); },
    Escape: () => {
      if (showSupplierPicker) { setShowSupplierPicker(false); return; }
      onCancel();
    },
    plus: () => {
      // Open supplier index when focus is on an opt-in field (data-aseel-key="1").
      const ae = document.activeElement;
      if (ae?.getAttribute?.('data-aseel-key') === '1') {
        setShowSupplierPicker(true);
      }
    },
    // N0-T11: Ctrl+nav handlers
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

  // Load deals list for navigation
  useEffect(() => {
    const unsub = dealsService.subscribeToDeals((fetchedDeals: Deal[]) => {
      setDealsList(fetchedDeals);
    });
    return () => unsub();
  }, []);

  // Modals State
  const [showItemSearch, setShowItemSearch] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'info' | 'items' | 'payments' | 'documents'>('info');

  // البحث عن المورد المختار حالياً للحصول على تفاصيله (الاسم المستعار والتجاري)
  const selectedSupplier = suppliers.find(s => s.id === formData.supplierId);
  const [viewSupplierId, setViewSupplierId] = useState<string | null>(null);

  const [showPrintView, setShowPrintView] = useState(false); // 🟢 حالة جديدة للطباعة


  // التحقق من صحة نظام الدفعات
  const validateInstallments = (): boolean => {
    if (!installmentPlanEnabled) {
      setInstallmentValidationError("");
      return true;
    }

    if (installments.length === 0) {
      setInstallmentValidationError("❌ يجب إضافة دفعة واحدة على الأقل");
      return false;
    }

    const totalPercentage = installments.reduce((sum, installment) => {
      return sum + (installment.percentage || 0);
    }, 0);

    if (Math.abs(totalPercentage - 100) > 0.01) {
      setInstallmentValidationError(`❌ مجموع النسب يجب أن يكون 100%، الحالي: ${totalPercentage.toFixed(2)}%`);
      return false;
    }

    const hasZeroPercentage = installments.some(installment => (installment.percentage || 0) <= 0);
    if (hasZeroPercentage) {
      setInstallmentValidationError("❌ جميع الدفعات يجب أن يكون لها نسبة أكبر من 0%");
      return false;
    }

    const grandTotal = calculateGrandTotal();
    const hasMismatchedAmounts = installments.some(installment => {
      const expectedAmount = ((installment.percentage || 0) / 100) * grandTotal;
      const actualAmount = installment.amount || 0;
      return Math.abs(expectedAmount - actualAmount) > 0.01;
    });

    if (hasMismatchedAmounts) {
      setInstallmentValidationError("❌ عدم تطابق بين النسب والمبالغ");
      return false;
    }

    setInstallmentValidationError("");
    return true;
  };

  // تحديث مبالغ الدفعات
  useEffect(() => {
    if (installmentPlanEnabled && installments.length > 0) {
      const grandTotal = calculateGrandTotal();
      const updatedInstallments = installments.map(installment => ({
        ...installment,
        amount: Math.round(((installment.percentage || 0) / 100) * grandTotal * 100) / 100
      }));
      setInstallments(updatedInstallments);
    }
  }, [formData.totalAmount, formData.subtotal, formData.discountAmount, formData.taxRate, formData.shippingCost]);

  // Load Activities
  useEffect(() => {
    if (formData.id) {
      loadActivities();
    }
  }, [formData.id]);

  const loadActivities = async () => {
    if (!formData.id) return;
    try {
      const loadedActivities = await dealsService.getDealActivities(formData.id);
      setActivities(loadedActivities);
    } catch (error) {
      console.error("Error loading activities:", error);
    }
  };

  // Subscriptions
  useEffect(() => {
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
    const unsubItems = itemsService.subscribeToItems(setAllDbItems);

    return () => {
      unsubSuppliers();
      unsubItems();
    };
  }, []);

  useEffect(() => {
    if (deal?.id) {
      const loadInitialDealData = async () => {
        try {
          await loadAndSetDealData(deal.id!);
          await loadActivities();
        } catch (error) {
          console.error("❌ Error loading deal:", error);
          alert("حدث خطأ في تحميل بيانات الصفقة");
        }
      };
      loadInitialDealData();
    }
  }, [deal?.id]);

  const toggleInstallmentPlan = (enabled: boolean) => {
    setInstallmentPlanEnabled(enabled);

    if (enabled && installments.length === 0) {
      const defaultInstallment: DealInstallment = {
        id: crypto.randomUUID(),
        installmentNumber: 1,
        percentage: 100,
        amount: calculateGrandTotal(),
        status: 'unpaid',
        notes: 'دفعة واحدة',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      setInstallments([defaultInstallment]);
      setFormData(prev => ({
        ...prev,
        installments: [defaultInstallment],
        installmentPlanEnabled: true
      }));
    }

    if (!enabled) {
      setInstallments([]);
      setInstallmentValidationError("");
      setFormData(prev => ({
        ...prev,
        installments: [],
        installmentPlanEnabled: false
      }));
    }
  };

  // --- Recalculate Logic ---
  const recalculateTotals = (
    newItems: DealItem[] = items,
    updatedFields: Partial<Deal> = {}
  ) => {
    const currentData = { ...formData, ...updatedFields };
    const itemsSubtotal = newItems.reduce(
      (sum, item) => sum + (item.totalPrice || 0),
      0
    );
    const validShipping = currentData.shippingIncluded
      ? 0
      : currentData.shippingCost || 0;
    const afterDiscount = Math.max(
      0,
      itemsSubtotal - (currentData.discountAmount || 0)
    );
    const taxableBase = afterDiscount + validShipping;

    let taxAmount = 0;
    if (currentData.taxType === 'amount') {
      taxAmount = currentData.taxAmount || 0;
    } else {
      taxAmount = taxableBase * ((currentData.taxRate || 0) / 100);
    }

    const grandTotal = taxableBase + taxAmount;

    setItems(newItems);
    setFormData((prev) => ({
      ...prev,
      ...updatedFields,
      items: newItems,
      subtotal: itemsSubtotal,
      taxAmount,
      totalAmount: grandTotal,
    }));
  };

  // --- Handlers ---
  const handleAddItemFromModal = (item: Item, lastPrice?: number) => {
    const dealItem: DealItem = {
      id: crypto.randomUUID(),
      itemId: item.id,
      name: item.name,
      categoryId: item.categoryId,
      categoryName: item.categoryName,
      specifications: item.specifications || item.modelNumber || "",
      hsCodePrimary: item.hsCodePrimary,
      modelNumber: item.modelNumber, // 🟢 Add this line
      imageUrls: item.imageUrls || [],
      quantity: 1,
      unitPrice: lastPrice || 0,
      totalPrice: lastPrice || 0,
      factoryImageUrl: item.imageUrls?.[0],
    };

    const updatedItems = [...items, dealItem];
    recalculateTotals(updatedItems);
    setShowItemSearch(false);
  };

  const handleUpdateItem = (index: number, field: string, value: any) => {
    const updatedItems = [...items];
    const item = { ...updatedItems[index], [field]: value };
    if (field === "quantity" || field === "unitPrice") {
      item.totalPrice =
        (Number(item.quantity) || 0) * (Number(item.unitPrice) || 0);
    }
    updatedItems[index] = item;
    recalculateTotals(updatedItems);
  };

  const handleRemoveItem = (index: number) => {
    recalculateTotals(items.filter((_, i) => i !== index));
  };

  // Payment Handlers
  const handlePaymentOperation = async (
    operation:
      | "claim"
      | "swift"
      | "add"
      | "confirm"
      | "cancel"
      | "unpost"
      | "linkJournal",
    paymentType: string,
    data: any,
    paymentId?: string
  ) => {
    if (!formData.id) {
      alert("يرجى حفظ الصفقة أولاً");
      return;
    }

    try {
      setLoading(true);

      /* إلغاء الترحيل لا يحتاج PATCH للصفقة أولاً؛ الحفظ اليدوي كان يسبب تعليقاً أو فشلاً
         (مثلاً تحقق الخادم أو شبكة) قبل وصول طلب unpost */
      if (operation !== "unpost" && operation !== "linkJournal") {
        try {
          const updateData: Partial<Deal> = {
            items,
            installments: installmentPlanEnabled ? installments : [],
            installmentPlanEnabled,
            totalAmount: formData.totalAmount,
            subtotal: formData.subtotal,
            taxAmount: formData.taxAmount,
            discountAmount: formData.discountAmount,
            shippingCost: formData.shippingCost,
            shippingIncluded: formData.shippingIncluded,
          };

          await dealsService.updateDeal(
            formData.id,
            updateData,
            currentUser.id,
            currentUser.name,
            currentUser.role || "user",
            "",
            ""
          );
        } catch (err) {
          console.error("Auto-save failed:", err);
        }
      }

      const cleanData = (data: any): any => {
        return Object.fromEntries(
          Object.entries(data).filter(([_, v]) => v !== undefined)
        );
      };

      let confirmAccountingMeta:
        | {
            journalId?: number;
            message: string;
            openManualJournal?: boolean;
            postingBlockers?: string[];
          }
        | undefined;
      let lastConfirmPaymentId: string | undefined;
      let unpostAccountingMeta:
        | {
            reversal_journal_id?: number;
            voided_journal_id?: number;
            accounting_note?: string;
          }
        | undefined;
      /** بعد تنفيذ السليب: ترحيل تلقائي عبر API → فتح القيد */
      let swiftAutoPostJournalId: number | undefined;

      switch (operation) {
        case "add": {
          const addAmt = Number(data?.amount ?? 0);
          const capAdd = maxPaymentPrincipalForDeal(formData);
          if (addAmt > capAdd + 1e-6) {
            alert(
              `لا يُسمح بدفع يتجاوز قيمة الصفقة. الأقصى المتاح: $${capAdd.toLocaleString()}`
            );
            setLoading(false);
            return;
          }
          await dealsService.addPayment(
            formData.id,
            {
              ...cleanData(data),
              type: paymentType,
              id: `payment_${Date.now()}`,
              paymentDate: new Date().toISOString(),
              confirmedBySupplier: false,
            },
            currentUser.id,
            currentUser.name,
            currentUser.role || "user"
          );
          break;
        }

        case "claim": {
          const claimAmt = Number(data?.amount ?? 0);
          const capClaim = maxPaymentPrincipalForDeal(formData);
          if (claimAmt > capClaim + 1e-6) {
            alert(
              `لا يُسمح بدفع يتجاوز قيمة الصفقة. الأقصى المتاح لتسجيل مطالبة: $${capClaim.toLocaleString()}`
            );
            setLoading(false);
            return;
          }
          await dealsService.addPayment(
            formData.id,
            {
              ...cleanData(data),
              type: paymentType,
              id: `payment_${Date.now()}`,
              paymentDate: new Date().toISOString(),
              confirmedBySupplier: false,
            },
            currentUser.id,
            currentUser.name,
            currentUser.role || "user"
          );
          {
            const nextSt = suggestStatusAfterClaim(formData, data.installmentNumber);
            if (nextSt) {
              try {
                await dealsService.updateDealStatus(
                  formData.id,
                  nextSt,
                  currentUser.id,
                  currentUser.name,
                  currentUser.role || "user",
                  "رفع مطالبة — جاهز لمسار الدفع"
                );
              } catch (e) {
                console.warn("updateDealStatus after claim:", e);
              }
            }
          }
          break;
        }

        case "swift": {
          const instNumRaw = data?.installmentNumber;
          const instNum =
            instNumRaw != null && Number.isFinite(Number(instNumRaw))
              ? Number(instNumRaw)
              : undefined;

          const resolved = resolvePaymentForSwiftInstallment(
            formData.payments,
            paymentType,
            instNum,
            paymentId ?? null
          );
          if (resolved.rejectReason) {
            alert(`❌ ${resolved.rejectReason}`);
            setLoading(false);
            return;
          }

          let payment = resolved.payment;
          let swiftPaymentId =
            payment?.id != null ? String(payment.id) : undefined;

          if (!swiftPaymentId) {
            if (!payment) {
              const swiftAmt = Number(data.amount ?? 0);
              const capSwift = maxPaymentPrincipalForDeal(formData);
              if (swiftAmt > capSwift + 1e-6) {
                alert(
                  `لا يُسمح بدفع يتجاوز قيمة الصفقة. الأقصى المتاح: $${capSwift.toLocaleString()}`
                );
                setLoading(false);
                return;
              }
              await dealsService.addPayment(
                formData.id,
                {
                  type: paymentType,
                  amount: swiftAmt,
                  paymentDate: data.paymentDate || new Date().toISOString(),
                  usdToIls: Number(data.usdToIls ?? 0),
                  transferCost: Number(data.transferCost ?? data.transferFee ?? 0),
                  notes: data.notes || "",
                  installmentId: data.installmentId,
                  installmentNumber: data.installmentNumber,
                  confirmedBySupplier: false,
                  alibabaClaimImage: undefined,
                } as Omit<DealPayment, "id">,
                currentUser.id,
                currentUser.name,
                currentUser.role || "user"
              );
              const fresh = await dealsService.getDeal(formData.id);
              const again = resolvePaymentForSwiftInstallment(
                fresh.payments,
                paymentType,
                instNum,
                null
              );
              if (again.rejectReason) {
                alert(`❌ ${again.rejectReason}`);
                setLoading(false);
                return;
              }
              payment = again.payment;
              swiftPaymentId =
                payment?.id != null ? String(payment.id) : undefined;
            } else {
              swiftPaymentId = String(payment.id);
            }
          }

          if (!swiftPaymentId) {
            alert("تعذر إنشاء أو العثور على سجل الدفعة");
            setLoading(false);
            return;
          }

          if (!data.cashBoxId) {
            alert("يجب اختيار صندوق مالي لتنفيذ عملية الدفع");
            setLoading(false);
            return;
          }

          if (!data.bankSwiftImage) {
            alert("يجب رفع صورة السليب أولاً");
            setLoading(false);
            return;
          }

          const swiftPrincipal = Number(data.amount ?? 0);
          const capSwiftEdit = maxPaymentPrincipalForDeal(formData, swiftPaymentId);
          if (swiftPrincipal > capSwiftEdit + 1e-6) {
            alert(
              `لا يُسمح بمبلغ يتجاوز قيمة الصفقة. الأقصى المسموح لهذه العملية: $${capSwiftEdit.toLocaleString()}`
            );
            setLoading(false);
            return;
          }

          const totalPayment = (data.amount || 0) + (data.transferCost || 0);
          const confirmMessage = `هل أنت متأكد من خصم ${totalPayment.toLocaleString()} من الصندوق المحدد؟`;

          if (!window.confirm(confirmMessage)) {
            setLoading(false);
            return;
          }

          try {
            await dealsService.updatePaymentWithSwift(
              formData.id,
              swiftPaymentId,
              cleanData({
                ...data,
                dealNumber: formData.dealNumber
              }),
              currentUser.id,
              currentUser.name,
              currentUser.role || "user",
              data.cashBoxId
            );
            const postTry = await dealsService.tryAutoPostDealPaymentAccounting(
              formData.id,
              swiftPaymentId,
              {
                cashBoxExternalId: data.cashBoxId
                  ? String(data.cashBoxId).trim()
                  : undefined,
              }
            );
            if (postTry.posted && postTry.journalId != null) {
              swiftAutoPostJournalId = postTry.journalId;
            }
          } catch (error: any) {
            if (error.message.includes('الرصيد غير كافي')) {
              alert(`❌ ${error.message}`);
              throw error;
            }
            throw error;
          }
          break;
        }

        case "confirm":
          if (paymentId) {
            lastConfirmPaymentId = paymentId;
            const paymentToConfirm = formData.payments?.find(p => p.id === paymentId);

            if (paymentToConfirm) {
              if (paymentToConfirm.bankSwiftImage && !paymentToConfirm.cashBoxId) {
                alert("⚠️ هذه الدفعة تحتوي على سليب ولكن لم يتم خصمها من الصندوق بعد");
                setLoading(false);
                return;
              }

              if (paymentToConfirm.cashBoxId && !paymentToConfirm.bankSwiftImage) {
                alert("⚠️ تم خصم المبلغ من الصندوق ولكن لم يتم رفع صورة السليب");
                setLoading(false);
                return;
              }
            }

            confirmAccountingMeta = await dealsService.confirmPayment(
              formData.id,
              paymentId,
              currentUser.id,
              currentUser.name,
              currentUser.role || "user",
              data.supplierConfirmationImage,
              data.supplierNotes,
              data.paymentConfirmationDate,
              data.cashBoxId
            );
          }
          break;

        case "unpost":
          if (String(currentUser.role || "").toLowerCase() !== "manager") {
            alert("هذا الإجراء متاح للمدير فقط من الواجهة.");
            setLoading(false);
            return;
          }
          if (!paymentId || !formData.id) {
            setLoading(false);
            return;
          }
          unpostAccountingMeta = await dealsService.unpostDealPayment(
            formData.id,
            paymentId
          );
          break;

        case "cancel":
          if (paymentId) {
            await dealsService.cancelPayment(
              formData.id,
              paymentId,
              currentUser.id,
              currentUser.name,
              currentUser.role || "user"
            );
          }
          break;

        case "linkJournal": {
          if (!paymentId) {
            setLoading(false);
            return;
          }
          const jid = Number(data?.journalId);
          if (!Number.isFinite(jid) || jid <= 0) {
            alert("رقم القيد غير صالح.");
            setLoading(false);
            return;
          }
          await dealsService.linkDealPaymentJournal(
            String(formData.id),
            String(paymentId),
            jid
          );
          break;
        }
      }

      const loadedAfterPay = await loadAndSetDealData(formData.id);
      await loadActivities();

      switch (operation) {
        case "swift": {
          if (swiftAutoPostJournalId != null) {
            alert(
              "✅ تم تنفيذ الدفع ورفع السليب، وتم إنشاء قيد المحاسبة وربطه بالدفعة."
            );
            onOpenAccountingJournal?.(swiftAutoPostJournalId, {
              dealId: formData.id!,
              dealNumber: formData.dealNumber || "",
              displayName: [
                formData.dealNumber,
                formData.dealDescription ||
                  formData.originalOfferNumber ||
                  formData.factoryName ||
                  "",
              ]
                .filter(Boolean)
                .join(" — "),
            });
          } else {
            alert("✅ تم تنفيذ الدفع ورفع السليب بنجاح");
          }
          break;
        }
        case "claim":
          alert("✅ تم رفع المطالبة. يمكنك الآن تسجيل الدفع من تبويب «تسجيل الدفع» في أي وقت.");
          break;
        case "confirm": {
          const pid = lastConfirmPaymentId;
          const row = pid
            ? loadedAfterPay?.payments?.find((x) => String(x.id) === String(pid))
            : undefined;
          const jid = confirmAccountingMeta?.journalId ?? row?.journalId;
          const posted = Boolean(row?.isPosted);
          alert(
            formatSupplierConfirmAlertText({
              posted,
              journalId: jid,
              openManualJournal: confirmAccountingMeta?.openManualJournal,
              meta: confirmAccountingMeta ?? undefined,
            })
          );
          if (confirmAccountingMeta?.openManualJournal) {
            const dealDesc =
              formData.dealDescription ||
              formData.originalOfferNumber ||
              formData.factoryName ||
              selectedSupplier?.tradeName ||
              "";
            onOpenAccountingJournal?.(null, {
              dealId: formData.id!,
              dealNumber: formData.dealNumber || '',
              displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(' — '),
            });
          } else if (
            confirmAccountingMeta?.journalId != null &&
            Number(confirmAccountingMeta.journalId) > 0
          ) {
            const j = Number(confirmAccountingMeta.journalId);
            const dealDesc =
              formData.dealDescription ||
              formData.originalOfferNumber ||
              formData.factoryName ||
              selectedSupplier?.tradeName ||
              "";
            onOpenAccountingJournal?.(j, {
              dealId: formData.id!,
              dealNumber: formData.dealNumber || "",
              displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(" — "),
            });
          }
          break;
        }
        case "cancel":
          alert("✅ تم إلغاء الدفعة من سجل الصفقة");
          break;
        case "unpost": {
          const rj = unpostAccountingMeta?.reversal_journal_id;
          const vj = unpostAccountingMeta?.voided_journal_id;
          const note = unpostAccountingMeta?.accounting_note || "";
          alert(
            `تم إلغاء ترحيل الدفعة محاسبياً.\n\n` +
              `• قيد عكسي مرحّل: ${rj != null ? `#${rj}` : "—"}\n` +
              `• القيد الأصلي أصبح غير مرحّل: ${vj != null ? `#${vj}` : "—"}\n\n` +
              `الدفعة أصبحت قابلة للحذف من «حذف من السجل».\n` +
              (note ? `\n${note}` : "")
          );
          break;
        }
        case "linkJournal":
          alert(
            "✅ تم ربط الدفعة بالقيد. سيظهر «فتح في المحاسبة» في سجل المدفوعات بعد التحديث."
          );
          break;
        default:
          alert("تم حفظ العملية بنجاح");
      }

    } catch (error: any) {
      console.error("Payment Operation Error:", error);
      alert(`❌ ${error.message || "حدث خطأ أثناء حفظ العملية"}`);
    } finally {
      setLoading(false);
    }
  };

  const handlePaymentConfirmation = async (confirmationData: any) => {
    if (!formData.id || !confirmationData.paymentId) return;
    try {
      setLoading(true);
      const acc = await dealsService.confirmPayment(
        formData.id,
        confirmationData.paymentId,
        currentUser.id,
        currentUser.name,
        currentUser.role || "user",
        confirmationData.supplierConfirmationImage,
        confirmationData.supplierNotes,
        confirmationData.paymentConfirmationDate,
        confirmationData.cashBoxId
      );
      const loaded = await loadAndSetDealData(formData.id);
      await loadActivities();
      const row = loaded?.payments?.find(
        (x) => String(x.id) === String(confirmationData.paymentId)
      );
      const jid = acc.journalId ?? row?.journalId;
      const posted = Boolean(row?.isPosted);
      alert(
        formatSupplierConfirmAlertText({
          posted,
          journalId: jid,
          openManualJournal: acc.openManualJournal,
          meta: acc,
        })
      );
      if (acc.openManualJournal) {
        const dealDesc =
          formData.dealDescription ||
          formData.originalOfferNumber ||
          formData.factoryName ||
          selectedSupplier?.tradeName ||
          "";
        onOpenAccountingJournal?.(null, {
          dealId: formData.id!,
          dealNumber: formData.dealNumber || '',
          displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(' — '),
        });
      } else if (acc.journalId != null && Number(acc.journalId) > 0) {
        const j = Number(acc.journalId);
        const dealDesc =
          formData.dealDescription ||
          formData.originalOfferNumber ||
          formData.factoryName ||
          selectedSupplier?.tradeName ||
          "";
        onOpenAccountingJournal?.(j, {
          dealId: formData.id!,
          dealNumber: formData.dealNumber || "",
          displayName: [formData.dealNumber, dealDesc].filter(Boolean).join(" — "),
        });
      }
    } catch (error: any) {
      console.error("Error confirming payment:", error);
      let diag = "";
      try {
        if (formData.id && confirmationData.paymentId) {
          const d = await dealsService.getPaymentPostingDiagnostics(
            formData.id,
            String(confirmationData.paymentId)
          );
          if (d.blockers?.length) {
            diag =
              "\n\n— تشخيص من الخادم —\n" +
              d.blockers.map((b, i) => `${i + 1}. ${b}`).join("\n");
          }
        }
      } catch {
        /* ignore */
      }
      alert(
        `حدث خطأ في تأكيد الدفعة${error?.message ? `:\n${error.message}` : ""}${diag}`
      );
    } finally {
      setLoading(false);
    }
  };

  // Status Change
  const handleStatusChange = async (newStatus: DealStatus, notes?: string) => {
    if (!formData.id) return;
    try {
      setLoading(true);
      await dealsService.updateDealStatus(
        formData.id,
        newStatus,
        currentUser.id,
        currentUser.name,
        currentUser.role || "user",
        notes
      );
      await loadAndSetDealData(formData.id);
      await loadActivities();
      alert(`تم تغيير حالة الصفقة إلى: ${newStatus}`);
    } catch (error) {
      console.error("Error changing status:", error);
      alert("حدث خطأ في تغيير الحالة");
    } finally {
      setLoading(false);
    }
  };

  const handleShippingWorkflowChange = async (code: ShippingWorkflowStatus) => {
    if (!formData.id) return;
    try {
      setLoading(true);
      await dealsService.patchShippingWorkflow(formData.id, code);
      await loadAndSetDealData(formData.id);
      await loadActivities();
      alert("تم حفظ مرحلة الشحن والتصنيع");
    } catch (error) {
      console.error("shipping workflow:", error);
      alert("تعذر حفظ مرحلة الشحن");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateDeal = async (
    updates: Partial<Deal>,
    action: string,
    details?: string
  ) => {
    if (!formData.id) return;

    try {
      await dealsService.updateDeal(
        formData.id,
        updates,
        currentUser.id,
        currentUser.name,
        currentUser.role || "user",
        action,
        details
      );

      const updatedDeal = await loadAndSetDealData(formData.id);
      await loadActivities();
      return updatedDeal;
    } catch (error) {
      console.error("❌ Error updating deal:", error);
      throw error;
    }
  };

  const handleFinalSave = async () => {
    if (!validateForm()) return;

    if (installmentPlanEnabled && !validateInstallments()) {
      alert("يرجى تصحيح أخطاء نظام الدفعات قبل الحفظ");
      return;
    }

    // ==========================================
    // 🛑 الفحص الشامل (فاتورة + رابط)
    // ==========================================
    const invoiceToCheck = formData.supplierInvoiceNumber?.trim() || undefined;
    const linkToCheck = formData.alibabaOrderLink?.trim() || undefined;

    // نفحص فقط إذا كان هناك فاتورة أو رابط
    if (invoiceToCheck || linkToCheck) {
      setSaving(true); // تشغيل التحميل

      try {
        const checkResult = await dealsService.checkDealUniqueness(
          invoiceToCheck,
          linkToCheck,
          formData.id // لاستثناء الصفقة الحالية عند التعديل
        );

        if (!checkResult.isUnique) {
          setSaving(false); // إيقاف التحميل

          if (checkResult.errorField === 'invoice') {
            alert(`⚠️ تنبيه خطير!\n\nرقم الفاتورة: "${invoiceToCheck}"\nمستخدم بالفعل في الصفقة رقم: (${checkResult.existingDealNumber})\n\n⛔ يمنع تكرار رقم الفاتورة في النظام بالكامل.`);
          } else if (checkResult.errorField === 'link') {
            alert(`⚠️ تنبيه خطير!\n\nرابط علي بابا هذا مستخدم بالفعل في الصفقة رقم: (${checkResult.existingDealNumber})\n\n⛔ يمنع تكرار نفس الطلب (الرابط) لصفقتين مختلفتين.`);
          }

          return; // ⛔ إيقاف الحفظ نهائياً
        }

      } catch (error) {
        console.error("Uniqueness check failed", error);
      }
      // لا توقف setSaving هنا لأننا سنكمل الحفظ
    }
    // ==========================================

    setSaving(true);

    try {
      const finalFormData: Partial<Deal> = {
        ...formData,
        items,
        subtotal: formData.subtotal,
        taxAmount: formData.taxAmount,
        totalAmount: formData.totalAmount,
        updatedAt: new Date().toISOString(),
        updatedBy: currentUser.id,
      };

      if (installmentPlanEnabled) {
        finalFormData.installments = installments;
        finalFormData.installmentPlanEnabled = true;
      } else {
        finalFormData.installments = [];
        finalFormData.installmentPlanEnabled = false;
      }

      const isExistingDeal = deal?.id || formData.id;

      if (isExistingDeal) {
        const dealId = deal?.id || formData.id!;
        /**
         * لا نرسل payments مع «حفظ الصفقة» — دمج formData القديم مع الخادم كان يعيد صفوفاً
         * محذوفة أو يُنشئ تكراراً (حذف دفعة ثم حفظ يعيد السطر من الذاكرة).
         * سجل الدفعات يُحدَّث فقط عبر مسارات الدفع / الحذف / التأكيد (dealsService).
         */
        const { payments: _paymentsOmitted, ...dealUpdateWithoutPayments } =
          finalFormData;

        await handleUpdateDeal(
          dealUpdateWithoutPayments,
          "تحديث بيانات الصفقة",
          "تم تحديث بيانات الصفقة (البنود والحقول؛ سجل الدفعات دون تغيير من هذا الزر)"
        );

        const updatedDeal = await dealsService.getDeal(dealId);
        setFormData(updatedDeal);
        setItems(updatedDeal.items || []);
        setInstallments(updatedDeal.installments || []);
        setInstallmentPlanEnabled(updatedDeal.installmentPlanEnabled || false);

        alert("✅ تم تحديث الصفقة بنجاح!");
      } else {
        if (!window.confirm("هل أنت متأكد من إنشاء الصفقة الجديدة؟")) {
          setSaving(false);
          return;
        }

        const createData: any = {
          supplierId: formData.supplierId || "",
          factoryName: formData.factoryName || "",
          items: items,
          payments: [],
          totalAmount: finalFormData.totalAmount || 0,
          subtotal: finalFormData.subtotal || 0,
          shippingCost: finalFormData.shippingCost || 0,
          shippingIncluded: finalFormData.shippingIncluded || false,
          discountAmount: finalFormData.discountAmount || 0,
          taxRate: finalFormData.taxRate || 0,
          taxAmount: finalFormData.taxAmount || 0,
          dealDate: formData.dealDate || new Date().toISOString().split("T")[0],
          createdBy: currentUser.id,
          updatedBy: currentUser.id,
          status: "initial",
          installments: finalFormData.installments || [],
          installmentPlanEnabled: finalFormData.installmentPlanEnabled || false,
        };

        const optionalFields = [
          "priceOfferId",
          "dealDescription",
          "originalOfferNumber",
          "alibabaOrderLink",
          "internalNotes",
          "notes",
          "invoiceLink",
          "supplierInvoiceNumber",
          "supplierName",
          "shippingMethod",
          "productionDays",
          "deliveryDays",
          "quoteImages",
          "quotePdfs",
          "quote_images",
          "quote_pdfs",
          "productionTime",
          "paymentMethod",
          "deliveryTime",
          "warrantyDuration",
          "certificates",
          "shipping_method_id",
          "shippingMethodCode",
          "shippingMethodName",
          "shipmentNotes",
          "totalWeight",
          "totalVolume",
          "isReadyStock",
          "shippingDetails",
          "productionPath",
        ];

        optionalFields.forEach((field) => {
          if (formData[field as keyof Deal] !== undefined && formData[field as keyof Deal] !== null) {
            createData[field] = formData[field as keyof Deal];
          }
        });

        // Current signature: dealsService.createDeal(data) — audit happens
        // server-side via authenticated user. Earlier Firestore signature took
        // (data, userId, userName, userRole); not needed on the SQL pipeline.
        const dealId = await dealsService.createDeal(createData);

        const createdDeal = await dealsService.getDeal(dealId);
        setFormData(createdDeal);
        setItems(createdDeal.items || []);
        setInstallments(createdDeal.installments || []);
        setInstallmentPlanEnabled(createdDeal.installmentPlanEnabled || false);
        await loadActivities();

        alert(`✅ تم إنشاء الصفقة بنجاح برقم: ${createdDeal.dealNumber}`);
      }

    } catch (e: any) {
      console.error("❌ Save Error:", e);
      alert(`❌ فشل الحفظ: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const calculateSubtotal = (): number => {
    return items.reduce((sum, item) => {
      const qty = item.quantity || 0;
      const price = item.unitPrice || 0;
      return sum + (qty * price);
    }, 0);
  };

  const loadAndSetDealData = async (dealId: string) => {
    try {
      const loadedDeal = await dealsService.getDeal(dealId);
      setFormData(loadedDeal);
      setItems(loadedDeal.items || []);
      setInstallments(loadedDeal.installments || []);
      setInstallmentPlanEnabled(loadedDeal.installmentPlanEnabled || false);
      return loadedDeal;
    } catch (error) {
      console.error("❌ خطأ في تحميل بيانات الصفقة:", error);
      throw error;
    }
  };

  const calculateTaxAmount = (): number => {
    const subtotal = calculateSubtotal();
    const discountAmount = formData.discountAmount || 0;
    const netAfterDiscount = Math.max(0, subtotal - discountAmount);
    const taxRate = formData.taxRate || 0;

    if (formData.taxType === 'amount') {
      return formData.taxAmount || 0;
    }
    return netAfterDiscount * (taxRate / 100);
  };

  const calculateGrandTotal = (): number => {
    const subtotal = calculateSubtotal();
    const discountAmount = formData.discountAmount || 0;
    const netAfterDiscount = Math.max(0, subtotal - discountAmount);
    const shipping = formData.shippingIncluded ? 0 : (formData.shippingCost || 0);
    // الوعاء الضريبي = صافي البضاعة بعد الخصم + الشحن (متسق مع recalculateTotals)
    const taxableBase = netAfterDiscount + shipping;

    let taxAmount = 0;
    if (formData.taxType === 'amount') {
      taxAmount = formData.taxAmount || 0;
    } else {
      taxAmount = taxableBase * ((formData.taxRate || 0) / 100);
    }

    return taxableBase + taxAmount;
  };

  const validateForm = (): boolean => {
    if (!formData.supplierId) {
      alert("يرجى اختيار المورد أولاً");
      return false;
    }

    if (items.length === 0) {
      alert("يرجى إضافة منتجات على الأقل");
      return false;
    }

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
    const statusMap: Record<OperationalStatus, string> = {
      initial: "أولية",
      manufacturing_started: "قيد التصنيع",
      production_completed: "تم التصنيع",
      shipping_preparation: "تجهيز الشحن",
      shipping_in_progress: "جاري الشحن",
      shipped: "تم الشحن",
      cancelled: "ملغاة",
    };
    return statusMap[status] || status;
  };

  const getOperationalStatusStyles = (status: OperationalStatus): string => {
    const styles: Record<OperationalStatus, string> = {
      initial: "bg-gray-100 text-gray-700 border-gray-200",
      manufacturing_started: "bg-blue-50 text-blue-700 border-blue-200",
      production_completed: "bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]",
      shipping_preparation: "bg-amber-50 text-amber-700 border-amber-200",
      shipping_in_progress: "bg-[var(--color-surface-2)] text-[var(--color-primary)] border-[var(--color-border)]",
      shipped: "bg-green-50 text-green-700 border-green-200",
      cancelled: "bg-red-50 text-red-700 border-red-200",
    };
    return styles[status] || styles["initial"];
  };

  const getOperationalStatusIcon = (status: OperationalStatus): React.ReactNode => {
    const icons: Record<OperationalStatus, React.ReactNode> = {
      initial: <FileText className="w-4 h-4" />,
      manufacturing_started: <Factory className="w-4 h-4" />,
      production_completed: <CheckCircle2 className="w-4 h-4" />,
      shipping_preparation: <Package className="w-4 h-4" />,
      shipping_in_progress: <Truck className="w-4 h-4" />,
      shipped: <CheckCircle2 className="w-4 h-4" />,
      cancelled: <AlertCircle className="w-4 h-4" />,
    };
    return icons[status] || <FileText className="w-4 h-4" />;
  };

  const getPaymentStatusFromPayments = (deal: Deal): PaymentStatus => {
    const total = deal.totalAmount || 0;
    const paid = deal.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0;

    if (total === 0) return "not_paid";
    const percentage = (paid / total) * 100;
    const payments = deal.payments || [];

    const paymentsWithClaimOnly = payments.filter(
      (p) => p.alibabaClaimImage && !p.bankSwiftImage && !p.confirmedBySupplier
    );

    const paymentsWithSwiftUnconfirmed = payments.filter(
      (p) => p.bankSwiftImage && !p.confirmedBySupplier
    );

    const confirmedPayments = payments.filter((p) => p.confirmedBySupplier);

    if (paymentsWithClaimOnly.length > 0 && paymentsWithSwiftUnconfirmed.length === 0) {
      return "claim_raised";
    }

    if (paymentsWithSwiftUnconfirmed.length > 0) {
      return "payment_pending_confirmation";
    }

    if (confirmedPayments.length > 0) {
      if (payments.length === confirmedPayments.length) {
        if (percentage === 100) return "paid";
        if (percentage > 0 && percentage < 100) return "partially_paid";
      }
      return "partially_paid";
    }

    if (percentage === 0) return "not_paid";
    if (percentage > 0 && percentage < 100) return "partially_paid";
    if (percentage === 100) return "paid";

    return "not_paid";
  };

  const getPaymentStatusText = (status: PaymentStatus): string => {
    const statusMap: Record<PaymentStatus, string> = {
      not_paid: "غير مدفوعة",
      claim_raised: "تم رفع مطالبة",
      payment_pending_confirmation: "بانتظار تأكيد",
      partially_paid: "مدفوعة جزئياً",
      paid: "مدفوعة كلياً",
    };
    return statusMap[status] || status;
  };

  const getPaymentStatusStyles = (status: PaymentStatus): string => {
    const styles: Record<PaymentStatus, string> = {
      not_paid: "bg-red-50 text-red-700 border-red-200",
      claim_raised: "bg-yellow-50 text-yellow-700 border-yellow-200",
      payment_pending_confirmation: "bg-blue-50 text-blue-700 border-blue-200",
      partially_paid: "bg-amber-50 text-amber-700 border-amber-200",
      paid: "bg-emerald-50 text-emerald-700 border-emerald-200",
    };
    return styles[status] || styles["not_paid"];
  };

  const getPaymentStatusIcon = (status: PaymentStatus): React.ReactNode => {
    const icons: Record<PaymentStatus, React.ReactNode> = {
      not_paid: <AlertCircle className="w-4 h-4" />,
      claim_raised: <AlertTriangle className="w-4 h-4" />,
      payment_pending_confirmation: <Clock className="w-4 h-4" />,
      partially_paid: <DollarSign className="w-4 h-4" />,
      paid: <CheckCircle className="w-4 h-4" />,
    };
    return icons[status] || <AlertCircle className="w-4 h-4" />;
  };

  const getPaymentStatusWithAmounts = (deal: Deal): string => {
    const status = getPaymentStatusFromPayments(deal);
    const total = deal.totalAmount || 0;
    const paid = deal.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0;
    const remaining = total - paid;

    const baseText = getPaymentStatusText(status);
    return baseText;
  };

  // حساب الإحصائيات
  const dealStats = {
    totalAmount: calculateGrandTotal(),
    itemsCount: items.length,
    paidAmount: formData.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0,
    remainingAmount: calculateGrandTotal() - (formData.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0),
    paymentPercentage: calculateGrandTotal() > 0 ? ((formData.payments?.reduce((sum, p) => sum + (p.amount || 0), 0) || 0) / calculateGrandTotal()) * 100 : 0
  };

  return (
    <div
      data-skin="aseel"
      style={{ height: 'calc(100vh - 5rem)', display: 'flex', flexDirection: 'column' }}
    >
    <AseelDocumentShell
      title="صفقة استيراد"
      state={
        formData.id
          ? `صفقة ${formData.dealNumber || `#${formData.id}`}`
          : 'صفقة جديدة'
      }
      nav={nav}
      actions={[
        { key: 'new', label: 'إضافة', icon: <Plus />, onClick: handleNewDeal },
        {
          key: 'save',
          label: saving ? '...تخزين' : 'تخزين',
          icon: <Save />,
          onClick: !saving ? () => void handleFinalSave() : undefined,
          disabled: saving,
        },
        {
          key: 'cancel',
          label: 'إلغاء',
          icon: <X />,
          onClick: onCancel,
          danger: true,
          separatorBefore: true,
        },
        {
          key: 'print',
          label: 'طباعة',
          icon: <Printer />,
          onClick: () => window.print(),
          separatorBefore: true,
        },
      ]}
      header={<></>}
      status={
        <>
          <span className="aseel-status-item">
            المستخدم <b>{currentUser?.name || '—'}</b>
          </span>
          <span className="aseel-status-item">
            السجل <b>{nav.position}/{nav.total}</b>
          </span>
          {formData.dealNumber && (
            <span className="aseel-status-item">
              رقم الصفقة <b>{formData.dealNumber}</b>
            </span>
          )}
          {formData.shippingWorkflowStatus && (
            <span className="aseel-status-item">
              المرحلة <b>{formData.shippingWorkflowStatus}</b>
            </span>
          )}
        </>
      }
    >
    <div className={`bg-gray-50 dark:bg-gray-900 ${compactMode ? 'p-3' : 'p-4 md:p-6'}`} style={{ height: '100%', overflow: 'auto' }}>
      {/* Top Header */}
      <div className={`flex flex-col ${compactMode ? 'gap-3 mb-4' : 'gap-4 mb-6'} sticky top-0 z-20 bg-gray-50/95 dark:bg-gray-900/95 backdrop-blur py-3 border-b border-gray-200 dark:border-gray-800`}>
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
          <div className="flex items-center gap-3">
            <button
              onClick={onCancel}
              className={`${compactMode ? 'p-1.5' : 'p-2'} bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors`}
              title="رجوع"
            >
              <ChevronLeft className="w-4 h-4 rtl:rotate-180" />
            </button>
            <div>
              {/* السطر الأول: رقم الصفقة والعنوان */}
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className={`${compactMode ? 'text-lg' : 'text-xl'} font-bold text-gray-900 dark:text-white flex items-center gap-2`}>
                  <LayoutList className={`${compactMode ? 'text-xs' : 'text-sm'} text-blue-600`} />
                  <span>{formData.dealNumber ? `صفقة #${formData.dealNumber}` : "صفقة جديدة"}</span>
                </h1>
                {/* عرض رقم العرض بشكل أنيق */}
                {formData.originalOfferNumber && (
                  <span className="bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)] text-sm px-2 py-0.5 rounded-full font-medium border border-[var(--color-border)] dark:border-[var(--color-border)] flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    عرض #{formData.originalOfferNumber}
                  </span>
                )}
              </div>

              {/* السطر الثاني: تفاصيل المورد والتاريخ */}
              {/* السطر الثاني: المورد والتاريخ */}
              <div className={`flex flex-wrap items-center gap-3 mt-1 ${compactMode ? 'text-xs' : 'text-sm'} text-gray-500 dark:text-gray-400`}>

                {/* اسم المورد (زر قابل للنقر) */}
                <div className="flex items-center gap-1.5" title="عرض تفاصيل المورد">
                  <Factory className="w-3.5 h-3.5 text-gray-400" />
                  <button
                    onClick={() => formData.supplierId && setViewSupplierId(formData.supplierId)}
                    className="font-medium text-blue-600 dark:text-blue-400 hover:underline hover:text-blue-800 transition-colors text-left"
                    disabled={!formData.supplierId}
                  >
                    {selectedSupplier
                      ? (
                        <>
                          {selectedSupplier.tradeName}
                          {selectedSupplier.alias && (
                            <span className="text-gray-500 dark:text-gray-400 font-normal mr-1">
                              ({selectedSupplier.alias})
                            </span>
                          )}
                        </>
                      )
                      : (formData.factoryName || "يرجى اختيار المورد")
                    }
                  </button>
                </div>

                <span className="text-gray-300 dark:text-gray-600">|</span>

                {/* التاريخ */}
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-gray-400" />
                  <span className="dir-ltr">
                    {formData.dealDate
                      ? new Date(formData.dealDate).toLocaleDateString('ar-EG')
                      : new Date().toLocaleDateString('ar-EG')
                    }
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex gap-2 justify-end ">
            <div className="flex items-center gap-2">
              <div className={`${compactMode ? 'px-2 py-0.5' : 'px-2 py-1'} rounded text-xs font-medium ${getOperationalStatusStyles(getOperationalStatus(formData.status as DealStatus))}`}>
                {getOperationalStatusText(getOperationalStatus(formData.status as DealStatus))}
              </div>
              <div className={`${compactMode ? 'px-2 py-0.5' : 'px-2 py-1'} rounded text-xs font-medium ${getPaymentStatusStyles(getPaymentStatusFromPayments(formData as Deal))}`}>
                {getPaymentStatusWithAmounts(formData as Deal)}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowPrintView(true)}
              className={`${compactMode ? 'px-3 py-1.5 text-sm' : 'px-4 py-2'} bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 flex items-center gap-2 transition-colors`}
            > عرض
            </button>
            <button
              onClick={handleFinalSave}
              disabled={saving || loading}
              className={`${compactMode ? 'px-3 py-1.5 text-sm' : 'px-4 py-2'} bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors`}
            >
              {saving || loading ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  جاري الحفظ...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" /> حفظ
                </>
              )}
            </button>
          </div>
        </div>

        {/* Tabs Navigation */}
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setActiveTab('info')}
            className={`flex-1 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'info'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
          >
            <Info className="inline w-4 h-4 mr-1" />
            المعلومات
          </button>
          <button
            onClick={() => setActiveTab('items')}
            className={`flex-1 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'items'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
          >
            <Package className="inline w-4 h-4 mr-1" />
            المنتجات
          </button>
          <button
            onClick={() => setActiveTab('payments')}
            className={`flex-1 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'payments'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
          >
            <CreditCard className="inline w-4 h-4 mr-1" />
            الدفعات
          </button>
          <button
            onClick={() => setActiveTab('documents')}
            className={`flex-1 py-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'documents'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
          >
            <FileText className="inline w-4 h-4 mr-1" />
            المرفقات
          </button>
        </div>
      </div>

      {/* Quick Stats */}
      <div className={`${compactMode ? 'mb-4' : 'mb-6'}`}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg border border-blue-100 dark:border-blue-800/30">
            <p className="text-xs text-blue-600 dark:text-blue-400 font-medium">القيمة الإجمالية</p>
            <p className="text-lg font-bold text-blue-900 dark:text-blue-300">${dealStats.totalAmount.toLocaleString()}</p>
          </div>
          <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-lg border border-green-100 dark:border-green-800/30">
            <p className="text-xs text-green-600 dark:text-green-400 font-medium">المدفوع</p>
            <p className="text-lg font-bold text-green-900 dark:text-green-300">${dealStats.paidAmount.toLocaleString()}</p>
          </div>
          <div className="bg-slate-50 dark:bg-slate-900/40 p-3 rounded-lg border border-slate-200 dark:border-slate-700">
            <p className="text-xs text-slate-600 dark:text-slate-400 font-medium">المتبقي</p>
            <p className="text-lg font-bold text-slate-900 dark:text-slate-100">${dealStats.remainingAmount.toLocaleString()}</p>
          </div>
          <div className="bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 p-3 rounded-lg border border-[var(--color-border)] dark:border-[var(--color-border)]/30">
            <p className="text-xs text-[var(--color-primary)] dark:text-[var(--color-primary)] font-medium">نسبة الدفع</p>
            <div className="flex items-center justify-between">
              <p className="text-lg font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)]">{dealStats.paymentPercentage.toFixed(1)}%</p>
              <div className="w-16 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all duration-300"
                  style={{ width: `${Math.min(dealStats.paymentPercentage, 100)}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto">
        {activeTab === 'info' && (
          <div className="space-y-4">
            <CollapsibleSection
              title="معلومات الصفقة الأساسية"
              icon={Info}
              defaultOpen={true}
              compact={compactMode}
            >
              <BasicInfoSection
                data={formData}
                setData={setFormData}
                suppliers={suppliers}
                isDeal={true}
                dealsService={dealsService}
                items={items}
              // compact={compactMode}
              />
            </CollapsibleSection>
          </div>
        )}

        {activeTab === 'items' && (
          <div className="space-y-4">
            <CollapsibleSection
              title="المنتجات والأسعار والملخص المالي"
              icon={Package}
              defaultOpen={true}
              compact={compactMode}
            >
              <ItemsTableSection
                items={items}
                onAddItem={() => setShowItemSearch(true)}
                onUpdateItem={handleUpdateItem}
                onRemoveItem={handleRemoveItem}
                onPreviewImage={setPreviewImage}
                supplierId={formData.supplierId}
                allDbItems={allDbItems}
                discountAmount={formData.discountAmount || 0}
                taxRate={formData.taxRate || 0}
                taxAmount={formData.taxAmount || 0}
                taxType={formData.taxType || 'percentage'}
                shippingCost={formData.shippingCost || 0}
                shippingIncluded={formData.shippingIncluded || false}
                payments={formData.payments || []}
                onUpdateFinancial={(field, value) => {
                  const updatedFields = { [field]: value };

                  if (field === 'taxType' || field === 'taxAmount' || field === 'taxRate') {
                    setFormData((prev) => {
                      const updated = { ...prev, ...updatedFields };
                      const itemsSubtotal = items.reduce((sum, item) => sum + (item.totalPrice || 0), 0);
                      const validShipping = updated.shippingIncluded ? 0 : (updated.shippingCost || 0);
                      const afterDiscount = Math.max(0, itemsSubtotal - (updated.discountAmount || 0));
                      const taxableBase = afterDiscount + validShipping;

                      let taxAmount = 0;
                      if (updated.taxType === 'amount') {
                        taxAmount = updated.taxAmount || 0;
                      } else {
                        taxAmount = taxableBase * ((updated.taxRate || 0) / 100);
                      }

                      const grandTotal = taxableBase + taxAmount;

                      return {
                        ...updated,
                        subtotal: itemsSubtotal,
                        taxAmount,
                        totalAmount: grandTotal,
                      };
                    });
                    return;
                  }

                  setFormData((prev) => ({ ...prev, ...updatedFields }));
                  recalculateTotals(items, updatedFields);
                }}
                productionDays={formData.productionDays}
                deliveryDays={formData.deliveryDays}
                paymentMethod={formData.paymentMethod}
                shippingMethod={formData.shippingMethod}
                warrantyDuration={formData.warrantyDuration}
                totalWeight={formData.totalWeight}
                totalVolume={formData.totalVolume}
                certificates={formData.certificates}
                shipmentNotes={formData.shipmentNotes}
                readOnly={false}
                showLocalPayments={false}
              // compact={compactMode}
              />
            </CollapsibleSection>
          </div>
        )}

        {activeTab === 'payments' && (
          <div className="space-y-4">
            <CollapsibleSection
              title="نظام الدفعات"
              icon={CreditCard}
              defaultOpen={true}
              compact={compactMode}
              className="border-blue-200 dark:border-blue-900"
            >
              <div className="space-y-6">
                <InstallmentManager
                  installments={installments}
                  grandTotal={calculateGrandTotal()}
                  onUpdateInstallments={(newInstallments) => {
                    setInstallments(newInstallments);
                    setFormData(prev => ({
                      ...prev,
                      installments: newInstallments
                    }));
                  }}
                  validationError={installmentValidationError}
                  installmentPlanEnabled={installmentPlanEnabled}
                  onTogglePlan={toggleInstallmentPlan}
                  deal={formData}
                  readOnly={formData.status === 'shipped' || formData.status === 'cancelled'}
                // compact={compactMode}
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
                  readOnly={
                    formData.status === "shipped" || formData.status === "cancelled"
                  }
                // compact={compactMode}
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
            </CollapsibleSection>
          </div>
        )}

        {activeTab === 'documents' && (
          <div className="space-y-4">
            <CollapsibleSection
              title="المرفقات والوثائق"
              icon={FileText}
              defaultOpen={true}
              compact={compactMode}
            >
              <AttachmentsSection data={formData}
                setData={setFormData}
              // compact={compactMode}
              />
            </CollapsibleSection>

            {formData.id && activities.length > 0 && (
              <CollapsibleSection
                title="سجل النشاطات"
                icon={Activity}
                defaultOpen={false}
                compact={compactMode}
              >
                <ActivityLog activities={activities}
                // compact={compactMode}
                />
              </CollapsibleSection>
            )}
          </div>
        )}
      </div>

      {/* Modals */}
      <ItemSearchModal
        isOpen={showItemSearch}
        onClose={() => setShowItemSearch(false)}
        onSelectItem={(item, price) => {
          handleAddItemFromModal(item, price);
        }}
        items={allDbItems}
        supplierId={formData.supplierId}
      />
      <ImagePreviewModal
        url={previewImage}
        onClose={() => setPreviewImage(null)}
      />

      {/* Bottom Action Bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 p-3 shadow-lg">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <Package className="w-4 h-4" />
            <span>{items.length} منتج</span>
            <span className="mx-2">•</span>
            <DollarSign className="w-4 h-4" />
            <span>${dealStats.totalAmount.toLocaleString()}</span>
            <span className="mx-2">•</span>
            <Clock className="w-4 h-4" />
            <span>آخر تحديث: {new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onCancel}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              رجوع
            </button>
            <button
              onClick={handleFinalSave}
              disabled={saving || loading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
            >
              {saving || loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  جاري الحفظ...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" /> حفظ الصفقة
                </>
              )}
            </button>
          </div>
        </div>
      </div>
      <SupplierViewModal
        isOpen={!!viewSupplierId}
        supplierId={viewSupplierId}
        onClose={() => setViewSupplierId(null)}
      />
      {/* 🟢 5. عرض صفحة الطباعة عند الضغط على الزر */}
      {showPrintView && (
        <div className="fixed inset-0 z-[100] bg-white overflow-y-auto">
          <DealPrintView
            deal={formData as Deal}
            currentUser={currentUser}
            supplier={selectedSupplier}
            onClose={() => setShowPrintView(false)}
            onEdit={() => setShowPrintView(false)}
          />
        </div>
      )}

    </div>
    </AseelDocumentShell>

      {/* M3-T1: Aseel supplier index picker (opens via +/… or programmatically). */}
      <AseelIndexPicker<Supplier>
        open={showSupplierPicker}
        title="فهرس الموردين"
        rows={suppliers}
        columns={[
          { key: 'id', header: 'الرقم', width: '90px', value: (r) => r.id ?? '' },
          { key: 'name', header: 'الاسم', value: (r) => r.tradeName ?? r.alias ?? '' },
          { key: 'phone', header: 'الهاتف', width: '140px', value: (r) => r.phone ?? r.mobile ?? '—' },
        ]}
        getRowKey={(r) => r.id ?? ''}
        searchValue={(r) => `${r.id ?? ''} ${r.tradeName ?? ''} ${r.alias ?? ''}`}
        onSelect={(r) => {
          setFormData({ ...formData, supplierId: r.id ?? '', supplierName: r.tradeName ?? r.alias ?? '' });
          setShowSupplierPicker(false);
        }}
        onClose={() => setShowSupplierPicker(false)}
      />
    </div>


  );
};