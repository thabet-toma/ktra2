import React, { useState } from 'react';

import {
  markObligationNotRequired,
  reopenObligation,
  setObligationAmount,
  setObligationClientPaid,
  submitObligation,
  type ObligationRow,
} from '../../services/accountingOfficeApi';
import type { SettingChoice } from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import {
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/**
 * ISSUE #275 — أفعالُ الالتزام الواحد، **مكوّنٌ واحدٌ لموضعين**: بطاقة «اليوم»
 * وسطرُ تبويب «الالتزامات والشغلات» في ملفّ الزبون. نسختان من نموذج «انقدّم»
 * ومن محرّر المبلغ كانتا تفترقان عند أول تعديلٍ في واحدةٍ منهما.
 *
 * **الخادمُ هو الحكم**: كلُّ فعلٍ ينجح يُنادي `onChanged` فتُعاد قراءةُ القائمة
 * والعدّادات من الخادم بدل تخمين الحالة في الواجهة. والفشلُ يُبلَّغ بنصّ الخادم.
 *
 * **والصلاحياتُ تُخفي ولا تحمي**: بلا `office.clients.write` لا أزرارَ كتابة،
 * وبلا `office.amounts.view` لا محرّرَ مبلغ (والخادم يردّ 403 على كلٍّ منها).
 * و«انقدّم» لا يُتراجَع عنه: زرُّه يغيب عن صفٍّ أُرسل، و«رجّعها» لـ«مش لازم» وحدها.
 */
export const OfficeObligationActions: React.FC<{
  obligation: ObligationRow;
  /** يومُ الطلب من الخادم — افتراضُ تاريخ التقديم، بلا قراءة ساعةٍ هنا. */
  day: string;
  directionChoices: readonly SettingChoice[];
  canWrite: boolean;
  canSeeAmounts: boolean;
  onChanged: () => void;
  onError: (message: string) => void;
  onOpenClient?: () => void;
}> = ({
  obligation,
  day,
  directionChoices,
  canWrite,
  canSeeAmounts,
  onChanged,
  onError,
  onOpenClient,
}) => {
  const [pending, setPending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitDraft, setSubmitDraft] = useState({ submitted_on: day, number: '' });
  const [amountOpen, setAmountOpen] = useState(false);
  const [amountDraft, setAmountDraft] = useState({
    amount: obligation.amount ?? '',
    direction: obligation.direction || (directionChoices[0]?.value ?? ''),
  });

  const submitted = obligation.status === 'submitted';
  const notRequired = obligation.status === 'not_required';

  const run = async (action: () => Promise<unknown>, failureMessage: string) => {
    setPending(true);
    try {
      await action();
      setSubmitting(false);
      setAmountOpen(false);
      onChanged();
    } catch (failure) {
      onError(humanizeThrown(failure, failureMessage));
    } finally {
      setPending(false);
    }
  };

  const openAmount = () => {
    // المسوّدةُ تُبنى من الصفّ الحالي في كل فتح — لا من قيمةٍ قديمةٍ محفوظة.
    setAmountDraft({
      amount: obligation.amount ?? '',
      direction: obligation.direction || (directionChoices[0]?.value ?? ''),
    });
    setAmountOpen(true);
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {canWrite && !submitted && !notRequired ? (
          <>
            <button
              type="button"
              disabled={pending}
              onClick={() => setSubmitting(true)}
              className={officePrimaryButtonClass}
            >
              انقدّم
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                run(
                  () => markObligationNotRequired(obligation.id),
                  'تعذّر تعليم الالتزام «مش لازم هالفترة».',
                )
              }
              className={officeSecondaryButtonClass}
            >
              مش لازم هالفترة
            </button>
          </>
        ) : null}
        {canWrite && notRequired ? (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(
              () => reopenObligation(obligation.id), 'تعذّر إرجاع الالتزام.',
            )}
            className={officeSecondaryButtonClass}
          >
            رجّعها
          </button>
        ) : null}
        {canWrite && canSeeAmounts && !submitted ? (
          <button type="button" onClick={openAmount} className={officeSecondaryButtonClass}>
            المبلغ
          </button>
        ) : null}
        {onOpenClient ? (
          <button type="button" onClick={onOpenClient} className={officeSecondaryButtonClass}>
            افتح الزبون
          </button>
        ) : null}
        {/* «الزبون دفع» ليس مبلغاً: خادمُه يقبله في كلّ حالةٍ وبمفتاح الكتابة
            وحده، فمكانُه هنا لا داخل لوحة المبلغ (المخفيّة عن مُقدَّمٍ أو عن
            عضوٍ لا يرى المبالغ). */}
        {canWrite ? (
          <label className="inline-flex items-center gap-2 text-[11.5px] font-medium text-slate-700 dark:text-slate-200">
            <input
              type="checkbox"
              checked={obligation.client_paid}
              disabled={pending}
              onChange={(event) =>
                run(
                  () => setObligationClientPaid(obligation.id, event.target.checked),
                  'تعذّر تحديث «الزبون دفع».',
                )
              }
              className="size-4 rounded border-slate-300"
            />
            الزبون دفع
          </label>
        ) : null}
      </div>

      {submitting ? (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            تاريخ التقديم
            <input
              type="date"
              value={submitDraft.submitted_on}
              max={day}
              onChange={(event) =>
                setSubmitDraft({ ...submitDraft, submitted_on: event.target.value })
              }
              className={`${officeInputClass} mt-1 block`}
            />
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            رقم التقديم (اختياري)
            <input
              value={submitDraft.number}
              onChange={(event) =>
                setSubmitDraft({ ...submitDraft, number: event.target.value })
              }
              className={`${officeInputClass} mt-1 block w-36`}
            />
          </label>
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              run(
                () => submitObligation(obligation.id, {
                  submitted_on: submitDraft.submitted_on || undefined,
                  number: submitDraft.number.trim() || undefined,
                }),
                'تعذّر تسجيل التقديم.',
              )
            }
            className={officePrimaryButtonClass}
          >
            سجّل التقديم
          </button>
          <button
            type="button"
            onClick={() => setSubmitting(false)}
            className={officeSecondaryButtonClass}
          >
            إلغاء
          </button>
        </div>
      ) : null}

      {amountOpen && canSeeAmounts ? (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            المبلغ
            <input
              inputMode="decimal"
              value={amountDraft.amount}
              onChange={(event) =>
                setAmountDraft({ ...amountDraft, amount: event.target.value })
              }
              className={`${officeInputClass} mt-1 block w-28 tabular-nums`}
            />
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الاتجاه
            <select
              value={amountDraft.direction}
              onChange={(event) =>
                setAmountDraft({ ...amountDraft, direction: event.target.value })
              }
              className={`${officeInputClass} mt-1 block`}
            >
              {directionChoices.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              run(
                () => setObligationAmount(obligation.id, {
                  amount: amountDraft.amount.trim() || null,
                  direction: amountDraft.amount.trim() ? amountDraft.direction : '',
                }),
                'تعذّر حفظ المبلغ.',
              )
            }
            className={officePrimaryButtonClass}
          >
            احفظ المبلغ
          </button>
          <button
            type="button"
            onClick={() => setAmountOpen(false)}
            className={officeSecondaryButtonClass}
          >
            إلغاء
          </button>
        </div>
      ) : null}
    </div>
  );
};
