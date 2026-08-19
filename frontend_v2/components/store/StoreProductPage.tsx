/**
 * صفحة صنف واحد — `/store/<slug>/p/<id>`
 *
 * معرض صور متعدد، زر إضافة للسلة مع محدد كمية، زر طلب واتساب، ودعم الثيم والطلب المسبق.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Copy,
  ImageOff,
  MessageCircle,
  Minus,
  Plus,
  Share2,
  ShoppingBag,
} from "lucide-react";

import { LoadingSpinner } from "../LoadingSpinner";
import { useStoreCart } from "../../contexts/StoreCartContext";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDescription, useDocumentTitle } from "../../hooks/useDocumentTitle";
import {
  getStoreProduct,
  getStoreProfile,
  isStoreNotFound,
  storeProductName,
  type StoreProduct,
  type StoreProfile,
} from "../../services/storeApi";
import { productInquiryMessage, whatsappLink } from "../../utils/storeLinks";
import { StoreCartDrawer } from "./StoreCartDrawer";
import { StoreAvailabilityBadge, StorePrice } from "./StoreProductCard";
import { StoreImageOverlay } from "./StoreImageOverlay";

interface StoreProductPageProps {
  slug: string;
  productId: string;
  onBack: () => void;
}

export const StoreProductPage: React.FC<StoreProductPageProps> = ({ slug, productId, onBack }) => {
  const toast = useToast();
  const { addItem, totalCount, setIsCartOpen } = useStoreCart();

  const [product, setProduct] = useState<StoreProduct | null>(null);
  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [activeImage, setActiveImage] = useState(0);
  const [quantity, setQuantity] = useState(1);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const name = product ? storeProductName(product) : "";
  const storeName = profile?.name || "المتجر";

  useDocumentTitle(product ? `${name} — ${storeName}` : "المتجر الإلكتروني");
  useDocumentDescription(
    product
      ? (product.description || `${name} — متوفّر لدى ${storeName}. اضغط للتواصل والطلب.`).slice(0, 300)
      : "منتج في متجر على منصة K.T.R.A.",
  );

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setMissing(false);
    setError(null);
    setActiveImage(0);
    setQuantity(1);
    Promise.all([getStoreProduct(slug, productId), getStoreProfile(slug)])
      .then(([item, card]) => {
        if (!alive) return;
        setProduct(item);
        setProfile(card);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (isStoreNotFound(e)) setMissing(true);
        else setError(e instanceof Error ? e.message : "تعذّر فتح الصنف");
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [slug, productId]);

  const copyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast("تم نسخ رابط المنتج", "success");
    } catch {
      toast("تعذّر النسخ — انسخ الرابط من شريط العنوان", "error");
    }
  }, [toast]);

  const inquiryLink = useMemo(() => {
    if (!product) return null;
    return whatsappLink(
      profile?.phone,
      productInquiryMessage(name, window.location.href),
    );
  }, [product, profile?.phone, name]);

  const handleAddToCart = () => {
    if (!product) return;
    addItem(product, quantity);
    toast(`تمت إضافة ${quantity} من «${name}» إلى السلة`, "success");
  };

  if (loading) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 dark:bg-slate-950">
        <LoadingSpinner showText={false} />
      </div>
    );
  }

  if (missing || !product) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 p-6 dark:bg-slate-950 font-sans">
        <div className="w-full max-w-lg rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
          <h1 className="text-xl font-black text-slate-900 dark:text-white">هذا المنتج لم يعد معروضاً</h1>
          <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
            قد يكون المتجر قد أوقف عرضه، أو أن الرابط غير صحيح. تصفّح بقية المنتجات المعروضة.
          </p>
          <button
            type="button"
            onClick={onBack}
            className="mt-6 rounded-2xl bg-blue-600 px-6 py-3 font-bold text-white transition hover:bg-blue-700"
          >
            العودة إلى المتجر
          </button>
        </div>
      </div>
    );
  }

  const images = product.images;

  return (
    <div
      dir="rtl"
      className="min-h-screen bg-slate-50 dark:bg-slate-950 font-sans text-slate-900 dark:text-slate-100"
      style={
        profile?.background_image_url
          ? {
              backgroundImage: `url(${profile.background_image_url})`,
              backgroundSize: profile.background_style === "cover" ? "cover" : "auto",
              backgroundRepeat: profile.background_style === "repeat_pattern" ? "repeat" : "no-repeat",
              backgroundAttachment: "fixed",
            }
          : undefined
      }
    >
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-900/90">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3 sm:px-6">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex min-h-10 items-center gap-2 rounded-xl px-3 text-xs font-bold text-slate-700 transition hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            <ArrowRight className="h-4 w-4" />
            <span>{storeName}</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void copyLink()}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              <Share2 className="h-3.5 w-3.5" />
              <span>مشاركة</span>
            </button>

            <button
              type="button"
              onClick={() => setIsCartOpen(true)}
              className="relative inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-blue-600 px-3 text-xs font-bold text-white shadow-md shadow-blue-600/20 transition hover:bg-blue-700"
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

      <main className="mx-auto max-w-5xl px-4 py-6 sm:py-10">
        {error ? (
          <div role="alert" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-center font-bold text-red-800 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </div>
        ) : null}

        <div className="grid gap-8 rounded-3xl border border-slate-200/80 bg-white/95 p-5 shadow-xl backdrop-blur-sm md:grid-cols-2 md:p-8 dark:border-slate-800/80 dark:bg-slate-900/95">
          {/* معرض الصور */}
          <div>
            <div className="relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-3xl bg-slate-50 border border-slate-100 sm:aspect-square dark:border-slate-800 dark:bg-slate-950">
              {images[activeImage] ? (
                <img src={images[activeImage]} alt={name} className="h-full w-full object-contain transition duration-300" />
              ) : (
                <ImageOff className="h-16 w-16 text-slate-300 dark:text-slate-700" />
              )}
              {activeImage === 0 && <StoreImageOverlay overlay={product.cover_overlay} />}
            </div>
            {images.length > 1 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {images.map((url, index) => (
                  <button
                    key={url}
                    type="button"
                    onClick={() => setActiveImage(index)}
                    aria-label={`صورة ${index + 1}`}
                    className={`h-16 w-16 overflow-hidden rounded-2xl border-2 transition ${index === activeImage ? "border-blue-600 shadow-md" : "border-slate-200 dark:border-slate-800 opacity-60 hover:opacity-100"}`}
                  >
                    <img src={url} alt="" className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          {/* تفاصيل المنتج وخيارات الشراء */}
          <div className="flex flex-col justify-between">
            <div>
              <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px]">
                {product.brand ? (
                  <span className="rounded-lg bg-slate-100 px-2.5 py-1 font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{product.brand}</span>
                ) : null}
                {product.category_name ? (
                  <span className="rounded-lg bg-blue-50 px-2.5 py-1 font-bold text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">{product.category_name}</span>
                ) : null}
                <StoreAvailabilityBadge availability={product.availability} />
              </div>

              <h1 className="text-2xl font-black text-slate-900 sm:text-3xl dark:text-white leading-tight">{name}</h1>
              {product.name_en && product.name_ar ? (
                <p className="mt-1 text-sm text-slate-400 font-medium" dir="ltr">{product.name_en}</p>
              ) : null}

              <div className="mt-4">
                <StorePrice price={product.price} currency={profile?.currency ?? null} className="text-3xl" />
              </div>

              {product.description ? (
                <div className="mt-6 border-t border-slate-100 pt-4 dark:border-slate-800">
                  <h4 className="text-xs font-bold text-slate-400 mb-2">وصف ومواصفات المنتج:</h4>
                  <p className="whitespace-pre-line text-xs sm:text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                    {product.description}
                  </p>
                </div>
              ) : null}
            </div>

            {/* أدوات الشراء والسلة */}
            <div className="mt-8 space-y-4 border-t border-slate-100 pt-6 dark:border-slate-800">
              {product.availability !== "out" && (
                <div className="flex items-center gap-4">
                  <span className="text-xs font-bold text-slate-600 dark:text-slate-400">الكمية:</span>
                  <div className="flex items-center rounded-2xl border border-slate-200 bg-slate-50 px-2 py-1 dark:border-slate-700 dark:bg-slate-800">
                    <button
                      type="button"
                      onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                      className="p-1 text-slate-600 hover:text-slate-900 dark:text-slate-300"
                    >
                      <Minus className="h-4 w-4" />
                    </button>
                    <span className="w-10 text-center text-sm font-black text-slate-900 dark:text-white">
                      {quantity}
                    </span>
                    <button
                      type="button"
                      onClick={() => setQuantity((q) => q + 1)}
                      className="p-1 text-slate-600 hover:text-slate-900 dark:text-slate-300"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {product.availability !== "out" && (
                  <button
                    type="button"
                    onClick={handleAddToCart}
                    className="flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-blue-600 px-6 font-bold text-white shadow-lg shadow-blue-600/30 transition hover:bg-blue-700 active:scale-[0.99]"
                  >
                    <ShoppingBag className="h-5 w-5" />
                    <span>أضف إلى السلة</span>
                  </button>
                )}

                {inquiryLink ? (
                  <a
                    href={inquiryLink}
                    target="_blank"
                    rel="noreferrer"
                    className="flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-6 font-bold text-white shadow-lg shadow-emerald-600/30 transition hover:bg-emerald-700 active:scale-[0.99]"
                  >
                    <MessageCircle className="h-5 w-5 fill-current" />
                    <span>اطلب عبر واتساب</span>
                  </a>
                ) : profile?.phone ? (
                  <a
                    href={`tel:${profile.phone}`}
                    className="flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-slate-800 px-6 font-bold text-white transition hover:bg-slate-700"
                  >
                    <span>اتصل للطلب: {profile.phone}</span>
                  </a>
                ) : null}
              </div>
            </div>
          </div>
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

export default StoreProductPage;

