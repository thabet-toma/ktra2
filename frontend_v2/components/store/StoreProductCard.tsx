/**
 * بطاقة صنف في شبكة المتجر — أصغر وحدة يراها الزائر.
 *
 * لا تفتح صفحة الصنف بنفسها ولا تعرف المسارات: التوجيه في `index.tsx` وحده،
 * فتبقى شاشات المتجر بلا أي ارتباط بموجِّه المسارات وتُقرأ وتُختبَر بمعزل.
 *
 * **لا تُطلَب نقطة التفصيل من هنا مسبقاً**: هي التي تزيد عدّاد المشاهدات
 * اليومي، فتحميلٌ استباقي لبطاقاتٍ لم تُفتَح يجعل الإحصاء كذباً.
 */
import React from "react";
import { ImageOff } from "lucide-react";

import { AVAILABILITY_LABEL, storeProductName, type StoreAvailability, type StoreProduct } from "../../services/storeApi";
import { formatNumber } from "../../utils/formatNumber";

const AVAILABILITY_TONE: Record<StoreAvailability, string> = {
  available: "bg-emerald-50 text-emerald-700 border-emerald-200",
  limited: "bg-amber-50 text-amber-800 border-amber-200",
  out: "bg-slate-100 text-slate-600 border-slate-200",
};

/** شارة التوفّر — حالة نصّية دائماً؛ الكمية نفسها لا تغادر الخادم. */
export const StoreAvailabilityBadge: React.FC<{ state: StoreAvailability }> = ({ state }) => (
  <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-bold ${AVAILABILITY_TONE[state] || AVAILABILITY_TONE.available}`}>
    {AVAILABILITY_LABEL[state] || AVAILABILITY_LABEL.available}
  </span>
);

/** السعر بصيغة المشروع الموحّدة + عملة المتجر. لا `toLocaleString` إطلاقاً. */
export const StorePrice: React.FC<{ price: string | null; currency: string | null; className?: string }> = ({
  price, currency, className = "",
}) => {
  const text = formatNumber(price, { maxDecimals: 2, group: true });
  if (!text) return <span className={`text-slate-400 ${className}`}>السعر عند الطلب</span>;
  return (
    <span className={`font-black text-slate-900 dark:text-white ${className}`}>
      {text}
      {currency ? <span className="mr-1 text-sm font-bold text-slate-500 dark:text-slate-400">{currency}</span> : null}
    </span>
  );
};

interface StoreProductCardProps {
  product: StoreProduct;
  currency: string | null;
  onOpen: (product: StoreProduct) => void;
}

export const StoreProductCard: React.FC<StoreProductCardProps> = ({ product, currency, onOpen }) => {
  const name = storeProductName(product);
  const image = product.images[0];

  return (
    <button
      type="button"
      onClick={() => onOpen(product)}
      className="group flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white text-right shadow-sm transition hover:-translate-y-0.5 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-700 dark:bg-slate-800"
    >
      <div className="relative h-48 w-full overflow-hidden bg-slate-50 sm:h-56 dark:bg-slate-900">
        {image ? (
          <img
            src={image}
            alt={name}
            loading="lazy"
            className="h-full w-full object-cover transition duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-slate-300 dark:text-slate-600">
            <ImageOff className="h-10 w-10" />
          </div>
        )}
        <div className="absolute top-3 right-3">
          <StoreAvailabilityBadge state={product.availability} />
        </div>
      </div>

      <div className="flex flex-1 flex-col p-4">
        <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
          {product.brand ? (
            <span className="rounded-md bg-slate-100 px-2 py-0.5 font-bold text-slate-600 dark:bg-slate-700 dark:text-slate-300">{product.brand}</span>
          ) : null}
          {product.category_name ? (
            <span className="rounded-md bg-blue-50 px-2 py-0.5 font-bold text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">{product.category_name}</span>
          ) : null}
        </div>

        <h3 className="line-clamp-2 text-base font-bold text-slate-900 transition group-hover:text-blue-700 dark:text-white" title={name}>
          {name}
        </h3>

        {product.description ? (
          <p className="mt-1 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">{product.description}</p>
        ) : null}

        <div className="mt-auto flex items-center justify-between pt-4">
          <StorePrice price={product.price} currency={currency} className="text-lg" />
          <span className="text-xs font-bold text-blue-600 dark:text-blue-400">عرض التفاصيل</span>
        </div>
      </div>
    </button>
  );
};
