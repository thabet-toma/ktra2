/**
 * K2 — ورقة الجرد: البنود تأتي من الجرد نفسه لا من كتالوجٍ منزَّل.
 *
 * الشاشة لا تنادي `getAllProducts` إطلاقاً: `POST stocktakes/ {scope}` يولّد
 * البنود في الخادم (K1)، والقائمة ملخّصٌ بلا بنود. الورقة تعرض البنود مجمّعةً
 * بالتصنيف، وتعدّل فرقَ ما تغيّر وحده، وتحفظ بـ`If-Match` كي لا يمحو تعديلُ
 * المدير عدَّ موظف الرابط (412 ⇒ «حدّث» ثم إعادة تطبيق التعديلات المحلية).
 *
 * الإضافة اليدوية تبحث في الخادم (`getProducts` بـ`search`) — لا كتالوج في
 * الذاكرة — وتستثني الخدمات والمنتجات الموجودة في الورقة.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  inventoryApi, isStaleDocumentError,
} from '../../services/inventoryApi';
import {
  KitDocumentShell, KitAutocomplete, type KitToolbarAction, type KitAutocompleteOption,
} from '../kit';
import { ProductCardModal } from '../shared/ProductCardModal';
import { DocumentDraftBanners } from '../shared/DocumentDraftBanners';
import { NewStocktakeModal } from './NewStocktakeModal';
import { StocktakeDialog } from './StocktakeDialog';
import { useConfirm } from '../../contexts/ConfirmContext';
import { useDocumentDraft } from '../../hooks/useDocumentDraft';
import { formatNumber, formatQuantity } from '../../utils/formatNumber';
import {
  formatDateLocalized, formatTimeValue, todayIso,
} from '../../utils/formatDate';
import { categoryPathLabel, type CategoryNodeLike } from '../../utils/categoryTree';
import {
  arabicCount,
  buildStocktakeLinesPayload,
  countStocktakeProgress,
  filterStocktakeLines,
  groupStocktakeLines,
  isApplicableStocktakeDraft,
  isCounted,
  newSheetLineFromProduct,
  productLabel,
  rebaseDraftRestore,
  rebaseHeader,
  sheetLinesFromStocktake,
  stocktakeStampText,
  stocktakeVariance,
  validateCountedQuantity,
  type ManualProductRow,
  type StocktakeFilter,
  type StocktakeHeader,
  type StocktakeSheetLine,
} from '../../utils/stocktake';
import type {
  Stocktake, StocktakeListRow, WarehouseOption,
} from '../../types/inventory';
import {
  Plus, Send, Trash2, RefreshCw, X, Save, Printer, Info, AlertTriangle,
} from 'lucide-react';

type TreeCategory = CategoryNodeLike & { name: string };

/** حمولة المسودّة المحلية — الإصدار الثالث يحمل هويّة الجرد ورأسَه ومرجعية رأسه. */
type StocktakeDraftPayload = {
  v: 3;
  docId: number;
  date: string;
  warehouse: number | '';
  notes: string;
  /** الرأس الذي بُنيت عليه قيم المسودّة — يُقارَن به عند إعادة التأسيس. */
  headerBaseline: StocktakeHeader;
  lines: StocktakeSheetLine[];
  removedIds: number[];
};

/** صيغ «بندٍ واحد / بندين / 3 بنود / 11 بنداً» لرسالة إعادة التطبيق. */
const REAPPLY_FORMS = {
  one: 'بندٍ واحد', two: 'بندين', few: 'بنود', many: 'بنداً',
};

/** أوضاع فلتر المراجعة: الكل / المعدود / غير المعدود / الفروقات — للعرض والطباعة. */
type FilterMode = NonNullable<StocktakeFilter['mode']>;
const FILTER_OPTIONS: { value: FilterMode; label: string }[] = [
  { value: 'all', label: 'الكل' },
  { value: 'counted', label: 'المعدود فقط' },
  { value: 'uncounted', label: 'غير المعدود فقط' },
  { value: 'variance', label: 'الفروقات فقط' },
];

/** فرقٌ معروضٌ بإشارته: «+2.5» و«-3»، والصفر بلا إشارة. */
const signed = (value: number): string =>
  value > 0 ? `+${formatQuantity(value)}` : formatQuantity(value);

/**
 * نافذة الترحيل (F6/ق٢): تقول كم بنداً لم يُعدّ، وتترك القرار صريحاً —
 * تُستثنى افتراضاً، أو تُعتبر صفراً بخانةٍ يختارها المستخدم.
 */
const PostStocktakeModal: React.FC<{
  total: number;
  uncounted: number;
  uncountedAsZero: boolean;
  busy: boolean;
  error: string | null;
  onChange: (value: boolean) => void;
  onClose: () => void;
  onConfirm: () => void;
}> = ({ total, uncounted, uncountedAsZero, busy, error, onChange, onClose, onConfirm }) => {
  const titleId = React.useId();

  const disabled = total === 0 || busy || (uncounted === total && !uncountedAsZero);

  return (
    <StocktakeDialog
      title="ترحيل الجرد"
      titleId={titleId}
      onClose={onClose}
      busy={busy}
      closeLabel="إغلاق نافذة الترحيل"
      icon={<Send className="h-4 w-4 shrink-0 text-[var(--ktra-ink-soft)]" />}
      bodyClassName="space-y-3 p-4 text-sm text-[var(--ktra-ink)]"
      footer={(
        <>
          <button type="button" className="ktra-btn" onClick={onClose} disabled={busy}>
            إلغاء
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            disabled={disabled}
            onClick={onConfirm}
          >
            {busy ? 'جارٍ الترحيل…' : 'ترحيل'}
          </button>
        </>
      )}
    >
      <p>
        بنود الجرد: <b>{formatNumber(total)}</b> ·
        غير معدود: <b data-testid="post-uncounted-count">{formatNumber(uncounted)}</b>
      </p>

      {total === 0 ? (
        <div role="alert" className="ktra-banner ktra-banner--warn">
          لا بنود في هذا الجرد — أضف بنداً واحداً على الأقل قبل الترحيل.
        </div>
      ) : uncounted > 0 ? (
        <>
          <label className="flex items-start gap-2">
            <input
              type="checkbox"
              className="mt-0.5 h-3.5 w-3.5 accent-[var(--ktra-accent)]"
              checked={uncountedAsZero}
              disabled={busy}
              onChange={(event) => onChange(event.target.checked)}
            />
            <span>
              اعتبرها صفراً
              <span className="mt-0.5 block text-xs text-[var(--ktra-ink-soft)]">
                بلا هذا الخيار تُستثنى البنود غير المعدودة: لا حركة مخزون ولا أثر في
                القيد، ويُحفظ رصيدها لقطةً للتدقيق.
              </span>
            </span>
          </label>
          {uncounted === total && !uncountedAsZero && (
            <div role="alert" className="ktra-banner ktra-banner--warn text-xs">
              كل البنود غير معدودة — اختر «اعتبرها صفراً» أو عدّ بنداً واحداً على الأقل.
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-[var(--ktra-ink-soft)]">
          كل البنود معدودة — سيُسوّى الرصيد ويُنشأ قيد الفرق.
        </p>
      )}

      {error && <div role="alert" className="ktra-banner ktra-banner--err">{error}</div>}
    </StocktakeDialog>
  );
};

/**
 * نافذة 412: لا تُمحى مسودّةٌ محلية ولا يُعاد بناء ما لم يُطلب — قرارٌ صريح
 * ثم «تحديث» يقرأ الجديد ويعيد تطبيق تعديلات المستخدم فوقه (`rebaseDraftRestore`).
 */
const StaleStocktakeModal: React.FC<{
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onRefresh: () => void;
}> = ({ busy, error, onClose, onRefresh }) => {
  const titleId = React.useId();

  return (
    <StocktakeDialog
      title="تغيّر الجرد منذ فتحته — حدّث"
      titleId={titleId}
      onClose={onClose}
      busy={busy}
      showCloseButton={false}
      icon={<AlertTriangle className="h-4 w-4 shrink-0 text-[var(--ktra-warn-fg)]" />}
      footer={(
        <>
          <button type="button" className="ktra-btn" onClick={onClose} disabled={busy}>
            لاحقاً
          </button>
          <button
            type="button"
            className="ktra-btn ktra-btn-primary"
            onClick={onRefresh}
            disabled={busy}
          >
            {busy ? 'جارٍ التحديث…' : 'تحديث'}
          </button>
        </>
      )}
    >
      <p>
        حُفظ تعديلٌ آخر على هذا الجرد (أو عدّ موظف الرابط) بعد آخر قراءة.
        بالتحديث تُقرأ النسخة الجديدة ثم تُعاد تعديلاتك غير المحفوظة فوقها.
      </p>
      {error && <div role="alert" className="ktra-banner ktra-banner--err">{error}</div>}
    </StocktakeDialog>
  );
};

export const StocktakePage: React.FC = () => {
  const navigate = useNavigate();
  const today = todayIso();

  const [warehouses, setWarehouses] = useState<WarehouseOption[]>([]);
  const [rows, setRows] = useState<StocktakeListRow[]>([]);
  const [treeCategories, setTreeCategories] = useState<TreeCategory[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  // الورقة المفتوحة
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingPosted, setEditingPosted] = useState(false);
  const [etag, setEtag] = useState<string | null>(null);
  const [date, setDate] = useState(today);
  const [warehouse, setWarehouse] = useState<number | ''>('');
  const [notes, setNotes] = useState('');
  // الرأس الذي بُنيت عليه قيم الشاشة الحالية — تُقارَن به حقول المستخدم عند
  // «تحديث» (والاستعادة) فلا يمحو الخادمُ تعديلاً، ولا يبقى قديمٌ بلا سبب.
  const [headerBaseline, setHeaderBaseline] = useState<StocktakeHeader>({
    date: today, warehouse: '', notes: '',
  });
  const [lines, setLines] = useState<StocktakeSheetLine[]>([]);
  const [removedIds, setRemovedIds] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [docUpdatedAt, setDocUpdatedAt] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [cardProductId, setCardProductId] = useState<number | null>(null);

  // البحث والفلتر
  const [search, setSearch] = useState('');
  const [filterMode, setFilterMode] = useState<FilterMode>('all');

  // الإضافة اليدوية بالبحث الخادمي
  const [addQuery, setAddQuery] = useState('');
  const [addRows, setAddRows] = useState<ManualProductRow[]>([]);
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // النوافذ
  const [staleOpen, setStaleOpen] = useState(false);
  const [staleBusy, setStaleBusy] = useState(false);
  const [staleError, setStaleError] = useState<string | null>(null);
  const [postOpen, setPostOpen] = useState(false);
  const [postUncountedAsZero, setPostUncountedAsZero] = useState(false);
  const [postBusy, setPostBusy] = useState(false);
  const [postError, setPostError] = useState<string | null>(null);

  const markTouched = () => setTouched(true);

  // قراءةٌ من الخادم جارية (تحديث/412): كل ما يعدّل الورقة معطَّل حتى يُطبَّق
  // الدمج — لا تعديل يقع بين القراءة والتطبيق.
  const sheetBusy = refreshing || staleBusy;

  // فتح جردٍ آخر أو «جرد جديد» أو «إغلاق» يستبدل الورقة المفتوحة — لا يضيع تعديلٌ
  // غير محفوظ بلا سؤال. الحوار هو `useConfirm`/`ConfirmDialog` المستعمل في بقية
  // الشاشات، لا `window.confirm`. `'discard'` = المستخدم اختار التجاهل صراحةً.
  const confirm = useConfirm();
  const confirmDiscardEdits = useCallback(async (): Promise<'clean' | 'discard' | 'cancel'> => {
    if (!touched) return 'clean';
    const ok = await confirm({
      title: 'تعديلات غير محفوظة',
      message: 'لديك تعديلات غير محفوظة على هذا الجرد — تجاهلها والمتابعة؟',
      confirmText: 'تجاهلها والمتابعة',
      danger: true,
    });
    return ok ? 'discard' : 'cancel';
  }, [confirm, touched]);

  // التجاهل المؤكَّد يمحو مسودّة الجرد المتروك أيضاً — وإلا عادت التعديلات التي
  // اختار المستخدم تجاهلها عند فتحه التالي. يُنادى قبل تبدّل الورقة (والخطّاف ما
  // زال على مفتاحها)، و`touched` يُنزَل أولاً فلا يعيد تفريغٌ لاحق كتابتها.
  // `discardDraft` يعود من الخطّاف بعد هذا السطر، فيُقرأ عبر مرجع.
  const discardDraftRef = useRef<(() => Promise<void>) | null>(null);
  const discardSheetDraft = useCallback(async () => {
    setTouched(false);
    await discardDraftRef.current?.();
  }, []);
  // «جرد جديد» بعد التجاهل: المحو عند استبدال الورقة فعلاً (الإنشاء)، لا عند
  // السؤال — فإلغاء النافذة يُبقي الورقة ومسودّتها كما كانتا.
  const discardOnCreateRef = useRef(false);

  // لقطة الخادم لآخر قراءة/تحديث **مع هويّة جردها ورأسها**: المرجع الذي تُعاد
  // عليه المسودّة المستعادة وحقول الرأس، وحاجزٌ يمنع تطبيق مسودّة A على غيره.
  const serverSnapshotRef = useRef<{
    docId: number;
    lines: StocktakeSheetLine[];
    header: StocktakeHeader;
  } | null>(null);
  // مرآة الحالة الحيّة: تُقرأ مرّةً واحدة بعد وصول ردّ «تحديث» للدمج على أحدث
  // بنودٍ وحذفات (لا نسخةٍ من لحظة الضغط)، وكل ضوابط التعديل معطَّلة ما دام
  // `sheetBusy` فلا تعديل يقع بين القراءة والدمج.
  const linesStateRef = useRef(lines);
  linesStateRef.current = lines;
  const removedIdsStateRef = useRef(removedIds);
  removedIdsStateRef.current = removedIds;
  const headerStateRef = useRef<StocktakeHeader>({ date, warehouse, notes });
  headerStateRef.current = { date, warehouse, notes };
  const headerBaselineRef = useRef(headerBaseline);
  headerBaselineRef.current = headerBaseline;
  // الجرد المفتوح الآن — ردُّ قراءةٍ لجردٍ تُرك أثناءها لا يُطبَّق على غيره.
  const editingIdRef = useRef(editingId);
  editingIdRef.current = editingId;

  const applyDraftRestore = useCallback((
    restored: StocktakeDraftPayload,
    server: { lines: StocktakeSheetLine[]; header: StocktakeHeader },
  ) => {
    const rebased = rebaseDraftRestore(
      server.lines, restored.lines || [], restored.removedIds || [],
    );
    // الرأس يتبع قاعدة البنود نفسها: ما لم يعدّله المستخدم يأخذ قيمة الخادم.
    const rebasedHeader = rebaseHeader(
      server.header,
      { date: restored.date, warehouse: restored.warehouse, notes: restored.notes },
      restored.headerBaseline,
    );
    setDate(rebasedHeader.header.date);
    setWarehouse(rebasedHeader.header.warehouse);
    setNotes(rebasedHeader.header.notes);
    setHeaderBaseline(server.header);
    setLines(rebased.lines);
    setRemovedIds(rebased.removedIds);
    setTouched(true);
    // الرأس المعدَّل بندٌ من «تعديلاتك» أيضاً — يُحتسب مع البنود والحذفات.
    const keptCount = rebased.reapplied + rebasedHeader.kept;
    if (keptCount > 0) {
      setMsg(
        `أُعيد تطبيق تعديلاتك على ${arabicCount(keptCount, REAPPLY_FORMS)} — راجعها واحفظ`,
      );
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [whs, takes, cats] = await Promise.all([
        inventoryApi.getWarehouses({ active_only: 'true' }) as Promise<WarehouseOption[]>,
        inventoryApi.getStocktakes(),
        inventoryApi.getCategories() as Promise<TreeCategory[]>,
      ]);
      setWarehouses(whs || []);
      setRows(takes || []);
      setTreeCategories((cats || []).map((category) => ({
        id: category.id, name: category.name, parent: category.parent ?? null,
      })));
    } catch (reason) {
      setErr(reason instanceof Error ? reason.message : 'فشل التحميل');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const applyStocktake = useCallback((
    stocktake: Stocktake,
    token: string | null,
    options: { resetView?: boolean } = {},
  ) => {
    const nextLines = sheetLinesFromStocktake(stocktake.lines || []);
    const header: StocktakeHeader = {
      date: stocktake.stocktake_date || today,
      warehouse: stocktake.warehouse ?? '',
      notes: stocktake.notes || '',
    };
    serverSnapshotRef.current = { docId: stocktake.id, lines: nextLines, header };
    setDate(header.date);
    setWarehouse(header.warehouse);
    setNotes(header.notes);
    setHeaderBaseline(header);
    setLines(nextLines);
    setEditingId(stocktake.id);
    setEditingPosted(!!stocktake.is_posted);
    setDocUpdatedAt(stocktake.updated_at ?? null);
    setEtag(token);
    setRemovedIds([]);
    setTouched(false);
    if (options.resetView !== false) {
      setSearch('');
      setFilterMode('all');
    }
  }, [today]);

  const openStocktake = useCallback(async (id: number): Promise<boolean> => {
    const decision = await confirmDiscardEdits();
    if (decision === 'cancel') return false;
    if (decision === 'discard') await discardSheetDraft();
    setErr(null);
    setMsg(null);
    setLoading(true);
    try {
      const { stocktake, etag: token } = await inventoryApi.getStocktake(id);
      applyStocktake(stocktake, token);
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return true;
    } catch (reason) {
      setErr(reason instanceof Error ? reason.message : 'فشل فتح المستند');
      return false;
    } finally {
      setLoading(false);
    }
  }, [applyStocktake, confirmDiscardEdits, discardSheetDraft]);

  const closeSheet = useCallback(() => {
    setEditingId(null);
    setEditingPosted(false);
    setEtag(null);
    setLines([]);
    setRemovedIds([]);
    setTouched(false);
    setSearch('');
    setFilterMode('all');
    setDate(today);
    setWarehouse('');
    setNotes('');
    setHeaderBaseline({ date: today, warehouse: '', notes: '' });
    setAddQuery('');
    setAddRows([]);
    serverSnapshotRef.current = null;
  }, [today]);

  /* ISSUE #121: المسودّة المحلية تبقى قائمةً — تغطّي رأس المستند المفتوح
   * وكلَّ كميات بنوده وحذفاته المحلية، **بما فيها الإضافة اليدوية غير المحفوظة**
   * (فهي داخل `lines`). لا تغطّي نطاق الإنشاء وحده: نافذة «جرد جديد» تُنشئ
   * الجرد في الخادم مباشرةً، فلا ورقةَ قبل الإنشاء. */
  const draftPayload = useMemo<StocktakeDraftPayload>(
    () => ({
      v: 3,
      docId: editingId ?? 0,
      date,
      warehouse,
      notes,
      headerBaseline,
      lines,
      removedIds,
    }),
    [editingId, date, warehouse, notes, headerBaseline, lines, removedIds],
  );

  // مرجع دالّة إخفاء الشريط: `onRestoreDraft` يُمرَّر إلى الخطّاف قبل أن يعود
  // ناتجُه، والدالّة ثابتة الهوية فلا حاجة لربطٍ دائري.
  const dismissBannerRef = useRef<(() => void) | null>(null);

  const onRestoreDraft = useCallback((restored: StocktakeDraftPayload) => {
    const server = serverSnapshotRef.current;
    // مسودّةٌ من إصدارٍ أقدم (بلا `baseline`، وربما صفوف `product: ""`) أو لجردٍ
    // آخر غير المفتوح: لا تُطبَّق — وإلّا محت مسودّةُ A أرقامَ B، أو أعادت
    // مرجعياتٍ قديمة فوق عدٍّ أحدث.
    if (!isApplicableStocktakeDraft(restored, server?.docId)) {
      dismissBannerRef.current?.();
      return;
    }
    applyDraftRestore(restored, server);
  }, [applyDraftRestore]);

  const draftApi = useDocumentDraft<StocktakeDraftPayload>({
    docType: 'stocktake',
    docId: editingId,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    isPosted: editingPosted,
    docUpdatedAt: editingId != null ? docUpdatedAt : null,
  });
  const { draftSavedAt, draftSaveFailed, discardDraft } = draftApi;
  dismissBannerRef.current = draftApi.dismissBanner;
  discardDraftRef.current = discardDraft;

  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (draftSaveFailed) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [draftSaveFailed]);

  // «إغلاق»: يسأل مع تعديلٍ غير محفوظ، والتجاهل المؤكَّد يمحو المسودّة المحلية.
  const requestCloseSheet = useCallback(async () => {
    const decision = await confirmDiscardEdits();
    if (decision === 'cancel') return;
    if (decision === 'discard') await discardSheetDraft();
    closeSheet();
  }, [closeSheet, confirmDiscardEdits, discardSheetDraft]);

  const handleUndoDraft = useCallback(() => {
    closeSheet();
    void discardDraft();
  }, [closeSheet, discardDraft]);

  const updateLineQuantity = (product: number, value: string) => {
    setLines((prev) => prev.map((line) => (
      line.product === product ? { ...line, counted_quantity: value } : line
    )));
    markTouched();
  };

  const removeLine = (line: StocktakeSheetLine) => {
    setLines((prev) => prev.filter((row) => row.product !== line.product));
    if (line.baseline !== undefined) {
      setRemovedIds((prev) => (prev.includes(line.product) ? prev : [...prev, line.product]));
    }
    markTouched();
  };

  const addProduct = (id: number | string) => {
    const product = addRows.find((row) => row.id === Number(id));
    if (!product) return;
    setLines((prev) => (
      prev.some((line) => line.product === product.id)
        ? prev
        : [...prev, newSheetLineFromProduct(product)]
    ));
    setRemovedIds((prev) => prev.filter((productId) => productId !== product.id));
    setAddQuery('');
    setAddRows([]);
    markTouched();
  };

  // بحث المنتجات في الخادم: كل حرفٍ استعلامُه، بمهلة 300ms وصفحة ≤20.
  const sheetIdsKey = useMemo(
    () => lines.map((line) => line.product).sort((a, b) => a - b).join(','),
    [lines],
  );
  useEffect(() => {
    const query = addQuery.trim();
    if (!query) {
      setAddRows([]);
      setAddLoading(false);
      setAddError(null);
      return undefined;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setAddLoading(true);
      setAddError(null);
      inventoryApi.getProducts({
        search: query, page: 1, page_size: 20, status: 'all',
      }).then((data: ManualProductRow[] | { results?: ManualProductRow[] }) => {
        if (cancelled) return;
        const found = Array.isArray(data) ? data : (data?.results ?? []);
        const existing = new Set(
          sheetIdsKey ? sheetIdsKey.split(',').map((id) => Number(id)) : [],
        );
        setAddRows(found.filter((row) => !row.is_service && !existing.has(row.id)));
      }).catch((reason: unknown) => {
        if (cancelled) return;
        setAddRows([]);
        setAddError(reason instanceof Error ? reason.message : 'تعذّر البحث');
      }).finally(() => {
        if (!cancelled) setAddLoading(false);
      });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [addQuery, sheetIdsKey]);

  const addOptions: KitAutocompleteOption[] = useMemo(() => addRows.map((product) => ({
    id: product.id,
    label: productLabel(product),
    sub: [
      product.sku,
      product.category != null
        ? categoryPathLabel(treeCategories, product.category, `تصنيف #${product.category}`)
        : 'بدون تصنيف',
      product.is_active === false ? 'غير فعّال' : '',
    ].filter(Boolean).join(' · '),
    keywords: `${product.sku ?? ''} ${product.name_ar ?? ''} ${product.name_en ?? ''} ${product.brand ?? ''}`
      .toLocaleLowerCase('ar'),
  })), [addRows, treeCategories]);

  /** قراءة الجديدة ثم وضع التعديلات المحلية فوقها — تُستعمل في «تحديث» و412. */
  const refreshWithLocalEdits = useCallback(async (source: 'manual' | 'stale') => {
    const requestedId = editingId;
    if (requestedId == null) return;
    const setBusy = source === 'stale' ? setStaleBusy : setRefreshing;
    const setFailure = source === 'stale' ? setStaleError : setErr;
    setBusy(true);
    setFailure(null);
    try {
      const { stocktake, etag: token } = await inventoryApi.getStocktake(requestedId);
      // فُتح جردٌ آخر أثناء القراءة: ردُّ هذا لا يُكتب فوقه (لا توكن ولا لقطة ولا بنود).
      if (editingIdRef.current !== requestedId) return;
      const fresh = sheetLinesFromStocktake(stocktake.lines || []);
      const freshHeader: StocktakeHeader = {
        date: stocktake.stocktake_date || today,
        warehouse: stocktake.warehouse ?? '',
        notes: stocktake.notes || '',
      };
      // لقطة الخادم صارت هذه — عليها تُعاد أي مسودّةٍ تُستعاد بعدها، وعليها
      // تُقارَن حقول الرأس المحلية.
      serverSnapshotRef.current = { docId: requestedId, lines: fresh, header: freshHeader };
      // البنود والحذفات والرأس ومرجعيته تُقرأ كلها من المرايا **بعد** وصول الردّ
      // (لا من نسخةٍ ملتقطة لحظة الضغط): ضوابط التعديل معطَّلة ما دام `sheetBusy`،
      // ومسودّةٌ تُستعرض أثناء القراءة صارت هي الحالة الحيّة فتُدمج كما هي.
      const merged = rebaseDraftRestore(
        fresh, linesStateRef.current, removedIdsStateRef.current,
      );
      const rebasedHeader = rebaseHeader(
        freshHeader,
        headerStateRef.current,
        headerBaselineRef.current,
      );
      setLines(merged.lines);
      setRemovedIds(merged.removedIds);
      setDate(rebasedHeader.header.date);
      setWarehouse(rebasedHeader.header.warehouse);
      setNotes(rebasedHeader.header.notes);
      setHeaderBaseline(freshHeader);
      setEtag(token);
      setDocUpdatedAt(stocktake.updated_at ?? null);
      setEditingPosted(!!stocktake.is_posted);
      const keptCount = merged.reapplied + rebasedHeader.kept;
      if (keptCount > 0) {
        setMsg(`أُعيد تطبيق تعديلاتك على ${arabicCount(keptCount, REAPPLY_FORMS)} — راجعها واحفظ`);
      } else {
        setMsg('✓ حُدِّث الجرد');
      }
      if (source === 'stale') setStaleOpen(false);
    } catch (reason) {
      setFailure(reason instanceof Error ? reason.message : 'تعذّر التحديث');
    } finally {
      setBusy(false);
    }
  }, [editingId, today]);

  const saveDraft = async (): Promise<boolean> => {
    if (editingId == null || editingPosted) return false;
    setErr(null);
    setMsg(null);
    setSaving(true);
    try {
      const lineChanges = buildStocktakeLinesPayload(lines, removedIds.length);
      const { stocktake, etag: token } = await inventoryApi.updateStocktake(
        editingId,
        {
          stocktake_date: date,
          warehouse: warehouse === '' ? null : Number(warehouse),
          notes,
          ...lineChanges,
        },
        etag,
      );
      applyStocktake(stocktake, token, { resetView: false });
      setMsg('✓ تم حفظ المسودة (بدون ترحيل)');
      void discardDraft();
      await load();
      return true;
    } catch (reason) {
      if (isStaleDocumentError(reason)) {
        setStaleError(null);
        setStaleOpen(true);
        return false;
      }
      setErr(reason instanceof Error ? reason.message : 'فشل الحفظ');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const requestPost = async () => {
    if (editingId == null || editingPosted) return;
    const saved = await saveDraft();
    if (!saved) return;
    setPostUncountedAsZero(false);
    setPostError(null);
    setPostOpen(true);
  };

  const confirmPost = async () => {
    if (editingId == null) return;
    setPostBusy(true);
    setPostError(null);
    try {
      await inventoryApi.postStocktake(editingId, {
        uncounted_as_zero: postUncountedAsZero,
      });
      const { stocktake, etag: token } = await inventoryApi.getStocktake(editingId);
      applyStocktake(stocktake, token, { resetView: false });
      setPostOpen(false);
      setMsg('✓ تم الترحيل (تسوية المخزون + قيد الفرق)');
      void discardDraft();
      await load();
    } catch (reason) {
      setPostError(reason instanceof Error ? reason.message : 'فشل الترحيل');
    } finally {
      setPostBusy(false);
    }
  };

  // ── المشتقات ─────────────────────────────────────────────────────────────
  const progress = useMemo(() => countStocktakeProgress(lines), [lines]);
  const invalidCount = useMemo(
    () => lines.filter((line) => !validateCountedQuantity(line.counted_quantity)).length,
    [lines],
  );
  const invalidReason = invalidCount > 0
    ? arabicCount(invalidCount, {
      one: 'بندٌ واحد بكمية غير صالحة',
      two: 'بندان بكميات غير صالحة',
      few: 'بنود بكميات غير صالحة',
      many: 'بنداً بكميات غير صالحة',
    })
    : null;
  const filtered = useMemo(
    () => filterStocktakeLines(lines, {
      query: search,
      mode: filterMode,
      posted: editingPosted,
    }),
    [lines, search, filterMode, editingPosted],
  );
  const groups = useMemo(
    () => groupStocktakeLines(filtered, treeCategories),
    [filtered, treeCategories],
  );

  const openNewStocktake = async () => {
    const decision = await confirmDiscardEdits();
    if (decision === 'cancel') return;
    discardOnCreateRef.current = decision === 'discard';
    setErr(null);
    setMsg(null);
    setNewOpen(true);
  };

  const printSheet = () => {
    if (!filtered.length) {
      setErr('لا بنود للطباعة (راجع البحث أو الفلتر)');
      return;
    }
    const whName = warehouses.find((row) => row.id === Number(warehouse))?.name
      || 'كل المخزون';
    const escape = (text: string) => text.replace(
      /[&<>]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[char] as string),
    );
    const body = groups.map((group) => {
      const header = `<tr><td colspan="6" style="background:#eef;font-weight:700;text-align:right">`
        + `${escape(group.label)} (${formatNumber(group.lines.length)})</td></tr>`;
      const rows = group.lines.map((line) => {
        const variance = stocktakeVariance(line, editingPosted);
        const color = variance === null || variance === 0
          ? '#555' : variance > 0 ? '#15803d' : '#b91c1c';
        // الخاتم المعروض يخصّ القيمة المعروضة (والقاعدة نفسها في الجدول).
        const stamp = stocktakeStampText(line);
        return `<tr><td>${escape(line.product_sku)}</td>`
          + `<td style="text-align:right">${escape(line.product_name)}</td>`
          + `<td>${formatQuantity(line.product_quantity_on_hand, '—')}</td>`
          + `<td>${isCounted(line) ? formatQuantity(line.counted_quantity, '—') : '—'}</td>`
          + `<td style="color:${color};font-weight:700">`
          + `${variance === null ? '—' : signed(variance)}</td>`
          + `<td>${escape(stamp)}</td></tr>`;
      }).join('');
      return header + rows;
    }).join('');
    const html = `<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">`
      + `<title>ورقة الجرد ${escape(formatDateLocalized(date))}</title><style>`
      + `body{font-family:'Segoe UI',Tahoma,sans-serif;padding:18px;color:#111}`
      + `h1{font-size:18px;margin:0 0 4px}.meta{font-size:12px;color:#555;margin-bottom:12px}`
      + `table{width:100%;border-collapse:collapse;font-size:13px}`
      + `th,td{border:1px solid #bbb;padding:6px 8px;text-align:center}`
      + `th{background:#f0f0f0}@media print{button{display:none}}`
      + `</style></head><body>`
      + `<h1>ورقة الجرد</h1>`
      + `<div class="meta">التاريخ: ${escape(formatDateLocalized(date))} · المستودع: ${escape(whName)}`
      + `${notes ? ` · ملاحظات: ${escape(notes)}` : ''} · معدود: `
      + `${formatNumber(progress.counted)} / ${formatNumber(progress.total)}</div>`
      + `<table><thead><tr><th>الرمز</th><th>المنتج</th><th>رصيد النظام</th>`
      + `<th>المعدودة</th><th>الفرق</th><th>عدّه</th></tr></thead><tbody>${body}</tbody></table>`
      + `<script>window.onload=function(){window.print()}</script></body></html>`;
    const win = window.open('', '_blank', 'width=900,height=700');
    if (!win) {
      setErr('تعذّر فتح نافذة الطباعة (قد يكون المتصفح يحجب النوافذ المنبثقة)');
      return;
    }
    win.document.write(html);
    win.document.close();
  };

  const actions: KitToolbarAction[] = [
    {
      key: 'new',
      label: 'جرد جديد',
      icon: <Plus />,
      onClick: () => { void openNewStocktake(); },
    },
    {
      key: 'refresh',
      label: 'تحديث',
      icon: <RefreshCw className={loading ? 'animate-spin' : ''} />,
      onClick: () => void load(),
      separatorBefore: true,
    },
    {
      key: 'back',
      label: 'عودة',
      icon: <X />,
      onClick: () => navigate(-1),
      danger: true,
      separatorBefore: true,
    },
  ];

  return (
    <div className="min-h-[calc(100vh-5rem)]">
      <KitDocumentShell
        title="الجرد (جرد المخزون)"
        state={`${formatNumber(rows.length)} مستند`}
        actions={actions}
        status={editingId != null && draftSavedAt ? (
          <span className="ktra-status-item" data-testid="draft-saved-indicator">
            مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
          </span>
        ) : undefined}
      >
        <div className="p-2">
          {err && <div className="ktra-banner ktra-banner--err mb-2">{err}</div>}
          {msg && (
            <div className="ktra-banner mb-2 text-[var(--ktra-ok)]">{msg}</div>
          )}
          <DocumentDraftBanners
            draft={{
              ...draftApi,
              // شريط مسودّةٍ لا تخصّ الجرد المفتوح (إصدارٌ أقدم أو جردٌ آخر) لا
              // يُعرض أصلاً: الخطّاف يضع شريطه بعد نداء `onRestore`، فإخفاؤه من
              // هناك لا يصمد؛ والفحص هنا بالقاعدة النقية نفسها التي تحرس التطبيق.
              restoredBanner: isApplicableStocktakeDraft(
                draftApi.restoredBanner?.payload, editingId,
              ) ? draftApi.restoredBanner : null,
            }}
            onApplyDraft={onRestoreDraft}
            onUndo={handleUndoDraft}
            isTouched={touched}
          />

          {editingId != null && (
            <div
              data-testid="stocktake-sheet"
              className="ktra-bg-panel mb-3 rounded border border-[var(--ktra-border)] p-2.5"
            >
              <div className={`ktra-banner mb-2 ${
                editingPosted ? 'text-[var(--ktra-warn-fg)]' : 'text-[var(--ktra-ink)]'
              }`}>
                {editingPosted
                  ? `عرض جرد مُرحَّل #${editingId} — للقراءة فقط (لا يمكن تعديله)`
                  : `تعديل مسودة جرد #${editingId} — راجع ثم احفظ أو رحّل`}
              </div>

              <div className="mb-2 flex flex-wrap gap-2">
                <label className="ktra-field">
                  <span className="ktra-field-label">التاريخ</span>
                  <input
                    type="date"
                    className="ktra-input"
                    value={date}
                    disabled={editingPosted || saving || sheetBusy}
                    onChange={(event) => { setDate(event.target.value); markTouched(); }}
                  />
                </label>
                <label className="ktra-field">
                  <span className="ktra-field-label">المستودع</span>
                  <select
                    className="ktra-input"
                    value={warehouse}
                    disabled={editingPosted || saving || sheetBusy}
                    onChange={(event) => {
                      setWarehouse(event.target.value ? Number(event.target.value) : '');
                      markTouched();
                    }}
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
                    data-testid="stocktake-notes"
                    value={notes}
                    disabled={editingPosted || saving || sheetBusy}
                    onChange={(event) => { setNotes(event.target.value); markTouched(); }}
                  />
                </label>
              </div>

              <div className="mb-2 flex flex-wrap items-center gap-3 text-[13px]">
                <span data-testid="stocktake-progress" className="flex items-center gap-2">
                  <span className="text-[var(--ktra-ink-soft)]">معدود</span>
                  <b>{formatNumber(progress.counted)}</b>
                  <span className="text-[var(--ktra-ink-soft)]">/</span>
                  <b>{formatNumber(progress.total)}</b>
                  <progress
                    className="h-2 w-36 accent-[var(--ktra-accent)]"
                    value={progress.counted}
                    max={Math.max(progress.total, 1)}
                    aria-label="تقدّم العدّ"
                  />
                </span>
                <span className="text-[var(--ktra-ink-soft)]">
                  غير معدود: <b>{formatNumber(progress.uncounted)}</b>
                </span>
                <div className="w-full sm:w-56">
                  <input
                    className="ktra-input w-full"
                    data-testid="stocktake-search"
                    value={search}
                    disabled={saving}
                    placeholder="ابحث بالاسم أو الرمز…"
                    aria-label="بحث في بنود الجرد"
                    onChange={(event) => setSearch(event.target.value)}
                  />
                </div>
                <select
                  className="ktra-input w-auto"
                  data-testid="stocktake-filter"
                  value={filterMode}
                  disabled={saving}
                  aria-label="تصفية بنود الجرد"
                  onChange={(event) => setFilterMode(event.target.value as FilterMode)}
                >
                  {FILTER_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="ktra-toolbtn"
                  onClick={() => void refreshWithLocalEdits('manual')}
                  disabled={refreshing || saving}
                  title="أعد قراءة الجرد من الخادم مع إبقاء تعديلاتك غير المحفوظة"
                >
                  <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                  تحديث
                </button>
                <button type="button" className="ktra-toolbtn" onClick={printSheet}>
                  <Printer className="h-4 w-4" />
                  طباعة
                </button>
              </div>

              {!editingPosted && (
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="ktra-field-label">إضافة منتج (بحث في الخادم)</span>
                  <div className="w-80 max-w-full">
                    <KitAutocomplete
                      value=""
                      options={addOptions}
                      maxResults={20}
                      disabled={saving || sheetBusy}
                      onPick={addProduct}
                      onTextChange={setAddQuery}
                      onInfo={(id) => setCardProductId(Number(id))}
                      placeholder="اكتب الاسم أو الرمز…"
                    />
                  </div>
                  {addLoading && <RefreshCw className="h-4 w-4 animate-spin" />}
                  {addError && (
                    <span className="text-xs text-[var(--ktra-danger)]">{addError}</span>
                  )}
                </div>
              )}

              <table className="ktra-grid mb-2" data-variant="list">
                <thead>
                  <tr>
                    <th>المنتج</th>
                    <th className="w-[13%]">رصيد النظام</th>
                    <th className="w-[20%]">الكمية المعدودة</th>
                    <th className="w-[12%]">الفرق</th>
                    <th className="w-[18%]">عدّه</th>
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody>
                  {groups.map((group) => (
                    <React.Fragment key={group.key}>
                      <tr className="bg-[var(--ktra-bg-soft,#e7ecf1)]">
                        <td colSpan={6} className="font-bold">
                          {group.label}
                          <span className="ms-1 font-normal text-[var(--ktra-ink-soft)]">
                            ({formatNumber(group.lines.length)})
                          </span>
                        </td>
                      </tr>
                      {group.lines.map((line) => {
                        const variance = stocktakeVariance(line, editingPosted);
                        const color = variance === null || variance === 0
                          ? 'text-[var(--ktra-ink-soft)]'
                          : variance > 0 ? 'text-[var(--ktra-ok)]' : 'text-[var(--ktra-danger)]';
                        return (
                          <tr key={line.product} data-testid="stocktake-line">
                            <td>
                              <div className="flex items-center gap-1.5">
                                <button
                                  type="button"
                                  className="text-start font-medium text-blue-700 hover:underline"
                                  onClick={() => setCardProductId(line.product)}
                                  title="بطاقة المنتج"
                                >
                                  {line.product_name}
                                </button>
                                {line.product_sku && (
                                  <span className="font-mono text-xs text-[var(--ktra-ink-soft)]">
                                    {line.product_sku}
                                  </span>
                                )}
                                {!line.product_is_active && (
                                  <span className="rounded border border-[var(--ktra-warn-bd)] bg-[var(--ktra-warn-bg)] px-1 text-[10px] text-[var(--ktra-warn-fg)]">
                                    غير فعّال
                                  </span>
                                )}
                                <button
                                  type="button"
                                  className="ktra-iconbtn"
                                  onClick={() => setCardProductId(line.product)}
                                  title="بطاقة المنتج"
                                  aria-label={`بطاقة المنتج ${line.product_name}`}
                                >
                                  <Info className="h-3 w-3" />
                                </button>
                              </div>
                            </td>
                            <td className="text-center text-[var(--ktra-ink-soft)]">
                              {formatQuantity(line.product_quantity_on_hand, '—')}
                            </td>
                            <td>
                              <input
                                type="number"
                                min="0"
                                step="any"
                                className={`ktra-input w-full ${
                                  validateCountedQuantity(line.counted_quantity)
                                    ? ''
                                    : 'border-[var(--ktra-danger)]! ring-1 ring-[var(--ktra-danger)]'
                                }`}
                                data-testid={`stocktake-count-${line.product}`}
                                value={line.counted_quantity}
                                placeholder="عدّ…"
                                aria-invalid={!validateCountedQuantity(line.counted_quantity)}
                                aria-label={`الكمية المعدودة — ${line.product_name}`}
                                disabled={editingPosted || saving || sheetBusy}
                                onChange={(event) => updateLineQuantity(
                                  line.product, event.target.value,
                                )}
                              />
                            </td>
                            <td className={`text-center font-bold ${color}`}>
                              {variance === null ? '—' : signed(variance)}
                            </td>
                            <td className="text-center text-xs text-[var(--ktra-ink-soft)]">
                              {stocktakeStampText(line)}
                            </td>
                            <td className="text-center">
                              {!editingPosted && (
                                <button
                                  type="button"
                                  className="ktra-iconbtn"
                                  onClick={() => removeLine(line)}
                                  disabled={saving || sheetBusy}
                                  title="حذف البند"
                                  aria-label={`حذف بند ${line.product_name}`}
                                >
                                  <Trash2 className="h-3 w-3" />
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  ))}
                  {!filtered.length && (
                    <tr>
                      <td colSpan={6} className="p-4 text-center text-[var(--ktra-ink-soft)]">
                        {lines.length
                          ? 'لا بنود تطابق البحث أو الفلتر'
                          : 'لا بنود في هذا الجرد — أضف منتجاً بالبحث أعلاه'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {editingPosted ? (
                <div className="flex gap-2">
                  <button
                    className="ktra-toolbtn ms-auto"
                    onClick={closeSheet}
                  >
                    <X className="h-4 w-4" /> إغلاق
                  </button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {invalidReason && (
                    <span
                      role="alert"
                      data-testid="stocktake-invalid-lines"
                      className="text-xs font-medium text-[var(--ktra-danger)]"
                    >
                      {invalidReason}
                    </span>
                  )}
                  <button
                    className="ktra-toolbtn ms-auto"
                    data-testid="stocktake-save"
                    onClick={() => void saveDraft()}
                    disabled={saving || refreshing || invalidCount > 0}
                    title="حفظ كمسودة بدون ترحيل"
                  >
                    {saving
                      ? <RefreshCw className="h-4 w-4 animate-spin" />
                      : <Save className="h-4 w-4" />}
                    حفظ
                  </button>
                  <button
                    className="ktra-toolbtn"
                    data-testid="stocktake-post"
                    onClick={() => void requestPost()}
                    disabled={saving || refreshing || invalidCount > 0}
                    title="حفظ ثم فتح نافذة الترحيل"
                  >
                    {saving
                      ? <RefreshCw className="h-4 w-4 animate-spin" />
                      : <Send className="h-4 w-4" />}
                    ترحيل
                  </button>
                  <button className="ktra-toolbtn" onClick={() => void requestCloseSheet()} disabled={saving}>
                    <X className="h-4 w-4" /> إغلاق
                  </button>
                </div>
              )}
            </div>
          )}

          <table className="ktra-grid" data-variant="list">
            <thead>
              <tr>
                <th className="w-14">#</th>
                <th className="w-28">الرقم</th>
                <th className="w-28">التاريخ</th>
                <th>المستودع</th>
                <th className="w-32">التقدّم</th>
                <th className="w-52">الحالة</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-4 text-center text-[var(--ktra-ink-soft)]">
                    لا عمليات جرد
                  </td>
                </tr>
              )}
              {rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => void openStocktake(row.id)}
                  className="cursor-pointer"
                  title="انقر لفتح المستند"
                >
                  <td>#{row.id}</td>
                  <td>{row.stocktake_number || '—'}</td>
                  <td>{formatDateLocalized(row.stocktake_date)}</td>
                  <td>{row.warehouse_name || 'كل المخزون'}</td>
                  <td className="text-center">
                    {formatNumber(row.counted_count)} / {formatNumber(row.line_count)}
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <button
                        className="ktra-toolbtn"
                        onClick={(event) => {
                          event.stopPropagation();
                          void openStocktake(row.id);
                        }}
                      >
                        {row.is_posted ? 'عرض' : 'فتح'}
                      </button>
                      {row.is_posted ? (
                        <span className="font-semibold text-[var(--ktra-ok)]">
                          مُرحَّل {row.journal ? `#${row.journal}` : ''}
                        </span>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </KitDocumentShell>

      {newOpen && (
        <NewStocktakeModal
          categories={treeCategories}
          warehouses={warehouses}
          onClose={() => {
            discardOnCreateRef.current = false;
            setNewOpen(false);
          }}
          onCreated={async ({ stocktake, etag: token }) => {
            setNewOpen(false);
            if (discardOnCreateRef.current) {
              discardOnCreateRef.current = false;
              await discardSheetDraft();
            }
            applyStocktake(stocktake, token);
            setMsg('✓ أُنشئ الجرد — ابدأ العدّ');
            void load();
          }}
        />
      )}

      {postOpen && (
        <PostStocktakeModal
          total={lines.length}
          uncounted={progress.uncounted}
          uncountedAsZero={postUncountedAsZero}
          busy={postBusy}
          error={postError}
          onChange={setPostUncountedAsZero}
          onClose={() => { if (!postBusy) setPostOpen(false); }}
          onConfirm={() => void confirmPost()}
        />
      )}

      {staleOpen && (
        <StaleStocktakeModal
          busy={staleBusy}
          error={staleError}
          onClose={() => { if (!staleBusy) setStaleOpen(false); }}
          onRefresh={() => void refreshWithLocalEdits('stale')}
        />
      )}

      {cardProductId != null && (
        <ProductCardModal productId={cardProductId} onClose={() => setCardProductId(null)} />
      )}
    </div>
  );
};

export default StocktakePage;
