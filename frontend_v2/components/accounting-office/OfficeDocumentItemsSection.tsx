/**
 * #278 — قسمُ «بنود الأوراق» في شاشة الإعدادات: قالبُ المكتب.
 *
 * **ثلاثةُ طبقاتٍ لا تُخلط**: بنداتُ المنصّة تظهر كما هي، و«ضمن القائمة» عليها
 * صفُّ خيارٍ (`OfficeDocumentItemChoice`) لا تعديلٌ على المنصّة؛ وبندُ المكتب
 * يُضاف ويُعطَّل بـ`is_active` ولا يُحذف بعد استعماله. والتعديلُ لا يمسّ صفوفاً
 * محفوظة — الصفُّ لقطةُ وقتِ توليده.
 *
 * **الردُّ حمولةٌ كاملة**: كلُّ فعلٍ يُعيد قائمةَ النظام من الخادم فتُستبدل الحالة،
 * فلا تُحسب القائمة مرّتين في الواجهة والخادم.
 */
import React, { useCallback, useEffect, useState } from 'react';

import {
  createOfficeDocumentItem,
  getDocumentItems,
  setOfficeDocumentChoice,
  updateOfficeDocumentItem,
  type OfficeDocumentItemRow,
  type OfficeDocumentItemsPayload,
} from '../../services/accountingOfficeApi';
import { humanizeThrown } from '../../utils/drfError';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

interface DraftItem {
  name: string;
  cadence: string;
  service_codes: string[];
  is_active: boolean;
}

const EMPTY_DRAFT: DraftItem = {
  name: '',
  cadence: 'monthly',
  service_codes: [],
  is_active: true,
};

export const OfficeDocumentItemsSection: React.FC<{ system: string }> = ({ system }) => {
  const toast = useToast();
  const { can } = usePermissions();
  const canManage = can('office.settings.manage');
  const [payload, setPayload] = useState<OfficeDocumentItemsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<DraftItem>({ ...EMPTY_DRAFT });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getDocumentItems(system)
      .then(setPayload)
      .catch((failure) => setError(humanizeThrown(failure, 'تعذّر تحميل بنود الأوراق.')))
      .finally(() => setLoading(false));
  }, [system]);

  useEffect(() => {
    load();
  }, [load]);

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

  const toggle = async (item: OfficeDocumentItemRow) => {
    setBusy(true);
    try {
      if (item.is_custom) {
        // بندُ المكتب يُعطَّل بـ`is_active` ولا يُحذف — والتعطيلُ يوقف التوليد.
        if (item.id === null) return;
        setPayload(await updateOfficeDocumentItem(item.id, {
          is_active: !item.is_active,
        }));
      } else {
        // بندُ المنصّة لا يُعدَّل: «ضمن القائمة» صفُّ خيارٍ فوقه.
        setPayload(await setOfficeDocumentChoice({
          item_code: item.item_code,
          included: !item.included,
        }));
      }
      toast('حُفظ القالب', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حفظ القالب.'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const addItem = async () => {
    setBusy(true);
    try {
      const next = await createOfficeDocumentItem({
        system,
        name: draft.name,
        cadence: draft.cadence,
        service_codes: draft.service_codes,
        is_active: draft.is_active,
      });
      setPayload(next);
      setDraft({ ...EMPTY_DRAFT });
      toast('أُضيف البند', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إضافة البند.'), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p className="text-[11.5px] text-slate-500 dark:text-slate-400">
        بنداتُ الأوراق التي تُطلب من الزبائن في هذا النظام. خيارُ الزبون في ملفّه
        يغلب هذا القالب.
      </p>
      <ul className="mt-2 grid gap-1.5 md:grid-cols-2">
        {payload.items.map((item) => (
          <li
            key={item.item_code}
            className="flex items-center gap-2 rounded-md border border-slate-100 px-2 py-1 text-[11px] dark:border-slate-800"
          >
            <span className="font-medium text-slate-700 dark:text-slate-300">{item.name}</span>
            <span className="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[9px] font-semibold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              {item.cadence_label}
            </span>
            {item.is_custom ? (
              <span className="shrink-0 text-[9px] font-semibold text-teal-700 dark:text-teal-400">
                بند المكتب
              </span>
            ) : null}
            <button
              type="button"
              disabled={!canManage || busy}
              onClick={() => toggle(item)}
              aria-pressed={item.included}
              className={`ms-auto shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold disabled:opacity-50 ${
                item.included
                  ? 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300'
                  : 'border-slate-200 text-slate-500 dark:border-slate-700 dark:text-slate-400'
              }`}
            >
              {item.included ? 'ضمن القائمة' : 'خارج القائمة'}
            </button>
          </li>
        ))}
      </ul>

      {canManage ? (
        <div className="mt-3 grid gap-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800 md:grid-cols-2">
          <p className="md:col-span-2 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
            أضف بنداً للمكتب
          </p>
          <label className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
            الاسم
            <input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              className={`mt-1 w-full ${officeInputClass}`}
            />
          </label>
          <label className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
            الدورية
            <select
              value={draft.cadence}
              onChange={(event) => setDraft({ ...draft, cadence: event.target.value })}
              className={`mt-1 w-full ${officeInputClass}`}
            >
              {payload.cadence_choices.map((choice) => (
                <option key={choice.value} value={choice.value}>{choice.label}</option>
              ))}
            </select>
          </label>
          <fieldset className="md:col-span-2">
            <legend className="text-[10px] font-semibold text-slate-600 dark:text-slate-300">
              الخدمات (بلا خدمةٍ = لكل زبون)
            </legend>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
              {payload.services.map((service) => {
                const checked = draft.service_codes.includes(service.code);
                return (
                  <label
                    key={service.code}
                    className="flex items-center gap-1 text-[10.5px] text-slate-600 dark:text-slate-300"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => setDraft({
                        ...draft,
                        service_codes: checked
                          ? draft.service_codes.filter((code) => code !== service.code)
                          : [...draft.service_codes, service.code],
                      })}
                    />
                    {service.name}
                  </label>
                );
              })}
            </div>
          </fieldset>
          <div className="md:col-span-2 flex items-center gap-3">
            <label className="flex items-center gap-1 text-[10.5px] font-semibold text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={() => setDraft({ ...draft, is_active: !draft.is_active })}
              />
              مفعَّل
            </label>
            <button
              type="button"
              disabled={busy || !draft.name.trim()}
              onClick={addItem}
              className={officePrimaryButtonClass}
            >
              أضف البند
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
};
