import React, { useCallback, useEffect, useState } from 'react';

import {
  listFeePayments,
  printFeePayment,
  printFeeStatement,
  shareFeePayment,
  shareFeeStatement,
  type FeeDocumentShare,
  type FeePaymentRow,
  type FeeReceiptPayload,
  type FeeStatementMovement,
} from '../../services/accountingOfficeApi';
import { AMOUNT_MASK, formatOfficeAmount } from '../../utils/accountingOffice';
import { formatDateValue, formatDateTimeValue, todayIso } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { printReport } from '../../utils/printReport';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/**
 * أتعابُ الزبون (#283/ب): دفعاتُه بإشعارِ قبضٍ لكلِّ واحدة، وكشفُ حسابٍ لفترة.
 *
 * **الطباعةُ من المتصفّح بنمط `utils/printReport.ts`** — نفس نمط كل شاشات
 * الطباعة في المستودع: الطلبُ يجلب الحمولة بالترويسات المعتادة (توكنٌ وشركة)،
 * ثم تُصيَّر الورقة وتُفتح نافذةُ الطباعة. وطلبُ صفحة الخادم في تبويبٍ جديد كان
 * سيردّ 401 لأن التبويب الجديد لا يحمل ترويسة المصادقة.
 *
 * **والرقمُ رقمُ السند المخزَّن** (`receipt_number`) لا رقمٌ يُولَّد عند العرض.
 *
 * **والقناعُ من الخادم** (`null`): عضوٌ بلا `office.amounts.view` يرى «—» ولا
 * صفراً — والصفرُ يقول «لا مال» وهو كذب.
 */

/** نافذةُ مشاركةٍ صغيرة: الرابطُ الحيّ ونسخُه — بلا طبقةٍ منبثقةٍ ثقيلة. */
const ShareRow: React.FC<{ share: FeeDocumentShare }> = ({ share }) => (
  <div className="mt-1 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] dark:border-slate-700 dark:bg-slate-800">
    <span className="font-medium text-slate-600 dark:text-slate-300">رابط المشاركة:</span>
    <input
      readOnly
      value={share.url}
      dir="ltr"
      onFocus={(event) => event.currentTarget.select()}
      className="min-w-0 flex-1 rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
    />
    <span className="tabular-nums text-slate-500 dark:text-slate-400">
      ينتهي {formatDateTimeValue(share.expires_at)}
    </span>
  </div>
);

export const OfficeClientFees: React.FC<{
  clientId: number;
  canWrite: boolean;
}> = ({ clientId, canWrite }) => {
  const toast = useToast();
  const [rows, setRows] = useState<FeePaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [share, setShare] = useState<FeeDocumentShare | null>(null);
  const [statementBusy, setStatementBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listFeePayments(clientId)
      .then((result) => setRows(result))
      .catch(() => setError('تعذّر جلب دفعات الزبون.'))
      .finally(() => setLoading(false));
  }, [clientId]);

  useEffect(load, [load]);

  const printReceipt = async (row: FeePaymentRow) => {
    setBusyId(row.id);
    try {
      const receipt = await printFeePayment(row.id);
      const opened = printReport<FeeReceiptPayload['allocations'][number]>({
        title: receipt.title,
        subtitle: `${receipt.client.name} · ${formatDateValue(receipt.date)}`,
        meta: [
          { label: 'رقم الإشعار', value: receipt.number },
          { label: 'طريقة الدفع', value: receipt.method_label },
          ...(receipt.cheque
            ? [{
              label: 'الشيك',
              value: [receipt.cheque.number, receipt.cheque.bank_name]
                .filter(Boolean)
                .join(' — '),
            }]
            : []),
          { label: 'الباقي على الزبون', value: formatOfficeAmount(receipt.due) },
        ],
        columns: [
          { header: 'البيان', value: (line) => line.period_label },
          {
            header: 'المبلغ',
            value: (line: { amount: string | null }) => formatOfficeAmount(line.amount),
            numeric: true,
          },
        ],
        rows: receipt.allocations,
        totals: ['المبلغ المقبوض', formatOfficeAmount(receipt.amount)],
        footer: receipt.office.name,
        emptyHint: 'دفعةٌ غيرُ مخصَّصةٍ على فاتورة — رصيدٌ دائنٌ للزبون.',
      });
      if (!opened) toast('المتصفح منع نافذة الطباعة — اسمح بالنوافذ المنبثقة.', 'info');
    } catch (thrown) {
      toast(humanizeThrown(thrown, 'تعذّر تجهيز الإشعار.'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  const shareOne = async (row: FeePaymentRow) => {
    setBusyId(row.id);
    try {
      const created = await shareFeePayment(row.id);
      setShare(created);
      try {
        await navigator.clipboard.writeText(created.url);
        toast('نُسخ رابط الإشعار', 'success');
      } catch {
        // متصفّحٌ بلا صلاحية حافظة — الرابطُ معروضٌ للتحديد اليدويّ.
        toast('انسخ الرابط يدوياً من الحقل', 'info');
      }
    } catch (thrown) {
      toast(humanizeThrown(thrown, 'تعذّر إنشاء رابط الإشعار.'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  /**
   * «أرسِل الكشف الشهريّ» (#283/ج): كشفُ الشهر الجاري ورابطُه — **بنقطةٍ قائمة**
   * (`fees/ledger/share/`، التي تُصدر صفّ `FeeStatement` ورابط `docshare` في
   * معاملةٍ واحدة) لا بنقطةٍ جديدة. ويُنسخ الرابطُ كما في «مشاركة» الدفعة.
   */
  const sendMonthlyStatement = async () => {
    setStatementBusy(true);
    const today = todayIso();
    try {
      const created = await shareFeeStatement(clientId, {
        periodFrom: `${today.slice(0, 8)}01`,
        periodTo: today,
      });
      setShare(created);
      try {
        await navigator.clipboard.writeText(created.url);
        toast('نُسخ رابط الكشف الشهري', 'success');
      } catch {
        toast('انسخ الرابط يدوياً من الحقل', 'info');
      }
    } catch (thrown) {
      toast(humanizeThrown(thrown, 'تعذّر إنشاء رابط الكشف الشهري.'), 'error');
    } finally {
      setStatementBusy(false);
    }
  };

  if (loading) return <OfficeSkeleton rows={4} />;
  if (error) return <OfficeError message={error} onRetry={load} />;

  return (
    <OfficeCard
      title="دفعات الأتعاب"
      actions={canWrite ? (
        <button
          type="button"
          disabled={statementBusy}
          onClick={() => void sendMonthlyStatement()}
          data-testid="send-monthly-statement"
          className={officeSecondaryButtonClass}
        >
          أرسِل الكشف الشهريّ
        </button>
      ) : undefined}
    >
      {rows.length === 0 ? (
        <OfficeEmpty title="لا دفعاتٍ مسجَّلةً لهذا الزبون بعد." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[11.5px]">
            <thead>
              <tr className="border-b border-slate-200 text-right text-[11px] text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2 font-medium">رقم الإشعار</th>
                <th className="px-2 py-2 font-medium">التاريخ</th>
                <th className="px-2 py-2 font-medium">الطريقة</th>
                <th className="px-2 py-2 font-medium">المبلغ</th>
                <th className="px-2 py-2 font-medium">الباقي عليه</th>
                <th className="px-2 py-2 font-medium">الإشعار</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-slate-100 last:border-0 dark:border-slate-800"
                >
                  <td className="px-2 py-2 tabular-nums font-semibold text-slate-800 dark:text-slate-100">
                    {row.receipt_number}
                  </td>
                  <td className="px-2 py-2 tabular-nums text-slate-600 dark:text-slate-300">
                    {formatDateValue(row.paid_at)}
                  </td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                    {row.method_label}
                  </td>
                  <td className="px-2 py-2 tabular-nums text-slate-800 dark:text-slate-100">
                    {formatOfficeAmount(row.amount)}
                  </td>
                  <td className="px-2 py-2 tabular-nums text-slate-600 dark:text-slate-300">
                    {formatOfficeAmount(row.due)}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {canWrite ? (
                        <>
                          <button
                            type="button"
                            disabled={busyId === row.id}
                            onClick={() => void printReceipt(row)}
                            className={officeSecondaryButtonClass}
                          >
                            إشعار قبض
                          </button>
                          <button
                            type="button"
                            disabled={busyId === row.id}
                            onClick={() => void shareOne(row)}
                            className={officeSecondaryButtonClass}
                          >
                            مشاركة
                          </button>
                        </>
                      ) : (
                        <span className="text-[11px] text-slate-400">{AMOUNT_MASK}</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {share ? <ShareRow share={share} /> : null}
    </OfficeCard>
  );
};

/**
 * كبسةُ «كشف حساب» في رأس الملفّ — مع منتقي الفترة (من/إلى) وطباعةٍ ومشاركة.
 *
 * **الافتراضُ سنةُ اليوم حتى اليوم**: كشفٌ مفتوحٌ من البداية يتضخّم مع كل دفعة،
 * والسنةُ الكاملة هي ما يطلبه المكتب عادةً. والتاريخان يُرسَلان كما اختارهما
 * الموظف — والخادمُ يقصّ الصفوف ويحسب الرصيد الجاري منها.
 */
export const OfficeClientStatementButton: React.FC<{
  clientId: number;
  canWrite: boolean;
}> = ({ clientId, canWrite }) => {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(`${todayIso().slice(0, 4)}-01-01`);
  const [to, setTo] = useState(todayIso());
  const [busy, setBusy] = useState(false);
  const [share, setShare] = useState<FeeDocumentShare | null>(null);
  const [error, setError] = useState('');

  const printSheet = async () => {
    setBusy(true);
    setError('');
    try {
      const sheet = await printFeeStatement(clientId, { periodFrom: from, periodTo: to });
      const opened = printReport<FeeStatementMovement>({
        title: sheet.title,
        subtitle: `${sheet.client.name} · ${formatDateValue(sheet.from)} → ${formatDateValue(sheet.to)}`,
        meta: [
          { label: 'رصيد أول المدة', value: formatOfficeAmount(sheet.opening_balance) },
          { label: 'الرصيد الختامي', value: formatOfficeAmount(sheet.closing_balance) },
          { label: 'المطلوب اليوم', value: formatOfficeAmount(sheet.due) },
          { label: 'مجموع الفواتير', value: formatOfficeAmount(sheet.totals.invoices) },
          { label: 'مجموع الدفعات', value: formatOfficeAmount(sheet.totals.payments) },
          { label: 'مجموع الشطوب', value: formatOfficeAmount(sheet.totals.write_offs) },
        ],
        columns: [
          { header: 'التاريخ', value: (row) => formatDateValue(row.date) },
          { header: 'النوع', value: (row) => row.kind_label },
          { header: 'البيان', value: (row) => row.label },
          {
            header: 'المبلغ',
            value: (row: { amount: string | null }) => formatOfficeAmount(row.amount),
            numeric: true,
          },
          {
            header: 'الرصيد الجاري',
            value: (row: { balance: string | null }) => formatOfficeAmount(row.balance),
            numeric: true,
          },
        ],
        rows: sheet.rows,
        totals: [
          '',
          '',
          'الرصيد الختامي',
          formatOfficeAmount(sheet.totals.movements),
          formatOfficeAmount(sheet.closing_balance),
        ],
        footer: sheet.office.name,
        emptyHint: 'لا حركاتٍ على هذا الزبون في هذه الفترة.',
      });
      if (!opened) toast('المتصفح منع نافذة الطباعة — اسمح بالنوافذ المنبثقة.', 'info');
    } catch (thrown) {
      setError(humanizeThrown(thrown, 'تعذّر تجهيز كشف الحساب.'));
    } finally {
      setBusy(false);
    }
  };

  const shareSheet = async () => {
    setBusy(true);
    setError('');
    try {
      const created = await shareFeeStatement(clientId, {
        periodFrom: from,
        periodTo: to,
      });
      setShare(created);
      try {
        await navigator.clipboard.writeText(created.url);
        toast('نُسخ رابط كشف الحساب', 'success');
      } catch {
        toast('انسخ الرابط يدوياً من الحقل', 'info');
      }
    } catch (thrown) {
      setError(humanizeThrown(thrown, 'تعذّر إنشاء رابط كشف الحساب.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={officeSecondaryButtonClass}
      >
        كشف حساب
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="كشف حساب"
            className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900"
          >
            <h2 className="text-[14px] font-bold text-slate-900 dark:text-slate-100">
              كشف حساب — الفترة
            </h2>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                من
                <input
                  type="date"
                  value={from}
                  onChange={(event) => setFrom(event.target.value)}
                  className={`${officeInputClass} mt-1 block w-40 tabular-nums`}
                />
              </label>
              <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
                إلى
                <input
                  type="date"
                  value={to}
                  onChange={(event) => setTo(event.target.value)}
                  className={`${officeInputClass} mt-1 block w-40 tabular-nums`}
                />
              </label>
            </div>
            {error ? (
              <p className="mt-3 text-[11.5px] font-medium text-rose-600 dark:text-rose-400">
                {error}
              </p>
            ) : null}
            {share ? <ShareRow share={share} /> : null}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void printSheet()}
                className={officePrimaryButtonClass}
              >
                طباعة
              </button>
              {canWrite ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void shareSheet()}
                  className={officeSecondaryButtonClass}
                >
                  مشاركة
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className={`ms-auto ${officeSecondaryButtonClass}`}
              >
                إغلاق
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
};
