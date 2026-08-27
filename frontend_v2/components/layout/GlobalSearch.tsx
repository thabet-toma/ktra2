/**
 * زرّ البحث في الترويسة — وصار بحثاً فعلياً.
 *
 * كان اسمُه `GlobalSearch` ومحتواه **روابط سريعة وحدها**، بلا حقل بحثٍ واحد:
 * أيقونةُ عدسةٍ تفتح قائمة تنقّل. فالمستخدم الذي في يده باركود أو رقم جهاز كان
 * عليه أن يعرف نوعه أولاً ثم يفتح شاشته ثم يبحث فيها — وهو ما يقلبه T-SCAN.
 *
 * الآن الزرّ يفتح `ScanLookupPanel`: حقلٌ واحد يقبل الباركود والسيريال والـIMEI
 * ورمز المنتج وجزءَ الاسم، وزرّ كاميرا بجانبه. والروابط السريعة لم تُحذف — صارت
 * **حالةَ الفراغ** داخل اللوحة: قبل أن تكتب شيئاً هي أنفعُ ما يُعرض، وبعد أن
 * تكتب تُستبدل بالنتائج. مساحةٌ واحدة تخدم الحاجتين بدل قائمتين.
 */
import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { AppView } from '../../types';
import { useCompany } from '../../contexts/CompanyContext';
import { ScanLookupPanel } from '../shared/ScanLookupPanel';

interface GlobalSearchProps {
  userRole: string;
  onNavigate: (view: AppView) => void;
}

const QUICK_LINKS: { label: string; view: AppView }[] = [
  { label: 'الصفقات', view: 'deals-management' },
  { label: 'الشحنات', view: 'shipments-management' },
  { label: 'التخليص', view: 'customs-clearance' },
  { label: 'فواتير الشراء', view: 'purchase-invoices' },
  { label: 'فواتير المبيعات', view: 'sales-invoices' },
  { label: 'الشيكات', view: 'accounting-cheques' },
  { label: 'البنوك وفروعها', view: 'accounting-banks' },
  { label: 'المطابقة البنكية', view: 'accounting-bank-reconciliation' },
];

const IMPORT_ONLY: AppView[] = [
  'deals-management',
  'shipments-management',
  'customs-clearance',
];

export const GlobalSearch: React.FC<GlobalSearchProps> = ({ userRole, onNavigate }) => {
  const { canAccessImport } = useCompany();
  const [open, setOpen] = useState(false);

  const links = QUICK_LINKS.filter(
    link => canAccessImport || !IMPORT_ONLY.includes(link.view)
  );

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="p-2 rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors"
        aria-label="بحث سريع"
        data-testid="global-search-button"
      >
        <Search className="h-4 w-4" />
      </button>

      {open && (
        <ScanLookupPanel
          onClose={() => setOpen(false)}
          emptyState={(
            <div className="mt-2">
              <div className="mb-1 px-1 text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
                روابط سريعة
              </div>
              <div className="flex flex-wrap gap-2">
                {links.map(link => (
                  <button
                    key={link.view}
                    onClick={() => { onNavigate(link.view); setOpen(false); }}
                    className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-[var(--font-size-sm)] text-[var(--color-text)] hover:bg-[var(--color-muted)] transition-colors"
                  >
                    {link.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        />
      )}
    </>
  );
};
