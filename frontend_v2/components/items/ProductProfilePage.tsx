/**
 * FEAT-3 — ProductProfilePage: مسار كرت الصنف (`/products/:id`).
 *
 * كان صفحةً منفصلة عن نموذج التحرير، فصار للصنف كرتان: واحد يُعرض وآخر يُعدَّل.
 * الآن هذه الصفحة غلاف رقيق فوق الكرت الموحّد `ItemFormAseel` — نفس الشاشة التي
 * تفتحها شاشة الأصناف للتعديل والإضافة، بتبويباتها القرائية (نظرة عامة/الفواتير/
 * حركة المخزون) وتحريرها في مكان واحد.
 */
import React, { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ItemFormAseel } from './ItemFormAseel';
import { openInNewTab } from '../../utils/openInNewTab';

/** روابط قديمة تفتح البطاقة على تبويب بعينه — «kpis» صار «overview». */
const TAB_ALIASES: Record<string, string> = {
  kpis: 'overview',
  overview: 'overview',
  invoices: 'invoices',
  ledger: 'ledger',
  // THA-411: لوحة الأرصدة الافتتاحية تُرسل المستخدم إلى هنا ليُرقّم بضاعة الافتتاح.
  serials: 'serials',
};

export const ProductProfilePage: React.FC = () => {
  // App مركّب على مسار splat (/*) بلا Route فيه :id، لذا useParams().id يرجع
  // undefined. نستخرج المعرّف من المسار مباشرة (/products/:id).
  const location = useLocation();
  const navigate = useNavigate();
  const id = useMemo(() => {
    const m = location.pathname.match(/\/products\/([^/]+)/);
    return m ? Number(m[1]) : NaN;
  }, [location.pathname]);
  const initialTab = useMemo(
    () => TAB_ALIASES[new URLSearchParams(location.search).get('tab') || ''] ?? 'overview',
    [location.search],
  );

  if (!Number.isFinite(id)) {
    return <div className="p-4 text-[var(--aseel-danger,#c00)]">معرّف صنف غير صالح.</div>;
  }

  return (
    <div className="min-h-[calc(100vh-5rem)]">
      <ItemFormAseel
        productId={id}
        products={[]}
        initialTab={initialTab}
        cancelLabel="عودة"
        extraActions={[
          { key: 'cost', label: 'تكلفة المنتجات', onClick: () => openInNewTab(`/product-cost?product=${id}`) },
        ]}
        onSaved={() => { /* الكرت يحدّث نفسه — لا قائمة خلفه لإعادة تحميلها */ }}
        onCancel={() => navigate(-1)}
      />
    </div>
  );
};

export default ProductProfilePage;
