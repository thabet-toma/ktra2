/**
 * تجميع البراندات — الكرت المجمّع: بطاقة المقاس/الأساس (مثل عجل 185/65/14) تجمع
 * مؤشّرات وحركات وفواتير كل البراندات تحته. المسار: /product-group?ids=1,2,3&name=…
 *
 * الصفحة غلافٌ رقيق فوق `useGroupInsights` (في `ProductInsightTabs.tsx`) —
 * البيانات والتبويبات نفسها تعرضها شجرة الأصناف في بطاقتها الجانبية، فبقاؤها
 * محبوسةً هنا كان يعني نسخةً ثانية منها.
 */
import React, { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { AseelDocumentShell } from '../aseel';
import { useAppBack } from '../../hooks/useAppBack';
import { formatQuantity, formatMoney } from '../../utils/formatNumber';
import { useGroupInsights } from './ProductInsightTabs';

export const GroupProfilePage: React.FC = () => {
  const location = useLocation();
  // كالكرت المفرد: يُفتح في تبويب جديد، فوجهة «عودة» تُحسم لا تُخمَّن.
  const back = useAppBack('/items', 'الأصناف');

  const ids = useMemo(() => {
    const raw = new URLSearchParams(location.search).get('ids') || '';
    return raw.split(',').map((s) => s.trim()).filter((s) => /^\d+$/.test(s)).map(Number);
  }, [location.search]);
  const nameParam = useMemo(
    () => new URLSearchParams(location.search).get('name') || '',
    [location.search],
  );

  const { profile, loading, error, tabs } = useGroupInsights(ids);

  const title = profile ? `كرت مجمّع: ${nameParam || profile.name}` : `كرت مجمّع: ${nameParam}`;

  return (
    <div className="min-h-[calc(100vh-5rem)]">
      <AseelDocumentShell
        title={title}
        actions={[{ key: 'back', label: back.label === 'رجوع' ? 'عودة' : back.label, onClick: back.go }]}
        tabs={tabs}
        status={
          error ? <span className="text-[var(--aseel-danger)]">تعذّر التحميل: {error}</span> :
          loading ? <span>جاري التحميل...</span> :
          <span className="aseel-status-item">{profile ? `إجمالي المخزون ${formatQuantity(profile.quantity_on_hand, '—')} · تقييم ${formatMoney(profile.inventory_valuation, '—')}` : ''}</span>
        }
      >
        {error && (
          <div role="alert" className="m-2 p-3 rounded border border-[var(--aseel-danger,#c00)] text-[var(--aseel-danger,#c00)] text-sm">
            تعذّر تحميل الكرت المجمّع: {error}
          </div>
        )}
      </AseelDocumentShell>
    </div>
  );
};

export default GroupProfilePage;
