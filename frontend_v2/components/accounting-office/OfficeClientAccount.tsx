import React, { useCallback, useEffect, useState } from 'react';

import {
  listFeeLedger,
  type FeeLedgerPayload,
} from '../../services/accountingOfficeApi';
import {
  accountBalanceClass,
  accountBalanceTone,
  formatOfficeAmount,
} from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import {
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
} from './OfficeUi';

/**
 * ISSUE #282/أ٢/٢ — تبويبُ «الحساب» في ملفّ الزبون.
 *
 * **أربعةُ أرقامٍ من دالّةٍ واحدة**: «اللي عليه» ورصيده الدائن والمُصدَر
 * والمُقبَض كلُّها من `client_due` في `fees/ledger/` — وهي `payments.client_due`
 * نفسُها في الخادم، لا حسابَ ثانٍ في الواجهة. **والقناعُ يُحترم**: العضوُ بلا
 * `office.amounts.view` يقرأ `null` فتُعرض «—» ولا تُحوَّل إلى صفر.
 *
 * **وحالةُ كلّ فاتورةٍ من الخادم** (`state_label`): «مدفوعة/مدفوعة جزئياً/غير
 * مدفوعة» تصل مكتوبةً من `payments.INVOICE_STATE_LABELS`، فلا جدولَ تسمياتٍ هنا.
 *
 * والقراءةُ واحدةٌ عند فتح التبويب — لا تُطلَب مع كل فتحِ ملفّ: حسابُ الزبون لا
 * يخصّ بطاقته الضريبية ولا ملاحظاته.
 */
export const OfficeClientAccount: React.FC<{
  clientId: number;
  /** رقمُ الملفّ الضريبيّ من رأس الملفّ — لا يُطلب مرّةً ثانية من الشبكة. */
  taxFileNumber: string;
}> = ({ clientId, taxFileNumber }) => {
  const [payload, setPayload] = useState<FeeLedgerPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);

  const reload = useCallback(() => setRefreshToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    listFeeLedger(clientId)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((failure) => {
        if (!cancelled) {
          setPayload(null);
          setError(humanizeThrown(failure, 'تعذّر تحميل حساب الزبون.'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, refreshToken]);

  if (loading) return <OfficeSkeleton rows={4} />;
  if (error) return <OfficeError message={error} onRetry={reload} />;

  const due = payload?.client_due ?? null;
  const invoices = payload?.invoices.results ?? [];
  const tone = accountBalanceTone(due?.due);
  const taxNoteTone = accountBalanceTone(due?.tax_note);
  const showsTaxNote = taxNoteTone === 'owed' || taxNoteTone === 'refund';

  return (
    <div className="space-y-4">
      <OfficeCard title="حساب الزبون">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Figure
            label="اللي عليه"
            value={formatOfficeAmount(due?.due)}
            className={`text-[18px] font-bold ${accountBalanceClass(tone)}`}
            hint={
              tone === 'refund' ? 'له عندنا'
                : tone === 'settled' ? 'مسدَّد'
                  : undefined
            }
          />
          <Figure label="رصيده الدائن" value={formatOfficeAmount(due?.credit)} />
          <Figure label="إجمالي فواتيره" value={formatOfficeAmount(due?.invoices_total)} />
          <Figure label="المقبوض" value={formatOfficeAmount(due?.paid_total)} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-slate-600 dark:text-slate-300">
          <span>
            رقم الملفّ الضريبي:{' '}
            <span className="font-semibold text-slate-800 dark:text-slate-100">
              {taxFileNumber || '—'}
            </span>
          </span>
          <span>
            فواتيرُه الصادرة:{' '}
            <span className="font-semibold">{payload?.invoices.count ?? 0}</span>
            {' · '}غيرُ مسدَّدة: <span className="font-semibold">{due?.unpaid_count ?? 0}</span>
          </span>
          {showsTaxNote ? (
            <span className="text-amber-700 dark:text-amber-400">
              عليه التزاماتٌ ضريبية: {formatOfficeAmount(due?.tax_note)}
            </span>
          ) : null}
        </div>
      </OfficeCard>

      <OfficeCard title="فواتيره الصادرة والمدفوعة">
        {invoices.length === 0 ? (
          <OfficeEmpty
            title="لا فواتير صادرة"
            hint="تُصدر فاتورةُ الزبون بالاعتماد من شاشة «المسودّات»."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[12px]">
              <thead>
                <tr className="border-b border-slate-200 text-[11px] text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2 text-start font-semibold">الفترة</th>
                  <th className="px-2 py-2 text-start font-semibold">الإجمالي</th>
                  <th className="px-2 py-2 text-start font-semibold">المدفوع</th>
                  <th className="px-2 py-2 text-start font-semibold">الباقي</th>
                  <th className="px-2 py-2 text-start font-semibold">الحالة</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr
                    key={invoice.id}
                    className="border-b border-slate-100 dark:border-slate-800"
                  >
                    <td className="px-2 py-2 font-medium text-slate-800 dark:text-slate-100">
                      {invoice.period_label}
                    </td>
                    <td className="px-2 py-2 tabular-nums text-slate-700 dark:text-slate-200">
                      {formatOfficeAmount(invoice.total)}
                    </td>
                    <td className="px-2 py-2 tabular-nums text-slate-700 dark:text-slate-200">
                      {formatOfficeAmount(invoice.paid_amount)}
                    </td>
                    <td className="px-2 py-2 tabular-nums text-slate-700 dark:text-slate-200">
                      {formatOfficeAmount(invoice.remaining)}
                    </td>
                    <td className="px-2 py-2">
                      <span
                        className={
                          invoice.state === 'paid'
                            ? 'rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10.5px] font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300'
                            : 'rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10.5px] font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300'
                        }
                      >
                        {invoice.state_label}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </OfficeCard>
    </div>
  );
};

/** رقمٌ واحدٌ بعنوانه — لا حسابَ في العرض، القيمةُ تصل مصيغةً. */
const Figure: React.FC<{
  label: string;
  value: string;
  className?: string;
  hint?: string;
}> = ({ label, value, className = '', hint }) => (
  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/40">
    <div className="text-[10.5px] font-semibold text-slate-500 dark:text-slate-400">
      {label}
    </div>
    <div className={`mt-1 tabular-nums ${className || 'text-[15px] font-bold text-slate-800 dark:text-slate-100'}`}>
      {value}
    </div>
    {hint ? (
      <div className="text-[10.5px] text-slate-500 dark:text-slate-400">{hint}</div>
    ) : null}
  </div>
);
