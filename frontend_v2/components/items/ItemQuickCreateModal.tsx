import React, { useState } from "react";
import { Package, X, Save } from "lucide-react";
import { inventoryApi } from "../../services/inventoryApi";

export type ItemQuickCreateModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onSaved: (newProduct: any) => void;
  /** task18 DEF-B1/B3: تعبئة الاسم العربي مسبقاً (مثلاً النص المكتوب في الإكمال التلقائي). */
  initialName?: string;
  /** task18: إنشاء الصنف تحت فئة محددة (من الشجرة) — يُرسَل كـ category. */
  categoryId?: string | number | null;
};

export const ItemQuickCreateModal: React.FC<ItemQuickCreateModalProps> = ({ isOpen, onClose, onSaved, initialName, categoryId }) => {
  const [nameAr, setNameAr] = useState(initialName || "");
  const [nameEn, setNameEn] = useState("");
  const [uom, setUom] = useState("عدد");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSave = async () => {
    if (!nameAr.trim()) {
      setError("الاسم العربي مطلوب");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      // The backend generates SKU if we don't pass it, since Product model has logic or we made it optional.
      // We pass the bare minimum.
      const payload: Record<string, unknown> = {
        name_ar: nameAr,
        name_en: nameEn || null,
        uom_primary: uom,
      };
      if (categoryId != null && categoryId !== "") payload.category = categoryId;
      const created = await inventoryApi.createProduct(payload);
      onSaved(created);
    } catch (e: any) {
      setError(e.message || "حدث خطأ أثناء الحفظ");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" dir="rtl">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-gray-900/50">
          <h3 className="font-bold flex items-center gap-2 text-gray-800 dark:text-gray-100">
            <Package className="w-5 h-5 text-emerald-600" />
            إضافة صنف سريع
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && <div className="text-red-600 bg-red-50 p-2 rounded text-sm">{error}</div>}

          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">الاسم العربي <span className="text-red-500">*</span></label>
            <input
              type="text"
              autoFocus
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-emerald-500"
              value={nameAr}
              onChange={(e) => setNameAr(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">الاسم الإنجليزي (اختياري)</label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-emerald-500"
              value={nameEn}
              onChange={(e) => setNameEn(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">وحدة القياس</label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-gray-300 dark:border-gray-600 focus:ring-2 focus:ring-emerald-500"
              value={uom}
              onChange={(e) => setUom(e.target.value)}
            />
          </div>
        </div>

        <div className="px-5 py-4 border-t border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 border rounded-lg text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
          >
            إلغاء
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving ? "جاري الحفظ..." : <><Save className="w-4 h-4" /> حفظ وإدراج</>}
          </button>
        </div>
      </div>
    </div>
  );
};
