import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Invoice,
  InvoiceItem,
  Supplier,
  User,
  Item,
  DealInvoiceInfo,
  InvoiceInstallment,
  DealActivity,
} from "@/types";
import {
  Save,
  ArrowRight,
  Loader2,
  Pencil,
  Plus,
  Printer,
  RefreshCw,
  Trash2,
  X,
  Send,
  Undo2,
  AlertCircle,
  CheckCircle2,
  Info,
} from "lucide-react";
import { ProductCardModal } from "../../shared/ProductCardModal";
import { AseelDatePicker } from "../../ui/AseelDatePicker";
import {
  suppliersService,
} from "@/services/firestoreService";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { maxPaymentPrincipalForDeal } from "@/utils/dealPaymentLimits";
import { resolvePaymentForSwiftInstallment } from "@/utils/dealPaymentMatch";
import { SupplierModal } from "@/components/common/SupplierModal";
import { mapPurchaseInvoiceDtoToInvoice } from "@/utils/mapPurchaseInvoiceDto";
import { dealsService } from "@/services/dealsService";
import { shipmentsService } from "@/services/shipmentsService";
import {
  invoiceGrandTotalIls,
  invoiceVatBaseIls,
} from "@/utils/invoiceTaxesAndFees";
import { roundSqlMoney2, roundSqlMoney4 } from "@/utils/sqlMoneyRound";
import { formatMoney } from "@/utils/formatNumber";
import { inventoryApi } from "@/services/inventoryApi";
import { openInNewTab } from "@/utils/openInNewTab";
import { ItemSearchModal, productToItem } from "../price-offers/ItemSearchModal";
import { ItemQuickCreateModal } from "../../items/ItemQuickCreateModal";

import { getPartnerBalance, type PartnerBalanceResponse } from "@/services/salesApi";
import {
  InvoiceBasicInfo,
  DealInfoSection,
  InstallmentsSection,
  DealActivityLog,
  ConversionDetailsSection,
  NISItemsTable,
  NISFinancialSummary,
  NISInvoiceTaxStrip,
} from "./sections";
import { ItemsTableSection } from "@/components/forms/shared/ItemsTableSection";
import { AttachmentsSection } from "@/components/forms/shared/AttachmentsSection";
import { PurchaseInvoiceAccountingPanel } from "./PurchaseInvoiceAccountingPanel";
import { InvoicePrintView } from "./InvoicePrintView";
import { DocumentPaymentsTab } from "@/components/shared/DocumentPaymentsTab";
import {
  AseelDocumentShell,
  AseelGrid,
  AseelIndexPicker,
  AseelAutocomplete,
  useRecordNavigation,
  useAseelKeymap,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../../aseel";
import { formatInvoiceImportLogisticsLine } from "@/utils/invoiceConversionUtils";
import { useToast } from "@/contexts/ToastContext";
import { useConfirm } from "@/contexts/ConfirmContext";

interface InvoiceFormProps {
  invoice: Partial<Invoice> | null;
  currentUser: User;
  onCancel: () => void;
  /** يُستدعى بعد حفظ ناجح — يمرَّر معرف الفاتورة في SQL لتحديث الرابط */
  onSave?: (ctx: { id: string }) => void;
  allDbItems: Item[];
  dealData?: any;
  readOnly?: boolean;
}

export const InvoiceForm: React.FC<InvoiceFormProps> = ({
  invoice: initialInvoice,
  currentUser,
  onCancel,
  onSave,
  allDbItems: initialDbItems,
  dealData,
  readOnly = false,
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [formData, setFormData] = useState<Partial<Invoice>>(
    initialInvoice || {}
  );
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [saving, setSaving] = useState(false);
  // M2: ترحيل/تراجع داخل المحرر — توحيداً مع شاشة المبيعات (شريط أدوات واحد).
  const [posting, setPosting] = useState(false);
  const [accMsg, setAccMsg] = useState<string | null>(null);
  const [accErr, setAccErr] = useState<string | null>(null);
  const [activeTabKey, setActiveTabKey] = useState<string>("basic");
  const [recalcBusy, setRecalcBusy] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  
  const [allDbItems, setAllDbItems] = useState<Item[]>(initialDbItems);
  // الأصناف تصل من الأب بشكل غير متزامن (subscribeToItems). useState يلتقط الـ prop
  // عند التركيب فقط، فإن فُتحت الفاتورة قبل اكتمال التحميل بقيت القائمة فارغة («لا
  // يوجد تطابق») حتى إعادة فتحها. هذا التأثير يعتمد آخر قائمة وصلت مع الحفاظ على أي
  // صنف أُنشئ inline، ويتفادى إعادة الرندر إن لم يتغيّر المحتوى فعلاً.
  useEffect(() => {
    setAllDbItems((prev) => {
      const incoming = initialDbItems || [];
      const incomingIds = new Set(incoming.map((i) => String(i.id)));
      const localOnly = prev.filter((p) => !incomingIds.has(String(p.id)));
      const merged = localOnly.length ? [...incoming, ...localOnly] : incoming;
      if (
        merged.length === prev.length &&
        merged.every((m, i) => String(m.id) === String(prev[i]?.id))
      ) {
        return prev; // لا تغيير فعلي — تجنّب إعادة الرندر
      }
      return merged;
    });
  }, [initialDbItems]);
  const [showSupplierPicker, setShowSupplierPicker] = useState(false);
  // DEF-007/008: بطاقة الصنف المشتركة (نقر مفرد على الشجرة / أيقونة (i)).
  const [cardProductId, setCardProductId] = useState<number | null>(null);
  // «موافق» (إضافة للفاتورة) يظهر فقط عند فتح البطاقة من الشجرة، لا من أيقونة (i).
  const [cardCanAdd, setCardCanAdd] = useState(false);
  // T-R2: السعر المقترح (آخر فاتورة شراء) ومصدره — لعرضهما داخل البطاقة.
  const [cardSuggestedPrice, setCardSuggestedPrice] = useState<number | null>(null);
  const [showAddSupplierModal, setShowAddSupplierModal] = useState(false);
  const [showPrintView, setShowPrintView] = useState(false);
  const [showItemSearch, setShowItemSearch] = useState(false);
  const [activeItemSearchIndex, setActiveItemSearchIndex] = useState<number | null>(null);
  // task18 DEF-B1/B3: إنشاء صنف جديد inline من خلية اسم الصنف (النص المكتوب يُمرَّر مسبقاً)
  const [inlineCreate, setInlineCreate] = useState<{ rowIndex: number; name: string } | null>(null);
  // task18 DEF-C1: رصيد المورد (قبل/بعد) عند اختيار مورد — يطابق شاشة المبيعات.
  const [supplierBalance, setSupplierBalance] = useState<PartnerBalanceResponse | null>(null);

  // حارس التغييرات غير المحفوظة (Dirty state tracking)
  const [viewMode, setViewMode] = useState<boolean>(!!initialInvoice?.id);
  const effectiveReadOnly = readOnly || viewMode;
  const dirtyRef = useRef(false);
  const markDirty = () => {
    dirtyRef.current = true;
  };
  useEffect(() => {
    const sid = formData.supplierId;
    if (!sid) {
      setSupplierBalance(null);
      return;
    }
    const t = window.setTimeout(() => {
      getPartnerBalance({ partnerId: sid, proposedTotal: formData.grandTotal ?? 0 })
        .then(setSupplierBalance)
        .catch(() => setSupplierBalance(null));
    }, 400);
    return () => window.clearTimeout(t);
  }, [formData.supplierId, formData.grandTotal]);
  /** بيانات الفاتورة والمورد — تُعرض من رأس الصفحة عند الضغط على «تفاصيل» */
  const [invoiceHeaderDetailsOpen, setInvoiceHeaderDetailsOpen] = useState(false);
  /** وصف الصفقة من SQL عند غيابه في الفاتورة المحمّلة */
  const [fetchedDealDescription, setFetchedDealDescription] = useState("");

  const [dealInfo, setDealInfo] = useState<DealInvoiceInfo>(() => {
    return (
      initialInvoice?.dealInfo ||
      dealData || {
        createdBy: currentUser.id,
        createdAt: new Date().toISOString(),
      }
    );
  });

  const [installments, setInstallments] = useState<InvoiceInstallment[]>(
    initialInvoice?.installments || []
  );

  const [installmentPlanEnabled, setInstallmentPlanEnabled] = useState(
    initialInvoice?.installmentPlanEnabled || false
  );

  const [dealActivities, setDealActivities] = useState<DealActivity[]>(
    initialInvoice?.dealInfo?.activityLog || []
  );

  // M4-T1: Aseel Navigation for invoices
  const [invoicesList, setInvoicesList] = useState<any[]>([]);

  const nav = useRecordNavigation<any>({
    items: invoicesList,
    getId: (inv) => inv.id || '',
    currentId: formData.id || null,
    onSelect: async (id) => {
      if (id === null) {
        setFormData({});
        setDealInfo({ createdBy: currentUser.id, createdAt: new Date().toISOString() });
        setInstallments([]);
        setInstallmentPlanEnabled(false);
      } else {
        try {
          const loaded = await purchaseInvoiceApi.get(Number(id));
          const mapped = mapPurchaseInvoiceDtoToInvoice(loaded);
          setFormData(mapped);
          setDealInfo(mapped.dealInfo || { createdBy: currentUser.id, createdAt: new Date().toISOString() });
          setInstallments(mapped.installments || []);
          setInstallmentPlanEnabled(mapped.installmentPlanEnabled || false);
        } catch (err) {
          // console suppressed
        }
      }
    },
  });

  const guardedCancel = async () => {
    if (!formData.id && !(formData.items || []).some(i => i.itemId) && !formData.supplierId) {
      // Empty draft, no need to warn
      onCancel();
      return;
    }
    if (dirtyRef.current) {
      if (!(await confirm({ message: "لديك تغييرات غير محفوظة. هل أنت متأكد من الخروج دون حفظ؟", confirmText: "خروج دون حفظ", cancelText: "بقاء", danger: false }))) {
        return;
      }
    }
    onCancel();
  };

  const guardedNew = async () => {
    if (!formData.id && !(formData.items || []).some(i => i.itemId) && !formData.supplierId) {
      nav?.goNew?.();
      return;
    }
    if (dirtyRef.current) {
      if (!(await confirm({ message: "لديك تغييرات غير محفوظة. هل أنت متأكد من فتح فاتورة جديدة وتجاهل التغييرات؟", confirmText: "متابعة", cancelText: "إلغاء", danger: false }))) {
        return;
      }
    }
    nav?.goNew?.();
  };

  // M4-T1: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => setShowPrintView(true),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    F12: () => handleSave(),
    Escape: () => {
      if (showSupplierPicker) { setShowSupplierPicker(false); return; }
      guardedCancel();
    },
    plus: () => {
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
    CtrlIns: () => guardedNew(),
  }, { enabled: !showSupplierPicker });

  // Load invoices list for navigation
  useEffect(() => {
    const loadInvoices = async () => {
      try {
        const list = await purchaseInvoiceApi.list();
        setInvoicesList(list);
      } catch (err) {
        // console suppressed
      }
    };
    loadInvoices();
  }, []);

  const effectiveShippingForTotals = (data: Partial<Invoice>) => {
    if (data.currency === "ILS") return 0;
    return data.shippingIncluded ? 0 : data.shippingCost || 0;
  };

  // Load Suppliers
  useEffect(() => {
    const unsubSuppliers = suppliersService.subscribeToSuppliers(setSuppliers);
    return () => unsubSuppliers();
  }, []);

  // Recalculate Totals
  const recalculateTotals = (updatedFields: Partial<Invoice> = {}) => {
    const nextData = { ...formData, ...updatedFields };
    const items = nextData.items || [];

    const itemsSubtotal = items.reduce(
      (sum, item) => sum + (item.totalPrice || 0),
      0
    );
    const validShipping = effectiveShippingForTotals(nextData);
    const afterDiscount = Math.max(
      0,
      itemsSubtotal - (nextData.discountAmount || 0)
    );
    const merchandiseBase = afterDiscount + validShipping;
    const vatBase = invoiceVatBaseIls(
      merchandiseBase,
      nextData.conversionMetadata as Record<string, unknown> | null,
      nextData.localPayments
    );

    let taxAmount = 0;
    if (nextData.taxType === 'amount') {
      taxAmount = nextData.taxAmount || 0;
    } else {
      taxAmount = vatBase * ((nextData.taxRate || 0) / 100);
    }
    const mainVatRounded = roundSqlMoney2(taxAmount);

    const grandTotal = roundSqlMoney2(
      invoiceGrandTotalIls(
        merchandiseBase,
        mainVatRounded,
        nextData.conversionMetadata as Record<string, unknown> | null,
        nextData.localPayments
      )
    );

    setFormData((prev) => ({
      ...prev,
      ...updatedFields,
      subtotal: roundSqlMoney2(itemsSubtotal),
      taxAmount: mainVatRounded,
      grandTotal: roundSqlMoney2(grandTotal),
    }));
  };

  // فاتورة جديدة (بدون id من SQL)
  useEffect(() => {
    if (initialInvoice?.id) return;
    setFormData((prev) => ({
      ...prev,
      items: prev.items && prev.items.length > 0 ? prev.items : [
        {
          id: crypto.randomUUID(),
          itemId: "",
          name: "",
          categoryId: "",
          categoryName: "",
          specifications: "",
          imageUrls: [],
          quantity: 1,
          unitPrice: 0,
          totalPrice: 0,
        }
      ],
      status: "incomplete",
      discountAmount: 0,
      taxRate: 0,
      subtotal: 0,
      grandTotal: 0,
      createdAt: new Date().toISOString(),
      isHistorical: dealData ? true : false,
      dealId: dealData?.id,
      dealNumber: dealData?.dealNumber,
      invoiceName: dealData?.dealDescription || dealData?.internalNotes || "",
      invoiceDate: dealData?.dealDate || new Date().toISOString().split("T")[0],
      dealInfo: dealInfo,
      currency: "ILS",
    }));
  }, [initialInvoice, dealData]);

  // فاتورة محفوظة: عند جلب التفاصيل الكاملة من الـ API (بنود، وصف…) نحدّث النموذج
  useEffect(() => {
    if (!initialInvoice?.id) return;
    setFormData((prev) => ({
      ...prev,
      ...initialInvoice,
      items: initialInvoice.items ?? prev.items ?? [],
    }));
    if (initialInvoice.dealInfo) {
      setDealInfo(initialInvoice.dealInfo);
      setInstallments(initialInvoice.installments || []);
      setInstallmentPlanEnabled(initialInvoice.installmentPlanEnabled || false);
      setDealActivities(initialInvoice.dealInfo.activityLog || []);
    }
    dirtyRef.current = false;
  }, [initialInvoice]);

  // Sync state to formData
  useEffect(() => {
    setFormData((prev) => ({
      ...prev,
      // 🟢 تعديل هام: دمج dealInfo الحالي بدلاً من استبداله بالكامل لمنع مسح التعديلات القادمة من BasicInfo
      dealInfo: {
        ...prev.dealInfo,
        ...dealInfo
      },
      installments: installments,
      installmentPlanEnabled: installmentPlanEnabled,
    }));
  }, [dealInfo, installments, installmentPlanEnabled]);

  const handleSave = async () => {
    if (!formData.supplierId) {
      toast("الرجاء اختيار المورد", "error");
      return;
    }
    if (!formData.items || formData.items.length === 0) {
      toast("الرجاء إضافة صنف واحد على الأقل", "error");
      return;
    }

    setSaving(true);
    try {
      const isNew = !formData.id;
      const now = new Date().toISOString();
      const invoiceId = formData.id || crypto.randomUUID();

      // 🟢 نأخذ الملاحظات من المكان الصحيح دون دمج قسري
      const activeAlibabaLink = formData.alibabaOrderLink || formData.dealInfo?.alibabaOrderLink || "";
      // هنا نعتمد على ما هو موجود في formData.dealInfo.internalNotes كأولوية للملاحظات الداخلية
      const internalNotes = formData.dealInfo?.internalNotes || formData.notes || "";

      const payload: any = {
        ...formData,
        id: invoiceId,
        updatedAt: now,
        dealInfo: {
          ...dealInfo,
          ...(formData.dealInfo),

          alibabaOrderLink: activeAlibabaLink,
          internalNotes: internalNotes, // حفظ الملاحظات الداخلية بشكل منفصل

          shippingCost: formData.shippingCost,
          shippingIncluded: formData.shippingIncluded,
          totalWeight: formData.totalWeight,
          totalVolume: formData.totalVolume,

          updatedAt: now,
          updatedBy: currentUser.id,
        },
        // الملاحظات العامة (root notes) يمكن أن تكون هي نفسها الداخلية
        notes: internalNotes,
        alibabaOrderLink: activeAlibabaLink,
        installments: installmentPlanEnabled ? installments : [],
        installmentPlanEnabled: installmentPlanEnabled,
      };

      const partnerId = Number(String(payload.supplierId || '').trim());
      const sqlBody: Record<string, unknown> = {
        invoice_name: payload.invoiceName || null,
        invoice_date: payload.invoiceDate || null,
        partner: Number.isFinite(partnerId) && partnerId > 0 ? partnerId : undefined,
        deal: payload.dealId ? Number(payload.dealId) : null,
        subtotal: roundSqlMoney2(payload.subtotal ?? 0),
        discount_amount: roundSqlMoney2(payload.discountAmount ?? 0),
        tax_rate: roundSqlMoney4(payload.taxRate ?? 0),
        tax_amount: roundSqlMoney2(payload.taxAmount ?? 0),
        tax_type: payload.taxType || 'percentage',
        shipping_cost: roundSqlMoney2(payload.shippingCost ?? 0),
        shipping_included: payload.shippingIncluded || false,
        grand_total: roundSqlMoney2(payload.grandTotal ?? 0),
        local_payments_json: payload.localPayments || null,
        conversion_metadata_json: payload.conversionMetadata || null,
        currency: payload.currency || 'ILS',
        status: payload.status || 'draft',
        notes: payload.notes || null,
        supplier_invoice_number: payload.supplierInvoiceNumber || null,
        factory_name: payload.factoryName || null,
        items: (payload.items || [])
          .filter((item: any) => item.itemId && item.itemId !== "")
          .map((item: any) => ({
            product: Number(item.itemId) || null,
            name: item.name,
            quantity: roundSqlMoney4(item.quantity ?? 0),
            unit_price: roundSqlMoney4(item.unitPrice ?? 0),
            total_price: roundSqlMoney2(item.totalPrice ?? 0),
            notes: item.notes || null,
            hs_code: item.hsCodePrimary || null,
            landed_unit_price_ils:
              item.landedUnitPriceIls != null && item.landedUnitPriceIls !== ""
                ? roundSqlMoney4(item.landedUnitPriceIls)
                : null,
            landed_line_total_ils:
              item.landedLineTotalIls != null && item.landedLineTotalIls !== ""
                ? roundSqlMoney2(item.landedLineTotalIls)
                : null,
          })),
      };

      let savedSqlId: string;
      if (isNew) {
        if (dealData?.id) {
          sqlBody.deal = Number(dealData.id) || null;
        }
        const created = await purchaseInvoiceApi.create(sqlBody as any);
        savedSqlId = String(created.id);
        setFormData((prev) => ({ ...prev, id: savedSqlId }));
      } else {
        if (formData.isHistorical) {
          toast("لا يمكن تعديل الفواتير المؤرشفة", "error");
          setSaving(false);
          return;
        }
        await purchaseInvoiceApi.update(Number(formData.id), sqlBody as any);
        savedSqlId = String(formData.id);
      }

      const dealIdForWorkflow = formData.dealId || dealData?.id || payload.dealId;
      if (dealIdForWorkflow) {
        try {
          await dealsService.patchShippingWorkflow(String(dealIdForWorkflow), "sw_released");
        } catch {
          /* لا نمنع نجاح حفظ الفاتورة */
        }
        try {
          await shipmentsService.patchLinkedShipmentsRouteForDeal(
            String(dealIdForWorkflow),
            "released"
          );
        } catch {
          /* نفس الأمر — الشحنة قد لا تكون في SQL */
        }
      }
      setAccMsg(null);
      setViewMode(true);
      if (onSave) onSave({ id: savedSqlId });
      toast("تم حفظ الفاتورة بنجاح", "success");
      dirtyRef.current = false;
    } catch (error) {
      // console suppressed
      const msg =
        error instanceof Error && error.message?.trim()
          ? error.message.trim()
          : "حدث خطأ أثناء الحفظ";
      toast(msg, "error");
    } finally {
      setSaving(false);
    }
  };

  /** M2: إعادة تحميل الفاتورة من الخادم بعد ترحيل/تراجع لتحديث الحالة والقيد. */
  const reloadInvoice = async () => {
    if (!formData.id) return;
    try {
      const loaded = await purchaseInvoiceApi.get(Number(formData.id));
      const mapped = mapPurchaseInvoiceDtoToInvoice(loaded);
      setFormData(mapped);
      setDealInfo(mapped.dealInfo || { createdBy: currentUser.id, createdAt: new Date().toISOString() });
    } catch {
      /* تجاهل — الحالة المعروضة ستُحدَّث عند التنقل */
    }
  };

  // M2: ترحيل الفاتورة من شريط الأدوات (موحَّد مع شاشة المبيعات).
  const handlePost = async () => {
    if (!formData.id || posting) return;
    setAccErr(null);
    setAccMsg(null);
    setPosting(true);
    try {
      const res = await purchaseInvoiceApi.postToAccounting(Number(formData.id));
      setAccMsg(res.message || `تم الترحيل — قيد محاسبي #${res.journal_id}`);
      setViewMode(true);
      await reloadInvoice();
      if (onSave) onSave({ id: String(formData.id) });
    } catch (e) {
      setAccErr(e instanceof Error ? e.message : "تعذّر ترحيل الفاتورة");
    } finally {
      setPosting(false);
    }
  };

  // M2: التراجع عن الترحيل — حذف القيود وإرجاع الفاتورة مسودة (Feature 1).
  const handleUnpost = async () => {
    if (!formData.id || posting) return;
    if (!(await confirm({
      message:
        "هذا المستند مرحَّل. سيؤدي التراجع عن الترحيل إلى حذف كل قيود اليومية " +
        "وحركات المخزون الخاصة بهذه الفاتورة وإرجاعها مسودة قابلة للتعديل/الحذف. متابعة؟",
      confirmText: "متابعة",
    }))) return;
    setAccErr(null);
    setAccMsg(null);
    setPosting(true);
    try {
      await purchaseInvoiceApi.unpost(Number(formData.id));
      setAccMsg("تم التراجع عن الترحيل وحذف القيود. الفاتورة الآن مسودة.");
      setViewMode(true);
      await reloadInvoice();
      if (onSave) onSave({ id: String(formData.id) });
    } catch (e) {
      setAccErr(e instanceof Error ? e.message : "تعذّر التراجع عن الترحيل");
    } finally {
      setPosting(false);
    }
  };

  const handleAddItem = () => {
    setShowItemSearch(true);
  };

  /* task13 M5: منطق تعبئة السطر مشترك بين المنتقي المدمج والفهرس الكامل */
  // FEAT-1: السعر المقترح لبند الشراء عبر PriceResolver المشترك في الخادم
  // (آخر/أقل سعر شراء حسب إعدادات الشراء، ثم تكلفة الصنف، ثم فارغ). يحل محل
  // مسار supplier_prices القديم (مصدر حقيقة موازٍ) — الآن من الفواتير المرحَّلة.
  const resolveSuggestedPrice = async (productId: string | number): Promise<number> => {
    const pid = Number(productId);
    if (!pid) return 0;
    try {
      const r = await purchaseInvoiceApi.resolvePrice({ product: pid });
      return r.unit_price != null ? Number(r.unit_price) || 0 : 0;
    } catch (err) {
      console.error("resolvePrice failed", err);
      return 0;
    }
  };

  const applyItemAt = async (index: number | null, item: Item, lastPrice?: number, qtyOverride?: number) => {
    // task18 DEF-C3: إن كان الصنف موجوداً في سطر آخر — نبّه المستخدم ودعه يختار:
    // موافق = دمج الكمية في السطر القائم · إلغاء = إضافته كسطر مستقل (سعر مختلف).
    const current = formData.items || [];
    const dupIndex = current.findIndex(
      (r, i) => i !== index && String(r.itemId) === String(item.id) && r.itemId !== ""
    );
    if (dupIndex >= 0) {
      const merge = await confirm({
        message: `الصنف «${item.name}» مضاف مسبقاً في الفاتورة. اختر الإجراء:`,
        confirmText: "دمج الكمية",
        cancelText: "سطر جديد مستقل",
        danger: false,
      });
      if (merge) {
        const updated = [...current];
        const existing = { ...updated[dupIndex] };
        existing.quantity = (Number(existing.quantity) || 0) + 1;
        existing.totalPrice = roundSqlMoney2((Number(existing.quantity) || 0) * (Number(existing.unitPrice) || 0));
        updated[dupIndex] = existing;
        // أفرغ السطر الذي كان قيد التحرير (لتفادي تكراره) ما لم يكن سطر الإدخال الفارغ.
        if (index !== null && index < updated.length && index !== dupIndex) {
          updated[index] = {
            id: updated[index].id,
            itemId: "", name: "", categoryId: "", categoryName: "",
            specifications: "", imageUrls: [], quantity: 1, unitPrice: 0, totalPrice: 0,
          };
        }
        recalculateTotals({ items: updated });
        return;
      }
      // إلغاء الدمج → نتابع بالمسار العادي فيُملأ السطر الجاري كصنف مستقل
      // (سطر مكرّر بسعره الخاص — وهو المطلوب).
    }
    // FEAT-1 edit-protection: السعر اليدوي يُحفظ فقط عند **إعادة اختيار نفس الصنف**
    // على السطر. اختيار صنف *مختلف* يُعاد تسعيره دائماً بسعر الصنف الجديد — وإلا
    // يرث الصنف الجديد سعر الصنف القديم.
    const currentRow =
      index !== null && index < (formData.items || []).length
        ? (formData.items || [])[index]
        : undefined;
    const existingPrice = Number(currentRow?.unitPrice) || 0;
    const sameProduct = currentRow != null && String(currentRow.itemId) === String(item.id);
    // T-R2: الكمية المُدخلة من بطاقة الصنف (إن وُجدت) وإلا 1.
    const qty = qtyOverride && qtyOverride > 0 ? qtyOverride : 1;
    const resolvedPrice = sameProduct && existingPrice > 0 ? existingPrice : (lastPrice || 0);
    const newItem: InvoiceItem = {
      id: crypto.randomUUID(),
      itemId: item.id,
      name: item.name,
      categoryId: item.categoryId,
      categoryName: item.categoryName,
      specifications: item.specifications || "",
      imageUrls: item.imageUrls,
      hsCodePrimary: item.hsCodePrimary,
      quantity: qty,
      unitPrice: roundSqlMoney4(resolvedPrice),
      totalPrice: roundSqlMoney2(qty * resolvedPrice),
    };

    let updatedItems = [...(formData.items || [])];
    if (index !== null && index < updatedItems.length) {
      newItem.id = updatedItems[index].id;
      updatedItems[index] = newItem;
    } else {
      updatedItems.push(newItem);
    }

    // ملاحظة: لا نُضيف سطراً فارغاً تلقائياً عند اختيار صنف (طلب المالك) — يُضاف
    // السطر يدوياً بزر «أضف صف» أو من الشجرة. كان السلوك السابق يفتح سطراً بنفسه.
    recalculateTotals({ items: updatedItems });
    markDirty();
  };

  const handleItemSelect = (item: Item, lastPrice?: number) => {
    applyItemAt(activeItemSearchIndex, item, lastPrice);
    setShowItemSearch(false);
    setActiveItemSearchIndex(null);
  };

  const handleUpdateItem = (index: number, field: string, value: any) => {
    const newItems = [...(formData.items || [])];
    newItems[index] = { ...newItems[index], [field]: value };

    if (field === "quantity" || field === "unitPrice") {
      const qty = newItems[index].quantity || 0;
      const price = newItems[index].unitPrice || 0;
      newItems[index].totalPrice = roundSqlMoney2(qty * price);
    }

    recalculateTotals({ items: newItems });
    markDirty();
  };

  const handleRemoveItem = (index: number) => {
    const updatedItems = (formData.items || []).filter((_, i) => i !== index);
    recalculateTotals({ items: updatedItems });
    markDirty();
  };

  const handleUpdateFinancial = (field: string, value: any) => {
    if (field === 'taxType' || field === 'taxAmount' || field === 'taxRate') {
      setFormData((prev) => {
        const updated = { ...prev, [field]: value };
        const items = updated.items || [];
        const itemsSubtotal = items.reduce((sum, item) => sum + (item.totalPrice || 0), 0);
        const validShipping = effectiveShippingForTotals(updated);
        const afterDiscount = Math.max(0, itemsSubtotal - (updated.discountAmount || 0));
        const merchandiseBase = afterDiscount + validShipping;
        const vatBase = invoiceVatBaseIls(
          merchandiseBase,
          updated.conversionMetadata as Record<string, unknown> | null,
          updated.localPayments
        );

        let taxAmount = 0;
        if (updated.taxType === 'amount') {
          taxAmount = updated.taxAmount || 0;
        } else {
          taxAmount = vatBase * ((updated.taxRate || 0) / 100);
        }
        const mainVatRounded = roundSqlMoney2(taxAmount);

        const grandTotal = roundSqlMoney2(
          invoiceGrandTotalIls(
            merchandiseBase,
            mainVatRounded,
            updated.conversionMetadata as Record<string, unknown> | null,
            updated.localPayments
          )
        );
        return {
          ...updated,
          subtotal: roundSqlMoney2(itemsSubtotal),
          taxAmount: mainVatRounded,
          grandTotal: roundSqlMoney2(grandTotal),
        };
      });
      markDirty();
      return;
    }
    recalculateTotals({ [field]: value });
    markDirty();
  };

  const handleDealInfoUpdate = (field: string, value: any) => {
    setDealInfo((prev) => ({ ...prev, [field]: value }));
    markDirty();
  };

  const handleAddInstallment = () => {
    const newInstallmentNumber = installments.length + 1;
    const newInstallment: InvoiceInstallment = {
      id: crypto.randomUUID(),
      installmentNumber: newInstallmentNumber,
      amount: 0,
      status: "unpaid",
      notes: "",
    };
    setInstallments([...installments, newInstallment]);
    markDirty();
  };

  const handleRemoveInstallment = (index: number) => {
    const updatedInstallments = installments.filter((_, i) => i !== index);
    const renumberedInstallments = updatedInstallments.map(
      (installment, idx) => ({ ...installment, installmentNumber: idx + 1 })
    );
    setInstallments(renumberedInstallments);
    markDirty();
  };

  const handleUpdateInstallment = (index: number, field: string, value: any) => {
    const updatedInstallments = [...installments];
    updatedInstallments[index] = { ...updatedInstallments[index], [field]: value };
    setInstallments(updatedInstallments);
    markDirty();
  };

  const handleToggleInstallmentPlan = (enabled: boolean) => {
    setInstallmentPlanEnabled(enabled);
    if (!enabled) {
      setInstallments([]);
    } else {
      handleAddInstallment();
    }
    markDirty();
  };

  const handleRecalculateLanded = async () => {
    if (!formData.shipment || !formData.id) {
      toast("لا توجد شحنة مرتبطة أو الفاتورة غير محفوظة بعد.", "error");
      return;
    }
    const meta = formData.conversionMetadata as Record<string, unknown> | undefined;
    const dr = Number(
      meta?.["remaining_balance_rate_deal"] ??
        meta?.["remainingBalanceRate"] ??
        3.6
    );
    const sr = Number(
      meta?.["remaining_balance_rate_shipment"] ??
        meta?.["shipmentRemainingRate"] ??
        meta?.["remainingBalanceRate"] ??
        3.6
    );
    const basis = String(
      meta?.["clearance_cost_basis"] ?? meta?.["clearanceCostBasis"] ?? ""
    ).toLowerCase();
    const useCl = basis === "cost_lines";
    setRecalcBusy(true);
    try {
      const res = await purchaseInvoiceApi.recalculateLandedCost({
        shipment_id: Number(formData.shipment),
        deal_remaining_rate: dr,
        shipment_remaining_rate: sr,
        use_cost_lines: useCl,
      });
      const full = await purchaseInvoiceApi.get(Number(formData.id));
      setFormData(mapPurchaseInvoiceDtoToInvoice(full));
      const msg =
        typeof res?.message === "string" && res.message.trim()
          ? res.message
          : res?.updated
            ? "تم إعادة حساب تكلفة الرسوم والبنود من الخادم."
            : "لم تُحدَّث الفاتورة من الخادم.";
      toast(msg, res?.updated ? "success" : "info");
    } catch (e) {
      // console suppressed
      toast(e instanceof Error ? e.message : "تعذّر إعادة الحساب", "error");
    } finally {
      setRecalcBusy(false);
    }
  };

  /** أساس البضاعة + شحن الفاتورة (لنسب «البضاعة» في بنود الرسوم الإضافية) */
  const ilsMerchandiseBase = useMemo(() => {
    const items = formData.items || [];
    const itemsSubtotal = items.reduce((s, i) => s + (Number(i.totalPrice) || 0), 0);
    const validShipping = effectiveShippingForTotals(formData);
    return Math.max(0, itemsSubtotal - (formData.discountAmount || 0)) + validShipping;
  }, [
    formData.items,
    formData.discountAmount,
    formData.currency,
    formData.shippingIncluded,
    formData.shippingCost,
  ]);

  /** أساس ض.ق.م: بضاعة + شحن دولي + تخليص + نقل محلي (كل ما قبل ض.ق.م الفاتورة) */
  const ilsVatBase = useMemo(
    () =>
      invoiceVatBaseIls(
        ilsMerchandiseBase,
        formData.conversionMetadata as Record<string, unknown> | null,
        formData.localPayments
      ),
    [ilsMerchandiseBase, formData.conversionMetadata, formData.localPayments]
  );

  /** وصف الصفقة (عربي) — من صفقة مفتوحة أو من حقل اسم/وصف الفاتورة أو جلب من الصفقة */
  const headerDealDescription = useMemo(() => {
    const fromDeal = String(dealData?.dealDescription ?? "").trim();
    const fromInvoice = String(formData.invoiceName ?? "").trim();
    const fromFetched = String(fetchedDealDescription ?? "").trim();
    return fromDeal || fromInvoice || fromFetched;
  }, [dealData?.dealDescription, formData.invoiceName, fetchedDealDescription]);

  useEffect(() => {
    const fromDeal = String(dealData?.dealDescription ?? "").trim();
    const fromInv = String(formData.invoiceName ?? "").trim();
    const did = formData.dealId;
    if (!did || fromDeal || fromInv) {
      setFetchedDealDescription("");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const d = await dealsService.getDeal(String(did));
        if (!cancelled) {
          setFetchedDealDescription(String(d?.dealDescription ?? "").trim());
        }
      } catch {
        if (!cancelled) setFetchedDealDescription("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [formData.dealId, formData.invoiceName, dealData?.dealDescription]);

  /** اسم المورد للعرض في الرأس */
  const headerSupplierName = useMemo(() => {
    const sid = formData.supplierId;
    const fromList = sid
      ? suppliers.find((s) => s.id === sid)?.tradeName
      : undefined;
    return (
      String(fromList ?? "").trim() ||
      String(formData.factoryName ?? "").trim() ||
      String(formData.supplierSnapshot?.tradeName ?? "").trim() ||
      String(formData.dealInfo?.supplierSnapshot?.tradeName ?? "").trim()
    );
  }, [
    formData.supplierId,
    formData.factoryName,
    formData.supplierSnapshot,
    formData.dealInfo?.supplierSnapshot,
    suppliers,
  ]);

  /** فواتير شيكل بنسبة: مزامنة taxAmount/grandTotal مع الأساس (غالباً كانت tax_amount=0 في DB) */
  useEffect(() => {
    if (effectiveReadOnly) return;
    if (formData.currency !== "ILS") return;
    if (formData.taxType === "amount") return;
    if (!(formData.items || []).length) return;
    recalculateTotals({});
  }, [
    readOnly,
    formData.isHistorical,
    formData.currency,
    formData.taxType,
    formData.items,
    formData.discountAmount,
    formData.shippingCost,
    formData.shippingIncluded,
    formData.conversionMetadata,
    formData.localPayments,
    formData.taxRate,
    ilsMerchandiseBase,
  ]);

  // G1: عرض موحّد بلا أصفار عشرية زائدة (مع فاصل آلاف للمبالغ).
  const fmt = (v: number) => formatMoney(v);

  const fld = (label: string, node: React.ReactNode) => (
    <label className="aseel-field">
      <span className="aseel-field-label">{label}</span>
      {node}
    </label>
  );

  const selectedSupplier = formData.supplierId
    ? suppliers.find((s) => s.id === formData.supplierId)
    : undefined;

  /* ───────────── تنبيه أثر السعر على متوسط تكلفة المنتج ───────────── */
  // عند إدخال سعر سيغيّر متوسط تكلفة المنتج (المرجّح بالكمية)، نعرض تنبيهاً فورياً
  // مع رابط لواجهة «تكلفة المنتجات» والمنتج محدد افتراضياً.
  interface CostWarning { productId: number; name: string; from: number; to: number }
  const [costWarnings, setCostWarnings] = useState<Record<string, CostWarning>>({});
  // تخزين مؤقّت لتكلفة كل منتج (متوسط مرجّح + إجمالي الكمية المشتراة) لتفادي طلب لكل ضغطة.
  const costCacheRef = useRef<Record<number, { avg: number; qty: number }>>({});

  const evaluateCostImpact = async (rowId: string, item: InvoiceItem) => {
    const pid = Number(item.itemId);
    const price = Number(item.unitPrice) || 0;
    const lineQty = Number(item.quantity) || 0;
    if (!pid || price <= 0 || lineQty <= 0) {
      setCostWarnings((w) => { if (!w[rowId]) return w; const n = { ...w }; delete n[rowId]; return n; });
      return;
    }
    let base = costCacheRef.current[pid];
    if (!base) {
      try {
        const b = await inventoryApi.getProductCostBreakdown(pid);
        base = { avg: Number(b.average_cost) || 0, qty: Number(b.total_purchased_qty) || 0 };
        costCacheRef.current[pid] = base;
      } catch {
        return; // تعذّر التحميل — لا تُظهر تنبيهاً مضلّلاً
      }
    }
    // متوسط مرجّح متوقّع لو أُضيف هذا السطر: Σ(تكلفة) + سعر×كمية ÷ Σ(كمية) + كمية.
    const newQty = base.qty + lineQty;
    const newAvg = newQty > 0 ? (base.avg * base.qty + price * lineQty) / newQty : price;
    // لا تكلفة سابقة (منتج جديد) → لا متوسط ليتغيّر؛ تغيّر ضئيل (<0.01) يُتجاهل.
    if (base.avg > 0 && Math.abs(newAvg - base.avg) >= 0.01) {
      setCostWarnings((w) => ({ ...w, [rowId]: { productId: pid, name: item.name, from: base.avg, to: newAvg } }));
    } else {
      setCostWarnings((w) => { if (!w[rowId]) return w; const n = { ...w }; delete n[rowId]; return n; });
    }
  };

  /* ───────────── أعمدة جدول البنود (AseelGrid) ───────────── */
  const itemColumns: AseelGridColumn<InvoiceItem>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "itemId", header: "رقم الصنف", width: "100px" },
    { key: "name", header: "اسم الصنف", width: "25%" },
    { 
      key: "specifications", 
      header: "بيان", 
      width: "1%",
      render: (r, ri) => (
        <input
          id={`aseel-grid-input-${ri}-specifications`}
          data-aseel-key="1"
          size={Math.max(4, (r.specifications || "").length)}
          style={{
            minWidth: "45px",
            width: "max-content",
            fieldSizing: "content",
            border: "1px solid transparent",
            background: "transparent",
            padding: "0 3px",
            font: "inherit",
            height: "20px",
            outline: "none"
          }}
          value={r.specifications == null ? "" : String(r.specifications)}
          onChange={(e) => handleUpdateItem(ri, "specifications", e.target.value)}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = "var(--aseel-accent)";
            e.currentTarget.style.background = "var(--aseel-field-focus)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = "transparent";
            e.currentTarget.style.background = "transparent";
          }}
        />
      )
    },
    { key: "quantity", header: "الكمية", width: "80px", align: "center", type: "number" },
    { key: "unitPrice", header: "سعر الوحدة", width: "100px", align: "center", type: "number" },
    { key: "totalPrice", header: "الإجمالي", width: "100px", align: "center", readOnly: true },
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const itemGetCell = (row: InvoiceItem, key: string): string | number => {
    const idx = (formData.items || []).indexOf(row);
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
    const items = [...(formData.items || [])];
    const item = { ...items[rowIndex] };
    if (key === "quantity") {
      item.quantity = Number(value) || 0;
      item.totalPrice = roundSqlMoney2(item.quantity * (item.unitPrice || 0));
    } else if (key === "unitPrice") {
      item.unitPrice = Number(value) || 0;
      item.totalPrice = roundSqlMoney2((item.quantity || 0) * item.unitPrice);
    }
    items[rowIndex] = item;

    // تنبيه أثر السعر على متوسط تكلفة المنتج (فوري أثناء كتابة السعر/الكمية).
    if (key === "unitPrice" || key === "quantity") {
      void evaluateCostImpact(item.id, item);
    }

    // Auto-expanding line item grid logic when last row is edited
    const lastRow = items[items.length - 1];
    if (rowIndex === items.length - 1 && lastRow.itemId) {
      items.push({
        id: crypto.randomUUID(),
        itemId: "",
        name: "",
        categoryId: "",
        categoryName: "",
        specifications: "",
        imageUrls: [],
        quantity: 1,
        unitPrice: 0,
        totalPrice: 0,
      });
    }

    recalculateTotals({ items });
  };

  const addRow = () => {
    const newItem: InvoiceItem = {
      id: crypto.randomUUID(),
      itemId: "",
      name: "",
      categoryId: "",
      categoryName: "",
      specifications: "",
      imageUrls: [],
      quantity: 1,
      unitPrice: 0,
      totalPrice: 0,
    };
    recalculateTotals({ items: [...(formData.items || []), newItem] });
    markDirty();
  };

  const removeRow = (key: string) => {
    const updated = (formData.items || []).filter((i) => i.id !== key);
    recalculateTotals({ items: updated });
    markDirty();
  };

  const renderItemIdCell = (row: InvoiceItem, rowIndex: number) => (
    <button
      type="button"
      className="aseel-cell-picker"
      disabled={effectiveReadOnly}
      data-aseel-key="1"
      onClick={() => {
        setActiveItemSearchIndex(rowIndex);
        setShowItemSearch(true);
      }}
      title="فهرس الأصناف الكامل (+)"
    >
      {row.itemId ? `#${row.itemId}` : "…"}
    </button>
  );

  /* task24: خريطة سعر الشراء المقترح (آخر/أقل شراء أو متوسط التكلفة) لكامل
     الكتالوج — تُجلب دفعة واحدة لعرض السعر داخل خيارات المنتقي بلا نقر. */
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
      .catch(() => { /* بلا تاريخ شراء — تُعرض الخيارات بلا سعر */ });
    return () => { cancelled = true; };
  }, []);

  /* task13 M5: منتقي مدمج في خلية اسم الصنف (يحل محل المودال كمسار أساسي) */
  const itemOptions = useMemo(
    () => allDbItems.map((it) => {
      const pp = purchasePriceMap.get(Number(it.id));
      return {
        id: it.id,
        label: it.name,
        price: pp ? formatMoney(Number(pp.price)) : undefined,
        // لا آخر/أقل شراء ولا متوسط تكلفة → نص «بدون سعر» بدل الفراغ.
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

  const renderItemNameCell = (row: InvoiceItem, rowIndex: number) => {
    const selectedId = row.itemId ? Number(row.itemId) : null;
    return (
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <AseelAutocomplete
        value={row.name || ""}
        options={itemOptions}
        disabled={effectiveReadOnly}
        placeholder="اكتب اسم الصنف…"
        onPick={async (id) => {
          const it = allDbItems.find((x) => String(x.id) === String(id));
          if (it) {
            const lastPrice = await resolveSuggestedPrice(it.id);
            applyItemAt(rowIndex, it, lastPrice);
            setTimeout(() => {
              document.getElementById(`aseel-grid-input-${rowIndex}-quantity`)?.focus();
            }, 50);
          }
        }}
        onInfo={(id) => { const pid = Number(id); if (pid) { setCardCanAdd(false); setCardProductId(pid); } }}
        onFreeText={(t) => {
          // task18 DEF-B1/B3: «إضافة كصنف جديد» يفتح إنشاء صنف سريع مُعبّأً بالنص
          // ويُنشئه فعلياً (Product) بدل ترك سطر حر بلا itemId يُحذف عند الحفظ.
          setInlineCreate({ rowIndex, name: t.trim() });
        }}
      />
      {/* DEF-008: أيقونة (i) بجانب المنتج المختار → بطاقة الصنف */}
      {selectedId != null && (
        <button
          type="button"
          className="aseel-ellipsis"
          onClick={() => { setCardCanAdd(false); setCardProductId(selectedId); }}
          title="بطاقة الصنف"
        ><Info className="w-3.5 h-3.5" /></button>
      )}
    </div>
    );
  };

  const renderDeleteCell = (row: InvoiceItem) =>
    effectiveReadOnly ? null : (
      <button
        type="button"
        className="aseel-iconbtn aseel-iconbtn--danger"
        onClick={() => removeRow(row.id)}
        title="حذف السطر"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    );

  itemColumns[1].render = renderItemIdCell;
  itemColumns[2].render = renderItemNameCell;
  itemColumns[7].render = renderDeleteCell;

  /* ───────────── تبويبات ───────────── */
  const notesTab = (
    <textarea
      className="aseel-input"
      rows={3}
      style={{ width: "100%" }}
      disabled={effectiveReadOnly}
      value={formData.notes || formData.dealInfo?.internalNotes || ""}
      onChange={(e) => handleDealInfoUpdate("internalNotes", e.target.value)}
    />
  );

  const attachmentsTab = (
    <div className="aseel-legacy-tab">
      <AttachmentsSection data={formData} setData={(val) => { setFormData(val); markDirty(); }} />
    </div>
  );

  const basicInfoTab = (
    <div className="aseel-legacy-tab">
      {supplierBalance && (
        <div
          className="aseel-banner"
          style={{ marginBottom: "8px", display: "flex", gap: "18px", flexWrap: "wrap", fontSize: "13px" }}
        >
          {/* task18 DEF-C1: رصيد المورد قبل/بعد هذه الفاتورة (من الـ subledger). */}
          <span>رصيد المورد قبل الفاتورة: <strong>{formatMoney(supplierBalance.open_balance)}</strong></span>
          <span>الرصيد المتوقع بعدها: <strong>{formatMoney(supplierBalance.projected_balance)}</strong></span>
        </div>
      )}
      <InvoiceBasicInfo
        data={formData}
        setData={(val) => { setFormData(val); markDirty(); }}
        suppliers={suppliers}
        readOnly={effectiveReadOnly}
        items={formData.items}
        onOpenAddSupplier={() => setShowAddSupplierModal(true)}
      />
    </div>
  );

  const itemsTab = (
    <div className="aseel-legacy-tab">
      {formData.currency === "ILS" ? (
        <>
          {(formData.conversionMetadata || formData.importLogistics) && (
            <ConversionDetailsSection
              metadata={formData.conversionMetadata}
              importLogistics={formData.importLogistics}
              shippingIncluded={Boolean(formData.shippingIncluded)}
              invoiceShippingCostIls={formData.shippingCost}
              invoiceClearanceId={formData.clearanceId}
            />
          )}
          <NISItemsTable
            items={formData.items || []}
            conversionRate={formData.conversionMetadata?.dealEffectiveRate || 1}
            invoiceTaxAmount={formData.taxAmount || 0}
            localPayments={formData.localPayments || {}}
            taxableBaseIls={ilsMerchandiseBase}
            invoiceVatBaseIls={ilsVatBase}
            conversionMetadata={formData.conversionMetadata}
          />
          <NISInvoiceTaxStrip
            taxType={formData.taxType || "percentage"}
            taxRate={formData.taxRate || 0}
            taxAmount={formData.taxAmount || 0}
            localPayments={formData.localPayments || {}}
            taxableBaseIls={ilsMerchandiseBase}
            vatBaseIls={ilsVatBase}
            readOnly={effectiveReadOnly}
            onFinancial={handleUpdateFinancial}
          />
          <NISFinancialSummary
            subtotal={formData.subtotal || 0}
            discountAmount={formData.discountAmount || 0}
            taxAmount={formData.taxAmount || 0}
            taxRate={formData.taxRate || 0}
            shippingCost={0}
            grandTotal={formData.grandTotal || 0}
            localPayments={formData.localPayments || {}}
            taxableBaseIls={ilsMerchandiseBase}
            invoiceVatBaseIls={ilsVatBase}
            hideShippingRow
          />
        </>
      ) : (
        <ItemsTableSection
          items={formData.items || []}
          onAddItem={handleAddItem}
          onUpdateItem={handleUpdateItem}
          onRemoveItem={handleRemoveItem}
          onPreviewImage={setPreviewImage}
          supplierId={formData.supplierId}
          readOnly={effectiveReadOnly}
          allDbItems={allDbItems}
          discountAmount={formData.discountAmount}
          taxRate={formData.taxRate || 0}
          taxAmount={formData.taxAmount || 0}
          taxType={formData.taxType || "percentage"}
          shippingCost={formData.shippingCost || 0}
          shippingIncluded={formData.shippingIncluded || false}
          localPayments={formData.localPayments || {}}
          productionDays={formData.dealInfo?.productionDays}
          deliveryDays={formData.dealInfo?.deliveryDays}
          paymentMethod={formData.dealInfo?.paymentMethod}
          shippingMethod={formData.dealInfo?.shippingMethod}
          warrantyDuration={formData.dealInfo?.warrantyDuration}
          totalWeight={formData.totalWeight}
          totalVolume={formData.totalVolume}
          certificates={formData.dealInfo?.certificates}
          shipmentNotes={formData.dealInfo?.shipmentNotes || ""}
          onUpdateFinancial={(field: string, value: any) => {
            const dealInfoFields = [
              "productionDays", "deliveryDays", "paymentMethod",
              "shippingMethod", "warrantyDuration", "certificates",
              "shipmentNotes",
            ];
            const weightVolumeFields = ["totalWeight", "totalVolume"];
            if (dealInfoFields.includes(field)) {
              handleDealInfoUpdate(field, value);
            } else if (weightVolumeFields.includes(field)) {
              handleDealInfoUpdate(field, value);
              handleUpdateFinancial(field, value);
            } else {
              handleUpdateFinancial(field, value);
            }
          }}
          currency={formData.currency}
        />
      )}
    </div>
  );

  const installmentsTab = (
    <div className="aseel-legacy-tab">
      <InstallmentsSection
        installments={installments}
        installmentPlanEnabled={installmentPlanEnabled}
        items={formData.items || []}
        discountAmount={formData.discountAmount}
        taxRate={formData.taxRate}
        shippingCost={formData.shippingCost || 0}
        shippingIncluded={formData.shippingIncluded || false}
        localPayments={formData.localPayments || {}}
        onToggleInstallmentPlan={(e) => { handleToggleInstallmentPlan(e); markDirty(); }}
        onAddInstallment={() => { handleAddInstallment(); markDirty(); }}
        onRemoveInstallment={(i) => { handleRemoveInstallment(i); markDirty(); }}
        onUpdateInstallment={(i, f, v) => { handleUpdateInstallment(i, f, v); markDirty(); }}
        readOnly={formData.isHistorical || false}
        currency={formData.currency}
        grandTotalFromForm={formData.currency === "ILS" ? formData.grandTotal : undefined}
        mainVatForExtras={formData.taxAmount || 0}
        conversionMetadata={formData.conversionMetadata}
      />
    </div>
  );

  const dealInfoTab = (
    <div className="aseel-legacy-tab">
      <DealInfoSection
        dealInfo={dealInfo}
        formData={formData}
        onUpdateDealInfo={(f, v) => { handleDealInfoUpdate(f, v); markDirty(); }}
      />
    </div>
  );

  const activityTab = (
    <div className="aseel-legacy-tab">
      {dealActivities.length > 0 ? (
        <DealActivityLog activities={dealActivities} />
      ) : (
        <p className="aseel-hint">لا يوجد سجل نشاطات للصفقة المرتبطة.</p>
      )}
    </div>
  );

  const otherTab = (
    <div className="aseel-other">
      <label className="aseel-field aseel-field--inline">
        <input
          type="checkbox"
          disabled={effectiveReadOnly}
          checked={formData.shippingIncluded || false}
          onChange={(e) => { handleUpdateFinancial("shippingIncluded", e.target.checked); markDirty(); }}
        />
        <span className="aseel-field-label" style={{ flex: "unset" }}>
          الأسعار تشمل الشحن
        </span>
      </label>
      <p className="aseel-hint">
        عملة الفاتورة: {formData.currency === "ILS" ? "شيكل (₪)" : "دولار ($)"}
        {formData.dealId ? ` — مرتبطة بالصفقة ${formData.dealNumber || formData.dealId}` : ""}
      </p>
    </div>
  );

  const isPosted = Boolean(formData.isPosted);
  const canPost = Boolean(formData.id) && !isPosted && !formData.isHistorical;

  const toolbarActions: AseelToolbarAction[] = [
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)", icon: saving ? <Loader2 className="animate-spin" /> : <Save />, onClick: !saving && !isPosted ? () => { handleSave(); dirtyRef.current = false; } : undefined, disabled: saving || isPosted },
    ...(viewMode && !isPosted && !formData.isHistorical ? [{ key: "edit", label: "تحرير", icon: <Pencil />, onClick: () => setViewMode(false), separatorBefore: true } as AseelToolbarAction] : []),
    { key: "new", label: "جديدة", icon: <Plus />, onClick: guardedNew, separatorBefore: true },
    {
      key: "post",
      label: posting ? "...ترحيل" : "ترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Send />,
      onClick: canPost && !posting ? () => void handlePost() : undefined,
      disabled: !canPost || posting,
      separatorBefore: true,
    },
    {
      key: "unpost",
      label: posting ? "...تراجع" : "تراجع عن الترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Undo2 />,
      onClick: isPosted && !posting ? () => void handleUnpost() : undefined,
      disabled: !isPosted || posting,
    },
    { key: "print", label: "طباعة (F2)", icon: <Printer />, onClick: () => setShowPrintView(true), separatorBefore: true },
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: guardedCancel, danger: true, separatorBefore: true },
  ];

  const accBanner = (accErr || accMsg) ? (
    <div className={`aseel-banner ${accErr ? "aseel-banner--err" : "aseel-banner--ok"}`}>
      {accErr ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{accErr || accMsg}</span>
    </div>
  ) : null;

  return (
    <div
      id="purchase-invoice-print"
      dir="rtl"
    >
    <AseelDocumentShell
      title="فاتورة الشراء"
      state={formData.id ? `فاتورة ${formData.invoiceNumber || `#${formData.id}`}` : "فاتورة جديدة"}
      company={
        formData.glPurchaseReceiptJournalId != null ? `قيد محاسبي #${formData.glPurchaseReceiptJournalId}` : undefined
      }
      nav={nav}
      actions={toolbarActions}

      header={
        <>
          {fld(
            "رقم الفاتورة",
            <input
              className="aseel-input"
              readOnly
              value={formData.id ? `#${formData.invoiceNumber || formData.id}` : "— جديدة —"}
            />
          )}
          {fld(
            "التاريخ",
            <AseelDatePicker
              className="aseel-input"
              disabled={effectiveReadOnly}
              value={formData.invoiceDate || ""}
              onChange={(val) => handleUpdateFinancial("invoiceDate", val)}
            />
          )}
          {fld(
            "تاريخ الاستحقاق",
            <AseelDatePicker
              className="aseel-input"
              disabled={effectiveReadOnly}
              value={formData.dealInfo?.dueDate || ""}
              onChange={(val) => handleDealInfoUpdate("dueDate", val)}
            />
          )}
          {fld(
            "رقم المستند",
            <input
              className="aseel-input"
              disabled={effectiveReadOnly}
              value={formData.supplierInvoiceNumber || ""}
              onChange={(e) => handleUpdateFinancial("supplierInvoiceNumber", e.target.value)}
              placeholder="رقم فاتورة المورد"
            />
          )}
          {fld(
            "المورد",
            <div className="aseel-pickfield">
              <input
                className="aseel-input aseel-input--hl"
                data-aseel-field="supplier"
                data-aseel-key="1"
                readOnly
                disabled={effectiveReadOnly}
                value={selectedSupplier ? `#${selectedSupplier.id}` : ""}
                placeholder="+ للفهرس"
                onClick={() => !readOnly && !formData.isHistorical && setShowSupplierPicker(true)}
              />
              <button
                type="button"
                className="aseel-ellipsis"
                disabled={effectiveReadOnly}
                onClick={() => setShowSupplierPicker(true)}
                title="فهرس الموردين (+)"
              >
                …
              </button>
            </div>
          )}
          {fld(
            "الاسم",
            <input
              className="aseel-input"
              readOnly
              value={headerSupplierName || ""}
            />
          )}
          {fld(
            "العملة",
            <select
              className="aseel-input"
              disabled={effectiveReadOnly}
              value={formData.currency || "ILS"}
              onChange={(e) => handleUpdateFinancial("currency", e.target.value)}
            >
              <option value="USD">USD — دولار</option>
              <option value="ILS">ILS — شيكل</option>
            </select>
          )}
          {formData.currency === "ILS" && fld(
            "نسبة الضريبة %",
            <input
              className="aseel-input"
              data-aseel-key="1"
              type="number"
              min={0}
              max={100}
              step={0.01}
              disabled={effectiveReadOnly}
              value={formData.taxRate || 0}
              onChange={(e) => handleUpdateFinancial("taxRate", Number(e.target.value))}
            />
          )}
          {fld(
            "مشتغل مرخص",
            <input
              className="aseel-input"
              disabled={effectiveReadOnly}
              value={formData.dealInfo?.licensedDealerNo || ""}
              onChange={(e) => handleDealInfoUpdate("licensedDealerNo", e.target.value)}
              placeholder="رقم المشتغل المرخص"
            />
          )}
          {formData.dealNumber && fld(
            "رقم الصفقة",
            <input
              className="aseel-input"
              readOnly
              value={formData.dealNumber}
            />
          )}
          {formData.importLogistics && fld(
            "رقم الشحنة",
            <input
              className="aseel-input"
              readOnly
              value={formData.importLogistics.shipmentNumber || ""}
            />
          )}
          {formData.importLogistics && fld(
            "رقم التخليص",
            <input
              className="aseel-input"
              readOnly
              value={String(formData.importLogistics.clearanceId || "")}
            />
          )}
          <label className="aseel-field aseel-field--inline">
            <input
              type="checkbox"
              disabled={effectiveReadOnly}
              checked={formData.shippingIncluded || false}
              onChange={(e) => handleUpdateFinancial("shippingIncluded", e.target.checked)}
            />
            <span className="aseel-field-label" style={{ flex: "unset" }}>
              الأسعار تشمل ض.ق.م
            </span>
          </label>
        </>
      }
      activeTab={activeTabKey}
      onTabChange={setActiveTabKey}
      tabs={[
        { key: "basic", label: "بيانات الفاتورة", content: basicInfoTab },
        { key: "items", label: "البنود والمنتجات", content: itemsTab },
        { key: "installments", label: "أقساط الدفع", content: installmentsTab },
        { key: "dealinfo", label: "معلومات الصفقة", content: dealInfoTab },
        { key: "notes", label: "الملاحظات", content: notesTab },
        { key: "attachments", label: "المرفقات", content: attachmentsTab },
        { key: "activity", label: "سجل النشاطات", content: activityTab },
        { key: "other", label: "بيانات أخرى", content: otherTab },
        // M2: المحاسبة والقيد + الحركات المالية inline داخل المحرر (توحيداً مع المبيعات).
        ...(formData.id && Number(formData.id) > 0 ? [
          {
            key: "accounting",
            label: "المحاسبة والقيد",
            content: (
              <div className="aseel-legacy-tab">
                <PurchaseInvoiceAccountingPanel
                  invoiceId={Number(formData.id)}
                  readOnly={readOnly}
                  onPosted={() => { void reloadInvoice(); if (onSave) onSave({ id: String(formData.id) }); }}
                />
              </div>
            ),
          },
          {
            key: "financial_movements",
            label: "الحركات المالية المرتبطة",
            content: (
              <DocumentPaymentsTab
                referenceType="PURCHASE_INVOICE"
                referenceId={Number(formData.id)}
                searchQuery={formData.invoiceNumber}
              />
            ),
          },
        ] : []),
      ]}
      totals={
        <>
          <div className="aseel-total-row">
            <span>مجموع البنود (قبل الخصم)</span>
            <span className="aseel-total-value">{fmt(ilsMerchandiseBase - (formData.shippingIncluded ? 0 : formData.shippingCost || 0))}</span>
          </div>
          {(formData.discountAmount || 0) > 0 && (
            <div className="aseel-total-row">
              <span>الخصم</span>
              <span className="aseel-total-value">{fmt(formData.discountAmount || 0)}</span>
            </div>
          )}
          <div className="aseel-total-row">
            <span>المجموع قبل الضريبة</span>
            <span className="aseel-total-value">{fmt(formData.subtotal || 0)}</span>
          </div>
          <div className="aseel-total-row">
            <span>الضريبة المضافة</span>
            <span className="aseel-total-value">{fmt(formData.taxAmount || 0)}</span>
          </div>
          <div className="aseel-total-row aseel-total-row--grand">
            <span>مبلغ الفاتورة الإجمالي</span>
            <span className="aseel-total-value">{fmt(formData.grandTotal || 0)}</span>
          </div>
        </>
      }
      status={
        <>
          <span className="aseel-status-item">المستخدم <b>{currentUser?.name || "—"}</b></span>
          <span className="aseel-status-item">رقم القيد <b>{formData.glPurchaseReceiptJournalId ?? "—"}</b></span>
          {formData.importLogistics && (
            <span className="aseel-status-item">رقم الحركة <b>{formData.importLogistics.shipmentNumber || "—"}</b></span>
          )}
          <span className="aseel-status-item">الحالة <b>{formData.isPosted ? "مرحّلة" : formData.isHistorical ? "مؤرشفة" : formData.id ? "مسودة" : "جديدة"}</b></span>
          <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
          <span className="aseel-status-item">{effectiveReadOnly ? "للقراءة فقط" : "قابل للتعديل ✓"}</span>
        </>
      }
    >
      {accBanner}
      {/* الشجرة انتقلت إلى الشريط الجانبي (aside) ليرتفع لأعلى المستند. */}
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <AseelGrid<InvoiceItem>
            columns={itemColumns}
            rows={formData.items || []}
            getCell={itemGetCell}
            getRowKey={(r) => r.id}
            onChange={effectiveReadOnly ? undefined : itemOnChange}
            onAddRow={effectiveReadOnly ? undefined : addRow}
            emptyHint="لا توجد بنود — أضف صنفاً من الشجرة أو اكتب اسمه"
          />
          {!readOnly && !formData.isHistorical && (
            <button type="button" className="aseel-addrow" onClick={addRow}>
              <Plus className="h-3 w-3" /> إضافة سطر
            </button>
          )}
          {(Object.entries(costWarnings) as [string, CostWarning][]).map(([rowId, w]) => (
            <div
              key={rowId}
              role="alert"
              style={{
                display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                margin: "4px 0", padding: "6px 10px", borderRadius: 4,
                background: "var(--aseel-warn-bg, #fff7e6)",
                border: "1px solid var(--aseel-warn, #e0a800)",
                color: "var(--aseel-ink)", fontSize: "var(--aseel-fs-sm)",
              }}
            >
              <AlertCircle style={{ width: 14, height: 14, color: "var(--aseel-warn, #e0a800)" }} />
              <span>
                هذا السعر سيغيّر متوسط تكلفة «<b>{w.name}</b>» من <b>{formatMoney(w.from)}</b> إلى{" "}
                <b>{formatMoney(w.to)}</b>.
              </span>
              <button
                type="button"
                className="aseel-toolbtn"
                style={{ fontWeight: 600 }}
                onClick={() => openInNewTab(`/product-cost?product=${w.productId}`)}
              >
                تكلفة المنتجات
              </button>
            </div>
          ))}
        </div>
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
      actionButton={
        <button
          type="button"
          onClick={() => setShowAddSupplierModal(true)}
          className="flex items-center gap-1 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
        >
          <Plus className="w-4 h-4" /> إضافة مورد
        </button>
      }
      onSelect={(r) => {
        setFormData((prev) => ({ ...prev, supplierId: r.id, factoryName: r.tradeName }));
        setShowSupplierPicker(false);
        markDirty();
      }}
      onClose={() => setShowSupplierPicker(false)}
    />

    {showAddSupplierModal && (
      <SupplierModal
        isOpen={showAddSupplierModal}
        onClose={() => setShowAddSupplierModal(false)}
        onSaveSuccess={(newSupplier) => {
          setShowAddSupplierModal(false);
          setFormData((prev) => ({ ...prev, supplierId: newSupplier.id, factoryName: newSupplier.tradeName || newSupplier.alias || "" }));
          setShowSupplierPicker(false);
          markDirty();
        }}
      />
    )}

    {showItemSearch && (
      <ItemSearchModal
        isOpen={showItemSearch}
        onClose={() => setShowItemSearch(false)}
        onSelectItem={handleItemSelect}
        items={allDbItems}
        supplierId={formData.supplierId}
        onItemCreated={(it) =>
          setAllDbItems((prev) =>
            prev.some((p) => String(p.id) === String(it.id)) ? prev : [it, ...prev]
          )
        }
      />
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
          applyItemAt(inlineCreate.rowIndex, item);
          setInlineCreate(null);
        }}
      />
    )}

    {previewImage && (
      <div className="fixed inset-0 z-[60] bg-black/90 flex items-center justify-center p-4" onClick={() => setPreviewImage(null)}>
        <img src={previewImage} alt="Preview" className="max-w-full max-h-full rounded-lg" />
        <button onClick={() => setPreviewImage(null)} className="absolute top-4 right-4 text-white p-2 aseel-bg-panel rounded-full">
          <ArrowRight className="w-6 h-6 rotate-180" />
        </button>
      </div>
    )}

    {/* DEF-007/008: بطاقة الصنف المشتركة — «موافق» يُدرج الصنف في فاتورة الشراء. */}
    {cardProductId != null && (() => {
      const it = allDbItems.find((x) => String(x.id) === String(cardProductId));
      return (
        <ProductCardModal
          productId={cardProductId}
          productName={it ? it.name : undefined}
          addMode={!(!cardCanAdd || effectiveReadOnly || !it)}
          suggestedPrice={cardSuggestedPrice}
          priceSource={cardSuggestedPrice != null ? "last_invoice" : "default"}
          onConfirm={(!cardCanAdd || effectiveReadOnly || !it) ? undefined : (opts) => {
            const price = opts?.unitPrice ?? cardSuggestedPrice ?? 0;
            applyItemAt(null, it, price, opts?.quantity);
          }}
          onClose={() => setCardProductId(null)}
        />
      );
    })()}
      {showPrintView && (
        <InvoicePrintView
          invoice={formData as Invoice}
          currentUser={currentUser}
          supplier={selectedSupplier}
          onClose={() => setShowPrintView(false)}
        />
      )}
    </div>
  );
};