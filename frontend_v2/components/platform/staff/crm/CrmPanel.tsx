import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Plus } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { claimCrmLead, createCrmActivity, createCrmLead, changeCrmLeadStatus, getCrmLead, getCrmLeadStats, listCrmActivities, listCrmColleagues, listCrmLeads, lookupCrmPhone, releaseCrmLead, requestCrmLeadTransfer, transferCrmLead, type CrmActivity, type CrmActivityInput, type CrmColleague, type CrmLead, type CrmLeadContactStats, type CrmLeadStatus, type CrmLookup } from '../../../../services/platformCrmApi';
import { formatNumber } from '../../../../utils/formatNumber';
import { captureScrollPosition, restoreScrollPosition, type ScrollPositionSnapshot } from '../../../../utils/scrollPosition';
import { CcCard, CcSectionTitle } from '../../ui';
import { CRM_POOL_LABEL, CrmLeadList, STATUS_LABELS } from './CrmLeadList';
import { CrmLeadProfile } from './CrmLeadProfile';
import { CrmManagerPanel, CrmTeamPanel, type CrmEmployeePick } from './CrmManagerPanel';
import { CrmMyStats } from './CrmMyStats';
import { CrmTransferInbox } from './CrmTransferInbox';

interface CrmPanelProps {
  isManager: boolean;
  /**
   * معرّفُ الموظّف من ملفّه هو — **مصدرُ الملكيّة الوحيد**.
   *
   * كان يُستنبَط من `is_me` في دليل الزملاء، والدليلُ يعيد `active`
   * وحدَهم: فموظّفٌ في إجازةٍ يسقط من دليل نفسِه فيصير غيرَ مالكٍ
   * لعملائه، فيرسل «طلبَ تحويل» على عميلِ نفسِه ويسدَّ بابَه.
   */
  myEmployeeId: number | null;
}
type Scope = 'mine' | 'pool' | 'all' | 'follow_ups';
const SCOPES: readonly Scope[] = ['mine', 'pool', 'all', 'follow_ups'];
const isLeadStatus = (value: string): value is CrmLeadStatus => Object.prototype.hasOwnProperty.call(STATUS_LABELS, value);
// المُمرِّر: `main.app-content` داخل غلاف التطبيق (مركز العمليات)، والنافذةُ في غلاف الموظّف.
const scrollContainer = () => document.querySelector<HTMLElement>('main.app-content');
const messageOf = (caught: unknown, fallback: string) => caught instanceof Error ? caught.message : fallback;

export const CrmPanel: React.FC<CrmPanelProps> = ({ isManager, myEmployeeId }) => {
  // النطاقُ الابتدائيُّ يتبع **وجودَ دفترٍ شخصيّ**، لا قيمةً ثابتة.
  // `scope=mine` يُرشَّح خادميّاً بـ`assigned_to=employee`، وبلا صفِّ موظّفٍ يعيد
  // `base.none()` — **صفرٌ بحكم البناء لا نتيجةَ بحث**. فمالكُ المنصّة يدخل من
  // مركز القيادة بلا صفّ `PlatformEmployee`، فكان يهبط على «عملائي» فيقرأ لوحةً
  // خاويةً على تبويبٍ سمّاه له النظام: وهو بعينه ما شكا منه («وين التسويق»).
  // ومن لا دفترَ له والمديرُ معاً: الدفترُ الذي يعنيه هو الكلُّ.
  const defaultScope: Scope = myEmployeeId === null && isManager ? 'all' : 'mine';
  // #73/#69: النطاقُ والبحثُ والحالةُ والموظّفُ **في الرابط** (`scope`/`q`/`status`/`employee`)،
  // بجانب `?lead=` — فتحديثُ الصفحة وملفُّ عميلٍ فُتح برابطٍ مباشر يعيدان القائمةَ مرشَّحةً
  // كما تُركت. الترشيحُ يُبدَّل بـ`replace` (لا يملأ التاريخ)، وفتحُ الملفّ وحدَه يُدفع.
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const scopeParam = searchParams.get('scope') ?? '';
  const scope: Scope = (SCOPES as readonly string[]).includes(scopeParam) && (scopeParam !== 'all' || isManager) ? scopeParam as Scope : defaultScope;
  const filterQ = searchParams.get('q') ?? '';
  const statusParam = searchParams.get('status') ?? '';
  const filterStatus: CrmLeadStatus | '' = isLeadStatus(statusParam) ? statusParam : '';
  // `employee` يرشّح «الكل» بموظّفٍ أو بالمخزن (#69) — لا معنى له في النطاقات الأخرى فيسقط بتبديلها.
  const employeeParam = scope === 'all' ? searchParams.get('employee') : null;
  const employeeId: number | 'none' | null = employeeParam === 'none' ? 'none' : Number(employeeParam) > 0 ? Number(employeeParam) : null;
  const patchListParams = (patch: Record<string, string | null>) => setSearchParams((prev) => { const next = new URLSearchParams(prev); Object.entries(patch).forEach(([key, value]) => { if (value) next.set(key, value); else next.delete(key); }); return next; }, { replace: true });
  const setScope = (next: Scope) => patchListParams({ scope: next === defaultScope ? null : next, ...(next === 'all' ? {} : { employee: null }) });
  // الترقيم (#69): الخادمُ يعيد خمسين في الصفحة، فموظّفٌ يحمل 120 رقماً كان يُعرض منه 50 بلا إشارة.
  const [leadCount, setLeadCount] = useState(0); const [nextPage, setNextPage] = useState<number | null>(null); const [loadingMore, setLoadingMore] = useState(false);
  const [leads, setLeads] = useState<CrmLead[]>([]); const [listLoading, setListLoading] = useState(true); const [listError, setListError] = useState('');
  const [colleagues, setColleagues] = useState<CrmColleague[]>([]); const [selected, setSelected] = useState<CrmLead | null>(null); const [activities, setActivities] = useState<CrmActivity[]>([]); const [leadStats, setLeadStats] = useState<CrmLeadContactStats | null>(null); const [detailLoading, setDetailLoading] = useState(false); const [detailError, setDetailError] = useState('');
  const [lookup, setLookup] = useState<CrmLookup | null>(null); const [lookupLoading, setLookupLoading] = useState(false); const [notice, setNotice] = useState(''); const [suggestOpen, setSuggestOpen] = useState(false); const [requestLeadId, setRequestLeadId] = useState<number | null>(null); const [requestTo, setRequestTo] = useState(''); const [requestReason, setRequestReason] = useState('');
  const [storeName, setStoreName] = useState(''); const [phone, setPhone] = useState(''); const [ownerName, setOwnerName] = useState('');
  // عدّادٌ يُزاد بعد كلّ فعلٍ يبدّل الملكيّةَ أو الحالة، فتُعاد قراءةُ العدّادات
  // من الخادم. لا تُحسَب من صفوف الشاشة: القائمةُ مُصفَّحةٌ ومُرشَّحة.
  const [refreshKey, setRefreshKey] = useState(0);
  const bumpStats = () => setRefreshKey((value) => value + 1);
  // المرشِّحاتُ هنا لا في القائمة (#73/#69): كلُّ إعادةِ تحميلٍ — تبديلُ النطاق، والاستلامُ،
  // والتحويلُ، والبتُّ في طلب — كانت تنادي بلا بحثٍ ولا حالة، فيضيع الترشيحُ والخانتان
  // ما زالتا تعرضانه. والطلبُ الأحدثُ وحدَه يكتب النتيجة: ردٌّ بطيءٌ لطلبٍ أقدم يُهمَل.
  // اسمُ موظّفٍ اختير من لوح الفريق — قد لا يكون في دليل الزملاء (الدليلُ للنشِطين وحدَهم).
  const [pickedNames, setPickedNames] = useState<Record<number, string>>({});
  const employeeFilter: CrmEmployeePick | null = employeeId === null ? null
    : employeeId === 'none' ? { id: 'none', name: CRM_POOL_LABEL }
      : { id: employeeId, name: pickedNames[employeeId] ?? colleagues.find((colleague) => colleague.id === employeeId)?.name ?? `موظف #${formatNumber(employeeId)}` };
  const rememberName = (pick: CrmEmployeePick | null) => { if (pick && typeof pick.id === 'number') { const id = pick.id; const name = pick.name; setPickedNames((names) => (names[id] === name ? names : { ...names, [id]: name })); } };
  const setEmployee = (pick: CrmEmployeePick | null) => { rememberName(pick); patchListParams({ employee: pick ? String(pick.id) : null }); };
  const listRequestRef = useRef(0);
  const leadQuery = useCallback((page: number) => listCrmLeads({ scope: scope === 'follow_ups' ? 'mine' : scope, follow_up: scope === 'follow_ups' ? 'due' : undefined, q: filterQ || undefined, status: filterStatus || undefined, assigned_to: employeeId ?? undefined, page: page > 1 ? page : undefined }), [scope, filterQ, filterStatus, employeeId]);
  const loadLeads = useCallback(async () => { const requestId = ++listRequestRef.current; setListLoading(true); setListError(''); try { const page = await leadQuery(1); if (requestId === listRequestRef.current) { setLeads(page.results); setLeadCount(page.count); setNextPage(page.next ? 2 : null); } } catch (caught: unknown) { if (requestId === listRequestRef.current) { setLeads([]); setLeadCount(0); setNextPage(null); setListError(messageOf(caught, 'تعذر تحميل العملاء.')); } } finally { if (requestId === listRequestRef.current) setListLoading(false); } }, [leadQuery]);
  // «عرض المزيد» يُلحق الصفحةَ التالية؛ وترشيحٌ تبدّل أثناء الطلب يُسقط الردّ (نفسُ عدّاد القائمة).
  const loadMore = async () => { if (nextPage === null) return; const requestId = listRequestRef.current; setLoadingMore(true); try { const page = await leadQuery(nextPage); if (requestId === listRequestRef.current) { setLeads((current) => [...current, ...page.results]); setLeadCount(page.count); setNextPage(page.next ? nextPage + 1 : null); } } catch (caught: unknown) { if (requestId === listRequestRef.current) setNotice(messageOf(caught, 'تعذر تحميل المزيد.')); } finally { setLoadingMore(false); } };
  const loadColleagues = useCallback(async () => { try { setColleagues(await listCrmColleagues()); } catch { setColleagues([]); } }, []);
  useEffect(() => { void loadLeads(); }, [loadLeads]); useEffect(() => { void loadColleagues(); }, [loadColleagues]);
  // ملفُّ العميل في الرابط (`?lead=`) فزرُّ «رجوع» المتصفح يعيد القائمة، والقائمةُ تبقى
  // مركَّبةً مخفيّةً تحته — فلا يضيع بحثُها ولا يُعاد تحميلُ لوح المدير — ويُستعاد موضعُ
  // التمرير حين يُغلق الملفّ. كان الملفُّ يستبدل القائمةَ كلَّها فيرجع المديرُ لرأسها.
  const leadParam = Number(searchParams.get('lead')) || null;
  const pushedLeadRef = useRef(false);
  const listScrollRef = useRef<ScrollPositionSnapshot | null>(null);
  const setLeadParam = (id: number | null, replace: boolean) => setSearchParams((prev) => { const next = new URLSearchParams(prev); if (id) next.set('lead', String(id)); else next.delete('lead'); return next; }, { replace });
  const showLead = (id: number) => { if (!leadParam) listScrollRef.current = captureScrollPosition(scrollContainer(), window.scrollY); pushedLeadRef.current = true; setLeadParam(id, Boolean(leadParam)); };
  // رجوعٌ في التاريخ إن كنّا دفعنا الملفَّ إليه، وإلا (رابطٌ مباشر) حذفُ المعامل بلا دفع.
  const closeLead = () => { if (pushedLeadRef.current) { pushedLeadRef.current = false; navigate(-1); return; } setLeadParam(null, true); };
  // ستاتستكس الرقم تُطلَب مع الملفّ، وفشلُها **لا يُقفل الملفّ**: الأرقامُ زينةُ
  // قرارٍ والسجلُّ هو العمل. ولذلك `catch` على النداء نفسِه لا على `Promise.all`
  // كلِّه — الأخيرُ يسقط بسقوط واحد.
  const openLead = async (id: number) => { setDetailLoading(true); setDetailError(''); try { const [lead, page, stats] = await Promise.all([getCrmLead(id), listCrmActivities(id), getCrmLeadStats(id).catch(() => null)]); setSelected(lead); setActivities(page.results); setLeadStats(stats); } catch (caught: unknown) { setDetailError(messageOf(caught, 'لا يمكن فتح ملف هذا العميل.')); setNotice(messageOf(caught, 'لا يمكن فتح ملف هذا العميل.')); setSelected(null); setLeadStats(null); setLeadParam(null, true); } finally { setDetailLoading(false); } };
  useEffect(() => {
    if (leadParam) {
      void openLead(leadParam).then(() => { const el = scrollContainer(); if (el) el.scrollTop = 0; else window.scrollTo(0, 0); });
      return;
    }
    pushedLeadRef.current = false; setSelected(null); setDetailError(''); setLeadStats(null);
    const snapshot = listScrollRef.current; listScrollRef.current = null;
    if (snapshot) window.requestAnimationFrame(() => restoreScrollPosition(snapshot, (top) => window.scrollTo(0, top)));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- المعاملُ وحدَه يقود فتحَ الملفّ وإغلاقَه
  }, [leadParam]);
  // كبسةُ موظّفٍ في لوح الفريق: «الكل» مرشَّحاً بأرقامه، والشاشةُ تنزل إلى القائمة.
  const listTopRef = useRef<HTMLDivElement>(null);
  const pickEmployee = (employee: CrmEmployeePick) => { rememberName(employee); patchListParams({ scope: defaultScope === 'all' ? null : 'all', employee: String(employee.id) }); window.requestAnimationFrame(() => listTopRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })); };
  const claim = async (lead: CrmLead) => { try { await claimCrmLead(lead.id); setNotice(`تم استلام ${lead.store_name}.`); bumpStats(); await loadLeads(); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر استلام العميل.')); } };
  // استلامٌ من بطاقة البحث: الرقمُ وُجد في المخزن، والفعلُ الصحيح هناك أن يُستلَم
  // لا أن يُطلَب تحويلُه. وبعد الاستلام يُنقل النطاقُ إلى «عملائي» ليراه فوراً.
  const claimFromLookup = async (id: number) => { try { await claimCrmLead(id); setNotice('تم استلام العميل، وصار في «عملائي».'); setLookup(null); bumpStats(); if (scope === 'mine') await loadLeads(); else setScope('mine'); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر استلام العميل.')); } };
  const performLookup = async (value: string) => { setLookupLoading(true); try { setLookup(await lookupCrmPhone(value)); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر التحقق من الرقم.')); setLookup(null); } finally { setLookupLoading(false); } };
  const saveStatus = async (status: CrmLeadStatus, body: string) => { if (!selected) return; try { const lead = await changeCrmLeadStatus(selected.id, status, body); setSelected(lead); bumpStats(); await openLead(lead.id); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر تغيير الحالة.')); } };
  const saveActivity = async (input: CrmActivityInput) => { if (!selected) return; try { await createCrmActivity(selected.id, input); await openLead(selected.id); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر حفظ سجل التواصل.')); } };
  const transfer = async (toEmployee: number, reason: string, direct: boolean) => { if (!selected) return; try { if (direct) await transferCrmLead(selected.id, toEmployee, reason); else await requestCrmLeadTransfer(selected.id, toEmployee, reason); setNotice(direct ? 'تم تحويل العميل.' : 'أرسل طلب تحويل العميل.'); closeLead(); bumpStats(); await loadLeads(); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر تنفيذ التحويل.')); } };
  // السببُ يأتي من حقلٍ في الصفحة لا من `window.prompt`: حوارُ المتصفّح لا
  // يُنسَّق ولا يحمل اتّجاه RTL، ويحجبه بعضُ المتصفّحات، ونمطُ هذا المستودع
  // `ToastProvider`/`ConfirmProvider` لا نوافذُ المتصفّح.
  const release = async (reason: string) => { if (!selected || !isManager || !reason.trim()) return; try { await releaseCrmLead(selected.id, reason); setNotice('أعيد العميل إلى المخزن المتاح.'); closeLead(); bumpStats(); await loadLeads(); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر إعادة العميل إلى المخزن.')); } };
  const suggest = async (event: React.FormEvent) => { event.preventDefault(); try { const created = await createCrmLead({ store_name: storeName, owner_name: ownerName || undefined, phones: [{ raw: phone, kind: 'primary' }] }); setNotice(isManager ? `تمت إضافة ${created.store_name}.` : `أُرسل اقتراح ${created.store_name} للاعتماد.`); setSuggestOpen(false); setStoreName(''); setPhone(''); setOwnerName(''); await loadLeads(); } catch (caught: unknown) { const data = caught instanceof Error && 'data' in caught ? (caught as Error & { data?: { existing_lead_name?: string; assigned_to?: { name: string } | null } }).data : undefined; setNotice(data?.existing_lead_name ? `هذا الرقم مسجّل لدى ${data.existing_lead_name}، والمسؤول ${data.assigned_to?.name || 'غير محدد'}.` : messageOf(caught, 'تعذر حفظ الرقم.')); } };
  const submitLookupTransfer = async (event: React.FormEvent) => { event.preventDefault(); if (!requestLeadId || !requestTo || !requestReason.trim()) return; try { await requestCrmLeadTransfer(requestLeadId, Number(requestTo), requestReason); setNotice('أرسل طلب التحويل إلى الموظف المسؤول.'); setRequestLeadId(null); setRequestTo(''); setRequestReason(''); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر إرسال طلب التحويل.')); } };
  // ‏`key` بمعرّف العميل: اللوحةُ تحمل حالةً محلّيّةً (الحالةُ المختارةُ ونصُّ
  // السبب ونموذجُ النشاط)، وبلا إعادةِ التركيب تنتقل تلك الحالةُ من عميلٍ إلى
  // الذي بعده — فيُحفَظ سببُ تحويلِ الأوّل على الثاني.
  return (
    <>
    {selected && <CrmLeadProfile key={selected.id} lead={selected} activities={activities} stats={leadStats} loading={detailLoading} error={detailError} isManager={isManager} isOwner={Boolean(myEmployeeId && selected.assigned_to?.id === myEmployeeId)} colleagues={colleagues} onBack={closeLead} onStatus={saveStatus} onActivity={saveActivity} onTransfer={transfer} onRelease={release} />}
    <div className={selected ? 'hidden' : 'space-y-6'} data-testid="crm-list-view">
      {myEmployeeId !== null && <CrmMyStats refreshKey={refreshKey} />}
      {isManager && <CrmTeamPanel isManager={isManager} refreshKey={refreshKey} onPickEmployee={pickEmployee} />}
      <div ref={listTopRef} className="scroll-mt-4" />
      <CrmLeadList
        isManager={isManager}
        hasPersonalDesk={myEmployeeId !== null}
        leads={leads}
        scope={scope}
        loading={listLoading}
        error={listError}
        onScope={setScope}
        appliedQ={filterQ}
        appliedStatus={filterStatus}
        onFilters={(q, status) => patchListParams({ q: q.trim() || null, status: status || null })}
        employeeFilter={employeeFilter}
        employeeOptions={colleagues}
        onEmployeeFilter={setEmployee}
        onSelect={(lead) => showLead(lead.id)}
        onClaim={(lead) => void claim(lead)}
        onLookup={(value) => void performLookup(value)}
        lookup={lookup}
        lookupLoading={lookupLoading}
        onOpenLookup={showLead}
        onRequestLookupTransfer={(id) => setRequestLeadId(id)}
        onClaimLookup={(id) => void claimFromLookup(id)}
      />
      {nextPage !== null && !listLoading && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={loadingMore}
            data-testid="crm-load-more"
            className="rounded-xl border border-cc-border bg-cc-surface px-4 py-2 text-sm font-bold text-cc-text hover:border-cc-accent disabled:opacity-60"
          >
            {loadingMore ? 'جارٍ التحميل…' : `عرض المزيد — ${formatNumber(leads.length)} من ${formatNumber(leadCount)}`}
          </button>
        </div>
      )}
      <CrmTransferInbox onDecided={() => { bumpStats(); void loadLeads(); }} onNotice={setNotice} />
      {requestLeadId && (
        <CcCard tone="warning" className="p-5">
          <CcSectionTitle title="طلب تحويل العميل" subtitle="اختر الموظف المستلم واكتب السبب لإرسال الطلب." />
          <form onSubmit={submitLookupTransfer} className="mt-4 space-y-3">
            <select
              required
              value={requestTo}
              onChange={(event) => setRequestTo(event.target.value)}
              className="w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text focus:border-cc-accent focus:outline-none"
              aria-label="تحويل إلى"
            >
              <option value="">اختر الموظف</option>
              {colleagues.filter((employee) => !employee.is_me).map((employee) => (
                <option key={employee.id} value={employee.id}>{employee.name}</option>
              ))}
            </select>
            <input
              required
              value={requestReason}
              onChange={(event) => setRequestReason(event.target.value)}
              className="w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
              placeholder="سبب التحويل"
            />
            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                className="rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
              >
                إرسال الطلب
              </button>
              <button
                type="button"
                onClick={() => setRequestLeadId(null)}
                className="rounded-xl border border-cc-border bg-cc-surface-2 px-4 py-2 text-sm font-bold text-cc-text hover:border-cc-border-strong transition-colors"
              >
                إلغاء
              </button>
            </div>
          </form>
        </CcCard>
      )}
      <CcCard className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CcSectionTitle
            title={isManager ? 'إضافة رقم' : 'اقتراح رقم'}
            subtitle={isManager ? 'يُضاف الرقم معتمداً.' : 'يرسل الاقتراح إلى المدير للاعتماد.'}
          />
          <button
            type="button"
            onClick={() => setSuggestOpen((value) => !value)}
            className="inline-flex items-center gap-2 rounded-xl bg-cc-accent px-3 py-2 text-xs font-extrabold text-cc-bg hover:opacity-90 transition-opacity shrink-0"
          >
            <Plus className="h-4 w-4" />
            {isManager ? 'إضافة رقم' : 'اقتراح رقم'}
          </button>
        </div>
        {suggestOpen && (
          <form onSubmit={suggest} className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-bold text-cc-text">
              اسم المحل
              <input
                required
                value={storeName}
                onChange={(event) => setStoreName(event.target.value)}
                className="mt-1.5 w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
              />
            </label>
            <label className="text-xs font-bold text-cc-text">
              رقم الهاتف
              <input
                required
                dir="ltr"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                className="mt-1.5 w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-left text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
              />
            </label>
            <label className="text-xs font-bold text-cc-text">
              صاحب المحل (اختياري)
              <input
                value={ownerName}
                onChange={(event) => setOwnerName(event.target.value)}
                className="mt-1.5 w-full rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
              />
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                className="rounded-xl bg-cc-accent px-4 py-2 text-sm font-extrabold text-cc-bg hover:opacity-90 transition-opacity"
              >
                حفظ
              </button>
            </div>
          </form>
        )}
      </CcCard>
      {isManager && <CrmManagerPanel isManager={isManager} onLeadChanged={() => { bumpStats(); void loadLeads(); }} />}
      {notice && (
        <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-sm text-sky-200" role="status">
          {notice}
        </div>
      )}
    </div>
    </>
  );
};
