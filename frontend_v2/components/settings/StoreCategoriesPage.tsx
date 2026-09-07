/**
 * شجرة فئات المتجر — شاشةٌ مستقلّة (مواصفة #166 م٣).
 *
 * قرارٌ معماريٌّ صريح: لا تُضَف كقسمٍ داخل `StoreSettingsPage.tsx` — ذاك
 * الملفّ ضخمٌ أصلاً، ومحرِّرُ شجرةٍ داخله يجعله غيرَ قابلٍ للصيانة.
 *
 * العمقُ محدودٌ بمستويين: الخادم يرفض المستوى الثالث بـ400 (`StoreCategory._reject_third_level`)،
 * وهذه الشاشة تمنعه في الواجهة أيضاً (منتقي الأب لا يعرض فئةً لها أبٌ بالفعل)
 * — لكن لا تكتفي بالمنع الواجهي: خطأ الخادم يُعرض كما هو عند وقوعه.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Layers, Loader2, Pencil, Plus, Trash2, X } from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  createStoreAdminCategory,
  deleteStoreAdminCategory,
  getStoreAdminCategories,
  updateStoreAdminCategory,
  type StoreAdminCategory,
  type StoreCategoryPayload,
} from "../../services/storeAdminApi";
import { humanizeDrfError } from "../../utils/drfError";
import { KitDocumentShell } from "../kit";

const emptyForm = (): StoreCategoryPayload => ({
  name: "", parent: null, sort_order: 0, is_active: true, image_url: "",
});

export const StoreCategoriesPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();

  const [categories, setCategories] = useState<StoreAdminCategory[]>([]);
  const [loading, setLoading] = useState(false);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<StoreCategoryPayload>(emptyForm());
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setCategories(await getStoreAdminCategories());
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const roots = categories.filter((c) => c.parent === null);
  const childrenOf = (parentId: number) => categories.filter((c) => c.parent === parentId);

  const openCreate = (parent: number | null) => {
    setEditingId(null);
    setForm({ ...emptyForm(), parent });
    setIsModalOpen(true);
  };

  const openEdit = (cat: StoreAdminCategory) => {
    setEditingId(cat.id);
    setForm({
      name: cat.name, parent: cat.parent, sort_order: cat.sort_order,
      is_active: cat.is_active, image_url: cat.image_url || "",
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast("يرجى إدخال اسم الفئة", "error");
      return;
    }
    setSaving(true);
    try {
      if (editingId) {
        const saved = await updateStoreAdminCategory(editingId, form);
        setCategories((prev) => prev.map((c) => (c.id === saved.id ? saved : c)));
        toast("تم حفظ تعديلات الفئة", "success");
      } else {
        const created = await createStoreAdminCategory(form);
        setCategories((prev) => [...prev, created]);
        toast("تمت إضافة الفئة", "success");
      }
      setIsModalOpen(false);
    } catch (e) {
      // مثال: إسناد أبٍ له أبٌ بالفعل — الخادم يرفضها 400 بنصٍّ عربي صريح،
      // ولا يكفي المنع الواجهي وحده (منتقي الأب هنا مقيَّدٌ أصلاً لكن الحارس الحقيقي خادمي).
      toast(humanizeDrfError(e), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (cat: StoreAdminCategory) => {
    const hasChildren = childrenOf(cat.id).length > 0;
    const ok = await confirm({
      title: "حذف الفئة",
      message: hasChildren
        ? `«${cat.name}» لها فئاتٌ فرعية — حذفها يفصل تلك الفئات عن أبيها. هل أنت متأكد؟`
        : `هل أنت متأكد من حذف «${cat.name}»؟ منتجاتها تبقى في المتجر بلا هذه الفئة.`,
      confirmText: "حذف",
      cancelText: "إلغاء",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteStoreAdminCategory(cat.id);
      await load();
      toast("تم حذف الفئة", "success");
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  const toggleActive = async (cat: StoreAdminCategory) => {
    try {
      const saved = await updateStoreAdminCategory(cat.id, { is_active: !cat.is_active });
      setCategories((prev) => prev.map((c) => (c.id === saved.id ? saved : c)));
    } catch (e) {
      toast(humanizeDrfError(e), "error");
    }
  };

  const renderRow = (cat: StoreAdminCategory, isChild: boolean) => (
    <div
      key={cat.id}
      className={`flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900 ${
        isChild ? "mr-8" : ""
      }`}
    >
      <div className="flex min-w-0 items-center gap-2">
        {cat.image_url ? (
          <img src={cat.image_url} alt="" className="h-8 w-8 shrink-0 rounded-lg object-cover" />
        ) : (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-400 dark:bg-slate-800">
            <Layers className="h-4 w-4" />
          </div>
        )}
        <div className="min-w-0">
          <div className="truncate text-xs font-bold text-slate-900 dark:text-white">{cat.name}</div>
          <div className="truncate font-mono text-[10px] text-slate-400">{cat.slug}</div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={() => toggleActive(cat)}
          className={`rounded-lg px-2 py-1 text-[10px] font-bold ${
            cat.is_active
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
              : "bg-slate-100 text-slate-500 dark:bg-slate-800"
          }`}
          title="تعطيلُ الفئة يُخفيها من تصفّح المتجر ولا يُخفي منتجاتِها"
        >
          {cat.is_active ? "ظاهرة" : "مخفية"}
        </button>
        {!isChild && (
          <button
            type="button"
            onClick={() => openCreate(cat.id)}
            title="إضافة فئة فرعية"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-950/50"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={() => openEdit(cat)}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => handleDelete(cat)}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/50"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );

  // العمقُ محدودٌ بمستويين — لا تُعرَض فئةٌ لها أبٌ بالفعل كخيارِ أبٍ (منعٌ
  // واجهيٌّ إضافيّ؛ الحارس الحقيقي خادميّ في `StoreCategory._reject_third_level`).
  const rootOptionsForParent = (excludeId: number | null) =>
    roots.filter((c) => c.id !== excludeId);

  return (
    <KitDocumentShell
      title="فئات المتجر"
      subtitle="شجرةٌ بمستويين لتصفّح كتالوج المتجر — تعطيل الفئة يُخفيها من التصفّح فقط ولا يُخفي منتجاتِها"
    >
      <div className="space-y-4 font-sans" dir="rtl">
        <div className="flex items-center justify-between rounded-2xl border border-amber-200 bg-amber-50 p-3 text-xs font-bold text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
          <span>
            الفئة أداةُ تصفّحٍ لا بوّابةُ نشر: تعطيلها يُخفيها من قوائم المتجر وحدها، ومنتجاتها تبقى معروضةً كما هي.
          </span>
        </div>

        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => openCreate(null)}
            className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm shadow-blue-600/20 transition hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            <span>فئة رئيسية جديدة</span>
          </button>
        </div>

        {loading ? (
          <div className="py-16 text-center text-slate-400">
            <Loader2 className="mx-auto h-6 w-6 animate-spin" />
          </div>
        ) : roots.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-slate-200 p-10 text-center text-xs text-slate-400 dark:border-slate-800">
            لا فئات بعد.
          </div>
        ) : (
          <div className="space-y-3">
            {roots.map((root) => (
              <div key={root.id} className="space-y-2">
                {renderRow(root, false)}
                {childrenOf(root.id).map((child) => renderRow(child, true))}
              </div>
            ))}
          </div>
        )}

        {isModalOpen && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
            onClick={(e) => e.target === e.currentTarget && setIsModalOpen(false)}
          >
            <div className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
              <div className="flex items-center justify-between border-b border-slate-100 pb-4 dark:border-slate-800">
                <h3 className="text-base font-black text-slate-900 dark:text-white">
                  {editingId ? "تعديل الفئة" : "إضافة فئة"}
                </h3>
                <button type="button" onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-slate-700">
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="my-4 space-y-3">
                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    اسم الفئة <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    الفئة الأب (اختياري — العمق الأقصى مستويان)
                  </label>
                  <select
                    value={form.parent ?? ""}
                    onChange={(e) =>
                      setForm((prev) => ({ ...prev, parent: e.target.value ? Number(e.target.value) : null }))
                    }
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  >
                    <option value="">بلا أب (فئة رئيسية)</option>
                    {rootOptionsForParent(editingId).map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                    رابط الصورة
                  </label>
                  <input
                    type="text"
                    value={form.image_url}
                    onChange={(e) => setForm((prev) => ({ ...prev, image_url: e.target.value }))}
                    placeholder="https://…"
                    dir="ltr"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-mono focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-bold text-slate-700 dark:text-slate-300">
                      الترتيب
                    </label>
                    <input
                      type="number"
                      value={form.sort_order ?? 0}
                      onChange={(e) => setForm((prev) => ({ ...prev, sort_order: Number(e.target.value) }))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    />
                  </div>
                  <label className="flex cursor-pointer items-center justify-between self-end rounded-xl bg-slate-50 p-3 dark:bg-slate-800">
                    <span className="text-xs font-bold text-slate-700 dark:text-slate-300">ظاهرة في التصفّح</span>
                    <input
                      type="checkbox"
                      checked={form.is_active ?? true}
                      onChange={(e) => setForm((prev) => ({ ...prev, is_active: e.target.checked }))}
                      className="h-4 w-4 rounded accent-blue-600"
                    />
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                >
                  إلغاء
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving}
                  className="rounded-xl bg-blue-600 px-6 py-2 text-xs font-bold text-white shadow-md shadow-blue-600/20 hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? "جارٍ الحفظ…" : "حفظ"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </KitDocumentShell>
  );
};

export default StoreCategoriesPage;
