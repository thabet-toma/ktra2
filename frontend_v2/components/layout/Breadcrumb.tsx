import React, { useState } from 'react';
import { AppView } from '../../types';
import { ChevronLeft, ArrowRight } from 'lucide-react';
import { useAppBack } from '../../hooks/useAppBack';
import { LinkedTabHint, TabOriginChip } from './TabAwareness';

export const VIEW_LABELS: Record<AppView, string> = {
  dashboard: 'الرئيسية',
  'super-admin': 'لوحة تحكم السوبر أدمن',
  'development-notes': 'ملاحظات التطوير',
  tasks: 'مهامي',
  'task-management': 'إدارة المهام',
  users: 'قائمة المستخدمين',
  reports: 'التقارير',
  'report-runner': 'تقرير',
  'team-time-report': 'أوقات الفريق',
  'employee-notes': 'ملاحظات الموظفين',
  'points-history': 'سجل نقاطي',
  'sales-orders': 'عروض وطلبيات البيع',
  'my-account': 'حسابي',
  payroll: 'الرواتب',
  'company-accountant-engagements': 'واجهة المحاسب القانوني',
  'sensitive-devices': 'تسجيل وتتبع الأجهزة الحساسة',
  'after-sales': 'بطاقات الكفالة',
  'service-orders': 'أوامر الصيانة',
  'hr-org': 'الهيكل التنظيمي',
  'hr-attendance': 'الحضور والانصراف',
  'hr-check-in': 'تسجيل حضوري',
  'hr-requests': 'الطلبات والسلف',
  'hr-contracts': 'العقود ومسير الرواتب',
  'points-management': 'إدارة النقاط',
  settings: 'الإعدادات',
  attendance: 'الحضور والغياب',
  'sales-invoices': 'فواتير المبيعات',
  'sales-customer-payments': 'دفعات العملاء',
  'sales-customers': 'العملاء',
  'sales-settings': 'إعدادات المبيعات',
  'purchase-settings': 'إعدادات الشراء',
  'purchase-receipts': 'إرساليات الشراء',
  'sales-delivery-notes': 'إرساليات البيع',
  'product-profile': 'بطاقة المنتج',
  'product-group': 'كرت مجمّع (براندات)',
  'purchase-invoices': 'فواتير الشراء',
  'international-invoices': 'الفواتير الدولية',
  'old-invoices': 'أرشيف الفواتير',
  'price-offers': 'عروض الأسعار',
  'import-offers': 'عروض وطلبيات الاستيراد',
  'deals-management': 'إدارة الصفقات',
  'items-management': 'المنتجات',
  'items-categories': 'فئات المنتجات',
  'supplier-management': 'الموردين',
  'shipments-management': 'إدارة الشحنات',
  'customs-clearance': 'التخليص الجمركي',
  'local-shipping': 'الشحن المحلي',
  'cash-boxes': 'صناديق الكاش',
  'cash-box-details': 'كشف الصندوق',
  gallery: 'صالة الصور',
  'accounting-coa': 'شجرة الحسابات',
  'accounting-journals': 'دفتر اليومية',
  'accounting-journal-entry': 'قيد اليومية',
  'accounting-cheques': 'الشيكات',
  'accounting-banks': 'البنوك وفروعها',
  'accounting-bank-reconciliation': 'المطابقة البنكية',
  'accounting-general-ledger': 'الأستاذ العام',
  'accounting-trial-balance': 'ميزان المراجعة',
  'accounting-vat-report': 'تقرير ضريبة القيمة المضافة',
  'accounting-landed-cost': 'تقرير التكلفة المستوردة',
  'accounting-fiscal-periods': 'الفترات المالية',
  'accounting-exchange-rates': 'أسعار الصرف',
  'accounting-balance-sheet': 'الميزانية العمومية',
  'accounting-income-statement': 'قائمة الدخل',
  'accounting-vat-statements': 'كشوف ضريبة القيمة المضافة',
  'accounting-year-end-close': 'الإغلاق السنوي',
  'accounting-opening-balances': 'الأرصدة الافتتاحية',
  'accounting-expense-vouchers': 'سندات المصروف',
  'accounting-revenue-vouchers': 'سندات الإيراد',
  'document-coding': 'ترميز مستندات',
  'client-books': 'دفاتر عملائي',
  'sales-return': 'مرجع البيع',
  'purchase-return': 'مرجع الشراء',
  'supplier-payments': 'سندات الصرف للموردين',
  'invoice-profits': 'أرباح الفواتير',
  'reserved-stock': 'تقرير المحجوزات',
  'partner-profile': 'ملف الشريك',
  'stock-levels': 'أرصدة المخزون',
  'stock-movements': 'حركات المخزون',
  'product-cost': 'تكلفة المنتجات',
  'warehouses': 'المستودعات',
  'warehouse-transfer': 'تحويل بين المستودعات',
  'stocktake': 'الجرد',
  'property-rental': 'تأجير العقارات',
  'sql-products': 'المنتجات (SQL)',
  'sql-partners': 'دليل الأطراف',
  'sql-deals': 'الصفقات (SQL)',
  'sql-shipments': 'الشحنات (SQL)',
  sourcing: 'البحث',
  'smart-assistant': 'المساعد الذكي',
  store: 'المتجر',
  'store-settings': 'متجري',
  'ui-kit': 'مكوّنات الواجهة',
  'sales-classic': 'فاتورة المبيعات (كلاسيكي)',
  'sales-quotations': 'عروض وطلبيات البيع',
  'credit-debit-notes': 'الإشعارات المدينة/الدائنة',
  'sql-clearances': 'التخليص (SQL)',
  'sql-purchase-invoices': 'فواتير الشراء (SQL)',
  shipments: 'الشحنات',
  'shipment-management': 'إدارة الشحنات',
  'import-flow': 'رحلة الاستيراد',
  'import-file-guide': 'مستندات ملف الاستيراد',
  clearance: 'التخليص الجمركي',
  'group-constants': 'ثوابت المجموعة',
  'activity-log': 'سجل النشاط',
  'permissions': 'الصلاحيات والأدوار',
  'about-us': 'من نحن',
  contact: 'تواصل معنا',
};

interface BreadcrumbItem {
  label: string;
}

export interface BreadcrumbProps {
  activeView: AppView;
  /** مسار قائمة الشاشة الحالية (`VIEW_PATHS[activeView]` في `App.tsx`) —
   *  وجهةُ «رجوع» حين لا سابقة في هذا التبويب. */
  listPath?: string;
}

export const Breadcrumb: React.FC<BreadcrumbProps> = ({ activeView, listPath }) => {
  const crumbs: BreadcrumbItem[] = [];
  const label = VIEW_LABELS[activeView] ?? activeView;
  const back = useAppBack(listPath, label);
  // عدّاد ضغطات «رجوع» — يوقظ لمحة «لديك أيضاً» مرّةً واحدة لا مع كل رسمة.
  const [backPresses, setBackPresses] = useState(0);

  if (activeView.startsWith('accounting-journal-entry')) {
    crumbs.push({ label: 'دفتر اليومية' });
    crumbs.push({ label: 'قيد اليومية' });
  } else {
    crumbs.push({ label });
  }

  return (
    <div className="relative flex items-center gap-3">
      <button
        type="button"
        onClick={() => {
          back.go();
          setBackPresses((n) => n + 1);
        }}
        className="px-3 py-1.5 rounded-lg bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold transition-all flex items-center gap-1.5 border border-[var(--color-border)] shadow-sm"
        title={back.hint}
        aria-label={back.hint}
      >
        <ArrowRight className="h-4 w-4" />
        <span className="text-sm">{back.label}</span>
      </button>
      <LinkedTabHint trigger={backPresses} />
      <TabOriginChip />

      <nav aria-label="breadcrumb" className="flex items-center gap-1 text-[var(--font-size-sm)] border-s border-[var(--color-border)] ps-2">
        {crumbs.map((crumb, i) => (
          <React.Fragment key={i}>
            {i > 0 && <ChevronLeft className="h-3 w-3 text-[var(--color-text-muted)]" />}
            <span className={i === crumbs.length - 1
              ? 'font-semibold text-[var(--color-text)]'
              : 'text-[var(--color-text-muted)]'}>
              {crumb.label}
            </span>
          </React.Fragment>
        ))}
      </nav>
    </div>
  );
};
