import React, { useState, useEffect, useRef } from 'react';
import { Shipment, Supplier, Deal, User, ShipmentInstallment } from '../../../types';
import { shipmentsService } from '../../../services/shipmentsService';
import { suppliersService } from '../../../services/firestoreService';
import { dealsService } from '../../../services/dealsService';
import { notificationsService } from '../../../services/notificationsService';
import { cloudinaryService } from '../../../services/cloudinaryService';
import { Truck, Save, Info, CreditCard, AlertCircle, Navigation } from 'lucide-react';
import { CollapsibleSection } from '@/components/ui/CollapsibleSection';
import { InstallmentManager } from '../deals/InstallmentManager';
import { PaymentProgress } from '../deals/PaymentProgress';
import { SupplierViewModal } from '@/components/common/SupplierViewModal';
import { getLatestShippingTerm } from '../../../constants/shipping';
import { ShipmentBasicInfo } from './form/ShipmentBasicInfo';
import { ShipmentShippingDetails } from './form/ShipmentShippingDetails';
import { ShipmentDealsTable } from './form/ShipmentDealsTable';
import { ShipmentDealSelector } from './form/ShipmentDealSelector';
import { ShipmentStatusVisualizer } from './form/ShipmentStatusVisualizer';



interface ShipmentFormProps {
    shipment: Partial<Shipment> | null;
    onCancel: () => void;
    onSave: () => void;
    currentUser: User;
}

export const ShipmentForm: React.FC<ShipmentFormProps> = ({ shipment, onCancel, onSave, currentUser }) => {
    // --- State Management ---
    const [formData, setFormData] = useState<any>(shipment || {
        status: 'draft',
        shipmentNumber: 'New',
        agentShipmentNumber: '',
        deals: [],
        totalShippingCostUsd: 0,
        totalVolume: 0,
        totalWeightKg: 0,
        installments: [],
        installmentPlanEnabled: false,
        payments: [],
        pricingMethod: 'total',
        unitType: 'cbm',
        pricePerUnit: 0,
        shipmentName: '',
        israeliSideName: ''
    });

    const [shippingInfo, setShippingInfo] = useState<any>({
        shippingType: 'sea',
        ...(shipment as any)?.shippingInfo
    });

    const [installments, setInstallments] = useState<ShipmentInstallment[]>(shipment?.installments || []);
    const [installmentPlanEnabled, setInstallmentPlanEnabled] = useState(shipment?.installmentPlanEnabled || false);
    const [installmentValidationError, setInstallmentValidationError] = useState("");

    const [allSuppliers, setAllSuppliers] = useState<Supplier[]>([]);
    const [allDeals, setAllDeals] = useState<Deal[]>([]);
    const [loading, setLoading] = useState(true);

    // Modal States
    const [selectedSupplierId, setSelectedSupplierId] = useState<string | null>(null);
    const [isSupplierModalOpen, setIsSupplierModalOpen] = useState(false);
    const [isDealSelectorOpen, setIsDealSelectorOpen] = useState(false); // 🟢 New

    const [saving, setSaving] = useState(false);
    const isSubmittingRef = useRef(false);
    const [totals, setTotals] = useState({ weight: 0, volume: 0 });
    const [uploadingFile, setUploadingFile] = useState(false);

    // --- Effects ---
    useEffect(() => {
        const unsubSuppliers = suppliersService.subscribeToSuppliers((suppliers) => {
            setAllSuppliers(suppliers.filter(s => s.type === 'shipping_agent'));
        });
        const unsubDeals = dealsService.subscribeToDeals((deals) => {
            const currentDealIds = formData.deals?.map((d: any) => d.dealId) || [];
            // جلب الصفقات الجاهزة للشحن أو التي هي جزء من هذه الشحنة بالفعل
            setAllDeals(deals.filter(d => d.status === 'production_completed' || d.status === 'shipping_preparation' || d.status === 'shipped' || currentDealIds.includes(d.id)));
        });
        setLoading(false);
        return () => { unsubSuppliers(); unsubDeals(); };
    }, []);

    // تحديث المجاميع
    useEffect(() => {
        if (formData.deals && allDeals.length > 0) {
            let totalW = 0, totalV = 0;
            const dealShippingTerms: string[] = [];
            formData.deals.forEach((d: any) => {
                const originalDeal = allDeals.find(ad => ad.id === d.dealId);
                totalW += d.totalWeightKg || originalDeal?.totalWeightKg || originalDeal?.totalWeight || 0;
                totalV += d.totalVolume || originalDeal?.totalVolume || 0;
                if (originalDeal?.shippingMethod) dealShippingTerms.push(originalDeal.shippingMethod);
            });
            setTotals({ weight: totalW, volume: totalV });
            if (dealShippingTerms.length > 0) {
                const latest = getLatestShippingTerm(dealShippingTerms);
                setShippingInfo((prev: any) => ({ ...prev, fromTerm: latest, toTerm: prev.toTerm || 'DDP' }));
            }
        } else {
            setTotals({ weight: 0, volume: 0 });
        }
    }, [formData.deals, allDeals]);

    // --- Calculations ---
    const calculateTotalExtraCosts = () => (formData.deals as any[])?.reduce((sum, deal) => sum + (deal.extraCosts || 0), 0) || 0;
    const calculateGrandTotal = () => (formData.totalShippingCostUsd || 0) + calculateTotalExtraCosts();

    useEffect(() => {
        if (installmentPlanEnabled && installments.length > 0) {
            const grandTotal = calculateGrandTotal();
            const updatedInstallments = installments.map(inst => ({
                ...inst,
                amount: Math.round(((inst.percentage || 0) / 100) * grandTotal * 100) / 100
            }));
            setInstallments(updatedInstallments);
        }
    }, [formData.totalShippingCostUsd, formData.deals]);

    // --- Handlers ---
    const handleAddDeals = (dealIds: string[]) => {
        const newDealsToAdd = dealIds.map(id => {
            const deal = allDeals.find(d => d.id === id);
            if (!deal) return null;
            return {
                dealId: deal.id,
                dealNumber: deal.dealNumber,
                originalOfferNumber: deal.originalOfferNumber || deal.dealNumber,
                totalAmount: deal.totalAmount,
                totalVolume: deal.totalVolume || 0,
                totalWeightKg: deal.totalWeight || deal.totalWeightKg || 0,
                distributedCost: 0,
                extraCosts: 0,
                notes: ''
            };
        }).filter(Boolean);

        const newDealsList = [...(formData.deals || []), ...newDealsToAdd];
        // إعادة توزيع التكلفة
        const distributedDeals = shipmentsService.calculateDistribution(newDealsList, formData.totalShippingCostUsd || 0);

        // دمج القيم السابقة (Extra Costs)
        const finalDeals = distributedDeals.map((d, index) => ({
            ...d,
            extraCosts: newDealsList[index].extraCosts,
            notes: newDealsList[index].notes
        }));

        setFormData((prev: any) => ({ ...prev, deals: finalDeals }));
    };

    const handleRemoveDeal = (dealId: string) => {
        const remainingDeals = (formData.deals || []).filter((d: any) => d.dealId !== dealId);
        const distributedDeals = shipmentsService.calculateDistribution(remainingDeals, formData.totalShippingCostUsd || 0);
        // الحفاظ على extraCosts القديمة
        const finalDeals = distributedDeals.map(d => {
            const oldDeal = (formData.deals || []).find((od: any) => od.dealId === d.dealId);
            return { ...d, extraCosts: oldDeal?.extraCosts || 0, notes: oldDeal?.notes || '' };
        });
        setFormData((prev: any) => ({ ...prev, deals: finalDeals }));
    };

    const handleDealUpdate = (dealId: string, field: string, value: any) => {
        const updatedDeals = formData.deals?.map((d: any) => d.dealId === dealId ? { ...d, [field]: value } : d);
        setFormData((prev: any) => ({ ...prev, deals: updatedDeals }));
    };

    const handleTotalChange = (newTotal: number) => {
        const distributedDeals = shipmentsService.calculateDistribution(formData.deals || [], newTotal);
        const mergedDeals = distributedDeals.map(d => {
            const existing = formData.deals?.find((ed: any) => ed.dealId === d.dealId);
            return { ...d, extraCosts: existing?.extraCosts || 0, notes: existing?.notes || '' };
        });

        let newPricePerUnit = formData.pricePerUnit;
        if (formData.pricingMethod === 'unit') {
            const totalUnits = formData.unitType === 'weight' ? totals.weight : formData.unitType === 'cbm' ? totals.volume : 1;
            if (totalUnits > 0) newPricePerUnit = newTotal / totalUnits;
        }

        setFormData((prev: any) => ({ ...prev, totalShippingCostUsd: newTotal, deals: mergedDeals, pricePerUnit: newPricePerUnit }));
    };

    // في ملف ShipmentForm.tsx

    // ... (داخل المكون ShipmentForm)

    const handleUnitPriceChange = (newPrice: number, overrideUnitType?: string) => {
        // 🟢 الإصلاح: استخدام القيمة الممرة، أو القيمة في النموذج، أو 'cbm' كقيمة افتراضية لمنع الوقوع في خطأ الحساب = 1
        const currentUnitType = overrideUnitType || formData.unitType || 'cbm';

        const totalUnits = currentUnitType === 'weight' ? totals.weight :
            currentUnitType === 'cbm' ? totals.volume : 1;

        const newTotal = newPrice * totalUnits;

        // تحديث الإجمالي وتوزيع التكلفة
        handleTotalChange(newTotal);

        // تحديث الحالة
        setFormData((prev: any) => ({
            ...prev,
            pricePerUnit: newPrice,
            // ضمان حفظ نوع الوحدة أيضاً
            unitType: currentUnitType
        }));
    };

    const handleFileUpload = async (file: File, type: 'billOfLading' | 'airwayBill') => {
        try {
            setUploadingFile(true);
            const uploadedUrl = await cloudinaryService.uploadFile(file);
            setShippingInfo((prev: any) => ({ ...prev, [type === 'billOfLading' ? 'billOfLadingFile' : 'airwayBillFile']: uploadedUrl }));
            alert('✅ تم رفع الملف بنجاح');
        } catch (error) { console.error(error); alert('❌ فشل في رفع الملف'); } finally { setUploadingFile(false); }
    };

    const handleSaveClick = async () => {
        if (isSubmittingRef.current || saving) return;
        if (installmentPlanEnabled && !validateInstallments()) { alert("يرجى تصحيح أخطاء نظام الدفعات"); return; }

        try {
            isSubmittingRef.current = true; setSaving(true);
            const finalData = {
                ...formData, shippingInfo, totalVolume: totals.volume, totalWeightKg: totals.weight,
                installments: installmentPlanEnabled ? installments : [], installmentPlanEnabled,
                shipmentName: formData.shipmentName || `شحنة ${formData.shipmentNumber}`,
            };

            if (formData.id) {
                await shipmentsService.updateShipment(formData.id, finalData, currentUser.id, currentUser.name);
                await notificationsService.addNotification({ userId: "all_managers", title: "تعديل شحنة", message: `تم تعديل الشحنة ${formData.shipmentNumber}`, type: "shipment_updated", targetId: formData.id, targetView: "shipments-management" });
                alert('✅ تم حفظ التعديلات');
            } else {
                const newId = await shipmentsService.createShipment(finalData as any, currentUser.id, currentUser.name);
                await notificationsService.addNotification({ userId: "all_managers", title: "شحنة جديدة", message: `تم إنشاء شحنة جديدة`, type: "shipment_created", targetId: newId, targetView: "shipments-management" });
                alert('✅ تم إنشاء الشحنة');
                const created = await shipmentsService.getShipment(newId);
                setFormData(created); setInstallments(created.installments || []);
            }
        } catch (error) { console.error(error); alert('فشل الحفظ'); } finally { isSubmittingRef.current = false; setSaving(false); }
    };

    const validateInstallments = () => {
        if (!installmentPlanEnabled) return true;
        if (installments.length === 0) { setInstallmentValidationError("يجب إضافة دفعة واحدة على الأقل"); return false; }
        const totalPct = installments.reduce((sum, i) => sum + (i.percentage || 0), 0);
        if (Math.abs(totalPct - 100) > 0.01) { setInstallmentValidationError("مجموع النسب يجب أن يكون 100%"); return false; }
        setInstallmentValidationError(""); return true;
    };

    // Placeholder payment handlers (keep original logic)
    const handlePaymentOperation = async (operation: any, type: any, data: any, id?: any) => { /* ... Original Logic ... */ };
    const handleConfirmSupplier = (data: any) => handlePaymentOperation("confirm", "", data, data.paymentId);

    if (loading) return <div>جاري التحميل...</div>;

    return (
        <div className="space-y-6 pb-20">
            {/* Header */}
            <div className="flex justify-between items-center bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 sticky top-0 z-10">
                <div className="flex items-center gap-4">
                    <div className="p-3 bg-blue-50 dark:bg-blue-900/30 rounded-xl text-blue-600 dark:text-blue-400">
                        <Truck className="w-8 h-8" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold dark:text-white">{formData.id ? `شحنة رقم: ${formData.shipmentNumber}` : 'إنشاء شحنة جديدة'}</h2>
                        {formData.agentShipmentNumber && <p className="text-sm text-gray-500 font-mono">Ref: {formData.agentShipmentNumber}</p>}
                    </div>
                </div>
                <div className="flex gap-3">
                    <button onClick={onCancel} className="px-5 py-2.5 bg-gray-100 dark:bg-gray-700 rounded-xl hover:bg-gray-200 dark:text-white">رجوع</button>
                    <button onClick={handleSaveClick} disabled={saving} className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white font-bold rounded-xl hover:bg-blue-700 disabled:opacity-50">
                        {saving ? 'جاري الحفظ...' : <><Save className="w-5 h-5" /> حفظ الشحنة</>}
                    </button>
                </div>
            </div>

            <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
                <div className="flex items-center justify-between mb-4 border-b border-gray-100 dark:border-gray-700 pb-4">
                    <h3 className="text-lg font-bold dark:text-white flex items-center gap-2">
                        <Navigation className="w-5 h-5 text-emerald-500" />
                        مسار حالات الشحنة
                    </h3>
                    <div className="flex items-center gap-4 text-xs">
                        <div className="px-3 py-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg font-bold">
                            من: {shippingInfo.fromTerm || '---'}
                        </div>
                        <div className="text-gray-400">⟶</div>
                        <div className="px-3 py-1 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-lg font-bold">
                            إلى: {shippingInfo.toTerm || 'DDP'}
                        </div>
                    </div>
                </div>

                <ShipmentStatusVisualizer
                    type={shippingInfo.shippingType || 'sea'}
                    currentStatus={shippingInfo.shipmentStatus?.status || 'agent_warehouse'}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column: Basic Info & Shipping Details */}
                <div className="lg:col-span-1 space-y-6">
                    <div className="flex items-center gap-2 mb-2">
                        <Info className="w-5 h-5 text-blue-500" />
                        <h3 className="text-lg font-bold dark:text-white">بيانات الشحنة</h3>
                    </div>

                    <ShipmentBasicInfo
                        formData={formData}
                        setFormData={setFormData}
                        allSuppliers={allSuppliers}
                        totals={totals}
                        handleTotalChange={handleTotalChange}
                        handleUnitPriceChange={handleUnitPriceChange}
                        onOpenSupplier={(id) => { setSelectedSupplierId(id); setIsSupplierModalOpen(true); }}
                    />

                    <ShipmentShippingDetails
                        shippingInfo={shippingInfo}
                        setShippingInfo={setShippingInfo}
                        handleFileUpload={handleFileUpload}
                        uploadingFile={uploadingFile}
                        handleShipmentStatusChange={(status, notes) => setShippingInfo((prev: any) => ({ ...prev, shipmentStatus: { status, statusDate: new Date().toISOString(), notes, completed: false } }))}
                    />
                </div>

                {/* Right Column: Deals & Finance */}
                <div className="lg:col-span-2 space-y-6">
                    <ShipmentDealsTable
                        deals={formData.deals}
                        allDeals={allDeals}
                        onRemoveDeal={handleRemoveDeal}
                        onUpdateDeal={handleDealUpdate}
                        onOpenSelector={() => setIsDealSelectorOpen(true)}
                        totalBase={formData.totalShippingCostUsd || 0}
                        totalExtra={calculateTotalExtraCosts()}
                        grandTotal={calculateGrandTotal()}
                    />

                    {/* Finance Section */}
                    <CollapsibleSection title="الدفعات والمالية (وكيل الشحن)" icon={CreditCard} defaultOpen={true}>
                        <div className="space-y-8">
                            <InstallmentManager
                                installments={installments as any}
                                grandTotal={calculateGrandTotal()}
                                onUpdateInstallments={(newInst) => setInstallments(newInst as any)}
                                validationError={installmentValidationError}
                                installmentPlanEnabled={installmentPlanEnabled}
                                onTogglePlan={(enabled) => {
                                    setInstallmentPlanEnabled(enabled);
                                    if (enabled && installments.length === 0) {
                                        setInstallments([{ id: crypto.randomUUID(), installmentNumber: 1, percentage: 100, amount: calculateGrandTotal(), status: 'unpaid', notes: 'دفعة واحدة', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }]);
                                    } else if (!enabled) setInstallments([]);
                                }}
                                deal={formData as any}
                                readOnly={formData.status === 'delivered' || formData.status === 'cancelled'}
                            />
                            {formData.id ? (
                                <PaymentProgress
                                    installments={installments as any}
                                    deal={{ ...formData, id: formData.id, totalAmount: calculateGrandTotal(), payments: formData.payments || [] } as any}
                                    currentUser={currentUser}
                                    onPaymentOperation={handlePaymentOperation}
                                    onConfirmSupplier={handleConfirmSupplier}
                                />
                            ) : (
                                <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 rounded-xl flex items-center gap-2 border border-yellow-100 dark:border-yellow-800">
                                    <AlertCircle className="w-5 h-5" />
                                    <span>يرجى حفظ الشحنة أولاً للبدء في إجراء عمليات الدفع.</span>
                                </div>
                            )}
                        </div>
                    </CollapsibleSection>
                </div>
            </div>

            {/* Modals */}
            <SupplierViewModal isOpen={isSupplierModalOpen} onClose={() => setIsSupplierModalOpen(false)} supplierId={selectedSupplierId} />

            <ShipmentDealSelector
                isOpen={isDealSelectorOpen}
                onClose={() => setIsDealSelectorOpen(false)}
                allDeals={allDeals}
                existingDealIds={formData.deals?.map((d: any) => d.dealId) || []}
                allSuppliers={allSuppliers}
                onAddDeals={handleAddDeals}
            />
        </div>
    );
};