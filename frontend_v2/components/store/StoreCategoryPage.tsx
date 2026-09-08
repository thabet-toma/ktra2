/**
 * صفحة الفئة — `/store/<slug>/cat/<id>[-slug]` (THA-166 م٧، قسم د).
 *
 * تتشارك الجسدَ (فلاتر + شبكة) مع الرئيسية عبر `useStoreCatalog`/
 * `StoreFacetFilters`/`StoreCatalogGrid`؛ الرأسُ وحده يختلف: اسمُ الفئة
 * وصورتُها ومسارُ تنقّلٍ (أب ← ابن) — من `GET /categories/<id>/` العامّة
 * (م٧: `facets.categories` في `/products/` لا تنشر `slug`/`image_url`،
 * وهذه النقطة سدُّ فجوةٍ لرأس الصفحة وحده).
 */
import React, { useEffect, useMemo, useState } from "react";
import { ArrowRight, ChevronLeft, MessageCircle, Search, Share2, ShoppingBag, Store as StoreIcon } from "lucide-react";

import { useStoreCart } from "../../contexts/StoreCartContext";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDescription, useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  getStoreCategory,
  getStoreProfile,
  isStoreNotFound,
  STORE_SORTS,
  type StoreCategoryDetail,
  type StoreProfile,
} from "../../services/storeApi";
import { parseLeadingId, whatsappLink } from "../../utils/storeLinks";
import { StoreCartDrawer } from "./StoreCartDrawer";
import { StoreCatalogGrid } from "./StoreCatalogGrid";
import { StoreFacetFilters, StoreFilterChips } from "./StoreFacetFilters";
import { storeThemeStyle } from "./storeTheme";
import { useStoreCatalog } from "./useStoreCatalog";

interface StoreCategoryPageProps {
  slug: string;
  categoryParam: string;
  onOpenProduct: (productId: number, name?: string) => void;
  onBack: () => void;
}

export const StoreCategoryPage: React.FC<StoreCategoryPageProps> = ({
  slug,
  categoryParam,
  onOpenProduct,
  onBack,
}) => {
  const toast = useToast();
  const { totalCount, setIsCartOpen } = useStoreCart();
  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [missing, setMissing] = useState(false);
  const [category, setCategory] = useState<StoreCategoryDetail | null>(null);
  const [categoryLoading, setCategoryLoading] = useState(true);
  const [categoryNotFound, setCategoryNotFound] = useState(false);

  const categoryId = useMemo(() => {
    const raw = parseLeadingId(decodeURIComponent(categoryParam || ""));
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  }, [categoryParam]);

  const catalog = useStoreCatalog(slug, {
    initialCategoryIds: categoryId !== null ? [categoryId] : [],
  });

  useEffect(() => {
    let alive = true;
    getStoreProfile(slug)
      .then((data) => {
        if (alive) setProfile(data);
      })
      .catch((e: unknown) => {
        if (alive && isStoreNotFound(e)) setMissing(true);
      });
    return () => {
      alive = false;
    };
  }, [slug]);

  useEffect(() => {
    if (categoryId === null) {
      setCategoryNotFound(true);
      setCategoryLoading(false);
      return;
    }
    let alive = true;
    setCategoryLoading(true);
    setCategoryNotFound(false);
    getStoreCategory(slug, categoryId)
      .then((data) => {
        if (!alive) return;
        setCategory(data);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (isStoreNotFound(e)) setCategoryNotFound(true);
      })
      .finally(() => {
        if (alive) setCategoryLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [slug, categoryId]);

  const storeName = profile?.name || "المتجر";
  const categoryName = category?.name || "";
  useDocumentTitle(categoryName ? `${categoryName} — ${storeName}` : storeName);
  useDocumentDescription(`تصفّح منتجات ${categoryName || "هذه الفئة"} لدى ${storeName}.`);

  const storeWhatsapp = useMemo(
    () => whatsappLink(profile?.phone, `مرحباً ${storeName}، أود الاستفسار عن منتجاتكم.`),
    [profile?.phone, storeName],
  );

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast("تم نسخ رابط الفئة", "success");
    } catch {
      toast("تعذّر النسخ — انسخ الرابط من شريط العنوان", "error");
    }
  };

  if (missing) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 p-6 dark:bg-slate-950 font-sans">
        <div className="w-full max-w-lg rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <StoreIcon className="mx-auto h-14 w-14 text-slate-300 dark:text-slate-600" />
          <h1 className="mt-4 text-xl font-black text-slate-900 dark:text-white">لا يوجد متجر بهذا الرابط</h1>
          <button
            type="button"
            onClick={onBack}
            className="mt-6 inline-block rounded-2xl bg-blue-600 px-6 py-3 text-xs font-bold text-white transition hover:bg-blue-700"
          >
            العودة للرئيسية
          </button>
        </div>
      </div>
    );
  }

  return (
    <div dir="rtl" className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans text-slate-900 dark:text-slate-100" style={storeThemeStyle(profile)}>
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-2 rounded-xl px-2 py-1.5 text-xs font-bold text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <ArrowRight className="h-4 w-4" />
            <span>{storeName}</span>
          </button>
          <div className="flex items-center gap-2">
            {storeWhatsapp && (
              <a
                href={storeWhatsapp}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white shadow-md transition hover:bg-emerald-700"
              >
                <MessageCircle className="h-4 w-4 fill-current" />
                <span className="hidden sm:inline">واتساب</span>
              </a>
            )}
            <button
              type="button"
              onClick={() => void copyLink()}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            >
              <Share2 className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">مشاركة</span>
            </button>
            <button
              type="button"
              onClick={() => setIsCartOpen(true)}
              className="relative inline-flex items-center gap-1.5 rounded-xl bg-[var(--store-primary,#2563eb)] px-3.5 py-2 text-xs font-bold text-white shadow-md transition hover:opacity-90"
            >
              <ShoppingBag className="h-4 w-4" />
              <span className="hidden sm:inline">السلة</span>
              {totalCount > 0 && (
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-black text-white">
                  {totalCount}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* رأسُ صفحة الفئة — اسمٌ وصورةٌ ومسارُ تنقّل (أب ← ابن). */}
      <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6">
        <nav className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
          <button type="button" onClick={onBack} className="hover:text-[var(--store-primary,#2563eb)] hover:underline">
            {storeName}
          </button>
          {category?.parent && (
            <>
              <ChevronLeft className="h-3.5 w-3.5" />
              <span>{category.parent.name}</span>
            </>
          )}
          {categoryName && (
            <>
              <ChevronLeft className="h-3.5 w-3.5" />
              <span className="text-slate-900 dark:text-white">{categoryName}</span>
            </>
          )}
        </nav>
        <div className="flex items-center gap-4">
          {category?.image_url && (
            <img
              src={category.image_url}
              alt={categoryName}
              className="h-16 w-16 shrink-0 rounded-2xl border border-slate-200 object-cover dark:border-slate-800"
            />
          )}
          <h1 className="text-xl font-black text-slate-900 dark:text-white sm:text-2xl">
            {categoryName || (categoryNotFound ? "فئةٌ غير معروفة" : "…")}
          </h1>
        </div>
      </div>

      {categoryNotFound && !categoryLoading ? (
        <div className="py-20 text-center">
          <StoreIcon className="mx-auto h-16 w-16 text-slate-300 dark:text-slate-600" />
          <h2 className="mt-4 text-base font-bold text-slate-700 dark:text-slate-200">هذه الفئة غير متاحة</h2>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">قد يكون الرابط غير صحيح، أو أن الفئة أُزيلت.</p>
          <button
            type="button"
            onClick={onBack}
            className="mt-6 rounded-2xl bg-[var(--store-primary,#2563eb)] px-6 py-2.5 text-xs font-bold text-white transition hover:opacity-90"
          >
            تصفّح المتجر الرئيسي
          </button>
        </div>
      ) : (
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
              <input
                type="search"
                value={catalog.searchInput}
                onChange={(e) => catalog.setSearchInput(e.target.value)}
                placeholder="ابحث ضمن هذه الفئة…"
                aria-label="بحث ضمن الفئة"
                className="h-10 w-full rounded-2xl border border-slate-200 bg-slate-50 ps-10 pe-4 text-xs text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              />
              <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <select
                value={catalog.sort}
                onChange={(e) => catalog.setSort(e.target.value as typeof catalog.sort)}
                aria-label="ترتيب النتائج"
                className="h-10 rounded-2xl border border-slate-200 bg-slate-50 px-3 text-xs font-bold text-slate-700 focus:border-blue-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              >
                {STORE_SORTS.map((option) => (
                  <option key={option.key} value={option.key}>{option.label}</option>
                ))}
              </select>
              <StoreFacetFilters facets={catalog.facets} priceRange={catalog.priceRange} currency={profile?.currency ?? null} catalog={catalog} />
            </div>
          </div>

          <StoreFilterChips facets={catalog.facets} catalog={catalog} />

          <StoreCatalogGrid
            products={catalog.products}
            count={catalog.count}
            currency={profile?.currency ?? null}
            loading={catalog.loading}
            loadingMore={catalog.loadingMore}
            hasNext={catalog.hasNext}
            error={catalog.error}
            filtersActive={catalog.filtersActive}
            onOpenProduct={onOpenProduct}
            onLoadMore={() => void catalog.loadMore()}
            onClearFilters={catalog.clearFilters}
            slug={slug}
            storePhone={profile?.phone}
          />
        </main>
      )}

      <StoreCartDrawer storeName={storeName} storePhone={profile?.phone} currency={profile?.currency ?? null} />
    </div>
  );
};

export default StoreCategoryPage;
