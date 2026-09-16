import React from "react";
import { formatNumber } from "../../../utils/formatNumber";

export interface CcTabItem {
  key: string;
  label: string;
  icon?: React.ReactNode;
  badge?: string | number;
}

export interface CcTabsProps {
  tabs: CcTabItem[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
}

export const CcTabs: React.FC<CcTabsProps> = ({
  tabs,
  active,
  onChange,
  className = "",
}) => {
  /** تنقّلُ الأسهم داخل `role="tablist"` — بلا هذا يكون الدورُ ادّعاءً: قارئُ
   *  الشاشة يَعِد المستخدمَ بسلوكِ تبويباتٍ لا يجده. والاتّجاهُ معكوسٌ لأنّ
   *  الواجهةَ RTL: السهمُ الأيسرُ يتقدّم. */
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") {
      return;
    }
    const currentIndex = tabs.findIndex((tab) => tab.key === active);
    if (currentIndex < 0 || tabs.length === 0) return;
    event.preventDefault();
    let nextIndex = currentIndex;
    if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = tabs.length - 1;
    else if (event.key === "ArrowLeft") nextIndex = (currentIndex + 1) % tabs.length;
    else nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    if (nextIndex !== currentIndex) onChange(tabs[nextIndex].key);
  };

  return (
    <div
      role="tablist"
      dir="rtl"
      onKeyDown={onKeyDown}
      className={`flex w-full min-w-0 items-center gap-2 overflow-x-auto border-b border-cc-border ${className}`}
    >
      {tabs.map((tab) => {
        const isActive = active === tab.key;
        const formattedBadge =
          tab.badge !== undefined
            ? typeof tab.badge === "number"
              ? formatNumber(tab.badge)
              : tab.badge
            : null;

        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(tab.key)}
            /* `whitespace-nowrap shrink-0`: بلاهما تنكسر التسمياتُ الطويلةُ على
               ثلاثة أسطرٍ ويُقَصّ آخرُ التبويبات عند الحافّة — رآه المالكُ في
               اللقطة، ولا بوّابةَ هنا تصيّر مكوّناً فتمسكه. والفائضُ يُمرَّر
               أفقيّاً لا يُطوى. */
            className={`group inline-flex shrink-0 whitespace-nowrap items-center gap-2 px-4 py-2.5 text-xs font-bold border-b-2 -mb-px transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded-t-md ${
              isActive
                ? "border-cc-accent-2 text-cc-text"
                : "border-transparent text-cc-text-muted hover:text-cc-text hover:border-cc-border-strong"
            }`}
          >
            {tab.icon && (
              <span
                className={`shrink-0 transition-colors duration-150 ${
                  isActive ? "text-cc-accent-2" : "text-cc-text-muted group-hover:text-cc-text"
                }`}
              >
                {tab.icon}
              </span>
            )}
            <span>{tab.label}</span>
            {formattedBadge !== null && (
              <span
                className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                  isActive
                    ? "bg-cc-accent text-cc-text"
                    : "bg-cc-surface-2 text-cc-text-muted group-hover:text-cc-text"
                }`}
              >
                {formattedBadge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};

export default CcTabs;
