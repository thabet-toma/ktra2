import React, { useState } from 'react';

import {
  setOfficeSetting,
  type OfficeSettingsPayload,
  type SettingRow,
} from '../../services/accountingOfficeApi';
import { humanizeThrown } from '../../utils/drfError';
import { missingFirstRunLabels } from '../../utils/accountingOffice';
import { usePermissions } from '../../contexts/PermissionsContext';
import { OfficeCard, officePrimaryButtonClass } from './OfficeUi';

/**
 * ISSUE #271 — خطوة أول تشغيل: «اختر نظام مكتبك الضريبي وحجمه».
 *
 * تظهر **قبل** قائمة الزبائن، ولا تُتخطّى: النظام الضريبي يحدّد اختيارات البطاقة
 * الضريبية، وحجمُ المكتب يحدّد ما يُعرض لاحقاً. والخادم يحرس القاعدة نفسها
 * (`create_office_client` يرفض قبل الاكتمال) — فالتخطّي بمكالمةٍ مباشرة لا يفتح
 * القائمة.
 *
 * **اختيارٌ مباشر**: كبسةٌ على الخيار تحسمه فوراً (بلا «احفظ» لكل حقل)، ثم
 * «ابدأ العمل» واحد. والاختياراتُ من `setting.choices` كما يرسلها الخادم.
 *
 * **ومَن لا يملك `office.settings.manage` لا يرى أزراراً تردّ 403**: الكتابةُ
 * مقيّدةٌ بالمفتاح خادمياً، فيُقال له إن أول التشغيل يكمله مالك المكتب أو مديره
 * بدل عرض خيارٍ لا يعمل.
 */
export const OfficeFirstRunStep: React.FC<{
  payload: OfficeSettingsPayload;
  onDone: () => void;
}> = ({ payload, onDone }) => {
  const { can } = usePermissions();
  const canManage = can('office.settings.manage');
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const missing = payload.settings.filter((setting) =>
    payload.missing_settings.includes(setting.key),
  );

  const currentValue = (setting: SettingRow): string => {
    if (setting.key in draft) return draft[setting.key];
    return typeof setting.value === 'string' ? setting.value : '';
  };

  const pending = missing.filter((setting) => currentValue(setting) === '');

  const submit = async () => {
    setSaving(true);
    setError('');
    try {
      for (const setting of missing) {
        const value = currentValue(setting);
        if (value !== '') await setOfficeSetting(setting.key, value);
      }
      onDone();
    } catch (failure) {
      setError(humanizeThrown(failure, 'تعذّر حفظ إعدادات المكتب.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <header className="rounded-xl border border-teal-200 bg-teal-50 p-5 dark:border-teal-900 dark:bg-teal-950/30">
        <h1 className="text-[20px] font-bold text-teal-900 dark:text-teal-200">
          اختر نظام مكتبك الضريبي وحجمه
        </h1>
        <p className="mt-1 text-[12px] text-teal-800 dark:text-teal-300">
          هذان الاختياران يحدّدان اختيارات البطاقة الضريبية لكل زبون وما يُعرض في
          الشاشات. غيرهما يُختار لاحقاً من «إعدادات المكتب».
        </p>
      </header>

      <OfficeCard>
        {canManage ? (
          <>
            {missing.map((setting) => (
              <div key={setting.key} className="border-b border-slate-100 py-3 last:border-b-0 dark:border-slate-800">
                <p className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                  {setting.label}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {setting.choices.map((choice) => {
                    const on = currentValue(setting) === choice.value;
                    return (
                      <button
                        key={choice.value}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setDraft((prev) => ({ ...prev, [setting.key]: choice.value }))}
                        className={
                          on
                            ? 'rounded-lg border border-teal-700 bg-teal-700 px-3 py-1.5 text-[12px] font-semibold text-white'
                            : 'rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200'
                        }
                      >
                        {choice.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-[11.5px] text-slate-500 dark:text-slate-400">
                الناقص:{' '}
                {missingFirstRunLabels(pending.map((setting) => setting.key), payload.settings).join(' و')
                  || 'لا شيء'}
              </p>
              <button
                type="button"
                onClick={submit}
                disabled={pending.length > 0 || saving}
                className={officePrimaryButtonClass}
              >
                {saving ? 'جاري الحفظ…' : 'ابدأ العمل'}
              </button>
            </div>
            {error ? (
              <p className="mt-2 text-[11.5px] font-medium text-rose-600 dark:text-rose-400">{error}</p>
            ) : null}
          </>
        ) : (
          // لا أزرارَ لمن لا يملك المفتاح: الكتابةُ تردّ 403 خادمياً، والطريقُ
          // الصادق أن يُقال له مَن يكمله لا أن يُعرض عليه اختيارٌ لا يعمل.
          <p
            role="status"
            className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200"
          >
            أول تشغيلٍ يكمله مالك المكتب أو مديره — لم يُختَر بعد نظامُ المكتب
            الضريبي وحجمه.
          </p>
        )}
      </OfficeCard>
    </div>
  );
};
