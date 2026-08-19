/**
 * وضع عرض الكتالوج / شرائح الهاتف المتجاوب (Mobile Slide/Story Catalog Mode)
 *
 * يتيح تصفح المنتجات كشرائح تفاعلية بملء الشاشة مع معرض صور وسعر وطلب مباشر.
 */
import React, { useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  Grid,
  ImageOff,
  MessageCircle,
  Share2,
  ShoppingBag,
} from "lucide-react";
import { useStoreCart } from "../../contexts/StoreCartContext";
import { useToast } from "../../contexts/ToastContext";
import {
  StoreProduct,
  storeProductName,
  StoreProfile,
} from "../../services/storeApi";
import { productInquiryMessage, whatsappLink } from "../../utils/storeLinks";
import { StoreAvailabilityBadge, StorePrice } from "./StoreProductCard";
import { StoreImageOverlay } from "./StoreImageOverlay";

interface StoreCatalogSliderProps {
  products: StoreProduct[];
  profile: StoreProfile | null;
  slug: string;
  onCloseCatalog: () => void;
  onOpenProductDetail: (productId: number) => void;
}

export const StoreCatalogSlider: React.FC<StoreCatalogSliderProps> = ({
  products,
  profile,
  slug,
  onCloseCatalog,
  onOpenProductDetail,
}) => {
  const toast = useToast();
  const { addItem, totalCount, setIsCartOpen } = useStoreCart();

  const [currentIndex, setCurrentIndex] = useState(0);
  const [activeImageIndex, setActiveImageIndex] = useState(0);

  const product = products[currentIndex] || null;

  // إعادة ضبط صورة المنتج عند الانتقال
  useEffect(() => {
    setActiveImageIndex(0);
  }, [currentIndex]);

  // دعم أسهم لوحة المفاتيح
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") handleNext();
      if (e.key === "ArrowRight") handlePrev();
      if (e.key === "Escape") onCloseCatalog();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [products.length]);

  const handleNext = () => {
    setCurrentIndex((prev) => (prev < products.length - 1 ? prev + 1 : 0));
  };

  const handlePrev = () => {
    setCurrentIndex((prev) => (prev > 0 ? prev - 1 : products.length - 1));
  };

  const handleShare = async () => {
    if (!product) return;
    const url = `${window.location.origin}/store/${encodeURIComponent(slug)}/p/${product.id}`;
    if (navigator.share) {
      try {
        await navigator.share({
          title: storeProductName(product),
          text: product.description || undefined,
          url,
        });
      } catch {
        // ألغى المستخدم المشاركة
      }
    } else {
      try {
        await navigator.clipboard.writeText(url);
        toast("تم نسخ رابط المنتج للمشاركة", "success");
      } catch {
        toast("تعذّر النسخ", "error");
      }
    }
  };

  if (!product) {
    return (
      <div className="flex min-h-[400px] flex-col items-center justify-center p-8 text-center" dir="rtl">
        <p className="text-slate-500">لا توجد منتجات لعرضها في الكتالوج.</p>
        <button
          type="button"
          onClick={onCloseCatalog}
          className="mt-4 rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white"
        >
          العودة للشبكة
        </button>
      </div>
    );
  }

  const name = storeProductName(product);
  const images = product.images || [];
  const activeImage = images[activeImageIndex] || images[0] || null;

  const inquiryUrl = whatsappLink(
    profile?.phone,
    productInquiryMessage(
      name,
      `${window.location.origin}/store/${encodeURIComponent(slug)}/p/${product.id}`,
    ),
  );

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-slate-950 text-white font-sans" dir="rtl">
      {/* شريط التحكم العلوي */}
      <div className="flex items-center justify-between border-b border-slate-800/80 bg-slate-900/90 px-4 py-3 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onCloseCatalog}
            className="flex items-center gap-1.5 rounded-xl bg-slate-800 px-3 py-1.5 text-xs font-bold text-slate-200 transition hover:bg-slate-700"
          >
            <Grid className="h-4 w-4" />
            <span>عرض الشبكة</span>
          </button>
          <span className="text-xs font-semibold text-slate-400">
            {currentIndex + 1} من {products.length}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleShare}
            className="rounded-xl bg-slate-800 p-2 text-slate-300 transition hover:bg-slate-700"
            title="مشاركة المنتج"
          >
            <Share2 className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setIsCartOpen(true)}
            className="relative rounded-xl bg-blue-600 p-2 text-white transition hover:bg-blue-700"
            title="فتح السلة"
          >
            <ShoppingBag className="h-4 w-4" />
            {totalCount > 0 && (
              <span className="absolute -top-1.5 -left-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[10px] font-black text-white shadow">
                {totalCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* منطقة الشريحة والتفاعل */}
      <div className="relative flex flex-1 flex-col items-center justify-center overflow-y-auto p-4 sm:p-6">
        {/* أسهم التقليب للديسكتوب */}
        <button
          type="button"
          onClick={handlePrev}
          className="absolute right-4 top-1/2 z-20 hidden -translate-y-1/2 rounded-full bg-black/60 p-3 text-white backdrop-blur transition hover:bg-black/80 md:flex"
        >
          <ChevronRight className="h-6 w-6" />
        </button>
        <button
          type="button"
          onClick={handleNext}
          className="absolute left-4 top-1/2 z-20 hidden -translate-y-1/2 rounded-full bg-black/60 p-3 text-white backdrop-blur transition hover:bg-black/80 md:flex"
        >
          <ChevronLeft className="h-6 w-6" />
        </button>

        {/* بطاقة الشريحة المركزية */}
        <div className="w-full max-w-lg rounded-3xl border border-slate-800 bg-slate-900 shadow-2xl overflow-hidden">
          {/* الصورة ومعرض الصور */}
          <div className="relative aspect-square w-full bg-slate-950">
            {activeImage ? (
              <img
                src={activeImage}
                alt={name}
                className="h-full w-full object-contain transition-all duration-300"
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center text-slate-600">
                <ImageOff className="h-16 w-16" />
                <span className="mt-2 text-xs">لا توجد صور لهذا المنتج</span>
              </div>
            )}

            {/* شريط الإعلان المخصص */}
            {activeImageIndex === 0 && (
              <StoreImageOverlay overlay={product.cover_overlay} />
            )}

            {/* بادج التوفر */}
            <div className="absolute top-4 left-4">
              <StoreAvailabilityBadge availability={product.availability} />
            </div>

            {/* نقاط التنقل بين صور المنتج الواحد */}
            {images.length > 1 && (
              <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5 rounded-full bg-black/60 px-3 py-1.5 backdrop-blur">
                {images.map((_, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setActiveImageIndex(idx)}
                    className={`h-2 rounded-full transition-all ${
                      idx === activeImageIndex ? "w-6 bg-blue-500" : "w-2 bg-white/40"
                    }`}
                  />
                ))}
              </div>
            )}
          </div>

          {/* تفاصيل المنتج */}
          <div className="p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                {product.brand && (
                  <span className="text-[11px] font-bold text-blue-400">
                    {product.brand}
                  </span>
                )}
                <h3 className="text-lg font-black text-white leading-snug">
                  {name}
                </h3>
              </div>
              <div className="text-left">
                <StorePrice price={product.price} currency={profile?.currency ?? null} />
              </div>
            </div>

            {product.description && (
              <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-slate-300">
                {product.description}
              </p>
            )}

            {/* أزرار الإجراءات */}
            <div className="mt-6 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => addItem(product, 1)}
                className="flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-blue-600/30 transition hover:bg-blue-700 active:scale-95"
              >
                <ShoppingBag className="h-4 w-4" />
                <span>أضف إلى السلة</span>
              </button>

              {inquiryUrl ? (
                <a
                  href={inquiryUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-4 py-3 text-xs font-bold text-white shadow-lg shadow-emerald-600/30 transition hover:bg-emerald-700 active:scale-95"
                >
                  <MessageCircle className="h-4 w-4 fill-current" />
                  <span>اطلب عبر واتساب</span>
                </a>
              ) : (
                <button
                  type="button"
                  onClick={() => onOpenProductDetail(product.id)}
                  className="flex items-center justify-center gap-2 rounded-2xl bg-slate-800 px-4 py-3 text-xs font-bold text-slate-200 transition hover:bg-slate-700"
                >
                  <Eye className="h-4 w-4" />
                  <span>تفاصيل الصنف</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* شريط التنقل السفلي للموبايل */}
      <div className="flex items-center justify-between border-t border-slate-800 bg-slate-900/90 px-5 py-3 md:hidden">
        <button
          type="button"
          onClick={handlePrev}
          className="flex items-center gap-1 text-xs font-bold text-slate-300 hover:text-white"
        >
          <ChevronRight className="h-4 w-4" />
          <span>السابق</span>
        </button>

        <button
          type="button"
          onClick={() => onOpenProductDetail(product.id)}
          className="text-xs text-blue-400 hover:underline"
        >
          فتح صفحة المنتج الكاملة
        </button>

        <button
          type="button"
          onClick={handleNext}
          className="flex items-center gap-1 text-xs font-bold text-slate-300 hover:text-white"
        >
          <span>التالي</span>
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
