import React, { useMemo, useState } from 'react';
import { Activity, ArrowRightLeft, MapPin, MessageCircle, Phone, StickyNote } from 'lucide-react';

import type { CrmActivity, CrmActivityInput, CrmColleague, CrmLead, CrmLeadContactStats, CrmLeadStatus } from '../../../../services/platformCrmApi';
import { formatDateTimeValue } from '../../../../utils/formatDate';
import { formatNumber } from '../../../../utils/formatNumber';
import { arabicDayCount, contactRecencyLabel, leadAttentionBadge } from '../../../../utils/leadContactStats';
import { CcAvatar, CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton } from '../../ui';
import { CRM_LEAD_PIPELINE, STATUS_LABELS, STATUS_TONES } from './CrmLeadList';

const ACTIVITY_LABELS: Record<CrmActivity['kind'], string> = { call: 'مكالمة', whatsapp: 'واتساب', visit: 'زيارة', note: 'ملاحظة', status_change: 'تغيير حالة', assignment: 'إسناد', transfer: 'تحويل', materials_sent: 'إرسال مواد' };

interface CrmLeadProfileProps {
  lead: CrmLead; activities: CrmActivity[]; loading: boolean; error: string; isManager: boolean; isOwner: boolean; colleagues: CrmColleague[];
  /** ستاتستكس الرقم مجمَّعةً من الخادم — `null` حين يتعذّر جلبُها، ولا تُقفل الملفّ. */
  stats: CrmLeadContactStats | null;
  onBack: () => void; onStatus: (status: CrmLeadStatus, body: string) => void; onActivity: (input: CrmActivityInput) => void;
  onTransfer: (toEmployee: number, reason: string, direct: boolean) => void;
  /** السببُ يأتي من حقلٍ في الصفحة لا من حوار المتصفّح. */
  onRelease: (reason: string) => void;
}

export const CrmLeadProfile: React.FC<CrmLeadProfileProps> = ({ lead, activities, stats, loading, error, isManager, isOwner, colleagues, onBack, onStatus, onActivity, onTransfer, onRelease }) => {
  const [noteOpen, setNoteOpen] = useState(false); const [activityKind, setActivityKind] = useState<CrmActivityInput['kind']>('note');
  const [body, setBody] = useState(''); const [nextFollowUp, setNextFollowUp] = useState(''); const [status, setStatus] = useState<CrmLeadStatus>(lead.status);
  const [transferTo, setTransferTo] = useState(''); const [reason, setReason] = useState('');
  const [releaseOpen, setReleaseOpen] = useState(false); const [releaseReason, setReleaseReason] = useState('');
  const availableColleagues = useMemo(() => colleagues.filter((employee) => !employee.is_me), [colleagues]);
  const happyIndex = CRM_LEAD_PIPELINE.indexOf(lead.status);
  // **رقمان لا رقمٌ واحد.** كان متغيّرٌ واحدٌ اسمُه `primaryPhone` يُفضّل رقمَ
  // واتساب، ثمّ يُعرَض في السطر «📞» — فيظهر رقمُ الواتساب مكانَ الأساسيّ.
  // والنموذجُ البصريُّ يفصلهما: «📞 الرقم» ثمّ شارةُ واتساب.
  const displayPhone = lead.phones.find((phone) => phone.kind === 'primary') || lead.phones[0];
  const whatsappPhone = lead.phones.find((phone) => phone.kind === 'whatsapp') || displayPhone;
  // الشارةُ لا تُرسَم إلّا إن كان للعميل رقمُ واتساب مسجَّلٌ فعلاً: شارةٌ ثابتةٌ
  // تُخبر الموظّفَ أنّ للمحلّ واتساب وهو غيرُ معروف — ادّعاءٌ لا بيانات.
  const hasWhatsApp = lead.phones.some((phone) => phone.kind === 'whatsapp');
  // حالةُ المنتقي تتبع العميلَ: بلا هذا يبقى المنتقي على الحالة القديمة بعد
  // الحفظ فيخالف ما تعرضه الترويسةُ فوقه.
  React.useEffect(() => { setStatus(lead.status); }, [lead.status]);
  // **الحكمُ من الأرقام المجمَّعة لا من `activities` المحمَّلة**: تلك صفحةٌ من
  // خمسين صفّاً، فعدُّها يقول «كُلِّم ٥٠ مرّة» عن رقمٍ كُلِّم ثمانين.
  const attention = stats ? leadAttentionBadge(stats) : null;
  // **الكتابةُ لصاحب العميل أو المدير** (212-Q2-ب): `log_activity` و
  // `change_lead_status` في `crm/services.py` ترفعان `LeadLockedError` (٤٠٣)
  // لغيرهما. وكانت النماذجُ تُرسَم للجميع، فيكتب الزائرُ ملاحظةً ويضغط حفظاً
  // فيضيع ما كتبه على رسالة رفض. و**طلبُ** التحويل يبقى مفتوحاً للجميع:
  // ذاك غرضُه كلُّه (`transfer-requests/` في الخادم).
  const canWrite = isOwner || isManager;
  const openActivity = (kind: CrmActivityInput['kind']) => { setActivityKind(kind); setNoteOpen(true); };
  const submitActivity = (event: React.FormEvent) => { event.preventDefault(); onActivity({ kind: activityKind, body, next_follow_up_at: nextFollowUp ? `${nextFollowUp}T09:00:00` : null }); setBody(''); setNextFollowUp(''); setNoteOpen(false); };
  const submitTransfer = (event: React.FormEvent) => { event.preventDefault(); if (!transferTo || !reason.trim()) return; onTransfer(Number(transferTo), reason, isOwner || isManager); setReason(''); setTransferTo(''); };

  return (
    <section className="space-y-4" aria-label="ملف العميل">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-xs font-bold text-sky-400 hover:text-sky-300 transition-colors"
      >
        ← العودة إلى العملاء
      </button>

      <CcCard className="p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <CcAvatar name={lead.store_name} size="lg" />
            <div>
              <p className="text-xs font-semibold text-cc-text-muted">ملف العميل</p>
              <h1 className="mt-1 text-xl font-extrabold text-cc-text">🏪 {lead.store_name}</h1>
              <p className="mt-1 text-xs text-cc-text-muted">صاحب المحل: {lead.owner_name || 'غير مسجل'}</p>
              {lead.city || lead.address ? (
                <p className="mt-1 flex items-center gap-1.5 text-xs text-cc-text-muted">
                  <MapPin className="h-3.5 w-3.5 text-sky-400 shrink-0" />
                  {[lead.city, lead.address].filter(Boolean).join(' – ')}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:items-end">
            <div className="flex flex-wrap items-center gap-3">
              <span dir="ltr" className="inline-flex items-center gap-1.5 text-sm font-mono text-sky-400">
                <Phone className="h-4 w-4" />
                {displayPhone?.raw || 'لا يوجد رقم'}
              </span>
              {hasWhatsApp && <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-400">🟢 WhatsApp</span>}
            </div>
          </div>
        </div>

        <div className="mt-4 border-t border-cc-border pt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
          <p className="text-xs text-cc-text-muted">
            الموظف المسؤول: <strong className="text-cc-text">{lead.assigned_to?.name || 'في المخزن المتاح'}</strong>
          </p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-cc-text-muted">الحالة:</span>
            <CcPill tone={STATUS_TONES[lead.status]}>{STATUS_LABELS[lead.status]}</CcPill>
          </div>
        </div>
      </CcCard>

      {stats && attention && (
        <CcCard className="p-5" aria-label="ستاتستكس الرقم">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 font-extrabold text-cc-text">
              <Activity className="h-5 w-5 text-sky-400" />
              ستاتستكس الرقم
            </h2>
            <span className={`rounded-full border px-3 py-1 text-xs font-bold ${attention.className}`}>
              {attention.label}
            </span>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <div className="rounded-xl border border-cc-border bg-cc-surface-2/60 p-3">
              <dt className="text-xs text-cc-text-muted">آخر تواصل</dt>
              <dd className="mt-1 text-sm font-extrabold text-cc-text">
                {contactRecencyLabel(stats.days_since_last_contact)}
              </dd>
              {stats.last_contact_at && (
                <dd className="mt-1 text-xs text-cc-text-muted">{formatDateTimeValue(stats.last_contact_at)}</dd>
              )}
            </div>
            <div className="rounded-xl border border-cc-border bg-cc-surface-2/60 p-3">
              <dt className="text-xs text-cc-text-muted">مرّات التواصل</dt>
              <dd className="mt-1 text-sm font-extrabold text-cc-text">
                {formatNumber(stats.contact_attempts)}
              </dd>
              <dd className="mt-1 text-xs text-cc-text-muted">
                📞 {formatNumber(stats.by_kind.call || 0)} · 🟢 {formatNumber(stats.by_kind.whatsapp || 0)} · 🚶 {formatNumber(stats.by_kind.visit || 0)}
              </dd>
            </div>
            <div className="rounded-xl border border-cc-border bg-cc-surface-2/60 p-3">
              <dt className="text-xs text-cc-text-muted">في حالته الحالية</dt>
              <dd className="mt-1 text-sm font-extrabold text-cc-text">
                {arabicDayCount(stats.days_in_status)}
              </dd>
            </div>
            <div className="rounded-xl border border-cc-border bg-cc-surface-2/60 p-3">
              <dt className="text-xs text-cc-text-muted">عمر الرقم</dt>
              <dd className="mt-1 text-sm font-extrabold text-cc-text">
                {arabicDayCount(stats.age_days)}
              </dd>
            </div>
            <div className="rounded-xl border border-cc-border bg-cc-surface-2/60 p-3">
              <dt className="text-xs text-cc-text-muted">عدد من تولّاه</dt>
              <dd className="mt-1 text-sm font-extrabold text-cc-text">
                {formatNumber(stats.handlers)}
              </dd>
            </div>
          </dl>
          {stats.next_follow_up_at && (
            <p className="mt-3 text-xs text-cc-text-muted">
              المتابعة القادمة:{' '}
              <strong className={stats.follow_up_state === 'overdue' ? 'text-rose-400' : 'text-sky-400'}>
                {formatDateTimeValue(stats.next_follow_up_at)}
              </strong>
            </p>
          )}
        </CcCard>
      )}

      <CcCard className="p-5">
        <CcSectionTitle title="حالة العميل" />
        <div className="mt-4 grid grid-cols-5 gap-2" aria-label="مسار حالة العميل">
          {CRM_LEAD_PIPELINE.map((item, index) => (
            <div key={item} className="min-w-0 text-center">
              <span
                className={`mx-auto flex h-7 w-7 items-center justify-center rounded-full text-xs font-extrabold ${
                  happyIndex >= index
                    ? 'bg-cc-accent text-cc-bg shadow-sm'
                    : 'bg-cc-surface-2 text-cc-text-muted border border-cc-border'
                }`}
              >
                {formatNumber(index + 1)}
              </span>
              <span className="mt-2 block truncate text-xs text-cc-text-muted">{STATUS_LABELS[item]}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-cc-text-muted">
          {happyIndex === -1 ? (
            <CcPill tone="warning">الحالة الحالية: {STATUS_LABELS[lead.status]}</CcPill>
          ) : (
            `المرحلة ${formatNumber(happyIndex + 1)} من ${formatNumber(CRM_LEAD_PIPELINE.length)}`
          )}
        </p>
        {canWrite ? <div className="mt-4 flex flex-wrap gap-2">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as CrmLeadStatus)}
            className="rounded-xl border border-cc-border bg-cc-surface px-3 py-2 text-sm text-cc-text focus:border-cc-accent focus:outline-none"
            aria-label="تغيير حالة العميل"
          >
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => onStatus(status, '')}
            className="rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
          >
            حفظ الحالة
          </button>
        </div> : <p className="mt-4 text-sm text-[var(--staff-muted)]">{lead.assigned_to ? 'تغييرُ الحالة لصاحب العميل أو المدير.' : 'استلِم العميلَ أوّلاً لتغيّر حالته.'}</p>}
      </CcCard>

      <CcCard className="p-5">
        <CcSectionTitle title="سجل التواصل" />
        {loading ? (
          <div className="mt-4 space-y-3">
            <CcSkeleton count={3} />
          </div>
        ) : error ? (
          <p className="mt-4 text-sm text-rose-400" role="alert">{error}</p>
        ) : activities.length === 0 ? (
          <CcEmpty
            title="لا توجد أنشطة مسجلة بعد"
            hint="أضف ملاحظة أو سجّل اتصالاً بعد حدوثه."
            className="mt-4 p-8"
          />
        ) : (
          <ol className="mt-4 divide-y divide-cc-border">
            {activities.map((activity) => (
              <li key={activity.id} className="py-4 first:pt-0">
                <div className="flex flex-wrap justify-between gap-2 text-xs text-cc-text-muted">
                  <span>{formatDateTimeValue(activity.created_at)} · {activity.employee?.name || 'النظام'}</span>
                  <span className="font-mono">#{formatNumber(activity.id)}</span>
                </div>
                <p className="mt-2 text-sm font-bold text-cc-text">
                  {ACTIVITY_LABELS[activity.kind]}{activity.body ? `: ${activity.body}` : ''}
                </p>
                {activity.kind === 'status_change' && activity.status_before && activity.status_after && (
                  <p className="mt-1 text-sm text-amber-300">
                    {STATUS_LABELS[activity.status_before]} <span aria-hidden="true">→</span> {STATUS_LABELS[activity.status_after]}
                  </p>
                )}
                {activity.materials.length > 0 && (
                  <p className="mt-1 text-xs text-cc-text-muted">المواد المرسلة: {activity.materials.join(' + ')}</p>
                )}
                {activity.next_follow_up_at && (
                  <p className="mt-1 text-xs font-semibold text-sky-400">
                    المتابعة القادمة: {formatDateTimeValue(activity.next_follow_up_at)}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
        {canWrite ? <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => openActivity('note')}
            className="inline-flex items-center gap-2 rounded-xl border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs font-bold text-cc-text hover:border-cc-border-strong transition-colors"
          >
            <StickyNote className="h-4 w-4" />
            إضافة ملاحظة
          </button>
          {whatsappPhone && (
            <a
              href={`https://wa.me/${whatsappPhone.e164.replace(/\D/g, '')}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => openActivity('whatsapp')}
              className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-3 py-2 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition-colors"
            >
              <MessageCircle className="h-4 w-4" />
              إرسال WhatsApp
            </a>
          )}
          <button
            type="button"
            onClick={() => openActivity('call')}
            className="inline-flex items-center gap-2 rounded-xl border border-sky-500/50 bg-sky-500/10 px-3 py-2 text-xs font-bold text-sky-300 hover:bg-sky-500/20 transition-colors"
          >
            <Phone className="h-4 w-4" />
            تسجيل اتصال
          </button>
        </div> : <p className="mt-5 text-sm text-[var(--staff-muted)]">{lead.assigned_to ? 'تسجيلُ التواصل لصاحب العميل أو المدير — ويمكنك طلبُ تحويله إليك أدناه.' : 'استلِم العميلَ أوّلاً لتسجّل تواصلاً معه.'}</p>}
      </CcCard>

      {noteOpen && canWrite && (
        <form onSubmit={submitActivity} className="rounded-2xl border border-sky-500/30 bg-cc-surface p-5 shadow-lg shadow-black/30">
          <h2 className="font-extrabold text-cc-text">سجّل ما حدث</h2>
          <p className="mt-1 text-xs text-cc-text-muted">فتح واتساب لا يسجل نشاطاً؛ أضف ما حدث فقط إن رغبت.</p>
          <label className="mt-4 block text-xs font-bold text-cc-text" htmlFor="crm-activity-body">
            التفاصيل
          </label>
          <textarea
            id="crm-activity-body"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            className="mt-1.5 min-h-24 w-full rounded-xl border border-cc-border bg-cc-bg/50 p-3 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
          />
          <label className="mt-3 block text-xs font-bold text-cc-text" htmlFor="crm-follow-up">
            المتابعة القادمة
          </label>
          <input
            id="crm-follow-up"
            type="date"
            value={nextFollowUp}
            onChange={(event) => setNextFollowUp(event.target.value)}
            className="mt-1.5 rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text focus:border-cc-accent focus:outline-none"
          />
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              className="rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
            >
              حفظ السجل
            </button>
            <button
              type="button"
              onClick={() => setNoteOpen(false)}
              className="rounded-xl border border-cc-border bg-cc-surface-2 px-4 py-2 text-sm font-bold text-cc-text hover:border-cc-border-strong transition-colors"
            >
              إلغاء
            </button>
          </div>
        </form>
      )}

      <form onSubmit={submitTransfer} className="rounded-2xl border border-cc-border bg-cc-surface p-5 shadow-lg shadow-black/30">
        <h2 className="flex items-center gap-2 font-extrabold text-cc-text">
          <ArrowRightLeft className="h-5 w-5 text-sky-400" />
          {isOwner || isManager ? 'تحويل العميل' : 'طلب تحويل العميل'}
        </h2>
        <p className="mt-1 text-xs text-cc-text-muted">
          الموظف الحالي: {lead.assigned_to?.name || 'في المخزن المتاح'}
        </p>
        <label className="mt-4 block text-xs font-bold text-cc-text" htmlFor="crm-transfer-to">
          تحويل إلى
        </label>
        <select
          required
          id="crm-transfer-to"
          value={transferTo}
          onChange={(event) => setTransferTo(event.target.value)}
          className="mt-1.5 w-full rounded-xl border border-cc-border bg-cc-surface px-3 py-2 text-sm text-cc-text focus:border-cc-accent focus:outline-none"
        >
          <option value="">اختر الموظف</option>
          {availableColleagues.map((employee) => (
            <option key={employee.id} value={employee.id}>
              {employee.name} · {employee.job_title}
            </option>
          ))}
        </select>
        <label className="mt-3 block text-xs font-bold text-cc-text" htmlFor="crm-transfer-reason">
          سبب التحويل
        </label>
        <input
          required
          id="crm-transfer-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="mt-1.5 w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="submit"
            className="rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
          >
            {isOwner || isManager ? 'تأكيد التحويل' : 'إرسال طلب التحويل'}
          </button>
          {isManager && (
            <button
              type="button"
              onClick={() => setReleaseOpen((value) => !value)}
              className="rounded-xl border border-rose-500/50 bg-rose-500/10 px-4 py-2 text-sm font-bold text-rose-300 hover:bg-rose-500/20 transition-colors"
            >
              إعادة إلى المخزن
            </button>
          )}
        </div>
      </form>

      {releaseOpen && isManager && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!releaseReason.trim()) return;
            onRelease(releaseReason);
            setReleaseOpen(false);
            setReleaseReason('');
          }}
          className="rounded-2xl border border-rose-500/30 bg-cc-surface p-5 shadow-lg shadow-black/30"
        >
          <h2 className="font-extrabold text-cc-text">إعادة العميل إلى المخزن</h2>
          <p className="mt-1 text-xs text-cc-text-muted">
            يُرفَع الإسنادُ عن الموظّف الحالي ويُسجَّل السببُ في سجلّ التواصل.
          </p>
          <label className="mt-4 block text-xs font-bold text-cc-text" htmlFor="crm-release-reason">
            سبب الإعادة
          </label>
          <input
            id="crm-release-reason"
            required
            value={releaseReason}
            onChange={(event) => setReleaseReason(event.target.value)}
            className="mt-1.5 w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
          />
          <div className="mt-4 flex gap-2">
            <button
              type="submit"
              className="rounded-xl bg-rose-500 px-4 py-2 text-sm font-extrabold text-slate-950 hover:bg-rose-400 transition-colors"
            >
              تأكيد الإعادة
            </button>
            <button
              type="button"
              onClick={() => setReleaseOpen(false)}
              className="rounded-xl border border-cc-border bg-cc-surface-2 px-4 py-2 text-sm font-bold text-cc-text hover:border-cc-border-strong transition-colors"
            >
              إلغاء
            </button>
          </div>
        </form>
      )}
    </section>
  );
};
