/**
 * K2 — «جرد جديد» في خطوتين (خطة §5.1): الرأس أولاً، ثم «ماذا سنجرد؟».
 *
 * الخطوة الثانية تعرض شجرة التصنيفات كاملةً بعدّادات الخادم، ودلالة الاختيار
 * صريحة (قرار ٣): تأشير عقدة = منتجاتها المباشرة وحدها؛ الأب المؤشَّر يؤشّر
 * أحفاده بصرياً ويمكن إلغاء ابنٍ فيبقى الأب «جزئياً». و«بدون تصنيف» قرارٌ منفصل
 * لأن الشجرة لا تحتويه.
 *
 * كل الأرقام من `GET stocktakes/scope-counts/` لا من كتالوجٍ منزَّل، والملخّص
 * الوحيد المرسوم هو هذا السطر — مكوّن الشجرة يستقبل `summary` بديلاً بدل
 * ملخّصه الافتراضي كي لا يقرأ المستخدم رقمين مختلفين.
 */
import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ChevronLeft, RefreshCw } from 'lucide-react';
import { CategoryTreeSelect, type CategoryTreeOption } from './CategoryTreeSelect';
import { StocktakeDialog } from './StocktakeDialog';
import { inventoryApi } from '../../services/inventoryApi';
import { formatNumber } from '../../utils/formatNumber';
import { todayIso } from '../../utils/formatDate';
import {
  arabicCount,
  buildStocktakeCreateBody,
  canCreateFromScope,
  summarizeScopeSelection,
  type StocktakeScopeMode,
} from '../../utils/stocktake';
import type {
  Stocktake, StocktakeScopeCounts, WarehouseOption,
} from '../../types/inventory';

type Props = {
  categories: CategoryTreeOption[];
  warehouses: WarehouseOption[];
  onClose: () => void;
  onCreated: (result: { stocktake: Stocktake; etag: string | null }) => void;
};

const MODES: { value: StocktakeScopeMode; label: string; hint: string }[] = [
  {
    value: 'all',
    label: 'كل المنتجات',
    hint: 'كل منتجٍ غير خدمي — النشطة فقط ما لم تختر غير الفعّالة.',
  },
  { value: 'categories', label: 'تصنيفات محدّدة', hint: 'تختار فروع الشجرة بنفسك — كل تصنيف يعني منتجاته المباشرة.' },
  { value: 'manual', label: 'يدوي (فارغ)', hint: 'جردٌ بلا بنود — تضيفها من الورقة واحداً واحداً.' },
];

export const NewStocktakeModal: React.FC<Props> = ({
  categories, warehouses, onClose, onCreated,
}) => {
  const titleId = useId();

  const [step, setStep] = useState<1 | 2>(1);
  const [date, setDate] = useState(todayIso());
  const [warehouse, setWarehouse] = useState<number | ''>('');
  const [notes, setNotes] = useState('');
  const [mode, setMode] = useState<StocktakeScopeMode>('categories');
  const [checkedIds, setCheckedIds] = useState<number[]>([]);
  const [uncategorized, setUncategorized] = useState(false);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [counts, setCounts] = useState<StocktakeScopeCounts | null>(null);
  const [countsLoading, setCountsLoading] = useState(true);
  const [countsError, setCountsError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // تسلسل طلبات العدّادات: تبديل «غير الفعّالة» بسرعة يُطلق طلبين، وردُّ
  // الأقدم قد يهبط بعد الأحدث — يحكم آخرُ طلبٍ أُطلق وحده.
  const countsRequestRef = useRef(0);

  const loadCounts = useCallback(async () => {
    const requestId = countsRequestRef.current + 1;
    countsRequestRef.current = requestId;
    setCountsLoading(true);
    setCountsError(null);
    try {
      const next = await inventoryApi.getStocktakeScopeCounts(includeInactive);
      if (countsRequestRef.current !== requestId) return;
      setCounts(next);
    } catch (reason) {
      if (countsRequestRef.current !== requestId) return;
      setCounts(null);
      setCountsError(reason instanceof Error ? reason.message : 'تعذّر حساب عدد المنتجات');
    } finally {
      if (countsRequestRef.current === requestId) setCountsLoading(false);
    }
  }, [includeInactive]);

  // تبديل «غير الفعّالة» يعيد القراءة من الخادم: العدّاد يجب أن يطابق البنود.
  useEffect(() => { void loadCounts(); }, [loadCounts]);

  const summary = summarizeScopeSelection({
    mode, checkedIds, uncategorized, counts,
  });
  // اليدوي لا ينتظر عدّاداتٍ أصلاً: فشلُها لا يمنع جرداً فارغاً مشروعاً.
  const canCreate = step === 2
    && !creating
    && canCreateFromScope(mode, summary)
    && (mode === 'manual' || (!countsLoading && !countsError));

  const create = async () => {
    if (!canCreate) return;
    setCreating(true);
    setError(null);
    try {
      const result = await inventoryApi.createStocktake(buildStocktakeCreateBody({
        mode,
        stocktakeDate: date,
        warehouse: warehouse === '' ? null : Number(warehouse),
        notes,
        checkedIds,
        uncategorized,
        includeInactive,
      }));
      onCreated(result);
    } catch (reason) {
      // فشل الشبكة وفشل الخادم سواء: النافذة تبقى باختياراتها ورسالةٌ تشرح.
      // ورسالة 400 الخادمية تسمّي التصنيفات المرفوضة، فلا تُستبدل بنصٍّ عام.
      setError(reason instanceof Error ? reason.message : 'تعذّر إنشاء الجرد');
    } finally {
      setCreating(false);
    }
  };

  const summaryText = mode === 'manual'
    ? 'جرد يدوي — تُضاف البنود من الورقة'
    : countsError
      ? 'تعذّر حساب عدد المنتجات'
      : countsLoading && !counts
        ? 'جارٍ حساب المنتجات…'
        : `سيُجرد ${arabicCount(summary.products, {
          one: 'منتجٌ واحد', two: 'منتجان', few: 'منتجات', many: 'منتجاً', zero: '0 منتج',
        })} في ${arabicCount(summary.categories, {
          one: 'تصنيفٍ واحد', two: 'تصنيفين', few: 'تصنيفات', many: 'تصنيفاً', zero: '0 تصنيف',
        })}`;
  const emptyChoice = mode !== 'manual' && !countsLoading && !countsError
    && summary.products === 0;

  return (
    <StocktakeDialog
      title="جرد جديد"
      titleId={titleId}
      onClose={onClose}
      busy={creating}
      closeLabel="إغلاق نافذة الجرد الجديد"
      closeTitle="إغلاق"
      overlayClassName="z-[90]"
      panelClassName="flex max-h-[90vh] max-w-2xl flex-col"
      bodyClassName="min-h-0 flex-1 space-y-4 overflow-y-auto p-4"
      headerExtra={(
        <span className="shrink-0 text-xs text-[var(--ktra-ink-soft)]">
          الخطوة {formatNumber(step)} من {formatNumber(2)}
        </span>
      )}
      footer={step === 1 ? (
        <>
          <button type="button" className="ktra-btn" onClick={onClose} disabled={creating}>
            إلغاء
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            disabled={!date || creating}
            onClick={() => setStep(2)}
          >
            التالي
            <ChevronLeft className="h-4 w-4" />
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className="ktra-btn"
            onClick={() => setStep(1)}
            disabled={creating}
          >
            السابق
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            onClick={() => void create()}
            disabled={!canCreate}
            title={countsError ? countsError : undefined}
          >
            {creating ? 'جارٍ الإنشاء…' : 'إنشاء'}
          </button>
        </>
      )}
    >
      {error && (
        <div role="alert" className="ktra-banner ktra-banner--err text-sm">{error}</div>
      )}

      {step === 1 ? (
        <>
          <div className="flex flex-wrap gap-3">
            <label className="ktra-field">
              <span className="ktra-field-label">التاريخ</span>
              <input
                type="date"
                className="ktra-input"
                value={date}
                disabled={creating}
                onChange={(event) => setDate(event.target.value)}
              />
            </label>
            <label className="ktra-field">
              <span className="ktra-field-label">المستودع</span>
              <select
                className="ktra-input"
                value={warehouse}
                disabled={creating}
                onChange={(event) => setWarehouse(
                  event.target.value ? Number(event.target.value) : '',
                )}
              >
                <option value="">— كل المخزون —</option>
                {warehouses.map((row) => (
                  <option key={row.id} value={row.id}>{row.name}</option>
                ))}
              </select>
            </label>
            <label className="ktra-field min-w-40 flex-1">
              <span className="ktra-field-label">ملاحظات</span>
              <input
                className="ktra-input"
                value={notes}
                disabled={creating}
                onChange={(event) => setNotes(event.target.value)}
              />
            </label>
          </div>
          <p className="text-xs text-[var(--ktra-ink-soft)]">
            المستودع وسمٌ على حركات الجرد ولا يقيّد البنود؛ البنود تُقرأ بأرصدة الشركة.
          </p>
        </>
      ) : (
        <>
          <h3 className="text-sm font-bold text-[var(--ktra-ink)]">ماذا سنجرد؟</h3>
          <div className="space-y-1.5">
            {MODES.map((option) => (
              <label
                key={option.value}
                className="flex cursor-pointer items-start gap-2 rounded border border-[var(--ktra-border-soft)] px-2 py-1.5 text-sm"
              >
                <input
                  type="radio"
                  name="stocktake-scope-mode"
                  className="mt-0.5 accent-[var(--ktra-accent)]"
                  checked={mode === option.value}
                  disabled={creating}
                  onChange={() => setMode(option.value)}
                />
                <span>
                  <span className="font-medium text-[var(--ktra-ink)]">{option.label}</span>
                  <span className="block text-xs text-[var(--ktra-ink-soft)]">{option.hint}</span>
                </span>
              </label>
            ))}
          </div>

          {mode !== 'manual' && countsError && (
            <div className="ktra-banner ktra-banner--err flex items-center gap-2 text-sm">
              <span className="flex-1">{countsError}</span>
              <button
                type="button"
                className="ktra-toolbtn"
                onClick={() => void loadCounts()}
                disabled={countsLoading}
              >
                <RefreshCw className={`h-4 w-4 ${countsLoading ? 'animate-spin' : ''}`} />
                إعادة المحاولة
              </button>
            </div>
          )}

          {mode === 'categories' && (
            <div className="space-y-2">
              {!countsError && (
                <CategoryTreeSelect
                  mode="multi"
                  categories={categories}
                  value={checkedIds}
                  onChange={setCheckedIds}
                  productCounts={counts?.categories ?? {}}
                  disabled={creating}
                  summary={(
                    <span data-testid="stocktake-scope-summary">{summaryText}</span>
                  )}
                />
              )}

              <label className="flex items-center gap-2 text-sm text-[var(--ktra-ink)]">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-[var(--ktra-accent)]"
                  checked={uncategorized}
                  disabled={creating || !counts}
                  onChange={(event) => setUncategorized(event.target.checked)}
                />
                بدون تصنيف
                {counts && (
                  <span className="text-xs text-[var(--ktra-ink-soft)]">
                    ({formatNumber(counts.uncategorized)})
                  </span>
                )}
              </label>
            </div>
          )}

          {mode !== 'categories' && (
            <div
              data-testid="stocktake-scope-summary"
              className="rounded border border-[var(--ktra-border-soft)] px-2 py-1.5 text-sm text-[var(--ktra-ink)]"
            >
              {summaryText}
            </div>
          )}

          {mode !== 'manual' && (
            <>
              <label className="flex items-center gap-2 text-sm text-[var(--ktra-ink)]">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-[var(--ktra-accent)]"
                  checked={includeInactive}
                  disabled={creating}
                  onChange={(event) => setIncludeInactive(event.target.checked)}
                />
                شمل المنتجات غير الفعّالة
              </label>
              <p className="text-xs text-[var(--ktra-ink-soft)]">
                الخدمات تُستبعد دائماً. المنتج غير الفعّال قد يكون له رصيدٌ باقٍ يُعدّ.
              </p>
            </>
          )}

          {emptyChoice && (
            <div role="alert" className="ktra-banner ktra-banner--warn text-sm">
              لا منتجات في هذا الاختيار
            </div>
          )}
        </>
      )}
    </StocktakeDialog>
  );
};

export default NewStocktakeModal;
