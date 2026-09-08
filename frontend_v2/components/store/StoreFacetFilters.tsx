/**
 * شريطُ الفلاتر بعدّاداتٍ سياقيّة (THA-166 م٧، قسم ج) — عمودٌ لاصقٌ على
 * الحاسوب، ودرجٌ سفليٌّ على الجوّال. لا استيراد من `components/kit`.
 *
 * **لازمةٌ يجب معرفتها هنا:** مجموعُ عدّاداتِ محورٍ (الفئات تحديداً) قد
 * يتجاوز عدد النتائج الكلّي — هذا سلوكٌ صحيحٌ من الخادم (استثناءٌ انفصاليّ)
 * ولا يُعالَج هنا بجمعٍ أو قصّ.
 */
import React, { useEffect, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import type { StoreFacets, StorePriceRange } from "../../services/storeApi";
import { formatNumber } from "../../utils/formatNumber";
import type { UseStoreCatalogResult } from "./useStoreCatalog";

interface StoreFacetFiltersProps {
  facets: StoreFacets | null;
  priceRange: StorePriceRange | null;
  currency: string | null;
  catalog: UseStoreCatalogResult;
}

const CHECKBOX_ROW =
  "flex cursor-pointer items-center justify-between gap-2 rounded-xl px-2 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800";

function FilterSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-slate-100 py-4 first:pt-0 last:border-b-0 dark:border-slate-800">
      <h4 className="mb-2 text-xs font-black text-slate-900 dark:text-white">{title}</h4>
      {children}
    </div>
  );
}

function FilterBody({ facets, priceRange, catalog }: Omit<StoreFacetFiltersProps, "currency">) {
  const [localMin, setLocalMin] = useState(catalog.minPrice);
  const [localMax, setLocalMax] = useState(catalog.maxPrice);

  useEffect(() => {
    setLocalMin(catalog.minPrice);
    setLocalMax(catalog.maxPrice);
  }, [catalog.minPrice, catalog.maxPrice]);

  const parentCategories = (facets?.categories || []).filter((c) => c.parent_id === null);
  const childrenByParent = (facets?.categories || []).reduce<Record<number, typeof parentCategories>>(
    (acc, c) => {
      if (c.parent_id !== null) {
        acc[c.parent_id] = [...(acc[c.parent_id] || []), c];
      }
      return acc;
    },
    {},
  );

  return (
    <div>
      {parentCategories.length > 0 && (
        <FilterSection title="الفئات">
          <div className="max-h-64 space-y-0.5 overflow-y-auto">
            {parentCategories.map((cat) => (
              <React.Fragment key={cat.id}>
                <label className={CHECKBOX_ROW}>
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={catalog.categoryIds.includes(cat.id)}
                      onChange={() => catalog.toggleCategory(cat.id)}
                      className="h-3.5 w-3.5 rounded border-slate-300"
                    />
                    <span>{cat.name}</span>
                  </span>
                  <span className="text-slate-400 dark:text-slate-500">({formatNumber(cat.count)})</span>
                </label>
                {(childrenByParent[cat.id] || []).map((child) => (
                  <label key={child.id} className={`${CHECKBOX_ROW} ps-6`}>
                    <span className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={catalog.categoryIds.includes(child.id)}
                        onChange={() => catalog.toggleCategory(child.id)}
                        className="h-3.5 w-3.5 rounded border-slate-300"
                      />
                      <span>{child.name}</span>
                    </span>
                    <span className="text-slate-400 dark:text-slate-500">({formatNumber(child.count)})</span>
                  </label>
                ))}
              </React.Fragment>
            ))}
          </div>
        </FilterSection>
      )}

      {facets && facets.brands.length > 0 && (
        <FilterSection title="الماركات">
          <div className="max-h-48 space-y-0.5 overflow-y-auto">
            {facets.brands.map((brand) => (
              <label key={brand.id} className={CHECKBOX_ROW}>
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={catalog.brandIds.includes(brand.id)}
                    onChange={() => catalog.toggleBrand(brand.id)}
                    className="h-3.5 w-3.5 rounded border-slate-300"
                  />
                  <span>{brand.name}</span>
                </span>
                <span className="text-slate-400 dark:text-slate-500">({formatNumber(brand.count)})</span>
              </label>
            ))}
          </div>
        </FilterSection>
      )}

      {facets && (
        <FilterSection title="الحالة">
          <div className="space-y-0.5">
            <label className={CHECKBOX_ROW}>
              <span className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={catalog.onSale}
                  onChange={(e) => catalog.setOnSale(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-slate-300"
                />
                <span>مخفّض</span>
              </span>
              <span className="text-slate-400 dark:text-slate-500">({formatNumber(facets.flags.on_sale)})</span>
            </label>
            <label className={CHECKBOX_ROW}>
              <span className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={catalog.isNew}
                  onChange={(e) => catalog.setIsNew(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-slate-300"
                />
                <span>جديد</span>
              </span>
              <span className="text-slate-400 dark:text-slate-500">({formatNumber(facets.flags.is_new)})</span>
            </label>
            <label className={CHECKBOX_ROW}>
              <span className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={catalog.inStock}
                  onChange={(e) => catalog.setInStock(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-slate-300"
                />
                <span>متوفر</span>
              </span>
              <span className="text-slate-400 dark:text-slate-500">({formatNumber(facets.flags.in_stock)})</span>
            </label>
          </div>
        </FilterSection>
      )}

      {/* `price_range` قد يغيب كلياً حين تُحجَب الأسعار — لا يُعرض منزلقٌ بأصفار. */}
      {priceRange && (
        <FilterSection title="نطاق السعر">
          <div className="flex items-center gap-2">
            <input
              type="number"
              inputMode="decimal"
              value={localMin}
              onChange={(e) => setLocalMin(e.target.value)}
              placeholder={priceRange.min ?? "0"}
              aria-label="أقل سعر"
              className="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
            <span className="text-slate-400">—</span>
            <input
              type="number"
              inputMode="decimal"
              value={localMax}
              onChange={(e) => setLocalMax(e.target.value)}
              placeholder={priceRange.max ?? "0"}
              aria-label="أعلى سعر"
              className="h-9 w-full rounded-xl border border-slate-200 bg-slate-50 px-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
          </div>
          <button
            type="button"
            onClick={() => catalog.setPriceBounds(localMin, localMax)}
            className="mt-2 h-8 w-full rounded-xl bg-[var(--store-primary,#2563eb)] text-[11px] font-bold text-white transition hover:opacity-90"
          >
            تطبيق
          </button>
        </FilterSection>
      )}
    </div>
  );
}

export const StoreFacetFilters: React.FC<StoreFacetFiltersProps> = ({ facets, priceRange, catalog }) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* الحاسوب — عمودٌ لاصقٌ عند التمرير على جهة البدء (يمين الشاشة في RTL). */}
      <aside className="hidden w-64 shrink-0 lg:block">
        <div className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto rounded-3xl border border-slate-200/80 bg-white/90 p-4 shadow-sm backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/90">
          <FilterBody facets={facets} priceRange={priceRange} catalog={catalog} />
        </div>
      </aside>

      {/* الجوّال — زرٌّ يفتح درجاً سفلياً، لا شريط جانبيّ مضغوط. */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        className="inline-flex h-10 items-center gap-1.5 rounded-2xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 shadow-sm lg:hidden dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
      >
        <SlidersHorizontal className="h-4 w-4" />
        <span>تصفية{catalog.activeFacetCount > 0 ? ` (${formatNumber(catalog.activeFacetCount)})` : ""}</span>
      </button>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" dir="rtl">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-3xl bg-white p-4 shadow-2xl dark:bg-slate-900">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-black text-slate-900 dark:text-white">الفلاتر</h3>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <FilterBody facets={facets} priceRange={priceRange} catalog={catalog} />
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="mt-4 h-11 w-full rounded-2xl bg-[var(--store-primary,#2563eb)] text-xs font-bold text-white"
            >
              عرض النتائج
            </button>
          </div>
        </div>
      )}
    </>
  );
};

/** رقاقاتُ المطبَّق فوق الشبكة مباشرةً — تُنزَع فرداً أو كلّها معاً. */
export const StoreFilterChips: React.FC<{ facets: StoreFacets | null; catalog: UseStoreCatalogResult }> = ({
  facets,
  catalog,
}) => {
  const chips: { key: string; label: string; onRemove: () => void }[] = [];

  catalog.categoryIds.forEach((id) => {
    const name = facets?.categories.find((c) => c.id === id)?.name;
    if (name) chips.push({ key: `cat-${id}`, label: name, onRemove: () => catalog.toggleCategory(id) });
  });
  catalog.brandIds.forEach((id) => {
    const name = facets?.brands.find((b) => b.id === id)?.name;
    if (name) chips.push({ key: `brand-${id}`, label: name, onRemove: () => catalog.toggleBrand(id) });
  });
  if (catalog.onSale) chips.push({ key: "on_sale", label: "مخفّض", onRemove: () => catalog.setOnSale(false) });
  if (catalog.isNew) chips.push({ key: "is_new", label: "جديد", onRemove: () => catalog.setIsNew(false) });
  if (catalog.inStock) chips.push({ key: "in_stock", label: "متوفر", onRemove: () => catalog.setInStock(false) });
  if (catalog.minPrice || catalog.maxPrice) {
    chips.push({
      key: "price",
      label: `السعر: ${catalog.minPrice || "٠"} — ${catalog.maxPrice || "∞"}`,
      onRemove: () => catalog.setPriceBounds("", ""),
    });
  }

  if (chips.length === 0) return null;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          onClick={chip.onRemove}
          className="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-[11px] font-bold text-blue-700 transition hover:bg-blue-100 dark:border-blue-900 dark:bg-blue-950/60 dark:text-blue-300"
        >
          <span>{chip.label}</span>
          <X className="h-3 w-3" />
        </button>
      ))}
      <button
        type="button"
        onClick={catalog.clearFilters}
        className="text-[11px] font-bold text-red-600 hover:underline dark:text-red-400"
      >
        مسح الكل
      </button>
    </div>
  );
};

export default StoreFacetFilters;
