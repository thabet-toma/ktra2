import React, { useCallback, useEffect, useState } from 'react';

import {
  confirmAppointment,
  createAppointment,
  listClientAppointments,
  type ClientAppointmentsPayload,
} from '../../services/accountingOfficeApi';
import { officeWhatsappLink, type SettingChoice } from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import { useToast } from '../../contexts/ToastContext';
import { OfficeAppointmentCard } from './OfficeAppointmentCard';
import {
  OfficeCard,
  OfficeEmpty,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/**
 * ISSUE #281 — تبويبُ «المواعيد» في ملفّ الزبون: الحجزُ وما حُجز.
 *
 * **الزبونُ لا يحجز بنفسه**: الموظّفُ يُسجّل الموعد من هنا (ومن التقويم)، بالنوع
 * والوقت — **و«ابعت تأكيد» معلَّمٌ افتراضياً**: الحجزُ بلا رسالةٍ يترك الزبونَ
 * يعرف موعده من الذاكرة. والتأكيدُ يُسجَّل صفَّ تذكيرٍ خادمياً ويعود نصُّه، فتُفتح
 * به محادثةُ واتساب من هنا مباشرةً (`officeWhatsappLink` وحدها تبني الرابط).
 *
 * والقائمةُ بالحالة نفسها لا بمرشِّح: ما صار وما أُلغي يبقيان ظاهرين بتاريخهما —
 * «ولا حذف: الإلغاءُ يكتب حالة».
 */
export const OfficeClientAppointments: React.FC<{
  clientId: number;
  canWrite: boolean;
  /** نظامُ الزبون — يبنى منه رابطُ الواتساب في البطاقة وفي تأكيد الحجز. */
  taxSystem: string | null;
}> = ({ clientId, canWrite, taxSystem }) => {
  const toast = useToast();
  const [payload, setPayload] = useState<ClientAppointmentsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [kind, setKind] = useState('');
  const [slot, setSlot] = useState('');
  const [note, setNote] = useState('');
  const [sendConfirmation, setSendConfirmation] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<{ body: string; link: string | null } | null>(
    null,
  );
  const [refreshToken, setRefreshToken] = useState(0);

  const kinds: SettingChoice[] = payload?.kind_choices ?? [];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    listClientAppointments(clientId)
      .then((data) => {
        if (!cancelled) {
          setPayload(data);
          setKind((current) => current || data.kind_choices[0]?.value || '');
        }
      })
      .catch((failure) => {
        if (!cancelled) {
          setPayload(null);
          setError(humanizeThrown(failure, 'تعذّر تحميل مواعيد الزبون.'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, refreshToken]);

  const reload = useCallback(() => setRefreshToken((token) => token + 1), []);

  const book = useCallback(async () => {
    if (!slot) {
      toast('اختر تاريخ الموعد ووقته.', 'error');
      return;
    }
    setBusy(true);
    setConfirmation(null);
    try {
      const created = await createAppointment({
        client_id: clientId,
        kind,
        scheduled_at: slot,
        note: note.trim(),
      });
      setSlot('');
      setNote('');
      if (sendConfirmation) {
        // التأكيدُ فعلٌ ثانٍ: فشلُه لا يُلغي الحجزَ — الحجزُ تمّ والسطرُ ظاهر.
        try {
          const sent = await confirmAppointment(created.id);
          setConfirmation({
            body: sent.body,
            link: officeWhatsappLink(sent.phone, taxSystem, sent.body),
          });
        } catch (failure) {
          toast(humanizeThrown(failure, 'حُجز الموعد ولم يُسجَّل التأكيد.'), 'error');
        }
      }
      toast('انحجز الموعد.', 'success');
      reload();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حجز الموعد.'), 'error');
    } finally {
      setBusy(false);
    }
  }, [clientId, kind, note, reload, sendConfirmation, slot, taxSystem, toast]);

  return (
    <div className="space-y-4">
      {canWrite ? (
        <OfficeCard title="احجز موعداً">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-[11px] text-slate-600 dark:text-slate-300">
              النوع
              <select
                value={kind}
                onChange={(event) => setKind(event.target.value)}
                className={officeInputClass}
              >
                {kinds.map((choice) => (
                  <option key={choice.value} value={choice.value}>
                    {choice.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[11px] text-slate-600 dark:text-slate-300">
              الوقت
              <input
                type="datetime-local"
                value={slot}
                onChange={(event) => setSlot(event.target.value)}
                className={officeInputClass}
              />
            </label>
            <label className="flex min-w-[180px] flex-1 flex-col gap-1 text-[11px] text-slate-600 dark:text-slate-300">
              ملاحظة
              <input
                type="text"
                value={note}
                maxLength={300}
                onChange={(event) => setNote(event.target.value)}
                placeholder="اتفاق التوقيع، أوراق ناقصة…"
                className={officeInputClass}
              />
            </label>
            <label className="flex items-center gap-1.5 pb-2 text-[11.5px] font-medium text-slate-700 dark:text-slate-200">
              <input
                type="checkbox"
                checked={sendConfirmation}
                onChange={(event) => setSendConfirmation(event.target.checked)}
              />
              ابعت تأكيد
            </label>
            <button
              type="button"
              onClick={book}
              disabled={busy}
              className={officePrimaryButtonClass}
            >
              احجز
            </button>
          </div>

          {confirmation ? (
            <div className="mt-3 rounded-lg border border-teal-200 bg-teal-50 p-2.5 dark:border-teal-900 dark:bg-teal-950/40">
              <p className="whitespace-pre-line text-[11.5px] text-teal-900 dark:text-teal-100">
                {confirmation.body}
              </p>
              {confirmation.link ? (
                <a
                  href={confirmation.link}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block rounded-lg bg-teal-700 px-3 py-1.5 text-[11.5px] font-semibold text-white hover:bg-teal-800"
                >
                  افتح واتساب
                </a>
              ) : (
                <p className="mt-1 text-[10.5px] text-teal-800 dark:text-teal-200">
                  لا رابطَ واتساب — رقمُ الجهة أرضيٌّ ونظامُ الزبون غير معروف.
                </p>
              )}
            </div>
          ) : null}
        </OfficeCard>
      ) : null}

      {error ? (
        <div>
          <p className="text-[12px] font-medium text-rose-600 dark:text-rose-400">{error}</p>
          <button type="button" onClick={reload} className={`mt-2 ${officeSecondaryButtonClass}`}>
            أعد المحاولة
          </button>
        </div>
      ) : loading && payload === null ? (
        <p className="text-[11.5px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>
      ) : !payload || payload.rows.length === 0 ? (
        <OfficeEmpty
          title="لا مواعيد لهذا الزبون"
          hint="احجز موعداً من الأعلى، أو من التقويم — والزبونُ لا يحجز بنفسه."
        />
      ) : (
        <div className="space-y-2">
          {payload.rows.map((row) => (
            <OfficeAppointmentCard
              key={row.id}
              appointment={row}
              canWrite={canWrite}
              taxSystem={taxSystem}
              onChanged={reload}
            />
          ))}
        </div>
      )}
    </div>
  );
};
