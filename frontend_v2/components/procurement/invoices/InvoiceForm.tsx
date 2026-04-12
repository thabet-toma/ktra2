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
  Paperclip,
  DollarSign,
  Coins,
  Briefcase,
  Calculator,
  RefreshCw,
} from "lucide-react";
import { ItemsTableSection } from "@/components/forms/shared/ItemsTableSection";
import { AttachmentsSection } from "@/components/forms/shared/AttachmentsSection";
import {
  suppliersService,
} from "@/services/firestoreService";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { mapPurchaseInvoiceDtoToInvoice } from "@/utils/mapPurchaseInvoiceDto";
import { dealsService } from "@/services/dealsService";
import { shipmentsService } from "@/services/shipmentsService";
import { formatInvoiceImportLogisticsLine } from "@/utils/invoiceConversionUtils";
import {
  invoiceGrandTotalIls,
  invoiceVatBaseIls,
} from "@/utils/invoiceTaxesAndFees";
import { roundSqlMoney2, roundSqlMoney4 } from "@/utils/sqlMoneyRound";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
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

  return (
    <div className="bg-gray-50 dark:bg-gray-900 min-h-screen pb-20">
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex flex-col sm:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onCancel}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              <ArrowRight className="w-5 h-5 text-gray-500" />
            </button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h1 className="text-xl font-bold text-gray-900 dark:text-white flex flex-wrap items-center gap-2">
                  {formData.id ? `تعديل الفاتورة: ${formData.invoiceNumber}` : "إنشاء فاتورة جديدة"}
                  {formData.isHistorical && <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">مؤرشف</span>}
                  {formData.dealId && <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">مرتبطة بصفقة</span>}
                  <span className={`text-xs px-2 py-0.5 rounded ${formData.currency === 'ILS' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'}`}>
                    العملة: {formData.currency === 'ILS' ? 'شيكل (₪)' : 'دولار ($)'}
                  </span>
                </h1>
                <button
                  type="button"
                  onClick={() => setInvoiceHeaderDetailsOpen((o) => !o)}
                  aria-expanded={invoiceHeaderDetailsOpen}
                  title={invoiceHeaderDetailsOpen ? "إخفاء" : "عرض بيانات الفاتورة والمورد"}
                  className={`text-sm font-semibold shrink-0 rounded-md px-2 py-0.5 transition-colors underline-offset-2 hover:underline ${
                    invoiceHeaderDetailsOpen
                      ? "text-blue-800 dark:text-blue-200 bg-blue-100 dark:bg-blue-900/50 ring-1 ring-blue-300 dark:ring-blue-600"
                      : "text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                  }`}
                >
                  تفاصيل
                </button>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 space-y-1">
                {formData.importLogistics ? (
                  <>
                    {formData.dealNumber ? (
                      <span className="block">
                        مرتبطة بالصفقة {formData.dealNumber}
                        {headerDealDescription ? (
                          <span className="block mt-0.5 text-gray-700 dark:text-gray-300 font-medium">
                            وصف الصفقة: {headerDealDescription}
                          </span>
                        ) : null}
                      </span>
                    ) : null}
                    <span className="block mt-1 text-indigo-700 dark:text-indigo-300 font-medium">
                      {formatInvoiceImportLogisticsLine(formData.importLogistics)}
                    </span>
                  </>
                ) : formData.dealNumber ? (
                  <>
                    <span className="block">
                      الفاتورة مرتبطة بالصفقة: {formData.dealNumber}
                    </span>
                    {headerDealDescription ? (
                      <span className="block text-gray-700 dark:text-gray-300 font-medium">
                        وصف الصفقة: {headerDealDescription}
                      </span>
                    ) : null}
                  </>
                ) : (
                  <>
                    <span className="block">إدارة تفاصيل فاتورة المشتريات</span>
                    {formData.dealId && headerDealDescription ? (
                      <span className="block text-gray-700 dark:text-gray-300 font-medium">
                        وصف الصفقة: {headerDealDescription}
                      </span>
                    ) : null}
                  </>
                )}
                {headerSupplierName ? (
                  <span className="block text-gray-700 dark:text-gray-300 font-medium">
                    المورد: {headerSupplierName}
                  </span>
                ) : null}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 dark:text-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 rounded-lg transition-colors flex-1 sm:flex-none justify-center"
            >
              رجوع
            </button>
            {!readOnly && formData.shipment && formData.id && formData.currency === "ILS" ? (
              <button
                type="button"
                onClick={() => void handleRecalculateLanded()}
                disabled={recalcBusy || formData.isPosted}
                title={
                  formData.isPosted
                    ? "الترحيل لا يغيّر النسب والحصص المعروضة (محفوظة في الفاتورة). إعادة الحساب من الخادم معطّلة للمرحّل — ألغِ الترحيل لتجديد الأرقام."
                    : undefined
                }
                className="px-4 py-2 bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 border border-slate-300 dark:border-slate-600 rounded-lg flex items-center gap-2 text-sm font-semibold disabled:opacity-50 hover:bg-slate-200 dark:hover:bg-slate-700"
              >
                {recalcBusy ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                إعادة حساب التكلفة
              </button>
            ) : null}
            {!readOnly && (
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm flex items-center justify-center gap-2 transition-all flex-1 sm:flex-none disabled:opacity-70 disabled:cursor-not-allowed"
              >
                {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
                <span>{formData.id ? "حفظ التغييرات" : "حفظ الفاتورة"}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {invoiceHeaderDetailsOpen ? (
        <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 py-4">
            <p className="text-xs font-bold text-gray-500 dark:text-gray-400 mb-3">بيانات الفاتورة والمورد</p>
            <InvoiceBasicInfo
              data={formData}
              setData={setFormData}
              suppliers={suppliers}
              readOnly={readOnly || formData.isHistorical}
              items={formData.items}
            />
          </div>
        </div>
      ) : null}

      <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        {formData.currency === 'ILS' ? (
          <div className="space-y-6">
            {(formData.conversionMetadata || formData.importLogistics) && (
              <ConversionDetailsSection
                metadata={formData.conversionMetadata}
                importLogistics={formData.importLogistics}
                shippingIncluded={Boolean(formData.shippingIncluded)}
                invoiceShippingCostIls={formData.shippingCost}
                invoiceClearanceId={formData.clearanceId}
              />
            )}

            <CollapsibleSection title="سلة المنتجات (شيكل)" icon={Briefcase} defaultOpen={true}>
              <NISItemsTable
                items={formData.items || []}
                conversionRate={formData.conversionMetadata?.dealEffectiveRate || 1}
                invoiceTaxAmount={formData.taxAmount || 0}
                localPayments={formData.localPayments || {}}
                taxableBaseIls={ilsMerchandiseBase}
                invoiceVatBaseIls={ilsVatBase}
                conversionMetadata={formData.conversionMetadata}
              />
            </CollapsibleSection>

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

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-8">
                <CollapsibleSection title="أقساط الدفع" icon={Calculator} defaultOpen={true}>
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
                    grandTotalFromForm={
                      formData.currency === "ILS" ? formData.grandTotal : undefined
                    }
                    mainVatForExtras={formData.taxAmount || 0}
                    conversionMetadata={formData.conversionMetadata}
                  />
                </CollapsibleSection>
              </div>

              <div className="lg:col-span-4">
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
              </div>
            </div>
          </div>
        ) : (
          <>
            <CollapsibleSection title="معلومات الفاتورة" icon={Briefcase} defaultOpen={true}>
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
                taxType={formData.taxType || 'percentage'}
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
                onUpdateFinancial={(field, value) => {
                  const dealInfoFields = [
                    'productionDays', 'deliveryDays', 'paymentMethod',
                    'shippingMethod', 'warrantyDuration', 'certificates',
                    'shipmentNotes'
                  ];
                  const weightVolumeFields = ['totalWeight', 'totalVolume'];

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
            </CollapsibleSection>

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
            />
          </>
        )}

        {/* Hiding DealInfoSection per user request */}
        {/* {formData.currency !== 'ILS' && (formData.dealId || formData.dealNumber) && (
          <DealInfoSection dealInfo={dealInfo} formData={formData} onUpdateDealInfo={handleDealInfoUpdate} />
        )} */}

        {dealActivities.length > 0 && <DealActivityLog activities={dealActivities} />}

        <CollapsibleSection title="المرفقات والصور" icon={Paperclip} defaultOpen={false}>
          <AttachmentsSection data={formData} setData={setFormData} />
        </CollapsibleSection>
      </div>

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
          <button onClick={() => setPreviewImage(null)} className="absolute top-4 right-4 text-white p-2 bg-gray-800 rounded-full">
            <ArrowRight className="w-6 h-6 rotate-180" />
          </button>
        </div>
      )}
    </div>
  );
};