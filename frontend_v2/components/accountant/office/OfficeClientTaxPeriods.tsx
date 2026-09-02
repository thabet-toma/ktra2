import React, { useCallback, useEffect, useState } from 'react';
import { CalendarPlus, CheckCircle2, Send } from 'lucide-react';

import {
  approveClientTaxPeriod,
  getClientTaxPeriodReadiness,
  listClientTaxPeriods,
  prepareClientTaxPeriod,
  submitClientTaxPeriod,
  type TaxPeriodFinding,
  type TaxPeriodRecord,
} from '../../../services/accountantApi';
import { useToast } from '../../../contexts/ToastContext';
import { formatDateValue } from '../../../utils/formatDate';
import { formatNumber } from '../../../utils/formatNumber';
import {
  OfficeBadge,
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeField,
  OfficeInput,
  OfficeModal,
  OfficeSkeleton,
} from './OfficeUi';

const STATUS_LABELS: Record<TaxPeriodRecord['status'], string> = {
  in_review: 'قيد المراجعة',
  needs_company_action: 'بانتظار الشركة',
  ready: 'جاهزة',
  approved: 'معتمدة',
  submitted: 'مقدَّمة',
  locked: 'مقفلة',
};

const STATUS_TONES: Record<TaxPeriodRecord['status'], string> = {
  in_review: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
  needs_company_action: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  ready: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200',
  approved: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200',
  submitted: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  locked: 'bg-slate-700 text-white dark:bg-slate-100 dark:text-slate-900',
};

const SEVERITY_TONES: Record<TaxPeriodFinding['severity'], string> = {
  blocker: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  info: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
};

const SEVERITY_LABELS: Record<TaxPeriodFinding['severity'], string> = {
  blocker: 'مانع',
  warning: 'تحذير',
  info: 'معلومة',
};

const failure = (caught: unknown, fallback: string) => (caught as Error)?.message || fallback;

const monthStart = () => new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10);
const monthEnd = () => new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).toISOString().slice(0, 10);

const PrepareForm: React.FC<{ onClose: () => void; onPrepared: (period: TaxPeriodRecord) => void; tenantId: number }> = (
  { onClose, onPrepared, tenantId },
) => {
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(monthEnd());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const res = await prepareClientTaxPeriod(tenantId, { period_from: from, period_to: to });
      onPrepared(res.period);
    } catch (caught) {
      setError(failure(caught, 'تعذّر تجهيز الفترة — قد تتقاطع مع فترة سابقة.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <OfficeModal
      title="تجهيز فترة ضريبية جديدة"
      onClose={onClose}
      footer={(
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-slate-300 px-5 py-2.5 font-bold dark:border-slate-700">إلغاء</button>
          <button type="submit" form="office-tax-period-form" disabled={saving} className="rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50">
            {saving ? 'جارٍ التجهيز…' : 'جهّز الفترة'}
          </button>
        </>
      )}
    >
      <form id="office-tax-period-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700 sm:col-span-2">{error}</p>}
        <OfficeField label="من">
          {(id) => <OfficeInput id={id} type="date" value={from} onChange={(event) => setFrom(event.target.value)} />}
        </OfficeField>
        <OfficeField label="إلى">
          {(id) => <OfficeInput id={id} type="date" value={to} onChange={(event) => setTo(event.target.value)} />}
        </OfficeField>
      </form>
    </OfficeModal>
  );
};

const ReauthModal: React.FC<{
  title: string;
  confirmLabel: string;
  extra?: React.ReactNode;
  onClose: () => void;
  onConfirm: (password: string) => Promise<void>;
}> = ({ title, confirmLabel, extra, onClose, onConfirm }) => {
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      await onConfirm(password);
    } catch (caught) {
      setError(failure(caught, 'تعذّر تنفيذ الإجراء.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <OfficeModal
      title={title}
      onClose={onClose}
      footer={(
        <>
          <button type="button" onClick={onClose} className="rounded-xl border border-slate-300 px-5 py-2.5 font-bold dark:border-slate-700">إلغاء</button>
          <button type="submit" form="office-tax-reauth-form" disabled={saving || !password} className="rounded-xl bg-indigo-700 px-5 py-2.5 font-bold text-white disabled:opacity-50">
            {saving ? 'جارٍ التنفيذ…' : confirmLabel}
          </button>
        </>
      )}
    >
      <form id="office-tax-reauth-form" onSubmit={submit} className="space-y-4">
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}
        {extra}
        <OfficeField label="كلمة المرور" required hint="فعلٌ حسّاس على دفتر العميل — أعد إدخال كلمة مرورك للتأكيد.">
          {(id) => <OfficeInput id={id} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoFocus />}
        </OfficeField>
      </form>
    </OfficeModal>
  );
};

/**
 * الفترات الضريبية على دفتر العميل — تُنادى من بطاقته مباشرة بـ`tenantId`
 * دفتره (مُداراً أو مربوطاً)، لا من بوابةٍ منفصلة. المنطق (فحوص الجاهزية وقفل
 * الفترة) هو نفسه القائم في M5؛ هذه واجهةٌ جديدة فقط.
 */
export const OfficeClientTaxPeriods: React.FC<{ tenantId: number; companyName: string }> = ({ tenantId, companyName }) => {
  const toast = useToast();
  const [periods, setPeriods] = useState<TaxPeriodRecord[]>([]);
  const [selected, setSelected] = useState<TaxPeriodRecord | null>(null);
  const [findings, setFindings] = useState<TaxPeriodFinding[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [preparing, setPreparing] = useState(false);
  const [reauth, setReauth] = useState<'approve' | 'submit' | null>(null);
  const [reference, setReference] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listClientTaxPeriods(tenantId)
      .then((res) => {
        setPeriods(res.results);
        setSelected((current) => current ?? res.results[0] ?? null);
      })
      .catch(() => setError('تعذّر تحميل فترات هذا الدفتر.'))
      .finally(() => setLoading(false));
  }, [tenantId]);

  useEffect(load, [load]);

  const loadReadiness = useCallback((period: TaxPeriodRecord) => {
    setFindings(null);
    getClientTaxPeriodReadiness(tenantId, period.id)
      .then((res) => setFindings(res.findings))
      .catch(() => toast('تعذّر تحميل قائمة الجاهزية.', 'error'));
  }, [tenantId, toast]);

  useEffect(() => {
    if (selected) loadReadiness(selected);
  }, [selected, loadReadiness]);

  const select = (period: TaxPeriodRecord) => {
    setSelected(period);
    setReference(period.submission_reference || '');
  };

  const approve = async (password: string) => {
    if (!selected) return;
    const res = await approveClientTaxPeriod(tenantId, selected.id, password);
    setSelected(res.period);
    setPeriods((rows) => rows.map((row) => (row.id === res.period.id ? res.period : row)));
    setReauth(null);
    toast('اعتُمدت الفترة الضريبية.', 'success');
  };

  const submit = async (password: string) => {
    if (!selected) return;
    if (!reference.trim()) throw new Error('مرجع التقديم إلزامي.');
    const res = await submitClientTaxPeriod(tenantId, selected.id, {
      submission_reference: reference.trim(), reauth_password: password,
    });
    setSelected(res.period);
    setPeriods((rows) => rows.map((row) => (row.id === res.period.id ? res.period : row)));
    setReauth(null);
    toast('سُجِّل التقديم وقُفلت الفترة.', 'success');
  };

  const blockers = findings?.filter((item) => item.severity === 'blocker').length || 0;

  return (
    <div className="space-y-5">
      <OfficeCard
        title={`فترات ${companyName}`}
        actions={(
          <button type="button" onClick={() => setPreparing(true)} className="flex items-center gap-2 rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">
            <CalendarPlus className="h-4 w-4" />فترة جديدة
          </button>
        )}
      >
        {loading ? <OfficeSkeleton rows={3} /> : error ? <OfficeError message={error} onRetry={load} /> : periods.length === 0 ? (
          <OfficeEmpty title="لا فترات مُجهَّزة بعد" hint="ابدأ بـ«فترة جديدة» لتشغيل قائمة الجاهزية على دفتر هذا العميل." />
        ) : (
          <ul className="flex flex-wrap gap-2">
            {periods.map((period) => (
              <li key={period.id}>
                <button
                  type="button"
                  onClick={() => select(period)}
                  aria-current={selected?.id === period.id}
                  className={`flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-bold transition ${
                    selected?.id === period.id
                      ? 'border-indigo-600 bg-indigo-50 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200'
                      : 'border-slate-300 text-slate-700 dark:border-slate-700 dark:text-slate-200'
                  }`}
                >
                  {formatDateValue(period.period_from)} → {formatDateValue(period.period_to)}
                  <OfficeBadge tone={STATUS_TONES[period.status]}>{STATUS_LABELS[period.status]}</OfficeBadge>
                </button>
              </li>
            ))}
          </ul>
        )}
      </OfficeCard>

      {selected && (
        <OfficeCard
          title="قائمة الجاهزية"
          actions={(
            <div className="flex flex-wrap gap-2">
              {selected.status !== 'approved' && selected.status !== 'submitted' && selected.status !== 'locked' && (
                <button
                  type="button"
                  disabled={blockers > 0}
                  onClick={() => setReauth('approve')}
                  className="flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                >
                  <CheckCircle2 className="h-4 w-4" />اعتماد الفترة
                </button>
              )}
              {selected.status === 'approved' && (
                <button type="button" onClick={() => setReauth('submit')} className="flex items-center gap-2 rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white">
                  <Send className="h-4 w-4" />تسجيل التقديم وقفل الفترة
                </button>
              )}
            </div>
          )}
        >
          {findings === null ? <OfficeSkeleton rows={2} /> : findings.length === 0 ? (
            <OfficeEmpty title="لا موانع ولا تحذيرات" hint="الفترة جاهزة للاعتماد." />
          ) : (
            <ul className="space-y-2">
              {findings.map((finding) => (
                <li key={finding.code} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
                  <span className="text-sm font-bold text-slate-700 dark:text-slate-200">{finding.message}</span>
                  <span className="flex items-center gap-2">
                    {finding.count > 0 && <span className="text-xs text-slate-500 dark:text-slate-400">({formatNumber(finding.count)})</span>}
                    <OfficeBadge tone={SEVERITY_TONES[finding.severity]}>{SEVERITY_LABELS[finding.severity]}</OfficeBadge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </OfficeCard>
      )}

      {preparing && (
        <PrepareForm
          tenantId={tenantId}
          onClose={() => setPreparing(false)}
          onPrepared={(period) => {
            setPreparing(false);
            setPeriods((rows) => [period, ...rows]);
            select(period);
            toast('جُهِّزت الفترة الضريبية.', 'success');
          }}
        />
      )}

      {reauth === 'approve' && (
        <ReauthModal
          title="اعتماد الفترة الضريبية"
          confirmLabel="اعتماد"
          onClose={() => setReauth(null)}
          onConfirm={approve}
        />
      )}

      {reauth === 'submit' && (
        <ReauthModal
          title="تسجيل تقديم الإقرار"
          confirmLabel="تسجيل وقفل"
          onClose={() => setReauth(null)}
          onConfirm={submit}
          extra={(
            <OfficeField label="مرجع التقديم" required>
              {(id) => <OfficeInput id={id} value={reference} onChange={(event) => setReference(event.target.value)} autoFocus />}
            </OfficeField>
          )}
        />
      )}
    </div>
  );
};

export default OfficeClientTaxPeriods;
