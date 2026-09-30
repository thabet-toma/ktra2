import React, { useEffect, useRef, useState } from 'react';
import { Check, ChevronLeft, RotateCcw, X } from 'lucide-react';

import { approveCrmLead, getCrmOverview, importCrmLeads, rejectCrmLead, releaseCrmLead, listCrmLeads, type CrmImportBatch, type CrmLead, type CrmOverview, type CrmOverviewEmployee, type CrmOverviewPeriod } from '../../../../services/platformCrmApi';
import { formatDateTimeValue } from '../../../../utils/formatDate';
import { formatNumber } from '../../../../utils/formatNumber';
import { CcAvatar, CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton, CcTable, CcTd, CcTh, CcThead, CcTr } from '../../ui';
import { STATUS_LABELS } from './CrmLeadList';

interface CrmManagerPanelProps { isManager: boolean; onLeadChanged: () => void; }
/** «غير مُسنَد» = المخزن؛ وإلا معرّفُ الموظّف — نفسُ `assigned_to` في `GET leads/`. */
export interface CrmEmployeePick { id: number | 'none'; name: string; }
interface CrmTeamPanelProps { isManager: boolean; refreshKey: number; onPickEmployee: (pick: CrmEmployeePick) => void; }

const PERIODS: ReadonlyArray<{ value: CrmOverviewPeriod; label: string }> = [
  { value: 'today', label: 'اليوم' }, { value: 'week', label: 'هذا الأسبوع' }, { value: 'month', label: 'هذا الشهر' }, { value: 'all', label: 'كل الوقت' },
];
const periodClass = (active: boolean) =>
  `rounded-lg px-3 py-1.5 text-xs font-bold transition-colors duration-150 ${active ? 'bg-cc-accent text-cc-bg' : 'text-cc-text-muted hover:text-cc-text hover:bg-cc-surface-2'}`;

/**
 * فريقُ التسويق عند المدير (#69): «كل موظف شو الأرقام اللي ماسكها وشو النتيجة».
 *
 * صفٌّ لكلّ موظّف: أرقامُه **الآن** وحالاتُها ومتأخّراتُها، ونتائجُه **في المدّة
 * المختارة** — كم تواصل، وكم منها انردّ عليه، وكم رقماً صار عميلاً. الكبسةُ على
 * الصفّ تفتح أرقامَه في القائمة تحته بدل فتحها رقماً رقماً. الأرقامُ كلّها من
 * `crm.services.manager_lead_overview` ولا يُحسب منها شيءٌ هنا إلا نسبةُ الردّ.
 */
export const CrmTeamPanel: React.FC<CrmTeamPanelProps> = ({ isManager, refreshKey, onPickEmployee }) => {
  const [overview, setOverview] = useState<CrmOverview | null>(null);
  const [period, setPeriod] = useState<CrmOverviewPeriod>('month');
  const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const requestRef = useRef(0);
  useEffect(() => {
    if (!isManager) return;
    const requestId = ++requestRef.current;
    setLoading(true); setError('');
    getCrmOverview(period)
      .then((next) => { if (requestId === requestRef.current) setOverview(next); })
      .catch((caught: unknown) => { if (requestId === requestRef.current) setError(caught instanceof Error ? caught.message : 'تعذر تحميل لوح الفريق.'); })
      .finally(() => { if (requestId === requestRef.current) setLoading(false); });
  }, [isManager, period, refreshKey]);
  if (!isManager) return null;
  const periodLabel = PERIODS.find((item) => item.value === period)?.label ?? '';
  const pick = (employee: CrmOverviewEmployee) => onPickEmployee({ id: employee.employee_id, name: employee.employee_name });
  return (
    <CcCard className="p-5" aria-label="فريق التسويق">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CcSectionTitle
          title="فريق التسويق"
          subtitle="اكبس على موظف لترى أرقامه في القائمة. النتائج محسوبة للمدة المختارة."
          badge={overview?.employees.length}
        />
        <div className="flex flex-wrap gap-1 rounded-xl border border-cc-border p-1" role="group" aria-label="مدة النتائج">
          {PERIODS.map((item) => (
            <button key={item.value} type="button" className={periodClass(period === item.value)} aria-pressed={period === item.value} onClick={() => setPeriod(item.value)}>
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {loading && !overview ? (
        <div className="mt-4"><CcSkeleton count={3} /></div>
      ) : error ? (
        <p className="mt-4 text-sm text-rose-400" role="alert">{error}</p>
      ) : (
        <>
          <button
            type="button"
            onClick={() => onPickEmployee({ id: 'none', name: 'المخزن المتاح' })}
            className="mt-4 inline-flex items-center gap-2 rounded-xl border border-cc-border bg-cc-surface-2 px-3 py-2 text-sm text-cc-text hover:border-cc-border-strong transition-colors"
          >
            في المخزن بلا موظف: <strong className="text-sky-400">{formatNumber(overview?.pool_size ?? 0)}</strong>
            <ChevronLeft className="h-4 w-4 text-cc-text-muted" />
          </button>
          {overview && overview.employees.length === 0 ? (
            <CcEmpty title="لا يوجد موظفون نشطون" className="mt-4 p-8" />
          ) : (
            <div className="mt-4">
              <CcTable>
                <CcThead>
                  <tr>
                    <CcTh>الموظف</CcTh>
                    <CcTh>الأرقام الآن</CcTh>
                    <CcTh>المتأخرات</CcTh>
                    <CcTh>تواصل ({periodLabel})</CcTh>
                    <CcTh>انردّ عليه</CcTh>
                    <CcTh>صاروا عملاء</CcTh>
                    <CcTh>آخر تواصل</CcTh>
                    <CcTh>حسب الحالة</CcTh>
                  </tr>
                </CcThead>
                <tbody>
                  {overview?.employees.map((employee) => (
                    <CcTr key={employee.employee_id} onClick={() => pick(employee)} className="cursor-pointer" data-testid={`crm-team-row-${employee.employee_id}`}>
                      <CcTd>
                        <button type="button" className="flex items-center gap-2 text-right" onClick={(event) => { event.stopPropagation(); pick(employee); }}>
                          <CcAvatar name={employee.employee_name} size="sm" />
                          <span className="font-bold text-cc-text hover:text-sky-400">{employee.employee_name}</span>
                          {employee.employee_status !== 'active' && <CcPill tone="neutral">غير نشط</CcPill>}
                        </button>
                      </CcTd>
                      <CcTd>
                        <span className="font-bold text-sky-400">{formatNumber(employee.total)}</span>
                      </CcTd>
                      <CcTd>
                        {employee.overdue > 0 ? (
                          <CcPill tone="danger">{formatNumber(employee.overdue)} متأخرة</CcPill>
                        ) : (
                          <span className="text-xs text-cc-text-muted">{formatNumber(0)}</span>
                        )}
                      </CcTd>
                      <CcTd>{formatNumber(employee.attempts)}</CcTd>
                      <CcTd>
                        {formatNumber(employee.reached)}
                        {employee.attempts > 0 && <span className="ms-1 text-xs text-cc-text-muted">({formatNumber((employee.reached / employee.attempts) * 100, { maxDecimals: 0 })}%)</span>}
                      </CcTd>
                      <CcTd>
                        <span className={employee.converted > 0 ? 'font-bold text-emerald-400' : 'text-cc-text-muted'}>{formatNumber(employee.converted)}</span>
                      </CcTd>
                      <CcTd>
                        <span className="text-xs text-cc-text-muted">{employee.last_activity_at ? formatDateTimeValue(employee.last_activity_at) : '—'}</span>
                      </CcTd>
                      <CcTd>
                        <div className="flex flex-wrap gap-1.5">
                          {Object.entries(employee.by_status).map(([status, count]) => (
                            <span
                              key={status}
                              className="inline-flex items-center gap-1 rounded-md bg-cc-surface-2 px-2 py-0.5 text-xs text-cc-text-muted border border-cc-border"
                            >
                              <span>{STATUS_LABELS[status as keyof typeof STATUS_LABELS] || status}:</span>
                              <strong className="text-cc-text">{formatNumber(count)}</strong>
                            </span>
                          ))}
                        </div>
                      </CcTd>
                    </CcTr>
                  ))}
                </tbody>
              </CcTable>
            </div>
          )}
        </>
      )}
    </CcCard>
  );
};

const parseRows = (text: string) => text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
  const [store_name = '', phone = '', owner_name = '', city = '', address = '', activity = ''] = line.split(',').map((item) => item.trim());
  return { store_name, phone, owner_name, city, address, activity };
});

export const CrmManagerPanel: React.FC<CrmManagerPanelProps> = ({ isManager, onLeadChanged }) => {
  const [pending, setPending] = useState<CrmLead[]>([]);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [rows, setRows] = useState(''); const [fileName, setFileName] = useState(''); const [notice, setNotice] = useState('');
  // نتيجةُ الدفعة تُحفَظ كاملةً لا تُلخَّص برقمٍ واحد: الخادمُ يعيد المُنشأَ
  // والمكرَّرَ وغيرَ الصالح وتفاصيلَ كلّ تكرار، وعرضُ «تمت معالجة ن صفاً» وحدَه
  // يُخفي عن المدير أنّ نصفَ ملفّه لم يدخل.
  const [batch, setBatch] = useState<CrmImportBatch | null>(null);
  // سببُ الرفض والإعادة في الصفحة لا في `window.prompt` — نمطُ المستودع
  // `ToastProvider`/`ConfirmProvider`، وحوارُ المتصفّح بلا اتّجاهٍ ولا تنسيق.
  const [reasonFor, setReasonFor] = useState<{ id: number; action: 'reject' | 'release' } | null>(null);
  const [reasonText, setReasonText] = useState('');
  const load = async () => {
    if (!isManager) return;
    setLoading(true); setError('');
    try { const nextPending = await listCrmLeads({ scope: 'all', approval_status: 'pending' }); setPending(nextPending.results); }
    catch (caught: unknown) { setError(caught instanceof Error ? caught.message : 'تعذر تحميل لوحة المدير.'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [isManager]);
  const upload = async (event: React.FormEvent) => { event.preventDefault(); if (!isManager) return; const parsed = parseRows(rows); if (!parsed.length) return; try { const result = await importCrmLeads(parsed, fileName); setBatch(result); setNotice(''); setRows(''); await load(); onLeadChanged(); } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : 'تعذر رفع الأرقام.'); } };
  const approve = async (id: number) => { if (!isManager) return; try { await approveCrmLead(id); setNotice('تم اعتماد الاقتراح.'); await load(); onLeadChanged(); } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : 'تعذر اعتماد الاقتراح.'); } };
  const submitReason = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!isManager || !reasonFor || !reasonText.trim()) return;
    const { id, action } = reasonFor;
    try {
      if (action === 'reject') { await rejectCrmLead(id, reasonText); setNotice('تم رفض الاقتراح.'); }
      else { await releaseCrmLead(id, reasonText); setNotice('أعيد العميل إلى المخزن المتاح.'); }
      setReasonFor(null); setReasonText('');
      await load(); onLeadChanged();
    } catch (caught: unknown) { setError(caught instanceof Error ? caught.message : 'تعذر تنفيذ الإجراء.'); }
  };
  const askReason = (id: number, action: 'reject' | 'release') => { setReasonFor((current) => current?.id === id && current.action === action ? null : { id, action }); setReasonText(''); };
  if (!isManager) return null;
  return (
    <section className="space-y-4" aria-label="لوحة مدير CRM">
      <CcCard className="p-5">
        <CcSectionTitle
          title="لوحة المدير"
          subtitle="رفع الأرقام واعتماد اقتراحات الموظفين."
        />
      </CcCard>
      {loading ? (
        <CcCard className="p-5">
          <CcSkeleton count={3} />
        </CcCard>
      ) : error ? (
        <CcCard tone="danger" className="p-5 text-sm text-rose-400" role="alert">
          {error}
        </CcCard>
      ) : (
        <>
          <CcCard className="p-5">
            <CcSectionTitle
              title="رفع الأرقام"
              subtitle="ضع صفاً لكل عميل: اسم المحل، الهاتف، المالك، المدينة، العنوان، النشاط."
            />
            <form onSubmit={upload} className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-bold text-cc-text" htmlFor="crm-import-name">
                  اسم الملف
                </label>
                <input
                  id="crm-import-name"
                  value={fileName}
                  onChange={(event) => setFileName(event.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
                  placeholder="leads.csv"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-cc-text" htmlFor="crm-import-rows">
                  الصفوف
                </label>
                <textarea
                  id="crm-import-rows"
                  value={rows}
                  onChange={(event) => setRows(event.target.value)}
                  className="mt-1.5 min-h-28 w-full rounded-xl border border-cc-border bg-cc-bg/50 p-3 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
                  placeholder="محل النور,0500000000,محمد,رهط,الشارع الرئيسي,أدوات كهربائية"
                />
              </div>
              <button
                type="submit"
                className="rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
              >
                رفع الدفعة
              </button>
            </form>
            {batch && (
              <div className="mt-4 rounded-xl border border-cc-border bg-cc-surface-2/60 p-4">
                <p className="font-bold text-cc-text">
                  نتيجةُ الدفعة{batch.file_name ? `: ${batch.file_name}` : ''}
                </p>
                <div className="mt-2 flex flex-wrap gap-4 text-sm">
                  <span className="text-cc-text-muted">الصفوف: <strong className="text-cc-text">{formatNumber(batch.total_rows)}</strong></span>
                  <span className="text-emerald-400">أُنشئ: <strong>{formatNumber(batch.created_count)}</strong></span>
                  <span className="text-amber-400">مكرَّر: <strong>{formatNumber(batch.duplicate_count)}</strong></span>
                  <span className="text-rose-400">غير صالح: <strong>{formatNumber(batch.invalid_count)}</strong></span>
                </div>
                {batch.duplicates.length > 0 && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-bold text-amber-400 hover:underline">
                      الأرقامُ المكرَّرة ({formatNumber(batch.duplicates.length)}) — ولدى مَن هي
                    </summary>
                    <ul className="mt-2 space-y-1 text-xs text-cc-text-muted">
                      {(batch.duplicates as Array<{ row?: number; phone?: string; existing_lead_name?: string; assigned_to_name?: string | null }>).map((duplicate, index) => (
                        <li key={`${duplicate.phone ?? index}`} dir="auto">
                          صف {formatNumber(duplicate.row ?? index + 1)} · <span dir="ltr" className="font-mono">{duplicate.phone}</span> — مسجَّلٌ لدى {duplicate.existing_lead_name || 'عميل آخر'}{duplicate.assigned_to_name ? ` (المسؤول ${duplicate.assigned_to_name})` : ' (في المخزن المتاح)'}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
          </CcCard>

          <CcCard className="p-5">
            <CcSectionTitle
              title="اقتراحات بانتظار الاعتماد"
              badge={pending.length}
            />
            {pending.length === 0 ? (
              <CcEmpty title="لا توجد اقتراحات معلقة" className="mt-4 p-8" />
            ) : (
              <ul className="mt-4 divide-y divide-cc-border">
                {pending.map((lead) => (
                  <li key={lead.id} className="py-3 first:pt-0">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-bold text-cc-text">{lead.store_name}</p>
                        <p className="text-xs text-cc-text-muted">{lead.suggested_by?.name || 'موظف'}</p>
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => approve(lead.id)}
                          className="inline-flex items-center gap-1 rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition-colors"
                        >
                          <Check className="h-4 w-4" />
                          اعتماد
                        </button>
                        <button
                          type="button"
                          onClick={() => askReason(lead.id, 'reject')}
                          className="inline-flex items-center gap-1 rounded-xl border border-rose-500/50 bg-rose-500/10 px-3 py-1.5 text-xs font-bold text-rose-300 hover:bg-rose-500/20 transition-colors"
                        >
                          <X className="h-4 w-4" />
                          رفض
                        </button>
                        <button
                          type="button"
                          onClick={() => askReason(lead.id, 'release')}
                          className="inline-flex items-center gap-1 rounded-xl border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs font-bold text-cc-text hover:border-cc-border-strong transition-colors"
                        >
                          <RotateCcw className="h-4 w-4" />
                          للمخزن
                        </button>
                      </div>
                    </div>
                    {reasonFor?.id === lead.id && (
                      <form onSubmit={submitReason} className="mt-3 flex w-full flex-col gap-2 sm:flex-row">
                        <label className="sr-only" htmlFor={`crm-reason-${lead.id}`}>
                          {reasonFor.action === 'reject' ? 'سبب الرفض' : 'سبب الإعادة إلى المخزن'}
                        </label>
                        <input
                          id={`crm-reason-${lead.id}`}
                          required
                          value={reasonText}
                          onChange={(event) => setReasonText(event.target.value)}
                          placeholder={reasonFor.action === 'reject' ? 'سبب الرفض' : 'سبب الإعادة إلى المخزن'}
                          className="min-w-0 flex-1 rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
                        />
                        <button
                          type="submit"
                          className="rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
                        >
                          تأكيد
                        </button>
                      </form>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CcCard>
          {notice && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300" role="status">
              {notice}
            </div>
          )}
        </>
      )}
    </section>
  );
};
