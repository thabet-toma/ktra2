import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  createFullOfficeExportLink,
  createOfficeClientNamesReport,
  dismissSelfObligation,
  downloadFullOfficeExport,
  listSelfObligations,
  submitSelfObligation,
  type OfficeSelfObligationRow,
  type OfficeSelfObligationsPayload,
} from '../../services/accountingOfficeApi';
import { humanizeThrown } from '../../utils/drfError';
import { formatDateValue, todayIso } from '../../utils/formatDate';
import {
  OFFICE_OWNER_ROLE,
  SELF_OBLIGATION_STATUS_PENDING,
  selfObligationDueText,
  selfObligationStatusClass,
} from '../../utils/accountingOffice';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/** دورُ مدير المكتب (`core/access.OFFICE_MANAGER_ROLE`) — شريكُ المالك في الحارس. */
const OFFICE_MANAGER_ROLE = 'office_manager';
/** المفتاحان اللذان يشترطهما الخادم فوق الدور — بأسمائها الخادمية. */
const CLIENTS_ALL_KEY = 'office.clients.all';
const AMOUNTS_VIEW_KEY = 'office.amounts.view';
/** نظامُ فلسطين وحده: بيانُ الأسماء (م111) لا نظيرَ له في النظام الإسرائيلي. */
const TAX_SYSTEM_PS = 'PS';

/** تنزيلُ بايتاتٍ باسمٍ صريح — كما في مستخرجات دفتر الزبون. */
const saveBlob = (blob: Blob, fileName: string): void => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
};

/**
 * «التشغيل والنسخ» (#290) — نسخةُ بيانات المكتب وبيانُ الأسماء والتزاماتُه هو.
 *
 * **الحارسُ دورٌ ومفتاحان معاً، والشاشةُ تعلنه بدل زرٍّ يردّ 403**: نفسُ شروط
 * `office_exports.missing_owner_permissions` — دورٌ في `ENTRY_APPROVER_ROLES`
 * (المالك أو مديرُ المكتب)، ومفتاحُ «يرى زبائن غيره»، ورؤيةُ المبالغ (النسخةُ
 * تحمل مبالغَ كل الزبائن). ومن نقصه أحدُ الثلاثة يقرأ **لماذا** لا يجد زرّاً
 * صامتاً ولا رفضاً بلا سبب.
 *
 * **والبيانُ الفلسطينيّ يُعلن نظامَه**: زرُّ «بيان الأسماء» يظهر لمكتب `PS`
 * وحده، وغيره يقرأ سطراً يقول إن النموذج فلسطينيّ — لا زرٌّ مصيرُه 400.
 *
 * **والتزاماتُ المكتب نفسِه** سجلٌّ مستقلّ عن التزامات الزبائن: تُقرأ لكل عضو
 * (موعدُ المكتب ليس سرّاً)، وتُكتب بالدور، و`can_write` يرسله الخادم فتظهر
 * الأزرار لمن يملكها وحده.
 */
export const OfficeOperationsSection: React.FC<{
  taxSystem: string | null | undefined;
}> = ({ taxSystem }) => {
  const toast = useToast();
  const { role, can } = usePermissions();
  const [payload, setPayload] = useState<OfficeSelfObligationsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [reloadToken, setReloadToken] = useState(0);

  /** ما ينقص هذا العضو ليكون مالكاً بهذا المعنى — قائمةُ أسبابٍ لا بوليان. */
  const blockedReasons = useMemo(() => {
    const reasons: string[] = [];
    if (role !== OFFICE_OWNER_ROLE && role !== OFFICE_MANAGER_ROLE) {
      reasons.push('دورُك ليس صاحبَ المكتب ولا مديرَه');
    }
    if (!can(CLIENTS_ALL_KEY)) reasons.push('مفتاحُ «يرى زبائن غيره» غيرُ ممنوحٍ لدورك');
    if (!can(AMOUNTS_VIEW_KEY)) reasons.push('صلاحيةُ «يرى المبالغ» غيرُ ممنوحةٍ لدورك');
    return reasons;
  }, [can, role]);
  const isOwner = blockedReasons.length === 0;

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    listSelfObligations()
      .then(setPayload)
      .catch((failure) => {
        setError(humanizeThrown(failure, 'تعذّر تحميل التزامات المكتب.'));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load, reloadToken]);

  const replaceRow = (updated: OfficeSelfObligationRow) => {
    setPayload((current) => (
      current === null
        ? current
        : {
          ...current,
          rows: current.rows.map((row) => (row.id === updated.id ? updated : row)),
          pending: current.rows.filter(
            (row) => (row.id === updated.id ? updated : row).status === SELF_OBLIGATION_STATUS_PENDING,
          ).length,
        }
    ));
  };

  const submitRow = async (row: OfficeSelfObligationRow) => {
    setBusy(`submit:${row.id}`);
    try {
      replaceRow(await submitSelfObligation(row.id));
      toast('سُجِّل تقديمُ البند', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تسجيل التقديم.'), 'error');
    } finally {
      setBusy('');
    }
  };

  const dismissRow = async (row: OfficeSelfObligationRow) => {
    setBusy(`dismiss:${row.id}`);
    try {
      replaceRow(await dismissSelfObligation(row.id));
      toast('أُسقِط البند كغير مطلوب', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إسقاط البند.'), 'error');
    } finally {
      setBusy('');
    }
  };

  const exportFull = async () => {
    setBusy('full');
    try {
      const blob = await downloadFullOfficeExport();
      // #290: اسمُ الملفّ بتاريخ اليوم المحليّ — `toISOString` تعطي UTC فينزاح
      // الاسم يوماً في المناطق الزمنية الموجبة بعد منتصف الليل.
      saveBlob(blob, `office-data-${todayIso()}.xlsx`);
      toast('نُزِّلت نسخةُ بيانات المكتب', 'success');
      // أخذُ النسخة يُسكِت تذكيرَ الشهر — نُعيد قراءةَ القائمة بعدها.
      setReloadToken((token) => token + 1);
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر تصدير بيانات المكتب.'), 'error');
    } finally {
      setBusy('');
    }
  };

  const shareLink = async (kind: 'full' | 'names') => {
    setBusy(kind);
    try {
      const link = kind === 'full'
        ? await createFullOfficeExportLink()
        : await createOfficeClientNamesReport();
      await navigator.clipboard?.writeText(link.url).catch(() => undefined);
      window.open(link.url, '_blank', 'noopener');
      toast('أُنشئ الرابط وفُتح في نافذةٍ جديدة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إنشاء الرابط.'), 'error');
    } finally {
      setBusy('');
    }
  };

  const rows = payload?.rows ?? [];

  return (
    <div className="space-y-4">
      <section>
        <h3 className="text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
          نسخة بيانات المكتب
        </h3>
        {isOwner ? (
          <>
            <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              مصنَّفُ Excel بتسع أوراقٍ: الزباين والبطاقات والخدمات والالتزامات والأوراق
              وسجلّ التذكيرات والفواتير والدفعات والدفاتر — ورابطُ PDF للنسخة نفسها.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void exportFull()}
                disabled={busy === 'full'}
                className={officePrimaryButtonClass}
              >
                {busy === 'full' ? 'يُصدَّر…' : 'صدّر بيانات المكتب كاملة'}
              </button>
              <button
                type="button"
                onClick={() => void shareLink('full')}
                disabled={busy === 'full'}
                className={officeSecondaryButtonClass}
              >
                رابط PDF للنسخة
              </button>
              {taxSystem === TAX_SYSTEM_PS ? (
                <button
                  type="button"
                  onClick={() => void shareLink('names')}
                  disabled={busy === 'names'}
                  className={officeSecondaryButtonClass}
                >
                  بيان أسماء الزبائن (م111)
                </button>
              ) : null}
            </div>
            {taxSystem === TAX_SYSTEM_PS ? null : (
              <p className="mt-2 text-[11px] font-medium text-amber-800 dark:text-amber-300">
                بيانُ أسماء الزبائن (م111) نموذجُ الدائرة الفلسطينية — لا يُصدر
                لمكتبٍ على نظامٍ آخر.
              </p>
            )}
          </>
        ) : (
          <p className="mt-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11.5px] text-slate-600 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-300">
            النسخةُ الكاملةُ للمالك وحده: {blockedReasons.join(' · ')}. التصديرُ
            يحمل زبائنَ المكتب كلَّهم ومبالغَهم، فطلبُه الآن يردّه الخادم 403.
          </p>
        )}
      </section>

      <div className="border-t border-slate-100 dark:border-slate-800" />

      <section>
        <h3 className="text-[12.5px] font-bold text-slate-800 dark:text-slate-100">
          التزامات المكتب نفسه
        </h3>
        <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
          التزاماتٌ تفرضها أنظمةُ المكتب عليه لا على زبائنِه — تُولَّد من المنصّة
          بحسب نظامه الضريبيّ.
        </p>
        {error ? (
          <div className="mt-2">
            <OfficeError message={error} onRetry={load} />
          </div>
        ) : loading && payload === null ? (
          <div className="mt-2">
            <OfficeSkeleton rows={2} />
          </div>
        ) : rows.length === 0 ? (
          <div className="mt-2">
            <OfficeEmpty
              title="لا التزامَ على المكتب نفسه"
              hint="لا بندَ ينطبق على نظام هذا المكتب الآن."
            />
          </div>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((row) => (
              <li key={row.id} className="py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                    {row.name}
                  </span>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    {row.source_label}
                  </span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${selfObligationStatusClass(row.status)}`}
                  >
                    {row.status_label}
                  </span>
                  <span className="ms-auto text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
                    الموعد: {formatDateValue(row.due_on)}
                    {selfObligationDueText(row)
                      ? ` · ${selfObligationDueText(row)}`
                      : ''}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  الفترة: {formatDateValue(row.period_start)} — {formatDateValue(row.period_end)}
                  {row.submitted_on ? ` · قُدِّم في ${formatDateValue(row.submitted_on)}` : ''}
                  {row.note ? ` · ${row.note}` : ''}
                </p>
                {payload?.can_write && row.status === SELF_OBLIGATION_STATUS_PENDING ? (
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void submitRow(row)}
                      disabled={busy === `submit:${row.id}`}
                      className={officeSecondaryButtonClass}
                    >
                      قُدِّم
                    </button>
                    <button
                      type="button"
                      onClick={() => void dismissRow(row)}
                      disabled={busy === `dismiss:${row.id}`}
                      className={officeSecondaryButtonClass}
                    >
                      غير مطلوب
                    </button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};
