import React, { useState, useEffect, useMemo } from "react";
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
  Plus,
  Printer,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import {
  suppliersService,
} from "@/services/firestoreService";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { mapPurchaseInvoiceDtoToInvoice } from "@/utils/mapPurchaseInvoiceDto";
import { dealsService } from "@/services/dealsService";
import { shipmentsService } from "@/services/shipmentsService";
import {
  invoiceGrandTotalIls,
  invoiceVatBaseIls,
} from "@/utils/invoiceTaxesAndFees";
import { roundSqlMoney2, roundSqlMoney4 } from "@/utils/sqlMoneyRound";
import { ItemSearchModal } from "../price-offers/ItemSearchModal";
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
import {
  AseelDocumentShell,
  AseelGrid,
  AseelIndexPicker,
  useRecordNavigation,
  useAseelKeymap,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../../aseel";
import { formatInvoiceImportLogisticsLine } from "@/utils/invoiceConversionUtils";

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
  allDbItems,
  dealData,
  readOnly = false,
}) => {
  const [formData, setFormData] = useState<Partial<Invoice>>(
    initialInvoice || {}
  );
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [saving, setSaving] = useState(false);
  const [recalcBusy, setRecalcBusy] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [showItemSearch, setShowItemSearch] = useState(false);
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
  const [showSupplierPicker, setShowSupplierPicker] = useState(false);

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
          console.error('Error loading invoice:', err);
        }
      }
    },
  });

  // M4-T1: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => window.print(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    F12: () => handleSave(),
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
    // N0-T11: Ctrl+nav handlers
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => nav.goNew(),
  }, { enabled: !showSupplierPicker });

  // Load invoices list for navigation
  useEffect(() => {
    const loadInvoices = async () => {
      try {
        const list = await purchaseInvoiceApi.list();
        setInvoicesList(list);
      } catch (err) {
        console.error('Error loading invoices list:', err);
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
      items: prev.items || [],
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
      currency: dealData ? "ILS" : "USD",
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
      alert("الرجاء اختيار المورد");
      return;
    }
    if (!formData.items || formData.items.length === 0) {
      alert("الرجاء إضافة صنف واحد على الأقل");
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
        status: payload.status || 'draft',
        notes: payload.notes || null,
        supplier_invoice_number: payload.supplierInvoiceNumber || null,
        factory_name: payload.factoryName || null,
        items: (payload.items || []).map((item: any) => ({
          product: item.itemId ? Number(item.itemId) || null : null,
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
          alert("لا يمكن تعديل الفواتير المؤرشفة");
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

      if (onSave) onSave({ id: savedSqlId });
      alert("تم حفظ الفاتورة بنجاح");
    } catch (error) {
      console.error("Error saving invoice:", error);
      const msg =
        error instanceof Error && error.message?.trim()
          ? error.message.trim()
          : "حدث خطأ أثناء الحفظ";
      alert(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleAddItem = () => {
    setShowItemSearch(true);
  };

  const handleItemSelect = (item: Item, lastPrice?: number) => {
    const newItem: InvoiceItem = {
      id: crypto.randomUUID(),
      itemId: item.id,
      name: item.name,
      categoryId: item.categoryId,
      categoryName: item.categoryName,
      specifications: item.specifications || "",
      imageUrls: item.imageUrls,
      hsCodePrimary: item.hsCodePrimary,
      quantity: 1,
      unitPrice: roundSqlMoney4(lastPrice || 0),
      totalPrice: roundSqlMoney2(lastPrice || 0),
    };

    const updatedItems = [...(formData.items || []), newItem];
    recalculateTotals({ items: updatedItems });
    setShowItemSearch(false);
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
  };

  const handleRemoveItem = (index: number) => {
    const updatedItems = (formData.items || []).filter((_, i) => i !== index);
    recalculateTotals({ items: updatedItems });
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
      return;
    }
    recalculateTotals({ [field]: value });
  };

  const handleDealInfoUpdate = (field: string, value: any) => {
    setDealInfo((prev) => ({ ...prev, [field]: value }));
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
  };

  const handleRemoveInstallment = (index: number) => {
    const updatedInstallments = installments.filter((_, i) => i !== index);
    const renumberedInstallments = updatedInstallments.map(
      (installment, idx) => ({ ...installment, installmentNumber: idx + 1 })
    );
    setInstallments(renumberedInstallments);
  };

  const handleUpdateInstallment = (index: number, field: string, value: any) => {
    const updatedInstallments = [...installments];
    updatedInstallments[index] = { ...updatedInstallments[index], [field]: value };
    setInstallments(updatedInstallments);
  };

  const handleToggleInstallmentPlan = (enabled: boolean) => {
    setInstallmentPlanEnabled(enabled);
    if (!enabled) {
      setInstallments([]);
    } else {
      handleAddInstallment();
    }
  };

  const handleRecalculateLanded = async () => {
    if (!formData.shipment || !formData.id) {
      alert("لا توجد شحنة مرتبطة أو الفاتورة غير محفوظة بعد.");
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
      alert(msg);
    } catch (e) {
      console.error(e);
      alert(e instanceof Error ? e.message : "تعذّر إعادة الحساب");
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
    if (readOnly || formData.isHistorical) return;
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

  const fmt = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const fld = (label: string, node: React.ReactNode) => (
    <label className="aseel-field">
      <span className="aseel-field-label">{label}</span>
      {node}
    </label>
  );

  const selectedSupplier = formData.supplierId
    ? suppliers.find((s) => s.id === formData.supplierId)
    : undefined;

  /* ───────────── أعمدة جدول البنود (AseelGrid) ───────────── */
  const itemColumns: AseelGridColumn<InvoiceItem>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "itemId", header: "رقم الصنف", width: "100px" },
    { key: "name", header: "اسم الصنف", width: "25%" },
    { key: "specifications", header: "بيان", width: "20%" },
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
  };

  const removeRow = (key: string) => {
    const updated = (formData.items || []).filter((i) => i.id !== key);
    recalculateTotals({ items: updated });
  };

  const renderItemIdCell = (row: InvoiceItem) => (
    <button
      type="button"
      className="aseel-cell-picker"
      disabled={readOnly || formData.isHistorical}
      data-aseel-key="1"
      onClick={() => setShowItemSearch(true)}
      title="اختر صنفاً (+ فهرس الأصناف)"
    >
      {row.itemId ? `#${row.itemId}` : "— اختر صنفاً —"}
    </button>
  );

  const renderDeleteCell = (row: InvoiceItem) =>
    readOnly || formData.isHistorical ? null : (
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
  itemColumns[7].render = renderDeleteCell;

  /* ───────────── تبويبات ───────────── */
  const notesTab = (
    <textarea
      className="aseel-input"
      rows={3}
      style={{ width: "100%" }}
      disabled={readOnly || formData.isHistorical}
      value={formData.notes || formData.dealInfo?.internalNotes || ""}
      onChange={(e) => handleDealInfoUpdate("internalNotes", e.target.value)}
    />
  );

  const attachmentsTab = (
    <div className="aseel-legacy-tab">
      <AttachmentsSection data={formData} setData={setFormData} />
    </div>
  );

  const basicInfoTab = (
    <div className="aseel-legacy-tab">
      <InvoiceBasicInfo
        data={formData}
        setData={setFormData}
        suppliers={suppliers}
        readOnly={readOnly || formData.isHistorical}
        items={formData.items}
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
            readOnly={readOnly || !!formData.isHistorical}
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
          readOnly={readOnly || formData.isHistorical}
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
        onToggleInstallmentPlan={handleToggleInstallmentPlan}
        onAddInstallment={handleAddInstallment}
        onRemoveInstallment={handleRemoveInstallment}
        onUpdateInstallment={handleUpdateInstallment}
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
        onUpdateDealInfo={handleDealInfoUpdate}
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
          disabled={readOnly || formData.isHistorical}
          checked={formData.shippingIncluded || false}
          onChange={(e) => handleUpdateFinancial("shippingIncluded", e.target.checked)}
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

  const toolbarActions: AseelToolbarAction[] = [
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)", icon: <Save />, onClick: !saving ? () => handleSave() : undefined, disabled: saving },
    { key: "new", label: "جديدة", icon: <Plus />, onClick: () => nav.goNew(), separatorBefore: true },
    { key: "print", label: "طباعة (F2)", icon: <Printer />, onClick: () => window.print(), separatorBefore: true },
    { key: "cancel", label: "إلغاء", icon: <X />, onClick: onCancel, danger: true, separatorBefore: true },
  ];

  return (
    <div
      id="purchase-invoice-print"
      dir="rtl"
      style={{ height: "calc(100vh - 13rem)", minHeight: 560 }}
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
            <input
              className="aseel-input"
              type="date"
              disabled={readOnly || formData.isHistorical}
              value={formData.invoiceDate || ""}
              onChange={(e) => handleUpdateFinancial("invoiceDate", e.target.value)}
            />
          )}
          {fld(
            "تاريخ الاستحقاق",
            <input
              className="aseel-input"
              type="date"
              disabled={readOnly || formData.isHistorical}
              value={formData.dealInfo?.dueDate || ""}
              onChange={(e) => handleDealInfoUpdate("dueDate", e.target.value)}
            />
          )}
          {fld(
            "رقم المستند",
            <input
              className="aseel-input"
              disabled={readOnly || formData.isHistorical}
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
                disabled={readOnly || formData.isHistorical}
                value={selectedSupplier ? `#${selectedSupplier.id}` : ""}
                placeholder="+ للفهرس"
                onClick={() => !readOnly && !formData.isHistorical && setShowSupplierPicker(true)}
              />
              <button
                type="button"
                className="aseel-ellipsis"
                disabled={readOnly || formData.isHistorical}
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
              disabled={readOnly || formData.isHistorical}
              value={formData.currency || "USD"}
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
              disabled={readOnly || formData.isHistorical}
              value={formData.taxRate || 0}
              onChange={(e) => handleUpdateFinancial("taxRate", Number(e.target.value))}
            />
          )}
          {fld(
            "مشتغل مرخص",
            <input
              className="aseel-input"
              disabled={readOnly || formData.isHistorical}
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
              disabled={readOnly || formData.isHistorical}
              checked={formData.shippingIncluded || false}
              onChange={(e) => handleUpdateFinancial("shippingIncluded", e.target.checked)}
            />
            <span className="aseel-field-label" style={{ flex: "unset" }}>
              الأسعار تشمل ض.ق.م
            </span>
          </label>
        </>
      }
      tabs={[
        { key: "basic", label: "بيانات الفاتورة", content: basicInfoTab },
        { key: "items", label: "البنود والمنتجات", content: itemsTab },
        { key: "installments", label: "أقساط الدفع", content: installmentsTab },
        { key: "dealinfo", label: "معلومات الصفقة", content: dealInfoTab },
        { key: "notes", label: "الملاحظات", content: notesTab },
        { key: "attachments", label: "المرفقات", content: attachmentsTab },
        { key: "activity", label: "سجل النشاطات", content: activityTab },
        { key: "other", label: "بيانات أخرى", content: otherTab },
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
          <span className="aseel-status-item">{readOnly || formData.isHistorical ? "للقراءة فقط" : "قابل للتعديل ✓"}</span>
        </>
      }
    >
      <AseelGrid<InvoiceItem>
        columns={itemColumns}
        rows={formData.items || []}
        getCell={itemGetCell}
        getRowKey={(r) => r.id}
        onChange={readOnly || formData.isHistorical ? undefined : itemOnChange}
        onAddRow={readOnly || formData.isHistorical ? undefined : addRow}
        emptyHint="لا توجد بنود — أضف صنفاً (+ فهرس الأصناف)"
      />
      {!readOnly && !formData.isHistorical && (
        <button type="button" className="aseel-addrow" onClick={addRow}>
          <Plus className="h-3 w-3" /> إضافة سطر
        </button>
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
      onSelect={(r) => {
        setFormData((prev) => ({ ...prev, supplierId: r.id, factoryName: r.tradeName }));
        setShowSupplierPicker(false);
      }}
      onClose={() => setShowSupplierPicker(false)}
    />

    {showItemSearch && (
      <ItemSearchModal
        isOpen={showItemSearch}
        onClose={() => setShowItemSearch(false)}
        onSelectItem={handleItemSelect}
        items={allDbItems}
        supplierId={formData.supplierId}
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
    </div>
  );
};