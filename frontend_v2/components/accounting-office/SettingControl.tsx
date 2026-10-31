import React, { useEffect, useState } from 'react';

import type { SettingRow } from '../../services/accountingOfficeApi';
import { humanizeThrown } from '../../utils/drfError';
import { officeInputClass } from './OfficeUi';

/**
 * ISSUE #271 — ضابطُ إعدادٍ واحد، مشتركٌ بين شاشة إعدادات المكتب وملف الزبون.
 *
 * الضابط **لا يحفظ بنفسه**: يُبلّغ بالقيمة الجديدة ومن عنده يأتي `onSave`. وبذلك
 * يبقى الفرق بين «إعداد مكتب» و«تخصيص زبون» في الشاشة المستدعية وحدها، والقاعدة
 * (أيّ قيمةٍ صالحة، وأيّ مستوى) في السجلّ خادمياً لا هنا.
 *
 * **ولا تسمياتٍ محليّة**: اسمُ الإعداد وقيمتُه واختياراتُه — ومنها أيام الأسبوع —
 * كلها من `SettingRow` الذي يبنيه الخادم من السجلّ.
 */
interface SettingControlProps {
  setting: SettingRow;
  /** القيمة المعروضة — قد تكون الموروثة حين لا تخصيص. */
  value: unknown;
  onReset?: () => void;
  resetLabel?: string;
  /** هل القيمة الحالية تخصيصٌ يملك صاحبه زرَّ الرجوع؟ */
  canReset?: boolean;
  disabled?: boolean;
  onSave: (value: unknown) => Promise<void> | void;
}

const asString = (value: unknown): string => (typeof value === 'string' ? value : '');

const asStringList = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const sameValue = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b);

export const SettingControl: React.FC<SettingControlProps> = ({
  setting,
  value,
  onReset,
  resetLabel = 'ارجع للافتراضي',
  canReset = false,
  disabled = false,
  onSave,
}) => {
  const [draft, setDraft] = useState<unknown>(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setDraft(value);
    setError('');
  }, [value]);

  const dirty = !sameValue(draft, value);
  // إعدادٌ بلا افتراضي لا يُحفظ فارغاً: الخادم يرفض `null` لـ`tax_system`
  // و`office_size` لأن مسحهما يُعيد المكتب إلى أول تشغيل.
  const draftMissing = draft === null || draft === undefined || draft === '';
  const cannotSave = !setting.has_default && draftMissing;

  const commit = async () => {
    setSaving(true);
    setError('');
    try {
      await onSave(draft);
    } catch (failure) {
      setError(humanizeThrown(failure, 'تعذّر حفظ الإعداد.'));
    } finally {
      setSaving(false);
    }
  };

  const runReset = async () => {
    if (!onReset) return;
    setSaving(true);
    setError('');
    try {
      await onReset();
    } catch (failure) {
      setError(humanizeThrown(failure, 'تعذّر الرجوع إلى الإعداد السابق.'));
    } finally {
      setSaving(false);
    }
  };

  const toggleDay = (day: string) => {
    const current = asStringList(draft);
    const next = current.includes(day)
      ? current.filter((item) => item !== day)
      : [...current, day];
    // الترتيبُ من `choices` كما يرسله الخادم — لا ترتيبُ نقرِ المستخدم.
    setDraft(setting.choices.filter((choice) => next.includes(choice.value)).map((c) => c.value));
  };

  return (
    <div className="border-b border-slate-100 py-3 last:border-b-0 dark:border-slate-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
            {setting.label}
          </p>
          {setting.note ? (
            <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">{setting.note}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {dirty ? (
            <button
              type="button"
              onClick={commit}
              disabled={saving || disabled || cannotSave}
              className="rounded-lg bg-teal-700 px-3 py-1.5 text-[11.5px] font-semibold text-white disabled:opacity-50"
            >
              {saving ? 'جاري الحفظ…' : 'احفظ'}
            </button>
          ) : null}
          {canReset && onReset ? (
            <button
              type="button"
              onClick={runReset}
              disabled={saving || disabled}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[11.5px] font-medium text-slate-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            >
              {resetLabel}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-2">
        {setting.kind === 'choice' ? (
          <select
            value={asString(draft)}
            disabled={disabled}
            onChange={(event) => setDraft(event.target.value === '' ? null : event.target.value)}
            className={`${officeInputClass} min-w-[220px]`}
          >
            {/* الخيار الفارغ لِـ«لم يُختَر بعد» وحده: إعدادٌ بلا افتراضي وقيمتُه
                المحفوظة فارغة. إظهارُه دائماً كان يُغري بمسح قيمةٍ فيردّها الخادم
                400 لأن المسح يُعيد المكتب إلى أول تشغيل. */}
            {!setting.has_default && (value === null || value === undefined || value === '') ? (
              <option value="">— لم يُختَر بعد —</option>
            ) : null}
            {setting.choices.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        ) : null}

        {setting.kind === 'weekdays' ? (
          <div className="flex flex-wrap gap-1.5">
            {setting.choices.map((choice) => {
              const on = asStringList(draft).includes(choice.value);
              return (
                <button
                  key={choice.value}
                  type="button"
                  disabled={disabled}
                  aria-pressed={on}
                  onClick={() => toggleDay(choice.value)}
                  className={
                    on
                      ? 'rounded-full border border-teal-700 bg-teal-700 px-2.5 py-1 text-[11px] font-semibold text-white'
                      : 'rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                  }
                >
                  {choice.label}
                </button>
              );
            })}
          </div>
        ) : null}

        {setting.kind === 'bool' ? (
          <label className="inline-flex items-center gap-2 text-[12px] text-slate-700 dark:text-slate-200">
            <input
              type="checkbox"
              checked={draft === true}
              disabled={disabled}
              onChange={(event) => setDraft(event.target.checked)}
              className="size-4 rounded border-slate-300"
            />
            نعم
          </label>
        ) : null}

        {setting.kind === 'integer' ? (
          <input
            type="number"
            value={typeof draft === 'number' ? draft : ''}
            disabled={disabled}
            onChange={(event) =>
              setDraft(event.target.value === '' ? null : Number(event.target.value))
            }
            className={`${officeInputClass} w-28 tabular-nums`}
          />
        ) : null}
      </div>

      <p className="mt-1.5 text-[10.5px] text-slate-400 dark:text-slate-500">
        القيمة الحالية:{' '}
        <span className="font-semibold text-slate-600 dark:text-slate-300">
          {setting.value_label || '—'}
        </span>
      </p>
      {error ? (
        <p className="mt-1 text-[11px] font-medium text-rose-600 dark:text-rose-400">{error}</p>
      ) : null}
    </div>
  );
};
