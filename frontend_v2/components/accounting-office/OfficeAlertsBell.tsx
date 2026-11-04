import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';

import {
  getOfficeAlerts,
  markAllOfficeAlertsSeen,
  markOfficeAlertSeen,
  type OfficeAlertRow,
  type OfficeAlertsPayload,
} from '../../services/accountingOfficeApi';
import {
  alertTargetPath,
  obligationBadgeClass,
  shortIsoDate,
} from '../../utils/accountingOffice';
import { formatNumber } from '../../utils/formatNumber';
import { humanizeThrown } from '../../utils/drfError';
import { moduleAllowsView } from '../../utils/viewPermissions';
import { usePermissions } from '../../contexts/PermissionsContext';

/** كلَّ خمس دقائق — الجرسُ لا يستحقّ استطلاعاً أسرع من ذلك. */
const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

/**
 * ISSUE #276 — جرسُ التنبيهات الداخلية في الشريط العلوي.
 *
 * **كلُّ عضوٍ يرى تنبيهاته هو فقط** (الخادمُ يحسمها بـ`recipient=user`)، والقراءةُ
 * تُسقط المحسوم، فالعدّادُ الأحمرُ صادقٌ بلا تصفيةٍ هنا. والنقرُ يعلّم «شفته»
 * **ثم** يفتح مكانَه: ملفّ الزبون على تبويب «الالتزامات والشغلات»
 * (`alertTargetPath`)، فالتنبيهُ يحمل مكانَه لا محتواه.
 *
 * **ولا يظهر إلا لمكتبِ محاسبةٍ مرخَّص**: الشرطُ هو مصدرُ الترخيص القائم نفسه
 * (`VIEW_MODULES` في `utils/viewPermissions.ts` — الشاشةُ نفسُها عامرُها)، فلا
 * شرطَ ثانٍ يُخترع هنا. وهو **بجانب** `NotificationCenter` ولا يمسّه: ذاك
 * إشعاراتُ الموقع، وهذا تنبيهاتُ المكتب.
 *
 * والحالاتُ: تحميلٌ أوّل، وخطأٌ بزرّ «أعد المحاولة»، وفراغ. والجلبُ عند التركيب
 * وكلَّ خمس دقائق وعند عودة التركيز للنافذة وبعد كل «شفته»؛ وردُّ طلبٍ قديمٍ لا
 * يكتب فوق أحدث منه (عدّادُ طلبات).
 */
export const OfficeAlertsBell: React.FC = () => {
  const navigate = useNavigate();
  const { modules } = usePermissions();
  // المصدرُ القائم لقرار الترخيص — لا شرطَ جديد.
  const licensed = moduleAllowsView('office-today', modules);
  const [payload, setPayload] = useState<OfficeAlertsPayload | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [marking, setMarking] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const requestRef = useRef(0);

  const load = useCallback(() => {
    const token = requestRef.current + 1;
    requestRef.current = token;
    setLoading(true);
    getOfficeAlerts()
      .then((data) => {
        if (requestRef.current !== token) return;
        setPayload(data);
        setError('');
      })
      .catch((failure) => {
        if (requestRef.current !== token) return;
        setError(humanizeThrown(failure, 'تعذّر تحميل التنبيهات.'));
      })
      .finally(() => {
        if (requestRef.current === token) setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!licensed) return undefined;
    load();
    const timer = window.setInterval(load, REFRESH_INTERVAL_MS);
    const onFocus = () => load();
    window.addEventListener('focus', onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
      // ردٌّ وصل بعد المغادرة لا يكتب شيئاً.
      requestRef.current += 1;
    };
  }, [licensed, load]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [open]);

  if (!licensed) return null;

  const unseen = payload?.unseen ?? 0;
  const rows = payload?.rows ?? [];

  const openAlert = async (alert: OfficeAlertRow) => {
    setOpen(false);
    if (!alert.seen) {
      try {
        await markOfficeAlertSeen(alert.id);
      } catch {
        // الفتحُ لا يُحبَس على تسجيل الشوفة — والقراءةُ التالية تُصحّح العدّاد.
      }
      load();
    }
    const target = alertTargetPath(alert);
    if (target) navigate(target);
  };

  const markAll = async () => {
    setMarking(true);
    try {
      await markAllOfficeAlertsSeen();
    } catch (failure) {
      setError(humanizeThrown(failure, 'تعذّر تعليم التنبيهات.'));
    } finally {
      setMarking(false);
    }
    load();
  };

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => {
          setOpen((value) => !value);
          if (!open) load();
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        title="تنبيهات المكتب"
        aria-label={
          unseen > 0
            ? `تنبيهات المكتب (${formatNumber(unseen, { maxDecimals: 0 })} غير مرئيّ)`
            : 'تنبيهات المكتب'
        }
        className="relative flex items-center justify-center rounded-md p-1.5 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
      >
        <Bell className="h-4 w-4" />
        {unseen > 0 ? (
          <span
            data-testid="office-alerts-count"
            className="absolute -top-1 -end-1 flex min-w-4 items-center justify-center rounded-full bg-rose-600 px-1 text-[10px] font-bold leading-4 text-white"
          >
            {formatNumber(unseen, { maxDecimals: 0 })}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="تنبيهات المكتب"
          className="absolute end-0 z-[60] mt-2 w-80 max-w-[90vw] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          <header className="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-700">
            <span className="text-[12.5px] font-bold text-slate-900 dark:text-slate-100">
              تنبيهات المكتب
            </span>
            <button
              type="button"
              onClick={markAll}
              disabled={marking || unseen === 0}
              className="text-[11px] font-semibold text-teal-700 disabled:opacity-40 dark:text-teal-300"
            >
              شفتهم كلهم
            </button>
          </header>

          <div className="max-h-80 overflow-y-auto">
            {loading && payload === null ? (
              <p className="px-3 py-4 text-[11.5px] text-slate-500 dark:text-slate-400">
                جاري التحميل…
              </p>
            ) : null}

            {error ? (
              <div className="px-3 py-3">
                <p className="text-[11.5px] font-semibold text-rose-700 dark:text-rose-300">
                  {error}
                </p>
                <button
                  type="button"
                  onClick={load}
                  className="mt-2 rounded-lg border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-700 dark:border-slate-700 dark:text-slate-200"
                >
                  أعد المحاولة
                </button>
              </div>
            ) : null}

            {!error && !loading && rows.length === 0 ? (
              <p className="px-3 py-6 text-center text-[11.5px] text-slate-500 dark:text-slate-400">
                لا تنبيهات — كل شيء في وقته.
              </p>
            ) : null}

            {rows.map((alert) => (
              <button
                key={alert.id}
                type="button"
                role="menuitem"
                onClick={() => openAlert(alert)}
                className="block w-full border-b border-slate-100 px-3 py-2 text-start last:border-b-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
              >
                <span className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={`rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${obligationBadgeClass(alert.badge)}`}
                  >
                    {alert.kind_label}
                  </span>
                  <span className="text-[10px] tabular-nums text-slate-400 dark:text-slate-500">
                    {shortIsoDate(alert.day)}
                  </span>
                </span>
                <span
                  className={`mt-1 block text-[11.5px] ${
                    alert.seen
                      ? 'text-slate-600 dark:text-slate-300'
                      : 'font-semibold text-slate-900 dark:text-slate-100'
                  }`}
                >
                  {alert.message}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};
