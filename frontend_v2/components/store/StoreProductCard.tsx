import React from "react";
import { MessageCircle, ShoppingBag } from "lucide-react";
import { useStoreCart } from "../../contexts/StoreCartContext";
import {
  AVAILABILITY_LABEL,
  storeProductName,
  type StoreAvailability,
  type StoreProduct,
} from "../../services/storeApi";
import { formatNumber } from "../../utils/formatNumber";
import { StoreImageOverlay } from "./StoreImageOverlay";
import { StoreImagePlaceholder } from "./StoreImagePlaceholder";

const AVAILABILITY_TONE: Record<StoreAvailability, string> = {
  available: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800",
  limited: "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800",
  out: "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700",
  preorder: "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-300 dark:border-indigo-800",
};

/** شارة التوفّر — حالة نصّية دائماً. */
export const StoreAvailabilityBadge: React.FC<{
  state?: StoreAvailability;
  availability?: StoreAvailability;
}> = ({ state, availability }) => {
  const current = availability || state || "available";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-bold shadow-sm ${
        AVAILABILITY_TONE[current] || AVAILABILITY_TONE.available
      }`}
    >
      {AVAILABILITY_LABEL[current] || AVAILABILITY_LABEL.available}
    </span>
  );
};

/** السعر بصيغة المشروع الموحّدة + عملة المتجر. */
export const StorePrice: React.FC<{
  price: string | null;
  currency: string | null;
  className?: string;
  /** للوحات الداكنة الثابتة (صفحة الحملة): `text-slate-900` عليها أسودُ على أسود. */
  onDark?: boolean;
  /** خصمٌ فعليّ — السعرُ أحمرُ (قسم أ من مواصفة #166 م٧)، لا اللون الافتراضي. */
  discounted?: boolean;
}> = ({ price, currency, className = "", onDark = false, discounted = false }) => {
  const text = formatNumber(price, { maxDecimals: 2, group: true });
  if (!text)
    return (
      <span
        className={`${onDark ? "text-slate-300" : "text-slate-400"} text-xs font-semibold ${className}`}
      >
        السعر عند الطلب
      </span>
    );
  const priceTone = discounted
    ? "text-rose-600 dark:text-rose-400"
    : onDark
      ? "text-white"
      : "text-slate-900 dark:text-white";
  return (
    <span className={`font-black ${priceTone} ${className}`}>
      {text}
      {currency ? (
        <span
          className={`ms-1 text-xs font-bold ${onDark ? "text-slate-300" : "text-slate-500 dark:text-slate-400"}`}
        >
          {currency}
        </span>
      ) : null}
    </span>
  );
};

interface StoreProductCardProps {
  product: StoreProduct;
  currency: string | null;
  onOpen?: (product: StoreProduct) => void;
  onClick?: () => void;
  /** الفعلُ الأساسيّ حين يكون السعر مخفياً — «السعر عند الطلب» (قسم هـ). */
  whatsappHref?: string | null;
}

export const StoreProductCard: React.FC<StoreProductCardProps> = ({
  product,
  currency,
  onOpen,
  onClick,
  whatsappHref,
}) => {
  const { addItem } = useStoreCart();
  const name = storeProductName(product);
  const image = product.images?.[0];
  const priceHidden = product.price == null;
  const discounted = Boolean(product.original_price);

  const handleClick = () => {
    if (onClick) onClick();
    else if (onOpen) onOpen(product);
  };

  const handleQuickAdd = (e: React.MouseEvent) => {
    e.stopPropagation();
    addItem(product, 1);
  };

  return (
    <div
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter") handleClick();
      }}
      className="group relative flex h-full cursor-pointer flex-col overflow-hidden rounded-3xl border border-slate-200/80 bg-white text-right shadow-sm transition duration-300 hover:-translate-y-1 hover:border-slate-300 hover:shadow-xl dark:border-slate-800/80 dark:bg-slate-900 dark:hover:border-slate-700"
    >
      <div className="relative aspect-square w-full overflow-hidden bg-slate-50 dark:bg-slate-950">
        {image ? (
          <img
            src={image}
            alt={name}
            loading="lazy"
            className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
          />
        ) : (
          <StoreImagePlaceholder name={name} />
        )}

        {/* خانةُ نهايةِ الصورة (يسارُها في RTL) — الشارةُ الحرّة للتاجر، بحدٍّ أقصى واحدة. */}
        <StoreImageOverlay overlay={product.cover_overlay} />

        {/* خانةُ بدايةِ الصورة (يمينُها في RTL) — الشارةُ المحسوبة وحدها، بحدٍّ أقصى واحدة. */}
        {product.discount_percent ? (
          <div className="absolute start-2.5 top-2.5 z-10">
            <span className="rounded-full bg-rose-600 px-2 py-0.5 text-[11px] font-black text-white shadow-sm">
              خصم {formatNumber(product.discount_percent)}٪
            </span>
          </div>
        ) : null}

        <div className="absolute bottom-2.5 start-2.5 z-10">
          <StoreAvailabilityBadge availability={product.availability} />
        </div>

        {/* زر الإضافة السريعة للسلة العائم — سعرٌ مخفيٌّ يستبدله استفسارُ واتساب (قسم هـ). */}
        {product.availability !== "out" && !priceHidden && (
          <button
            type="button"
            onClick={handleQuickAdd}
            className="absolute bottom-2.5 end-2.5 z-10 flex h-9 w-9 items-center justify-center rounded-2xl bg-white/90 text-slate-800 shadow-md backdrop-blur transition hover:bg-[var(--store-primary,#2563eb)] hover:text-white dark:bg-slate-800/90 dark:text-slate-100"
            title="أضف إلى السلة"
          >
            <ShoppingBag className="h-4 w-4" />
          </button>
        )}
        {priceHidden && whatsappHref && (
          <a
            href={whatsappHref}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="absolute bottom-2.5 end-2.5 z-10 flex h-9 w-9 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-md transition hover:bg-emerald-700"
            title="استفسر عبر واتساب"
          >
            <MessageCircle className="h-4 w-4 fill-current" />
          </a>
        )}
      </div>

      <div className="flex flex-1 flex-col p-4">
        <div className="mb-1.5 flex flex-wrap gap-1.5 text-[10px]">
          {product.brand && (
            <span className="rounded-lg bg-slate-100 px-2 py-0.5 font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {product.brand}
            </span>
          )}
          {product.category_name && (
            <span className="rounded-lg bg-blue-50 px-2 py-0.5 font-bold text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
              {product.category_name}
            </span>
          )}
        </div>

        <h3
          className="line-clamp-2 text-sm font-bold text-slate-900 transition group-hover:text-blue-600 dark:text-white dark:group-hover:text-blue-400"
          title={name}
        >
          {name}
        </h3>

        {product.description && (
          <p className="mt-1 line-clamp-1 text-xs text-slate-500 dark:text-slate-400">
            {product.description}
          </p>
        )}

        {/* منطقةُ السعر بارتفاعٍ محجوزٍ ثابت — بطاقةٌ مخفَّضة لا تعلو جاراتها (قسم أ). */}
        <div className="mt-auto flex min-h-[2.75rem] items-end justify-between pt-3">
          <div className="flex items-baseline gap-2">
            <StorePrice
              price={product.price}
              currency={currency}
              discounted={discounted}
              className="text-base"
            />
            {product.original_price ? (
              <span className="text-[11px] font-semibold text-slate-400 line-through dark:text-slate-500">
                {formatNumber(product.original_price, { maxDecimals: 2, group: true })} {currency}
              </span>
            ) : null}
          </div>
          <span className="shrink-0 text-[11px] font-bold text-[var(--store-primary,#2563eb)]">
            التفاصيل
          </span>
        </div>
      </div>
    </div>
  );
};

