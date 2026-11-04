import React, { useCallback, useEffect, useState } from 'react';

import {
  clearDeadlineRuleOverride,
  keepDeadlineRuleOverride,
  listDeadlineRules,
  setDeadlineRuleOverride,
  type DeadlineRuleRow,
} from '../../services/accountingOfficeApi';
import {
  deadlineRuleDescription,
  overriddenRuleInput,
  shortIsoDate,
} from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/** مفتاحُ الصفّ **بالإصدار** لا بالكود: الكودُ يتكرّر لكل سنة. */
const ruleRowKey = (row: DeadlineRuleRow) => `${row.rule_code}-${row.year}-${row.version}`;

/** مسوّدةُ تعديل سطر: الحقلُ الفارغ يعني «كالمنصة». */
interface OverrideDraft {
  /** صفُّ العرض الذي فُتح عليه النموذج — الكودُ وحده يفتحه تحت كل سنة. */
  rowKey: string;
  code: string;
  name: string;
  rule_day: string;
  rule_month: string;
  electronic_extension_days: string;
  note: string;
}

/**
 * ISSUE #277 — قسم «لائحة المواعيد»: تعديلُ المكتب على سطر، وسجلُّه، ورجوعُه.
 *
 * **اللائحةُ بياناتُ منصّةٍ لا تُعدَّل**؛ تعديلُ المكتب صفٌّ إلحاقيٌّ يسري على كل
 * زبائن المكتب وكل السنوات. فالسطرُ يعرض: قاعدةَ المنصة (وصفاً من أرقامها)،
 * وتعديلَ المكتب إن وُجد **بارزاً وبجانبه تاريخُ المنصة**، وزرَّي «عدّل» و«رجّع
 * للمنصة»، وسجلَّ من ومتى.
 *
 * **وتنبيهُ «المنصة غيّرت موعداً أنت معدّله»** يُعرض شريطاً فوق سطره بزرّين:
 * «أُبقي تاريخي» (`keep-override`) و«آخذ الجديد» (`clear-override`) — والقرارُ
 * خادميّ بالكامل، والشاشةُ تُعيد القراءة من ردّه.
 *
 * **والانتظارُ يقرؤه الخادم**: `awaiting_decision` لكل سطرٍ يُحسب بالمسند نفسه
 * الذي يبني عليه التنبيه — فلا تُطابق الشاشةُ نصّ التنبيه باسم السطر (وكانت
 * تطابق، فيخفق مع سطرين متشابهي الاسم أو باسمٍ تغيّر).
 *
 * والكتابةُ تُخفى عمّن لا يملك `office.settings.manage` (والخادم يردّ 403).
 */
export const OfficeDeadlineRulesSection: React.FC<{ system: 'PS' | 'IL' }> = ({
  system,
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const canManage = can('office.settings.manage');
  const [rows, setRows] = useState<DeadlineRuleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<OverrideDraft | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listDeadlineRules(system)
      .then((payload) => setRows(payload.rules))
      .catch((failure) =>
        setError(humanizeThrown(failure, 'تعذّر تحميل لائحة المواعيد.')),
      )
      .finally(() => setLoading(false));
  }, [system]);

  useEffect(() => {
    load();
  }, [load]);

  const openEdit = (row: DeadlineRuleRow) => {
    // **الحقولُ تبدأ من تعديل المكتب وحده**: بلا تعديلٍ ساري تبدأ فارغةً
    // (والمنصةُ في الـplaceholder)، فالحفظُ بلا تغييرٍ لا يُثبّت قيمَ المنصة صراحةً.
    const override = row.override && !row.override.cleared ? row.override : null;
    setDraft({
      rowKey: ruleRowKey(row),
      code: row.code,
      name: row.name,
      rule_day: override?.rule_day != null ? String(override.rule_day) : '',
      rule_month: override?.rule_month != null ? String(override.rule_month) : '',
      electronic_extension_days:
        override?.electronic_extension_days != null
          ? String(override.electronic_extension_days)
          : '',
      note: '',
    });
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const result = await setDeadlineRuleOverride({
        system,
        code: draft.code,
        rule_day: draft.rule_day.trim() === '' ? null : Number(draft.rule_day),
        rule_month: draft.rule_month.trim() === '' ? null : Number(draft.rule_month),
        electronic_extension_days:
          draft.electronic_extension_days.trim() === ''
            ? null
            : Number(draft.electronic_extension_days),
        note: draft.note.trim(),
      });
      toast(`حُفظ التعديل — تغيّر تاريخ ${result.changed_obligations} التزام`, 'success');
      setDraft(null);
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ التعديل.'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const decide = async (row: DeadlineRuleRow, keep: boolean) => {
    const agreed = await confirm({
      title: keep ? 'أُبقي تاريخي' : 'آخذ تاريخ المنصة',
      message: keep
        ? `يُثبَّت تعديلُك على «${row.name}» على قيمك الحالية ويسقط التنبيه.`
        : `يرجع «${row.name}» إلى تاريخ المنصة، وتُعاد مواعيدُ التزاماتك غير المقدَّمة.`,
      confirmText: keep ? 'أُبقي تاريخي' : 'آخذ الجديد',
      danger: !keep,
    });
    if (!agreed) return;
    try {
      if (keep) {
        await keepDeadlineRuleOverride(system, row.code);
      } else {
        await clearDeadlineRuleOverride(system, row.code);
      }
      toast(keep ? 'ثُبِّت تاريخك' : 'رجع السطر إلى تاريخ المنصة', 'success');
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تنفيذ القرار.'), 'error');
    }
  };

  if (loading && rows.length === 0) {
    return <p className="text-[11.5px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>;
  }
  if (error) {
    return (
      <div>
        <p className="text-[12px] font-medium text-rose-600 dark:text-rose-400">{error}</p>
        <button type="button" onClick={load} className={`mt-2 ${officeSecondaryButtonClass}`}>
          أعد المحاولة
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
        لائحة المواعيد
      </h3>
      <p className="text-[11px] text-slate-500 dark:text-slate-400">
        تاريخُ المنصة هو الأصل، وتعديلُ المكتب عليه يسري على كل زبائن المكتب وكل
        السنوات — ويبقى مسجَّلاً بمن عدّله ومتى.
      </p>

      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((row) => {
          const override = row.override;
          const rowKey = ruleRowKey(row);
          return (
            <li key={rowKey} className="py-2.5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                      {row.name}
                    </span>
                    <span className="rounded-full border border-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      {row.year}
                    </span>
                    {override ? (
                      <span className="rounded-full border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                        معدَّل من المكتب
                      </span>
                    ) : null}
                  </div>

                  <p className="mt-1 text-[11px] text-slate-600 dark:text-slate-300">
                    {override
                      ? deadlineRuleDescription(overriddenRuleInput(row.platform, override))
                      : deadlineRuleDescription({
                          rule_kind: row.platform.rule_kind,
                          rule_kind_label: row.platform.rule_kind_label,
                          rule_day: row.platform.rule_day,
                          rule_month: row.platform.rule_month,
                        })}
                  </p>
                  {override ? (
                    <p className="mt-0.5 text-[10.5px] text-slate-500 dark:text-slate-400">
                      المنصة:{' '}
                      {deadlineRuleDescription({
                        rule_kind: row.platform.rule_kind,
                        rule_kind_label: row.platform.rule_kind_label,
                        rule_day: row.platform.rule_day,
                        rule_month: row.platform.rule_month,
                      })}
                    </p>
                  ) : null}
                  {override?.note ? (
                    <p className="mt-0.5 text-[10.5px] text-slate-500 dark:text-slate-400">
                      ملاحظة: {override.note}
                    </p>
                  ) : null}
                </div>

                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {canManage ? (
                    <button
                      type="button"
                      onClick={() => openEdit(row)}
                      className={officeSecondaryButtonClass}
                    >
                      عدّل
                    </button>
                  ) : null}
                  {canManage && override ? (
                    <button
                      type="button"
                      onClick={() => decide(row, false)}
                      className={officeSecondaryButtonClass}
                    >
                      رجّع للمنصة
                    </button>
                  ) : null}
                  {row.history.length > 0 ? (
                    <button
                      type="button"
                      onClick={() =>
                        setHistory(history === rowKey ? null : rowKey)
                      }
                      className={officeSecondaryButtonClass}
                    >
                      السجلّ
                    </button>
                  ) : null}
                </div>
              </div>

              {row.awaiting_decision && override && canManage ? (
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-2 text-[11px] font-medium text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                  المنصة غيّرت موعداً أنت معدّله — تُبقي تاريخك أم تأخذ الجديد؟
                  <button
                    type="button"
                    onClick={() => decide(row, true)}
                    className={officePrimaryButtonClass}
                  >
                    أُبقي تاريخي
                  </button>
                  <button
                    type="button"
                    onClick={() => decide(row, false)}
                    className={officeSecondaryButtonClass}
                  >
                    آخذ الجديد
                  </button>
                </div>
              ) : null}

              {history === rowKey ? (
                <ul className="mt-2 space-y-1 rounded-lg border border-slate-200 p-2 text-[10.5px] text-slate-600 dark:border-slate-700 dark:text-slate-300">
                  {row.history.map((entry) => (
                    <li key={entry.id} className="flex flex-wrap items-center gap-2">
                      <span className="tabular-nums">
                        {entry.created_at ? shortIsoDate(entry.created_at) : '—'}
                      </span>
                      <span className="font-semibold">{entry.created_by_name || '—'}</span>
                      <span>
                        {entry.cleared
                          ? 'رجّع للمنصة'
                          : deadlineRuleDescription(overriddenRuleInput(row.platform, entry))}
                      </span>
                      {entry.note ? <span>— {entry.note}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : null}

              {draft?.rowKey === rowKey ? (
                <div className="mt-2 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
                  {/* «آخر يوم في الفترة» لا يومَ فيه يُعدَّل — والخادم يرفضه. */}
                  {row.platform.rule_kind !== 'end_of_period' ? (
                    <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                      {/* سطرُ الحدث مداه أيامٌ بعد الحدث، وغيره يومٌ في شهر. */}
                      {row.platform.rule_kind === 'days_after_event'
                        ? 'أيام بعد الحدث (فارغ = كالمنصة)'
                        : 'اليوم (فارغ = كالمنصة)'}
                      <input
                        inputMode="numeric"
                        value={draft.rule_day}
                        placeholder={row.platform.rule_day != null ? String(row.platform.rule_day) : ''}
                        onChange={(event) => setDraft({ ...draft, rule_day: event.target.value })}
                        className={`${officeInputClass} mt-1 block w-24 tabular-nums`}
                      />
                    </label>
                  ) : null}
                  {/* الشهرُ لسطر «يوم في السنة التالية» وحده — والخادم يرفضه لغيره. */}
                  {row.platform.rule_kind === 'month_day_next_year' ? (
                    <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                      الشهر (فارغ = كالمنصة)
                      <input
                        inputMode="numeric"
                        value={draft.rule_month}
                        placeholder={row.platform.rule_month != null ? String(row.platform.rule_month) : ''}
                        onChange={(event) => setDraft({ ...draft, rule_month: event.target.value })}
                        className={`${officeInputClass} mt-1 block w-24 tabular-nums`}
                      />
                    </label>
                  ) : null}
                  <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                    أيام التمديد الإلكتروني
                    <input
                      inputMode="numeric"
                      value={draft.electronic_extension_days}
                      placeholder={String(row.platform.electronic_extension_days)}
                      onChange={(event) =>
                        setDraft({ ...draft, electronic_extension_days: event.target.value })
                      }
                      className={`${officeInputClass} mt-1 block w-24 tabular-nums`}
                    />
                  </label>
                  <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
                    الملاحظة (مطلوبة)
                    <input
                      value={draft.note}
                      onChange={(event) => setDraft({ ...draft, note: event.target.value })}
                      className={`${officeInputClass} mt-1 block w-56`}
                    />
                  </label>
                  <button
                    type="button"
                    disabled={saving || draft.note.trim() === ''}
                    onClick={save}
                    className={officePrimaryButtonClass}
                  >
                    احفظ
                  </button>
                  <button
                    type="button"
                    onClick={() => setDraft(null)}
                    className={officeSecondaryButtonClass}
                  >
                    إلغاء
                  </button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
