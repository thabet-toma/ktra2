import React, { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';

import { claimCrmLead, createCrmActivity, createCrmLead, changeCrmLeadStatus, getCrmLead, getCrmLeadStats, listCrmActivities, listCrmColleagues, listCrmLeads, lookupCrmPhone, releaseCrmLead, requestCrmLeadTransfer, transferCrmLead, type CrmActivity, type CrmActivityInput, type CrmColleague, type CrmLead, type CrmLeadContactStats, type CrmLeadStatus, type CrmLookup } from '../../../../services/platformCrmApi';
import { CcCard, CcSectionTitle } from '../../ui';
import { CrmLeadList } from './CrmLeadList';
import { CrmLeadProfile } from './CrmLeadProfile';
import { CrmManagerPanel } from './CrmManagerPanel';
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
const messageOf = (caught: unknown, fallback: string) => caught instanceof Error ? caught.message : fallback;

export const CrmPanel: React.FC<CrmPanelProps> = ({ isManager, myEmployeeId }) => {
  // النطاقُ الابتدائيُّ يتبع **وجودَ دفترٍ شخصيّ**، لا قيمةً ثابتة.
  // `scope=mine` يُرشَّح خادميّاً بـ`assigned_to=employee`، وبلا صفِّ موظّفٍ يعيد
  // `base.none()` — **صفرٌ بحكم البناء لا نتيجةَ بحث**. فمالكُ المنصّة يدخل من
  // مركز القيادة بلا صفّ `PlatformEmployee`، فكان يهبط على «عملائي» فيقرأ لوحةً
  // خاويةً على تبويبٍ سمّاه له النظام: وهو بعينه ما شكا منه («وين التسويق»).
  // ومن لا دفترَ له والمديرُ معاً: الدفترُ الذي يعنيه هو الكلُّ.
  const [scope, setScope] = useState<Scope>(myEmployeeId === null && isManager ? 'all' : 'mine'); const [leads, setLeads] = useState<CrmLead[]>([]); const [listLoading, setListLoading] = useState(true); const [listError, setListError] = useState('');
  const [colleagues, setColleagues] = useState<CrmColleague[]>([]); const [selected, setSelected] = useState<CrmLead | null>(null); const [activities, setActivities] = useState<CrmActivity[]>([]); const [leadStats, setLeadStats] = useState<CrmLeadContactStats | null>(null); const [detailLoading, setDetailLoading] = useState(false); const [detailError, setDetailError] = useState('');
  const [lookup, setLookup] = useState<CrmLookup | null>(null); const [lookupLoading, setLookupLoading] = useState(false); const [notice, setNotice] = useState(''); const [suggestOpen, setSuggestOpen] = useState(false); const [requestLeadId, setRequestLeadId] = useState<number | null>(null); const [requestTo, setRequestTo] = useState(''); const [requestReason, setRequestReason] = useState('');
  const [storeName, setStoreName] = useState(''); const [phone, setPhone] = useState(''); const [ownerName, setOwnerName] = useState('');
  // عدّادٌ يُزاد بعد كلّ فعلٍ يبدّل الملكيّةَ أو الحالة، فتُعاد قراءةُ العدّادات
  // من الخادم. لا تُحسَب من صفوف الشاشة: القائمةُ مُصفَّحةٌ ومُرشَّحة.
  const [refreshKey, setRefreshKey] = useState(0);
  const bumpStats = () => setRefreshKey((value) => value + 1);
  const loadLeads = useCallback(async (nextScope: Scope = scope, q = '', status: CrmLeadStatus | '' = '') => { setListLoading(true); setListError(''); try { const page = await listCrmLeads({ scope: nextScope === 'follow_ups' ? 'mine' : nextScope, follow_up: nextScope === 'follow_ups' ? 'due' : undefined, q: q || undefined, status: status || undefined }); setLeads(page.results); } catch (caught: unknown) { setLeads([]); setListError(messageOf(caught, 'تعذر تحميل العملاء.')); } finally { setListLoading(false); } }, [scope]);
  const loadColleagues = useCallback(async () => { try { setColleagues(await listCrmColleagues()); } catch { setColleagues([]); } }, []);
  useEffect(() => { void loadLeads(); }, [loadLeads]); useEffect(() => { void loadColleagues(); }, [loadColleagues]);
  // ستاتستكس الرقم تُطلَب مع الملفّ، وفشلُها **لا يُقفل الملفّ**: الأرقامُ زينةُ
  // قرارٍ والسجلُّ هو العمل. ولذلك `catch` على النداء نفسِه لا على `Promise.all`
  // كلِّه — الأخيرُ يسقط بسقوط واحد.
  const openLead = async (id: number) => { setDetailLoading(true); setDetailError(''); try { const [lead, page, stats] = await Promise.all([getCrmLead(id), listCrmActivities(id), getCrmLeadStats(id).catch(() => null)]); setSelected(lead); setActivities(page.results); setLeadStats(stats); } catch (caught: unknown) { setDetailError(messageOf(caught, 'لا يمكن فتح ملف هذا العميل.')); setNotice(messageOf(caught, 'لا يمكن فتح ملف هذا العميل.')); setSelected(null); setLeadStats(null); } finally { setDetailLoading(false); } };
  const claim = async (lead: CrmLead) => { try { await claimCrmLead(lead.id); setNotice(`تم استلام ${lead.store_name}.`); bumpStats(); await loadLeads('pool'); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر استلام العميل.')); } };
  // استلامٌ من بطاقة البحث: الرقمُ وُجد في المخزن، والفعلُ الصحيح هناك أن يُستلَم
  // لا أن يُطلَب تحويلُه. وبعد الاستلام يُنقل النطاقُ إلى «عملائي» ليراه فوراً.
  const claimFromLookup = async (id: number) => { try { await claimCrmLead(id); setNotice('تم استلام العميل، وصار في «عملائي».'); setLookup(null); bumpStats(); setScope('mine'); await loadLeads('mine'); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر استلام العميل.')); } };
  const performLookup = async (value: string) => { setLookupLoading(true); try { setLookup(await lookupCrmPhone(value)); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر التحقق من الرقم.')); setLookup(null); } finally { setLookupLoading(false); } };
  const saveStatus = async (status: CrmLeadStatus, body: string) => { if (!selected) return; try { const lead = await changeCrmLeadStatus(selected.id, status, body); setSelected(lead); bumpStats(); await openLead(lead.id); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر تغيير الحالة.')); } };
  const saveActivity = async (input: CrmActivityInput) => { if (!selected) return; try { await createCrmActivity(selected.id, input); await openLead(selected.id); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر حفظ سجل التواصل.')); } };
  const transfer = async (toEmployee: number, reason: string, direct: boolean) => { if (!selected) return; try { if (direct) await transferCrmLead(selected.id, toEmployee, reason); else await requestCrmLeadTransfer(selected.id, toEmployee, reason); setNotice(direct ? 'تم تحويل العميل.' : 'أرسل طلب تحويل العميل.'); setSelected(null); bumpStats(); await loadLeads(); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر تنفيذ التحويل.')); } };
  // السببُ يأتي من حقلٍ في الصفحة لا من `window.prompt`: حوارُ المتصفّح لا
  // يُنسَّق ولا يحمل اتّجاه RTL، ويحجبه بعضُ المتصفّحات، ونمطُ هذا المستودع
  // `ToastProvider`/`ConfirmProvider` لا نوافذُ المتصفّح.
  const release = async (reason: string) => { if (!selected || !isManager || !reason.trim()) return; try { await releaseCrmLead(selected.id, reason); setNotice('أعيد العميل إلى المخزن المتاح.'); setSelected(null); bumpStats(); await loadLeads(); } catch (caught: unknown) { setDetailError(messageOf(caught, 'تعذر إعادة العميل إلى المخزن.')); } };
  const suggest = async (event: React.FormEvent) => { event.preventDefault(); try { const created = await createCrmLead({ store_name: storeName, owner_name: ownerName || undefined, phones: [{ raw: phone, kind: 'primary' }] }); setNotice(isManager ? `تمت إضافة ${created.store_name}.` : `أُرسل اقتراح ${created.store_name} للاعتماد.`); setSuggestOpen(false); setStoreName(''); setPhone(''); setOwnerName(''); await loadLeads(); } catch (caught: unknown) { const data = caught instanceof Error && 'data' in caught ? (caught as Error & { data?: { existing_lead_name?: string; assigned_to?: { name: string } | null } }).data : undefined; setNotice(data?.existing_lead_name ? `هذا الرقم مسجّل لدى ${data.existing_lead_name}، والمسؤول ${data.assigned_to?.name || 'غير محدد'}.` : messageOf(caught, 'تعذر حفظ الرقم.')); } };
  const submitLookupTransfer = async (event: React.FormEvent) => { event.preventDefault(); if (!requestLeadId || !requestTo || !requestReason.trim()) return; try { await requestCrmLeadTransfer(requestLeadId, Number(requestTo), requestReason); setNotice('أرسل طلب التحويل إلى الموظف المسؤول.'); setRequestLeadId(null); setRequestTo(''); setRequestReason(''); } catch (caught: unknown) { setNotice(messageOf(caught, 'تعذر إرسال طلب التحويل.')); } };
  // ‏`key` بمعرّف العميل: اللوحةُ تحمل حالةً محلّيّةً (الحالةُ المختارةُ ونصُّ
  // السبب ونموذجُ النشاط)، وبلا إعادةِ التركيب تنتقل تلك الحالةُ من عميلٍ إلى
  // الذي بعده — فيُحفَظ سببُ تحويلِ الأوّل على الثاني.
  if (selected) return <CrmLeadProfile key={selected.id} lead={selected} activities={activities} stats={leadStats} loading={detailLoading} error={detailError} isManager={isManager} isOwner={Boolean(myEmployeeId && selected.assigned_to?.id === myEmployeeId)} colleagues={colleagues} onBack={() => { setSelected(null); setDetailError(''); }} onStatus={saveStatus} onActivity={saveActivity} onTransfer={transfer} onRelease={release} />;
  return (
    <div className="space-y-6">
      {myEmployeeId !== null && <CrmMyStats refreshKey={refreshKey} />}
      <CrmLeadList
        isManager={isManager}
        hasPersonalDesk={myEmployeeId !== null}
        leads={leads}
        scope={scope}
        loading={listLoading}
        error={listError}
        onScope={(nextScope) => { setScope(nextScope); void loadLeads(nextScope); }}
        onFilters={(q, status) => void loadLeads(scope, q, status)}
        onSelect={(lead) => void openLead(lead.id)}
        onClaim={(lead) => void claim(lead)}
        onLookup={(value) => void performLookup(value)}
        lookup={lookup}
        lookupLoading={lookupLoading}
        onOpenLookup={(id) => void openLead(id)}
        onRequestLookupTransfer={(id) => setRequestLeadId(id)}
        onClaimLookup={(id) => void claimFromLookup(id)}
      />
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
      {isManager && <CrmManagerPanel isManager={isManager} onLeadChanged={() => void loadLeads()} />}
      {notice && (
        <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-sm text-sky-200" role="status">
          {notice}
        </div>
      )}
    </div>
  );
};
