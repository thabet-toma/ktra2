import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  getOfficeSettings,
  listCustomizingClients,
  resetOfficeSetting,
  setOfficeSetting,
  type OfficeClientRow,
  type OfficeSettingsPayload,
} from '../../services/accountingOfficeApi';
import { clientFilePath, missingFirstRunLabels } from '../../utils/accountingOffice';
import { humanizeThrown } from '../../utils/drfError';
import { useToast } from '../../contexts/ToastContext';
import { SettingControl } from './SettingControl';
import { OfficeCard, OfficeError, OfficeSkeleton } from './OfficeUi';

type CustomizingClient = Pick<OfficeClientRow, 'id' | 'name' | 'status' | 'status_label'>;

/**
 * ISSUE #271 — شاشة إعدادات المكتب، بمجموعة «المكتب» وحدها الآن.
 *
 * لكل إعداد: قيمته الفعلية، و«ارجع للافتراضي» (حين يملك افتراضيًا فعلاً —
 * `can_reset`)، و«مخصَّص عند N زبون» يُكبَس فيعرض القائمة، وكلُّ اسمٍ فيها رابطٌ
 * يفتح ملفّ الزبون. والثلاثةُ من السجلّ نفسه: `value_label` و`can_reset`
 * و`client_customization_count` يحسبها الخادم، فلا حسابَ موازياً هنا يفترق عنه.
 *
 * وتخصيصُ الزبون **ليس** هنا: مكانه ملفّه — الإعدادُ المكتبيّ سقفٌ، والتخصيص
 * استثناءٌ يُرى حيث يُقرأ الزبون.
 */
export const OfficeSettingsScreen: React.FC = () => {
  const toast = useToast();
  const navigate = useNavigate();
  const [payload, setPayload] = useState<OfficeSettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState<Record<string, CustomizingClient[] | undefined>>({});

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getOfficeSettings()
      .then(setPayload)
      .catch((failure) => setError(humanizeThrown(failure, 'تعذّر تحميل إعدادات المكتب.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async (key: string, value: unknown) => {
    try {
      await setOfficeSetting(key, value);
      toast('حُفظ الإعداد', 'success');
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ الإعداد.'), 'error');
      throw failure; // `SettingControl` يعرضه تحت السطر نفسه
    }
  };

  const reset = async (key: string) => {
    try {
      await resetOfficeSetting(key);
      toast('رجع الإعداد إلى الافتراضي', 'success');
      load();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر الرجوع إلى الافتراضي.'), 'error');
      throw failure;
    }
  };

  const toggleClients = async (key: string) => {
    if (expanded[key]) {
      setExpanded((prev) => ({ ...prev, [key]: undefined }));
      return;
    }
    try {
      const rows = await listCustomizingClients(key);
      setExpanded((prev) => ({ ...prev, [key]: rows }));
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تحميل قائمة الزبائن المخصِّصين.'), 'error');
    }
  };

  if (loading && !payload) return <OfficeSkeleton />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!payload) return null;

  const officeGroup = payload.settings.filter((setting) => setting.group === 'office');
  // التسمية من `payload.groups` وحدها — لا نصٌّ احتياطيّ يفترق عن السجلّ.
  const groupLabel = payload.groups.find((group) => group.id === 'office')?.label ?? '';

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
        <h1 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">
          إعدادات المكتب
        </h1>
        <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
          هذه قيم المكتب، وكلُّ زبونٍ يرثها ما لم يُخصَّص له غيرها. التخصيصُ يُدار من
          ملفّ الزبون.
        </p>
        {payload.first_run_required ? (
          <p
            role="status"
            className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] font-medium text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
          >
            لم يكتمل أول تشغيل بعد — اختر{' '}
            {missingFirstRunLabels(payload.missing_settings, payload.settings).join(' و')}.
          </p>
        ) : null}
      </header>

      <OfficeCard title={groupLabel}>
        {officeGroup.map((setting) => {
          const clients = expanded[setting.key];
          const count = setting.client_customization_count ?? 0;
          return (
            <div key={setting.key}>
              <SettingControl
                setting={setting}
                value={setting.value}
                canReset={setting.can_reset === true}
                onReset={() => reset(setting.key)}
                onSave={(value) => save(setting.key, value)}
              />
              {/* إعدادٌ مكتبيٌّ فقط (`office_size`) لا يُخصَّص لزبون — «مخصَّص عند 0» كذبٌ عنه. */}
              {setting.levels.includes('client') ? (
                <div className="pb-3">
                  <button
                    type="button"
                    onClick={() => toggleClients(setting.key)}
                    disabled={count === 0}
                    className="text-[11px] font-medium text-teal-700 disabled:text-slate-400 dark:text-teal-400 dark:disabled:text-slate-600"
                  >
                    مخصَّص عند {count} زبون
                    {count > 0 ? (clients ? ' — أخفِ القائمة' : ' — اعرضهم') : ''}
                  </button>
                  {clients ? (
                    clients.length === 0 ? (
                      <p className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                        لا زبونَ خصّص هذا الإعداد.
                      </p>
                    ) : (
                      <ul className="mt-1.5 flex flex-wrap gap-1.5">
                        {clients.map((client) => (
                          <li key={client.id}>
                            <button
                              type="button"
                              onClick={() => navigate(clientFilePath(client.id))}
                              className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600 hover:border-teal-300 hover:text-teal-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:text-teal-300"
                            >
                              {client.name} · {client.status_label}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </OfficeCard>
    </div>
  );
};
