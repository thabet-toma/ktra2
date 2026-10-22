/**
 * K4 — صفحة عدّ الموظف `/count/:token`: جوال أولاً، بلا تسجيل ولا قشرة تطبيق.
 *
 * **الطلب العاري وحده:** `fetch` مع `API_BASE` (الثابت) و`credentials: 'omit'` —
 * لا `restApi` المصادَق ولا توكن ولا شركة جلسة. والخادم يشتقّ الشركة من التوكن.
 *
 * **الحفظ التلقائي:** تغييرٌ ⇒ السطر متّسخ ⇒ مهلة 1500ms ⇒ دفعةٌ واحدة (≤500)
 * في الطلب، وطلبٌ واحد في الطيران. القيمة تُكتب في `localStorage` قبل أي طلب،
 * فانقطاعُ الشبكة أو إغلاق الصفحة لا يضيّع عدّاً؛ وبعد النجاح تُحذف من النسخة
 * المحلية. والخطأ المحلي (سالب/غير رقمي/أكثر من أربع منازل/15 رقماً صحيحاً)
 * لا يُرسل. وردُّ `ignored > 0` — سطرٌ خرج من نطاق الرابط — لا يُعلَّم محفوظاً
 * ولا يمحو نسخته المحلية، بل يوقف الطابور حتى إعادة تحميل الصفحة.
 *
 * **ما لا يظهر أبداً:** تكلفة، سعر، قيمة مالية، أو رابطٌ للتطبيق.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertTriangle, CheckCircle2, Clock, Loader2, RefreshCw, Search, ShieldAlert, WifiOff,
} from 'lucide-react';
import { API_BASE } from '../../services/restApi';
import { useConfirm } from '../../contexts/ConfirmContext';
import { formatDateValue } from '../../utils/formatDate';
import { formatNumber, formatQuantity } from '../../utils/formatNumber';
import { arabicCount } from '../../utils/stocktake';
import {
  canonicalQuantityText,
  countInputVariance,
  countLineInputValue,
  countUncounted,
  filterCountLines,
  groupCountLines,
  parseCountedInput,
} from '../../utils/stocktakeCountLinks';
import type { PublicStocktakeCount } from '../../types/inventory';

type Phase = 'loading' | 'ready' | 'not_found' | 'gone' | 'throttled' | 'error';

type RowState =
  | { kind: 'pending' }
  | { kind: 'saved' }
  | { kind: 'error'; message: string };

interface DraftBatchItem {
  lineId: number;
  raw: string;
  value: string | null;
}

const countUrl = (token: string): string =>
  `${API_BASE}/share/${encodeURIComponent(token)}/count/`;

const storageKeyFor = (token: string): string => `ktra.count.${token}`;

/** نسخة محلية آمنة: كل وصولٍ في try/catch — وضع التصفح الخاص يرمي. */
const readLocalCopy = (key: string): Record<string, string> => {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as { v?: number; values?: unknown };
    if (parsed?.v !== 1 || parsed.values == null || typeof parsed.values !== 'object') return {};
    const values: Record<string, string> = {};
    for (const [lineId, value] of Object.entries(parsed.values as Record<string, unknown>)) {
      if (typeof value === 'string') values[lineId] = value;
    }
    return values;
  } catch {
    return {};
  }
};

const writeLocalCopy = (
  key: string,
  dirtyIds: ReadonlySet<number>,
  values: Record<number, string>,
): void => {
  try {
    const stored: Record<string, string> = {};
    for (const lineId of dirtyIds) {
      const value = values[lineId];
      if (value !== undefined) stored[String(lineId)] = value;
    }
    if (Object.keys(stored).length) {
      window.localStorage.setItem(key, JSON.stringify({ v: 1, values: stored }));
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    // لا نسخة محلية في وضع التصفح الخاص — الصفحة تعمل، والشبكة وحدها تحفظ.
  }
};

const removeLocalCopy = (key: string): void => {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // تجاهل — لا شيء يمكن فعله.
  }
};

/** أوّل رسالةٍ من أيّ شكل خطأ DRF على سطر — `{counted_quantity:[msg]}`. */
const rowErrorText = (raw: unknown): string => {
  if (typeof raw === 'string') return raw;
  if (Array.isArray(raw)) return rowErrorText(raw[0]);
  if (raw && typeof raw === 'object') {
    for (const value of Object.values(raw as Record<string, unknown>)) {
      const message = rowErrorText(value);
      if (message) return message;
    }
  }
  return 'سطر العدّ غير صالح.';
};

const signed = (value: number): string =>
  value > 0 ? `+${formatQuantity(value)}` : formatQuantity(value);

const StateScreen: React.FC<{
  icon: React.ReactNode;
  title: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}> = ({ icon, title, message, onRetry, retryLabel = 'إعادة المحاولة' }) => (
  <div className="min-h-screen bg-slate-50 px-4 py-16 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
    <div className="mx-auto w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
        {icon}
      </div>
      <h1 className="mt-4 text-lg font-bold">{title}</h1>
      <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-emerald-600 px-4 text-sm font-bold text-white hover:bg-emerald-700"
        >
          <RefreshCw className="h-4 w-4" /> {retryLabel}
        </button>
      )}
    </div>
  </div>
);

export const PublicStocktakeCountPage: React.FC = () => {
  const { token = '' } = useParams<{ token: string }>();
  const confirm = useConfirm();
  const storageKey = storageKeyFor(token);

  const [phase, setPhase] = useState<Phase>('loading');
  const [data, setData] = useState<PublicStocktakeCount | null>(null);
  const [values, setValues] = useState<Record<number, string>>({});
  const [rowStates, setRowStates] = useState<Record<number, RowState>>({});
  const [query, setQuery] = useState('');
  const [uncountedOnly, setUncountedOnly] = useState(false);
  const [retryBanner, setRetryBanner] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [scopeChanged, setScopeChanged] = useState(false);
  const [finished, setFinished] = useState(false);
  const [finishing, setFinishing] = useState(false);

  const valuesRef = useRef<Record<number, string>>({});
  const dirtyRef = useRef<Set<number>>(new Set());
  const blockedRef = useRef<Set<number>>(new Set());
  const debounceRef = useRef<number | null>(null);
  const retryRef = useRef<number | null>(null);
  const finishRetryRef = useRef<number | null>(null);
  // طابور الحفظ وطلب الإنهاء لا يتقاسمان رايةً واحدة: تصفيرُ الطابور لرايتِه
  // أثناء طيران «انتهيت» كان يجعل تحذير الإغلاق أعمى عن طلبِ إنهاءٍ حقيقي.
  const inflightRef = useRef(false);
  const finishInflightRef = useRef(false);
  const scopeChangedRef = useRef(false);
  const mountedRef = useRef(true);
  const chainRef = useRef<Promise<void>>(Promise.resolve());
  const enqueueRef = useRef<() => void>(() => {});
  const sendFinishedRef = useRef<() => Promise<void>>(async () => {});

  const persistLocal = useCallback(() => {
    writeLocalCopy(storageKey, dirtyRef.current, valuesRef.current);
  }, [storageKey]);

  const clearTimers = useCallback(() => {
    if (debounceRef.current != null) {
      window.clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    if (retryRef.current != null) {
      window.clearTimeout(retryRef.current);
      retryRef.current = null;
    }
    if (finishRetryRef.current != null) {
      window.clearTimeout(finishRetryRef.current);
      finishRetryRef.current = null;
    }
  }, []);

  const goGone = useCallback(() => {
    clearTimers();
    dirtyRef.current.clear();
    removeLocalCopy(storageKey);
    setRetryBanner(false);
    setPhase('gone');
  }, [clearTimers, storageKey]);

  const scheduleRetry = useCallback(() => {
    setRetryBanner(true);
    if (retryRef.current != null) return;
    retryRef.current = window.setTimeout(() => {
      retryRef.current = null;
      enqueueRef.current();
    }, 10_000);
  }, []);

  /** إعادة «انتهيت» بعد 10 ث — فرعٌ واحد بدل نسختين في الشبكة والفشل. */
  const scheduleFinishRetry = useCallback(() => {
    setRetryBanner(true);
    if (finishRetryRef.current != null) return;
    finishRetryRef.current = window.setTimeout(() => {
      finishRetryRef.current = null;
      void sendFinishedRef.current();
    }, 10_000);
  }, []);

  const applyBatchErrors = (body: unknown, batch: DraftBatchItem[]): void => {
    const entries = (body as { entries?: unknown } | null)?.entries;
    if (entries == null || typeof entries !== 'object') {
      setPageError('تعذّر حفظ الأسطر — صحّح ما تراه ثم حاول.');
      return;
    }
    for (const [rawIndex, rawError] of Object.entries(entries as Record<string, unknown>)) {
      const item = batch[Number(rawIndex)];
      if (!item) continue;
      // الرسالة تخصّ القيمة **المرسلة**: إن كان الموظف قد صحّح السطر أثناء
      // الطيران فهي قديمة، ولا تُحجب القيمة الجديدة — تُترك متّسخةً وتُرسل
      // في الدورة التالية.
      if ((valuesRef.current[item.lineId] ?? '') !== item.raw) continue;
      blockedRef.current.add(item.lineId);
      setRowStates((prev) => ({
        ...prev,
        [item.lineId]: { kind: 'error', message: rowErrorText(rawError) },
      }));
    }
  };

  /** دفعةٌ واحدة في الطيران، من طابورٍ واحد: لا طلبان يكتبان السطر نفسه. */
  const runQueue = useCallback(async (): Promise<void> => {
    if (!token) return;
    // نطاق الرابط تغيّر: لا حفظ قبل إعادة تحميل — الكتابة سترفض السطر نفسه
    // كلّ مرة، والقائمة المعروضة لم تعد مطابقة للخادم.
    if (scopeChangedRef.current) return;
    for (;;) {
      const batch: DraftBatchItem[] = [];
      for (const lineId of dirtyRef.current) {
        if (blockedRef.current.has(lineId)) continue;
        const raw = valuesRef.current[lineId] ?? '';
        const parsed = parseCountedInput(raw);
        // `parsed.ok === false` لا `!parsed.ok`: مع `strictNullChecks: false` في
        // هذا المشروع لا يُضيّق النفيُ الاتحادَ (يفعلها فحص المساواة الصريح).
        if (parsed.ok === false) {
          const message = parsed.error;
          // الخطأ المحلي يحجب السطر عن الإرسال، لكن «انتهيت» تقرأ المتّسخ
          // وحده؛ بلا إضافته إلى `blockedRef` تقول «تعذّر حفظ بعض البنود»
          // بدل «صحّح الأسطر المعلَّمة بخطأ» — رسالةٌ صادقةٌ لكنها خاطئة السبب.
          blockedRef.current.add(lineId);
          setRowStates((prev) => ({
            ...prev,
            [lineId]: { kind: 'error', message },
          }));
          continue;
        }
        batch.push({ lineId, raw, value: parsed.value });
        if (batch.length >= 500) break;
      }
      if (!batch.length) return;

      setPageError(null);
      inflightRef.current = true;
      try {
        const response = await fetch(countUrl(token), {
          method: 'POST',
          credentials: 'omit',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            entries: batch.map((item) => ({
              line_id: item.lineId,
              counted_quantity: item.value,
            })),
          }),
        });
        if (response.status === 404) {
          setPhase('not_found');
          return;
        }
        if (response.status === 410) {
          goGone();
          return;
        }
        if (response.status === 429 || response.status >= 500) {
          scheduleRetry();
          return;
        }
        if (response.status === 413) {
          setPageError('حجم الطلب كبير جداً — حدّث الصفحة وحاول.');
          return;
        }
        if (response.status === 400) {
          const body = await response.json().catch(() => null);
          applyBatchErrors(body, batch);
          return;
        }
        if (!response.ok) {
          scheduleRetry();
          return;
        }
        const body = await response.json().catch(() => null) as
          { written?: number; ignored?: number; finished?: boolean } | null;
        if (body?.finished) setFinished(true);
        if ((body?.ignored ?? 0) > 0) {
          // سطرٌ خارج نطاق الرابط الآن (نُقل منتجه لتصنيفٍ آخر): الخادم تجاهله
          // بلا خطأ. تعليمه «✓ حُفظ» يمحو عدّاً لم يُكتب، فالطابور يتوقّف
          // والقيم تبقى في النسخة المحلية حتى إعادة التحميل.
          scopeChangedRef.current = true;
          setScopeChanged(true);
          persistLocal();
          return;
        }
        if (retryRef.current != null) {
          window.clearTimeout(retryRef.current);
          retryRef.current = null;
        }
        setRetryBanner(false);
        // التأكيد يخصّ **القيمة المرسلة**: تغيّرت أثناء الطيران ⇒ تبقى متّسخة
        // وتُرحَّل في الدورة التالية.
        for (const item of batch) {
          if (!dirtyRef.current.has(item.lineId)) continue;
          if ((valuesRef.current[item.lineId] ?? '') !== item.raw) continue;
          dirtyRef.current.delete(item.lineId);
          blockedRef.current.delete(item.lineId);
          setRowStates((prev) => ({ ...prev, [item.lineId]: { kind: 'saved' } }));
        }
        persistLocal();
      } catch {
        scheduleRetry();
        return;
      } finally {
        inflightRef.current = false;
      }
    }
  }, [goGone, persistLocal, scheduleRetry, token]);

  const enqueueFlush = useCallback(() => {
    chainRef.current = chainRef.current.then(() => runQueue()).catch(() => undefined);
  }, [runQueue]);
  enqueueRef.current = enqueueFlush;

  const scheduleSave = useCallback(() => {
    if (debounceRef.current != null) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      debounceRef.current = null;
      enqueueFlush();
    }, 1_500);
  }, [enqueueFlush]);

  const load = useCallback(async () => {
    if (!token) {
      setPhase('not_found');
      return;
    }
    clearTimers();
    setPhase('loading');
    setPageError(null);
    setRetryBanner(false);
    setScopeChanged(false);
    scopeChangedRef.current = false;
    setFinished(false);
    dirtyRef.current = new Set();
    blockedRef.current = new Set();
    try {
      const response = await fetch(countUrl(token), {
        method: 'GET',
        credentials: 'omit',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
      });
      if (!mountedRef.current) return;
      if (response.status === 404) {
        setPhase('not_found');
        return;
      }
      if (response.status === 410) {
        goGone();
        return;
      }
      if (response.status === 429) {
        setPhase('throttled');
        return;
      }
      if (!response.ok) {
        setPageError('تعذّر تحميل الجرد — حاول بعد قليل.');
        setPhase('error');
        return;
      }
      const payload = await response.json() as PublicStocktakeCount;
      if (!mountedRef.current) return;

      const nextValues: Record<number, string> = {};
      for (const line of payload.lines) {
        nextValues[line.line_id] = canonicalQuantityText(line.counted_quantity);
      }
      // نسخة هذا الجهاز تُطبَّق فوق قيم الخادم وتُعلَّم متّسخة وتُرسل فوراً — هي
      // عدٌّ لم يصل، لا اقتراحاً يُنتظر تأكيده.
      const local = readLocalCopy(storageKey);
      const dirty = new Set<number>();
      for (const [rawLineId, rawValue] of Object.entries(local)) {
        const lineId = Number(rawLineId);
        if (!Number.isInteger(lineId) || !(lineId in nextValues)) continue;
        const text = String(rawValue ?? '');
        // **الفراغ قيمةٌ محفوظة أيضاً**: مسحُ عدٍّ لم يصل بعد يجب أن يُعاد
        // إرسالُه `null`، لا أن يُسقَط لأن نصّه فارغ.
        if (canonicalQuantityText(text) === canonicalQuantityText(nextValues[lineId])) continue;
        nextValues[lineId] = text;
        dirty.add(lineId);
      }
      valuesRef.current = nextValues;
      setValues(nextValues);
      dirtyRef.current = dirty;
      const states: Record<number, RowState> = {};
      for (const line of payload.lines) {
        states[line.line_id] = dirty.has(line.line_id)
          ? { kind: 'pending' }
          : canonicalQuantityText(nextValues[line.line_id]) !== ''
            ? { kind: 'saved' }
            : { kind: 'pending' };
      }
      setRowStates(states);
      setData(payload);
      setFinished(Boolean(payload.finished));
      setPhase('ready');
      persistLocal();
      if (dirty.size) enqueueFlush();
    } catch {
      if (mountedRef.current) {
        setPageError('تعذّر الاتصال بالخادم — تحقّق من الشبكة.');
        setPhase('error');
      }
    }
  }, [clearTimers, enqueueFlush, goGone, persistLocal, storageKey, token]);

  useEffect(() => {
    mountedRef.current = true;
    void load();
    return () => {
      mountedRef.current = false;
      clearTimers();
    };
  }, [clearTimers, load]);

  // تحذير الإغلاق ما دام عدٌّ لم يُؤكَّد أو طلبٌ في الطيران (حفظٌ أو إنهاء).
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current.size && !inflightRef.current && !finishInflightRef.current) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  const handleValueChange = (lineId: number, text: string) => {
    const next = { ...valuesRef.current, [lineId]: text };
    valuesRef.current = next;
    setValues(next);
    dirtyRef.current.add(lineId);
    blockedRef.current.delete(lineId);
    setRowStates((prev) => ({ ...prev, [lineId]: { kind: 'pending' } }));
    setPageError(null);
    persistLocal();
    scheduleSave();
  };

  const sendFinished = useCallback(async () => {
    if (!token) return;
    setFinishing(true);
    setPageError(null);
    enqueueFlush();
    await chainRef.current;
    if (dirtyRef.current.size) {
      setPageError(
        blockedRef.current.size
          ? 'صحّح الأسطر المعلَّمة بخطأ أولاً، ثم أنهِ العدّ.'
          : 'تعذّر حفظ بعض البنود — حاول بعد قليل.',
      );
      setFinishing(false);
      return;
    }
    finishInflightRef.current = true;
    try {
      const response = await fetch(countUrl(token), {
        method: 'POST',
        credentials: 'omit',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ entries: [], finished: true }),
      });
      if (response.status === 404) {
        setPhase('not_found');
        return;
      }
      if (response.status === 410) {
        goGone();
        return;
      }
      if (response.status === 429 || response.status >= 500) {
        scheduleFinishRetry();
        return;
      }
      if (!response.ok) {
        setPageError('تعذّر إنهاء العدّ — حاول بعد قليل.');
        return;
      }
      const body = await response.json().catch(() => null) as { finished?: boolean } | null;
      if (body?.finished) setFinished(true);
      setRetryBanner(false);
    } catch {
      scheduleFinishRetry();
    } finally {
      finishInflightRef.current = false;
      setFinishing(false);
    }
  }, [enqueueFlush, goGone, scheduleFinishRetry, token]);
  sendFinishedRef.current = sendFinished;

  const requestFinish = async () => {
    if (!data) return;
    const uncounted = countUncounted(data.lines, valuesRef.current);
    const ok = await confirm({
      title: 'إنهاء العدّ',
      message: uncounted > 0
        ? `بقي ${arabicCount(uncounted, {
          one: 'بند واحد',
          two: 'بندان',
          few: 'بنود',
          many: 'بنداً',
        })} بلا عدّ. إنهاء على أيّ حال؟`
        : 'إنهاء العدّ؟',
      confirmText: 'إنهاء',
      danger: false,
    });
    if (!ok) return;
    await sendFinished();
  };

  const visibleLines = useMemo(
    () => (data ? filterCountLines(data.lines, { query, uncountedOnly, values }) : []),
    [data, query, uncountedOnly, values],
  );
  const groups = useMemo(() => groupCountLines(visibleLines), [visibleLines]);
  const progress = useMemo(() => {
    if (!data) return { total: 0, counted: 0 };
    const uncounted = countUncounted(data.lines, values);
    return { total: data.lines.length, counted: data.lines.length - uncounted };
  }, [data, values]);

  const head = (
    <>
      <title>عدّ الجرد — K.T.R.A</title>
      <meta name="robots" content="noindex" />
    </>
  );

  if (phase === 'loading') {
    return (
      <>
        {head}
        <div dir="rtl" className="min-h-screen bg-slate-50 px-3 py-4 dark:bg-slate-950">
          <div className="mx-auto w-full max-w-3xl animate-pulse space-y-3">
            <div className="h-24 rounded-xl bg-slate-200 dark:bg-slate-800" />
            <div className="h-11 rounded-lg bg-slate-200 dark:bg-slate-800" />
            {[1, 2, 3, 4, 5].map((row) => (
              <div key={row} className="h-24 rounded-lg bg-slate-200 dark:bg-slate-800" />
            ))}
          </div>
        </div>
      </>
    );
  }

  if (phase === 'not_found') {
    return (
      <>
        {head}
        <div dir="rtl">
          <StateScreen
            icon={<ShieldAlert className="h-6 w-6 text-amber-500" />}
            title="الرابط غير صحيح"
            message="تأكّد من نسخه كاملاً — الرابط لا يطابق أيّ جرد."
          />
        </div>
      </>
    );
  }

  if (phase === 'gone') {
    return (
      <>
        {head}
        <div dir="rtl">
          <StateScreen
            icon={<AlertTriangle className="h-6 w-6 text-amber-500" />}
            title="انتهى هذا الرابط"
            message="الجرد رُحِّل أو انتهت صلاحية الرابط. راجع المسؤول."
          />
        </div>
      </>
    );
  }

  if (phase === 'throttled') {
    return (
      <>
        {head}
        <div dir="rtl">
          <StateScreen
            icon={<Clock className="h-6 w-6 text-slate-500" />}
            title="حاول بعد قليل"
            message="الطلبات كثيرة الآن — انتظر دقيقة ثم أعد المحاولة."
            onRetry={() => void load()}
          />
        </div>
      </>
    );
  }

  if (phase === 'error' || !data) {
    return (
      <>
        {head}
        <div dir="rtl">
          <StateScreen
            icon={<WifiOff className="h-6 w-6 text-slate-500" />}
            title="تعذّر تحميل الجرد"
            message={pageError || 'تحقّق من اتصالك ثم أعد المحاولة.'}
            onRetry={() => void load()}
          />
        </div>
      </>
    );
  }

  return (
    <>
      {head}
      <div dir="rtl" className="min-h-screen bg-slate-50 pb-24 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto w-full max-w-3xl px-3 py-3">
            <p className="truncate text-xs text-slate-500 dark:text-slate-400">
              {data.company_name}
            </p>
            <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <h1 className="text-lg font-bold">
                {data.stocktake_number ? `جرد ${data.stocktake_number}` : 'جرد المخزون'}
              </h1>
              <span className="text-sm text-slate-500 dark:text-slate-400">
                {formatDateValue(data.date)}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {data.warehouse || 'كل المخزون'} · العادّ: <b className="text-slate-700 dark:text-slate-200">{data.counter_name}</b>
            </p>

            <div className="mt-2 flex items-center gap-2">
              <progress
                className="h-2 min-w-0 flex-1 accent-emerald-600"
                value={progress.counted}
                max={Math.max(progress.total, 1)}
                aria-label="تقدّم العدّ"
              />
              <span className="shrink-0 text-xs font-semibold text-slate-600 dark:text-slate-300" data-testid="count-progress">
                معدود {formatNumber(progress.counted)} من {formatNumber(progress.total)}
              </span>
            </div>

            {finished && (
              <p
                className="mt-2 flex items-center gap-1.5 rounded border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                data-testid="count-finished"
              >
                <CheckCircle2 className="h-4 w-4" />
                أنهيت — يمكنك التعديل حتى يرحّل المسؤول الجرد.
              </p>
            )}
          </div>
        </header>

        <div className="border-b border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute end-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                className="h-11 w-full rounded-lg border border-slate-300 bg-white px-3 pe-9 text-sm outline-none focus:border-emerald-500 focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-slate-700 dark:bg-slate-950"
                value={query}
                placeholder="ابحث بالاسم أو الرمز…"
                aria-label="بحث في بنود الجرد"
                data-testid="count-search"
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <label className="flex shrink-0 items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                className="h-4 w-4 accent-emerald-600"
                checked={uncountedOnly}
                data-testid="count-uncounted-only"
                onChange={(event) => setUncountedOnly(event.target.checked)}
              />
              غير المعدود فقط
            </label>
          </div>
        </div>

        <main className="mx-auto w-full max-w-3xl px-2 py-2">
          {scopeChanged && (
            <div
              role="alert"
              className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs font-semibold text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
            >
              <span>تغيّر نطاق الجرد — أعد تحميل الصفحة</span>
              <button
                type="button"
                className="shrink-0 rounded bg-amber-600 px-2 py-1 font-bold text-white hover:bg-amber-700"
                onClick={() => void load()}
              >
                إعادة التحميل
              </button>
            </div>
          )}
          {retryBanner && (
            <div
              role="alert"
              className="mb-2 flex items-center gap-1.5 rounded border border-amber-300 bg-amber-50 p-2 text-xs font-semibold text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
            >
              <Clock className="h-4 w-4 shrink-0" />
              حاول بعد قليل — عدّك محفوظ على هذا الجهاز
            </div>
          )}
          {pageError && (
            <div
              role="alert"
              className="mb-2 rounded border border-red-300 bg-red-50 p-2 text-xs font-semibold text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200"
            >
              {pageError}
            </div>
          )}

          {groups.map((group) => (
            <section key={group.key} className="mb-2">
              <h2 className="sticky top-0 z-10 -mx-2 border-b border-slate-200 bg-slate-50/95 px-3 py-1.5 text-xs font-bold text-slate-600 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 dark:text-slate-300">
                {group.label}
                <span className="ms-1 font-normal text-slate-400">
                  ({formatNumber(group.lines.length)})
                </span>
              </h2>
              <ul className="space-y-1.5 pt-1.5">
                {group.lines.map((line) => {
                  const value = countLineInputValue(line, values);
                  const variance = countInputVariance(line.system_quantity, value);
                  const state = rowStates[line.line_id] ?? { kind: 'pending' };
                  const invalid = state.kind === 'error';
                  return (
                    <li
                      key={line.line_id}
                      className={`rounded-lg border bg-white p-2.5 shadow-sm dark:bg-slate-900 ${
                        invalid
                          ? 'border-red-300 dark:border-red-800'
                          : 'border-slate-200 dark:border-slate-800'
                      }`}
                      data-testid={`count-row-${line.line_id}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="break-words text-sm font-semibold">{line.name}</p>
                          <p className="break-words text-[11px] text-slate-500 dark:text-slate-400">
                            {[line.sku, line.brand].filter(Boolean).join(' · ')}
                          </p>
                        </div>
                        <span className="max-w-24 shrink-0 truncate rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300" title={line.uom || undefined}>
                          {line.uom || '—'}
                        </span>
                      </div>

                      <div className="mt-2 flex items-end gap-2">
                        <div className="w-16 shrink-0 text-center">
                          <p className="text-[10px] text-slate-500 dark:text-slate-400">كمية النظام</p>
                          <p className="break-all font-mono text-xs">
                            {formatQuantity(line.system_quantity, '—')}
                          </p>
                        </div>
                        <label className="min-w-0 flex-1">
                          <span className="sr-only">الكمية المعدودة — {line.name}</span>
                          <input
                            type="text"
                            inputMode="decimal"
                            dir="ltr"
                            className={`h-11 w-full min-w-0 rounded-lg border bg-white px-2 text-center text-base font-bold outline-none focus:border-emerald-500 focus-visible:ring-2 focus-visible:ring-emerald-500 dark:bg-slate-950 ${
                              invalid
                                ? 'border-red-400 ring-1 ring-red-300'
                                : 'border-slate-300 dark:border-slate-700'
                            }`}
                            value={value}
                            placeholder="عدّ…"
                            aria-invalid={invalid}
                            data-testid={`count-input-${line.line_id}`}
                            onChange={(event) => handleValueChange(line.line_id, event.target.value)}
                          />
                        </label>
                        <div className="w-16 shrink-0 text-center">
                          <p className="text-[10px] text-slate-500 dark:text-slate-400">الفرق</p>
                          <p
                            className={`break-all font-mono text-xs font-bold ${
                              variance == null || variance === 0
                                ? 'text-slate-400'
                                : variance > 0
                                  ? 'text-emerald-600 dark:text-emerald-400'
                                  : 'text-red-600 dark:text-red-400'
                            }`}
                            data-testid={`count-variance-${line.line_id}`}
                          >
                            {variance == null ? '—' : signed(variance)}
                          </p>
                        </div>
                      </div>

                      <div className="mt-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-[11px]">
                        <span
                          className={
                            state.kind === 'error'
                              ? 'font-semibold text-red-600 dark:text-red-400'
                              : state.kind === 'saved'
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-slate-400'
                          }
                          data-testid={`count-state-${line.line_id}`}
                        >
                          {state.kind === 'error'
                            ? `⚠ ${state.message}`
                            : state.kind === 'saved'
                              ? '✓ حُفظ'
                              : '⏳ ينتظر'}
                        </span>
                        {state.kind === 'saved' && line.counted_by_name && (
                          <span className="text-slate-400">
                            عدّه: {line.counted_by_name}
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}

          {!groups.length && (
            <p className="rounded border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
              {data.lines.length
                ? 'لا بنود تطابق البحث أو الفلتر'
                : 'لا بنود في هذا الجرد'}
            </p>
          )}
        </main>

        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 p-2 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
          <div className="mx-auto flex w-full max-w-3xl items-center gap-2">
            <span className="min-w-0 flex-1 text-xs text-slate-600 dark:text-slate-300">
              معدود {formatNumber(progress.counted)} من {formatNumber(progress.total)}
            </span>
            <button
              type="button"
              className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg bg-emerald-600 px-4 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-60"
              disabled={finishing || finished}
              data-testid="count-finish"
              onClick={() => void requestFinish()}
            >
              {finishing
                ? <><Loader2 className="h-4 w-4 animate-spin" /> جارٍ الإنهاء…</>
                : finished
                  ? <><CheckCircle2 className="h-4 w-4" /> أنهيت</>
                  : 'انتهيت'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
};
