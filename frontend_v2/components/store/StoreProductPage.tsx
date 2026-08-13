/**
 * صفحة صنف واحد — `/store/<slug>/p/<id>`، وهي الرابط الذي يُشارَك فعلاً.
 *
 * هذا النداء وحده يزيد عدّاد المشاهدات اليومي على الخادم، فلا يُطلَب إلا حين
 * يفتح الزائر الصفحة بالفعل (لا تحميل استباقي من البطاقات).
 *
 * زر واتساب يحمل اسم الصنف ورابطه: المتجر بلا سلة ولا دفع (خارج النطاق)،
 * فالرسالة الجاهزة هي كامل مسار الطلب — بائعٌ يستقبل «مرحباً» وحدها لا يعرف
 * عن أي صنف يُسأل.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Copy, ImageOff, MessageCircle } from "lucide-react";

import { LoadingSpinner } from "../LoadingSpinner";
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
import { StoreAvailabilityBadge, StorePrice } from "./StoreProductCard";

interface StoreProductPageProps {
  slug: string;
  productId: string;
  onBack: () => void;
}

export const StoreProductPage: React.FC<StoreProductPageProps> = ({ slug, productId, onBack }) => {
  const toast = useToast();

  const [product, setProduct] = useState<StoreProduct | null>(null);
  const [profile, setProfile] = useState<StoreProfile | null>(null);
  const [activeImage, setActiveImage] = useState(0);
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

  if (loading) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 dark:bg-slate-900">
        <LoadingSpinner showText={false} />
      </div>
    );
  }

  if (missing || !product) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 p-6 dark:bg-slate-900">
        <div className="w-full max-w-lg rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-slate-800">
          <h1 className="text-xl font-black text-slate-900 dark:text-white">هذا المنتج لم يعد معروضاً</h1>
          <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
            قد يكون المتجر قد أوقف عرضه، أو أن الرابط غير صحيح. تصفّح بقية المنتجات المعروضة.
          </p>
          <button
            type="button"
            onClick={onBack}
            className="mt-6 rounded-xl bg-blue-600 px-6 py-3 font-bold text-white transition hover:bg-blue-700"
          >
            العودة إلى المتجر
          </button>
        </div>
      </div>
    );
  }

  const images = product.images;

  return (
    <div dir="rtl" className="min-h-screen bg-slate-100 dark:bg-slate-900">
      <header className="bg-white shadow-sm dark:bg-slate-800">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex min-h-11 items-center gap-2 text-sm font-bold text-slate-700 transition hover:text-blue-700 dark:text-slate-200"
          >
            <ArrowRight className="h-4 w-4" />
            {storeName}
          </button>
          <button
            type="button"
            onClick={() => void copyLink()}
            className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-slate-300 px-4 text-sm font-bold text-slate-700 transition hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200"
          >
            <Copy className="h-4 w-4" />
            نسخ الرابط
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        {error ? (
          <div role="alert" className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-center font-bold text-red-800 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </div>
        ) : null}

        <div className="grid gap-6 rounded-3xl bg-white p-4 shadow-sm md:grid-cols-2 md:p-6 dark:bg-slate-800">
          <div>
            <div className="flex h-72 w-full items-center justify-center overflow-hidden rounded-2xl bg-slate-50 sm:h-96 dark:bg-slate-900">
              {images[activeImage] ? (
                <img src={images[activeImage]} alt={name} className="h-full w-full object-contain" />
              ) : (
                <ImageOff className="h-12 w-12 text-slate-300 dark:text-slate-600" />
              )}
            </div>
            {images.length > 1 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {images.map((url, index) => (
                  <button
                    key={url}
                    type="button"
                    onClick={() => setActiveImage(index)}
                    aria-label={`صورة ${index + 1}`}
                    className={`h-16 w-16 overflow-hidden rounded-xl border-2 transition ${index === activeImage ? "border-blue-600" : "border-transparent hover:border-slate-300"}`}
                  >
                    <img src={url} alt="" className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className="flex flex-col">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px]">
              {product.brand ? (
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-bold text-slate-600 dark:bg-slate-700 dark:text-slate-300">{product.brand}</span>
              ) : null}
              {product.category_name ? (
                <span className="rounded-md bg-blue-50 px-2 py-0.5 font-bold text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">{product.category_name}</span>
              ) : null}
              <StoreAvailabilityBadge state={product.availability} />
            </div>

            <h1 className="text-2xl font-black text-slate-900 dark:text-white">{name}</h1>
            {product.name_en && product.name_ar ? (
              <p className="mt-1 text-sm text-slate-400" dir="ltr">{product.name_en}</p>
            ) : null}

            <div className="mt-4">
              <StorePrice price={product.price} currency={profile?.currency ?? null} className="text-3xl" />
            </div>

            {product.description ? (
              <p className="mt-4 whitespace-pre-line text-sm leading-7 text-slate-600 dark:text-slate-300">
                {product.description}
              </p>
            ) : null}

            <div className="mt-auto flex flex-wrap gap-2 pt-6">
              {inquiryLink ? (
                <a
                  href={inquiryLink}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-6 font-bold text-white transition hover:bg-emerald-700"
                >
                  <MessageCircle className="h-5 w-5" />
                  اطلب عبر واتساب
                </a>
              ) : profile?.phone ? (
                <a
                  href={`tel:${profile.phone}`}
                  className="inline-flex min-h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-blue-600 px-6 font-bold text-white transition hover:bg-blue-700"
                >
                  <MessageCircle className="h-5 w-5" />
                  اتصل للطلب: {profile.phone}
                </a>
              ) : (
                <p className="text-sm font-bold text-slate-500 dark:text-slate-400">
                  لم يضف المتجر رقم تواصل بعد.
                </p>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

export default StoreProductPage;
