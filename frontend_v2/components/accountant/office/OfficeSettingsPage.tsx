import React, { useCallback, useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import {
  getPracticeSettings,
  updatePracticeSettings,
  type PracticeSettingsRecord,
} from '../../../services/accountantPracticeApi';
import { useToast } from '../../../contexts/ToastContext';
import { OfficeCard, OfficeError, OfficeField, OfficeInput, OfficeSkeleton } from './OfficeUi';

/**
 * إعدادات المكتب — ما لا يُقرَّر لكل زبون على حدة: أنواع الخدمات التي يقدّمها
 * المكتب، والمهلة الافتراضية لموعد انتهاء برنامج المراجعة.
 *
 * أنواع الخدمة قائمةٌ مغلقة عمداً: برنامج «ض.ق.م شهرية» يجب أن يكون هو نفسه عند
 * كل زبون، وإلا صار الفرز والأجندة على أربع كتاباتٍ لنوعٍ واحد.
 */
export const OfficeSettingsPage: React.FC = () => {
  const toast = useToast();
  const [settings, setSettings] = useState<PracticeSettingsRecord | null>(null);
  const [dueDays, setDueDays] = useState('');
  const [types, setTypes] = useState<string[]>([]);
  const [newType, setNewType] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const apply = (value: PracticeSettingsRecord) => {
    setSettings(value);
    setDueDays(String(value.default_program_due_days));
    setTypes(value.service_types);
  };

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getPracticeSettings()
      .then((res) => apply(res.settings))
      .catch(() => setError('تعذّر تحميل إعدادات المكتب.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const addType = () => {
    const value = newType.trim();
    if (!value) return;
    if (types.includes(value)) {
      setFormError('هذا النوع موجود أصلاً.');
      return;
    }
    setTypes([...types, value]);
    setNewType('');
    setFormError('');
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (types.length === 0) {
      setFormError('أبقِ نوع خدمة واحداً على الأقل — البرامج تُبنى عليها.');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      const response = await updatePracticeSettings({
        default_program_due_days: Number(dueDays),
        service_types: types,
      });
      apply(response.settings);
      toast('حُفظت إعدادات المكتب.', 'success');
    } catch (caught) {
      setFormError((caught as Error).message || 'تعذّر حفظ الإعدادات.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <OfficeSkeleton rows={5} />;
  if (error) return <OfficeError message={error} onRetry={load} />;
  if (!settings) return null;

  // النوع المستعمَل في برنامج قائم يبقى محفوظاً على البرنامج نفسه؛ حذفه هنا يمنع
  // اختياره مستقبلاً فقط، ولا يُعدّل برنامجاً قديماً.
  return (
    <form onSubmit={save} className="max-w-3xl space-y-6">
      {formError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{formError}</p>}

      <OfficeCard title="مواعيد البرامج">
        <OfficeField
          label="المهلة الافتراضية لموعد الانتهاء (بالأيام)"
          hint="تُستعمل حين يُنشأ برنامج بلا موعد انتهاء — بين يوم و365 يوماً."
        >
          {(id) => (
            <OfficeInput
              id={id}
              type="number"
              min={1}
              max={365}
              value={dueDays}
              onChange={(event) => setDueDays(event.target.value)}
              className="max-w-[12rem]"
            />
          )}
        </OfficeField>
      </OfficeCard>

      <OfficeCard title="أنواع الخدمات">
        <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
          كل برنامج مراجعة يختار نوعه من هذه القائمة. حذف نوع يمنع اختياره لاحقاً، ولا يغيّر
          برنامجاً قائماً.
        </p>
        <ul className="space-y-2">
          {types.map((type) => (
            <li key={type} className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-4 py-2.5 dark:border-slate-800">
              <span className="font-bold text-slate-800 dark:text-slate-100">{type}</span>
              <button
                type="button"
                onClick={() => setTypes(types.filter((item) => item !== type))}
                aria-label={`حذف ${type}`}
                className="rounded-lg border border-red-300 p-2 text-red-700"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <OfficeField label="نوع خدمة جديد" className="min-w-[16rem] flex-1">
            {(id) => (
              <OfficeInput
                id={id}
                value={newType}
                onChange={(event) => setNewType(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addType(); } }}
                placeholder="مثال: مراجعة سنوية"
              />
            )}
          </OfficeField>
          <button type="button" onClick={addType} className="flex items-center gap-2 rounded-xl border border-indigo-600 px-5 py-2.5 font-bold text-indigo-700 dark:text-indigo-300">
            <Plus className="h-4 w-4" />أضف
          </button>
        </div>
      </OfficeCard>

      <button type="submit" disabled={saving} className="rounded-xl bg-indigo-700 px-6 py-3 font-bold text-white disabled:opacity-50">
        {saving ? 'جارٍ الحفظ…' : 'حفظ الإعدادات'}
      </button>
    </form>
  );
};

export default OfficeSettingsPage;
