/**
 * ISSUE #118 — الخطّاف المشترك لمسودّات المستندات المحلّية (IndexedDB).
 *
 * غلافٌ رقيقٌ فوق `utils/documentDraft.ts` (وحدة القرار — كل المنطق هناك، لا
 * قرار هنا). أوّل مستهلك: `InvoiceForm` (فاتورة الشراء) — التي لا تحفظ شيئاً
 * اليوم إطلاقاً. سابقة النمط: `hooks/useSimpleUi.ts` (غلافٌ رقيق فوق دوالّ صرفة).
 *
 * العقد (issue #109 §٢): `useDocumentDraft({ docType, docId, payload, isTouched,
 * onRestore })` — و`isPosted`/`docUpdatedAt` اختياريان فوق العقد الأساسي لخدمة
 * قرار الاستعادة (§٩) بلا كسر التوقيع المذكور في المواصفة.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Dexie from "dexie";

import db from "@/services/offline/db";
import { resolveTenantId } from "@/utils/tenantContext";
import { tabId, subscribeTabPresence, isTabIdLive } from "@/utils/tabLink";
import { isOfflineRecordForTenant } from "@/utils/offlineTenantScope";
import { useToast } from "@/contexts/ToastContext";
import {
  buildDocumentDraftKey,
  draftPreviewLine,
  evaluateDraftRestore,
  selectOrphanDrafts,
  shouldPersistDraft,
  shouldWarnCrossTabWrite,
  type DraftRestoreEligibility,
} from "@/utils/documentDraft";

/** بعد ٥٠٠ms من آخر تغيير — بدل ٢٠٠٠ اليوم في `SalesInvoiceEditor` (issue #109 §٣). */
const WRITE_DEBOUNCE_MS = 500;

export interface UseDocumentDraftOptions<TPayload> {
  /** نوع المستند — يدخل في مفتاح العزل (`"purchase_invoice"`, `"price_offer"`…). */
  docType: string;
  /** معرّف المستند القائم، أو `null`/`undefined` لمستند جديد لم يُحفظ بعد. */
  docId: string | number | null | undefined;
  /** الحمولة الحالية — كائنٌ يكفي وحده لإعادة بناء الشاشة عبر `onRestore`. */
  payload: TPayload;
  /** علامة «لُمِس»: تُرفَع عند أوّل تعديل **مستخدم**، لا عند التعبئة البرمجية. */
  isTouched: boolean;
  /** يُستدعى مرّةً بحمولة المسودّة عند استعادة مؤهَّلة تلقائياً (`restore`). */
  onRestore: (payload: TPayload) => void;
  /** المستند مرحَّل؟ — يحكم أهليّة الاستعادة فقط؛ الحفظ لا يتأثر (§٤). */
  isPosted?: boolean;
  /** ختم تعديل المستند الحالي من الخادم — يُقارَن بختم لحظة بدء المسودّة (§٩). */
  docUpdatedAt?: string | null;
}

export interface DocumentDraftBanner<TPayload> {
  /** وقت آخر حفظ محلي للمسودّة المستعادة/المعروضة. */
  updatedAt: string;
  eligibility: DraftRestoreEligibility;
  /**
   * الحمولة المفسَّرة دائماً — حتى لـ`stale`/`posted` حيث لا استعادة تلقائية:
   * المستدعي يعرض زرّ «استعرض مسودتي» (issue #119 §٩) الذي يطبّقها يدوياً
   * (`onRestore(banner.payload)`) بعد قرار المستخدم لا الخطّاف.
   */
  payload: TPayload;
}

/** يتيمٌ لواجهة الاستعراض — مسودّة مستندٍ جديد أخرى غير هذه (issue #119 §٧). */
export interface OrphanDraftSummary {
  key: string;
  updatedAt: string;
  /** سطر محتواها الأوّل (`draftPreviewLine`) — لتمييز يتيمٍ عن آخر. */
  previewLine: string;
}

const NEW_DRAFT_SESSION_KEY = "ktra:draftSessionTabId";

/**
 * معرّف هذا التبويب **لمفتاح مسودّة مستندٍ جديد وحده** — يُولَّد مرّةً ويُحمَل
 * عبر إعادة التحميل (`sessionStorage`)، بخلاف `tabLink.tabId()` الذي يتجدّد مع
 * كل تحميل صفحة (مصمَّمٌ للحضور اللحظي بين التبويبات لا للاستمرار عبر التحديث).
 *
 * بلا هذا الفصل: مسودّة مستندٍ جديد تُكتب بمفتاحٍ يحمل `tabId()` عند الكتابة،
 * ثم إعادة تحميل الصفحة (§٦: «أخفِ التبويب ← أعِد التحميل») تولّد `tabId()`
 * جديداً فيُبنى مفتاح قراءةٍ مختلف — تضيع المسودّة رغم كتابتها فعلاً. هذا هو
 * بالضبط ما نصّت عليه المواصفة (issue #109 §٧): «معرّفٌ عشوائيٌّ عند فتح شاشةِ
 * مستندٍ جديد **ويُحمَل معها عبر إعادة التحميل**» — و`sessionStorage` هو الآلية
 * الوحيدة التي تتصرّف هكذا: تبقى عبر التحديث، وتختلف بين تبويبين حقيقيين.
 */
function newDocumentSessionTabId(): string {
  try {
    const existing = sessionStorage.getItem(NEW_DRAFT_SESSION_KEY);
    if (existing) return existing;
    const generated = tabId();
    sessionStorage.setItem(NEW_DRAFT_SESSION_KEY, generated);
    return generated;
  } catch {
    return tabId(); // تصفّح خاص أو تخزين محجوب — بلا استمرار عبر التحديث، وبلا سقوط
  }
}

export interface UseDocumentDraftResult<TPayload> {
  /** وقت آخر حفظ محلي ناجح في هذه الجلسة (ISO)، أو `null` إن لم يُحفظ شيء بعد. */
  draftSavedAt: string | null;
  /** فشلت آخر محاولة حفظ فعلاً (حصّة ممتلئة، تصفّح خاص…) — للافتة «احفظ يدوياً». */
  draftSaveFailed: boolean;
  /** مسودّة استُعيدت تلقائياً أو عُرضت للاطّلاع عند الفتح، أو `null`. */
  restoredBanner: DocumentDraftBanner<TPayload> | null;
  /** يخفي الشريط دون مسّ المسودّة نفسها. */
  dismissBanner: () => void;
  /** يمسح المسودّة المحلية فوراً — بعد حفظ ناجح، تجاهل صريح، أو «تراجع». */
  discardDraft: () => Promise<void>;
  /**
   * مسودّات مستندٍ جديد **يتيمة** لنفس الشركة والنوع (docId فارغ في الخطّاف)
   * — فارغة دائماً لمستندٍ قائم. issue #119 §٧.
   */
  orphanDrafts: OrphanDraftSummary[];
}

export function useDocumentDraft<TPayload>(
  options: UseDocumentDraftOptions<TPayload>,
): UseDocumentDraftResult<TPayload> {
  const toast = useToast();
  const {
    docType,
    docId,
    payload,
    isTouched,
    onRestore,
    isPosted = false,
    docUpdatedAt = null,
  } = options;

  const tenantId = resolveTenantId();
  // معرّفان مختلفان عمداً: `thisTabId` (الحضور اللحظي) للتوثيق فقط داخل الصفّ
  // (`tab_id`، أساسٌ لتنبيه §٨ لاحقاً)، و`draftTabId` (يبقى عبر إعادة التحميل)
  // هو ما يدخل مفتاح مستندٍ جديد فعلياً.
  const thisTabId = tabId();
  const draftTabId = newDocumentSessionTabId();
  const key = buildDocumentDraftKey({ tenantId, docType, docId, tabId: draftTabId });

  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const [draftSaveFailed, setDraftSaveFailed] = useState(false);
  const [restoredBanner, setRestoredBanner] = useState<DocumentDraftBanner<TPayload> | null>(null);
  const [orphanDrafts, setOrphanDrafts] = useState<OrphanDraftSummary[]>([]);

  // هويّات التبويبات التي أُنذر عنها بالفعل لهذه الهويّة (مفتاح) — «مرّةً
  // واحدة» (issue #119 §٨)، لا تُصفَّر إلا بتغيّر الهويّة نفسها.
  const warnedTabsRef = useRef<Set<string>>(new Set());

  // مراجع حيّة كي تقرأ الكتابة المؤجَّلة (مؤقّت/إخفاء/تفكيك) آخر قيمة بلا
  // إعادة تسجيل مستمعين مع كل حرف يُكتب.
  const isTouchedRef = useRef(isTouched);
  isTouchedRef.current = isTouched;
  const payloadRef = useRef(payload);
  payloadRef.current = payload;
  // ختم المستند **لحظة بدء هذه الجلسة** — يُكتب مع كل حفظ محلي كي تقارنه الجلسة
  // التالية بختم الخادم الحالي عند العودة (§٩)، لا بختم لحظة الكتابة نفسها.
  //
  // ويُلتقط **مرّةً واحدة** لكل هويّة (`key`) ولا يُحدَّث بعدها: لو تتبّع آخر
  // قيمةٍ للخاصيّة لصار الختمُ المخزَّن هو ختمَ الخادم الحاليَّ دوماً، فلا
  // يختلفان أبداً، **ولما أطلق فحصُ «تغيّر المستند بعد مسودّتك» ولا مرّة**.
  // (وأوّلُ قيمةٍ قد تصل `null` قبل أن يُحمَّل المستند، فيُلتقط أوّلُ ختمٍ
  // حقيقيّ لا أوّلُ تصيير.)
  const sessionDocUpdatedAtRef = useRef<string | null>(null);
  const sessionStampKeyRef = useRef<string | null>(null);
  if (sessionStampKeyRef.current !== key) {
    sessionStampKeyRef.current = key;
    sessionDocUpdatedAtRef.current = docUpdatedAt ?? null;
  } else if (sessionDocUpdatedAtRef.current == null && docUpdatedAt != null) {
    sessionDocUpdatedAtRef.current = docUpdatedAt;
  }

  // «مرّةً واحدة» (issue #119 §٨) مقيّدةٌ بهويّة المستند نفسها — هويّةٌ جديدة
  // (مستندٌ آخر) تستحقّ إنذارها الخاص لو تعارضت.
  const warnedKeyTrackerRef = useRef<string | null>(null);
  if (warnedKeyTrackerRef.current !== key) {
    warnedKeyTrackerRef.current = key;
    warnedTabsRef.current = new Set();
  }

  // فتح قناة الحضور مبكراً (لا عند أوّل كتابة) — الحضور يُبنى بتبادل
  // `hello`/`who` غير متزامن، فبلا هذا يصل فحصُ الحيويّة أوّل كتابةٍ مؤجَّلة
  // (٥٠٠ms) قبل أن يتعرّف على أيّ تبويبٍ آخر أصلاً.
  useEffect(() => subscribeTabPresence(), []);

  const writeNow = useCallback(async (): Promise<void> => {
    if (!shouldPersistDraft(isTouchedRef.current)) return;
    const row = {
      key,
      tenant_id: tenantId,
      doc_type: docType,
      doc_id: docId != null && docId !== "" ? String(docId) : null,
      tab_id: thisTabId,
      data: JSON.stringify(payloadRef.current),
      doc_updated_at: sessionDocUpdatedAtRef.current,
      updated_at: new Date().toISOString(),
    };
    // إنذارُ «مفتوحٌ في نافذةٍ أخرى» (issue #119 §٨) — قبل الكتابة الفعلية لا
    // بعدها: قرارٌ صريح ثم تمضي الكتابة كما هي، لا دمج ولا منع. فشل هذا الفحص
    // وحده (تصفّح خاص، قناةٌ محجوبة) لا يجوز أن يمنع الكتابة نفسها — معزولٌ في
    // try/catch خاصّ به.
    try {
      const existing = await db.document_drafts.get(key);
      const previousTabId = existing?.tab_id ?? null;
      if (
        previousTabId &&
        shouldWarnCrossTabWrite({
          previousTabId,
          thisTabId,
          isOtherTabLive: isTabIdLive(previousTabId),
          alreadyWarnedForKey: warnedTabsRef.current.has(previousTabId),
        })
      ) {
        warnedTabsRef.current.add(previousTabId);
        toast("هذا المستند مفتوحٌ في نافذةٍ أخرى.", "info");
      }
    } catch {
      /* أفضل جهد — لا يجوز أن يمنع فشلُ فحص التعارض الكتابةَ نفسها */
    }
    try {
      await db.transaction("rw", db.document_drafts, async () => {
        await db.document_drafts.put(row);
        // Dexie لا تكشف IDBTransaction.commit() افتراضياً (issue #109 §٣) —
        // نُنهي المعاملة فوراً بدل انتظار أحداثٍ معلّقة قد لا تُتاح لها فرصة
        // (إخفاء التبويب قد يسبقه إسقاط الصفحة بلا حدث إطلاقاً).
        const idbtrans = Dexie.currentTransaction?.idbtrans as
          | (IDBTransaction & { commit?: () => void })
          | undefined;
        if (idbtrans && typeof idbtrans.commit === "function") {
          idbtrans.commit();
        }
      });
      setDraftSavedAt(row.updated_at);
      setDraftSaveFailed(false);
    } catch {
      // امتلاء الحصّة أو تصفّح خاص — الصمت عن فشلٍ معلوم أسوأ من التحذير (§١٠).
      setDraftSaveFailed(true);
    }
  }, [key, tenantId, docType, docId, thisTabId, toast]);

  // ── القراءة والاستعادة عند فتح هذه الهويّة (مفتاح) ─────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const row = await db.document_drafts.get(key);
        if (cancelled || !row || !row.data) return;
        if (!isOfflineRecordForTenant(row, tenantId)) return;
        const eligibility = evaluateDraftRestore({
          isPosted,
          draftDocUpdatedAt: row.doc_updated_at,
          currentDocUpdatedAt: docUpdatedAt,
        });
        const parsed = JSON.parse(row.data) as TPayload;
        if (eligibility === "restore") {
          onRestore(parsed);
        }
        // الحمولة تُحمَل في الشريط حتى لـ`stale`/`posted` — «استعرض مسودتي»
        // (issue #119 §٩) يطبّقها يدوياً من طرف المستدعي، لا استعادةً صامتة.
        if (!cancelled) setRestoredBanner({ updatedAt: row.updated_at, eligibility, payload: parsed });
      } catch {
        /* مسودّة تالفة أو IndexedDB غير متاحة — تُتجاهَل بصمت، لا تُسقط الشاشة */
      }
    })();
    return () => {
      cancelled = true;
    };
    // مرّة واحدة لكل هويّة مستند (مفتاح) — لا عند كل تغيّر حمولة.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // ── اليتامى: مسودّات مستندٍ جديد أخرى لنفس الشركة والنوع (issue #119 §٧) ──
  // فقط على شاشة «مستندٍ جديد» — `docId` فارغ. مستندٌ قائم مفتاحه على معرّف
  // المستند نفسه فلا يتامى بهذا المعنى (راجع `selectOrphanDrafts`).
  useEffect(() => {
    if (docId != null && docId !== "") {
      setOrphanDrafts([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const rows = await db.document_drafts
          .where("[tenant_id+doc_type]")
          .equals([tenantId, docType])
          .toArray();
        const scoped = rows.filter((r) => isOfflineRecordForTenant(r, tenantId) && r.data);
        const orphans = selectOrphanDrafts(
          scoped.map((r) => ({ key: r.key, docId: r.doc_id, updatedAt: r.updated_at })),
          key,
        );
        if (cancelled) return;
        setOrphanDrafts(
          orphans.map((o) => {
            const row = scoped.find((r) => r.key === o.key);
            return {
              key: o.key,
              updatedAt: o.updatedAt,
              previewLine: row ? draftPreviewLine(row.data) : "",
            };
          }),
        );
      } catch {
        /* IndexedDB غير متاحة — لا يتامى يُعرَضون بدل إسقاط الشاشة */
      }
    })();
    return () => {
      cancelled = true;
    };
    // مرّة واحدة لكل هويّة مستند جديد — لا عند كل تغيّر حمولة.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, docType, docId, key]);

  // ── الكتابة بعد ٥٠٠ms من آخر تغيير ───────────────────────────────────────
  useEffect(() => {
    if (!isTouched) return;
    const t = window.setTimeout(() => {
      void writeNow();
    }, WRITE_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, isTouched, writeNow]);

  // ── الكتابة عند إخفاء التبويب — الحدّ الأخير المضمون (لا beforeunload) ──
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") void writeNow();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [writeNow]);

  // ── الكتابة عند مغادرة المسار داخل التطبيق (تفكيك المكوّن أو تبديل الهويّة) ──
  useEffect(() => {
    return () => {
      void writeNow();
    };
  }, [key, writeNow]);

  const dismissBanner = useCallback(() => setRestoredBanner(null), []);

  const discardDraft = useCallback(async () => {
    try {
      await db.document_drafts.delete(key);
    } catch {
      /* أفضل جهد — لا يُسقط تدفّق الحفظ/التراجع */
    }
    setRestoredBanner(null);
    setDraftSavedAt(null);
  }, [key]);

  return { draftSavedAt, draftSaveFailed, restoredBanner, dismissBanner, discardDraft, orphanDrafts };
}
