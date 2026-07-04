import React from 'react';
import { Eye, EyeOff } from 'lucide-react';
import { usePriceVisibility } from '../../contexts/PriceVisibilityContext';

/**
 * زر إظهار/إخفاء أسعار الأصناف (آخر/أقل سعر) في القوائم **والربح الإجمالي** في الفاتورة —
 * للخصوصية أمام الزبون. الحالة مخزّنة عالمياً (PriceVisibilityContext) فتؤثّر على المبيعات
 * والمشتريات معاً. يختفي الزر كلياً حين يُعطَّل من الإعدادات (showToggle=false).
 */
export const PriceVisibilityToggle: React.FC = () => {
  const { visible, toggle, showToggle } = usePriceVisibility();

  if (!showToggle) return null;

  return (
    <button
      onClick={toggle}
      className="p-2 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors"
      title={visible ? 'إخفاء الأسعار والأرباح' : 'إظهار الأسعار والأرباح'}
      aria-label={visible ? 'إخفاء الأسعار والأرباح' : 'إظهار الأسعار والأرباح'}
      aria-pressed={visible}
    >
      {visible ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
    </button>
  );
};
