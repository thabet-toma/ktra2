import React, { useState, useEffect } from "react";
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
  Info,
  DollarSign,
  Coins,
  Briefcase,
  Calculator
} from "lucide-react";
import { ItemsTableSection } from "@/components/forms/shared/ItemsTableSection";
import { AttachmentsSection } from "@/components/forms/shared/AttachmentsSection";
import {
  invoicesService,
  suppliersService,
} from "@/services/firestoreService";
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
  NISLocalPayments,
} from "./sections";

interface InvoiceFormProps {
  invoice: Partial<Invoice> | null;
  currentUser: User;
  onCancel: () => void;
  onSave?: () => void;
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
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [showItemSearch, setShowItemSearch] = useState(false);

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
    const validShipping = nextData.shippingIncluded
      ? 0
      : nextData.shippingCost || 0;
    const afterDiscount = Math.max(
      0,
      itemsSubtotal - (nextData.discountAmount || 0)
    );
    const taxableBase = afterDiscount + validShipping;

    let taxAmount = 0;
    if (nextData.taxType === 'amount') {
      taxAmount = nextData.taxAmount || 0;
    } else {
      taxAmount = taxableBase * ((nextData.taxRate || 0) / 100);
    }

    const calculateTotalLocalPayments = () => {
      const lp = nextData.localPayments;
      if (!lp || lp.includedInPrice) return 0;
      if (lp.calculationMethod === 'lump_sum') return lp.lumpSumAmount || 0;
      return (
        (lp.customsClearanceFees || 0) +
        (lp.customsDuties || 0) +
        (lp.portFees || 0) +
        (lp.internalShippingFees || 0) +
        (lp.palestinianTaxCustoms || 0)
      );
    };

    const totalLocalPayments = calculateTotalLocalPayments();
    const grandTotal = taxableBase + taxAmount + totalLocalPayments;

    setFormData((prev) => ({
      ...prev,
      ...updatedFields,
      subtotal: itemsSubtotal,
      taxAmount,
      grandTotal,
    }));
  };

  // Initialize form data
  useEffect(() => {
    if (!initialInvoice?.id) {
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
        invoiceName: dealData?.internalNotes || "",
        invoiceDate: dealData?.dealDate || new Date().toISOString().split('T')[0],
        dealInfo: dealInfo,
        currency: dealData ? 'ILS' : 'USD',
      }));
    } else if (initialInvoice.dealInfo) {
      setDealInfo(initialInvoice.dealInfo);
      setInstallments(initialInvoice.installments || []);
      setInstallmentPlanEnabled(initialInvoice.installmentPlanEnabled || false);
      setDealActivities(initialInvoice.dealInfo.activityLog || []);
    }
  }, [initialInvoice, dealData]);

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

      if (isNew) {
        payload.createdBy = currentUser.id;
        payload.createdAt = now;

        if (dealData?.id) {
          payload.dealId = dealData.id;
          payload.dealNumber = dealData.dealNumber;
        }

        await invoicesService.addInvoiceToDb(payload);
        setFormData(prev => ({ ...prev, id: invoiceId }));
      } else {
        if (formData.isHistorical) {
          alert("لا يمكن تعديل الفواتير المؤرشفة");
          setSaving(false);
          return;
        }
        await invoicesService.updateInvoiceInDb(payload as Invoice);
      }

      if (onSave) onSave();
      alert("تم حفظ الفاتورة بنجاح");

    } catch (error) {
      console.error("Error saving invoice:", error);
      alert("حدث خطأ أثناء الحفظ");
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
      unitPrice: lastPrice || 0,
      totalPrice: lastPrice || 0,
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
      newItems[index].totalPrice = qty * price;
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
        const validShipping = updated.shippingIncluded ? 0 : (updated.shippingCost || 0);
        const afterDiscount = Math.max(0, itemsSubtotal - (updated.discountAmount || 0));
        const taxableBase = afterDiscount + validShipping;

        let taxAmount = 0;
        if (updated.taxType === 'amount') {
          taxAmount = updated.taxAmount || 0;
        } else {
          taxAmount = taxableBase * ((updated.taxRate || 0) / 100);
        }

        const lp = updated.localPayments;
        const totalLocalPayments = (!lp || lp.includedInPrice) ? 0 : (
          (lp.customsClearanceFees || 0) +
          (lp.customsDuties || 0) +
          (lp.portFees || 0) +
          (lp.internalShippingFees || 0) +
          (lp.palestinianTaxCustoms || 0)
        );

        const grandTotal = taxableBase + taxAmount + totalLocalPayments;
        return { ...updated, subtotal: itemsSubtotal, taxAmount, grandTotal };
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
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                {formData.id ? `تعديل الفاتورة: ${formData.invoiceNumber}` : "إنشاء فاتورة جديدة"}
                {formData.isHistorical && <span className="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded">مؤرشف</span>}
                {formData.dealId && <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">مرتبطة بصفقة</span>}
                <span className={`text-xs ml-2 px-2 py-0.5 rounded ${formData.currency === 'ILS' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800'}`}>
                  العملة: {formData.currency === 'ILS' ? 'شيقل (₪)' : 'دولار ($)'}
                </span>
              </h1>
              <p className="text-sm text-gray-500">
                {formData.dealNumber ? `الفاتورة مرتبطة بالصفقة: ${formData.dealNumber}` : "إدارة تفاصيل فاتورة المشتريات"}
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

      <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
        <CollapsibleSection title="بيانات الفاتورة والمورد" icon={Info} defaultOpen={true}>
          <InvoiceBasicInfo
            data={formData}
            setData={setFormData}
            suppliers={suppliers}
            readOnly={readOnly || formData.isHistorical}
            items={formData.items}
          />
        </CollapsibleSection>

        {formData.currency === 'ILS' ? (
          <div className="space-y-6">
            {formData.conversionMetadata && (
              <ConversionDetailsSection metadata={formData.conversionMetadata} />
            )}

            <CollapsibleSection title="سلة المنتجات (شيقل)" icon={Briefcase} defaultOpen={true}>
              <NISItemsTable
                items={formData.items || []}
                conversionRate={formData.conversionMetadata?.dealEffectiveRate || 1}
              />
            </CollapsibleSection>

            <NISLocalPayments
              data={formData.localPayments || {}}
              onUpdate={(field, val) => handleUpdateFinancial(field, val)}
              readOnly={readOnly || formData.isHistorical}
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
                  />
                </CollapsibleSection>
              </div>

              <div className="lg:col-span-4">
                <NISFinancialSummary
                  subtotal={formData.subtotal || 0}
                  discountAmount={formData.discountAmount || 0}
                  taxAmount={formData.taxAmount || 0}
                  taxRate={formData.taxRate || 0}
                  shippingCost={formData.shippingCost || 0}
                  grandTotal={formData.grandTotal || 0}
                  localPayments={formData.localPayments || {}}
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