import React from "react";
import { ImageOff, ShoppingBag } from "lucide-react";
import { useStoreCart } from "../../contexts/StoreCartContext";
import {
  AVAILABILITY_LABEL,
  storeProductName,
  type StoreAvailability,
  type StoreProduct,
} from "../../services/storeApi";
import { formatNumber } from "../../utils/formatNumber";
import { StoreImageOverlay } from "./StoreImageOverlay";

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
}> = ({ price, currency, className = "", onDark = false }) => {
  const text = formatNumber(price, { maxDecimals: 2, group: true });
  if (!text)
    return (
      <span
        className={`${onDark ? "text-slate-300" : "text-slate-400"} text-xs font-semibold ${className}`}
      >
        السعر عند الطلب
      </span>
    );
  return (
    <span
      className={`font-black ${onDark ? "text-white" : "text-slate-900 dark:text-white"} ${className}`}
    >
      {text}
      {currency ? (
        <span
          className={`mr-1 text-xs font-bold ${onDark ? "text-slate-300" : "text-slate-500 dark:text-slate-400"}`}
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
}

export const StoreProductCard: React.FC<StoreProductCardProps> = ({
  product,
  currency,
  onOpen,
  onClick,
}) => {
  const { addItem } = useStoreCart();
  const name = storeProductName(product);
  const image = product.images?.[0];

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
          <div className="flex h-full w-full items-center justify-center text-slate-300 dark:text-slate-700">
            <ImageOff className="h-10 w-10" />
          </div>
        )}

        {/* شريط الإعلان الترويجي المخصص */}
        <StoreImageOverlay overlay={product.cover_overlay} />

        <div className="absolute top-2.5 left-2.5 z-10">
          <StoreAvailabilityBadge availability={product.availability} />
        </div>

        {/* زر الإضافة السريعة للسلة العائم */}
        {product.availability !== "out" && (
          <button
            type="button"
            onClick={handleQuickAdd}
            className="absolute bottom-2.5 left-2.5 z-10 flex h-9 w-9 items-center justify-center rounded-2xl bg-white/90 text-slate-800 shadow-md backdrop-blur transition hover:bg-blue-600 hover:text-white dark:bg-slate-800/90 dark:text-slate-100 dark:hover:bg-blue-600"
            title="أضف إلى السلة"
          >
            <ShoppingBag className="h-4 w-4" />
          </button>
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

        <div className="mt-auto flex items-center justify-between pt-3">
          <StorePrice price={product.price} currency={currency} className="text-base" />
          <span className="text-[11px] font-bold text-blue-600 dark:text-blue-400">
            التفاصيل
          </span>
        </div>
      </div>
    </div>
  );
};

