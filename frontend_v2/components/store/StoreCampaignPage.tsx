/**
 * صفحة الهبوط الإعلانية للحملات والمجموعات — `/store/<slug>/c/<collectionSlug>`
 *
 * مخصصة لروابط الحملات الإعلانية على TikTok و Meta و WhatsApp و Snapchat.
 */
import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Copy,
  ExternalLink,
  Flame,
  ImageOff,
  MessageCircle,
  Share2,
  ShoppingBag,
  Sparkles,
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
  StoreCollectionDetail,
  StoreProduct,
  storeProductName,
  StoreProfile,
} from "../../services/storeApi";
import { productInquiryMessage, whatsappLink } from "../../utils/storeLinks";
import { StoreCartDrawer } from "./StoreCartDrawer";
import { StoreAvailabilityBadge, StorePrice, StoreProductCard } from "./StoreProductCard";
import { StoreImageOverlay } from "./StoreImageOverlay";

interface StoreCampaignPageProps {
  slug: string;
  collectionSlug: string;
  onNavigateHome: () => void;
  onOpenProduct: (productId: number) => void;
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
  const [products, setProducts] = useState<StoreProduct[]>([]);
  const [activeImageIdx, setActiveImageIdx] = useState(0);

  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const storeName = profile?.name || "المتجر";
  const campaignTitle = collection?.title || "عرض خاص";

  useDocumentTitle(`${campaignTitle} — ${storeName}`);
  useDocumentDescription(
    collection?.description || `تصفح عرض ${campaignTitle} الحصري لدى ${storeName}`,
  );

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setMissing(false);
    setError(null);

    Promise.all([
      getStoreProfile(slug),
      getStoreCollectionDetail(slug, collectionSlug),
    ])
      .then(([prof, campData]) => {
        if (!alive) return;
        setProfile(prof);
        setCollection(campData.collection);
        setProducts(campData.products.results);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (isStoreNotFound(e)) setMissing(true);
        else setError(e instanceof Error ? e.message : "تعذّر تحميل صفحة العرض");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [slug, collectionSlug]);

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

  if (loading) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-950 text-white">
        <LoadingSpinner showText={false} />
      </div>
    );
  }

  if (missing || !collection) {
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
  const isSingleProductLanding = Boolean(featured && products.length <= 1);
  const featuredImages = featured?.images || [];
  const activeFeaturedImage = featuredImages[activeImageIdx] || featuredImages[0] || null;

  const featuredInquiryUrl = featured
    ? whatsappLink(
        profile?.phone,
        productInquiryMessage(storeProductName(featured), window.location.href),
      )
    : null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-blue-600 selection:text-white" dir="rtl">
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
              className="relative flex items-center gap-1.5 rounded-xl bg-blue-600 px-3 py-1.5 text-xs font-bold text-white shadow-lg shadow-blue-600/30 transition hover:bg-blue-700"
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
                    <div className="flex h-full w-full items-center justify-center text-slate-600">
                      <ImageOff className="h-16 w-16" />
                    </div>
                  )}
                  {/* شريط الإعلان المخصص */}
                  {activeImageIdx === 0 && (
                    <StoreImageOverlay overlay={featured.cover_overlay} />
                  )}

                  <div className="absolute top-3 left-3">
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

                  <div className="mt-4 flex items-baseline gap-3">
                    <StorePrice
                      price={featured.price}
                      currency={profile?.currency ?? null}
                      onDark
                      className="text-3xl"
                    />
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
                    className="flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3.5 text-xs font-bold text-white shadow-lg shadow-blue-600/30 transition hover:bg-blue-700 active:scale-95"
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
          /* في حال تشكيلة منتجات الحملة */
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 sm:gap-6">
              {products.map((p) => (
                <StoreProductCard
                  key={p.id}
                  product={p}
                  currency={profile?.currency ?? null}
                  onClick={() => onOpenProduct(p.id)}
                />
              ))}
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
      />
    </div>
  );
};
