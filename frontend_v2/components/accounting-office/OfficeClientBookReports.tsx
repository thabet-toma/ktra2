import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  downloadClientBookReportXlsx,
  downloadClientBookXlsx,
  getClientBookReportPrint,
  getClientBookReports,
  shareClientBookReport,
  type BookReportPeriod,
  type ClientBookReportKind,
  type ClientBookReportShare,
  type ClientBookReportsPayload,
} from '../../services/accountingOfficeApi';
import { humanizeThrown } from '../../utils/drfError';
import { formatDateValue, todayIso } from '../../utils/formatDate';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeCard, OfficeEmpty, OfficeError, OfficeSkeleton,
  officeInputClass, officePrimaryButtonClass, officeSecondaryButtonClass,
} from './OfficeUi';

/** الفترةُ الافتراضيةُ كما يفترضها الخادم: من بداية السنة إلى اليوم. */
const defaultPeriod = (): BookReportPeriod => {
  const today = todayIso();
  return { from: `${today.slice(0, 4)}-01-01`, to: today };
};

/** تنزيلُ بايتاتٍ باسمٍ صريح — الواجهةُ لا تعرف نوعَ الملفّ إلا من امتداده. */
const saveBlob = (blob: Blob, fileName: string): void => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
};

/**
 * مستخرجاتُ دفتر الزبون (#288/ب-١) — شاشةٌ داخل تبويب «الدفتر» (#288/أ).
 *
 * **الأنواعُ من الخادم لا من قائمةٍ هنا**: `client-books/<id>/reports/` تعرف نوعَ
 * الدفتر (بسيطٌ أم مزدوج) وما يتبعه من تقارير، فقائمةٌ في الواجهة كانت ستعرض
 * نوعاً يردّه الخادم 400.
 *
 * **و«PDF» من المتصفح لا من مكتبة**: «طباعة» تفتح ورقةَ الخادم في نافذةٍ تطبع
 * نفسها، ومن حوار الطباعة يحفظها المستخدم PDF — كما في بقية تقارير المنصّة
 * (`utils/printReport.ts`). والملفُّ المباشر Excel يُنزَّل بايتات.
 *
 * **والرابطُ فعلُ كتابة**: زرُّه يظهر لمن يملك مفتاح الكتابة وحده (`canShare`)،
 * والخادم يردّ 403 لغيره أو 400 حين يُطفئ المكتب إعدادَ «رابط PDF للتقارير» —
 * والرسالتان تصلان كما كتبهما الخادم.
 */
export const OfficeClientBookReports: React.FC<{
  clientId: number;
  canShare: boolean;
}> = ({ clientId, canShare }) => {
  const toast = useToast();
  const [payload, setPayload] = useState<ClientBookReportsPayload | null>(null);
  const [kind, setKind] = useState('');
  const [period, setPeriod] = useState<BookReportPeriod>(defaultPeriod);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [link, setLink] = useState<ClientBookReportShare | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getClientBookReports(clientId)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        setKind((current) => (
          data.reports.some((row) => row.kind === current)
            ? current
            : data.reports[0]?.kind ?? ''
        ));
      })
      .catch((failure) => {
        if (!cancelled) setError(humanizeThrown(failure, 'تعذّر تحميل التقارير.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [clientId, reloadToken]);

  const reports = useMemo<ClientBookReportKind[]>(
    () => payload?.reports ?? [], [payload],
  );

  /** تقريرٌ لا يقوم بغير حسابٍ أو طرف (`statement`) — لا زرَّ إخراجٍ قبل اختياره. */
  const needsParams = useMemo(
    () => reports.find((row) => row.kind === kind)?.params.length ? true : false,
    [reports, kind],
  );

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  const withBusy = async (action: string, work: () => Promise<void>, failure: string) => {
    setBusy(action);
    try {
      await work();
    } catch (thrown) {
      toast(humanizeThrown(thrown, failure), 'error');
    } finally {
      setBusy('');
    }
  };

  const exportOne = () => withBusy('excel', async () => {
    const blob = await downloadClientBookReportXlsx(clientId, kind, period);
    saveBlob(blob, `client-book-${clientId}-${kind}.xlsx`);
  }, 'تعذّر تصدير الملف.');

  const exportBook = () => withBusy('book', async () => {
    const blob = await downloadClientBookXlsx(clientId, period);
    saveBlob(blob, `client-book-${clientId}.xlsx`);
  }, 'تعذّر تصدير الدفتر.');

  const printOne = () => withBusy('print', async () => {
    // النافذةُ تُفتح **قبل** النداء: فتحُها بعد `await` يجعله المتصفح نافذةً
    // منبثقةً محجوبةً (فقدانُ سياق المستخدم)، فيبقى الطلبُ بلا ورق.
    const opened = window.open('', '_blank');
    if (!opened) {
      toast('المتصفح منع نافذة الطباعة — اسمح بالنوافذ المنبثقة لهذا الموقع.', 'error');
      return;
    }
    try {
      const html = await getClientBookReportPrint(clientId, kind, period);
      opened.document.open();
      opened.document.write(html);
      opened.document.close();
    } catch (thrown) {
      opened.close();
      throw thrown;
    }
  }, 'تعذّر فتح ورقة الطباعة.');

  const share = () => withBusy('share', async () => {
    setLink(await shareClientBookReport(clientId, kind, period));
    toast('جاهز الرابط — انسخه وأرسله للزبون.', 'success');
  }, 'تعذّر إنشاء رابط المشاركة.');

  const copyLink = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link.url);
      toast('نُسخ الرابط.', 'success');
    } catch {
      // المتصفح يمنع الحافظة بلا HTTPS أو بلا إذن: الرابطُ معروضٌ للنسخ اليدويّ.
      toast('تعذّر النسخ التلقائي — انسخ الرابط من الحقل.', 'error');
    }
  };

  if (loading && !payload) return <OfficeSkeleton rows={3} />;
  if (error) return <OfficeError message={error} onRetry={reload} />;
  if (!reports.length) {
    return <OfficeEmpty title="لا تقاريرَ متاحة لهذا الدفتر." hint="نوعُ الدفتر هو ما يحدّد تقاريره." />;
  }

  const disabled = busy !== '' || !kind || needsParams;

  return (
    <OfficeCard
      title="التقارير"
      actions={(
        <button
          type="button"
          onClick={() => void exportBook()}
          disabled={busy !== ''}
          className={officeSecondaryButtonClass}
        >
          {busy === 'book' ? 'يُجهَّز…' : 'تنزيل الدفتر كاملاً (Excel)'}
        </button>
      )}
    >
      <p className="mb-3 text-[11px] font-medium text-slate-500 dark:text-slate-400">
        كلُّ مستخرجٍ يحمل علامة «{payload?.watermark ?? 'نسخة عمل'}» — للعرض والمتابعة لا للإقرار.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
          التقرير
          <select
            value={kind}
            onChange={(event) => { setKind(event.target.value); setLink(null); }}
            className={`${officeInputClass} mt-1 block w-full min-w-[180px]`}
          >
            {reports.map((row) => (
              <option key={row.kind} value={row.kind}>{row.title}</option>
            ))}
          </select>
        </label>
        <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
          من
          <input
            type="date"
            value={period.from}
            onChange={(event) => { setPeriod({ ...period, from: event.target.value }); setLink(null); }}
            className={`${officeInputClass} mt-1 block w-full tabular-nums`}
          />
        </label>
        <label className="text-[11.5px] font-medium text-slate-600 dark:text-slate-300">
          إلى
          <input
            type="date"
            value={period.to}
            onChange={(event) => { setPeriod({ ...period, to: event.target.value }); setLink(null); }}
            className={`${officeInputClass} mt-1 block w-full tabular-nums`}
          />
        </label>
      </div>

      {needsParams ? (
        <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-2 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-300">
          كشفُ الحساب يحتاج تحديدَ حسابٍ أو طرف — يُصدَّر من شاشة التقارير في المكتب.
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void exportOne()}
          disabled={disabled}
          className={officePrimaryButtonClass}
        >
          {busy === 'excel' ? 'يُجهَّز…' : 'تصدير Excel'}
        </button>
        <button
          type="button"
          onClick={() => void printOne()}
          disabled={disabled}
          className={officeSecondaryButtonClass}
        >
          {busy === 'print' ? 'يُفتح…' : 'طباعة'}
        </button>
        {canShare ? (
          <button
            type="button"
            onClick={() => void share()}
            disabled={disabled}
            className={officeSecondaryButtonClass}
          >
            {busy === 'share' ? 'يُنشَأ…' : 'مشاركة رابط'}
          </button>
        ) : null}
      </div>

      {link ? (
        <div className="mt-3 rounded-lg border border-teal-200 bg-teal-50 p-3 dark:border-teal-900 dark:bg-teal-950/40">
          <div className="flex flex-wrap items-center gap-2">
            <input
              readOnly
              value={link.url}
              aria-label="رابط التقرير"
              onFocus={(event) => event.target.select()}
              className={`${officeInputClass} min-w-0 flex-1 font-mono text-[11px]`}
            />
            <button type="button" onClick={() => void copyLink()} className={officeSecondaryButtonClass}>
              انسخ
            </button>
            <a
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className={officeSecondaryButtonClass}
            >
              افتح
            </a>
          </div>
          <p className="mt-1 text-[10.5px] font-medium text-teal-800 dark:text-teal-300">
            ينتهي الرابط في {formatDateValue(link.expires_at)} — ومن يفتحه يرى التقرير
            بعلامة «نسخة عمل».
          </p>
        </div>
      ) : null}
    </OfficeCard>
  );
};
