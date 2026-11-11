/**
 * #280/ب — قسمُ «نصوص التذكير» في إعدادات المكتب: نصٌّ لكل (نوع × لغة).
 *
 * **النصُّ الظاهر هو الفعليّ** (`body`): بديلُ المكتب إن وُجد، وإلا افتراضيُّ
 * المنصّة (`default_body`) — والخادمُ يرسلهما معاً مع علمِ التخصيص، فتعرض
 * الشاشةُ ما سيُرسَل ولا تُعيد بناءه. و«ارجع للافتراضي» **حذفُ البديل** لا
 * كتابةُ الافتراضيِّ مكانه، فيعود سطرُ المكتب إلى نصّ المنصّة بلا نسخةٍ ثانية.
 *
 * **والرموزُ تُدرَج بضغطة** من قائمة الخادم (`placeholders`) لا من نسخةٍ هنا:
 * رمزٌ يُكتب في الواجهة ولا يعرفه الخادمُ يردّه 400 عند الحفظ.
 *
 * والقراءةُ لكل عضو (من يرسل يقرأ ما سيرسل)، والكتابةُ بـ`office.settings.manage`
 * وحدها — والخادمُ يردّ 403 على غيرها على أيّ حال.
 */
import React, { useCallback, useEffect, useState } from 'react';

import {
  getReminderTemplates,
  resetReminderTemplate,
  setReminderTemplate,
  type ReminderTemplateRow,
  type ReminderTemplatesPayload,
} from '../../services/accountingOfficeApi';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/** مفتاحُ مسوّدة نصٍّ واحد: النوع واللغة معاً — لا فهرسَ صفّ. */
const draftKey = (row: Pick<ReminderTemplateRow, 'reminder_type' | 'language'>): string =>
  `${row.reminder_type}|${row.language}`;

export const OfficeReminderTemplatesSection: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const canManage = can('office.settings.manage');
  const [payload, setPayload] = useState<ReminderTemplatesPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  /** المسوّداتُ المفتوحة فقط — ما ليس منها يُعرض بنصّ الخادم. */
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingKey, setSavingKey] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getReminderTemplates()
      .then(setPayload)
      .catch((failure) => setError(humanizeThrown(failure, 'تعذّر تحميل نصوص التذكير.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && payload === null) {
    return <p className="text-[11.5px] text-slate-500 dark:text-slate-400">جاري التحميل…</p>;
  }
  if (error) {
    return (
      <div>
        <p role="alert" className="text-[12px] font-medium text-rose-600 dark:text-rose-400">
          {error}
        </p>
        <button type="button" onClick={load} className={`mt-2 ${officeSecondaryButtonClass}`}>
          أعد المحاولة
        </button>
      </div>
    );
  }
  if (!payload) return null;

  // الأنواعُ بترتيب الخادم، ولكلٍّ لغاتُه — لا ترتيبَ محليّاً يفترق عن السجلّ.
  const groups: { type: string; label: string; rows: ReminderTemplateRow[] }[] = [];
  payload.rows.forEach((row) => {
    const bucket = groups.find((entry) => entry.type === row.reminder_type);
    if (bucket) bucket.rows.push(row);
    else groups.push({ type: row.reminder_type, label: row.reminder_type_label, rows: [row] });
  });

  const draftOf = (row: ReminderTemplateRow): string => drafts[draftKey(row)] ?? row.body;

  const setDraft = (row: ReminderTemplateRow, value: string) => {
    setDrafts((prev) => ({ ...prev, [draftKey(row)]: value }));
  };

  /** إدراجُ رمزٍ في آخر النصّ — هو ما يفهمه الخادم حرفاً (`{client_name}`). */
  const insertPlaceholder = (row: ReminderTemplateRow, placeholder: string) => {
    const current = draftOf(row);
    const spacer = current === '' || /\s$/.test(current) ? '' : ' ';
    setDraft(row, `${current}${spacer}{${placeholder}}`);
  };

  const save = async (row: ReminderTemplateRow) => {
    const key = draftKey(row);
    const body = draftOf(row);
    if (!body.trim()) return;
    setSavingKey(key);
    try {
      setPayload(await setReminderTemplate(row.reminder_type, row.language, body));
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      toast('حُفظ نصّ التذكير', 'success');
    } catch (failure) {
      // الرمزُ المجهول يردّه الخادم برسالته التي تسمّيه — تُعرض كما وصل.
      toast(humanizeThrown(failure, 'تعذّر حفظ نصّ التذكير.'), 'error');
    } finally {
      setSavingKey(null);
    }
  };

  const resetToDefault = async (row: ReminderTemplateRow) => {
    const ok = await confirm({
      title: 'ارجع للافتراضي',
      message:
        `يُحذف نصّ المكتب لهذا النوع بلغته، ويعود نصُّ المنصّة كما هو. `
        + 'الرسائل التي أُرسلت سابقاً تبقى بنصّها في السجلّ.',
      confirmText: 'ارجع للافتراضي',
      danger: true,
    });
    if (!ok) return;
    const key = draftKey(row);
    setSavingKey(key);
    try {
      await resetReminderTemplate(row.reminder_type, row.language);
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
      load();
      toast('رجع النصّ إلى افتراضي المنصّة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر الرجوع إلى النصّ الافتراضي.'), 'error');
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div>
      <p className="text-[11.5px] text-slate-500 dark:text-slate-400">
        نصُّ كل نوعٍ بلغة المستلِم. الرسالةُ تُبنى بالنصّ الفعليّ، والرموز تتحوّل
        إلى قيمها وقت البناء — وما ليس منها يبقى حرفياً.
      </p>

      {groups.map((group) => (
        <div key={group.type} className="mt-3">
          <h3 className="text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
            {group.label}
          </h3>
          <div className="mt-1.5 grid gap-2 md:grid-cols-2">
            {group.rows.map((row) => {
              const key = draftKey(row);
              const draft = draftOf(row);
              const dirty = draft !== row.body;
              return (
                <div
                  key={key}
                  className="rounded-lg border border-slate-100 p-2 dark:border-slate-800"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[10.5px] font-semibold text-slate-600 dark:text-slate-300">
                      {row.language_label}
                    </span>
                    {row.is_custom ? (
                      <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[9.5px] font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
                        مخصَّص
                      </span>
                    ) : null}
                    {row.is_custom && row.updated_by ? (
                      <span className="text-[9.5px] text-slate-400 dark:text-slate-500">
                        {row.updated_by}
                      </span>
                    ) : null}
                  </div>

                  <textarea
                    value={draft}
                    onChange={(event) => setDraft(row, event.target.value)}
                    rows={5}
                    readOnly={!canManage}
                    aria-label={`نصّ ${group.label} — ${row.language_label}`}
                    className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white p-2 text-[11.5px] leading-6 text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  />

                  {canManage ? (
                    <>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {payload.placeholders.map((placeholder) => (
                          <button
                            key={placeholder}
                            type="button"
                            onClick={() => insertPlaceholder(row, placeholder)}
                            className="rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[9.5px] font-medium text-teal-700 hover:border-teal-300 dark:border-slate-700 dark:bg-slate-800 dark:text-teal-300"
                          >
                            {`{${placeholder}}`}
                          </button>
                        ))}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          disabled={!dirty || savingKey === key || !draft.trim()}
                          onClick={() => save(row)}
                          className={officePrimaryButtonClass}
                        >
                          احفظ
                        </button>
                        {row.is_custom ? (
                          <button
                            type="button"
                            disabled={savingKey === key}
                            onClick={() => resetToDefault(row)}
                            className={officeSecondaryButtonClass}
                          >
                            ارجع للافتراضي
                          </button>
                        ) : null}
                      </div>
                    </>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};
