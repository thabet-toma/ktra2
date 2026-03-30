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

    // 🟢 ميزة: إعادة حساب السعر تلقائياً عند تغيير نوع الوحدة من القائمة
    useEffect(() => {
        if (formData.pricingMethod === 'unit' && formData.pricePerUnit > 0) {
            handleUnitPriceChange(formData.pricePerUnit, formData.unitType);
        }
    }, [formData.unitType, formData.pricingMethod]);

    return (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 space-y-4">
            {/* ... (الحقول العلوية: الرقم التسلسلي، رقم الشحنة، الطرف الإسرائيلي... تبقى كما هي) ... */}
            {formData.id && (
                <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-xl flex justify-between items-center border border-dashed border-gray-300 dark:border-gray-700">
                    <span className="text-sm text-gray-500">الرقم التسلسلي:</span>
                    <span className="font-mono font-bold text-gray-700 dark:text-gray-300">{formData.shipmentNumber}</span>
                </div>
            )}

            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">رقم الشحنة (لدى الوكيل / البوليصة)</label>
                <div className="relative">
                    <Hash className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
                    <input
                        type="text"
                        value={formData.agentShipmentNumber || ''}
                        onChange={(e) => setFormData((prev: any) => ({ ...prev, agentShipmentNumber: e.target.value }))}
                        className="w-full p-3 pl-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl font-mono focus:ring-2 focus:ring-blue-500 outline-none"
                        placeholder="Ref Number..."
                    />
                </div>
            </div>

            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">الطرف الإسرائيلي</label>
                <div className="relative">
                    <UserCircle className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
                    <input
                        type="text"
                        value={formData.israeliSideName || ''}
                        onChange={(e) => setFormData((prev: any) => ({ ...prev, israeliSideName: e.target.value }))}
                        className="w-full p-3 pl-10 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl"
                        placeholder="الاسم..."
                    />
                </div>
            </div>

            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">اسم تعريفي (اختياري)</label>
                <input
                    type="text"
                    value={formData.shipmentName || ''}
                    onChange={(e) => setFormData((prev: any) => ({ ...prev, shipmentName: e.target.value }))}
                    className="w-full p-3 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl"
                    placeholder="مثال: حاوية إلكترونيات - دفعة 1"
                />
            </div>

            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">وكيل الشحن <span className="text-red-500">*</span></label>
                <div className="flex gap-2">
                    <select
                        required
                        value={formData.shippingAgentId || ''}
                        onChange={(e) => {
                            const agent = allSuppliers.find(s => s.id === e.target.value);
                            setFormData((prev: any) => ({ ...prev, shippingAgentId: e.target.value, shippingAgentName: agent?.tradeName || '' }));
                        }}
                        className="w-full p-3 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl"
                    >
                        <option value="">اختر وكيل شحن</option>
                        {allSuppliers.map(s => <option key={s.id} value={s.id}>{s.tradeName}</option>)}
                    </select>
                    {formData.shippingAgentId && (
                        <button type="button" onClick={() => onOpenSupplier(formData.shippingAgentId)} className="p-3 bg-blue-50 hover:bg-blue-100 rounded-xl text-blue-600">
                            <Eye className="w-5 h-5" />
                        </button>
                    )}
                </div>
            </div>

            <hr className="border-gray-200 dark:border-gray-700" />

            {/* Pricing Section */}
            <div className="bg-blue-50 dark:bg-blue-900/10 p-4 rounded-xl border border-blue-100 dark:border-blue-800">
                <div className="flex gap-2 mb-3">
                    <button type="button" onClick={() => setFormData((prev: any) => ({ ...prev, pricingMethod: 'total' }))}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${formData.pricingMethod === 'total' ? 'bg-blue-600 text-white shadow-md' : 'text-blue-600 bg-white/50 dark:bg-gray-800'}`}>
                        إجمالي
                    </button>
                    <button type="button" onClick={() => setFormData((prev: any) => ({ ...prev, pricingMethod: 'unit' }))}
                        className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all ${formData.pricingMethod === 'unit' ? 'bg-blue-600 text-white shadow-md' : 'text-blue-600 bg-white/50 dark:bg-gray-800'}`}>
                        بالوحدة
                    </button>
                </div>

                {formData.pricingMethod === 'unit' && (
                    <div className="grid grid-cols-2 gap-3 mb-2">
                        <div>
                            <label className="text-[10px] text-gray-500 mb-1 block">نوع الوحدة</label>
                            <select
                                value={formData.unitType || 'cbm'} // 🟢 ضمان قيمة افتراضية
                                onChange={(e) => {
                                    const newUnitType = e.target.value;
                                    setFormData((prev: any) => ({ ...prev, unitType: newUnitType }));
                                    // إعادة الحساب فوراً عند التغيير
                                    handleUnitPriceChange(formData.pricePerUnit, newUnitType);
                                }}
                                className="w-full p-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg text-sm"
                            >
                                <option value="cbm">حجم (CBM)</option>
                                <option value="weight">وزن (KG)</option>
                                <option value="container">حاوية</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-[10px] text-gray-500 mb-1 block">سعر الوحدة ($)</label>
                            <input
                                type="number" min="0" step="0.01"
                                value={formData.pricePerUnit || ''}
                                onChange={(e) => {
                                    const val = parseFloat(e.target.value) || 0;
                                    // 🟢 تمرير نوع الوحدة الحالي صراحةً لضمان عدم ضياعه
                                    handleUnitPriceChange(val, formData.unitType);
                                }}
                                className="w-full p-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg text-sm font-bold text-blue-600"
                            />
                        </div>
                    </div>
                )}

                <div>
                    <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                        تكلفة الشحن الأساسية (بدون إضافات)
                    </label>
                    <div className="relative">
                        <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
                        <input
                            required type="number" min="0" step="0.01"
                            value={formData.totalShippingCostUsd || ''}
                            onChange={(e) => handleTotalChange(parseFloat(e.target.value) || 0)}
                            className="w-full p-2 pl-9 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg font-bold text-lg"
                            placeholder="0.00"
                        />
                    </div>
                </div>

                {/* 🟢 تم تصحيح أماكن الوزن والحجم كانت معكوسة في الكود السابق */}
                <div className="pt-2 mt-2 border-t border-blue-200 dark:border-blue-800 flex justify-between items-center text-xs text-blue-800 dark:text-blue-300">
                    <span>الوزن الكلي: {totals.weight.toLocaleString()} kg</span>
                    <span>الحجم الكلي: {totals.volume.toLocaleString()} cbm</span>
                </div>
            </div>
        </div>
    );
};