import React, { useState } from 'react';
import { LockKeyhole, PhoneCall, Search, UserPlus } from 'lucide-react';

import type { CrmLead, CrmLeadStatus, CrmLookup } from '../../../../services/platformCrmApi';
import { formatNumber } from '../../../../utils/formatNumber';

export const STATUS_LABELS: Record<CrmLeadStatus, string> = {
  new: 'جديد', contacted: 'تم الاتصال', interested: 'مهتم', follow_up: 'متابعة', customer: 'عميل',
  not_interested: 'غير مهتم', no_answer: 'لا يجيب', wrong_number: 'رقم خاطئ', postponed: 'مؤجل', closed: 'مغلق',
};

interface CrmLeadListProps {
  isManager: boolean; leads: CrmLead[]; scope: 'mine' | 'pool' | 'all'; loading: boolean; error: string;
  onScope: (scope: 'mine' | 'pool' | 'all') => void; onFilters: (q: string, status: CrmLeadStatus | '') => void;
  onSelect: (lead: CrmLead) => void; onClaim: (lead: CrmLead) => void; onLookup: (phone: string) => void;
  lookup: CrmLookup | null; lookupLoading: boolean; onOpenLookup: (id: number) => void; onRequestLookupTransfer: (id: number) => void;
  /** استلامُ رقمٍ وُجد في المخزن من بطاقة البحث مباشرةً — الفعلُ الصحيح هناك. */
  onClaimLookup: (id: number) => void;
}

const tabClass = (active: boolean) => `rounded-lg px-3 py-2 text-sm font-bold ${active ? 'bg-[var(--staff-accent)] text-slate-950' : 'text-[var(--staff-muted)] hover:bg-black/15'}`;

export const CrmLeadList: React.FC<CrmLeadListProps> = ({ isManager, leads, scope, loading, error, onScope, onFilters, onSelect, onClaim, onLookup, lookup, lookupLoading, onOpenLookup, onRequestLookupTransfer, onClaimLookup }) => {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState<CrmLeadStatus | ''>('');
  const [phone, setPhone] = useState('');
  const submitSearch = (event: React.FormEvent) => { event.preventDefault(); onFilters(q, status); };
  const lookupPhone = (event: React.FormEvent) => { event.preventDefault(); if (phone.trim()) onLookup(phone); };

  return <section className="space-y-4" aria-label="قائمة العملاء">
    <header className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
      <h1 className="text-xl font-extrabold text-[var(--staff-text)]">العملاء</h1>
      <p className="mt-1 text-sm text-[var(--staff-muted)]">ابحث باسم المحل أو رقم الهاتف ثم افتح ملف العميل أو استلمه من المخزن.</p>
      <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="نطاق العملاء">
        <button type="button" className={tabClass(scope === 'mine')} onClick={() => onScope('mine')} role="tab" aria-selected={scope === 'mine'}>عملائي</button>
        <button type="button" className={tabClass(scope === 'pool')} onClick={() => onScope('pool')} role="tab" aria-selected={scope === 'pool'}>المخزن المتاح</button>
        {isManager && <button type="button" className={tabClass(scope === 'all')} onClick={() => onScope('all')} role="tab" aria-selected={scope === 'all'}>الكل</button>}
      </div>
      <form className="mt-4 grid gap-2 sm:grid-cols-[1fr_auto_auto]" onSubmit={submitSearch}>
        <label className="sr-only" htmlFor="crm-lead-search">ابحث بالاسم أو الرقم</label>
        <input id="crm-lead-search" value={q} onChange={(event) => setQ(event.target.value)} className="rounded-xl border border-[var(--staff-line)] bg-black/15 px-3 py-2 text-sm text-[var(--staff-text)] outline-none focus:border-cyan-400" placeholder="اسم المحل أو رقم الهاتف" />
        <select value={status} onChange={(event) => setStatus(event.target.value as CrmLeadStatus | '')} className="rounded-xl border border-[var(--staff-line)] bg-black/15 px-3 py-2 text-sm text-[var(--staff-text)]" aria-label="ترشيح بالحالة">
          <option value="">كل الحالات</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <button type="submit" className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--staff-accent)] px-4 py-2 text-sm font-extrabold text-slate-950"><Search className="h-4 w-4" />بحث</button>
      </form>
    </header>

    <section className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30">
      <h2 className="text-base font-extrabold text-[var(--staff-text)]">بحث الرقم قبل الاتصال</h2>
      <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={lookupPhone}>
        <label className="sr-only" htmlFor="crm-phone-lookup">رقم الهاتف</label>
        <input id="crm-phone-lookup" dir="ltr" value={phone} onChange={(event) => setPhone(event.target.value)} className="min-w-0 flex-1 rounded-xl border border-[var(--staff-line)] bg-black/15 px-3 py-2 text-left text-sm text-[var(--staff-text)] outline-none focus:border-cyan-400" placeholder="0500000000" />
        <button type="submit" className="rounded-xl border border-cyan-400/50 px-4 py-2 text-sm font-bold text-cyan-300 hover:bg-cyan-400/10">تحقق من الرقم</button>
      </form>
      {lookupLoading && <p className="mt-3 text-sm text-[var(--staff-muted)]">جارٍ التحقق من الرقم...</p>}
      {/* ثلاثُ حالاتٍ لا حالتان. الرقمُ الموجودُ قد يكون **مُسنَداً** أو **في
          المخزن**؛ وقبلَ هذا كان المخزنُ يُعرَض ببطاقة القفل نفسِها فتقول «قيد
          المتابعة بواسطة الموظف: غير محدد» — إخبارٌ بقفلٍ لا وجودَ له، وحجبٌ
          لزرّ الاستلام الذي هو الفعلُ الصحيح هنا. */}
      {lookup?.found && lookup.locked_by && <div className="mt-3 rounded-xl border border-amber-400/40 bg-amber-400/10 p-4"><p className="flex items-center gap-2 font-bold text-amber-200"><LockKeyhole className="h-4 w-4" />هذا الرقم قيد المتابعة بواسطة الموظف: {lookup.locked_by.name}</p><p className="mt-1 text-sm text-[var(--staff-muted)]">{lookup.is_mine ? 'هذا العميل مُسنَدٌ إليك أنت.' : 'لا يمكن لموظف آخر بدء محادثة جديدة مع هذا الرقم.'}</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => lookup.lead && onOpenLookup(lookup.lead.id)} className="rounded-lg border border-[var(--staff-line)] px-3 py-2 text-sm font-bold text-[var(--staff-text)]">فتح الملف</button>{!lookup.is_mine && <button type="button" onClick={() => lookup.lead && onRequestLookupTransfer(lookup.lead.id)} className="rounded-lg bg-amber-300 px-3 py-2 text-sm font-bold text-slate-950">طلب تحويل العميل</button>}</div></div>}
      {lookup?.found && !lookup.locked_by && <div className="mt-3 rounded-xl border border-emerald-400/40 bg-emerald-400/10 p-4"><p className="font-bold text-emerald-200">هذا الرقم مسجَّلٌ وفي المخزن المتاح — لا موظّفَ عليه.</p><p className="mt-1 text-sm text-[var(--staff-muted)]">استلِمْه قبل الاتصال كي لا يعمل عليه زميلٌ في الوقت نفسِه.</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => lookup.lead && onOpenLookup(lookup.lead.id)} className="rounded-lg border border-[var(--staff-line)] px-3 py-2 text-sm font-bold text-[var(--staff-text)]">فتح الملف</button>{lookup.can_claim && <button type="button" onClick={() => lookup.lead && onClaimLookup(lookup.lead.id)} className="inline-flex items-center gap-1 rounded-lg bg-emerald-400 px-3 py-2 text-sm font-bold text-slate-950"><UserPlus className="h-4 w-4" />استلام</button>}</div></div>}
      {lookup && !lookup.found && <p className="mt-3 text-sm text-emerald-300">الرقم غير مسجل ويمكن اقتراحه أو إضافته.</p>}
    </section>

    <section className="overflow-hidden rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] shadow-lg shadow-black/30">
      {loading ? <p className="p-6 text-sm text-[var(--staff-muted)]" role="status">جارٍ تحميل العملاء...</p> : error ? <p className="p-6 text-sm text-rose-300" role="alert">{error}</p> : leads.length === 0 ? <p className="p-8 text-center text-sm text-[var(--staff-muted)]">لا توجد نتائج في هذا النطاق. غيّر البحث أو راجع المخزن المتاح.</p> : <ul className="divide-y divide-[var(--staff-line)]">{leads.map((lead) => <li key={lead.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"><button type="button" onClick={() => onSelect(lead)} className="min-w-0 text-right"><span className="block truncate font-extrabold text-[var(--staff-text)]">{lead.store_name}</span><span className="mt-1 block text-sm text-[var(--staff-muted)]">{lead.owner_name || 'لا يوجد اسم مالك'} · {STATUS_LABELS[lead.status]}</span><span dir="ltr" className="mt-1 block text-left text-xs text-cyan-300">{lead.phones[0]?.raw || 'لا يوجد رقم'}</span></button><div className="flex shrink-0 items-center gap-2"><span className="text-xs text-[var(--staff-muted)]">#{formatNumber(lead.id)}</span>{scope === 'pool' && <button type="button" onClick={() => onClaim(lead)} className="inline-flex items-center gap-1 rounded-lg bg-emerald-400 px-3 py-2 text-sm font-bold text-slate-950"><UserPlus className="h-4 w-4" />استلام</button>}<button type="button" onClick={() => onSelect(lead)} className="inline-flex items-center gap-1 rounded-lg border border-[var(--staff-line)] px-3 py-2 text-sm font-bold text-[var(--staff-text)]"><PhoneCall className="h-4 w-4" />فتح الملف</button></div></li>)}</ul>}
    </section>
  </section>;
};
