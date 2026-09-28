import React, { useMemo, useState } from "react";
import { Loader2, Package, X } from "lucide-react";
import {
  bulkApplyWarrantyPolicy, lookupManufacturerWarrantors,
  type ManufacturerWarrantorRow, type WarrantyPolicyBulkInput, type WarrantyPolicyMethod,
} from "../../services/afterSalesApi";
import {
  SalesProductPickerModal, type SalesProductPickerItem,
} from "../sales/SalesProductPickerModal";

/**
 * #231 — تطبيق سياسة واحدة على كل براندات منتجٍ أبٍ أو تصنيف دفعةً واحدة:
 * صفٌّ لكل براند (upsert)، وكلٌّ أو لا شيء إن فشل أيّ براند (منتج خدمة تحت
 * «برقم تسلسلي» مثلاً) — لا كتابة جزئية يخلطها المستخدم بنجاح وهمي.
 */

interface ProductOption extends SalesProductPickerItem {
  family_id?: number | null;
  family_name?: string | null;
  category?: number | null;
  category_name?: string | null;
}

interface Props {
  products: ProductOption[];
  onClose: () => void;
  onApplied: (count: number) => void;
}

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const fieldClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60";

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

type Selector = "family" | "category";

export const WarrantyPolicyBulkModal: React.FC<Props> = ({ products, onClose, onApplied }) => {
  const [selector, setSelector] = useState<Selector>("family");
  const [anchorProduct, setAnchorProduct] = useState<ProductOption | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [method, setMethod] = useState<WarrantyPolicyMethod>("serial");
  const [dealerMonths, setDealerMonths] = useState(0);
  const [manufacturerMonths, setManufacturerMonths] = useState(0);
  const [supplierMonths, setSupplierMonths] = useState(0);
  const [warrantorId, setWarrantorId] = useState<number | "">("");
  const [warrantors, setWarrantors] = useState<ManufacturerWarrantorRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  React.useEffect(() => {
    lookupManufacturerWarrantors().then(setWarrantors).catch(() => setWarrantors([]));
  }, []);

  const categories = useMemo(() => {
    const seen = new Map<number, string>();
    for (const p of products) {
      if (p.category != null && !seen.has(p.category)) {
        seen.set(p.category, p.category_name || `#${p.category}`);
      }
    }
    return Array.from(seen.entries()).map(([id, name]) => ({ id, name }));
  }, [products]);

  const apply = async () => {
    setErr(null);
    if (selector === "family" && !anchorProduct?.family_id) {
      setErr("اختر برانداً من المنتج الأب المطلوب أولاً");
      return;
    }
    if (selector === "category" && !categoryId) {
      setErr("اختر تصنيفاً");
      return;
    }
    if (dealerMonths <= 0 && manufacturerMonths <= 0) {
      setErr("حدّد مدة كفالة التاجر أو المصنع أكبر من صفر — كفالة المورّد وحدها داخلية لا تُصدر للزبون بطاقة");
      return;
    }
    setBusy(true);
    try {
      const input: WarrantyPolicyBulkInput = {
        method, dealer_months: dealerMonths, manufacturer_months: manufacturerMonths,
        supplier_months: supplierMonths, manufacturer_warrantor: warrantorId || null,
        ...(selector === "family"
          ? { family: anchorProduct!.family_id! }
          : { category: categoryId as number }),
      };
      const result = await bulkApplyWarrantyPolicy(input);
      onApplied(result.applied);
      onClose();
    } catch (e) {
      setErr(messageOf(e, "تعذّر تطبيق السياسة الجماعية"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label="تطبيق سياسة كفالة جماعياً"
      className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
    >
      <div className="w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
          <span className="truncate font-bold text-[var(--color-text)]">تطبيق سياسة كفالة جماعياً</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="إغلاق"
            aria-label="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 p-3 md:p-4">
          {err && (
            <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setSelector("family")}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm font-semibold ${
                selector === "family"
                  ? "border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]"
                  : "border-[var(--color-border)] text-[var(--color-text)]"
              }`}
            >
              كل براندات منتجٍ أب
            </button>
            <button
              type="button"
              onClick={() => setSelector("category")}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm font-semibold ${
                selector === "category"
                  ? "border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]"
                  : "border-[var(--color-border)] text-[var(--color-text)]"
              }`}
            >
              كل منتجات تصنيف
            </button>
          </div>

          {selector === "family" ? (
            <div>
              <label className={labelClass}>اختر أيّ براندٍ من المنتج الأب</label>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="flex h-10 w-full items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
              >
                <Package className="h-4 w-4 text-[var(--color-text-muted)]" />
                {anchorProduct
                  ? (anchorProduct.family_name || anchorProduct.display_name || anchorProduct.name_ar)
                  : "اختر برانداً…"}
              </button>
              {anchorProduct && (
                <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                  ستُطبَّق السياسة على كل براندات «{anchorProduct.family_name || "هذا المنتج"}».
                </p>
              )}
            </div>
          ) : (
            <div>
              <label className={labelClass} htmlFor="bulk-category">التصنيف</label>
              <select
                id="bulk-category"
                className={fieldClass}
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">اختر تصنيفاً…</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className={labelClass} htmlFor="bulk-method">طريقة الإثبات</label>
            <select
              id="bulk-method"
              className={fieldClass}
              value={method}
              onChange={(e) => setMethod(e.target.value as WarrantyPolicyMethod)}
            >
              <option value="serial">برقم تسلسلي</option>
              <option value="invoice">على الفاتورة</option>
            </select>
            {selector === "family" && (
              <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
                البراندات ذات المنتجات الخدمية تُرفض تلقائياً تحت «برقم تسلسلي» — عدّل التحديد أو اختر «على الفاتورة».
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className={labelClass} htmlFor="bulk-dealer">كفالة التاجر (أشهر)</label>
              <input
                id="bulk-dealer" type="number" min="0" max="600" className={fieldClass}
                value={dealerMonths} onChange={(e) => setDealerMonths(Number(e.target.value) || 0)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="bulk-manufacturer">كفالة المصنع (أشهر)</label>
              <input
                id="bulk-manufacturer" type="number" min="0" max="600" className={fieldClass}
                value={manufacturerMonths}
                onChange={(e) => setManufacturerMonths(Number(e.target.value) || 0)}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="bulk-supplier">كفالة المورّد (أشهر)</label>
              <input
                id="bulk-supplier" type="number" min="0" max="600" className={fieldClass}
                value={supplierMonths} onChange={(e) => setSupplierMonths(Number(e.target.value) || 0)}
              />
            </div>
          </div>

          <div>
            <label className={labelClass} htmlFor="bulk-warrantor">جهة كفالة المصنع</label>
            <select
              id="bulk-warrantor"
              className={fieldClass}
              value={warrantorId}
              onChange={(e) => setWarrantorId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">لا يوجد</option>
              {warrantors.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-[var(--color-border)] p-3 sm:flex-row sm:items-center">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50 sm:w-32"
          >
            إغلاق
          </button>
          <button
            type="button"
            onClick={() => void apply()}
            disabled={busy}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            تطبيق
          </button>
        </div>
      </div>

      <SalesProductPickerModal
        isOpen={pickerOpen}
        onClose={() => setPickerOpen(false)}
        products={products}
        onSelect={(productId) => {
          setAnchorProduct(products.find((p) => p.id === productId) || null);
          setPickerOpen(false);
        }}
      />
    </div>
  );
};

export default WarrantyPolicyBulkModal;
