import React from 'react';
import { AppView } from '../../types';
import { ChevronLeft } from 'lucide-react';

export const VIEW_LABELS: Record<AppView, string> = {
  dashboard: 'الرئيسية',
  tasks: 'مهامي',
  'task-management': 'إدارة المهام',
  users: 'قائمة المستخدمين',
  reports: 'التقارير',
  'employee-notes': 'ملاحظات الموظفين',
  'points-history': 'سجل نقاطي',
  'points-management': 'إدارة النقاط',
  settings: 'الإعدادات',
  attendance: 'الحضور والغياب',
  'sales-invoices': 'فواتير المبيعات',
  'sales-customer-payments': 'دفعات العملاء',
  'sales-customers': 'العملاء',
  'sales-settings': 'إعدادات المبيعات',
  'purchase-invoices': 'فواتير الشراء',
  'old-invoices': 'أرشيف الفواتير',
  'price-offers': 'عروض الأسعار',
  'deals-management': 'إدارة الصفقات',
  'items-management': 'الأصناف',
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
  'sales-return': 'مرجع البيع',
  'purchase-return': 'مرجع الشراء',
  'supplier-payments': 'سندات الصرف للموردين',
  'stock-levels': 'أرصدة المخزون',
  'stock-movements': 'حركات المخزون',
  'property-rental': 'تأجير العقارات',
  'sql-products': 'المنتجات (SQL)',
  'sql-partners': 'الشركاء (SQL)',
  'sql-deals': 'الصفقات (SQL)',
  'sql-shipments': 'الشحنات (SQL)',
  sourcing: 'البحث',
  'smart-assistant': 'المساعد الذكي',
  store: 'المتجر',
  'aseel-kit': 'مكوّنات الأصيل',
  'aseel-sales': 'فاتورة المبيعات (الأصيل)',
  'sales-quotations': 'العروض والطلبيات',
  'credit-debit-notes': 'الإشعارات المدينة/الدائنة',
  'sql-clearances': 'التخليص (SQL)',
  'sql-purchase-invoices': 'فواتير الشراء (SQL)',
  shipments: 'الشحنات',
  'shipment-management': 'إدارة الشحنات',
  clearance: 'التخليص الجمركي',
  'group-constants': 'ثوابت المجموعة',
};

interface BreadcrumbItem {
  label: string;
}

export const Breadcrumb: React.FC<{ activeView: AppView }> = ({ activeView }) => {
  const crumbs: BreadcrumbItem[] = [];
  const label = VIEW_LABELS[activeView] ?? activeView;

  if (activeView.startsWith('accounting-journal-entry')) {
    crumbs.push({ label: 'دفتر اليومية' });
    crumbs.push({ label: 'قيد اليومية' });
  } else {
    crumbs.push({ label });
  }

  return (
    <nav aria-label="breadcrumb" className="flex items-center gap-1 text-[var(--font-size-sm)]">
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
  );
};