import React, { useCallback, useEffect, useMemo, useState } from 'react';

import {
  approveAllFeeDrafts,
  approveFeeDraft,
  cancelFeeDraft,
  listFeeDrafts,
  type FeeDraftRow,
} from '../../services/accountingOfficeApi';
import {
  FEE_DRAFT_FILTERS,
  feeDraftActions,
  feeDraftStatusClass,
  filterFeeDrafts,
  formatOfficeAmount,
  pendingFeeDraftCount,
  type FeeDraftFilter,
} from '../../utils/accountingOffice';
import { formatDateValue } from '../../utils/formatDate';
import { humanizeThrown } from '../../utils/drfError';
import { useConfirm } from '../../contexts/ConfirmContext';
import { usePermissions } from '../../contexts/PermissionsContext';
import { useToast } from '../../contexts/ToastContext';
import {
  OfficeCard,
  OfficeEmpty,
  OfficeError,
  OfficeSkeleton,
  officePrimaryButtonClass,
  officeSecondaryButtonClass,
} from './OfficeUi';

/** الأدوارُ التي تعتمد المسودّات — `fees.FEE_APPROVER_ROLES` في الخادم. */
const APPROVER_ROLES: readonly string[] = ['manager', 'office_manager'];

/**
 * ISSUE #282/أ٢/٢ — شاشةُ «المسودّات»: قائمةُ مسودّات الأتعاب وأفعالُها.
 *
 * **ثلاثةُ أفعالٍ لا غير، وكلُّها نقاطٌ قائمة**: «اعتمد» (`approve/`)، «اعتمد
 * الكل» (`approve-all/`)، «أَلغِها» (`cancel/`). والاعتمادُ يُصدر الورقةَ
 * المرقَّمة وقيدَها في المعاملة نفسها، فبطاقةُ الورقة تصل في **ردّ الاعتماد**
 * نفسِه (`invoice`) فلا جلبٌ ثانٍ لإظهار الرقم والتاريخ والرابط.
 *
 * **والحالةُ تُقرأ من `status` وتُعرَض بـ`status_label`**: لا تسميةَ حالةٍ في
 * الواجهة. والأزرارُ تتبع `feeDraftActions` (مسودّةٌ وحدها تُعتمد وتُلغى) —
 * إخفاءُ زرٍّ مصيرُه 400، والحكمُ النهائيُّ للخادم على أيّ حال.
 *
 * **والفلترةُ عرضٌ لا طلب**: القائمةُ تُقرأ كاملةً (`fees/drafts/` بلا فلاتر)
 * فتصفيةُ الحالة في الذاكرة — قائمةُ المكتب في الشهر الواحد عشراتٌ لا آلاف.
 */
export const OfficeFeeDraftsScreen: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const { role } = usePermissions();
  const canApprove = APPROVER_ROLES.includes(role);
  const [rows, setRows] = useState<FeeDraftRow[]>([]);
  const [filter, setFilter] = useState<FeeDraftFilter>('draft');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);
  /** الصفُّ الذي يجري عليه فعلٌ الآن — يُعطّل أزرارَه وحدها. */
  const [busyId, setBusyId] = useState<number | null>(null);
  const [approvingAll, setApprovingAll] = useState(false);

  const reload = useCallback(() => setRefreshToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    listFeeDrafts()
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((failure) => {
        if (!cancelled) setError(humanizeThrown(failure, 'تعذّر تحميل المسودّات.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  /** ردُّ الفعل يحمل الصفَّ بحالته الجديدة، فيُستبدل موضعُه بلا إعادة قراءة. */
  const replaceRow = (row: FeeDraftRow) => {
    setRows((previous) => previous.map((item) => (item.id === row.id ? row : item)));
  };

  const pending = useMemo(() => pendingFeeDraftCount(rows), [rows]);
  const visible = useMemo(() => filterFeeDrafts(rows, filter), [rows, filter]);

  const approve = async (row: FeeDraftRow) => {
    setBusyId(row.id);
    try {
      const updated = await approveFeeDraft(row.id);
      replaceRow(updated);
      toast(
        updated.invoice
          ? `اعتُمدت المسودّة وأُصدرت الفاتورة ${updated.invoice.number}`
          : 'اعتُمدت المسودّة وأُصدرت فاتورتها',
        'success',
      );
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر اعتماد المسودّة.'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  const approveAll = async () => {
    if (!pending) return;
    const ok = await confirm({
      title: 'اعتماد كل المسودّات المنتظرة',
      message:
        `تُعتمد ${pending} مسودّةً ويُصدر لكلٍّ ورقتُها برقمٍ متسلسل، ولا تُلمَس `
        + 'المعتمدةُ ولا الملغاة. اعتمادُ مسودّةٍ يصير دَيناً على الزبون.',
      confirmText: 'اعتمد الكل',
    });
    if (!ok) return;
    setApprovingAll(true);
    try {
      const result = await approveAllFeeDrafts();
      toast(
        result.approved
          ? `اعتُمدت ${result.approved} مسودّةً — بقي ${result.remaining} منتظرة`
          : 'لا مسودّات منتظرة',
        result.approved ? 'success' : 'info',
      );
      reload();
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر اعتماد المسودّات.'), 'error');
    } finally {
      setApprovingAll(false);
    }
  };

  const cancel = async (row: FeeDraftRow) => {
    const ok = await confirm({
      title: 'إلغاء المسودّة',
      message:
        `تُلغى مسودّة «${row.client.name}» لـ${row.period_label} وتبقى في التاريخ. `
        + 'لا يُلغى شيءٌ أُصدر: الورقةُ المرقَّمة تُصحَّح بإشعارٍ دائن.',
      confirmText: 'أَلغِها',
      danger: true,
    });
    if (!ok) return;
    setBusyId(row.id);
    try {
      replaceRow(await cancelFeeDraft(row.id));
      toast('أُلغيت المسودّة', 'success');
    } catch (failure) {
      toast(humanizeThrown(failure, 'تعذّر إلغاء المسودّة.'), 'error');
    } finally {
      setBusyId(null);
    }
  };

  if (error) {
    return <OfficeError message={error} onRetry={reload} />;
  }

  return (
    <div className="space-y-4">
      <OfficeCard
        title="مسودّات الأتعاب"
        actions={
          canApprove ? (
            <button
              type="button"
              onClick={approveAll}
              disabled={!pending || approvingAll}
              className={officePrimaryButtonClass}
            >
              {approvingAll ? 'جارٍ الاعتماد…' : `اعتمد الكل (${pending})`}
            </button>
          ) : null
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          {FEE_DRAFT_FILTERS.map((entry) => (
            <button
              key={entry.key || 'all'}
              type="button"
              onClick={() => setFilter(entry.key)}
              aria-pressed={filter === entry.key}
              className={
                filter === entry.key
                  ? 'rounded-full border border-teal-700 bg-teal-700 px-3 py-1 text-[11.5px] font-semibold text-white'
                  : 'rounded-full border border-slate-200 bg-white px-3 py-1 text-[11.5px] font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
              }
            >
              {entry.label}
            </button>
          ))}
          {!canApprove ? (
            <span className="text-[11px] text-slate-500 dark:text-slate-400">
              اعتمادُ المسودّات لصاحب المكتب ومدير المكتب وحدهما.
            </span>
          ) : null}
        </div>

        {loading ? (
          <div className="mt-3">
            <OfficeSkeleton rows={5} />
          </div>
        ) : visible.length === 0 ? (
          <div className="mt-3">
            <OfficeEmpty
              title="لا مسودّات في هذا الفلتر"
              hint="تتولّد المسودّات من «حدّث المكتب» بحسب الاشتراكات والخدمات والإضافات."
            />
          </div>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-[12px]">
              <thead>
                <tr className="border-b border-slate-200 text-start text-[11px] text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2 text-start font-semibold">الفترة</th>
                  <th className="px-2 py-2 text-start font-semibold">الزبون</th>
                  <th className="px-2 py-2 text-start font-semibold">المبلغ</th>
                  <th className="px-2 py-2 text-start font-semibold">الحالة</th>
                  <th className="px-2 py-2 text-start font-semibold">الورقة</th>
                  <th className="px-2 py-2 text-start font-semibold">أفعال</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <DraftRow
                    key={row.id}
                    row={row}
                    canApprove={canApprove}
                    busy={busyId === row.id}
                    onApprove={() => approve(row)}
                    onCancel={() => cancel(row)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </OfficeCard>
    </div>
  );
};

/** سطرُ مسودّة: الفترةُ والزبون والمبلغ والحالة وبطاقةُ الورقة والفعنان. */
const DraftRow: React.FC<{
  row: FeeDraftRow;
  canApprove: boolean;
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}> = ({ row, canApprove, busy, onApprove, onCancel }) => {
  const actions = feeDraftActions(row.status);
  return (
    <tr className="border-b border-slate-100 align-top dark:border-slate-800">
      <td className="px-2 py-2.5 font-medium text-slate-800 dark:text-slate-100">
        {row.period_label}
      </td>
      <td className="px-2 py-2.5 text-slate-700 dark:text-slate-200">{row.client.name}</td>
      <td className="px-2 py-2.5 tabular-nums text-slate-800 dark:text-slate-100">
        {formatOfficeAmount(row.total)}
        {row.remaining && row.remaining !== row.total ? (
          <span className="ms-1 text-[10.5px] text-slate-500 dark:text-slate-400">
            (بقي {formatOfficeAmount(row.remaining)})
          </span>
        ) : null}
      </td>
      <td className="px-2 py-2.5">
        <span
          className={`rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${feeDraftStatusClass(row.status)}`}
        >
          {row.status_label}
        </span>
      </td>
      <td className="px-2 py-2.5 text-[11.5px]">
        {row.invoice ? (
          <div className="space-y-0.5">
            <div className="font-semibold text-slate-800 dark:text-slate-100">
              {row.invoice.number}
            </div>
            <div className="text-slate-500 dark:text-slate-400">
              {formatDateValue(row.invoice.issued_at)}
            </div>
            {row.invoice.url ? (
              <a
                href={row.invoice.url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-teal-700 hover:underline dark:text-teal-400"
              >
                افتح الورقة
              </a>
            ) : (
              <span className="text-slate-400 dark:text-slate-500">بلا رابطٍ بعد</span>
            )}
          </div>
        ) : (
          <span className="text-slate-400 dark:text-slate-500">لم تصدر</span>
        )}
      </td>
      <td className="px-2 py-2.5">
        {canApprove ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {actions.approve ? (
              <button
                type="button"
                onClick={onApprove}
                disabled={busy}
                className={`${officePrimaryButtonClass} px-2.5 py-1`}
              >
                {busy ? 'جارٍ…' : 'اعتمد'}
              </button>
            ) : null}
            {actions.cancel ? (
              <button
                type="button"
                onClick={onCancel}
                disabled={busy}
                className={`${officeSecondaryButtonClass} px-2.5 py-1 text-rose-700 dark:text-rose-300`}
              >
                أَلغِها
              </button>
            ) : null}
            {!actions.approve && !actions.cancel ? (
              <span className="text-[10.5px] text-slate-400 dark:text-slate-500">—</span>
            ) : null}
          </div>
        ) : (
          <span className="text-[10.5px] text-slate-400 dark:text-slate-500">—</span>
        )}
      </td>
    </tr>
  );
};
