/**
 * N0-T4 — GroupConstantsPage (ثوابت المجموعة)
 * صفحة Aseel-style بـ AseelDocumentShell، 4 tabs:
 *   1. بيانات عامة — كل حقول TenantSettings
 *   2. أرقام الدفاتر — جدول AseelGrid لعرض كل TenantBook
 *   3. حسابات افتراضية — ينقل من SalesSettings
 *   4. ضرائب — ينقل من SalesSettings
 * Reference: docs/aseel_reference/tools.txt 10–200.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AseelDocumentShell,
  AseelFormSection,
  AseelGrid,
  type AseelGridColumn,
  type AseelToolbarAction,
} from '../aseel';
import { apiGetObject, apiPatchObject } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';

type TenantSettingsData = {
  id?: number;
  company_name_primary?: string | null;
  company_name_sub?: string | null;
  address?: string | null;
  po_box?: string | null;
  phone?: string | null;
  fax?: string | null;
  email?: string | null;
  licensed_dealer_no?: string | null;
  income_tax_file_no?: string | null;
  default_vat_rate?: string | null;
  default_source_discount_rate?: string | null;
  currency?: number | null;
  fiscal_period_label?: string | null;
  fiscal_period_start?: string | null;
  fiscal_period_end?: string | null;
  default_freight_credit_account?: number | null;
  mixture_auto_fill_enabled?: boolean;
  barcode_action?: string | null;
};

type TenantBookRow = {
  id: number;
  document_type: string;
  book_number: number;
  name: string;
  last_used_number: number;
  is_active: boolean;
};

type CurrencyRow = { CurrencyID: number; Code: string; Name?: string | null };
type AccountRow = { id: number; code?: string | null; name?: string | null };

const DOC_TYPE_LABELS: Record<string, string> = {
  sales_invoice: 'فاتورة مبيعات',
  purchase_invoice: 'فاتورة شراء',
  sales_return: 'مرجع بيع',
  purchase_return: 'مرجع شراء',
  receipt_voucher: 'سند قبض',
  payment_voucher: 'سند صرف',
  multi_receipt: 'إيصال قبض متعدد',
  multi_payment: 'سند صرف متعدد',
  credit_note: 'إشعار دائن',
  debit_note: 'إشعار مدين',
  quotation: 'عرض سعر',
  journal_entry: 'قيد محاسبة',
  deal: 'صفقة',
  shipment: 'شحنة',
  clearance: 'تخليص جمركي',
};

const fld = (label: string, node: React.ReactNode) => (
  <label className="aseel-field">
    <span className="aseel-field-label">{label}</span>
    {node}
  </label>
);

export const GroupConstantsPage: React.FC = () => {
  const tenantId = resolveTenantId();
  const [activeTab, setActiveTab] = useState(0);
  const [settings, setSettings] = useState<TenantSettingsData | null>(null);
  const [books, setBooks] = useState<TenantBookRow[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyRow[]>([]);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [localErr, setLocalErr] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [settingsRes, booksRes, currenciesRes, accountsRes] = await Promise.all([
        apiGetObject(`tenants/settings/`, { tenantId }).catch(() => null),
        apiGetObject(`tenants/books/`, { tenantId }).catch(() => []),
        apiGetObject(`tenants/currencies/`, { tenantId }).catch(() => []),
        apiGetObject(`accounting/accounts/`, { tenantId }).catch(() => []),
      ]);
      setSettings(settingsRes as TenantSettingsData | null);
      setBooks((booksRes as any[]) || []);
      setCurrencies((currenciesRes as any[]) || []);
      setAccounts((accountsRes as any[]) || []);
    } catch {
      setLocalErr('فشل تحميل البيانات');
    }
  }, [tenantId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setLocalErr(null);
    setMsg(null);
    try {
      await apiPatchObject(`tenants/settings/`, settings, { tenantId });
      setMsg('تم حفظ ثوابت المجموعة');
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : 'فشل الحفظ');
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = (key: keyof TenantSettingsData, value: any) => {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const tabs = useMemo(
    () => [
      { key: 'general', label: 'بيانات عامة' },
      { key: 'books', label: 'أرقام الدفاتر' },
      { key: 'accounts', label: 'حسابات افتراضية' },
      { key: 'taxes', label: 'ضرائب' },
    ],
    []
  );

  const toolbarActions: AseelToolbarAction[] = [
    {
      key: 'save',
      label: saving ? '...حفظ' : 'حفظ',
      onClick: handleSave,
      disabled: saving,
    },
    { key: 'refresh', label: 'تحديث', onClick: loadData },
  ];

  /* ── Tab 1: بيانات عامة ─────────────────────────────────── */
  const generalTab = settings && (
    <AseelFormSection title="بيانات الشركة" cols={3}>
      {fld('الاسم الرئيسي', (
        <input className="aseel-input" value={settings.company_name_primary || ''}
          onChange={(e) => updateSetting('company_name_primary', e.target.value)} />
      ))}
      {fld('الاسم الفرعي', (
        <input className="aseel-input" value={settings.company_name_sub || ''}
          onChange={(e) => updateSetting('company_name_sub', e.target.value)} />
      ))}
      {fld('العنوان', (
        <input className="aseel-input" value={settings.address || ''}
          onChange={(e) => updateSetting('address', e.target.value)} />
      ))}
      {fld('ص.ب', (
        <input className="aseel-input" value={settings.po_box || ''}
          onChange={(e) => updateSetting('po_box', e.target.value)} />
      ))}
      {fld('الهاتف', (
        <input className="aseel-input" value={settings.phone || ''}
          onChange={(e) => updateSetting('phone', e.target.value)} />
      ))}
      {fld('الفاكس', (
        <input className="aseel-input" value={settings.fax || ''}
          onChange={(e) => updateSetting('fax', e.target.value)} />
      ))}
      {fld('البريد الإلكتروني', (
        <input className="aseel-input" type="email" value={settings.email || ''}
          onChange={(e) => updateSetting('email', e.target.value)} />
      ))}
      {fld('رقم تاجر مرخص', (
        <input className="aseel-input" value={settings.licensed_dealer_no || ''}
          onChange={(e) => updateSetting('licensed_dealer_no', e.target.value)} />
      ))}
      {fld('رقم ملف ضريبة الدخل', (
        <input className="aseel-input" value={settings.income_tax_file_no || ''}
          onChange={(e) => updateSetting('income_tax_file_no', e.target.value)} />
      ))}
      {fld('نسبة ض.ق.م الافتراضية %', (
        <input className="aseel-input" type="number" value={settings.default_vat_rate || '16'}
          onChange={(e) => updateSetting('default_vat_rate', e.target.value)} />
      ))}
      {fld('نسبة خصم المصدر الافتراضية %', (
        <input className="aseel-input" type="number" value={settings.default_source_discount_rate || '0'}
          onChange={(e) => updateSetting('default_source_discount_rate', e.target.value)} />
      ))}
      {fld('العملة', (
        <select className="aseel-input" value={settings.currency || ''}
          onChange={(e) => updateSetting('currency', e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {currencies.map((c) => (
            <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code} — {c.Name}</option>
          ))}
        </select>
      ))}
      {fld('تسمية الفترة المالية', (
        <input className="aseel-input" value={settings.fiscal_period_label || ''}
          onChange={(e) => updateSetting('fiscal_period_label', e.target.value)} />
      ))}
      {fld('بداية الفترة', (
        <input className="aseel-input" type="date" value={settings.fiscal_period_start || ''}
          onChange={(e) => updateSetting('fiscal_period_start', e.target.value)} />
      ))}
      {fld('نهاية الفترة', (
        <input className="aseel-input" type="date" value={settings.fiscal_period_end || ''}
          onChange={(e) => updateSetting('fiscal_period_end', e.target.value)} />
      ))}
      {fld('حساب أجرة الشحن (دائن)', (
        <select className="aseel-input" value={settings.default_freight_credit_account || ''}
          onChange={(e) => updateSetting('default_freight_credit_account', e.target.value ? Number(e.target.value) : null)}>
          <option value="">— اختر —</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
          ))}
        </select>
      ))}
      {fld('إجراء الباركود', (
        <select className="aseel-input" value={settings.barcode_action || 'index'}
          onChange={(e) => updateSetting('barcode_action', e.target.value)}>
          <option value="index">فتح فهرس الأصناف</option>
          <option value="cashier">فتح فاتورة كاشير</option>
        </select>
      ))}
      <label className="aseel-field aseel-field--inline">
        <input type="checkbox" checked={settings.mixture_auto_fill_enabled || false}
          onChange={(e) => updateSetting('mixture_auto_fill_enabled', e.target.checked)} />
        <span className="aseel-field-label" style={{ flex: 'unset' }}>تعبئة تلقائية للمخلوط</span>
      </label>
    </AseelFormSection>
  );

  /* ── Tab 2: أرقام الدفاتر ───────────────────────────────── */
  const bookColumns: AseelGridColumn<TenantBookRow>[] = [
    { key: 'document_type', header: 'نوع المستند', width: '25%', render: (r) => DOC_TYPE_LABELS[r.document_type] || r.document_type },
    { key: 'book_number', header: 'رقم الدفتر', width: '80px', align: 'center' },
    { key: 'name', header: 'الاسم' },
    { key: 'last_used_number', header: 'آخر رقم مستخدم', width: '120px', align: 'center' },
    { key: 'is_active', header: 'نشط', width: '60px', align: 'center', render: (r) => r.is_active ? '✓' : '✗' },
  ];

  const booksTab = (
    <AseelFormSection title="أرقام الدفاتر" cols={1}>
      <AseelGrid columns={bookColumns} rows={books} getRowKey={(r) => `${r.document_type}-${r.book_number}`} getCell={(r, k) => (r as any)[k] ?? ''} />
    </AseelFormSection>
  );

  /* ── Tab 3: حسابات افتراضية ─────────────────────────────── */
  const accountsTab = (
    <AseelFormSection title="حسابات افتراضية" cols={2}>
      <p className="aseel-hint">يتم نقل الحسابات الافتراضية من صفحة إعدادات المبيعات.</p>
    </AseelFormSection>
  );

  /* ── Tab 4: ضرائب ───────────────────────────────────────── */
  const taxesTab = (
    <AseelFormSection title="ضرائب" cols={2}>
      <p className="aseel-hint">يتم نقل إعدادات الضرائب من صفحة إعدادات المبيعات.</p>
    </AseelFormSection>
  );

  const tabContent = [generalTab, booksTab, accountsTab, taxesTab][activeTab];

  const banner = localErr || msg ? (
    <div className={`aseel-banner ${localErr ? 'aseel-banner--err' : 'aseel-banner--ok'}`}>
      <span>{localErr || msg}</span>
    </div>
  ) : null;

  return (
    <div dir="rtl" style={{ height: 'calc(100vh - 13rem)', minHeight: 560 }}>
      <AseelDocumentShell
        title="ثوابت المجموعة"
        state="F11"
        actions={toolbarActions}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        header={null}
      >
        {banner}
        {tabContent}
      </AseelDocumentShell>
    </div>
  );
};
