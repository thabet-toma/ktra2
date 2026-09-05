/**
 * ISSUE #113 (مواصفة #108 §١/§٤/§٧) — محرِّر «طلبية» (`PurchaseRFQ`): كيانٌ
 * حقيقيّ يسبق عرض السعر، بلا سعر إلزامي على بنوده. يحلّ محلّ ما كان يُصنع
 * سابقاً بلافتة `offerType="outgoing_order"` داخل `PriceOfferForm.tsx` — تلك
 * اللافتة كانت تُنشئ `PurchaseOrder`/`LogisticsDeal` مباشرةً بأسعار وهمية لأن
 * لا مكان كان لكميات بلا أسعار. هنا يُنشأ `PurchaseRFQ` وحده.
 *
 * الأعمدة تُقرأ من `utils/procurementColumns.ts` (`getScreenColumns('rfq')`) —
 * لا نسخة محلية من مصفوفة #108 §٤. و«أقل سعر» يظهر إشارةً بجانب السعر
 * التقديري وفي منتقي الأصناف نفسه (لا عموداً — هو مصدر تعبئة فقط في الطلبية)،
 * مبنيّاً بـ`utils/purchasePriceHint.ts` كي تحمل رقاقة «أقل شراء» علامة
 * العملة الأساسية صراحةً (الحكم الذي يمنع التباس ١٢$ مقابل ٤٣٫٢٠₪).
 *
 * البنود تُقفل عند أوّل إرسال لا عند الترسية (#112 §٧) — `isLockedForEditing`
 * يعكس ذلك: التحرير الحرّ على المسودة وحدها، وبعد الإرسال يبقى الإلغاء
 * والترسية وإضافة مستقبِل جديد فقط.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  KitAutocomplete,
  useKitKeymap,
  type KitGridColumn,
  type KitToolbarAction,
} from "../../kit";
import { Save, X, Loader2, AlertCircle, CheckCircle2, Trash2, Send, Ban, UserPlus, Printer, FileSpreadsheet, GitCompare, Copy, ShieldOff, Info, Undo2, FileText } from "lucide-react";
import {
  CommercialDocumentEditor,
  type CommercialHeaderField,
} from "../../shared/CommercialDocumentEditor";
import {
  addPurchaseRfqRecipient,
  cancelPurchaseRfq,
  createPurchaseRfq,
  duplicatePurchaseRfq,
  getPurchaseRfq,
  sendPurchaseRfq,
  updatePurchaseRfq,
  type ProcurementScope,
  type PurchaseRFQAwardResult,
  type PurchaseRFQDto,
  type PurchaseRFQLineDto,
  type PurchaseRFQRecipientDto,
} from "../../../services/procurementDocumentsApi";
import { purchaseInvoiceApi } from "../../../services/purchaseInvoiceApi";
import {
  buildPurchasePriceHintChips,
  formatLowestPurchaseHint,
  type PurchasePriceListEntry,
} from "../../../utils/purchasePriceHint";
import { getScreenColumns, type ProcurementColumnKey } from "../../../utils/procurementColumns";
import { formatDateValue, formatTimeValue } from "../../../utils/formatDate";
import { useDocumentDraft } from "../../../hooks/useDocumentDraft";
import { orphanDraftsBannerText } from "../../../utils/documentDraft";
import { useToast } from "../../../contexts/ToastContext";
import { useConfirm } from "../../../contexts/ConfirmContext";
import { revokeDocumentShare } from "../../../services/docShareApi";
import type { Item, Supplier } from "../../../types";
import { PurchaseRFQPrintView } from "./PurchaseRFQPrintView";
import { RfqComparisonMatrix } from "./RfqComparisonMatrix";

type RfqLineItem = {
  key: string;
  id?: number;
  itemId: string;
  name: string;
  specs: string;
  quantity: number;
  unitOfMeasure: string;
  estimatedPrice: number | null;
};

const newLineKey = () => `rfq-ln-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
const blankLine = (): RfqLineItem => ({
  key: newLineKey(), itemId: "", name: "", specs: "",
  quantity: 0, unitOfMeasure: "", estimatedPrice: null,
});

const lineFromDto = (line: PurchaseRFQLineDto): RfqLineItem => ({
  key: newLineKey(),
  id: line.id,
  itemId: line.product != null ? String(line.product) : "",
  name: line.name_snapshot || line.product_name || "",
  specs: line.specs || "",
  quantity: Number(line.quantity || 0),
  unitOfMeasure: line.unit_of_measure || "",
  estimatedPrice: line.estimated_price != null ? Number(line.estimated_price) : null,
});

/** عرض/محاذاة/نوع كل عمود — النصّ (header) وحده من المصفوفة المشتركة. */
const COLUMN_LAYOUT: Partial<Record<ProcurementColumnKey, Pick<KitGridColumn<RfqLineItem>, "width" | "align" | "type">>> = {
  seq: { width: "52px", align: "center" },
  product: { width: "28%" },
  specs: { width: "24%" },
  quantity: { width: "90px", align: "center", type: "number" },
  unitOfMeasure: { width: "110px", align: "center" },
  estimatedPrice: { width: "160px", align: "center", type: "number" },
};

const STATUS_LABELS: Record<PurchaseRFQDto["status"], string> = {
  draft: "مسودة", sent: "مُرسَلة", awarded: "مُرساة", cancelled: "ملغاة",
};

interface Props {
  /** null = طلبية جديدة. */
  rfq: PurchaseRFQDto | null;
  items: Item[];
  suppliers: Supplier[];
  scope: ProcurementScope;
  isReadOnly?: boolean;
  onSaved: (rfq: PurchaseRFQDto) => void;
  onCancel: () => void;
  /**
   * ISSUE #122: المورّد الذي سعّر على الهاتف — يُفتح له محرِّرُ العرض القائم
   * (عرضٌ جديد غير محفوظ معبّأ ببنود الطلبية بلا أسعار، أو عرضُه إن كان قد
   * ردّ). القرارُ بين الاثنين عند المُستدعي لأنّه من يملك شاشة العروض؛ هنا
   * الزرُّ وحده. بلا هذه الخاصّية لا يُعرض الزرّ إطلاقاً.
   */
  onOpenRecipientOffer?: (recipient: PurchaseRFQRecipientDto, rfq: PurchaseRFQDto) => void;
}

export const PurchaseRFQForm: React.FC<Props> = ({
  rfq, items, suppliers, scope, isReadOnly = false, onSaved, onCancel,
  onOpenRecipientOffer,
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [current, setCurrent] = useState<PurchaseRFQDto | null>(rfq);
  // ISSUE #115 قصّة ١٦: معرّف رابط المشاركة الجاري إبطاله — لتعطيل زرّه وحده
  // لا كل الشاشة، فإبطال رابط مورّدٍ لا يُجمّد قائمة المستقبِلين الأخرى.
  const [revokingShareId, setRevokingShareId] = useState<number | null>(null);
  const [rfqDate, setRfqDate] = useState(rfq?.rfq_date || new Date().toISOString().slice(0, 10));
  const [replyDeadline, setReplyDeadline] = useState(rfq?.reply_deadline || "");
  const [notes, setNotes] = useState(rfq?.notes || "");
  const [lines, setLines] = useState<RfqLineItem[]>(() =>
    rfq?.lines?.length ? rfq.lines.map(lineFromDto) : [blankLine()]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [selectedRecipients, setSelectedRecipients] = useState<Set<string>>(new Set());
  const [addRecipientId, setAddRecipientId] = useState("");
  const [showPrintView, setShowPrintView] = useState(false);
  const [exporting, setExporting] = useState(false);
  // ISSUE #116 (مواصفة #108 §٨): شاشةٌ مستقلّة تُفتح عند الطلب — لا تُفرَض
  // على المحرِّر اليومي. الترسية صارت تمرّ من داخلها (تختار مورداً أولاً).
  const [showComparison, setShowComparison] = useState(false);
  // ISSUE #121 (issue #118/#109 §٢): مسودّة محلية. البنود مقفلة بعد أوّل إرسال
  // (`isLocked` أدناه) — لا معنى لحفظ مسودّة لشاشةٍ لا تُعدَّل، فـ`isTouched`
  // مشروطة بأن تكون الطلبية لا تزال قابلةً للتحرير فعلاً (قرارٌ محلي — انظر
  // تقرير القضية #121).
  // ISSUE #121: **حالةٌ لا مرجع.** العلامةُ تُرفَع من داخل أثرٍ يجري **بعد**
  // الرسم، فمرجعٌ صامتٌ يُبقي `isTouched` كاذبةً في الرسمة نفسِها التي كان
  // يجب أن تُجدوِل الكتابة — ويُضيع من عدّل تعديلاً واحداً وغادر. الحالةُ
  // تُعيد الرسم فيرى الخطّافُ العلامةَ فوراً.
  const [isDirty, setIsDirty] = useState(false);
  const markDirty = useCallback((value: boolean) => setIsDirty(value), []);
  const skipNextDirtyRef = useRef(true);
  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);

  useEffect(() => { setCurrent(rfq); }, [rfq]);

  // ISSUE #113: «أقل سعر» — تُجلب لكامل الكتالوج دفعة واحدة (نفس نمط
  // task24/InvoiceForm) بلا حصرها بمورد: الطلبية تُرسَل لعدّة موردين معاً.
  const [lowestPriceMap, setLowestPriceMap] = useState<Map<number, PurchasePriceListEntry[]>>(new Map());
  useEffect(() => {
    let cancelled = false;
    purchaseInvoiceApi.priceList(null)
      .then((rows) => {
        if (cancelled) return;
        const m = new Map<number, PurchasePriceListEntry[]>();
        for (const r of rows) {
          if (r.prices?.length) m.set(r.product_id, r.prices as PurchasePriceListEntry[]);
        }
        setLowestPriceMap(m);
      })
      .catch(() => { /* بلا تاريخ شراء — الطلبية تُملأ يدوياً */ });
    return () => { cancelled = true; };
  }, []);

  // البنود تُقفل عند أوّل إرسال — لا عند الترسية (#112 §٧).
  const isLocked = isReadOnly || (current != null && current.status !== "draft");
  const isNew = current == null;

  /* ISSUE #121: الحمولة المحلية — كائنٌ خفيف يكفي وحده لإعادة بناء الشاشة. */
  const draftPayload = useMemo(
    () => ({ rfqDate, replyDeadline, notes, lines }),
    [rfqDate, replyDeadline, notes, lines],
  );
  type RfqDraftPayload = typeof draftPayload;

  const onRestoreDraft = useCallback((restored: RfqDraftPayload) => {
    setRfqDate(restored.rfqDate);
    setReplyDeadline(restored.replyDeadline);
    setNotes(restored.notes);
    setLines(restored.lines);
    // استعادةٌ من مسودّة تعني اختلافاً عن آخر نسخة محفوظة — تُسجَّل «ملموسة» فوراً.
    markDirty(true);
  }, []);

  const {
    draftSavedAt,
    draftSaveFailed,
    restoredBanner: draftBanner,
    discardDraft,
    orphanDrafts,
  } = useDocumentDraft<RfqDraftPayload>({
    // ISSUE #133 غ٥: مفتاحٌ لكل نطاق — بلا هذا كانت مسودّةٌ يتيمة لطلبية شراء
    // محلّي تظهر في شاشة طلبية استيراد (وعكسها)، فالبحث عن اليتامى يفلتر
    // بـ`[tenant_id+doc_type]` وحده ولم يكن النطاق جزءاً من `doc_type`.
    docType: `purchase_rfq_${scope}`,
    docId: current?.id ?? null,
    payload: draftPayload,
    // القرار (يُذكر في تقرير القضية #121): الحفظ المحلي يتوقّف بمجرّد أن تُقفَل
    // البنود (`isLocked`) — الملاحظات تبقى قابلةً للكتابة بعدها في الواجهة، لكن
    // لا مسار حفظٍ خادمي لها أصلاً بعد القفل (زرّ «تخزين» نفسه معطَّل حينها)،
    // فمسودّة محلية عندها لا تخدم غرضاً حقيقياً.
    isTouched: isDirty && !isLocked,
    onRestore: onRestoreDraft,
    isPosted: isLocked,
    docUpdatedAt: current?.updated_at ?? null,
  });

  useEffect(() => {
    if (skipNextDirtyRef.current) {
      skipNextDirtyRef.current = false;
      return;
    }
    markDirty(true);
  }, [draftPayload]);

  /* ISSUE #121 (نمط الحارس المقلوب — issue #120): يعترض المغادرة فقط إن فشل
     الحفظ المحلي فعلاً — لا دائماً. */
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (draftSaveFailed) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [draftSaveFailed]);

  /** «تراجع»: يعيد البنود/الملاحظات إلى حالة الطلبية المحمَّلة (فارغة لطلبية جديدة) ويمسح المسودّة. */
  const handleUndoDraft = useCallback(() => {
    setRfqDate(rfq?.rfq_date || new Date().toISOString().slice(0, 10));
    setReplyDeadline(rfq?.reply_deadline || "");
    setNotes(rfq?.notes || "");
    setLines(rfq?.lines?.length ? rfq.lines.map(lineFromDto) : [blankLine()]);
    skipNextDirtyRef.current = true;
    markDirty(false);
    void discardDraft();
  }, [rfq, discardDraft]);

  const draftSaveFailedBanner = draftSaveFailed && !isLocked ? (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="draft-save-failed-banner"
      className="sticky top-0 z-40 flex items-center gap-2 border-b border-red-200 bg-red-100 px-4 py-2 text-sm font-medium text-red-800"
    >
      <AlertCircle className="h-4 w-4 shrink-0" />
      <span>تعذّر حفظ نسخة محلية من هذه الطلبية — اضغط «تخزين» يدوياً كي لا يضيع عملك.</span>
    </div>
  ) : null;

  const draftRestoreBanner = draftBanner ? (
    <div className="ktra-banner ktra-banner--warn" role="status" data-testid="draft-restored-banner">
      <Info className="h-4 w-4 shrink-0" />
      <span>
        {draftBanner.eligibility === "restore" &&
          `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "stale" &&
          `تغيّرت الطلبية بعد مسودتك (عُدِّلت ${formatTimeValue(current?.updated_at || "")}، ومسودتُك ${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "posted" &&
          `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(draftBanner.updatedAt)}) لهذه الطلبية — بنودُها مقفَلة، للاطّلاع فقط.`}
      </span>
      {draftBanner.eligibility === "restore" && (
        <button type="button" className="ktra-toolbtn" onClick={handleUndoDraft} data-testid="draft-restored-undo">
          <Undo2 className="h-4 w-4" /> تراجع
        </button>
      )}
      {draftBanner.eligibility === "stale" && (
        <>
          <button type="button" className="ktra-toolbtn"
            onClick={() => onRestoreDraft(draftBanner.payload)} data-testid="draft-stale-preview">
            استعرض مسودتي
          </button>
          <button type="button" className="ktra-toolbtn"
            onClick={() => void discardDraft()} data-testid="draft-stale-discard">
            تجاهلها
          </button>
        </>
      )}
    </div>
  ) : null;

  const orphanDraftsBanner = orphanDrafts.length > 0 && !orphanBarDismissed ? (
    <div className="ktra-banner" role="status" data-testid="orphan-drafts-banner">
      <Info className="h-4 w-4 shrink-0" />
      <div className="flex flex-col gap-1">
        <span>{orphanDraftsBannerText(orphanDrafts.length)}</span>
        <ul className="list-disc pr-4 text-xs">
          {orphanDrafts.map((o) => (
            <li key={o.key}>{formatTimeValue(o.updatedAt)} — {o.previewLine || "—"}</li>
          ))}
        </ul>
      </div>
      <button type="button" className="ktra-toolbtn" onClick={() => setOrphanBarDismissed(true)} data-testid="orphan-drafts-dismiss">
        <X className="h-4 w-4" /> إخفاء
      </button>
    </div>
  ) : null;

  const addLine = () => setLines((prev) => [...prev, blankLine()]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const updateLine = (key: string, patch: Partial<RfqLineItem>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const fillLineWithItem = useCallback((lineKey: string, item: Item) => {
    const lowest = lowestPriceMap.get(Number(item.id))?.find(
      (p) => (p.source_label || p.label || "").startsWith("أقل شراء"),
    );
    setLines((prev) => prev.map((line) => (line.key === lineKey ? {
      ...line,
      itemId: item.id,
      name: item.name,
      // «أقل سعر» مصدر تعبئة السعر التقديري (مصفوفة #108 §٤) — يبقى قابلاً
      // للتعديل بحرّية بعدها، لا حقلاً محسوباً.
      estimatedPrice: lowest ? Number(lowest.unit_price) : line.estimatedPrice,
    } : line)));
  }, [lowestPriceMap]);

  const itemOptions = useMemo(
    () => items.map((it) => ({
      id: it.id,
      label: it.name,
      sub: it.modelNumber || it.categoryName || undefined,
      keywords: [it.barcode, it.modelNumber, it.supplierCodes].filter(Boolean).join(" ").toLowerCase(),
      // ISSUE #113 — نفس رقاقات منتقي فاتورة الشراء، بعلامة العملة الأساسية
      // الصريحة على «أقل شراء» (judgement call: لا رقم غامض بجانب آخر شراء).
      prices: buildPurchasePriceHintChips(lowestPriceMap.get(Number(it.id))).map(
        ({ label, value, link }) => ({ label, value, link: link ?? undefined }),
      ),
    })),
    [items, lowestPriceMap],
  );

  const handleSave = async (): Promise<PurchaseRFQDto | null> => {
    const usableLines = lines.filter((l) => (l.itemId || l.name.trim()) && Number(l.quantity) > 0);
    if (usableLines.length === 0) {
      setErr("أضف صنفاً واحداً على الأقل (باختياره أو بكتابة اسمه) وحدد كميته.");
      return null;
    }
    setErr(null); setMsg(null);
    setSaving(true);
    try {
      const body = {
        scope,
        rfq_date: rfqDate,
        reply_deadline: replyDeadline || null,
        notes,
        lines: usableLines.map((l, idx): PurchaseRFQLineDto => ({
          id: l.id,
          product: l.itemId ? Number(l.itemId) : null,
          seq: idx + 1,
          name_snapshot: l.name,
          specs: l.specs,
          quantity: String(l.quantity),
          unit_of_measure: l.unitOfMeasure,
          estimated_price: l.estimatedPrice != null ? String(l.estimatedPrice) : null,
        })),
      };
      const saved = isNew
        ? await createPurchaseRfq(body)
        : await updatePurchaseRfq(current!.id, body);
      setCurrent(saved);
      setMsg("تم الحفظ.");
      // ISSUE #121 (issue #118 §٥): حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      markDirty(false);
      void discardDraft();
      onSaved(saved);
      return saved;
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleSend = async () => {
    setErr(null); setMsg(null);
    setSaving(true);
    try {
      let target = current;
      if (!target || isNew) target = await handleSave();
      if (!target) return;
      const supplierIds = [...selectedRecipients].map(Number).filter((n) => Number.isFinite(n));
      const sent = await sendPurchaseRfq(target.id, supplierIds);
      setCurrent(sent);
      setSelectedRecipients(new Set());
      // البنود صارت مقفلة — أيّ مسودّةٍ محلية سابقة لم تعد تخدم غرضاً.
      markDirty(false);
      void discardDraft();
      toast(`تم إرسال الطلبية ${sent.rfq_number || ""}`.trim(), "success");
      onSaved(sent);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "تعذّر الإرسال";
      setErr(message);
      toast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleAddRecipient = async () => {
    if (!current || !addRecipientId) return;
    setSaving(true);
    try {
      await addPurchaseRfqRecipient(current.id, Number(addRecipientId));
      setAddRecipientId("");
      // إعادة قراءة الطلبية أرخص وأوثق من دمج الردّ الجزئي يدوياً.
      const refreshed = await updatePurchaseRfq(current.id, {});
      setCurrent(refreshed);
      onSaved(refreshed);
      toast("أُضيف المستقبِل.", "success");
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "تعذّرت إضافة المستقبِل", "error");
    } finally {
      setSaving(false);
    }
  };

  // ISSUE #115 قصّة ١٣: نسخ رابط المستقبِل الخاص — نفس نمط `ShareDocumentModal`.
  const handleCopyShareLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast("نُسخ الرابط", "success");
    } catch {
      toast("انسخ الرابط يدوياً", "info");
    }
  };

  // ISSUE #115 قصّة ١٦: إبطال رابطٍ أُرسل بالخطأ — نقطة `revoke` القائمة في
  // `docshare`، لا نقطة جديدة. إعادة قراءة الطلبية بعدها أوثق من تحديث محليّ.
  const handleRevokeShare = async (shareId: number) => {
    if (!current) return;
    const ok = await confirm({
      title: "إبطال الرابط",
      message: "سيتوقف رابط هذا المورّد عن العمل فوراً. لا يمكن التراجع.",
      confirmText: "إبطال",
      danger: true,
    });
    if (!ok) return;

    setRevokingShareId(shareId);
    try {
      await revokeDocumentShare(shareId);
      const refreshed = await getPurchaseRfq(current.id);
      setCurrent(refreshed);
      onSaved(refreshed);
      toast("أُبطل الرابط", "success");
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "تعذّر إبطال الرابط", "error");
    } finally {
      setRevokingShareId(null);
    }
  };

  /**
   * ISSUE #112 قصّة ٤٤ (#108 §٧): البنودُ تُقفل عند أوّل إرسال — ومن تغيّر
   * احتياجُه بعدها يأخذ **نسخةً جديدة** بدل أن يبنيها من الصفر. النسخةُ مسودّةٌ
   * بلا رقم ولا مستقبِلين، والأصلُ لا يُمَسّ.
   */
  const handleDuplicate = async () => {
    if (!current) return;
    const label = current.rfq_number || `مسودة #${current.id}`;
    const ok = await confirm({
      title: "نسخة جديدة",
      message: `إنشاء نسخة جديدة (مسودة) من الطلبية ${label}؟ البنود تُنسَخ كاملةً، ولا يُنسَخ الموردون ولا الروابط المُرسلة.`,
      confirmText: "نسخة جديدة",
    });
    if (!ok) return;
    setSaving(true);
    try {
      const copy = await duplicatePurchaseRfq(current.id);
      // المُستدعي يُبدّل الطلبية المفتوحة، ومفتاحُ التركيب هناك يُعيد بناء
      // المحرِّر على النسخة الجديدة.
      onSaved(copy);
      toast("فُتحت نسخة جديدة (مسودة)", "success");
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "تعذّر إنشاء نسخة جديدة", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleCancelRfq = async () => {
    if (!current) return;
    setSaving(true);
    try {
      const cancelled = await cancelPurchaseRfq(current.id);
      setCurrent(cancelled);
      markDirty(false);
      void discardDraft();
      onSaved(cancelled);
      toast("أُلغيت الطلبية.", "success");
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "تعذّر الإلغاء", "error");
    } finally {
      setSaving(false);
    }
  };

  /**
   * ISSUE #114 — ملفّ Excel للمورد: صفَّا عناوين (عبري/عربي)، وعمود سعر
   * فارغ. `buildRfqSupplierXlsxBuffer` تبني الحمولة بقائمة سماح وحدها —
   * لا يُمرَّر «السعر التقديري» مهما حمله `current`.
   */
  const handleExportXlsx = async () => {
    if (!current) return;
    setExporting(true);
    try {
      const { buildRfqSupplierXlsxBuffer } = await import("../../../utils/purchaseRfqXlsx");
      const buffer = await buildRfqSupplierXlsxBuffer(current);
      const blob = new Blob([buffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${current.rfq_number || "طلبية"}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      toast(e instanceof Error ? e.message : "تعذّر توليد ملف Excel", "error");
    } finally {
      setExporting(false);
    }
  };

  useKitKeymap({
    F12: () => { if (!saving && !isLocked) void handleSave(); },
    Escape: () => onCancel(),
    CtrlIns: () => { if (!isLocked) addLine(); },
  }, { enabled: true });

  const toolbarActions: KitToolbarAction[] = [
    { key: "save", label: saving ? "...تخزين" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: !isLocked && !saving ? () => void handleSave() : undefined,
      disabled: isLocked || saving },
    { key: "cancel", label: "رجوع", icon: <X />, onClick: onCancel, separatorBefore: true },
    ...(current ? [{
      key: "print", label: "طباعة", icon: <Printer />,
      onClick: () => setShowPrintView(true), separatorBefore: true,
    }] : []),
    ...(current ? [{
      key: "export-xlsx", label: exporting ? "...تصدير" : "تصدير Excel",
      icon: exporting ? <Loader2 className="animate-spin" /> : <FileSpreadsheet />,
      onClick: !exporting ? () => void handleExportXlsx() : undefined, disabled: exporting,
    }] : []),
    ...(current && current.status === "draft" ? [{
      key: "send", label: "إرسال للموردين", icon: <Send />,
      onClick: !saving ? () => void handleSend() : undefined, disabled: saving,
    }] : []),
    ...(isNew ? [{
      key: "send-new", label: "حفظ وإرسال…", icon: <Send />,
      onClick: !saving ? () => void handleSend() : undefined, disabled: saving,
    }] : []),
    ...(current && current.status === "sent" ? [{
      key: "award", label: "مقارنة الموردين وترسية", icon: <GitCompare />,
      onClick: () => setShowComparison(true),
    }] : []),
    ...(current && current.status === "awarded" ? [{
      key: "comparison", label: "مقارنة الموردين", icon: <GitCompare />,
      onClick: () => setShowComparison(true),
    }] : []),
    ...(current && current.status !== "draft" ? [{
      key: "duplicate", label: "نسخة جديدة", icon: <Copy />,
      onClick: !saving ? () => void handleDuplicate() : undefined, disabled: saving,
      separatorBefore: true,
    }] : []),
    ...(current && (current.status === "draft" || current.status === "sent") ? [{
      key: "cancel-rfq", label: "إلغاء الطلبية", icon: <Ban />, danger: true,
      onClick: !saving ? () => void handleCancelRfq() : undefined, disabled: saving,
    }] : []),
  ];

  const gridColumns: KitGridColumn<RfqLineItem>[] = [
    ...getScreenColumns("rfq").map((col) => ({
      key: col.key,
      header: col.header,
      ...COLUMN_LAYOUT[col.key],
    })),
    { key: "del", header: "", width: "36px", align: "center" as const },
  ];

  const gridGetCell = (row: RfqLineItem, key: string): string | number => {
    const idx = lines.findIndex((l) => l.key === row.key);
    if (key === "seq") return idx + 1;
    if (key === "specs") return row.specs;
    if (key === "quantity") return String(row.quantity);
    if (key === "unitOfMeasure") return row.unitOfMeasure;
    if (key === "estimatedPrice") return row.estimatedPrice != null ? String(row.estimatedPrice) : "";
    return "";
  };

  const gridOnChange = (rowIdx: number, key: string, val: string) => {
    const row = lines[rowIdx];
    if (!row) return;
    if (key === "specs") updateLine(row.key, { specs: val });
    else if (key === "quantity") updateLine(row.key, { quantity: Number(val) || 0 });
    else if (key === "unitOfMeasure") updateLine(row.key, { unitOfMeasure: val });
    else if (key === "estimatedPrice") {
      updateLine(row.key, { estimatedPrice: val.trim() === "" ? null : Number(val) || 0 });
    }
  };

  gridColumns[gridColumns.length - 1].render = (row: RfqLineItem) =>
    isLocked ? null : (
      <button type="button" className="ktra-iconbtn ktra-iconbtn--danger" onClick={() => removeLine(row.key)}>
        <Trash2 className="h-3 w-3" />
      </button>
    );

  const productColumn = gridColumns.find((c) => c.key === "product");
  if (productColumn) {
    productColumn.render = (row: RfqLineItem) => (
      <KitAutocomplete
        value={row.name || ""}
        options={itemOptions}
        disabled={isLocked}
        placeholder="اكتب اسم الصنف…"
        onPick={(id) => {
          const item = items.find((candidate) => String(candidate.id) === String(id));
          if (item) fillLineWithItem(row.key, item);
        }}
        onFreeText={(text) => updateLine(row.key, { itemId: "", name: text.trim() })}
        onTextChange={row.itemId ? undefined : (text) => updateLine(row.key, { itemId: "", name: text })}
        createLabel={(text) => `إبقاء «${text}» كبند نصّي في الطلبية`}
      />
    );
  }

  // «أقل سعر» إشارةً بجانب السعر التقديري — لا عموداً (مصفوفة #108 §٤).
  const estimatedPriceColumn = gridColumns.find((c) => c.key === "estimatedPrice");
  if (estimatedPriceColumn) {
    estimatedPriceColumn.render = (row: RfqLineItem) => {
      const hint = row.itemId ? formatLowestPurchaseHint(lowestPriceMap.get(Number(row.itemId))) : null;
      return (
        <div className="flex flex-col items-center gap-0.5">
          <input
            className="ktra-input ktra-input--sm text-center"
            type="number" min="0" step="0.01"
            disabled={isLocked}
            value={row.estimatedPrice ?? ""}
            placeholder="—"
            onChange={(e) => updateLine(row.key, {
              estimatedPrice: e.target.value.trim() === "" ? null : Number(e.target.value) || 0,
            })}
          />
          {hint && (
            <span className="text-[9px] ktra-text-soft truncate max-w-[150px]" title={hint}>
              {hint}
            </span>
          )}
        </div>
      );
    };
  }

  const saveBanner = (err || msg) ? (
    <div className={`ktra-banner ${err ? "ktra-banner--err" : "ktra-banner--ok"}`}>
      {err ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{err || msg}</span>
    </div>
  ) : null;

  const banner = (
    <>
      {draftSaveFailedBanner}
      {saveBanner}
      {draftRestoreBanner}
      {orphanDraftsBanner}
    </>
  );

  const headerFields: CommercialHeaderField[] = [
    {
      key: "number", label: "رقم الطلبية",
      control: <input className="ktra-input ktra-input--hl" readOnly
        value={current?.rfq_number || "يُخصَّص عند أوّل إرسال"} />,
    },
    {
      key: "date", label: "التاريخ",
      control: <input className="ktra-input" type="date" disabled={isLocked}
        value={rfqDate} onChange={(e) => setRfqDate(e.target.value)} />,
    },
    {
      key: "replyDeadline", label: "مهلة الردّ",
      control: <input className="ktra-input" type="date"
        disabled={isReadOnly && (current?.status === "cancelled" || current?.status === "awarded")}
        value={replyDeadline} onChange={(e) => setReplyDeadline(e.target.value)} />,
    },
    {
      key: "status", label: "الحالة",
      control: <input className="ktra-input" readOnly
        value={current ? STATUS_LABELS[current.status] : "مسودة (غير محفوظة)"} />,
    },
  ];

  // مسموحٌ دوماً — الملاحظات لا تُقفَل بالإرسال (#112 §٧).
  const notesTab = (
    <div className="space-y-2 px-1 py-2">
      <textarea className="ktra-input w-full" rows={6}
        disabled={isReadOnly && current?.status === "cancelled"}
        value={notes} onChange={(e) => setNotes(e.target.value)}
        placeholder="ملاحظات داخلية عن الطلبية…" />
    </div>
  );

  const supplierName = (id: number) => suppliers.find((s) => String(s.id) === String(id))?.tradeName || `#${id}`;

  const recipientsTab = (
    <div className="space-y-3 px-1 py-2">
      {current == null ? (
        <p className="ktra-hint">احفظ الطلبية أولاً قبل اختيار الموردين — أو استعمل «حفظ وإرسال».</p>
      ) : (
        <>
          {current.recipients.length > 0 && (
            <div className="space-y-1">
              <span className="ktra-field-label">
                المستقبِلون ({current.replies_count} من {current.recipients_count} ردّوا)
              </span>
              <ul className="space-y-1">
                {current.recipients.map((r) => (
                  <li key={r.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span>{r.supplier_name || supplierName(r.supplier)}</span>
                      <div className="flex items-center gap-2">
                        <span className="ktra-text-soft">
                          {r.replied_at ? "وصل ردّه" : r.sent_at ? "بانتظار الردّ" : "لم يُرسَل"}
                        </span>
                        {/* ISSUE #122: المورّد الذي يُسعّر على الهاتف يدخل من هنا —
                            لا نافذةَ إدخالٍ ثانية، بل محرِّرُ العرض نفسه معبّأً
                            ببنود الطلبية بلا أسعار. وعلى `sent` وحدها: المسودّة
                            بنودُها غير مقفلة، والمُرساةُ والملغاةُ انتهى أمرُهما.
                            وعرضٌ واحدٌ لكلّ مستقبِل — من ردّ يُفتح عرضُه لا يُنشأ ثانٍ. */}
                        {onOpenRecipientOffer && current.status === "sent" && (
                          <button type="button" className="ktra-toolbtn"
                            title={r.quotation != null
                              ? "فتح عرض هذا المورّد للتصحيح"
                              : "فتح محرِّر عرضٍ جديد معبّأً ببنود الطلبية"}
                            onClick={() => onOpenRecipientOffer(r, current)}>
                            <FileText className="h-3.5 w-3.5" />
                            {r.quotation != null ? "افتح عرضه" : "حوّل إلى عرض"}
                          </button>
                        )}
                      </div>
                    </div>
                    {/* ISSUE #115 قصّة ١٣/١٦: الرابط يظهر فقط لمن أُرسل له فعلاً وله رابطٌ حيّ. */}
                    {r.share_url && r.share_is_live ? (
                      <div className="mt-1.5 flex items-center gap-1.5">
                        <input readOnly dir="ltr" value={r.share_url}
                          onFocus={(e) => e.currentTarget.select()}
                          className="ktra-input flex-1 truncate font-mono text-[11px]" />
                        <button type="button" title="نسخ الرابط"
                          className="ktra-iconbtn"
                          onClick={() => void handleCopyShareLink(r.share_url!)}>
                          <Copy className="h-3.5 w-3.5" />
                        </button>
                        {r.share ? (
                          <button type="button" title="إبطال الرابط"
                            disabled={revokingShareId === r.share}
                            className="ktra-iconbtn ktra-iconbtn--danger"
                            onClick={() => void handleRevokeShare(r.share!)}>
                            <ShieldOff className="h-3.5 w-3.5" />
                          </button>
                        ) : null}
                      </div>
                    ) : r.share_url ? (
                      <div className="mt-1 text-[11px] text-red-700">
                        {r.share_revoked_at ? "أُبطل الرابط" : "انتهت صلاحية الرابط"}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {current.status === "draft" && (
            <div className="space-y-1">
              <span className="ktra-field-label">اختر الموردين ليتلقّوا الطلبية عند الإرسال</span>
              <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-[var(--color-border)] p-2">
                {suppliers.map((s) => (
                  <label key={s.id} className="flex items-center gap-2 text-xs">
                    <input type="checkbox"
                      checked={selectedRecipients.has(String(s.id))}
                      onChange={(e) => setSelectedRecipients((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(String(s.id)); else next.delete(String(s.id));
                        return next;
                      })} />
                    {s.tradeName}
                  </label>
                ))}
              </div>
            </div>
          )}
          {current.status !== "draft" && current.status !== "cancelled" && current.status !== "awarded" && (
            <div className="flex items-end gap-2">
              <label className="ktra-field flex-1">
                <span className="ktra-field-label">إضافة مستقبِل جديد</span>
                <select className="ktra-input" value={addRecipientId}
                  onChange={(e) => setAddRecipientId(e.target.value)}>
                  <option value="">اختر مورداً…</option>
                  {suppliers
                    .filter((s) => !current.recipients.some((r) => String(r.supplier) === String(s.id)))
                    .map((s) => <option key={s.id} value={s.id}>{s.tradeName}</option>)}
                </select>
              </label>
              <button type="button" className="ktra-btn" disabled={!addRecipientId || saving}
                onClick={() => void handleAddRecipient()}>
                <UserPlus className="h-4 w-4" /> إضافة
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );

  if (showPrintView && current) {
    return (
      <div className="fixed inset-0 z-[100] ktra-bg-field overflow-y-auto">
        <PurchaseRFQPrintView rfq={current} onClose={() => setShowPrintView(false)} />
      </div>
    );
  }

  if (showComparison && current) {
    return (
      <RfqComparisonMatrix
        rfqId={current.id}
        rfqNumber={current.rfq_number}
        canAward={current.status === "sent"}
        awardStopsAtAcceptedOffer={scope === "import"}
        onClose={() => setShowComparison(false)}
        onAwarded={(result: PurchaseRFQAwardResult) => {
          setCurrent(result);
          onSaved(result);
        }}
      />
    );
  }

  return (
    <CommercialDocumentEditor<RfqLineItem>
      title={scope === "import" ? "طلبية استيراد" : "طلبية شراء"}
      state={current ? STATUS_LABELS[current.status] : "مسودة جديدة"}
      actions={toolbarActions}
      headerFields={headerFields}
      lines={lines}
      lineColumns={gridColumns}
      getLineCell={gridGetCell}
      getLineKey={(line) => line.key}
      onLineChange={gridOnChange}
      onAddLine={isLocked ? undefined : addLine}
      readOnly={isLocked}
      banner={banner}
      tabs={[
        { key: "notes", label: "الملاحظات", content: notesTab },
        {
          key: "recipients",
          label: current && current.recipients.length
            ? `الموردون (${current.recipients.length})`
            : "الموردون",
          content: recipientsTab,
        },
      ]}
      status={
        <>
          <span className="ktra-status-item">عدد البنود <b>{lines.length}</b></span>
          {current?.created_at && (
            <span className="ktra-status-item">أُنشئت {formatDateValue(current.created_at)}</span>
          )}
          {isLocked && <span className="ktra-status-item">البنود مقفَلة — أُرسلت الطلبية</span>}
          {draftSavedAt && !isLocked && (
            <span className="ktra-status-item" data-testid="draft-saved-indicator">
              مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
            </span>
          )}
        </>
      }
    />
  );
};
