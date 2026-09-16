import React, { useCallback, useEffect, useState } from 'react';
import { ArrowRightLeft, Check, X } from 'lucide-react';

import {
  decideCrmTransferRequest,
  listCrmTransferRequests,
  type CrmTransfer,
} from '../../../../services/platformCrmApi';
import type { CcTone } from '../../../../utils/ccTone';
import { formatDateTimeValue } from '../../../../utils/formatDate';
import { formatNumber } from '../../../../utils/formatNumber';
import { CcCard, CcEmpty, CcPill, CcSectionTitle, CcSkeleton } from '../../ui';

/**
 * صندوقُ طلبات التحويل — **بلا هذه اللوحة يكون زرُّ «طلب تحويل العميل» بابَ
 * مسدودٍ**: الطلبُ يُرسَل ويُخزَّن ولا يراه أحدٌ ولا يبتّ فيه أحد.
 *
 * كانت النقاطُ الثلاثُ (`transfer-requests/` قائمةً وتفصيلاً و`decide/`) مكتوبةً
 * في عميل الـAPI ولا يستدعيها مكوّنٌ واحد — يحرس ذلك بعد اليوم تعدادُ
 * الاستهلاك **في المكوّنات** لا في العميل (`test_crm_ui_contract.py`).
 *
 * والقائمةُ مضيَّقةٌ خادميّاً على ما يخصّ الطالبَ أو صاحبَ العميل، فما يظهر هنا
 * هو ما يحقّ لقارئه أن يراه — لا ترشيحَ في الواجهة يُلتفُّ عليه.
 *
 * **لكنّ الرؤيةَ ليست البتّ** (212-Q2-ب): كانت «قبول/رفض» تُرسَمان على كلّ طلبٍ
 * معلَّق، ومنها ما طلبتَه أنت من زميلك — فينقر صاحبُه على «قبول» فيوافق على
 * طلبِ نفسِه، ويردّ الخادمُ ٤٠٣. والزرُّ الآن خلف `can_decide` **الذي يقوله
 * الخادم** من القاعدة نفسِها التي يرفض بها، لا من نسخةٍ ثانيةٍ لها هنا.
 */
const STATUS_LABELS: Record<string, string> = {
  pending: 'بانتظار القرار',
  approved: 'مقبول',
  rejected: 'مرفوض',
};

const STATUS_TONES: Record<string, CcTone> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
};

interface CrmTransferInboxProps {
  /** يُنادى بعد كلّ بتٍّ ناجح كي تُحدَّث قائمةُ العملاء: الملكيّةُ تغيّرت. */
  onDecided: () => void;
  onNotice: (message: string) => void;
}

export const CrmTransferInbox: React.FC<CrmTransferInboxProps> = ({ onDecided, onNotice }) => {
  const [rows, setRows] = useState<CrmTransfer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [decidingId, setDecidingId] = useState<number | null>(null);
  const [rejectNote, setRejectNote] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const page = await listCrmTransferRequests();
      setRows(page.results);
    } catch (caught: unknown) {
      setRows([]);
      setError(caught instanceof Error ? caught.message : 'تعذر تحميل طلبات التحويل.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const decide = async (transfer: CrmTransfer, approve: boolean, note = '') => {
    try {
      await decideCrmTransferRequest(transfer.id, approve, note);
      onNotice(approve ? 'قُبل طلبُ التحويل وانتقل العميل.' : 'رُفض طلبُ التحويل.');
      setDecidingId(null);
      setRejectNote('');
      await load();
      onDecided();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'تعذر البتُّ في الطلب.');
    }
  };

  const pending = rows.filter((row) => row.status === 'pending');
  const settled = rows.filter((row) => row.status !== 'pending');

  return (
    <CcCard className="p-5" aria-label="طلبات تحويل العملاء">
      <CcSectionTitle
        title="طلبات التحويل"
        subtitle="ما طلبتَه من زملائك وما طُلب منك — والبتُّ لصاحب العميل أو المدير."
        badge={pending.length}
      />

      {loading ? (
        <div className="mt-4 space-y-3">
          <CcSkeleton count={2} />
        </div>
      ) : error ? (
        <p className="mt-4 text-sm text-rose-400" role="alert">{error}</p>
      ) : rows.length === 0 ? (
        <CcEmpty title="لا توجد طلبات تحويل تخصّك" className="mt-4 p-8" />
      ) : (
        <>
          {pending.length > 0 && (
            <ul className="mt-4 divide-y divide-cc-border">
              {pending.map((row) => (
                <li key={row.id} className="py-4 first:pt-0">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 font-bold text-cc-text">
                        <ArrowRightLeft className="h-4 w-4 text-amber-400" />
                        {row.from_employee?.name || 'المخزن المتاح'} → {row.to_employee?.name || 'غير محدد'}
                      </p>
                      <p className="mt-1 text-xs text-cc-text-muted">
                        العميل #{formatNumber(row.lead)} · {formatDateTimeValue(row.created_at)}
                      </p>
                      {row.reason && <p className="mt-1 text-sm text-cc-text">السبب: {row.reason}</p>}
                    </div>
                    {!row.can_decide ? (
                      <CcPill tone="neutral">
                        بانتظار قرار صاحب العميل
                      </CcPill>
                    ) : (
                      <div className="flex shrink-0 gap-2">
                        <button
                          type="button"
                          onClick={() => void decide(row, true)}
                          className="inline-flex items-center gap-1 rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition-colors"
                        >
                          <Check className="h-4 w-4" />
                          قبول
                        </button>
                        <button
                          type="button"
                          onClick={() => setDecidingId(decidingId === row.id ? null : row.id)}
                          className="inline-flex items-center gap-1 rounded-xl border border-rose-500/50 bg-rose-500/10 px-3 py-1.5 text-xs font-bold text-rose-300 hover:bg-rose-500/20 transition-colors"
                        >
                          <X className="h-4 w-4" />
                          رفض
                        </button>
                      </div>
                    )}
                  </div>

                  {/* سببُ الرفض حقلٌ في الصفحة لا `window.prompt`: الحوارُ الأصليُّ
                      للمتصفّح لا يُنسَّق ولا يُقرأ RTL، ونمطُ المستودع
                      `ToastProvider`/`ConfirmProvider` لا نوافذُ المتصفّح. */}
                  {decidingId === row.id && row.can_decide && (
                    <form
                      className="mt-3 flex flex-col gap-2 sm:flex-row"
                      onSubmit={(event) => { event.preventDefault(); void decide(row, false, rejectNote); }}
                    >
                      <label className="sr-only" htmlFor={`crm-reject-note-${row.id}`}>سبب الرفض</label>
                      <input
                        id={`crm-reject-note-${row.id}`}
                        value={rejectNote}
                        onChange={(event) => setRejectNote(event.target.value)}
                        placeholder="سبب الرفض (اختياري)"
                        className="min-w-0 flex-1 rounded-xl border border-cc-border bg-cc-bg/50 px-3 py-2 text-sm text-cc-text placeholder:text-cc-text-muted focus:border-cc-accent focus:outline-none"
                      />
                      <button type="submit" className="rounded-xl bg-rose-500 px-4 py-2 text-sm font-extrabold text-slate-950 hover:bg-rose-400 transition-colors">
                        تأكيد الرفض
                      </button>
                    </form>
                  )}
                </li>
              ))}
            </ul>
          )}

          {settled.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs font-bold text-cc-text-muted hover:text-cc-text">
                طلبات مُبتٌّ فيها ({formatNumber(settled.length)})
              </summary>
              <ul className="mt-3 space-y-2">
                {settled.map((row) => (
                  <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-cc-surface-2/60 border border-cc-border px-3 py-2 text-xs text-cc-text-muted">
                    <span>
                      العميل #{formatNumber(row.lead)} → {row.to_employee?.name || 'غير محدد'}
                      {row.decided_at ? ` · ${formatDateTimeValue(row.decided_at)}` : ''}
                    </span>
                    <CcPill tone={STATUS_TONES[row.status] || 'neutral'}>
                      {STATUS_LABELS[row.status] || row.status}
                    </CcPill>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </CcCard>
  );
};
