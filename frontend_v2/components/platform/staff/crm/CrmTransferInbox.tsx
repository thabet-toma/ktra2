import React, { useCallback, useEffect, useState } from 'react';
import { ArrowRightLeft, Check, Inbox, X } from 'lucide-react';

import {
  decideCrmTransferRequest,
  listCrmTransferRequests,
  type CrmTransfer,
} from '../../../../services/platformCrmApi';
import { formatDateTimeValue } from '../../../../utils/formatDate';
import { formatNumber } from '../../../../utils/formatNumber';

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
 */
const STATUS_LABELS: Record<string, string> = {
  pending: 'بانتظار القرار',
  approved: 'مقبول',
  rejected: 'مرفوض',
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
    <section
      className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-5 shadow-lg shadow-black/30"
      aria-label="طلبات تحويل العملاء"
    >
      <h2 className="flex items-center gap-2 font-extrabold text-[var(--staff-text)]">
        <Inbox className="h-5 w-5 text-cyan-300" />
        طلبات التحويل
      </h2>
      <p className="mt-1 text-sm text-[var(--staff-muted)]">
        ما طلبتَه من زملائك وما طُلب منك — والبتُّ لصاحب العميل أو المدير.
      </p>

      {loading ? (
        <p className="mt-4 text-sm text-[var(--staff-muted)]" role="status">جارٍ تحميل طلبات التحويل...</p>
      ) : error ? (
        <p className="mt-4 text-sm text-rose-300" role="alert">{error}</p>
      ) : rows.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--staff-muted)]">لا توجد طلبات تحويل تخصّك.</p>
      ) : (
        <>
          {pending.length > 0 && (
            <ul className="mt-4 divide-y divide-[var(--staff-line)]">
              {pending.map((row) => (
                <li key={row.id} className="py-4 first:pt-0">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 font-bold text-[var(--staff-text)]">
                        <ArrowRightLeft className="h-4 w-4 text-amber-300" />
                        {row.from_employee?.name || 'المخزن المتاح'} → {row.to_employee?.name || 'غير محدد'}
                      </p>
                      <p className="mt-1 text-sm text-[var(--staff-muted)]">
                        العميل #{formatNumber(row.lead)} · {formatDateTimeValue(row.created_at)}
                      </p>
                      {row.reason && <p className="mt-1 text-sm text-[var(--staff-text)]">السبب: {row.reason}</p>}
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <button
                        type="button"
                        onClick={() => void decide(row, true)}
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-400 px-3 py-2 text-sm font-bold text-slate-950"
                      >
                        <Check className="h-4 w-4" />
                        قبول
                      </button>
                      <button
                        type="button"
                        onClick={() => setDecidingId(decidingId === row.id ? null : row.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-rose-400/50 px-3 py-2 text-sm font-bold text-rose-300"
                      >
                        <X className="h-4 w-4" />
                        رفض
                      </button>
                    </div>
                  </div>

                  {/* سببُ الرفض حقلٌ في الصفحة لا `window.prompt`: الحوارُ الأصليُّ
                      للمتصفّح لا يُنسَّق ولا يُقرأ RTL، ونمطُ المستودع
                      `ToastProvider`/`ConfirmProvider` لا نوافذُ المتصفّح. */}
                  {decidingId === row.id && (
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
                        className="min-w-0 flex-1 rounded-lg border border-[var(--staff-line)] bg-black/15 px-3 py-2 text-sm text-[var(--staff-text)]"
                      />
                      <button type="submit" className="rounded-lg bg-rose-400 px-4 py-2 text-sm font-extrabold text-slate-950">
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
              <summary className="cursor-pointer text-sm font-bold text-[var(--staff-muted)]">
                طلبات مُبتٌّ فيها ({formatNumber(settled.length)})
              </summary>
              <ul className="mt-3 space-y-2">
                {settled.map((row) => (
                  <li key={row.id} className="rounded-lg bg-black/15 px-3 py-2 text-sm text-[var(--staff-muted)]">
                    العميل #{formatNumber(row.lead)} → {row.to_employee?.name || 'غير محدد'} ·{' '}
                    {STATUS_LABELS[row.status] || row.status}
                    {row.decided_at ? ` · ${formatDateTimeValue(row.decided_at)}` : ''}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
};
