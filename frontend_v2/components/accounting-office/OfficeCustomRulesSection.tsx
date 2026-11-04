import React, { useCallback, useEffect, useState } from 'react';

import {
  createOfficeCustomRule,
  listOfficeCustomRules,
  updateOfficeCustomRule,
  type OfficeCustomRulesPayload,
} from '../../services/accountingOfficeApi';
import { humanizeThrown } from '../../utils/drfError';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/** مسوّدةُ التزام مكتبٍ: `id === null` تعني جديداً. */
interface CustomRuleDraft {
  id: number | null;
  name: string;
  service: string;
  cadence: string;
  rule_kind: string;
  rule_day: string;
  rule_month: string;
}

/**
 * ISSUE #277 — قسم «التزامات المكتب»: قاعدةٌ عرّفها المكتب لنفسه.
 *
 * تتولّد كالرسمية تماماً (نفس المحرّك ونفس الفترات) بكودٍ مشتقّ `office-<id>`
 * وعلامة «من المكتب» في سطور الالتزامات. **ولا حذف**: التعطيلُ يوقف توليد
 * الفترات الجديدة، وما وُلد يبقى بتاريخه — والصفُّ لا يُطوى.
 *
 * والتسمياتُ (الدوريات وأنواع القواعد والخدمات) كلُّها من الخادم في حمولة
 * `custom-rules/`، فلا جدولَ محلياً يفترق عن ثوابته.
 */
export const OfficeCustomRulesSection: React.FC = () => {
  const toast = useToast();
  const { can } = usePermissions();
  const canManage = can('office.settings.manage');
  const [payload, setPayload] = useState<OfficeCustomRulesPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<CustomRuleDraft | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listOfficeCustomRules()
      .then(setPayload)
      .catch((failure) =>
        setError(humanizeThrown(failure, 'تعذّر تحميل التزامات المكتب.')),
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openNew = () => {
    if (!payload) return;
    setDraft({
      id: null,
      name: '',
      service: String(payload.services[0]?.id ?? ''),
      cadence: payload.cadence_choices[0]?.value ?? '',
      rule_kind: payload.rule_kind_choices[0]?.value ?? '',
      rule_day: '15',
      rule_month: '4',
    });
  };

  const openEdit = (row: OfficeCustomRulesPayload['custom_rules'][number]) => {
    setDraft({
      id: row.id,
      name: row.name,
      service: String(row.service.id),
      cadence: row.cadence,
      rule_kind: row.rule_kind,
      rule_day: row.rule_day === null ? '' : String(row.rule_day),
      rule_month: row.rule_month === null ? '' : String(row.rule_month),
    });
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    const body = {
      name: draft.name.trim(),
      service: Number(draft.service),
      cadence: draft.cadence,
      rule_kind: draft.rule_kind,
      rule_day: draft.rule_day.trim() === '' ? null : Number(draft.rule_day),
      rule_month: draft.rule_month.trim() === '' ? null : Number(draft.rule_month),
    };
    try {
      const next = draft.id === null
        ? await createOfficeCustomRule(body)
        : await updateOfficeCustomRule(draft.id, body);
      setPayload(next);
      setDraft(null);
      toast('حُفظ التزام المكتب', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ التزام المكتب.'), 'error');
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (
    row: OfficeCustomRulesPayload['custom_rules'][number],
  ) => {
    try {
      setPayload(await updateOfficeCustomRule(row.id, { is_active: !row.is_active }));
      toast(row.is_active ? 'عُطِّل — لا فتراتٍ جديدة' : 'فُعِّل', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تغيير التفعيل.'), 'error');
    }
  };

  if (loading && payload === null) {
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
  if (!payload) return null;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
          التزامات المكتب
        </h3>
        {canManage ? (
          <button type="button" onClick={openNew} className={officeSecondaryButtonClass}>
            أضف التزاماً
          </button>
        ) : null}
      </div>
      <p className="text-[11px] text-slate-500 dark:text-slate-400">
        التزامٌ يعرّفه المكتب لنفسه: يُولَّد كالرسميّ ويظهر بعلامة «من المكتب».
        وتعطيلُه يوقف الفترات الجديدة ولا يمحو ما وُلد.
      </p>

      {payload.custom_rules.length === 0 ? (
        <p className="text-[11.5px] text-slate-400 dark:text-slate-500">
          لا التزامات خاصة بالمكتب بعد.
        </p>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {payload.custom_rules.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                    {row.name}
                  </span>
                  <span className="rounded-full border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300">
                    {row.origin_label}
                  </span>
                  {!row.is_active ? (
                    <span className="rounded-full border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                      معطَّل
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-[10.5px] text-slate-500 dark:text-slate-400">
                  {row.service.name} · {row.cadence_label} · {row.rule_kind_label}
                  {row.rule_day !== null ? ` · يوم ${row.rule_day}` : ''}
                  {row.rule_month !== null ? ` · شهر ${row.rule_month}` : ''}
                </p>
              </div>
              {canManage ? (
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => openEdit(row)}
                    className={officeSecondaryButtonClass}
                  >
                    عدّل
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleActive(row)}
                    className={officeSecondaryButtonClass}
                  >
                    {row.is_active ? 'عطّل' : 'فعّل'}
                  </button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {draft ? (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الاسم
            <input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              className={`${officeInputClass} mt-1 block w-48`}
            />
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الخدمة
            <select
              value={draft.service}
              onChange={(event) => setDraft({ ...draft, service: event.target.value })}
              className={`${officeInputClass} mt-1 block`}
            >
              {payload.services.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الدورية
            <select
              value={draft.cadence}
              onChange={(event) => setDraft({ ...draft, cadence: event.target.value })}
              className={`${officeInputClass} mt-1 block`}
            >
              {payload.cadence_choices.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            القاعدة
            <select
              value={draft.rule_kind}
              onChange={(event) => setDraft({ ...draft, rule_kind: event.target.value })}
              className={`${officeInputClass} mt-1 block`}
            >
              {payload.rule_kind_choices.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            اليوم
            <input
              inputMode="numeric"
              value={draft.rule_day}
              onChange={(event) => setDraft({ ...draft, rule_day: event.target.value })}
              className={`${officeInputClass} mt-1 block w-20 tabular-nums`}
            />
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            الشهر (للسنوي)
            <input
              inputMode="numeric"
              value={draft.rule_month}
              onChange={(event) => setDraft({ ...draft, rule_month: event.target.value })}
              className={`${officeInputClass} mt-1 block w-20 tabular-nums`}
            />
          </label>
          <button
            type="button"
            disabled={saving || draft.name.trim() === '' || draft.service === ''}
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
    </div>
  );
};
