/**
 * K4 — «رابط للموظف»: نافذة المدير فوق `StocktakeDialog` نفسها.
 *
 * نموذجٌ في الأعلى (اسمٌ إلزامي، صلاحية 1/3/7، ونطاقٌ افتراضيّه الجرد كلّه)،
 * وقائمةُ روابط هذا الجرد تحته. **الشجرة مقصوصة على بنود هذا الجرد**: تُعرض
 * العُقد التي في شجرتها الفرعية بندٌ واحد على الأقل، ويُرسَل للخادم ما له بندٌ
 * مباشر فقط (الخادم يرفض غيره). والقاعدة في `utils/stocktakeCountLinks.ts`
 * وحدها، لا نسخةً ثانية هنا.
 *
 * لا QR: لا مكتبة QR في المشروع، وإضافة اعتمادية لهذه النافذة ممنوعة — النسخ
 * وواتساب يكفيان (الخطة §5.2 تطلب QR، والتذكرة أسقطته صراحةً).
 */
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  Ban, Check, ChevronDown, ChevronUp, Copy, Link2, MessageCircle, RefreshCw,
} from 'lucide-react';
import { CategoryTreeSelect, type CategoryTreeOption } from './CategoryTreeSelect';
import { StocktakeDialog } from './StocktakeDialog';
import { inventoryApi } from '../../services/inventoryApi';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useToast } from '../../contexts/ToastContext';
import { extractDrfFieldErrors } from '../../utils/drfError';
import { formatDateValue, formatDateTimeValue } from '../../utils/formatDate';
import { formatNumber } from '../../utils/formatNumber';
import {
  countLinkScopeLabel,
  countLinkStatusLabel,
  filterCountLinkCategoryIds,
  stocktakeCountScopeIds,
} from '../../utils/stocktakeCountLinks';
import type {
  StocktakeCountLinkRow, StocktakeCountLinkStatus,
} from '../../types/inventory';

export interface StocktakeCountLinksDialogProps {
  stocktakeId: number;
  /** رقم الجرد أو تاريخه — يُكتب في رسالة واتساب وفي بطاقة الرابط. */
  stocktakeLabel: string;
  /** شجرة تصنيفات الشركة كلها — تُقصّ هنا على تصنيفات بنود آخر لقطةٍ من الخادم. */
  categories: CategoryTreeOption[];
  /** عدد بنود آخر لقطةٍ من الخادم في كل تصنيف مباشر — ومنه تُشتقّ المعرّفات المرسلة. */
  lineCountsByCategory: Record<number, number>;
  onClose: () => void;
  /** كل تغيير في القائمة يُبلَّغ للورقة كي يُضبط مؤقّت التحديث التلقائي. */
  onLinksChanged: (links: StocktakeCountLinkRow[]) => void;
}

const DAY_OPTIONS: Array<1 | 3 | 7> = [1, 3, 7];

const STATUS_CLASS: Record<StocktakeCountLinkStatus, string> = {
  active: 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300',
  finished: 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300',
  expired: 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
  revoked: 'border-slate-300 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
};

const pageUrl = (token: string): string => `${window.location.origin}/count/${token}`;

const shareText = (stocktakeLabel: string, counterName: string, url: string): string =>
  `رابط جرد ${stocktakeLabel} — ${counterName}: ${url}`;

type ApiError = {
  status?: number;
  data?: unknown;
};

/** زرّا المشاركة (نسخ/واتساب) — نفساه في بطاقة «الرابط الجديد» وفي كل صفّ. */
const CountLinkShareActions: React.FC<{
  row: StocktakeCountLinkRow;
  stocktakeLabel: string;
  onCopy: (token: string) => void;
}> = ({ row, stocktakeLabel, onCopy }) => (
  <>
    <button
      type="button"
      className="ktra-toolbtn"
      onClick={() => onCopy(row.token)}
      title="انسخ رابط العدّ"
    >
      <Copy className="h-3.5 w-3.5" /> نسخ
    </button>
    <a
      className="ktra-toolbtn"
      href={`https://wa.me/?text=${encodeURIComponent(shareText(stocktakeLabel, row.counter_name, pageUrl(row.token)))}`}
      target="_blank"
      rel="noreferrer"
      title="أرسل الرابط على واتساب"
    >
      <MessageCircle className="h-3.5 w-3.5" /> واتساب
    </a>
  </>
);

export const StocktakeCountLinksDialog: React.FC<StocktakeCountLinksDialogProps> = ({
  stocktakeId, stocktakeLabel, categories, lineCountsByCategory,
  onClose, onLinksChanged,
}) => {
  const titleId = useId();
  const nameFieldId = useId();
  const confirm = useConfirm();
  const toast = useToast();

  const [links, setLinks] = useState<StocktakeCountLinkRow[]>([]);
  const [linksLoading, setLinksLoading] = useState(true);
  const [linksError, setLinksError] = useState<string | null>(null);

  const [counterName, setCounterName] = useState('');
  const [days, setDays] = useState<1 | 3 | 7>(3);
  const [splitOpen, setSplitOpen] = useState(false);
  const [checkedIds, setCheckedIds] = useState<number[]>([]);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<StocktakeCountLinkRow | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  // مرآةٌ حيّة: الإنشاء/الإبطال يقرأ أحدث قائمة، لا نسخةَ آخر رسمٍ من الدالّة.
  const linksRef = useRef(links);
  linksRef.current = links;

  const scope = useMemo(
    () => stocktakeCountScopeIds(categories, Object.keys(lineCountsByCategory).map(Number)),
    [categories, lineCountsByCategory],
  );
  const checkedForSend = useMemo(
    () => filterCountLinkCategoryIds(checkedIds, scope.direct),
    [checkedIds, scope.direct],
  );
  const splitImpossible = scope.visible.length === 0;
  const trimmedName = counterName.trim();
  const nameTooLong = trimmedName.length > 80;
  const validSelection = !splitOpen || checkedForSend.length > 0;
  const canCreate = trimmedName !== '' && !nameTooLong && validSelection && !creating;

  const publish = useCallback((rows: StocktakeCountLinkRow[]) => {
    setLinks(rows);
    onLinksChanged(rows);
  }, [onLinksChanged]);

  const loadLinks = useCallback(async () => {
    setLinksLoading(true);
    setLinksError(null);
    try {
      const rows = await inventoryApi.getStocktakeCountLinks(stocktakeId);
      publish(rows);
    } catch (reason) {
      const error = reason as ApiError;
      setLinksError(
        error.status === 403
          ? 'صلاحيتك في هذه الشركة لا تسمح بقراءة روابط العدّ.'
          : reason instanceof Error ? reason.message : 'تعذّر تحميل روابط الجرد.',
      );
    } finally {
      setLinksLoading(false);
    }
  }, [publish, stocktakeId]);

  useEffect(() => {
    void loadLinks();
  }, [loadLinks]);

  const copyLink = useCallback(async (token: string) => {
    try {
      await navigator.clipboard.writeText(pageUrl(token));
      toast('نُسخ الرابط', 'success');
    } catch {
      toast('تعذّر النسخ — انسخ الرابط يدوياً.', 'error');
    }
  }, [toast]);

  const createLink = async () => {
    if (!canCreate) return;
    setCreating(true);
    setGeneralError(null);
    setFieldErrors({});
    try {
      const row = await inventoryApi.createStocktakeCountLink(stocktakeId, {
        counter_name: trimmedName,
        days,
        categories: splitOpen ? checkedForSend : null,
      });
      publish([row, ...linksRef.current]);
      setCreated(row);
      setCounterName('');
      setCheckedIds([]);
      setSplitOpen(false);
    } catch (reason) {
      const error = reason as ApiError;
      if (error.status === 403) {
        setGeneralError('صلاحيتك لا تسمح بإنشاء روابط عدّ لهذا الجرد.');
        return;
      }
      const fields = extractDrfFieldErrors(error.data);
      if (Object.keys(fields).length) {
        setFieldErrors(fields);
        return;
      }
      setGeneralError(reason instanceof Error ? reason.message : 'تعذّر إنشاء الرابط.');
    } finally {
      setCreating(false);
    }
  };

  const revoke = async (row: StocktakeCountLinkRow) => {
    const ok = await confirm({
      title: 'إبطال رابط العدّ',
      message: `إبطال رابط ${row.counter_name}؟ لن يستطيع إرسال أيّ عدّ بعدها.`,
      confirmText: 'إبطال',
      danger: true,
    });
    if (!ok) return;
    setRevokingId(row.id);
    setGeneralError(null);
    try {
      const updated = await inventoryApi.revokeStocktakeCountLink(stocktakeId, row.id);
      publish(linksRef.current.map((item) => (item.id === updated.id ? updated : item)));
      if (created?.id === updated.id) setCreated(updated);
    } catch (reason) {
      setGeneralError(reason instanceof Error ? reason.message : 'تعذّر إبطال الرابط.');
    } finally {
      setRevokingId(null);
    }
  };

  const linkMeta = (row: StocktakeCountLinkRow) => {
    const parts = [
      `ينتهي: ${formatDateValue(row.expires_at) || '—'}`,
    ];
    if (row.finished_at) parts.push(`أنهى: ${formatDateTimeValue(row.finished_at)}`);
    return parts.join(' · ');
  };

  const renderActions = (row: StocktakeCountLinkRow) => {
    const live = row.status === 'active' || row.status === 'finished';
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        {live && (
          <>
            <CountLinkShareActions row={row} stocktakeLabel={stocktakeLabel} onCopy={copyLink} />
            <button
              type="button"
              className="ktra-toolbtn text-[var(--ktra-danger)]"
              onClick={() => void revoke(row)}
              disabled={revokingId != null || creating}
              title="أوقف هذا الرابط نهائياً"
            >
              {revokingId === row.id
                ? <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                : <Ban className="h-3.5 w-3.5" />}
              إبطال
            </button>
          </>
        )}
      </div>
    );
  };

  return (
    <StocktakeDialog
      title="رابط للموظف"
      titleId={titleId}
      onClose={onClose}
      busy={creating || revokingId != null}
      icon={<Link2 className="h-4 w-4 shrink-0 text-[var(--ktra-ink-soft)]" />}
      panelClassName="max-w-2xl"
      bodyClassName="max-h-[72vh] space-y-4 overflow-y-auto p-4 text-sm text-[var(--ktra-ink)]"
      footer={(
        <button type="button" className="ktra-btn" onClick={onClose} disabled={creating || revokingId != null}>
          إغلاق
        </button>
      )}
    >
      <section className="space-y-3 rounded border border-[var(--ktra-border-soft)] bg-[var(--ktra-surface-2)] p-3">
        <p className="text-xs text-[var(--ktra-ink-soft)]">
          رابطٌ عامٌّ بلا تسجيل: الموظف يرى بنود نطاقه وكمية النظام، ويكتب المعدود.
          لا يرى تكلفةً ولا سعراً ولا قيمة.
        </p>

        <div className="space-y-1">
          <label htmlFor={nameFieldId} className="ktra-field-label">اسم الموظف</label>
          <input
            id={nameFieldId}
            className={`ktra-input w-full ${fieldErrors.counter_name ? 'border-[var(--ktra-danger)]!' : ''}`}
            value={counterName}
            maxLength={80}
            disabled={creating}
            placeholder="مثال: أحمد"
            aria-invalid={Boolean(fieldErrors.counter_name)}
            data-testid="count-link-counter-name"
            onChange={(event) => {
              setCounterName(event.target.value);
              setFieldErrors((prev) => ({ ...prev, counter_name: '' }));
            }}
          />
          {fieldErrors.counter_name && (
            <span role="alert" className="block text-xs text-[var(--ktra-danger)]">
              {fieldErrors.counter_name}
            </span>
          )}
          {nameTooLong && (
            <span role="alert" className="block text-xs text-[var(--ktra-danger)]">
              اسم الموظف 80 محرفاً كحدّ أقصى.
            </span>
          )}
        </div>

        <div>
          <span className="ktra-field-label">الصلاحية</span>
          <div className="mt-1 inline-flex overflow-hidden rounded border border-[var(--ktra-border)]" role="group" aria-label="مدة صلاحية الرابط">
            {DAY_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={`px-3 py-1.5 text-xs font-semibold transition ${
                  days === option
                    ? 'bg-[var(--ktra-accent)] text-white'
                    : 'bg-[var(--ktra-panel)] text-[var(--ktra-ink)] hover:bg-[var(--ktra-surface-2)]'
                }`}
                aria-pressed={days === option}
                disabled={creating}
                onClick={() => setDays(option)}
              >
                {formatNumber(option)} {option === 1 ? 'يوم' : 'أيام'}
              </button>
            ))}
          </div>
          {fieldErrors.days && (
            <span role="alert" className="mt-1 block text-xs text-[var(--ktra-danger)]">
              {fieldErrors.days}
            </span>
          )}
        </div>

        <div>
          <span className="ktra-field-label">النطاق</span>
          <p className="mt-0.5 text-xs text-[var(--ktra-ink-soft)]">
            {splitOpen
              ? 'يعدّ الموظف تصنيفاتٍ مختارة من بنود هذا الجرد وحده.'
              : 'كل الجرد — يعدّ الموظف كل بنود هذا الجرد، بما فيها البنود بلا تصنيف.'}
          </p>

          <button
            type="button"
            className="ktra-toolbtn mt-2"
            aria-expanded={splitOpen}
            disabled={creating || splitImpossible}
            onClick={() => setSplitOpen((value) => !value)}
          >
            {splitOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            تقسيم على أكثر من موظف؟
          </button>

          {splitImpossible && (
            <p className="mt-1 text-xs text-[var(--ktra-ink-soft)]">
              لا تصنيفات في بنود هذا الجرد — استعمل «كل الجرد».
            </p>
          )}
          <p className="mt-1 text-xs text-[var(--ktra-ink-soft)]">
            البنود بلا تصنيف تُعدّ في رابط «كل الجرد» وحده — لا تدخل في رابطٍ جزئي.
          </p>

          {splitOpen && !splitImpossible && (
            <div className="mt-2 space-y-1">
              <CategoryTreeSelect
                mode="multi"
                categories={categories}
                value={checkedIds}
                onChange={setCheckedIds}
                restrictTo={scope.visible}
                productCounts={lineCountsByCategory}
                disabled={creating}
              />
              {checkedIds.length > 0 && checkedForSend.length === 0 && (
                <p role="alert" className="text-xs font-semibold text-[var(--ktra-danger)]">
                  لا بنود في هذا الاختيار
                </p>
              )}
              {fieldErrors.categories && (
                <p role="alert" className="text-xs text-[var(--ktra-danger)]">
                  {fieldErrors.categories}
                </p>
              )}
            </div>
          )}
        </div>

        {generalError && (
          <div role="alert" className="ktra-banner ktra-banner--err">{generalError}</div>
        )}

        <div className="flex justify-end">
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            data-testid="count-link-create"
            disabled={!canCreate}
            onClick={() => void createLink()}
          >
            {creating
              ? <><RefreshCw className="me-1 h-4 w-4 animate-spin" /> جارٍ الإنشاء…</>
              : <><Check className="me-1 h-4 w-4" /> إنشاء الرابط</>}
          </button>
        </div>
      </section>

      {created && (
        <section
          className="space-y-2 rounded border border-emerald-300 bg-emerald-50 p-3 dark:border-emerald-800 dark:bg-emerald-950/30"
          data-testid="count-link-created"
        >
          <h3 className="text-xs font-bold text-emerald-800 dark:text-emerald-300">
            الرابط الجديد — {created.counter_name}
          </h3>
          <input
            className="ktra-input w-full font-mono text-xs"
            readOnly
            value={pageUrl(created.token)}
            aria-label="رابط العدّ الجديد"
            data-testid="count-link-url"
            onFocus={(event) => event.currentTarget.select()}
          />
          <div className="flex flex-wrap items-center gap-1.5">
            {created.status === 'active' || created.status === 'finished' ? (
              <CountLinkShareActions
                row={created}
                stocktakeLabel={stocktakeLabel}
                onCopy={copyLink}
              />
            ) : (
              <span className="text-xs font-semibold text-[var(--ktra-danger)]">
                أُبطل هذا الرابط — لا يمكن مشاركته.
              </span>
            )}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-bold">روابط هذا الجرد</h3>
          <button
            type="button"
            className="ktra-iconbtn"
            onClick={() => void loadLinks()}
            disabled={linksLoading || creating || revokingId != null}
            title="أعد تحميل القائمة"
            aria-label="إعادة تحميل روابط الجرد"
          >
            <RefreshCw className={`h-4 w-4 ${linksLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {linksError && (
          <div role="alert" className="ktra-banner ktra-banner--err flex items-center justify-between gap-2">
            <span>{linksError}</span>
            <button type="button" className="ktra-toolbtn" onClick={() => void loadLinks()}>
              إعادة المحاولة
            </button>
          </div>
        )}

        {linksLoading && !links.length && (
          <p className="text-xs text-[var(--ktra-ink-soft)]">جارٍ تحميل الروابط…</p>
        )}

        {!linksLoading && !links.length && !linksError && (
          <p className="rounded border border-dashed border-[var(--ktra-border)] p-3 text-center text-xs text-[var(--ktra-ink-soft)]">
            لا روابط بعد — أنشئ رابطاً واحفظه للموظف.
          </p>
        )}

        <ul className="space-y-1.5">
          {links.map((row) => (
            <li
              key={row.id}
              className="rounded border border-[var(--ktra-border-soft)] p-2.5"
              data-testid="count-link-row"
            >
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <b className="min-w-0 flex-1 truncate">{row.counter_name}</b>
                <span className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold ${STATUS_CLASS[row.status]}`}>
                  {countLinkStatusLabel(row.status, row.progress.counted)}
                </span>
                <span className="text-xs text-[var(--ktra-ink-soft)]" data-testid="count-link-progress">
                  {formatNumber(row.progress.counted)} / {formatNumber(row.progress.lines)}
                </span>
              </div>
              <div className="mt-1 text-xs text-[var(--ktra-ink-soft)]">
                {countLinkScopeLabel(row.categories)} · {linkMeta(row)}
              </div>
              <div className="mt-1.5">{renderActions(row)}</div>
            </li>
          ))}
        </ul>
      </section>
    </StocktakeDialog>
  );
};
