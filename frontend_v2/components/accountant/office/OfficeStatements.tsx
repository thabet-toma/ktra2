import React from 'react';

import type { ClientStatements, ClientSummary, StatementRow } from '../../../services/accountantApi';
import { formatNumber } from '../../../utils/formatNumber';
import { OfficeCard, OfficeEmpty } from './OfficeUi';

/** سطر بيان مالي: اسم الحساب يميناً ومبلغه يساراً بخط أحادي — كما تُقرأ البيانات. */
const StatementLine: React.FC<{ row: StatementRow }> = ({ row }) => (
  <li className="flex items-center justify-between gap-4 border-b border-dashed border-slate-200 py-2 last:border-0 dark:border-slate-800">
    <span className="text-sm text-slate-700 dark:text-slate-200">
      {row.code && <span className="ml-2 font-mono text-xs text-slate-400">{row.code}</span>}
      {row.name}
    </span>
    <span className="font-mono text-sm font-bold" style={{ direction: 'ltr' }}>{formatNumber(row.amount)}</span>
  </li>
);

const StatementSection: React.FC<{
  title: string;
  rows: StatementRow[];
  total: string;
  totalLabel: string;
}> = ({ title, rows, total, totalLabel }) => (
  <div>
    <h3 className="mb-2 text-sm font-black text-slate-500 dark:text-slate-400">{title}</h3>
    {rows.length === 0 ? (
      <p className="rounded-xl border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500 dark:border-slate-700">لا حركة</p>
    ) : (
      <ul>{rows.map((row) => <StatementLine key={row.account_id} row={row} />)}</ul>
    )}
    <div className="mt-2 flex items-center justify-between rounded-xl bg-slate-100 px-3 py-2 dark:bg-slate-800">
      <span className="text-sm font-black">{totalLabel}</span>
      <span className="font-mono text-sm font-black" style={{ direction: 'ltr' }}>{formatNumber(total)}</span>
    </div>
  </div>
);

/** قائمة الدخل: إيرادات − مصاريف = صافي الربح. */
export const IncomeStatement: React.FC<{ data: ClientStatements }> = ({ data }) => (
  <OfficeCard title={`قائمة الدخل — ${data.period_from} إلى ${data.period_to}`}>
    <div className="grid gap-6 lg:grid-cols-2">
      <StatementSection title="الإيرادات" rows={data.income.revenue} total={data.income.revenue_total} totalLabel="إجمالي الإيرادات" />
      <StatementSection title="المصاريف" rows={data.income.expenses} total={data.income.expense_total} totalLabel="إجمالي المصاريف" />
    </div>
    <div className={`mt-6 flex items-center justify-between rounded-2xl px-5 py-4 ${Number(data.income.profit) >= 0 ? 'bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100' : 'bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-100'}`}>
      <span className="text-lg font-black">{Number(data.income.profit) >= 0 ? 'صافي الربح' : 'صافي الخسارة'}</span>
      <span className="font-mono text-2xl font-black" style={{ direction: 'ltr' }}>{formatNumber(data.income.profit)}</span>
    </div>
  </OfficeCard>
);

/** الميزانية العمومية: أصول = خصوم + حقوق ملكية، والفرق يُعرض صراحةً. */
export const BalanceSheet: React.FC<{ data: ClientStatements }> = ({ data }) => (
  <OfficeCard title={`الميزانية العمومية — حتى ${data.period_to}`}>
    <div className="grid gap-6 lg:grid-cols-2">
      <StatementSection title="الأصول" rows={data.balance.assets} total={data.balance.asset_total} totalLabel="إجمالي الأصول" />
      <div className="space-y-6">
        <StatementSection title="الخصوم" rows={data.balance.liabilities} total={data.balance.liability_total} totalLabel="إجمالي الخصوم" />
        <StatementSection title="حقوق الملكية" rows={data.balance.equity} total={data.balance.equity_total} totalLabel="إجمالي حقوق الملكية" />
      </div>
    </div>
    <p className={`mt-5 rounded-xl px-4 py-3 text-sm font-bold ${Number(data.balance.gap) === 0 ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-900'}`}>
      {Number(data.balance.gap) === 0
        ? 'الأصول تساوي الخصوم وحقوق الملكية — الميزانية متوازنة.'
        : `الفرق ${formatNumber(data.balance.gap)} — يمثّل أرباح الفترات غير المقفلة أو قيداً يحتاج مراجعة.`}
    </p>
  </OfficeCard>
);

/** ورقة الضريبة: ما يُسلَّم للدائرة — مخرجات ناقص مدخلات، بلا تفسير إضافي. */
export const VatReturnSheet: React.FC<{
  summary: ClientSummary;
  companyName: string;
}> = ({ summary, companyName }) => {
  const due = Number(summary.vat_due);
  return (
    <OfficeCard title="ورقة ضريبة القيمة المضافة">
      <div className="rounded-2xl border border-slate-200 p-5 dark:border-slate-800">
        <header className="mb-5 border-b border-slate-200 pb-4 text-center dark:border-slate-800">
          <h3 className="text-lg font-black">{companyName}</h3>
          <p className="text-sm text-slate-500">إقرار ضريبة القيمة المضافة · {summary.period_from} إلى {summary.period_to}</p>
        </header>
        <ul className="space-y-1">
          <StatementLine row={{ account_id: 1, code: '', name: 'ضريبة المبيعات (المخرجات)', amount: summary.output_vat }} />
          <StatementLine row={{ account_id: 2, code: '', name: 'ضريبة المشتريات (المدخلات)', amount: summary.input_vat }} />
        </ul>
        <div className={`mt-5 flex items-center justify-between rounded-2xl px-5 py-4 ${due >= 0 ? 'bg-indigo-50 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-100' : 'bg-emerald-50 text-emerald-900 dark:bg-emerald-950'}`}>
          <span className="text-lg font-black">{due >= 0 ? 'المستحق للدائرة' : 'رصيد لصالح الشركة'}</span>
          <span className="font-mono text-2xl font-black" style={{ direction: 'ltr' }}>{formatNumber(summary.vat_due)}</span>
        </div>
        <p className="mt-4 text-xs text-slate-500">
          المرتجعات مخصومة من جهتها. الأرقام من الفواتير المرحّلة داخل الفترة فقط.
        </p>
      </div>
    </OfficeCard>
  );
};

/** منحنى بسيط بأعمدة CSS — يكفي لقراءة الاتجاه بلا مكتبة رسم. */
export const TrendBars: React.FC<{ series: { month: string; revenue: string; expenses: string; profit: string }[] }> = ({ series }) => {
  if (series.length === 0) return <OfficeEmpty title="لا حركة في الأشهر الماضية" />;
  const peak = Math.max(
    1,
    ...series.map((point) => Math.max(Math.abs(Number(point.revenue)), Math.abs(Number(point.expenses)))),
  );
  return (
    <div className="flex items-end gap-4 overflow-x-auto pb-2" role="img" aria-label="اتجاه الإيرادات والمصاريف">
      {series.map((point) => (
        <div key={point.month} className="flex min-w-[3.5rem] flex-1 flex-col items-center gap-2">
          <div className="flex h-40 w-full items-end justify-center gap-1">
            <div
              className="w-1/3 rounded-t bg-emerald-500"
              style={{ height: `${Math.max(2, (Math.abs(Number(point.revenue)) / peak) * 100)}%` }}
              title={`إيرادات ${formatNumber(point.revenue)}`}
            />
            <div
              className="w-1/3 rounded-t bg-rose-400"
              style={{ height: `${Math.max(2, (Math.abs(Number(point.expenses)) / peak) * 100)}%` }}
              title={`مصاريف ${formatNumber(point.expenses)}`}
            />
          </div>
          <span className="font-mono text-[11px] text-slate-500" style={{ direction: 'ltr' }}>{point.month}</span>
        </div>
      ))}
    </div>
  );
};
