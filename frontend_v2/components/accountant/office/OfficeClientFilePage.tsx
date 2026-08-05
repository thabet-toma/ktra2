import React, { useCallback, useEffect, useState } from 'react';
import { ArrowRight, Download, Printer } from 'lucide-react';

import {
  downloadReviewPackageCsv,
  getClientStatements,
  getClientSummary,
  getClientTrend,
  listClientDocuments,
  type ClientExpenseRow,
  type ClientInvoiceRow,
  type ClientStatements,
  type ClientSummary,
  type TrendPoint,
} from '../../../services/accountantApi';
import { formatNumber } from '../../../utils/formatNumber';
import { printReport } from '../../../utils/printReport';
import { OfficeCard, OfficeError, OfficeSkeleton, OfficeStat, OfficeTable } from './OfficeUi';
import { BalanceSheet, IncomeStatement, TrendBars, VatReturnSheet } from './OfficeStatements';

type Tab = 'overview' | 'income' | 'balance' | 'vat' | 'sales' | 'purchases' | 'expenses';

// ترتيب المهنة: نظرة عامة ← البيانات المالية ← الإقرار ← المستندات الخام.
const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'نظرة عامة' },
  { key: 'income', label: 'قائمة الدخل' },
  { key: 'balance', label: 'الميزانية العمومية' },
  { key: 'vat', label: 'إقرار الضريبة' },
  { key: 'sales', label: 'فواتير البيع' },
  { key: 'purchases', label: 'فواتير الشراء' },
  { key: 'expenses', label: 'المصاريف' },
];

const monthStart = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
};

const monthEnd = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
};

/**
 * ملف الزبون: سحب مستنداته وحساب ربحه وضريبته **بحسبة مباشرة**:
 * الإيرادات − المصاريف = الربح · ضريبة المخرجات − ضريبة المدخلات = المستحق.
 */
export const OfficeClientFilePage: React.FC<{
  tenantId: number;
  companyName: string;
  onBack: () => void;
}> = ({ tenantId, companyName, onBack }) => {
  const [tab, setTab] = useState<Tab>('overview');
  const [range, setRange] = useState({ from: monthStart(), to: monthEnd() });
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [statements, setStatements] = useState<ClientStatements | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [invoices, setInvoices] = useState<ClientInvoiceRow[]>([]);
  const [expenses, setExpenses] = useState<ClientExpenseRow[]>([]);
  const [totals, setTotals] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // الفتح المباشر بالرابط (/office/clients/5) يصل بلا اسم — نأخذه من الخادم.
  const [title, setTitle] = useState(companyName);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    const done = () => setLoading(false);
    if (tab === 'overview' || tab === 'vat') {
      Promise.all([
        getClientSummary(tenantId, range.from, range.to),
        tab === 'overview' ? getClientTrend(tenantId, 6) : Promise.resolve({ series: [] as TrendPoint[] }),
      ])
        .then(([summaryRes, trendRes]) => {
          setSummary(summaryRes.summary);
          if (summaryRes.company_name) setTitle(summaryRes.company_name);
          setTrend(trendRes.series);
        })
        .catch(() => setError('تعذّر حساب أرقام هذا الزبون.'))
        .finally(done);
      return;
    }
    if (tab === 'income' || tab === 'balance') {
      getClientStatements(tenantId, range.from, range.to)
        .then((res) => { setStatements(res); if (res.company_name) setTitle(res.company_name); })
        .catch(() => setError('تعذّر تجهيز البيانات المالية.'))
        .finally(done);
      return;
    }
    if (tab === 'expenses') {
      listClientDocuments<ClientExpenseRow>(tenantId, 'expenses', range.from, range.to)
        .then((res) => { setExpenses(res.results); setTotals(res.totals); })
        .catch(() => setError('تعذّر سحب المصاريف.'))
        .finally(done);
      return;
    }
    listClientDocuments<ClientInvoiceRow>(tenantId, tab, range.from, range.to)
      .then((res) => { setInvoices(res.results); setTotals(res.totals); })
      .catch(() => setError('تعذّر سحب الفواتير.'))
      .finally(done);
  }, [tenantId, tab, range.from, range.to]);

  useEffect(load, [load]);

  const exportCsv = async () => {
    try {
      const blob = await downloadReviewPackageCsv(tenantId, {
        period_from: range.from,
        period_to: range.to,
      });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${title || companyName}-${range.from}-${range.to}.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch {
      setError('تعذّر تصدير ملف الزبون.');
    }
  };

  const printCurrent = () => {
    if (tab === 'expenses') {
      printReport({
        title: `مصاريف ${title || companyName}`,
        subtitle: `${range.from} → ${range.to}`,
        columns: [
          { header: 'الحساب', value: (row: ClientExpenseRow) => `${row.code} — ${row.name}` },
          { header: 'عدد القيود', value: (row: ClientExpenseRow) => row.entries, numeric: true },
          { header: 'المبلغ', value: (row: ClientExpenseRow) => formatNumber(row.amount), numeric: true },
        ],
        rows: expenses,
        emptyHint: 'لا مصاريف في هذه الفترة.',
      });
      return;
    }
    if ((tab === 'overview' || tab === 'vat') && summary) {
      printReport({
        title: tab === 'vat' ? `إقرار ضريبة — ${title || companyName}` : `ملخص ${title || companyName}`,
        subtitle: `${range.from} → ${range.to}`,
        columns: [
          { header: 'البند', value: (row: { label: string; value: string }) => row.label },
          { header: 'القيمة', value: (row: { label: string; value: string }) => formatNumber(row.value), numeric: true },
        ],
        rows: [
          { label: 'الإيرادات', value: summary.revenue },
          { label: 'المصاريف', value: summary.expenses },
          { label: 'الربح', value: summary.profit },
          { label: 'ضريبة المخرجات', value: summary.output_vat },
          { label: 'ضريبة المدخلات', value: summary.input_vat },
          { label: 'المستحق للضريبة', value: summary.vat_due },
        ],
      });
      return;
    }
    printReport({
      title: `${tab === 'sales' ? 'فواتير بيع' : 'فواتير شراء'} — ${title || companyName}`,
      subtitle: `${range.from} → ${range.to}`,
      columns: [
        { header: 'الرقم', value: (row: ClientInvoiceRow) => row.invoice_number },
        { header: 'التاريخ', value: (row: ClientInvoiceRow) => row.invoice_date },
        { header: 'النوع', value: (row: ClientInvoiceRow) => row.kind_label },
        { header: 'الطرف', value: (row: ClientInvoiceRow) => row.partner_name },
        { header: 'قبل الضريبة', value: (row: ClientInvoiceRow) => formatNumber(row.subtotal), numeric: true },
        { header: 'الضريبة', value: (row: ClientInvoiceRow) => formatNumber(row.tax_amount), numeric: true },
        { header: 'الإجمالي', value: (row: ClientInvoiceRow) => formatNumber(row.grand_total), numeric: true },
      ],
      rows: invoices,
      emptyHint: 'لا فواتير في هذه الفترة.',
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button type="button" onClick={onBack} className="rounded-xl border border-slate-300 p-2 dark:border-slate-700" aria-label="عودة للزبائن">
            <ArrowRight className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-black text-slate-900 dark:text-white">{title || companyName}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">ملف زبون — قراءة وتحليل فقط</p>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="mb-1 block text-xs font-bold text-slate-500" htmlFor="client-from">من</label>
            <input id="client-from" type="date" value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} className="rounded-xl border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-bold text-slate-500" htmlFor="client-to">إلى</label>
            <input id="client-to" type="date" value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} className="rounded-xl border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950" />
          </div>
          <button type="button" onClick={printCurrent} className="flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 font-bold dark:border-slate-700">
            <Printer className="h-4 w-4" />طباعة
          </button>
          <button type="button" onClick={() => void exportCsv()} className="flex items-center gap-2 rounded-xl border border-slate-300 px-4 py-2 font-bold dark:border-slate-700">
            <Download className="h-4 w-4" />CSV
          </button>
        </div>
      </div>

      <nav className="flex flex-wrap gap-2" aria-label="أقسام ملف الزبون">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            aria-current={tab === item.key}
            className={`rounded-xl px-4 py-2 font-bold transition ${
              tab === item.key
                ? 'bg-indigo-700 text-white'
                : 'border border-slate-300 text-slate-700 hover:border-indigo-400 dark:border-slate-700 dark:text-slate-200'
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {loading ? <OfficeSkeleton rows={6} /> : error ? <OfficeError message={error} onRetry={load} /> : (
        <>
          {tab === 'overview' && summary && (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                <OfficeStat label="الإيرادات" value={formatNumber(summary.revenue)} hint="إيرادات الفترة من القيود المرحّلة" />
                <OfficeStat label="المصاريف" value={formatNumber(summary.expenses)} hint="كل حسابات المصاريف" />
                <OfficeStat label="الربح" value={formatNumber(summary.profit)} hint="الإيرادات − المصاريف" tone={Number(summary.profit) >= 0 ? 'positive' : 'negative'} />
                <OfficeStat label="ضريبة المخرجات" value={formatNumber(summary.output_vat)} hint="مبيعات ناقص مرتجعاتها" />
                <OfficeStat label="ضريبة المدخلات" value={formatNumber(summary.input_vat)} hint="مشتريات ناقص مرتجعاتها" />
                <OfficeStat
                  label={Number(summary.vat_due) >= 0 ? 'المستحق للضريبة' : 'رصيد لصالح الشركة'}
                  value={formatNumber(summary.vat_due)}
                  hint="مخرجات − مدخلات"
                  tone="accent"
                />
              </div>

              <OfficeCard title="اتجاه آخر ستة أشهر" actions={<span className="text-xs text-slate-500">أخضر: إيرادات · وردي: مصاريف</span>}>
                <TrendBars series={trend} />
              </OfficeCard>

              <div className="grid gap-4 sm:grid-cols-3">
                <OfficeStat label="الأصول" value={formatNumber(summary.assets)} hint={`حتى ${range.to}`} />
                <OfficeStat label="الخصوم" value={formatNumber(summary.liabilities)} />
                <OfficeStat label="حقوق الملكية" value={formatNumber(summary.equity)} />
              </div>

              <OfficeCard title="ماذا أفعل الآن؟">
                <div className="flex flex-wrap gap-2">
                  <button type="button" onClick={() => setTab('income')} className="rounded-xl bg-indigo-700 px-4 py-2 font-bold text-white">قائمة الدخل</button>
                  <button type="button" onClick={() => setTab('balance')} className="rounded-xl border border-slate-300 px-4 py-2 font-bold dark:border-slate-700">الميزانية العمومية</button>
                  <button type="button" onClick={() => setTab('vat')} className="rounded-xl border border-slate-300 px-4 py-2 font-bold dark:border-slate-700">ورقة الضريبة</button>
                  <button type="button" onClick={() => setTab('sales')} className="rounded-xl border border-slate-300 px-4 py-2 font-bold dark:border-slate-700">مراجعة فواتير البيع</button>
                </div>
              </OfficeCard>
            </div>
          )}

          {tab === 'income' && statements && <IncomeStatement data={statements} />}
          {tab === 'balance' && statements && <BalanceSheet data={statements} />}
          {tab === 'vat' && summary && <VatReturnSheet summary={summary} companyName={title || companyName} />}

          {(tab === 'sales' || tab === 'purchases') && (
            <OfficeCard title={tab === 'sales' ? 'فواتير البيع' : 'فواتير الشراء'}>
              <OfficeTable
                columns={[
                  { key: 'number', header: 'الرقم' },
                  { key: 'date', header: 'التاريخ' },
                  { key: 'kind', header: 'النوع' },
                  { key: 'partner', header: 'الطرف' },
                  { key: 'tax_number', header: 'الرقم الضريبي' },
                  { key: 'status', header: 'الحالة' },
                  { key: 'subtotal', header: 'قبل الضريبة', numeric: true },
                  { key: 'tax', header: 'الضريبة', numeric: true },
                  { key: 'total', header: 'الإجمالي', numeric: true },
                ]}
                rows={invoices.map((row) => ({
                  __key: row.id,
                  number: row.invoice_number,
                  date: row.invoice_date,
                  kind: row.kind_label,
                  partner: row.partner_name,
                  tax_number: row.partner_tax_number || '—',
                  status: row.status_label,
                  subtotal: formatNumber(row.subtotal),
                  tax: formatNumber(row.tax_amount),
                  total: formatNumber(row.grand_total),
                }))}
                footer={{
                  number: 'الإجمالي (المرتجعات مخصومة)',
                  subtotal: formatNumber(totals.subtotal || '0'),
                  tax: formatNumber(totals.tax_amount || '0'),
                  total: formatNumber(totals.grand_total || '0'),
                }}
              />
            </OfficeCard>
          )}

          {tab === 'expenses' && (
            <OfficeCard title="المصاريف مجمّعة بالحساب">
              <OfficeTable
                columns={[
                  { key: 'code', header: 'رمز الحساب' },
                  { key: 'name', header: 'الحساب' },
                  { key: 'entries', header: 'عدد القيود', numeric: true },
                  { key: 'amount', header: 'المبلغ', numeric: true },
                ]}
                rows={expenses.map((row) => ({
                  __key: row.account_id,
                  code: row.code || '—',
                  name: row.name,
                  entries: formatNumber(row.entries),
                  amount: formatNumber(row.amount),
                }))}
                footer={{ name: 'إجمالي المصاريف', amount: formatNumber(totals.amount || '0') }}
                emptyHint="المصاريف تُقرأ من القيود المرحّلة على حسابات المصروفات."
              />
            </OfficeCard>
          )}
        </>
      )}
    </div>
  );
};

export default OfficeClientFilePage;
