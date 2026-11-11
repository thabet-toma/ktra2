import React, { useCallback, useState } from 'react';

import {
  cancelAppointment,
  completeAppointment,
  confirmAppointment,
  rescheduleAppointment,
} from '../../services/accountingOfficeApi';
import {
  appointmentSlotValue,
  appointmentStatusClass,
  isOpenAppointment,
  officeAppointmentAnchorId,
  officeWhatsappLink,
  type OfficeAppointmentRow,
} from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import { formatDateLocalized } from '../../utils/formatDate';
import { useToast } from '../../contexts/ToastContext';
import {
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/**
 * ISSUE #281 — بطاقةُ موعدٍ واحدة: وقتُه وحالتُه وأفعالُه.
 *
 * **الأفعالُ أربعة، وثلاثةٌ منها لا تظهر إلّا على المحجوز** (`isOpenAppointment`):
 * «ابعت تأكيد» يُسجَّل صفُّ تذكيرٍ خادمياً ويعود بالنصّ، و«أجّل» يُزحزح الوقتَ على
 * الصفّ نفسه، و«ألغِ» يكتب حالةً ولا يحذف، و«صار» يُثبت أنّ الزيارة وقعت.
 *
 * **والرابطُ يُبنى في `officeWhatsappLink` وحدها**: مفتاحُ الدولة من نظام الزبون
 * (`tax_system` في السطر)، وإن غاب فالبطاقةُ تعرض النصَّ بلا زرٍّ يفتح محادثةً
 * مع رقمٍ آخر. والخادمُ هو من يقرّر النصَّ — لا نسخةَ في الواجهة.
 */
export const OfficeAppointmentCard: React.FC<{
  appointment: OfficeAppointmentRow;
  canWrite: boolean;
  /** `null` تعني «ابطُ لا رابط» — الرقمُ الأرضيُّ لا يُصاغ بلا نظام. */
  taxSystem?: string | null;
  showClient?: boolean;
  onChanged: () => void;
}> = ({ appointment, canWrite, taxSystem = null, showClient = false, onChanged }) => {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [moving, setMoving] = useState(false);
  const [slot, setSlot] = useState('');
  const [confirmation, setConfirmation] = useState<{ body: string; link: string | null } | null>(
    null,
  );
  const open = isOpenAppointment(appointment);
  const system = (appointment.tax_system ?? taxSystem ?? null) as string | null;

  const act = useCallback(
    async (run: () => Promise<void>, done: string, failed: string) => {
      setBusy(true);
      try {
        await run();
        onChanged();
        toast(done, 'success');
      } catch (failure) {
        toast(humanizeThrown(failure, failed), 'error');
      } finally {
        setBusy(false);
      }
    },
    [onChanged, toast],
  );

  const confirm = () =>
    act(
      async () => {
        const result = await confirmAppointment(appointment.id);
        setConfirmation({
          body: result.body,
          link: officeWhatsappLink(result.phone, system, result.body),
        });
      },
      'تسجّل التأكيد — الرسالةُ جاهزة.',
      'تعذّر تسجيل التأكيد.',
    );

  const cancel = () =>
    act(
      () => cancelAppointment(appointment.id).then(() => undefined),
      'انلغى الموعد — وبقي في السجلّ.',
      'تعذّر إلغاء الموعد.',
    );

  const markDone = () =>
    act(
      () => completeAppointment(appointment.id).then(() => undefined),
      'تسجّل أنّ الموعد صار.',
      'تعذّر تسجيل الموعد.',
    );

  const startMove = () => {
    if (moving) {
      setMoving(false);
      return;
    }
    setConfirmation(null);
    setSlot(appointmentSlotValue(appointment.scheduled_at));
    setMoving(true);
  };

  const saveMove = () => {
    if (!slot) {
      toast('اختر تاريخ الموعد ووقته.', 'error');
      return;
    }
    act(
      () => rescheduleAppointment(appointment.id, slot).then(() => {
        setMoving(false);
      }),
      'انزاح الموعد — الصفُّ نفسه.',
      'تعذّر تأجيل الموعد.',
    );
  };

  return (
    <article
      id={officeAppointmentAnchorId(appointment.id)}
      className="rounded-xl border border-slate-200 bg-white p-3.5 dark:border-slate-700 dark:bg-slate-900"
    >
      <header className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          {showClient ? (
            <h3 className="truncate text-[13px] font-semibold text-slate-900 dark:text-slate-100">
              {appointment.client.name}
            </h3>
          ) : null}
          <p className="text-[12px] font-semibold tabular-nums text-slate-800 dark:text-slate-200">
            {formatDateLocalized(appointment.day)} · {appointment.time}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
            {appointment.kind_label}
            {appointment.confirmed_at ? ' · التأكيد مسجَّل' : ''}
            {appointment.created_by ? ` · سجّله ${appointment.created_by.name}` : ''}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${appointmentStatusClass(appointment.status)}`}
        >
          {appointment.status_label}
        </span>
      </header>

      {appointment.note ? (
        <p className="mt-1.5 text-[11.5px] text-slate-600 dark:text-slate-300">
          {appointment.note}
        </p>
      ) : null}

      {open && canWrite ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={confirm}
            disabled={busy}
            className={officePrimaryButtonClass}
          >
            ابعت تأكيد
          </button>
          <button
            type="button"
            onClick={startMove}
            disabled={busy}
            className={officeSecondaryButtonClass}
          >
            {moving ? 'إلغاء التأجيل' : 'أجّل'}
          </button>
          <button
            type="button"
            onClick={markDone}
            disabled={busy}
            className={officeSecondaryButtonClass}
          >
            صار
          </button>
          <button
            type="button"
            onClick={cancel}
            disabled={busy}
            className={officeSecondaryButtonClass}
          >
            ألغِ
          </button>
        </div>
      ) : null}

      {moving ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <input
            type="datetime-local"
            value={slot}
            onChange={(event) => setSlot(event.target.value)}
            className={officeInputClass}
            aria-label="وقت الموعد الجديد"
          />
          <button
            type="button"
            onClick={saveMove}
            disabled={busy || !slot}
            className={officePrimaryButtonClass}
          >
            احفظ الوقت
          </button>
        </div>
      ) : null}

      {confirmation ? (
        <div className="mt-2 rounded-lg border border-teal-200 bg-teal-50 p-2.5 dark:border-teal-900 dark:bg-teal-950/40">
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
    </article>
  );
};
