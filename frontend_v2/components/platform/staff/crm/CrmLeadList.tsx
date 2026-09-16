import React, { useState } from 'react';
import { LockKeyhole, PhoneCall, Search, UserPlus } from 'lucide-react';

import type { CrmLead, CrmLeadStatus, CrmLookup } from '../../../../services/platformCrmApi';
import type { CcTone } from '../../../../utils/ccTone';
import { formatDateValue } from '../../../../utils/formatDate';
import { formatNumber } from '../../../../utils/formatNumber';
import { CcAvatar, CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton } from '../../ui';

export const STATUS_LABELS: Record<CrmLeadStatus, string> = {
  new: 'جديد', contacted: 'تم الاتصال', interested: 'مهتم', follow_up: 'متابعة', customer: 'عميل',
  not_interested: 'غير مهتم', no_answer: 'لا يجيب', wrong_number: 'رقم خاطئ', postponed: 'مؤجل', closed: 'مغلق',
};
export const CRM_LEAD_PIPELINE: readonly CrmLeadStatus[] = ['new', 'contacted', 'interested', 'follow_up', 'customer'];

export const STATUS_TONES: Record<CrmLeadStatus, CcTone> = {
  new: 'accent',
  contacted: 'neutral',
  interested: 'success',
  follow_up: 'warning',
  customer: 'success',
  not_interested: 'danger',
  no_answer: 'warning',
  wrong_number: 'danger',
  postponed: 'neutral',
  closed: 'neutral',
};

interface CrmLeadListProps {
  isManager: boolean; hasPersonalDesk: boolean; leads: CrmLead[]; scope: 'mine' | 'pool' | 'all' | 'follow_ups'; loading: boolean; error: string;
  onScope: (scope: 'mine' | 'pool' | 'all' | 'follow_ups') => void; onFilters: (q: string, status: CrmLeadStatus | '') => void;
  onSelect: (lead: CrmLead) => void; onClaim: (lead: CrmLead) => void; onLookup: (phone: string) => void;
  lookup: CrmLookup | null; lookupLoading: boolean; onOpenLookup: (id: number) => void; onRequestLookupTransfer: (id: number) => void;
  /** استلامُ رقمٍ وُجد في المخزن من بطاقة البحث مباشرةً — الفعلُ الصحيح هناك. */
  onClaimLookup: (id: number) => void;
}

const tabClass = (active: boolean) =>
  `rounded-xl px-3.5 py-2 text-xs font-bold transition-colors duration-150 ${active ? 'bg-cc-accent text-cc-bg shadow-sm' : 'text-cc-text-muted hover:text-cc-text hover:bg-cc-surface-2'}`;

/**
 * بدايةُ اليومِ المحلّيّ — مرجعُ «متأخّرة» على البطاقة.
 *
 * كانت المقارنةُ بـ`Date.now()`، فموعدُ **اليوم** (تكتبه الشاشةُ 09:00) يصير
 * «متأخّراً» في التاسعة وواحدة وهو عملُ اليوم لا متأخّرُه؛ والأسوأُ أنّ الخادمَ
 * يعدّ «المتأخّرة» بقاعدةٍ ثانيةٍ فيختلف الرقمُ عن الشارة على الشاشة نفسِها.
 * القاعدةُ واحدةٌ في الطرفين: **يومٌ مضى** — نظيرُها الخادميُّ
 * `crm.services.follow_up_day_bounds`.
 */
const localStartOfToday = (): number => {
  const midnight = new Date();
  midnight.setHours(0, 0, 0, 0);
  return midnight.getTime();
};

export const CrmLeadList: React.FC<CrmLeadListProps> = ({ isManager, hasPersonalDesk, leads, scope, loading, error, onScope, onFilters, onSelect, onClaim, onLookup, lookup, lookupLoading, onOpenLookup, onRequestLookupTransfer, onClaimLookup }) => {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<CrmLeadStatus | ''>('');
  const [phone, setPhone] = useState('');
  const startOfToday = localStartOfToday();
  const submitSearch = (event: React.FormEvent) => { event.preventDefault(); onFilters(q, status); };
  const lookupPhone = (event: React.FormEvent) => { event.preventDefault(); if (phone.trim()) onLookup(phone); };

  return (
    <section className="space-y-4" aria-label="قائمة العملاء">
      <CcCard className="p-5">
        <CcSectionTitle
          title="العملاء"
          subtitle="ابحث باسم المحل أو رقم الهاتف ثم افتح ملف العميل أو استلمه من المخزن."
          badge={leads.length}
        />
        <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="نطاق العملاء">
          <button type="button" className={tabClass(scope === 'mine')} onClick={() => onScope('mine')} role="tab" aria-selected={scope === 'mine'}>عملائي</button>
          {hasPersonalDesk && <button type="button" className={tabClass(scope === 'follow_ups')} onClick={() => onScope('follow_ups')} role="tab" aria-selected={scope === 'follow_ups'}>متابعاتي</button>}
          <button type="button" className={tabClass(scope === 'pool')} onClick={() => onScope('pool')} role="tab" aria-selected={scope === 'pool'}>المخزن المتاح</button>
          {isManager && <button type="button" className={tabClass(scope === 'all')} onClick={() => onScope('all')} role="tab" aria-selected={scope === 'all'}>الكل</button>}
        </div>
        <form className="mt-4 grid gap-2 sm:grid-cols-[1fr_auto_auto]" onSubmit={submitSearch}>
          <label className="sr-only" htmlFor="crm-lead-search">ابحث بالاسم أو الرقم</label>
          <input
            id="crm-lead-search"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            className="rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted outline-none focus:border-cc-accent"
            placeholder="اسم المحل أو رقم الهاتف"
          />
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as CrmLeadStatus | '')}
            className="rounded-xl border border-cc-border bg-cc-surface px-3 py-2 text-sm text-cc-text focus:border-cc-accent focus:outline-none"
            aria-label="ترشيح بالحالة"
          >
            <option value="">كل الحالات</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <button
            type="submit"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
          >
            <Search className="h-4 w-4" />
            بحث
          </button>
        </form>
      </CcCard>

      <CcCard className="p-5">
        <CcSectionTitle title="بحث الرقم قبل الاتصال" />
        <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={lookupPhone}>
          <label className="sr-only" htmlFor="crm-phone-lookup">رقم الهاتف</label>
          <input
            id="crm-phone-lookup"
            dir="ltr"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            className="min-w-0 flex-1 rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-left text-sm text-cc-text placeholder:text-cc-text-muted outline-none focus:border-cc-accent"
            placeholder="0500000000"
          />
          <button
            type="submit"
            className="rounded-xl border border-cc-border bg-cc-surface-2 px-4 py-2 text-sm font-bold text-cc-text hover:border-cc-border-strong transition-colors"
          >
            تحقق من الرقم
          </button>
        </form>
        {lookupLoading && <p className="mt-3 text-sm text-cc-text-muted">جارٍ التحقق من الرقم...</p>}
        {/* ثلاثُ حالاتٍ لا حالتان. الرقمُ الموجودُ قد يكون **مُسنَداً** أو **في
            المخزن**؛ وقبلَ هذا كان المخزنُ يُعرَض ببطاقة القفل نفسِها فتقول «قيد
            المتابعة بواسطة الموظف: غير محدد» — إخبارٌ بقفلٍ لا وجودَ له، وحجبٌ
            لزرّ الاستلام الذي هو الفعلُ الصحيح هنا. */}
        {lookup?.found && lookup.locked_by && (
          <div className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
            <p className="flex items-center gap-2 font-bold text-amber-200">
              <LockKeyhole className="h-4 w-4" />
              هذا الرقم قيد المتابعة بواسطة الموظف: {lookup.locked_by.name}
            </p>
            <p className="mt-1 text-sm text-cc-text-muted">
              {lookup.is_mine ? 'هذا العميل مُسنَدٌ إليك أنت.' : 'لا يمكن لموظف آخر بدء محادثة جديدة مع هذا الرقم.'}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => lookup.lead && onOpenLookup(lookup.lead.id)}
                className="rounded-xl border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs font-bold text-cc-text hover:border-cc-border-strong transition-colors"
              >
                فتح الملف
              </button>
              {!lookup.is_mine && (
                <button
                  type="button"
                  onClick={() => lookup.lead && onRequestLookupTransfer(lookup.lead.id)}
                  className="rounded-xl bg-cc-accent px-3 py-1.5 text-xs font-bold text-cc-bg hover:opacity-90 transition-opacity"
                >
                  طلب تحويل العميل
                </button>
              )}
            </div>
          </div>
        )}
        {lookup?.found && !lookup.locked_by && (
          <div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
            <p className="font-bold text-emerald-300">هذا الرقم مسجَّلٌ وفي المخزن المتاح — لا موظّفَ عليه.</p>
            <p className="mt-1 text-sm text-cc-text-muted">استلِمْه قبل الاتصال كي لا يعمل عليه زميلٌ في الوقت نفسِه.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => lookup.lead && onOpenLookup(lookup.lead.id)}
                className="rounded-xl border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs font-bold text-cc-text hover:border-cc-border-strong transition-colors"
              >
                فتح الملف
              </button>
              {lookup.can_claim && (
                <button
                  type="button"
                  onClick={() => lookup.lead && onClaimLookup(lookup.lead.id)}
                  className="inline-flex items-center gap-1 rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition-colors"
                >
                  <UserPlus className="h-4 w-4" />
                  استلام
                </button>
              )}
            </div>
          </div>
        )}
        {lookup && !lookup.found && (
          <p className="mt-3 text-sm text-emerald-400">الرقم غير مسجل ويمكن اقتراحه أو إضافته.</p>
        )}
      </CcCard>

      <CcCard className="overflow-hidden">
        {loading ? (
          <div className="p-6 space-y-3">
            <CcSkeleton count={4} />
          </div>
        ) : error ? (
          <p className="p-6 text-sm text-rose-400" role="alert">{error}</p>
        ) : leads.length === 0 ? (
          <CcEmpty
            title="لا توجد نتائج في هذا النطاق"
            hint="غيّر البحث أو راجع المخزن المتاح."
            className="p-8"
          />
        ) : (
          <ul className="divide-y divide-cc-border">
            {leads.map((lead) => {
              const isOverdue = lead.next_follow_up_at !== null && new Date(lead.next_follow_up_at).getTime() < startOfToday;
              return (
                <li key={lead.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between transition-colors hover:bg-cc-surface-2/40">
                  <div className="flex items-center gap-3 min-w-0">
                    <CcAvatar name={lead.store_name} size="md" />
                    <button type="button" onClick={() => onSelect(lead)} className="min-w-0 text-right group">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="truncate font-extrabold text-cc-text group-hover:text-sky-400 transition-colors">
                          {lead.store_name}
                        </span>
                        <CcPill tone={STATUS_TONES[lead.status]}>{STATUS_LABELS[lead.status]}</CcPill>
                        {lead.next_follow_up_at && (
                          <CcPill tone={isOverdue ? 'danger' : 'accent'}>
                            {isOverdue ? 'متأخرة' : 'المتابعة القادمة'}: {formatDateValue(lead.next_follow_up_at)}
                          </CcPill>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-cc-text-muted">
                        <span>{lead.owner_name || 'لا يوجد اسم مالك'}</span>
                        <span>·</span>
                        <span dir="ltr" className="text-sky-400 font-mono">
                          {lead.phones[0]?.raw || 'لا يوجد رقم'}
                        </span>
                      </div>
                    </button>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 self-end sm:self-center">
                    <span className="text-xs font-mono text-cc-text-muted">#{formatNumber(lead.id)}</span>
                    {scope === 'pool' && (
                      <button
                        type="button"
                        onClick={() => onClaim(lead)}
                        className="inline-flex items-center gap-1 rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition-colors"
                      >
                        <UserPlus className="h-3.5 w-3.5" />
                        استلام
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => onSelect(lead)}
                      className="inline-flex items-center gap-1 rounded-xl border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs font-bold text-cc-text hover:border-cc-border-strong transition-colors"
                    >
                      <PhoneCall className="h-3.5 w-3.5 text-sky-400" />
                      فتح الملف
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CcCard>
    </section>
  );
};
