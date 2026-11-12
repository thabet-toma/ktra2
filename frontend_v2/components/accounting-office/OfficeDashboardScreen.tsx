import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  approveAllFeeDrafts,
  getOfficeDashboard,
  type DashboardPayload,
  type DashboardWaitingGroup,
} from '../../services/accountingOfficeApi';
import {
  ALERT_OPENS_DEADLINE_RULES,
  DASHBOARD_ACTION_APPROVE_ALL,
  DASHBOARD_ACTION_OPEN_DEADLINE_RULES,
  DASHBOARD_ACTION_OPEN_READY_TO_SEND,
  OFFICE_READY_TO_SEND_PATH,
  alertTargetPath,
  clientsOfResponsiblePath,
  dashboardThresholdHint,
} from '../../utils/accountingOffice';
import { formatDateLocalized } from '../../utils/formatDate';
import { formatMoney } from '../../utils/formatNumber';
import { humanizeThrown } from '../../utils/drfError';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/**
 * ISSUE #289 — لوحةُ صاحب المكتب: «كم على المكتب، ومن متأخّر، وما ينتظرني».
 *
 * **كلُّ رقمٍ من الخادم**: `due_total` مجموعُ «اللي عليه» من الدالّة الواحدة
 * (`payments.client_due`)، و`late_total` والاحمرارُ يُحسبان هناك بعتبتين من
 * سجلّ الإعدادات — فالشاشةُ ترسم ولا تعيد حساباً، وتغييرُ العتبة يغيّر اللونَ
 * بلا نشرِ واجهة.
 *
 * **والقناعُ في المفتاح لا في شرطٍ هنا**: من لا يرى المبالغ يصل `due_total`
 * `null` فتُعرض «—» بـ`formatMoney(value, '—')` — لا `if` على صلاحية في الواجهة،
 * ولا رقمٌ يُحسب ويُخفى.
 *
 * **والصفُّ الأحمرُ للمالك، والكبسةُ تفتح زبائنَه**: الجدولُ توزيعٌ لا تقرير،
 * فكبسةُ اسم الموظف تفتح قائمةَ زبائنه مقيَّدةً به (`?responsible=`) — ومنها
 * ملفُّ الزبون و«حوّل الزبون» القائم.
 *
 * **ولا جدولَ في مكتب شخصٍ واحد**: `single_person` من الخادم (حجمُ المكتب
 * المختار)، والواجهةُ تقرأ العلمَ ولا تستنتجه من عدد الصفوف.
 */
export const OfficeDashboardScreen: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);
  // اعتمادُ الكلّ فعلٌ واحدٌ طويلُ الأثر — يُقفل زرَّه حتى يردّ الخادم.
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getOfficeDashboard()
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((failure) => {
        if (!cancelled) {
          // لا تُعرض أرقامُ طلبٍ سابقٍ مع رسالة الفشل.
          setPayload(null);
          setError(humanizeThrown(failure, 'تعذّر تحميل لوحة المكتب.'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  const reload = useCallback(() => setRefreshToken((token) => token + 1), []);

  const approveAll = useCallback(async () => {
    setApproving(true);
    try {
      const result = await approveAllFeeDrafts();
      toast(`اعتُمدت ${result.approved} مسودّة`, 'success');
      reload();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر اعتماد المسودّات.'), 'error');
    } finally {
      setApproving(false);
    }
  }, [reload, toast]);

  /** فعلُ مجموعةٍ في «بانتظارك» — المفتاحُ من الخادم، والوجهةُ من `utils`. */
  const runAction = useCallback(
    (group: DashboardWaitingGroup) => {
      if (group.action === DASHBOARD_ACTION_APPROVE_ALL) {
        approveAll();
        return;
      }
      if (group.action === DASHBOARD_ACTION_OPEN_READY_TO_SEND) {
        navigate(OFFICE_READY_TO_SEND_PATH);
        return;
      }
      if (group.action === DASHBOARD_ACTION_OPEN_DEADLINE_RULES) {
        // الوجهةُ من `alertTargetPath` نفسِها — لا نسخةً ثانيةً لبناء `?group=`.
        navigate(alertTargetPath({ client: null, opens: ALERT_OPENS_DEADLINE_RULES }));
      }
    },
    [approveAll, navigate],
  );

  const actionLabel = (group: DashboardWaitingGroup): string => {
    if (group.action === DASHBOARD_ACTION_APPROVE_ALL) {
      return approving ? 'جاري الاعتماد…' : 'اعتمد الكل';
    }
    if (group.action === DASHBOARD_ACTION_OPEN_READY_TO_SEND) return 'افتح «جاهز للإرسال»';
    if (group.action === DASHBOARD_ACTION_OPEN_DEADLINE_RULES) return 'افتح لائحة المواعيد';
    return '';
  };

  if (loading && !payload) return <OfficeSkeleton rows={4} />;
  if (error) return <OfficeError message={error} onRetry={reload} />;
  if (!payload) return <OfficeEmpty title="لا بيانات لهذا المكتب بعد" />;

  const { staff, waiting, thresholds } = payload;

  return (
    <div className="space-y-4">
      <header className="rounded-xl border border-slate-200 bg-white p-4 md:p-5 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-bold text-slate-900 dark:text-slate-100">
              لوحة المكتب
            </h1>
            <p className="mt-1 text-[12px] text-slate-500 dark:text-slate-400">
              {payload.day ? `${formatDateLocalized(payload.day)} — ` : ''}
              ما على المكتب، ومن متأخّر، وما ينتظرك.
            </p>
          </div>
          <button type="button" onClick={reload} className={officeSecondaryButtonClass}>
            حدّث
          </button>
        </div>

        {/* الرقمان الكبيران — و«—» حين يُقنَّع المبلغ (لا يملك العضو رؤيتَه). */}
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 dark:border-amber-900 dark:bg-amber-950/40">
            <span className="block text-[10.5px] font-medium text-amber-800 dark:text-amber-300">
              اللي عليه المكتب
            </span>
            <span className="mt-0.5 block text-[24px] font-bold leading-8 tabular-nums text-amber-900 dark:text-amber-200">
              {formatMoney(payload.due_total, '—')}
            </span>
          </div>
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 dark:border-rose-900 dark:bg-rose-950/40">
            <span className="block text-[10.5px] font-medium text-rose-800 dark:text-rose-300">
              متأخّر (التزامات وشغلات)
            </span>
            <span className="mt-0.5 block text-[24px] font-bold leading-8 tabular-nums text-rose-900 dark:text-rose-200">
              {payload.late_total}
            </span>
          </div>
        </div>
      </header>

      {/* #289: «بانتظارك» — كلُّ مجموعةٍ بعدّادها وفعلها، ومنها «اعتمد الكل»
          على المسودّات عبر النقطة القائمة (`fees/drafts/approve-all/`). */}
      <OfficeCard
        title="بانتظارك"
        actions={
          waiting.total > 0 ? (
            <span className="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-teal-800 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-300">
              {waiting.total}
            </span>
          ) : null
        }
      >
        {waiting.groups.length === 0 ? (
          <p className="text-[12px] text-slate-500 dark:text-slate-400">
            لا شيء ينتظرك الآن — لا مسودّاتٍ ولا تصعيداتٍ ولا تغييرَ لائحة.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {waiting.groups.map((group) => (
              <li
                key={group.kind}
                className="flex flex-wrap items-center justify-between gap-2 py-2.5"
              >
                <span className="min-w-0">
                  <span className="block text-[12.5px] font-semibold text-slate-800 dark:text-slate-100">
                    {group.label}
                  </span>
                  <span className="mt-0.5 block text-[11px] font-medium tabular-nums text-slate-500 dark:text-slate-400">
                    {group.count}
                  </span>
                </span>
                {group.action ? (
                  <button
                    type="button"
                    onClick={() => runAction(group)}
                    disabled={approving && group.action === DASHBOARD_ACTION_APPROVE_ALL}
                    className={officePrimaryButtonClass}
                  >
                    {actionLabel(group)}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </OfficeCard>

      {/* الجدولُ لمن يوزّع: مكتبُ شخصٍ واحدٍ لا صفوفَ فيه. */}
      {payload.single_person ? (
        <OfficeCard title="الموظفون">
          <p className="text-[12px] text-slate-500 dark:text-slate-400">
            مكتبُ شخصٍ واحد — لا جدولَ توزيع. زبائنُ المكتب كلُّهم عليك.
          </p>
        </OfficeCard>
      ) : (
        <OfficeCard title="الموظفون">
          {staff.length === 0 ? (
            <OfficeEmpty
              title="لا موظفين بعد"
              hint="أضف زبوناً ليظهر صاحبه في هذا الجدول."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-right text-[12px]">
                  <thead>
                    <tr className="border-b border-slate-200 text-[11px] text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      <th scope="col" className="py-1.5 font-medium">الموظف</th>
                      <th scope="col" className="py-1.5 font-medium tabular-nums">الزبائن</th>
                      <th scope="col" className="py-1.5 font-medium tabular-nums">متأخّر</th>
                      <th scope="col" className="py-1.5 font-medium tabular-nums">ناقصه أوراق</th>
                      <th scope="col" className="py-1.5 font-medium tabular-nums">عليهم مال</th>
                    </tr>
                  </thead>
                  <tbody>
                    {staff.map((row) => (
                      <tr
                        key={row.id}
                        className={
                          row.red
                            ? 'border-b border-rose-100 bg-rose-50 text-rose-800 last:border-b-0 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200'
                            : 'border-b border-slate-100 text-slate-700 last:border-b-0 dark:border-slate-800 dark:text-slate-200'
                        }
                      >
                        <td className="py-2">
                          <button
                            type="button"
                            onClick={() => navigate(clientsOfResponsiblePath(row.id))}
                            aria-label={`زبائن ${row.name}`}
                            className="font-semibold underline-offset-2 hover:underline"
                          >
                            {row.name}
                          </button>
                        </td>
                        <td className="py-2 tabular-nums">{row.clients}</td>
                        <td className="py-2 font-semibold tabular-nums">{row.late}</td>
                        <td className="py-2 tabular-nums">{row.missing_docs}</td>
                        <td className="py-2 tabular-nums">{row.overdue_clients}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[10.5px] text-slate-500 dark:text-slate-400">
                {dashboardThresholdHint(thresholds)}
              </p>
            </>
          )}
        </OfficeCard>
      )}
    </div>
  );
};
