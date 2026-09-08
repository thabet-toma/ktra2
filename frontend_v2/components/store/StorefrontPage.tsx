/**
 * واجهة متجر شركة واحدة — `/store/<slug>`
 *
 * مظهر مخصص، شريط إعلانات، مجموعات وحملات، وضع الشرائح / الكتالوج، وسلة مشتريات تفاعلية.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Flame,
  Layers,
  MapPin,
  Megaphone,
  MessageCircle,
  Search,
  Share2,
  ShoppingBag,
  Store as StoreIcon,
} from "lucide-react";

import { useStoreCart } from "../../contexts/StoreCartContext";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDescription, useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  getStoreCollections,
  getStoreHome,
  getStoreProfile,
  isStoreNotFound,
  STORE_SORTS,
  type StoreCollection,
  type StoreHomeBlock,
  type StoreProfile,
} from "../../services/storeApi";
import { whatsappLink } from "../../utils/storeLinks";
import { StoreCartDrawer } from "./StoreCartDrawer";
import { StoreCatalogGrid } from "./StoreCatalogGrid";
import { StoreCatalogSlider } from "./StoreCatalogSlider";
import { StoreFacetFilters, StoreFilterChips } from "./StoreFacetFilters";
import { StoreHomeBlocks } from "./StoreHomeBlocks";
import { storeThemeStyle } from "./storeTheme";
import { useStoreCatalog } from "./useStoreCatalog";

interface StorefrontPageProps {
  slug: string;
  onOpenProduct: (productId: number, name?: string) => void;
  onOpenCollection?: (collectionSlug: string) => void;
  onOpenCategory?: (categoryId: number) => void;
}

export const StorefrontPage: React.FC<StorefrontPageProps> = ({
  slug,
  onOpenProduct,
  onOpenCollection,
  onOpenCategory,
}) => {
  const toast = useToast();
  const { totalCount, setIsCartOpen } = useStoreCart();

  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [collections, setCollections] = useState<StoreCollection[]>([]);
  const [homeBlocks, setHomeBlocks] = useState<StoreHomeBlock[]>([]);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // وضع العرض (شبكة أم كتالوج شرائح)
  const [viewMode, setViewMode] = useState<"grid" | "slideshow">("grid");

  const catalog = useStoreCatalog(slug);

  const storeName = profile?.name || "المتجر";
  useDocumentTitle(profile ? `${storeName} — المتجر الإلكتروني` : "المتجر الإلكتروني");
  useDocumentDescription(
    profile
      ? (profile.hero_subtitle || `تصفّح منتجات ${storeName} وأسعارها${profile.address ? ` — ${profile.address}` : ""}. للطلب تواصل معنا مباشرة.`)
      : "متجر إلكتروني على منصة K.T.R.A.",
  );

  useEffect(() => {
    let alive = true;
    setProfile(null);
    Promise.all([
      getStoreProfile(slug),
      getStoreCollections(slug)
        .then((paged) => paged.results)
        .catch(() => [] as StoreCollection[]),
      // كتلُ الصفحة الرئيسية تحسينٌ اختياري — فشلُها لا يعطّل فتح المتجر،
      // وحمولةٌ غير متوقّعة الشكل تسقط إلى فراغ بدل كسر التصيير (قاعدة السقوط).
      getStoreHome(slug)
        .then((payload) => (Array.isArray(payload?.blocks) ? payload.blocks : []))
        .catch(() => [] as StoreHomeBlock[]),
    ])
      .then(([profData, colsData, blocksData]) => {
        if (!alive) return;
        setProfile(profData);
        setCollections(colsData);
        setHomeBlocks(blocksData);
        if (profData.catalog_mode_default === "slideshow") {
          setViewMode("slideshow");
        }
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (isStoreNotFound(e)) setMissing(true);
        else setError(e instanceof Error ? e.message : "تعذّر فتح المتجر");
      });
    return () => {
      alive = false;
    };
  }, [slug]);

  const copyStoreLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast("تم نسخ رابط المتجر", "success");
    } catch {
      toast("تعذّر النسخ — انسخ الرابط من شريط العنوان", "error");
    }
  }, [toast]);

  const storeWhatsapp = useMemo(
    () => whatsappLink(profile?.phone, `مرحباً ${storeName}، أود الاستفسار عن منتجاتكم.`),
    [profile?.phone, storeName],
  );

  if (missing || catalog.missing) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 p-6 dark:bg-slate-950 font-sans">
        <div className="w-full max-w-lg rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <StoreIcon className="mx-auto h-14 w-14 text-slate-300 dark:text-slate-600" />
          <h1 className="mt-4 text-xl font-black text-slate-900 dark:text-white">لا يوجد متجر بهذا الرابط</h1>
          <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
            الرابط الذي فتحته (<span className="font-mono">/store/{slug}</span>) لا يقود إلى متجر مفتوح.
            تأكّد من نسخه كاملاً كما وصلك، أو اطلب من الشركة رابط متجرها من جديد.
          </p>
          <a
            href="/"
            className="mt-6 inline-block rounded-2xl bg-blue-600 px-6 py-3 text-xs font-bold text-white transition hover:bg-blue-700"
          >
            العودة للرئيسية
          </a>
        </div>
      </div>
    );
  }

  // إذا تم تفعيل وضع الكتالوج بالشرائح
  if (viewMode === "slideshow" && catalog.products.length > 0) {
    return (
      <StoreCatalogSlider
        products={catalog.products}
        profile={profile}
        slug={slug}
        onCloseCatalog={() => setViewMode("grid")}
        onOpenProductDetail={onOpenProduct}
      />
    );
  }

  return (
    <div
      dir="rtl"
      className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans text-slate-900 dark:text-slate-100"
      style={storeThemeStyle(profile)}
    >
      {/* شريط الإعلانات الترويجي العلوي */}
      {profile?.show_announcement && profile?.announcement_bar && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-center text-xs font-bold text-white shadow-sm flex items-center justify-center gap-2">
          <Megaphone className="h-3.5 w-3.5" />
          <span>{profile.announcement_bar}</span>
        </div>
      )}

      {/* الترويسة الأنيقة */}
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/90">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            {profile?.logo_url ? (
              <img
                src={profile.logo_url}
                alt={storeName}
                className="h-11 w-11 rounded-2xl object-cover border border-slate-200 dark:border-slate-700"
              />
            ) : (
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--store-primary,#2563eb)] text-white shadow-md">
                <StoreIcon className="h-6 w-6" />
              </div>
            )}
            <div>
              <h1 className="text-base font-black text-slate-900 dark:text-white leading-tight">
                {storeName}
              </h1>
              {profile?.address && (
                <p className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
                  <MapPin className="h-3 w-3" />
                  <span className="truncate max-w-[180px] sm:max-w-xs">{profile.address}</span>
                </p>
              )}
            </div>
          </div>

          {/* الأزرار العلوية */}
          <div className="flex items-center gap-2">
            {/* زر تبديل لوضع الكتالوج بالشرائح */}
            <button
              type="button"
              onClick={() => setViewMode("slideshow")}
              className="hidden sm:inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
              title="عرض الكتالوج بالشرائح التفاعلية"
            >
              <Layers className="h-4 w-4 text-blue-500" />
              <span>وضع الكتالوج</span>
            </button>

            {storeWhatsapp ? (
              <a
                href={storeWhatsapp}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white shadow-md shadow-emerald-600/20 transition hover:bg-emerald-700"
              >
                <MessageCircle className="h-4 w-4 fill-current" />
                <span className="hidden sm:inline">واتساب</span>
              </a>
            ) : null}

            <button
              type="button"
              onClick={() => void copyStoreLink()}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
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

      {/* البانر الترويجي والعنوان المميز */}
      {profile?.banner_image_url && (
        <div className="mx-auto max-w-7xl px-4 pt-4 sm:px-6">
          <div className="relative overflow-hidden rounded-3xl border border-slate-200 shadow-sm dark:border-slate-800">
            <img
              src={profile.banner_image_url}
              alt={storeName}
              className="h-36 w-full object-cover sm:h-56 md:h-72"
            />
          </div>
        </div>
      )}

      {/* الترحيب والعنوان الرئيسي */}
      {(profile?.hero_title || profile?.hero_subtitle) && (
        <div className="mx-auto max-w-7xl px-4 pt-6 text-center sm:px-6">
          {profile.hero_title && (
            <h2 className="text-xl font-black text-slate-900 dark:text-white sm:text-3xl">
              {profile.hero_title}
            </h2>
          )}
          {profile.hero_subtitle && (
            <p className="mx-auto mt-2 max-w-2xl text-xs sm:text-sm text-slate-600 dark:text-slate-400">
              {profile.hero_subtitle}
            </p>
          )}
        </div>
      )}

      {/* شريط المجموعات والحملات الإعلانية (Campaigns / Collections Bar) */}
      {collections.length > 0 && (
        <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6">
          <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none">
            <span className="shrink-0 text-xs font-bold text-slate-500 dark:text-slate-400">
              المجموعات المميزة:
            </span>
            {collections.map((col) => (
              <button
                key={col.id}
                type="button"
                onClick={() => {
                  if (onOpenCollection) {
                    onOpenCollection(col.slug);
                  } else {
                    window.location.href = `/store/${encodeURIComponent(slug)}/c/${encodeURIComponent(col.slug)}`;
                  }
                }}
                className="group shrink-0 flex items-center gap-1.5 rounded-2xl border border-slate-200 bg-white/90 px-3.5 py-1.5 text-xs font-bold text-slate-700 shadow-sm backdrop-blur transition hover:border-blue-500 hover:bg-blue-50/60 dark:border-slate-800 dark:bg-slate-900/90 dark:text-slate-200 dark:hover:border-blue-500"
              >
                {col.badge_text ? (
                  <span className="flex items-center gap-1 rounded-full bg-amber-100 px-1.5 py-0.2 text-[10px] font-bold text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                    <Flame className="h-3 w-3 fill-current" />
                    {col.badge_text}
                  </span>
                ) : null}
                <span>{col.title}</span>
                <span className="rounded-full bg-slate-100 px-1.5 text-[10px] text-slate-500 dark:bg-slate-800">
                  {col.items_count}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* كتلُ الصفحة الرئيسية — فوق الشبكة القائمة، والشبكةُ تبقى تحتها كما هي */}
      <StoreHomeBlocks
        blocks={homeBlocks}
        profile={profile}
        onOpenProduct={onOpenProduct}
        onOpenCollection={onOpenCollection}
        onOpenCategory={onOpenCategory}
      />

      {/* الجسدُ المشترك: فلاتر + شبكة (قسم د) — نفسُه في صفحة الفئة. */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {error && (
          <div role="alert" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-center font-bold text-red-800 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </div>
        )}
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className="relative flex-1 max-w-sm">
            <input
              type="search"
              value={catalog.searchInput}
              onChange={(e) => catalog.setSearchInput(e.target.value)}
              placeholder="ابحث بالاسم أو الماركة…"
              aria-label="بحث في منتجات المتجر"
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
            {catalog.products.length > 0 && (
              <button
                type="button"
                onClick={() => setViewMode("slideshow")}
                className="hidden items-center gap-1 text-xs font-bold text-[var(--store-primary,#2563eb)] hover:underline sm:inline-flex"
              >
                <Layers className="h-3.5 w-3.5" />
                <span>شرائح</span>
              </button>
            )}
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

      {/* تذييل الصفحة مع روابط السوشيال ميديا */}
      <footer className="mt-16 border-t border-slate-200/80 bg-white/80 py-8 text-center text-xs text-slate-500 backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/80 dark:text-slate-400">
        <div className="mx-auto max-w-7xl px-4 space-y-3">
          {/* أيقونات السوشيال ميديا إذا وُجدت */}
          {(profile?.instagram_url || profile?.tiktok_url || profile?.facebook_url || profile?.snapchat_url) && (
            <div className="flex justify-center gap-4 py-2">
              {profile.instagram_url && (
                <a href={profile.instagram_url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-pink-600 transition">
                  Instagram
                </a>
              )}
              {profile.tiktok_url && (
                <a href={profile.tiktok_url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-black dark:hover:text-white transition">
                  TikTok
                </a>
              )}
              {profile.facebook_url && (
                <a href={profile.facebook_url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-blue-600 transition">
                  Facebook
                </a>
              )}
              {profile.snapchat_url && (
                <a href={profile.snapchat_url} target="_blank" rel="noopener noreferrer" className="text-slate-500 hover:text-amber-500 transition">
                  Snapchat
                </a>
              )}
            </div>
          )}

          <p>{storeName} — الأسعار والتوفّر قابلة للتغيير. للطلب تواصل مع المتجر مباشرة.</p>
          <p>
            متجر مدعوم بنظام <a href="/" className="font-bold text-blue-600 hover:underline dark:text-blue-400">K.T.R.A</a>
          </p>
        </div>
      </footer>

      {/* درج السلة التفاعلي */}
      <StoreCartDrawer
        storeName={storeName}
        storePhone={profile?.phone}
        currency={profile?.currency ?? null}
      />
    </div>
  );
};

export default StorefrontPage;

