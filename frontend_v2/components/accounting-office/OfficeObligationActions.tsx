import React, { useState } from 'react';

import {
  clearObligationExtension,
  computeObligationAmount,
  confirmObligationAmount,
  extendObligation,
  markObligationNotRequired,
  reopenObligation,
  setObligationAmount,
  setObligationClientPaid,
  submitObligation,
  type ObligationComputedDetails,
  type ObligationRow,
} from '../../services/accountingOfficeApi';
import type { SettingChoice } from '../../utils/accountingOffice';
import {
  computedAmountConfirmed,
  defaultExtensionDate,
  formatOfficeAmount,
} from '../../utils/accountingOffice';
import { formatDateValue } from '../../utils/formatDate';
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
 *
 * **و«احسب من الدفتر / أكّد» فعلان لا فعل** (#287/٤): الأول يقرأ الدفترَ ويعرض
 * تفصيلَه (مبيعاتٌ ومدخلاتٌ معترفٌ بها وغيرُ مخصومة، وعدُّ أسطرٍ «راجع» لم
 * تُخصم ضريبتُها) ويحفظ `computed_amount` بلا مساسٍ بالمبلغ؛ والثاني يجعل
 * المحسوبَ هو المعدَّل. وإعدادُ الحساب مطفأٌ في الخادم يردّ 400 برسالته.
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
  // #277: «مدّد» — تاريخٌ وملاحظة، وافتراضُ التاريخ يومٌ بعد الموعد الساري.
  const [extendOpen, setExtendOpen] = useState(false);
  const [extendDraft, setExtendDraft] = useState({ until: '', note: '' });
  // #287/٤: تفصيلُ «احسب من الدفتر» — يُعرض قبل «أكّد» لا بعده.
  const [computing, setComputing] = useState(false);
  const [computed, setComputed] = useState<ObligationComputedDetails | null>(null);

  const submitted = obligation.status === 'submitted';
  const notRequired = obligation.status === 'not_required';

  const run = async (action: () => Promise<unknown>, failureMessage: string) => {
    setPending(true);
    try {
      await action();
      setSubmitting(false);
      setAmountOpen(false);
      setExtendOpen(false);
      // التفصيلُ المحسوبُ يخصّ مبلغاً قد لا يكون هو المبلغَ الآن: فعلٌ نجح
      // يمسحه فلا يبقى ملخّصٌ ولا إعلانُ أسطرٍ «راجع» على رقمٍ غيره.
      setComputed(null);
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

  const openExtend = () => {
    // افتراضُ التاريخ **ثلاثون يوماً بعد الموعد الساري**: التمديدُ إلى تاريخٍ
    // ليس بعده يرفضه الخادم، والموعدُ الساري نفسُه يرفضه كذلك.
    setExtendDraft({ until: defaultExtensionDate(obligation.due_date), note: '' });
    setExtendOpen(true);
  };

  /**
   * «احسب من الدفتر» (#287/٤) — فعلٌ لا يُغلق لوحةً: ردُّه تفصيلٌ يُقرأ.
   *
   * ولا يستعمل `run` لأنه يحتاج الردَّ نفسه؛ ويأخذ `pending` معه كي لا يرسل
   * الموظفُ «انقدّم» في نافذةِ الحساب (الخادمُ يرفض حسابَ ما قُدّم، والحسابُ
   * يُحفظ في السطر — فالفعلان يتزاحمان على صفٍّ واحد).
   */
  const compute = async () => {
    setComputing(true);
    setPending(true);
    try {
      const row = await computeObligationAmount(obligation.id);
      setComputed(row.computed_details);
      onChanged();
    } catch (failure) {
      onError(humanizeThrown(failure, 'تعذّر حساب المبلغ من الدفتر.'));
    } finally {
      setComputing(false);
      setPending(false);
    }
  };

  // «أكّد» لا يُفتح إلا بتفصيلٍ مقروءٍ في هذه الجلسة: رقمُ ضريبةٍ يُؤكَّد بلا
  // رؤية `review_lines` ليس تأكيداً — ولذلك أُعيد الحسابُ بعد كل تحميلٍ للصفحة.
  const canConfirmComputed =
    computed !== null && !computedAmountConfirmed(obligation);

  const confirmComputed = () =>
    run(() => confirmObligationAmount(obligation.id), 'تعذّر تأكيد المبلغ المحسوب.');

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
        {/* #287/٤: «احسب» يقرأ الدفتر ويحفظ `computed_amount` بلا مساسٍ بالمبلغ،
            و«أكّد» يجعله المعدَّل — ولا يُفتح قبل أن يوجد محسوب. */}
        {canWrite && canSeeAmounts && !submitted ? (
          <>
            <button
              type="button"
              disabled={pending || computing}
              onClick={() => { void compute(); }}
              className={officeSecondaryButtonClass}
            >
              {computing ? '…' : 'احسب من الدفتر'}
            </button>
            <button
              type="button"
              disabled={pending || !canConfirmComputed}
              onClick={() => { void confirmComputed(); }}
              className={officeSecondaryButtonClass}
            >
              أكّد المحسوب
            </button>
          </>
        ) : null}
        {/* #277: التمديدُ على الموعد المنتظِر وحده — يُسكِت الأحمرَ إلى موعده،
            ويُلغى فيرجع الفعليُّ كما كان. */}
        {canWrite && !submitted && !notRequired ? (
          <button type="button" disabled={pending} onClick={openExtend} className={officeSecondaryButtonClass}>
            مدّد
          </button>
        ) : null}
        {canWrite && !submitted && obligation.extended_to ? (
          <button
            type="button"
            disabled={pending}
            onClick={() => run(
              () => clearObligationExtension(obligation.id), 'تعذّر إلغاء التمديد.',
            )}
            className={officeSecondaryButtonClass}
          >
            ألغِ التمديد
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

      {obligation.computed_amount && !submitted ? (
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          المحسوبُ من الدفتر: {formatOfficeAmount(obligation.computed_amount)}
          {computedAmountConfirmed(obligation)
            ? ' — وهو المبلغُ المعدَّل حالياً.'
            : ' — «احسب من الدفتر» يعرض تفصيله، ثم «أكّد المحسوب» يجعله المبلغَ.'}
        </p>
      ) : null}

      {computed && !submitted ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-2 text-[11px] dark:border-slate-700 dark:bg-slate-800/40">
          <p className="font-medium text-slate-700 dark:text-slate-200">
            من الدفتر {formatDateValue(computed.from)} ← {formatDateValue(computed.to)}
          </p>
          <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-600 dark:text-slate-300 sm:grid-cols-3">
            <div className="flex justify-between gap-2">
              <dt>ضريبة المبيعات</dt>
              <dd className="tabular-nums">{formatOfficeAmount(computed.sales_tax)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>ضريبة المدخلات</dt>
              <dd className="tabular-nums">{formatOfficeAmount(computed.input_tax)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>المعترف بها</dt>
              <dd className="tabular-nums">{formatOfficeAmount(computed.recognised_input)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>غير المخصوم (كلفة)</dt>
              <dd className="tabular-nums">{formatOfficeAmount(computed.non_deductible)}</dd>
            </div>
            <div className="flex justify-between gap-2 font-semibold text-slate-700 dark:text-slate-200">
              <dt>المستحقّ</dt>
              <dd className="tabular-nums">{formatOfficeAmount(computed.vat_due)}</dd>
            </div>
          </dl>
          {/* أسطرُ «راجع» تُعلَن **قبل** التأكيد: ضريبتُها لم تُخصم، فالرقمُ ناقص. */}
          {computed.review_lines > 0 ? (
            <p className="mt-1 font-medium text-amber-800 dark:text-amber-300">
              {computed.review_lines} سطر بنسبةٍ غير مؤكَّدة: لم تُخصم ضريبتُه بعد —
              والرقمُ ناقصٌ حتى يؤكّد المكتبُ نسبتَه من لائحة النسب.
            </p>
          ) : null}
        </div>
      ) : null}

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

      {extendOpen ? (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            مدّد حتى
            <input
              type="date"
              value={extendDraft.until}
              onChange={(event) =>
                setExtendDraft({ ...extendDraft, until: event.target.value })
              }
              className={`${officeInputClass} mt-1 block`}
            />
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الملاحظة (مطلوبة)
            <input
              value={extendDraft.note}
              onChange={(event) =>
                setExtendDraft({ ...extendDraft, note: event.target.value })
              }
              className={`${officeInputClass} mt-1 block w-56`}
            />
          </label>
          <button
            type="button"
            disabled={pending || !extendDraft.until || !extendDraft.note.trim()}
            onClick={() => run(
              () => extendObligation(obligation.id, {
                until: extendDraft.until,
                note: extendDraft.note.trim(),
              }),
              'تعذّر تمديد الالتزام.',
            )}
            className={officePrimaryButtonClass}
          >
            سجّل التمديد
          </button>
          <button
            type="button"
            onClick={() => setExtendOpen(false)}
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
