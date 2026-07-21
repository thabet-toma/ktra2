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
      <div className="bg-[var(--color-surface)] rounded-xl shadow-xl w-full max-w-md overflow-hidden">
        <div className="px-5 py-4 border-b border-[var(--color-border)] flex justify-between items-center bg-[var(--color-surface-2)]">
          <h3 className="font-bold flex items-center gap-2 text-[var(--color-text)]">
            <Package className="w-5 h-5 text-emerald-600" />
            إضافة صنف سريع
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-[var(--color-surface-3)] rounded-full">
            <X className="w-5 h-5 text-[var(--color-text-muted)]" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && <div className="text-red-600 bg-red-50 p-2 rounded text-sm">{error}</div>}

          <div>
            <label className="block text-sm font-medium mb-1 text-[var(--color-text)]">الاسم العربي <span className="text-red-500">*</span></label>
            <input
              type="text"
              autoFocus
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-emerald-500"
              value={nameAr}
              onChange={(e) => setNameAr(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-[var(--color-text)]">الاسم الإنجليزي (اختياري)</label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-emerald-500"
              value={nameEn}
              onChange={(e) => setNameEn(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-[var(--color-text)]">وحدة القياس</label>
            <input
              type="text"
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-emerald-500"
              value={uom}
              onChange={(e) => setUom(e.target.value)}
            />
          </div>
        </div>

        <div className="px-5 py-4 border-t border-[var(--color-border)] bg-[var(--color-surface-2)] flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 border rounded-lg text-sm font-medium hover:bg-[var(--color-surface-3)] text-[var(--color-text-muted)]"
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
