import React, { useState, useEffect, useRef } from 'react';
import { Shipment, Supplier, Deal, DealPayment, User, ShipmentInstallment } from '../../../types';
import { maxPaymentPrincipalForDeal } from '@/utils/dealPaymentLimits';
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
    /** يُستدعى بعد حفظ ناجح — `shipmentId` يُمرَّر عند الإنشاء أو التحديث لتحديث الراوت */
    onSave?: (shipmentId: string) => void;
    currentUser: User;
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
}

export const ShipmentForm: React.FC<ShipmentFormProps> = ({
    shipment,
    onCancel,
    onSave,
    currentUser,
    onOpenAccountingJournal,
}) => {
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
        shipmentStatus: {
            status: 'agent_warehouse',
            statusDate: new Date().toISOString(),
            completed: false,
            notes: '',
        },
        ...(shipment as any)?.shippingInfo,
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
    const [paymentBusy, setPaymentBusy] = useState(false);
    const isSubmittingRef = useRef(false);
    const [totals, setTotals] = useState({ weight: 0, volume: 0 });
    const [uploadingFile, setUploadingFile] = useState(false);
    const linkedDealIdsRef = useRef<string[]>([]);
    linkedDealIdsRef.current = (formData.deals || []).map((d: any) => String(d.dealId));

    // --- Effects ---
    useEffect(() => {
        const unsubSuppliers = suppliersService.subscribeToSuppliers((suppliers) => {
            setAllSuppliers(suppliers.filter(s => s.type === 'shipping_agent'));
        });
        const unsubDeals = dealsService.subscribeToDeals((deals) => {
            const linked = linkedDealIdsRef.current;
            // مرتبطة بالشحنة: تبقى للعرض/التعديل. للإضافة الجديدة: فقط وضع الشحنة
            // «تم الشحن للوكيل وبانتظار الشحن الدولي» (sw_wait_intl_ship).
            setAllDeals(
                deals.filter((d) => {
                    if (linked.includes(String(d.id))) return true;
                    return d.shippingWorkflowStatus === "sw_wait_intl_ship";
                })
            );
        });
        setLoading(false);
        return () => { unsubSuppliers(); unsubDeals(); };
    }, []);

    // مزامنة حقول الصفقة من SQL مع صفوف الشحنة، ثم إعادة توزيع تكلفة الشحن على الصفوف
    // (سابقاً كان التوزيع يُعاد فقط عند تغيّر الحجم فقط؛ فيبقى allocated صفراً من الـ API رغم وجود إجمالي شحن)
    useEffect(() => {
        if (!allDeals.length) return;
        setFormData((prev: any) => {
            const rows = prev.deals || [];
            if (!rows.length) return prev;
            const merged = rows.map((d: any) => {
                const live = allDeals.find((ad) => String(ad.id) === String(d.dealId));
                if (!live) return d;
                const nextVol = Number(live.totalVolume || 0);
                const nextW = Number(live.totalWeightKg ?? live.totalWeight ?? 0);
                return {
                    ...d,
                    dealNumber: live.dealNumber,
                    originalOfferNumber: live.originalOfferNumber || live.dealNumber,
                    totalAmount: live.totalAmount,
                    totalVolume: nextVol,
                    totalWeightKg: nextW,
                };
            });
            const withDist = shipmentsService
                .calculateDistribution(merged, prev.totalShippingCostUsd || 0, {
                    pricingMethod: prev.pricingMethod,
                    unitType: prev.unitType,
                })
                .map((x: any, i: number) => ({
                    ...x,
                    extraCosts: merged[i]?.extraCosts ?? 0,
                    notes: merged[i]?.notes ?? "",
                }));
            const unchanged =
                withDist.length === rows.length &&
                withDist.every((n: any, i: number) => {
                    const o = rows[i];
                    if (!o || String(n.dealId) !== String(o.dealId)) return false;
                    return (
                        n.distributedCost === o.distributedCost &&
                        n.extraCosts === o.extraCosts &&
                        n.notes === o.notes &&
                        n.totalVolume === o.totalVolume &&
                        n.totalWeightKg === o.totalWeightKg &&
                        n.totalAmount === o.totalAmount &&
                        n.dealNumber === o.dealNumber &&
                        n.originalOfferNumber === o.originalOfferNumber
                    );
                });
            if (unchanged) return prev;
            return { ...prev, deals: withDist };
        });
    }, [allDeals]);

    // تحديث المجاميع من صفوف الشحنة (ولا نربطها بتحميل allDeals — وإلا يبقى الحجم 0 حتى يصل الاشتراك)
    useEffect(() => {
        if (!formData.deals?.length) {
            setTotals({ weight: 0, volume: 0 });
            return;
        }
        let totalW = 0, totalV = 0;
        const dealShippingTerms: string[] = [];
        formData.deals.forEach((d: any) => {
            const originalDeal = allDeals.find(ad => String(ad.id) === String(d.dealId));
            totalW += Number(originalDeal?.totalWeightKg ?? originalDeal?.totalWeight ?? d.totalWeightKg ?? 0);
            totalV += Number(originalDeal?.totalVolume ?? d.totalVolume ?? 0);
            if (originalDeal?.shippingMethod) dealShippingTerms.push(originalDeal.shippingMethod);
        });
        setTotals({ weight: totalW, volume: totalV });
        if (dealShippingTerms.length > 0) {
            const latest = getLatestShippingTerm(dealShippingTerms);
            setShippingInfo((prev: any) => ({ ...prev, fromTerm: latest, toTerm: prev.toTerm || 'DDP' }));
        }
    }, [formData.deals, allDeals]);

    // تسعير بالوحدة: عند وصول/تحديث الحجم أو الوزن، ضرب سعر الوحدة × عدد الوحدات (يتفادى بقاء 0 بعد إدخال السعر مبكراً)
    useEffect(() => {
        if (formData.pricingMethod !== 'unit') return;
        const unitPrice = Number(formData.pricePerUnit) || 0;
        if (unitPrice <= 0) return;
        const ut = formData.unitType || 'cbm';
        const totalUnits =
            ut === 'weight' ? totals.weight : ut === 'cbm' ? totals.volume : 1;
        if (totalUnits <= 0) return;
        const newTotal = Math.round(unitPrice * totalUnits * 100) / 100;
        const cur = Number(formData.totalShippingCostUsd) || 0;
        if (Math.abs(cur - newTotal) < 0.005) return;

        const distributedDeals = shipmentsService.calculateDistribution(
            formData.deals || [],
            newTotal,
            { pricingMethod: formData.pricingMethod, unitType: formData.unitType }
        );
        const mergedDeals = distributedDeals.map((d) => {
            const existing = formData.deals?.find((ed: any) => ed.dealId === d.dealId);
            return { ...d, extraCosts: existing?.extraCosts || 0, notes: existing?.notes || '' };
        });
        setFormData((prev: any) => ({
            ...prev,
            totalShippingCostUsd: newTotal,
            deals: mergedDeals,
            pricePerUnit: totalUnits > 0 ? newTotal / totalUnits : prev.pricePerUnit,
        }));
    }, [
        formData.pricingMethod,
        formData.unitType,
        formData.pricePerUnit,
        totals.weight,
        totals.volume,
    ]);

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
        const distributedDeals = shipmentsService.calculateDistribution(
            newDealsList,
            formData.totalShippingCostUsd || 0,
            { pricingMethod: formData.pricingMethod, unitType: formData.unitType }
        );

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
        const distributedDeals = shipmentsService.calculateDistribution(
            remainingDeals,
            formData.totalShippingCostUsd || 0,
            { pricingMethod: formData.pricingMethod, unitType: formData.unitType }
        );
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
        const distributedDeals = shipmentsService.calculateDistribution(
            formData.deals || [],
            newTotal,
            { pricingMethod: formData.pricingMethod, unitType: formData.unitType }
        );
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
            const grandSave = (formData.totalShippingCostUsd || 0) + calculateTotalExtraCosts();
            const planForSave = installmentPlanEnabled || grandSave > 0.005;
            const finalData = {
                ...formData, shippingInfo, totalVolume: totals.volume, totalWeightKg: totals.weight,
                installments: planForSave ? installments : [],
                installmentPlanEnabled: planForSave,
                shipmentName: formData.shipmentName || `شحنة ${formData.shipmentNumber}`,
            };

            if (formData.id) {
                await shipmentsService.updateShipment(formData.id, finalData, currentUser.id, currentUser.name);
                for (const row of finalData.deals || []) {
                    if (row?.dealId) {
                        await shipmentsService.addDealToShipment(String(formData.id), String(row.dealId));
                    }
                }
                await notificationsService.addNotification({ userId: "all_managers", title: "تعديل شحنة", message: `تم تعديل الشحنة ${formData.shipmentNumber}`, type: "shipment_updated", targetId: formData.id, targetView: "shipments-management" });
                alert('✅ تم حفظ التعديلات');
                onSave?.(String(formData.id));
            } else {
                const newId = await shipmentsService.createShipment(finalData as any, currentUser.id, currentUser.name);
                for (const row of finalData.deals || []) {
                    if (row?.dealId) {
                        await shipmentsService.addDealToShipment(String(newId), String(row.dealId));
                    }
                }
                await notificationsService.addNotification({ userId: "all_managers", title: "شحنة جديدة", message: `تم إنشاء شحنة جديدة`, type: "shipment_created", targetId: newId, targetView: "shipments-management" });
                alert('✅ تم إنشاء الشحنة');
                const created = await shipmentsService.getShipment(newId);
                setFormData(created); setInstallments(created.installments || []);
                onSave?.(String(newId));
            }
        } catch (error) { console.error(error); alert('فشل الحفظ'); } finally { isSubmittingRef.current = false; setSaving(false); }
    };

    const validateInstallments = () => {
        const grand = (formData.totalShippingCostUsd || 0) + calculateTotalExtraCosts();
        const planRequired = installmentPlanEnabled || grand > 0.005;
        if (!planRequired) {
            setInstallmentValidationError("");
            return true;
        }
        if (installments.length === 0) {
            setInstallmentValidationError("يجب أن يظهر جدول دفعات (دفعة واحدة على الأقل) — راجع إجمالي الشحنة");
            return false;
        }
        const totalPct = installments.reduce((sum, i) => sum + (i.percentage || 0), 0);
        if (Math.abs(totalPct - 100) > 0.01) {
            setInstallmentValidationError("مجموع النسب يجب أن يكون 100%");
            return false;
        }
        setInstallmentValidationError("");
        return true;
    };

    const payCapData = (): Partial<Deal> => ({
        totalAmount: calculateGrandTotal(),
        payments: formData.payments || [],
    });

    const shipmentPaymentSync = () => ({
        totalShippingCostUsd: formData.totalShippingCostUsd,
        deals: formData.deals as Shipment['deals'],
    });

    const handlePaymentOperation = async (
        operation:
            | "claim"
            | "swift"
            | "add"
            | "confirm"
            | "cancel"
            | "linkJournal",
        paymentType: string,
        data: any,
        paymentId?: string
    ) => {
        if (!formData.id) {
            alert("يرجى حفظ الشحنة أولاً");
            return;
        }
        const cleanData = (x: any) =>
            Object.fromEntries(Object.entries(x || {}).filter(([_, v]) => v !== undefined));

        let confirmAccountingMeta: { journalId?: number; message: string; openManualJournal?: boolean } | undefined;
        let lastConfirmPaymentId: string | undefined;
        let swiftAutoPostJournalId: number | undefined;

        try {
            setPaymentBusy(true);
            switch (operation) {
                case "add": {
                    const addAmt = Number(data?.amount ?? 0);
                    const capAdd = maxPaymentPrincipalForDeal(payCapData());
                    if (addAmt > capAdd + 1e-6) {
                        alert(`لا يُسمح بدفع يتجاوز تكلفة الشحن. الأقصى المتاح: $${capAdd.toLocaleString()}`);
                        return;
                    }
                    await shipmentsService.addShipmentAgentPayment(
                        formData.id,
                        {
                            ...cleanData(data),
                            type: paymentType,
                            paymentDate: new Date().toISOString(),
                            confirmedBySupplier: false,
                        } as Omit<DealPayment, "id">,
                        shipmentPaymentSync()
                    );
                    break;
                }
                case "claim": {
                    const claimAmt = Number(data?.amount ?? 0);
                    const capClaim = maxPaymentPrincipalForDeal(payCapData());
                    if (claimAmt > capClaim + 1e-6) {
                        alert(
                            `لا يُسمح بالمطالبة فوق تكلفة الشحن. الأقصى المتاح: $${capClaim.toLocaleString()}`
                        );
                        return;
                    }
                    await shipmentsService.addShipmentAgentPayment(
                        formData.id,
                        {
                            ...cleanData(data),
                            type: paymentType,
                            paymentDate: new Date().toISOString(),
                            confirmedBySupplier: false,
                        } as Omit<DealPayment, "id">,
                        shipmentPaymentSync()
                    );
                    break;
                }
                case "swift": {
                    let payment = formData.payments?.find((p) => p.type === paymentType);
                    let swiftPaymentId = paymentId;

                    if (!swiftPaymentId) {
                        if (!payment) {
                            const swiftAmt = Number(data.amount ?? 0);
                            const capSwift = maxPaymentPrincipalForDeal(payCapData());
                            if (swiftAmt > capSwift + 1e-6) {
                                alert(
                                    `لا يُسمح بدفع يتجاوز تكلفة الشحن. الأقصى المتاح: $${capSwift.toLocaleString()}`
                                );
                                return;
                            }
                            await shipmentsService.addShipmentAgentPayment(
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
                                },
                                shipmentPaymentSync()
                            );
                            const fresh = await shipmentsService.getShipment(formData.id);
                            const instNo = Number(data.installmentNumber ?? 0);
                            payment =
                                fresh.payments?.find((p) => p.type === paymentType) ||
                                (instNo > 0
                                    ? fresh.payments?.find(
                                          (p) => Number(p.installmentNumber) === instNo
                                      )
                                    : undefined) ||
                                fresh.payments?.slice(-1)[0];
                            swiftPaymentId = payment?.id;
                        } else {
                            swiftPaymentId = payment.id;
                        }
                    }

                    if (!swiftPaymentId) {
                        alert("تعذر إنشاء أو العثور على سجل الدفعة");
                        return;
                    }

                    if (!data.cashBoxId) {
                        alert("يجب اختيار صندوق مالي لتنفيذ عملية الدفع");
                        return;
                    }

                    if (!data.bankSwiftImage) {
                        alert("يجب رفع صورة السليب أولاً");
                        return;
                    }

                    const swiftPrincipal = Number(data.amount ?? 0);
                    const capSwiftEdit = maxPaymentPrincipalForDeal(payCapData(), swiftPaymentId);
                    if (swiftPrincipal > capSwiftEdit + 1e-6) {
                        alert(
                            `لا يُسمح بمبلغ يتجاوز تكلفة الشحن. الأقصى المسموح: $${capSwiftEdit.toLocaleString()}`
                        );
                        return;
                    }

                    const totalPayment = (data.amount || 0) + (data.transferCost || 0);
                    if (!window.confirm(`هل أنت متأكد من خصم ${totalPayment.toLocaleString()} $ من الصندوق المحدد؟`)) {
                        return;
                    }

                    try {
                        await shipmentsService.updateShipmentAgentPaymentWithSwift(
                            formData.id,
                            swiftPaymentId,
                            cleanData({
                                ...data,
                                dealNumber: formData.shipmentNumber,
                            }),
                            shipmentPaymentSync()
                        );
                        const postTry =
                            await shipmentsService.tryAutoPostShipmentAgentPaymentAccounting(
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
                        } else if (postTry.blockers?.length) {
                            const b = postTry.blockers.join("\n");
                            console.warn("Shipment payment accounting:", b);
                            alert(
                                `لم يُنشأ قيد المحاسبة تلقائياً:\n\n${b}\n\n` +
                                    `تحقق من: ربط الصندوق بحساب GL، ربط وكيل الشحن بحساب دائن، وحفظ إجمالي الشحن إن لزم. يمكنك لاحقاً «ربط قيد» يدوياً.`
                            );
                        }
                    } catch (error: any) {
                        if (error?.message?.includes("الرصيد غير كافي")) {
                            alert(`❌ ${error.message}`);
                            throw error;
                        }
                        throw error;
                    }
                    break;
                }
                case "linkJournal": {
                    if (!paymentId) {
                        alert("معرّف الدفعة مفقود.");
                        return;
                    }
                    const jid = Number(data?.journalId);
                    if (!Number.isFinite(jid) || jid <= 0) {
                        alert("رقم القيد غير صالح.");
                        return;
                    }
                    await shipmentsService.linkShipmentAgentPaymentJournal(
                        String(formData.id),
                        String(paymentId),
                        jid
                    );
                    break;
                }
                case "confirm":
                    if (paymentId) {
                        lastConfirmPaymentId = paymentId;
                        const paymentToConfirm = formData.payments?.find((p) => p.id === paymentId);

                        if (paymentToConfirm) {
                            if (paymentToConfirm.bankSwiftImage && !paymentToConfirm.cashBoxId) {
                                alert("⚠️ هذه الدفعة تحتوي على سليب ولكن لم يتم خصمها من الصندوق بعد");
                                return;
                            }
                            if (paymentToConfirm.cashBoxId && !paymentToConfirm.bankSwiftImage) {
                                alert("⚠️ تم خصم المبلغ من الصندوق ولكن لم يتم رفع صورة السليب");
                                return;
                            }
                        }

                        confirmAccountingMeta = await shipmentsService.confirmShipmentAgentPayment(
                            formData.id,
                            paymentId,
                            data.supplierConfirmationImage,
                            data.supplierNotes,
                            data.paymentConfirmationDate,
                            data.cashBoxId
                        );
                    }
                    break;

                case "cancel":
                    if (paymentId) {
                        const paymentToCancel = formData.payments?.find((p) => p.id === paymentId);
                        if (paymentToCancel?.isPosted) {
                            alert("لا يمكن إلغاء دفعة مرحّلة محاسبياً من هنا.");
                            return;
                        }
                        if (paymentToCancel?.cashBoxWithdrawalAt) {
                            if (
                                !window.confirm(
                                    "⚠️ هذه الدفعة تم خصمها بالفعل من الصندوق. هل تريد حقاً إلغاءها؟"
                                )
                            ) {
                                return;
                            }
                        }
                        await shipmentsService.cancelShipmentAgentPayment(formData.id, paymentId);
                    }
                    break;
            }

            const loadedAfterPay = await shipmentsService.getShipment(formData.id);
            setFormData((prev: any) => ({
                ...loadedAfterPay,
                installments: prev.installments,
                installmentPlanEnabled: prev.installmentPlanEnabled,
            }));

            switch (operation) {
                case "swift":
                    if (swiftAutoPostJournalId != null) {
                        alert(
                            "✅ تم تنفيذ الدفع ورفع السليب، وتم إنشاء قيد المحاسبة وربطه بالدفعة."
                        );
                        onOpenAccountingJournal?.(swiftAutoPostJournalId, {
                            dealId: String(formData.id),
                            dealNumber: String(formData.shipmentNumber || ""),
                            displayName: [
                                "شحنة",
                                formData.shipmentNumber || formData.id,
                                formData.shipmentName || "",
                            ]
                                .filter(Boolean)
                                .join(" — "),
                        });
                    } else {
                        alert("✅ تم تنفيذ الدفع ورفع السليب بنجاح");
                    }
                    break;
                case "linkJournal":
                    alert(
                        "✅ تم ربط الدفعة بالقيد. سيظهر «فتح في المحاسبة» في سجل المدفوعات بعد التحديث."
                    );
                    break;
                case "claim":
                    alert("✅ تم رفع المطالبة. يمكنك متابعة تسجيل الدفع لاحقاً.");
                    break;
                case "confirm":
                    alert(confirmAccountingMeta?.message || "✅ تم تأكيد المورد وحفظ البيانات.");
                    break;
                case "cancel":
                    alert("✅ تم إلغاء الدفعة من سجل الشحنة");
                    break;
                default:
                    alert("تم حفظ العملية بنجاح");
            }
        } catch (error: any) {
            console.error("Shipment payment error:", error);
            alert(`❌ ${error?.message || "حدث خطأ أثناء حفظ الدفعة"}`);
        } finally {
            setPaymentBusy(false);
        }
    };

    const handleConfirmSupplier = (data: any) =>
        handlePaymentOperation("confirm", "", data, data.paymentId);

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
                        totalExtra={calculateTotalExtraCosts()}
                        grandTotal={calculateGrandTotal()}
                    />

                    {/* Finance Section */}
                    <CollapsibleSection title="المالية — خطة الدفع وتنفيذ التحويل" icon={CreditCard} defaultOpen={true}>
                        <div className="space-y-6">
                            <InstallmentManager
                                variant="shipment"
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
                                    variant="shipment"
                                    currentUser={currentUser}
                                    onPaymentOperation={handlePaymentOperation}
                                    onConfirmSupplier={handleConfirmSupplier}
                                    onOpenAccountingJournal={onOpenAccountingJournal}
                                    readOnly={
                                        formData.status === "delivered" ||
                                        formData.status === "cancelled"
                                    }
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