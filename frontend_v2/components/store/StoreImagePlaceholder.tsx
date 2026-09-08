/**
 * بديلٌ محايدٌ لصورة منتجٍ مفقودة — يحمل اسم المنتج، لا أيقونة صورةٍ مكسورة
 * (مواصفة #166 م٧، قسم هـ). مكوّنٌ خالصٌ بلا سياق.
 */
import React from "react";

export const StoreImagePlaceholder: React.FC<{ name: string; className?: string }> = ({
  name,
  className = "",
}) => {
  const initial = name.trim().charAt(0) || "؟";
  return (
    <div
      className={`flex h-full w-full flex-col items-center justify-center gap-1.5 bg-slate-100 p-3 text-center dark:bg-slate-800 ${className}`}
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-lg font-black text-slate-300 shadow-sm dark:bg-slate-900 dark:text-slate-600">
        {initial}
      </span>
      <span className="line-clamp-2 text-[10px] font-bold text-slate-400 dark:text-slate-500">{name}</span>
    </div>
  );
};

export default StoreImagePlaceholder;
