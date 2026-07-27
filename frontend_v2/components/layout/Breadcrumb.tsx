import React from 'react';
import { AppView } from '../../types';
import { ChevronLeft, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const VIEW_LABELS: Record<AppView, string> = {
  dashboard: 'الرئيسية',
  tasks: 'مهامي',
  'task-management': 'إدارة المهام',
  users: 'قائمة المستخدمين',
  reports: 'التقارير',
  'employee-notes': 'ملاحظات الموظفين',
  'points-history': 'سجل نقاطي',
  'sales-orders': 'عروض وطلبيات البيع',
  'personal-expenses': 'مصاريفي الشخصية',
  'points-management': 'إدارة النقاط',
  settings: 'الإعدادات',
  attendance: 'الحضور والغياب',
  'sales-invoices': 'فواتير المبيعات',
  'sales-customer-payments': 'دفعات العملاء',
  'sales-customers': 'العملاء',
  'sales-settings': 'إعدادات المبيعات',
  'purchase-settings': 'إعدادات الشراء',
  'product-profile': 'بطاقة الصنف',
  'product-group': 'كرت مجمّع (براندات)',
  'purchase-invoices': 'فواتير الشراء',
  'international-invoices': 'الفواتير الدولية',
  'old-invoices': 'أرشيف الفواتير',
  'price-offers': 'عروض الأسعار',
  'import-offers': 'عروض وطلبيات الاستيراد',
  'deals-management': 'إدارة الصفقات',
  'items-management': 'الأصناف',
  'items-categories': 'فئات الأصناف',
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
  'sales-return': 'مرجع البيع',
  'purchase-return': 'مرجع الشراء',
  'supplier-payments': 'سندات الصرف للموردين',
  'invoice-profits': 'أرباح الفواتير',
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
  'aseel-kit': 'مكوّنات الأصيل',
  'aseel-sales': 'فاتورة المبيعات (الأصيل)',
  'sales-quotations': 'عروض وطلبيات البيع',
  'credit-debit-notes': 'الإشعارات المدينة/الدائنة',
  'sql-clearances': 'التخليص (SQL)',
  'sql-purchase-invoices': 'فواتير الشراء (SQL)',
  shipments: 'الشحنات',
  'shipment-management': 'إدارة الشحنات',
  'import-flow': 'رحلة الاستيراد',
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

export const Breadcrumb: React.FC<{ activeView: AppView }> = ({ activeView }) => {
  const navigate = useNavigate();
  const crumbs: BreadcrumbItem[] = [];
  const label = VIEW_LABELS[activeView] ?? activeView;

  if (activeView.startsWith('accounting-journal-entry')) {
    crumbs.push({ label: 'دفتر اليومية' });
    crumbs.push({ label: 'قيد اليومية' });
  } else {
    crumbs.push({ label });
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => {
          console.log('[Routing] Back button clicked: Navigating back');
          navigate(-1);
        }}
        className="px-3 py-1.5 rounded-lg bg-[var(--color-surface-2)] hover:bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold transition-all flex items-center gap-1.5 border border-[var(--color-border)] shadow-sm"
        title="رجوع للصفحة السابقة"
        aria-label="رجوع"
      >
        <ArrowRight className="h-4 w-4" />
        <span className="text-sm">رجوع</span>
      </button>

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
