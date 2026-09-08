/**
 * صفحة الهبوط الإعلانية للحملات والمجموعات — `/store/<slug>/c/<collectionSlug>`
 *
 * مخصصة لروابط الحملات الإعلانية على TikTok و Meta و WhatsApp و Snapchat.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Flame,
  MessageCircle,
  Search,
  Share2,
  ShoppingBag,
  Store,
} from "lucide-react";
import { LoadingSpinner } from "../LoadingSpinner";
import { useStoreCart } from "../../contexts/StoreCartContext";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDescription, useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  getStoreCollectionDetail,
  getStoreProfile,
  isStoreNotFound,
  STORE_SORTS,
  StoreCollectionDetail,
  storeProductName,
  StoreProfile,
  type StoreProductQuery,
  type StoreSort,
} from "../../services/storeApi";
import { campaignCountdown } from "../../utils/campaignCountdown";
import { formatNumber } from "../../utils/formatNumber";
import { productInquiryMessage, whatsappLink } from "../../utils/storeLinks";
import { StoreCartDrawer } from "./StoreCartDrawer";
import { StoreCatalogGrid } from "./StoreCatalogGrid";
import { StoreFacetFilters, StoreFilterChips } from "./StoreFacetFilters";
import { StoreAvailabilityBadge, StorePrice } from "./StoreProductCard";
import { StoreImageOverlay } from "./StoreImageOverlay";
import { StoreImagePlaceholder } from "./StoreImagePlaceholder";
import { storeColorVars } from "./storeTheme";
import { useStoreCatalog } from "./useStoreCatalog";

interface StoreCampaignPageProps {
  slug: string;
  collectionSlug: string;
  onNavigateHome: () => void;
  onOpenProduct: (productId: number, name?: string) => void;
}

export const StoreCampaignPage: React.FC<StoreCampaignPageProps> = ({
  slug,
  collectionSlug,
  onNavigateHome,
  onOpenProduct,
}) => {
  const toast = useToast();
  const { addItem, totalCount, setIsCartOpen } = useStoreCart();

  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [collection, setCollection] = useState<StoreCollectionDetail | null>(null);
  const [activeImageIdx, setActiveImageIdx] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  // دالّةُ جلبٍ محقونة في `useStoreCatalog` المشتركة — تحلّ محلّ نسخةٍ يدويّة
  // من `load`/`loadMore`/الـdebounce كانت مستقلّة هنا وحدها (THA-166 م٧،
  // تصحيحٌ بعد المراجعة: كانت الصفحاتُ الثلاث تتباعد فعلاً). `StoreCollectionDetailView`
  // يبني الآن `facets`/`price_range` بنفس دوالّ `StoreProductListView`، فشريط
  // الفلاتر يعمل هنا كما في الرئيسية والفئة تماماً.
  const fetchCampaignProducts = useCallback(
    (query: StoreProductQuery) =>
      getStoreCollectionDetail(slug, collectionSlug, query).then((campData) => {
        setCollection(campData.collection);
        return campData.products;
      }),
    [slug, collectionSlug],
  );
  const catalog = useStoreCatalog(slug, { fetcher: fetchCampaignProducts });

  const storeName = profile?.name || "المتجر";
  const campaignTitle = collection?.title || "عرض خاص";

  useDocumentTitle(`${campaignTitle} — ${storeName}`);
  useDocumentDescription(
    collection?.description || `تصفح عرض ${campaignTitle} الحصري لدى ${storeName}`,
  );

  useEffect(() => {
    let alive = true;
    getStoreProfile(slug)
      .then((prof) => {
        if (alive) setProfile(prof);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [slug]);

  // العدّادُ حيٌّ — تحديثٌ كل دقيقة يكفي (ليس عرض ثوانٍ)، ولا يستهلك فحصاً كثيفاً.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const countdown = useMemo(
    () => campaignCountdown(collection?.ends_at, now),
    [collection?.ends_at, now],
  );

  const handleShare = async () => {
    const url = window.location.href;
    if (navigator.share) {
      try {
        await navigator.share({
          title: campaignTitle,
          text: collection?.description || undefined,
          url,
        });
      } catch {
        // تجاهل
      }
    } else {
      try {
        await navigator.clipboard.writeText(url);
        toast("تم نسخ رابط العرض للمشاركة", "success");
      } catch {
        toast("تعذّر النسخ", "error");
      }
    }
  };

  if (catalog.loading && !collection) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-950 text-white">
        <LoadingSpinner showText={false} />
      </div>
    );
  }

  if (catalog.missing || !collection) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white font-sans">
        <div className="w-full max-w-md rounded-3xl bg-slate-900 p-8 text-center shadow-2xl border border-slate-800">
          <h1 className="text-xl font-black text-white">هذا العرض غير متاح حالياً</h1>
          <p className="mt-3 text-xs leading-relaxed text-slate-400">
            قد تكون الحملة الإعلانية قد انتهت، أو أن الرابط غير صحيح.
          </p>
          <button
            type="button"
            onClick={onNavigateHome}
            className="mt-6 rounded-2xl bg-blue-600 px-6 py-3 text-xs font-bold text-white transition hover:bg-blue-700"
          >
            تصفح المتجر الرئيسي
          </button>
        </div>
      </div>
    );
  }

  const featured = collection.featured_product;
  const isSingleProductLanding = Boolean(featured && catalog.products.length <= 1);
  const featuredImages = featured?.images || [];
  const activeFeaturedImage = featuredImages[activeImageIdx] || featuredImages[0] || null;

  const featuredInquiryUrl = featured
    ? whatsappLink(
        profile?.phone,
        productInquiryMessage(storeProductName(featured), window.location.href),
      )
    : null;

  return (
    <div
      className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-blue-600 selection:text-white"
      dir="rtl"
      style={storeColorVars(profile)}
    >
      {/* الترويسة الأنيقة */}
      <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onNavigateHome}
              className="flex items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-bold text-slate-300 transition hover:bg-slate-800 hover:text-white"
            >
              <Store className="h-4 w-4 text-blue-400" />
              <span>{storeName}</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleShare}
              className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-bold text-slate-300 transition hover:bg-slate-800 hover:text-white"
            >
              <Share2 className="h-3.5 w-3.5" />
              <span>مشاركة</span>
            </button>

            <button
              type="button"
              onClick={() => setIsCartOpen(true)}
              className="relative flex items-center gap-1.5 rounded-xl bg-[var(--store-primary,#2563eb)] px-3 py-1.5 text-xs font-bold text-white shadow-lg transition hover:opacity-90"
            >
              <ShoppingBag className="h-4 w-4" />
              <span>السلة</span>
              {totalCount > 0 && (
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-black text-white">
                  {totalCount}
                </span>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* محتوى الحملة */}
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
        {/* البانر الإعلاني العلوي */}
        {collection.banner_image_url && (
          <div className="mb-8 overflow-hidden rounded-3xl border border-slate-800 shadow-2xl">
            <img
              src={collection.banner_image_url}
              alt={campaignTitle}
              className="h-48 w-full object-cover sm:h-72"
            />
          </div>
        )}

        {/* عنوان الحملة والبادج */}
        <div className="mb-8 text-center sm:mb-12">
          {collection.badge_text && (
            <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-amber-500/20 to-rose-500/20 border border-amber-500/30 px-4 py-1 text-xs font-black text-amber-400">
              <Flame className="h-3.5 w-3.5 text-amber-500 fill-amber-500" />
              <span>{collection.badge_text}</span>
            </div>
          )}
          <h1 className="text-2xl font-black text-white sm:text-4xl">
            {campaignTitle}
          </h1>
          {collection.description && (
            <p className="mx-auto mt-3 max-w-2xl text-xs sm:text-sm text-slate-400 leading-relaxed">
              {collection.description}
            </p>
          )}
          {/* عدّادُ الانتهاء — يختفي حين لا `ends_at`، أو انتهت الحملة، أو
              تجاوزت مدّةً معقولة (لا تاريخ بدءٍ يُعرَض أبداً، THA-166 م٧). */}
          {countdown && (
            <div className="mx-auto mt-4 inline-flex items-center gap-2 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-xs font-black text-rose-300">
              <Clock className="h-4 w-4" />
              <span>
                {countdown.days > 0
                  ? `ينتهي العرض خلال ${formatNumber(countdown.days)} يوم و${formatNumber(countdown.hours)} ساعة`
                  : `ينتهي العرض خلال ${formatNumber(countdown.hours)} ساعة و${formatNumber(countdown.minutes)} دقيقة`}
              </span>
            </div>
          )}
        </div>

        {/* إذا كانت الحملة لمنتج واحد مميز (Single Product Ad Landing) */}
        {isSingleProductLanding && featured ? (
          <div className="mx-auto max-w-4xl overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/90 shadow-2xl p-6 sm:p-10">
            <div className="grid grid-cols-1 gap-8 md:grid-cols-2 items-center">
              {/* معرض الصور */}
              <div className="space-y-3">
                <div className="relative aspect-square w-full rounded-2xl bg-slate-950 overflow-hidden border border-slate-800">
                  {activeFeaturedImage ? (
                    <img
                      src={activeFeaturedImage}
                      alt={storeProductName(featured)}
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <StoreImagePlaceholder name={storeProductName(featured)} className="bg-slate-900" />
                  )}
                  {/* شريط الإعلان المخصص */}
                  {activeImageIdx === 0 && (
                    <StoreImageOverlay overlay={featured.cover_overlay} />
                  )}

                  <div className="absolute top-3 start-3">
                    <StoreAvailabilityBadge availability={featured.availability} />
                  </div>
                </div>

                {featuredImages.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto pb-1">
                    {featuredImages.map((img, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => setActiveImageIdx(idx)}
                        className={`h-16 w-16 shrink-0 rounded-xl overflow-hidden border-2 transition ${
                          idx === activeImageIdx ? "border-blue-500" : "border-slate-800 opacity-60"
                        }`}
                      >
                        <img src={img} alt="" className="h-full w-full object-cover" />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* تفاصيل المنتج والعرض */}
              <div className="flex flex-col justify-between space-y-6">
                <div>
                  {featured.brand && (
                    <span className="text-xs font-bold text-blue-400">
                      {featured.brand}
                    </span>
                  )}
                  <h2 className="text-xl font-black text-white sm:text-2xl mt-1">
                    {storeProductName(featured)}
                  </h2>

                  <div className="mt-4 flex flex-wrap items-baseline gap-3">
                    <StorePrice
                      price={featured.price}
                      currency={profile?.currency ?? null}
                      onDark
                      discounted={Boolean(featured.original_price)}
                      className="text-3xl"
                    />
                    {featured.original_price ? (
                      <span className="text-base font-semibold text-slate-500 line-through">
                        {formatNumber(featured.original_price, { maxDecimals: 2, group: true })} {profile?.currency ?? ""}
                      </span>
                    ) : null}
                    {featured.discount_percent ? (
                      <span className="rounded-full bg-rose-600 px-2.5 py-1 text-xs font-black text-white">
                        خصم {formatNumber(featured.discount_percent)}٪
                      </span>
                    ) : null}
                  </div>

                  {featured.description && (
                    <p className="mt-4 text-xs sm:text-sm text-slate-300 leading-relaxed">
                      {featured.description}
                    </p>
                  )}

                  {/* مميزات سريعة */}
                  <div className="mt-6 space-y-2 border-t border-slate-800 pt-4">
                    <div className="flex items-center gap-2 text-xs text-slate-300">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span>ضمان الجودة وأصالة المنتج ١٠٠٪</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-300">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span>توصيل سريع مع إمكانية المعاينة عند الاستلام</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-300">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      <span>خدمة عملاء مباشرة ومتابعة مستمرة</span>
                    </div>
                  </div>
                </div>

                {/* أزرار الإجراء */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 pt-2">
                  <button
                    type="button"
                    onClick={() => addItem(featured, 1)}
                    className="flex items-center justify-center gap-2 rounded-2xl bg-[var(--store-primary,#2563eb)] px-5 py-3.5 text-xs font-bold text-white shadow-lg transition hover:opacity-90 active:scale-95"
                  >
                    <ShoppingBag className="h-4 w-4" />
                    <span>أضف إلى السلة</span>
                  </button>

                  {featuredInquiryUrl && (
                    <a
                      href={featuredInquiryUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-5 py-3.5 text-xs font-bold text-white shadow-lg shadow-emerald-600/30 transition hover:bg-emerald-700 active:scale-95"
                    >
                      <MessageCircle className="h-4 w-4 fill-current" />
                      <span>اطلب الآن عبر واتساب</span>
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* في حال تشكيلة منتجات الحملة — نفس الجسد المشترك (فلاتر + شبكة +
             فرز) الذي تستهلكه الرئيسية والفئة، بعد أن صار `StoreCollectionDetailView`
             يبني `facets`/`price_range` مقيَّدةً بمنتجات هذه الحملة وحدها. */
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
            <StoreFacetFilters
              facets={catalog.facets}
              priceRange={catalog.priceRange}
              currency={profile?.currency ?? null}
              catalog={catalog}
            />
            <div className="min-w-0 flex-1 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="relative max-w-xs flex-1">
                  <input
                    type="search"
                    value={catalog.searchInput}
                    onChange={(e) => catalog.setSearchInput(e.target.value)}
                    placeholder="ابحث ضمن العرض…"
                    aria-label="بحث ضمن منتجات العرض"
                    className="h-10 w-full rounded-2xl border border-slate-800 bg-slate-900 ps-10 pe-4 text-xs text-white placeholder:text-slate-500 focus:border-[var(--store-primary,#2563eb)] focus:outline-none"
                  />
                  <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                </div>
                <select
                  value={catalog.sort}
                  onChange={(e) => catalog.setSort(e.target.value as StoreSort)}
                  aria-label="ترتيب النتائج"
                  className="h-10 rounded-2xl border border-slate-800 bg-slate-900 px-3 text-xs font-bold text-slate-200 focus:border-[var(--store-primary,#2563eb)] focus:outline-none"
                >
                  {STORE_SORTS.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
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
            </div>
          </div>
        )}

        {/* تذييل العرض وزر العودة */}
        <div className="mt-16 text-center">
          <button
            type="button"
            onClick={onNavigateHome}
            className="inline-flex items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900 px-6 py-3 text-xs font-bold text-slate-300 transition hover:bg-slate-800 hover:text-white"
          >
            <span>مشاهدة كافة منتجات المتجر</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </main>

      {/* درج السلة التفاعلي */}
      <StoreCartDrawer
        storeName={storeName}
        storePhone={profile?.phone}
        currency={profile?.currency ?? null}
        collectionSlug={collectionSlug}
      />
    </div>
  );
};
