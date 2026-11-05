import React from 'react';

import type { ObligationRow, SettingChoice } from '../../utils/accountingOffice';
import {
  badgeLabelOf,
  documentDocsText,
  obligationAmountText,
  obligationBadgeClass,
  obligationExtensionText,
  obligationOriginLabel,
  obligationStatusClass,
  platformOfficialText,
  shortIsoDate,
  statusLabelOf,
} from '../../utils/accountingOffice';
import { OfficeObligationActions } from './OfficeObligationActions';

/**
 * ISSUE #275 — سطرُ الالتزام الواحد، **مكوّنٌ واحدٌ لموضعين**: بطاقة «اليوم»
 * وسطرُ تبويب «الالتزامات والشغلات» في ملفّ الزبون. كان رسمُ السطر (الأصلُ
 * و«تقديري» والشاراتُ والتواريخ وكتلةُ المبلغ والتحذيرات) مستنسخاً فيهما،
 * فتفترق نسختان عند أول تعديلٍ في واحدة.
 *
 * **والفرقُ بين الموضعين مُعلَنٌ بوسائط لا بنسخة**: «اليوم» يُظهر اسمَ الزبون
 * (وزرّه يفتح ملفّه) والفترةَ والمسؤولَ وتواريخَ «داخلي/رسمي»؛ وملفُّ الزبون
 * يُظهر حالةَ الالتزام المخزَّنة وتواريخَ «رسمي/فعلي»، والفترةُ في ترويسة
 * الشغلة فوقه. والتسمياتُ كلُّها من الخادم (`origin_label` · `status_label` ·
 * `badges[].label` · `direction_label`) فلا جدولَ محليّاً.
 */
export const OfficeObligationRow: React.FC<{
  obligation: ObligationRow;
  /** يومُ الطلب من الخادم — تُحسب عنه الشاراتُ ويُعرض التاريخُ القصير. */
  day: string;
  directionChoices: readonly SettingChoice[];
  canWrite: boolean;
  canSeeAmounts: boolean;
  onChanged: () => void;
  onError: (message: string) => void;
  /** «اليوم»: اسمُ الزبون زرّاً يفتح ملفّه، وتحته «الاسم — الفترة». */
  showClient?: boolean;
  onOpenClient?: () => void;
  /** ملفُّ الزبون: شارةُ الحالة المخزَّنة (و«اليوم» يعرض المنتظِر وحده). */
  showStatus?: boolean;
  /** هل يُعرض اسمُ المسؤول الفعليّ؟ يُخفى في «شخص واحد». */
  showAssignee?: boolean;
  /** «داخلي/رسمي» في «اليوم»، و«رسمي/فعلي» في ملفّ الزبون. */
  dates?: 'internal-official' | 'official-actual';
}> = ({
  obligation,
  day,
  directionChoices,
  canWrite,
  canSeeAmounts,
  onChanged,
  onError,
  showClient = false,
  onOpenClient,
  showStatus = false,
  showAssignee = false,
  dates = 'internal-official',
}) => {
  // النصوصُ المشتقّة تُحسب **مرّةً** للسطر: كلُّ نداءٍ يمرّ على عدّة حقول.
  const originLabel = obligationOriginLabel(obligation);
  const extensionText = obligationExtensionText(obligation);
  const platformText = platformOfficialText(obligation);
  return (
  <div className="space-y-2">
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          {showClient ? (
            <button
              type="button"
              onClick={onOpenClient}
              className="max-w-full truncate text-[13px] font-bold text-slate-900 hover:underline dark:text-slate-100"
            >
              {obligation.client.name}
            </button>
          ) : (
            <span className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
              {obligation.name}
            </span>
          )}
          {/* #277: «من المكتب» و«حدث» وحدَهما — الرسميُّ أصلٌ افتراضيّ لا شارةَ له،
              ولونُهما محايدٌ فلا يلتبسان بالأحمر ولا بالأصفر. */}
          {originLabel ? (
            <span className="rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {originLabel}
            </span>
          ) : null}
          {showStatus ? (
            <span
              className={`rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${obligationStatusClass(obligation.status)}`}
            >
              {statusLabelOf(obligation)}
            </span>
          ) : null}
          {obligation.badges.map((badge) => (
            <span
              key={badge.key}
              className={`rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${obligationBadgeClass(badge.key)}`}
            >
              {badgeLabelOf(badge)}
            </span>
          ))}
          {obligation.estimated ? (
            <span
              title="سنة بلا لائحةٍ منشورة — الموعد مقيسٌ على آخر لائحة"
              className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900 dark:bg-amber-950/50 dark:text-amber-200"
            >
              تقديري
            </span>
          ) : null}
          {/* #278: عدّادُ الأوراق «وصل 3/5» — نصوصُ الخادم وحده، ويغيب بلا صفوف. */}
          {documentDocsText(obligation.docs) ? (
            <span className="text-[10px] font-semibold tabular-nums text-slate-500 dark:text-slate-400">
              {documentDocsText(obligation.docs)}
            </span>
          ) : null}
        </div>

        {showClient ? (
          <p className="mt-1 text-[12.5px] font-semibold text-slate-700 dark:text-slate-200">
            {obligation.name} — {obligation.period_label}
          </p>
        ) : null}

        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          {dates === 'internal-official' ? (
            <>
              <span className="text-[10.5px] tabular-nums text-slate-500 dark:text-slate-400">
                داخلي {shortIsoDate(obligation.internal_deadline)}
              </span>
              <span className="text-[10.5px] tabular-nums text-slate-500 dark:text-slate-400">
                رسمي {shortIsoDate(obligation.official_date)}
              </span>
            </>
          ) : (
            <>
              <span className="text-[10.5px] tabular-nums text-slate-500 dark:text-slate-400">
                رسمي {shortIsoDate(obligation.official_date)}
              </span>
              <span className="text-[10.5px] tabular-nums text-slate-500 dark:text-slate-400">
                فعلي {shortIsoDate(obligation.actual_deadline)}
              </span>
            </>
          )}
          {showAssignee && obligation.task.assignee ? (
            <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
              {obligation.task.assignee.name}
            </span>
          ) : null}
        </div>

        {/* #277: التمديد والموعدُ الرسميّ للمنصّة يظهران بجانب التاريخ الساريّ —
            والملاحظةُ نصُّ المكتب كما كتبها. */}
        {extensionText ? (
          <p className="mt-1 text-[10.5px] font-semibold text-slate-600 dark:text-slate-300">
            {extensionText}
          </p>
        ) : null}
        {platformText ? (
          <p className="mt-1 text-[10.5px] font-medium text-slate-500 dark:text-slate-400">
            {platformText}
          </p>
        ) : null}

        {obligation.warnings.map((warning) => (
          <p
            key={warning}
            className="mt-1 text-[10.5px] font-medium text-amber-800 dark:text-amber-300"
          >
            ⚠ {warning}
          </p>
        ))}
      </div>

      <div className="shrink-0 text-end">
        <span className="block text-[12.5px] font-bold tabular-nums text-slate-800 dark:text-slate-100">
          {obligationAmountText(obligation)}
        </span>
        {obligation.client_paid ? (
          <span className="mt-0.5 block text-[10px] font-semibold text-emerald-700 dark:text-emerald-300">
            الزبون دفع
          </span>
        ) : null}
      </div>
    </div>

    <OfficeObligationActions
      obligation={obligation}
      day={day}
      directionChoices={directionChoices}
      canWrite={canWrite}
      canSeeAmounts={canSeeAmounts}
      onChanged={onChanged}
      onError={onError}
      onOpenClient={onOpenClient}
    />
  </div>
);
};
