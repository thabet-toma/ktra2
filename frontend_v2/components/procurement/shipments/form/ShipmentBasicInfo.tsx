import React, { useEffect } from 'react';
import { UserCircle, Hash, Eye, DollarSign } from 'lucide-react';
import { Supplier } from '../../../../types';

interface ShipmentBasicInfoProps {
    formData: any;
    setFormData: (data: any) => void;
    allSuppliers: Supplier[];
    totals: { weight: number, volume: number };
    handleTotalChange: (total: number) => void;
    handleUnitPriceChange: (price: number, unitType?: string) => void;
    onOpenSupplier: (id: string) => void;
}

export const ShipmentBasicInfo: React.FC<ShipmentBasicInfoProps> = ({
    formData, setFormData, allSuppliers, totals, handleTotalChange, handleUnitPriceChange, onOpenSupplier
}) => {

    // إعادة حساب عند تغيير نوع الوحدة أو أسلوب التسعير — «إجمالي» يعيد توزيع المبلغ الحالي على الصفقات
    useEffect(() => {
        if (formData.pricingMethod === 'unit' && formData.pricePerUnit > 0) {
            handleUnitPriceChange(formData.pricePerUnit, formData.unitType);
        } else if (formData.pricingMethod === 'total') {
            handleTotalChange(Number(formData.totalShippingCostUsd) || 0);
        }
    }, [formData.unitType, formData.pricingMethod]);

    return (
        <div className="aseel-bg-field dark:aseel-bg-panel p-6 rounded-2xl shadow-sm border aseel-border-soft dark:aseel-border-soft space-y-4">
            {/* ... (الحقول العلوية: الرقم التسلسلي، رقم الشحنة، الطرف الإسرائيلي... تبقى كما هي) ... */}
            {formData.id && (
                <div className="p-3 aseel-bg-panel dark:aseel-bg-panel rounded-xl flex justify-between items-center border border-dashed aseel-border-soft dark:aseel-border-soft">
                    <span className="text-sm aseel-text-soft">الرقم التسلسلي:</span>
                    <span className="font-mono font-bold aseel-text-ink dark:aseel-text-soft">{formData.shipmentNumber}</span>
                </div>
            )}

            <div>
                <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft mb-1">رقم الشحنة (لدى الوكيل / البوليصة)</label>
                <div className="relative">
                    <Hash className="absolute left-3 top-1/2 -translate-y-1/2 aseel-text-soft w-4 h-4" />
                    <input
                        type="text"
                        value={formData.agentShipmentNumber || ''}
                        onChange={(e) => setFormData((prev: any) => ({ ...prev, agentShipmentNumber: e.target.value }))}
                        className="w-full p-3 pl-10 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                        placeholder="Ref Number..."
                    />
                </div>
            </div>

            <div>
                <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft mb-1">الطرف الإسرائيلي</label>
                <div className="relative">
                    <UserCircle className="absolute left-3 top-1/2 -translate-y-1/2 aseel-text-soft w-5 h-5" />
                    <input
                        type="text"
                        value={formData.israeliSideName || ''}
                        onChange={(e) => setFormData((prev: any) => ({ ...prev, israeliSideName: e.target.value }))}
                        className="w-full p-3 pl-10 aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl"
                        placeholder="الاسم..."
                    />
                </div>
            </div>

            <div>
                <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft mb-1">اسم تعريفي (اختياري)</label>
                <input
                    type="text"
                    value={formData.shipmentName || ''}
                    onChange={(e) => setFormData((prev: any) => ({ ...prev, shipmentName: e.target.value }))}
                    className="w-full p-3 aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl"
                    placeholder="مثال: حاوية إلكترونيات - دفعة 1"
                />
            </div>

            <div>
                <label className="block text-sm font-medium aseel-text-ink dark:aseel-text-soft mb-1">وكيل الشحن <span className="aseel-text-soft">*</span></label>
                <div className="flex gap-2">
                    <select
                        required
                        value={formData.shippingAgentId || ''}
                        onChange={(e) => {
                            const agent = allSuppliers.find(s => s.id === e.target.value);
                            setFormData((prev: any) => ({ ...prev, shippingAgentId: e.target.value, shippingAgentName: agent?.tradeName || '' }));
                        }}
                        className="w-full p-3 aseel-bg-panel dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-xl"
                    >
                        <option value="">اختر وكيل شحن</option>
                        {allSuppliers.map(s => <option key={s.id} value={s.id}>{s.tradeName}</option>)}
                    </select>
                    {formData.shippingAgentId && (
                        <button type="button" onClick={() => onOpenSupplier(formData.shippingAgentId)} className="p-3 aseel-bg-accent-bg hover:aseel-bg-accent-bg rounded-xl aseel-text-accent">
                            <Eye className="w-5 h-5" />
                        </button>
                    )}
                </div>
            </div>

            <hr className="aseel-border-soft dark:aseel-border-soft" />

            {/* Pricing Section */}
            <div className="aseel-bg-accent-bg dark:aseel-bg-panel/10 p-4 rounded-xl border aseel-border-soft dark:aseel-border-soft">
                <div className="flex gap-2 mb-3">
                    <button type="button" onClick={() => setFormData((prev: any) => ({ ...prev, pricingMethod: 'total' }))}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${formData.pricingMethod === 'total' ? 'aseel-bg-accent text-white shadow-md' : 'aseel-text-accent aseel-bg-field/50 dark:aseel-bg-panel'}`}>
                        إجمالي
                    </button>
                    <button type="button" onClick={() => setFormData((prev: any) => ({ ...prev, pricingMethod: 'unit' }))}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${formData.pricingMethod === 'unit' ? 'aseel-bg-accent text-white shadow-md' : 'aseel-text-accent aseel-bg-field/50 dark:aseel-bg-panel'}`}>
                        بالوحدة
                    </button>
                </div>

                {formData.pricingMethod === 'unit' && (
                    <div className="grid grid-cols-2 gap-3 mb-2">
                        <div>
                            <label className="text-[10px] aseel-text-soft mb-1 block">نوع الوحدة</label>
                            <select
                                value={formData.unitType || 'cbm'} // 🟢 ضمان قيمة افتراضية
                                onChange={(e) => {
                                    const newUnitType = e.target.value;
                                    setFormData((prev: any) => ({ ...prev, unitType: newUnitType }));
                                    // إعادة الحساب فوراً عند التغيير
                                    handleUnitPriceChange(formData.pricePerUnit, newUnitType);
                                }}
                                className="w-full p-2 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg text-sm"
                            >
                                <option value="cbm">حجم (CBM)</option>
                                <option value="weight">وزن (KG)</option>
                                <option value="container">حاوية</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-[10px] aseel-text-soft mb-1 block">سعر الوحدة ($)</label>
                            <input
                                type="number" min="0" step="0.01"
                                value={formData.pricePerUnit || ''}
                                onChange={(e) => {
                                    const val = parseFloat(e.target.value) || 0;
                                    // 🟢 تمرير نوع الوحدة الحالي صراحةً لضمان عدم ضياعه
                                    handleUnitPriceChange(val, formData.unitType);
                                }}
                                className="w-full p-2 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg text-sm font-bold aseel-text-accent"
                            />
                        </div>
                    </div>
                )}

                <div>
                    <label className="block text-xs font-medium aseel-text-soft dark:aseel-text-soft mb-1">
                        تكلفة الشحن الأساسية (بدون إضافات)
                    </label>
                    <div className="relative">
                        <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 aseel-text-soft w-4 h-4" />
                        <input
                            required type="number" min="0" step="0.01"
                            value={formData.totalShippingCostUsd || ''}
                            onChange={(e) => handleTotalChange(parseFloat(e.target.value) || 0)}
                            className="w-full p-2 pl-9 aseel-bg-field dark:aseel-bg-panel border aseel-border-soft dark:aseel-border-soft rounded-lg font-bold text-lg"
                            placeholder="0.00"
                        />
                    </div>
                </div>

                {/* 🟢 تم تصحيح أماكن الوزن والحجم كانت معكوسة في الكود السابق */}
                <div className="pt-2 mt-2 border-t aseel-border-accent dark:aseel-border-soft flex justify-between items-center text-xs aseel-text-ink dark:aseel-text-soft">
                    <span>الوزن الكلي: {totals.weight.toLocaleString()} kg</span>
                    <span>الحجم الكلي: {totals.volume.toLocaleString()} cbm</span>
                </div>
            </div>
        </div>
    );
};