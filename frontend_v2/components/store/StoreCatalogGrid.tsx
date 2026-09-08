/**
 * شبكةُ المنتجات المشتركة + حالتا التحميل واللانتائج (THA-166 م٧، قسم هـ).
 * لا استيراد من `components/kit`.
 */
import React from "react";
import { Store as StoreIcon } from "lucide-react";
import { LoadingSpinner } from "../LoadingSpinner";
import { storeProductName, type StoreProduct } from "../../services/storeApi";
import { formatNumber } from "../../utils/formatNumber";
import { productWhatsappHref } from "../../utils/storeLinks";
import { StoreProductCard } from "./StoreProductCard";

interface StoreCatalogGridProps {
  products: StoreProduct[];
  count: number;
  currency: string | null;
  loading: boolean;
  loadingMore: boolean;
  hasNext: boolean;
  error: string | null;
  filtersActive: boolean;
  onOpenProduct: (productId: number, name?: string) => void;
  onLoadMore: () => void;
  onClearFilters: () => void;
  /** لبناء رابط واتساب حين يكون السعر مخفياً — يصير الفعل الأساسي في البطاقة (قسم هـ). */
  slug?: string;
  storePhone?: string | null;
}

export const StoreCatalogGrid: React.FC<StoreCatalogGridProps> = ({
  products,
  count,
  currency,
  loading,
  loadingMore,
  hasNext,
  error,
  filtersActive,
  onOpenProduct,
  onLoadMore,
  onClearFilters,
  slug,
  storePhone,
}) => {
  if (error) {
    return (
      <div role="alert" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-center font-bold text-red-800 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
        {error}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <LoadingSpinner showText={false} />
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="py-20 text-center">
        <StoreIcon className="mx-auto h-16 w-16 text-slate-300 dark:text-slate-600" />
        <h2 className="mt-4 text-base font-bold text-slate-700 dark:text-slate-200">
          {filtersActive ? "لا نتائج مطابقة" : "لا توجد منتجات معروضة بعد"}
        </h2>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          {filtersActive ? "جرّب تخفيف معايير البحث أو الفلاتر المختارة." : "هذا المتجر لم ينشر منتجات حتى الآن — عُد لاحقاً."}
        </p>
        {filtersActive && (
          <button
            type="button"
            onClick={onClearFilters}
            className="mt-6 rounded-2xl bg-[var(--store-primary,#2563eb)] px-6 py-2.5 text-xs font-bold text-white transition hover:opacity-90"
          >
            امسح الفلاتر
          </button>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 text-xs font-bold text-slate-500 dark:text-slate-400">
        عرض {formatNumber(products.length)} من {formatNumber(count)} منتجاً
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-6 lg:grid-cols-3 xl:grid-cols-4">
        {products.map((product) => {
          const name = storeProductName(product);
          const whatsappHref =
            product.price == null && slug
              ? productWhatsappHref(window.location.origin, storePhone, slug, product.id, name)
              : null;
          return (
            <StoreProductCard
              key={product.id}
              product={product}
              currency={currency}
              whatsappHref={whatsappHref}
              onOpen={(item) => onOpenProduct(item.id, name)}
            />
          );
        })}
      </div>

      {hasNext && (
        <div className="mt-10 text-center">
          <button
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
            className="rounded-2xl border-2 border-[var(--store-primary,#2563eb)] bg-white px-8 py-3 text-xs font-bold text-[var(--store-primary,#2563eb)] shadow-sm transition hover:opacity-90 disabled:opacity-60 dark:bg-slate-900"
          >
            {loadingMore ? "جارٍ التحميل…" : "عرض المزيد من المنتجات"}
          </button>
        </div>
      )}
    </>
  );
};

export default StoreCatalogGrid;
