import React, { useEffect, useState } from "react";
import { Package, X, Save } from "lucide-react";
import { inventoryApi } from "../../services/inventoryApi";
import { blankSimpleFields, simplePayload, validateSimpleFields } from "../../utils/itemSimpleFields";

export type ItemQuickCreateModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onSaved: (newProduct: any) => void;
  /** task18 DEF-B1/B3: تعبئة الاسم العربي مسبقاً (مثلاً النص المكتوب في الإكمال التلقائي). */
  initialName?: string;
  /** task18: إنشاء المنتج تحت فئة محددة (من الشجرة) — يُرسَل كـ category. */
  categoryId?: string | number | null;
  /** T-SERVICELINE: فتح النافذة على «بند خدمة» (مدخل «إضافة خدمة» من الفاتورة). */
  initialIsService?: boolean;
};

export const ItemQuickCreateModal: React.FC<ItemQuickCreateModalProps> = ({ isOpen, onClose, onSaved, initialName, categoryId, initialIsService = false }) => {
  const [nameAr, setNameAr] = useState(initialName || "");
  const [nameEn, setNameEn] = useState("");
  const [uomId, setUomId] = useState<number | null>(null);
  const [uoms, setUoms] = useState<Array<{ id: number; name_ar: string; name_en: string; code: string }>>([]);
  const [salePrice, setSalePrice] = useState("");
  const [isService, setIsService] = useState(initialIsService);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // T-ITEMS M1: وحدة القياس صارت اختياراً من الجدول. كانت نصّاً حرّاً يُرسَل
  // باسم `uom_primary` — وهو ليس في عقد الخادم، فيرميه DRF بصمت: يكتب
  // المستخدم «كرتونة» ويحصل على «تم الحفظ» ولا وحدة على المنتج.
  useEffect(() => {
    if (!isOpen) return;
    inventoryApi.getUoms().then(setUoms).catch(() => setUoms([]));
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async () => {
    const fields = {
      ...blankSimpleFields(),
      name_ar: nameAr, name_en: nameEn, uom_id: uomId,
      sale_price: salePrice, is_service: isService,
    };
    const invalid = validateSimpleFields(fields);
    if (invalid) { setError(invalid); return; }
    setSaving(true);
    setError(null);
    try {
      // نفس تعريف «الوضع البسيط» الذي يستعمله الكرت الكامل — الحمولة تُبنى
      // مرّةً واحدة في `utils/itemSimpleFields` فلا تتباعد الشاشتان.
      const payload = simplePayload(fields);
      // التصنيف يأتي من المستدعي (عقدة الشجرة) ويسبق قيمة النموذج الفارغة.
      if (categoryId != null && categoryId !== "") payload.category = Number(categoryId);
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
            إضافة منتج سريع
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
            <select
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-emerald-500"
              value={uomId ?? ""}
              onChange={(e) => setUomId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— بدون وحدة —</option>
              {uoms.map((u) => (
                <option key={u.id} value={u.id}>{u.name_ar || u.name_en || u.code}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-[var(--color-text)]">سعر البيع (اختياري)</label>
            <input
              type="number"
              min="0"
              step="0.01"
              placeholder="اتركه فارغاً ليتبع آخر سعر بيع"
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 border-[var(--color-border)] focus:ring-2 focus:ring-emerald-500"
              value={salePrice}
              onChange={(e) => setSalePrice(e.target.value)}
            />
          </div>

          <label className="flex items-center gap-2 text-sm font-medium text-[var(--color-text)]">
            <input
              type="checkbox"
              checked={isService}
              onChange={(e) => setIsService(e.target.checked)}
            />
            بند خدمة (لا يُخصم من المخزون — يُسجَّل كإيرادات خدمات)
          </label>
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
