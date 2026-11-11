/**
 * #280/ب — قسمُ «عطل المكتب» في إعدادات المكتب.
 *
 * **قائمةٌ يكتبها المكتب** لا تقويمَ عطلٍ وطنيّ يُخترَع: اليومُ المعطَّل يمنع
 * ظهورَ التذكيرات فيه، وتظهر في أوّل يومٍ مسموح بعده — لأن الحسابَ من السجلّ
 * لا من صفٍّ محفوظ. والحذفُ يمحو الصفَّ وحدَه، فلا تبقى عطلةٌ تُحجب بلا سبب.
 *
 * والقراءةُ لكل عضو، والكتابةُ بـ`office.settings.manage` — والخادمُ يرفض
 * التكرار 400 برسالته (فرادةٌ على اليوم نفسه).
 */
import React, { useCallback, useEffect, useState } from 'react';

import {
  createOfficeHoliday,
  deleteOfficeHoliday,
  getOfficeHolidays,
  type OfficeHolidayRow,
} from '../../services/accountingOfficeApi';
import { formatDateValue } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

export const OfficeHolidaysSection: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const canManage = can('office.settings.manage');
  const [rows, setRows] = useState<OfficeHolidayRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [date, setDate] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getOfficeHolidays()
      .then(setRows)
      .catch((failure) => setError(humanizeThrown(failure, 'تعذّر تحميل عطل المكتب.')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && rows === null) {
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

  const holidays = rows ?? [];

  const add = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!date) return;
    setBusy(true);
    try {
      const created = await createOfficeHoliday({ date, name: name.trim() || undefined });
      setRows(
        [...holidays, created].sort((left, right) => left.date.localeCompare(right.date)),
      );
      setDate('');
      setName('');
      toast('أُضيفت عطلة المكتب', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إضافة العطلة.'), 'error');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: OfficeHolidayRow) => {
    const ok = await confirm({
      title: 'حذف عطلة',
      message:
        `تُحذف عطلة ${formatDateValue(row.date)}، فتعود التذكيراتُ تظهر في ذلك اليوم `
        + 'إن حان وقتُها. لا يُمسّ سجلُّ تذكيرٍ سابق.',
      confirmText: 'احذف العطلة',
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteOfficeHoliday(row.id);
      setRows(holidays.filter((entry) => entry.id !== row.id));
      toast('حُذفت عطلة المكتب', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر حذف العطلة.'), 'error');
    }
  };

  return (
    <div>
      <p className="text-[11.5px] text-slate-500 dark:text-slate-400">
        يومٌ معطَّلٌ هنا لا تظهر فيه تذكيرات — تُؤجَّل إلى أوّل يومٍ مسموح بعده.
        لا تقويمَ عطلٍ تلقائيّ: المكتبُ يعطّل يومَه بيده.
      </p>

      {holidays.length === 0 ? (
        <p className="mt-2 text-[11.5px] text-slate-500 dark:text-slate-400">
          لا عطلةَ مسجّلة.
        </p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          {holidays.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-2 py-1.5">
              <span className="text-[11.5px] font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                {formatDateValue(row.date)}
              </span>
              {row.name ? (
                <span className="text-[11px] text-slate-500 dark:text-slate-400">{row.name}</span>
              ) : null}
              {canManage ? (
                <button
                  type="button"
                  onClick={() => remove(row)}
                  className="ms-auto text-[10.5px] font-medium text-rose-600 hover:underline dark:text-rose-400"
                >
                  احذف
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {canManage ? (
        <form onSubmit={add} className="mt-2 flex flex-wrap items-end gap-2">
          <label className="text-[10.5px] font-semibold text-slate-600 dark:text-slate-300">
            اليوم
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              required
              className={`${officeInputClass} mt-1 block tabular-nums`}
            />
          </label>
          <label className="text-[10.5px] font-semibold text-slate-600 dark:text-slate-300">
            الاسم (اختياري)
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="عيد، إجازة المكتب…"
              className={`${officeInputClass} mt-1 block w-48`}
            />
          </label>
          <button
            type="submit"
            disabled={busy || !date}
            className={officePrimaryButtonClass}
          >
            أضف عطلة
          </button>
        </form>
      ) : null}
    </div>
  );
};
