import React, { useCallback, useEffect, useState } from 'react';

import {
  getClientEvents,
  recordClientEvent,
  type ClientEventsPayload,
} from '../../services/accountingOfficeApi';
import { shortIsoDate } from '../../utils/accountingOffice';
import { formatDateValue } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import {
  OfficeCard,
  OfficeEmpty,
  OfficeSkeleton,
  officeInputClass,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/**
 * ISSUE #277 — «صار حدث» في ملفّ الزبون: تسجيلُ خبرٍ (اقتطاع ضريبة مصدر) وتواريخُه.
 *
 * **الحدثُ يولّد التزامَه خادمياً** من سطر `cadence="event"` في لائحة نظام الزبون:
 * اقتطاعٌ بتاريخ X ⇒ موعدٌ في X+30. والواجهةُ لا تحسب تاريخاً ولا تختار قاعدة —
 * النوعُ من `event_kinds` (المفعّلة في إعدادات المكتب)، والردُّ يحمل التزاماتِ
 * الحدث كما هي في تبويب الالتزامات.
 *
 * **و«التاريخ لا يُمحى»**: لا زرَّ حذفٍ ولا تعديل — تصحيحُ خبرٍ خبرٌ جديد، والقائمةُ
 * تسرد ما سُجّل بأحدث وقوعٍ أوّلاً. وإضافةُ نوعٍ ثانٍ لا تلمس هذا المكوّن.
 */
export const OfficeClientEvents: React.FC<{
  clientId: number;
  canWrite: boolean;
  /** يُنادى بعد تسجيلٍ ناجح: الشغلاتُ والالتزاماتُ تُقرأ من الخادم من جديد. */
  onRecorded: () => void;
  onError: (message: string) => void;
}> = ({ clientId, canWrite, onRecorded, onError }) => {
  const [payload, setPayload] = useState<ClientEventsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState({ kind: '', occurred_on: '', note: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    getClientEvents(clientId)
      .then(setPayload)
      .catch((failure) =>
        setError(humanizeThrown(failure, 'تعذّر تحميل أحداث الزبون.')),
      )
      .finally(() => setLoading(false));
  }, [clientId]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    setSaving(true);
    try {
      await recordClientEvent(clientId, {
        kind: draft.kind,
        occurred_on: draft.occurred_on,
        note: draft.note.trim(),
      });
      setDraft({ kind: '', occurred_on: '', note: '' });
      load();
      onRecorded();
    } catch (failure) {
      onError(humanizeThrown(failure, 'تعذّر تسجيل الحدث.'));
    } finally {
      setSaving(false);
    }
  };

  if (error) {
    return <OfficeCard title="الأحداث">
      <p className="text-[12px] font-medium text-rose-600 dark:text-rose-400">{error}</p>
      <button type="button" onClick={load} className={`mt-2 ${officeSecondaryButtonClass}`}>
        أعد المحاولة
      </button>
    </OfficeCard>;
  }
  if (loading && !payload) return <OfficeSkeleton rows={2} />;
  if (!payload) return null;

  const canRecord = canWrite && payload.event_kinds.length > 0;

  return (
    <OfficeCard title="الأحداث">
      <p className="text-[11.5px] text-slate-500 dark:text-slate-400">
        خبرٌ واحدٌ يولّد التزامَه من لائحة نظام الزبون — والتاريخُ المسجَّل لا يُمحى.
      </p>

      {canRecord ? (
        <div className="mt-3 flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            النوع
            <select
              value={draft.kind}
              onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
              className={`${officeInputClass} mt-1 block`}
            >
              <option value="">— اختر —</option>
              {payload.event_kinds.map((kind) => (
                <option key={kind.value} value={kind.value}>
                  {kind.label}
                </option>
              ))}
            </select>
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            تاريخ الحدث
            <input
              type="date"
              value={draft.occurred_on}
              onChange={(event) => setDraft({ ...draft, occurred_on: event.target.value })}
              className={`${officeInputClass} mt-1 block`}
            />
          </label>
          <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300">
            ملاحظة (اختيارية)
            <input
              value={draft.note}
              onChange={(event) => setDraft({ ...draft, note: event.target.value })}
              className={`${officeInputClass} mt-1 block w-48`}
            />
          </label>
          <button
            type="button"
            disabled={saving || !draft.kind || !draft.occurred_on}
            onClick={submit}
            className={officePrimaryButtonClass}
          >
            سجّل الحدث
          </button>
        </div>
      ) : null}

      {payload.events.length === 0 ? (
        <div className="mt-3">
          <OfficeEmpty title="لا أحداث مسجَّلة" hint="سجّل الخبرَ حين يقع فيظهر التزامُه بموعده." />
        </div>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
          {payload.events.map((event) => (
            <li key={event.id} className="py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  {event.kind_label}
                </span>
                <span className="text-[11.5px] font-semibold tabular-nums text-slate-800 dark:text-slate-100">
                  {formatDateValue(event.occurred_on)}
                </span>
                {event.note ? (
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    {event.note}
                  </span>
                ) : null}
                {event.created_by_name ? (
                  <span className="text-[10.5px] text-slate-400 dark:text-slate-500">
                    سجّله {event.created_by_name}
                  </span>
                ) : null}
              </div>
              {event.obligations.length > 0 ? (
                <ul className="mt-1 space-y-0.5">
                  {event.obligations.map((obligation) => (
                    <li
                      key={obligation.id}
                      className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600 dark:text-slate-300"
                    >
                      <span className="font-semibold">{obligation.name}</span>
                      <span className="tabular-nums text-slate-500 dark:text-slate-400">
                        فعلي {shortIsoDate(obligation.actual_deadline)}
                      </span>
                      <span className="text-slate-400 dark:text-slate-500">
                        {obligation.status_label}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </OfficeCard>
  );
};
