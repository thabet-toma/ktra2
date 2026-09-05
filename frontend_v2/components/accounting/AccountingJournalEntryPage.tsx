import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { accountingApi, type CashBoxLedgerLink } from "../../services/accountingApi";
import { pickDefaultCashAccount } from "../../utils/cashBox";
import {
  applyQuickEntryAmount,
  emptyQuickEntryAmounts,
  noQuickEntryTouch,
  suggestQuickEntrySides,
  type QuickEntryAmounts,
  type QuickEntryKind,
  type QuickEntryTouched,
} from "../../utils/journalQuickEntry";
import { formatMoney, formatNumber } from "../../utils/formatNumber";
import { formatTimeValue } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";
import { orphanDraftsBannerText } from "../../utils/documentDraft";
import type {
  AccountingAccount,
  AccountingPartner,
  CostCenterDto,
  CurrencyDto,
} from "../../types/accounting";
import {
  ArrowRight,
  Plus,
  Trash2,
  Save,
  CheckCircle,
  Loader2,
  ExternalLink,
  Handshake,
  AlertTriangle,
  AlertCircle,
  Info,
  Printer,
  RefreshCw,
  Undo2,
  X,
  Search,
} from "lucide-react";
import {
  KitDocumentShell,
  KitGrid,
  useRecordNavigation,
  useKitKeymap,
  useKitFieldShortcuts,
  type KitGridColumn,
} from "../kit";
import { AccountTreePicker } from "./AccountTreePicker";
import OfflineGuard from "../offline/OfflineGuard";
import { entityPathForReference } from "../../utils/entityLinks";
import {
  buildHeaderNarration,
  buildLineNarration,
  isGeneratedLineNarration,
  isGeneratedNarration,
  type NarrationLine,
} from "../../utils/journalNarration";

/* ─────────── types ─────────── */

type LineState = {
  id?: number;
  accountId: string;
  partnerId: string;
  costCenterId: string;
  debit: string;
  credit: string;
  description: string;
  /** كتب المستخدم بيان السطر بيده — فلا يدهسه التوليد التلقائي. */
  descriptionTouched?: boolean;
};

type DealRef = {
  dealId: string;
  dealNumber: string;
  displayName: string;
};

interface Props {
  journalId: number | null;
  onBack: () => void;
  dealRef?: DealRef | null;
  /** من أين فُتح القيد — لربط «فتح الشحنة» بدل صفقة خاطئة */
  relatedKind?: "deal" | "shipment" | null;
  onNavigateToDeal?: (dealId: string) => void;
  onNavigateToShipment?: (shipmentId: string) => void;
}

/* ─────────── helpers ─────────── */

const emptyLine = (): LineState => ({
  accountId: "",
  partnerId: "",
  costCenterId: "",
  debit: "",
  credit: "",
  description: "",
  descriptionTouched: false,
});

/** القيد المزدوج طرفان — تبدأ الشبكة بسطرين ويُضاف الثالث عند الحاجة. */
const MIN_LINES = 2;

const startingLines = (): LineState[] =>
  Array.from({ length: MIN_LINES }, emptyLine);

/* ─── الوضع البسيط: قيدٌ بطرفين ─────────────────────────────────────────────
 * القيد البسيط (طرف مدين واحد وطرف دائن واحد) هو الغالب الأعمّ في الاستعمال
 * اليومي، والمركّب (ثلاثة أطراف فأكثر) استثناء. فالافتراضي سطرٌ واحد: بيانٌ
 * واحد للقيد كلّه، حسابان، ومبلغٌ يُكتب **مرّة واحدة** يملأ الجهتين خلف
 * الستار — والشبكة الكاملة تبقى خلف زرّ «متقدم» بلا نقصان.
 * الحالة تبقى `lines` نفسها (لا نسخة ثانية) فيبقى الحساب والتحقّق والحمولة
 * على مصدرٍ واحد. */
const SIMPLE_DEBIT = 0;
const SIMPLE_CREDIT = 1;

const amountOf = (v: string): number => parseFloat(v) || 0;
const isActiveLine = (l: LineState): boolean =>
  !!l.accountId && (amountOf(l.debit) > 0 || amountOf(l.credit) > 0);

/** هل يسع هذا القيدُ الوضعَ البسيط؟ طرفٌ مدين وطرفٌ دائن لا أكثر. */
const isSimpleShape = (ls: LineState[]): boolean => {
  // سطرٌ محفوظ بلا مبلغ لا يُسقَط بصمت عند الطيّ إلى البسيط.
  if (ls.some((l) => l.id && !isActiveLine(l))) return false;
  const active = ls.filter(isActiveLine);
  if (active.length > 2) return false;
  return (
    active.filter((l) => amountOf(l.debit) > 0).length <= 1 &&
    active.filter((l) => amountOf(l.credit) > 0).length <= 1
  );
};

/** يرتّب السطور للوضع البسيط: [0] الطرف المدين و[1] الطرف الدائن. */
const normalizeToSimple = (ls: LineState[]): LineState[] => {
  const debit = ls.find((l) => amountOf(l.debit) > 0)
    || ls.find((l) => l.accountId && amountOf(l.credit) === 0)
    || emptyLine();
  const credit = ls.find((l) => amountOf(l.credit) > 0)
    || ls.find((l) => l !== debit && l.accountId)
    || emptyLine();
  return [debit, credit === debit ? emptyLine() : credit];
};

/* ─── T-JQE (issue #133): شريط القيد السريع بثلاث خانات ─────────────────────
 * مقبوضات/مدفوعات/عمليات ذمم تحلّ محلّ خانة «المبلغ» الواحدة. الحساب الفعلي
 * على `lines[SIMPLE_DEBIT/CREDIT]` هو مصدر الحقيقة دوماً — هذا استنتاجٌ عرضيّ
 * وحده: أيّ خانةٍ من الثلاث تُظهر الرقم عند تحميل قيدٍ محفوظ أو طيّه من
 * المتقدّم.
 *
 * `forceTouched` يفرّق بين مصدرين لا يتساويان:
 *  - قيدٌ **محمَّل من الخادم** (`hydrateFromJournal`): حساباه حقيقتان محفوظتان
 *    لا اقتراحان، فتُعامَلان «ملموستين» دائماً — بصرف النظر عن مطابقتهما
 *    للصندوق الافتراضي الحالي (قد يتغيّر الإعداد لاحقاً) — كي لا يدهسهما
 *    تغييرُ المبلغ.
 *  - قيدٌ **يُركَّب في المتصفح** ويُطوى من المتقدّم إلى البسيط
 *    (`switchEntryMode`): لم يُحفظ بعد، فحسابٌ يطابق الصندوق الافتراضي حرفياً
 *    غالباً وصل إلى هناك من هذا الاقتراح نفسه في جولةٍ سابقة — فرضُ «ملموس»
 *    هنا كان يُجمِّد الاقتراح بقية الجلسة (العطل المُبلَّغ عنه: طيّ إلى البسيط
 *    يُسكت التلقين تماماً). فتُحسب اللمسة هنا بالمقارنة: حسابٌ **مُدخَل فعلاً
 *    ويخالف** الافتراضي الحالي فقط يُعامَل ملموساً (اختيارٌ يدوي واضح)؛ حقلٌ
 *    فارغ أو يطابق الافتراضي يبقى مفتوحاً لاقتراحٍ لاحق. */
function inferQuickEntryDisplay(
  normalized: LineState[],
  defaultCashAccountId: number | null,
  opts: { forceTouched: boolean } = { forceTouched: true },
): { kind: QuickEntryKind; amounts: QuickEntryAmounts; touched: QuickEntryTouched } {
  const debitAcc = normalized[SIMPLE_DEBIT]?.accountId ? Number(normalized[SIMPLE_DEBIT].accountId) : null;
  const creditAcc = normalized[SIMPLE_CREDIT]?.accountId ? Number(normalized[SIMPLE_CREDIT].accountId) : null;
  const amt = normalized[SIMPLE_DEBIT]?.debit || normalized[SIMPLE_CREDIT]?.credit || "";
  let kind: QuickEntryKind = "receivable";
  if (defaultCashAccountId != null && debitAcc === defaultCashAccountId) kind = "receipts";
  else if (defaultCashAccountId != null && creditAcc === defaultCashAccountId) kind = "payments";
  const touched: QuickEntryTouched = opts.forceTouched
    ? { debit: true, credit: true }
    : {
        debit: debitAcc != null && debitAcc !== defaultCashAccountId,
        credit: creditAcc != null && creditAcc !== defaultCashAccountId,
      };
  return {
    kind,
    amounts: { ...emptyQuickEntryAmounts(), [kind]: amt },
    touched,
  };
}

/** الذمم تحتاج جهة: رقمٌ عليها بلا طرفٍ رصيدٌ لا صاحب له في كشف الحساب. */
const PARTNER_SUB_TYPES = new Set(["receivable", "payable"]);

const REF_TYPE_LABELS: Record<string, string> = {
  LOGISTICS_PAYMENT: "دفعة صفقة",
  PURCHASE_RECEIPT: "استلام مخزون",
  JOURNAL_REVERSAL: "عكس قيد",
  LOGISTICS_EXPENSE: "مصروف لوجستي",
  MANUAL: "قيد يدوي",
  // A3: قيد يدوي وسمه المحاسب «تسوية» — لا شاشة مستقلة له عمداً: نفس الشاشة
  // ونفس قواعد التوازن، ووسمٌ يجعله قابلاً للتصفية في دفتر اليومية.
  ADJUSTMENT: "قيد تسوية",
};

function refTypeLabel(t: string, description?: string, sourceLabel?: string) {
  if (
    t === "LOGISTICS_PAYMENT" &&
    description &&
    /\bشحنة\b/i.test(description)
  ) {
    return "دفعة لوجستيات";
  }
  // الخادم يسمّي كل مصادر القيود (source_label) — لا نكرّر الخريطة هنا.
  return REF_TYPE_LABELS[t] || sourceLabel || t;
}

function fmtAmount(v: string | number) {
  return formatMoney(v, "");
}

/* ─────────── component ─────────── */

export const AccountingJournalEntryPage: React.FC<Props> = ({
  journalId,
  onBack,
  dealRef,
  relatedKind = null,
  onNavigateToDeal,
  onNavigateToShipment,
}) => {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  const [costCenters, setCostCenters] = useState<CostCenterDto[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const toast = useToast();
  const [posted, setPosted] = useState(false);

  const [header, setHeader] = useState({
    transaction_date: new Date().toISOString().split("T")[0],
    description: "",
    reference_type: "",
    reference_id: "",
    reference_summary: "",
    deal_ref_number: "",
    currency: "" as string,
    exchange_rate: "1",
    currency_code: "" as string,
    source_label: "" as string,
  });

  const [lines, setLines] = useState<LineState[]>(startingLines);
  /** كتب المستخدم البيان الإجمالي بيده — فيتوقّف التوليد التلقائي. */
  const [headerDescTouched, setHeaderDescTouched] = useState(false);
  /** «بسيط» طرفان بمبلغٍ واحد · «متقدم» الشبكة الكاملة. */
  const [entryMode, setEntryMode] = useState<"simple" | "advanced">("simple");

  /* T-JQE (issue #133): شريط القيد السريع بثلاث خانات — مقبوضات · مدفوعات ·
     عمليات ذمم — تحلّ محلّ خانة «المبلغ» الواحدة في الوضع البسيط. */
  const [cashBoxes, setCashBoxes] = useState<CashBoxLedgerLink[]>([]);
  const [quickKind, setQuickKind] = useState<QuickEntryKind>("receipts");
  const [quickAmounts, setQuickAmounts] = useState<QuickEntryAmounts>(emptyQuickEntryAmounts());
  /** حسابٌ عدّله المستخدم بيده على أحد طرفَي الوضع البسيط — **حالة** لا مرجعاً
      يُقرأ داخل effect، كي لا يضيع تعديلُ مستخدمٍ عدّل ثم غادر. */
  const [quickTouched, setQuickTouched] = useState<QuickEntryTouched>(noQuickEntryTouch());
  /** الصندوق الافتراضي مصدره إعدادات الشركة (`CashBoxLedgerAccount.is_default`
      عبر `pickDefaultCashAccount`) — لا تخمينٌ من بادئة كود الشجرة (`^110` كانت
      تبتلع 1103/1104 تاريخياً). */
  const defaultCashAccountId = useMemo(
    () => pickDefaultCashAccount({ boxes: cashBoxes }).accountId,
    [cashBoxes],
  );

  /* ISSUE #121: مسودّة محلية (IndexedDB) — هذه الشاشة لا تحفظ شيئاً محلياً
     اليوم. علامة «لُمِس» حالةٌ صريحة تُرفَع **مزامنةً** داخل كل معالج تعديلٍ
     حقيقي (لا داخل useEffect مبنيٍّ على الحمولة — ذاك يفوّت بالضبط حالة
     «عدّل ثم غادر» التي من أجلها هذه الميزة، لأنه يُنفَّذ بعد الرسم). لا تُرفع
     عند التعبئة البرمجية من الخادم (`hydrateFromJournal`, `handleUndoDraft`). */
  const [touched, setTouched] = useState(false);
  /** شريط اليتامى (issue #119 §٧) — إخفاءٌ محليّ بلا مسّ المسودّات نفسها. */
  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);

  // N3-T1: Kit Navigation + account picker state
  const [journalsList, setJournalsList] = useState<any[]>([]);
  const [showAccountPicker, setShowAccountPicker] = useState(false);
  // which line index is waiting for account pick
  const [pickerTargetLine, setPickerTargetLine] = useState<number | null>(null);
  // tooltip: { lineIdx, balance }
  const [balanceTooltip, setBalanceTooltip] = useState<{ lineIdx: number; balance: string } | null>(null);
  const tooltipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** سطر القيد بصيغة مولّد البيان (أسماء بدل معرّفات). */
  const toNarrationLine = useCallback(
    (l: LineState, accs: AccountingAccount[], parts: AccountingPartner[]): NarrationLine => ({
      accountName: accs.find((a) => String(a.id) === l.accountId)?.name || "",
      partnerName: parts.find((p) => String(p.id) === l.partnerId)?.name || "",
      debit: l.debit,
      credit: l.credit,
    }),
    [],
  );

  /** ملء النموذج من قيد محمَّل — مشترك بين التحميل الأول والتنقّل بين السجلات. */
  const hydrateFromJournal = useCallback(
    (
      j: any,
      accs: AccountingAccount[],
      parts: AccountingPartner[],
      defCashAccountId: number | null = null,
    ) => {
      setPosted(!!j.is_posted);
      // تعبئةٌ من الخادم — لا تُعامَل كتعديل مستخدم (issue #121).
      setTouched(false);
      const desc = j.description || "";
      setHeader((h) => ({
        ...h,
        transaction_date: j.transaction_date || "",
        description: desc,
        reference_type: j.reference_type || "",
        reference_id: j.reference_id != null ? String(j.reference_id) : "",
        reference_summary: j.reference_summary || "",
        deal_ref_number: j.deal_ref_number || "",
        currency: j.currency != null ? String(j.currency) : h.currency,
        exchange_rate: j.exchange_rate != null ? String(j.exchange_rate) : "1",
        currency_code: j.currency_code || "",
        source_label: j.source_label || "",
      }));
      const mapped: LineState[] = (j.lines || []).map((line: any) => ({
        id: line.id,
        accountId: line.account != null ? String(line.account) : "",
        partnerId: line.partner != null ? String(line.partner) : "",
        costCenterId: line.cost_center != null ? String(line.cost_center) : "",
        debit: parseFloat(String(line.debit)) > 0 ? String(line.debit) : "",
        credit: parseFloat(String(line.credit)) > 0 ? String(line.credit) : "",
        description: line.description || "",
        descriptionTouched: false,
      }));
      // بيان محفوظ يوافق ما يولّده النظام يبقى تلقائياً (يتبع تغيير الحسابات)،
      // وما كتبه المستخدم بيده يُصان كما هو.
      const narration = mapped.map((l) => toNarrationLine(l, accs, parts));
      mapped.forEach((l, i) => {
        l.descriptionTouched = !isGeneratedLineNarration(l.description, narration[i], desc);
      });
      setHeaderDescTouched(!isGeneratedNarration(desc, narration));
      while (mapped.length < MIN_LINES) mapped.push(emptyLine());
      // قيدٌ بطرفين يُفتح بسيطاً، والمركّب يفتح على الشبكة الكاملة.
      const simple = isSimpleShape(mapped);
      setEntryMode(simple ? "simple" : "advanced");
      const normalized = simple ? normalizeToSimple(mapped) : mapped;
      setLines(normalized);
      if (simple) {
        // قيدٌ محمَّلٌ من الخادم — حساباه حقيقتان محفوظتان لا اقتراحان، فتُفرَض
        // «ملموس» (الافتراضي `forceTouched: true`) بصرف النظر عن مطابقتهما
        // للصندوق الافتراضي الحالي؛ خلافاً لطيّ المتقدّم إلى البسيط أثناء
        // التركيب (انظر `switchEntryMode`).
        const disp = inferQuickEntryDisplay(normalized, defCashAccountId);
        setQuickKind(disp.kind);
        setQuickAmounts(disp.amounts);
        setQuickTouched(disp.touched);
      } else {
        setQuickKind("receipts");
        setQuickAmounts(emptyQuickEntryAmounts());
        setQuickTouched(noQuickEntryTouch());
      }
    },
    [toNarrationLine],
  );

  /* ISSUE #121: قراءةُ المسودّة من IndexedDB غيرُ متزامنة، وإعادةُ تهيئة
     «قيدٍ جديد» أدناه غيرُ متزامنةٍ أيضاً (تنتظر وصولَ قائمة القيود) — فأيُّهما
     وصل ثانياً كتب فوق الآخر. بلا هذا الحارس تُستعاد المسودّة فعلاً ثمّ تُمحى
     من الشاشة بعد أجزاء من الثانية، فيرى المستخدمُ شريطَ «استُعيدت» فوق نموذجٍ
     فارغ — أسوأ من ألّا تُستعاد. حارسٌ لمرّةٍ واحدة: أوّلُ تهيئةٍ بعد استعادةٍ
     تُتخطّى، وما بعدها (ضغطُ «جديد» صراحةً) يُصفّر كالمعتاد. */
  const draftRestoredRef = useRef(false);

  const nav = useRecordNavigation<any>({
    items: journalsList,
    getId: (j) => j.id || 0,
    currentId: journalId,
    onSelect: async (id) => {
      if (id === null) {
        if (draftRestoredRef.current) {
          draftRestoredRef.current = false;
          return;
        }
        // New journal - reset form
        setHeader({
          transaction_date: new Date().toISOString().split("T")[0],
          description: "",
          reference_type: "MANUAL",
          reference_id: "",
          reference_summary: "",
          deal_ref_number: "",
          currency: "",
          exchange_rate: "1",
          currency_code: "",
          source_label: "",
        });
        setLines(startingLines());
        setHeaderDescTouched(false);
        setEntryMode("simple");
        setPosted(false);
        setTouched(false);
        setQuickKind("receipts");
        setQuickAmounts(emptyQuickEntryAmounts());
        setQuickTouched(noQuickEntryTouch());
      } else {
        try {
          const j = await accountingApi.getJournal(Number(id));
          hydrateFromJournal(j, accounts, partners, defaultCashAccountId);
        } catch (err) {
          // console suppressed
        }
      }
    },
  });

  /* ── ISSUE #121: مسودّة محلية (IndexedDB) — القيد اليدوي لا يحفظ شيئاً
     محلياً اليوم. الحمولة كائنٌ خفيف يكفي وحده لإعادة بناء الشاشة؛ لا صلة
     بحمولة الحفظ الخادمية (`buildPayload`). */
  const draftPayload = useMemo(
    () => ({ header, lines, entryMode, headerDescTouched, quickKind, quickAmounts, quickTouched }),
    [header, lines, entryMode, headerDescTouched, quickKind, quickAmounts, quickTouched],
  );

  const onRestoreDraft = useCallback(
    (restored: {
      header: typeof header;
      lines: LineState[];
      entryMode: "simple" | "advanced";
      headerDescTouched: boolean;
      quickKind?: QuickEntryKind;
      quickAmounts?: QuickEntryAmounts;
      quickTouched?: QuickEntryTouched;
    }) => {
      setHeader(restored.header);
      setLines(restored.lines);
      setEntryMode(restored.entryMode);
      setHeaderDescTouched(restored.headerDescTouched);
      setQuickKind(restored.quickKind ?? "receipts");
      setQuickAmounts(restored.quickAmounts ?? emptyQuickEntryAmounts());
      setQuickTouched(restored.quickTouched ?? noQuickEntryTouch());
      draftRestoredRef.current = true;
      // استعادةٌ من مسودّة تعني اختلافاً عن آخر نسخة محفوظة — تُسجَّل «ملموسة».
      setTouched(true);
    },
    [],
  );

  const {
    draftSavedAt,
    draftSaveFailed,
    restoredBanner: draftBanner,
    discardDraft,
    orphanDrafts,
  } = useDocumentDraft<{
    header: typeof header;
    lines: LineState[];
    entryMode: "simple" | "advanced";
    headerDescTouched: boolean;
    quickKind: QuickEntryKind;
    quickAmounts: QuickEntryAmounts;
    quickTouched: QuickEntryTouched;
  }>({
    docType: "journal_entry",
    docId: journalId,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    isPosted: posted,
    // GAP معروف: `JournalHeader` (accounting/models.py) لا يحمل حقل
    // updated_at/timestamps إطلاقاً — ولا حتى على مستوى القاعدة — و
    // `JournalHeaderSerializer` لا يعرض واحداً. فلا مصدر حقيقي لـ`docUpdatedAt`
    // في هذه الشاشة، و`null` دائماً هنا يُعطّل بصمت فحص «تغيّر المستند بعد
    // مسودّتك» (issue #109 §٩) لشاشة القيد اليدوي وحدها. إصلاحه خادميّ
    // (إضافة updated_at للنموذج + migration + الserializer) وخارج نطاق هذه المهمة.
    docUpdatedAt: null,
  });

  /* ISSUE #120: الحارسُ مقلوب — يعترض المغادرةَ فقط إن فشل الحفظُ المحلّيّ فعلاً. */
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

  /** «تراجع» على شريط الاستعادة: يعيد القيد إلى نسخته المحفوظة ويمسح المسودّة. */
  const handleUndoDraft = useCallback(async () => {
    if (journalId != null) {
      try {
        const j = await accountingApi.getJournal(journalId);
        hydrateFromJournal(j, accounts, partners, defaultCashAccountId);
      } catch {
        /* أفضل جهد — تعذّر إعادة الجلب لا يجوز أن يمنع مسح المسودّة */
      }
    } else {
      setHeader({
        transaction_date: new Date().toISOString().split("T")[0],
        description: "",
        reference_type: "MANUAL",
        reference_id: "",
        reference_summary: "",
        deal_ref_number: "",
        currency: "",
        exchange_rate: "1",
        currency_code: "",
        source_label: "",
      });
      setLines(startingLines());
      setHeaderDescTouched(false);
      setEntryMode("simple");
      setPosted(false);
      setQuickKind("receipts");
      setQuickAmounts(emptyQuickEntryAmounts());
      setQuickTouched(noQuickEntryTouch());
    }
    setTouched(false);
    void discardDraft();
  }, [journalId, accounts, partners, hydrateFromJournal, discardDraft, defaultCashAccountId]);

  // N3-T1: Kit keyboard shortcuts.
  useKitKeymap({
    F2: () => window.print(),
    F5: () => load(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-ktra-field="search"]');
      el?.focus();
    },
    F12: () => saveAndPost(),
    Escape: () => {
      if (balanceTooltip) { setBalanceTooltip(null); return; }
      if (showAccountPicker) { setShowAccountPicker(false); setPickerTargetLine(null); return; }
      onBack();
    },
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => nav.goNew(),
  }, { enabled: !showAccountPicker });

  // N3-T1: Field shortcuts — Space=auto-balance, *=balance-lookup, +=account-picker
  useKitFieldShortcuts({
    'remaining-fill': () => {
      // autofill the remaining diff on the focused debit/credit cell
      const ae = document.activeElement as HTMLInputElement | null;
      if (!ae) return;
      const lineIdx = Number(ae.getAttribute('data-line-idx'));
      if (isNaN(lineIdx)) return;
      const side = ae.getAttribute('data-side') as 'debit' | 'credit' | null;
      if (!side) return;
      const remaining = Math.abs(diff);
      if (remaining < 0.005) return;
      if (side === 'debit' && diff < 0) {
        updateLine(lineIdx, { debit: formatNumber(remaining, { maxDecimals: 2 }) });
      } else if (side === 'credit' && diff > 0) {
        updateLine(lineIdx, { credit: formatNumber(remaining, { maxDecimals: 2 }) });
      }
    },
  }, { enabled: !showAccountPicker });

  // P0-5: قائمة التنقّل (الأول/السابق/التالي) كانت تجلب **كل** القيود —
  // صارت أحدث 200 قيد (القائمة مُرقَّمة إلزامياً خادمياً). فتح قيد أقدم
  // مباشرةً بالرابط يبقى شغّالاً؛ التنقّل التسلسلي يغطي الأحدث.
  useEffect(() => {
    const loadJournals = async () => {
      try {
        const paged = await accountingApi.getJournalsPaged({
          page: "1", page_size: "200",
        });
        setJournalsList(paged.results);
      } catch (err) {
        // console suppressed
      }
    };
    loadJournals();
  }, []);

  /* ── load data ── */
  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [acc, part, cc, cur, boxes] = await Promise.all([
        accountingApi.getAccounts(),
        accountingApi.getPartners().catch(() => []),
        accountingApi.getCostCenters().catch(() => []),
        accountingApi.getCurrencies().catch(() => []),
        accountingApi.getCashBoxLedgers().catch(() => []),
      ]);
      const activeAccounts = (acc as AccountingAccount[]).filter((a) => a.is_active);
      setAccounts(activeAccounts);
      setPartners(part as AccountingPartner[]);
      setCostCenters(cc as CostCenterDto[]);
      setCurrencies(cur as CurrencyDto[]);
      setCashBoxes(boxes as CashBoxLedgerLink[]);
      // الصندوق الافتراضي هنا محسوبٌ محلياً من الصناديق المجلوبة للتوّ — حالة
      // `cashBoxes` لا تنعكس إلا بعد إعادة رسم لاحقة، فقراءتها هنا تُطالع نسخةً
      // قديمة (سباق نفس المشكلة التي عولجت لعملة الأساس أدناه).
      const defCashAccountId = pickDefaultCashAccount({ boxes: boxes as CashBoxLedgerLink[] }).accountId;

      const baseCurrency = (cur as CurrencyDto[]).find((c) => c.IsBaseCurrency);

      if (journalId != null) {
        const j = await accountingApi.getJournal(journalId);
        if (j.currency == null && baseCurrency) j.currency = baseCurrency.CurrencyID;
        hydrateFromJournal(j, activeAccounts, part as AccountingPartner[], defCashAccountId);
      } else if (draftRestoredRef.current) {
        // الحارسُ **لا يُستهلَك هنا**: موضعا التصفير التلقائيّ اثنان (هذا،
        // وإعادةُ تهيئة «قيدٍ جديد» في `nav.onSelect`) وأيّهما استهلكه ترك
        // الآخر يكتب فوق المسودّة. الاستهلاكُ في اليد الواحدة التي يُصفّرها
        // المستخدم صراحةً.
        // ISSUE #121: هذا التحميلُ غيرُ متزامن (حسابات وعملات ومراكز كلفة)،
        // فيصل **بعد** استعادة المسودّة ويكتب فوقها — فيرى المستخدم شريط
        // «استُعيدت» فوق نموذجٍ فارغ. يُتخطّى تصفيرُ النموذج مرّةً واحدة، وتبقى
        // العملةُ الأساسية تُملأ إن كانت المسودّة لم تحمل واحدة.
        setPosted(false);
        if (baseCurrency) {
          setHeader((h) => (h.currency ? h : {
            ...h,
            currency: String(baseCurrency.CurrencyID),
            exchange_rate: "1",
            currency_code: baseCurrency.Code,
          }));
        }
      } else {
        setPosted(false);
        setTouched(false);
        setLines(startingLines());
        setEntryMode("simple");
        setQuickKind("receipts");
        setQuickAmounts(emptyQuickEntryAmounts());
        setQuickTouched(noQuickEntryTouch());
        setHeader((h) => ({ ...h, reference_type: h.reference_type || "MANUAL" }));
        if (baseCurrency) {
          setHeader((h) => ({
            ...h,
            currency: String(baseCurrency.CurrencyID),
            exchange_rate: "1",
            currency_code: baseCurrency.Code,
          }));
        }
        if (dealRef?.displayName) {
          setHeader((h) => ({
            ...h,
            description: h.description || `صفقة: ${dealRef.displayName}`,
          }));
          setHeaderDescTouched(true);
        } else {
          setHeaderDescTouched(false);
        }
      }
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحميل"));
    } finally {
      setLoading(false);
    }
  }, [journalId, dealRef?.displayName, hydrateFromJournal]);

  useEffect(() => { void load(); }, [load]);

  /* ── توليد البيان تلقائياً من الحسابات (يتوقف عند أي كتابة يدوية) ── */
  useEffect(() => {
    if (posted || loading) return;
    const narration = lines.map((l) => toNarrationLine(l, accounts, partners));
    const nextHeaderDesc = headerDescTouched
      ? header.description
      : buildHeaderNarration(narration);
    if (!headerDescTouched && nextHeaderDesc !== header.description) {
      setHeader((h) => ({ ...h, description: nextHeaderDesc }));
    }
    // بيان السطر يتبع حسابه حين يكون البيان الإجمالي مولَّداً (صيغة «من ح/ … إلى ح/ …»
    // لا تصلح بياناً لسطر مفرد)، ويتبع ما كتبه المستخدم حين يكتبه بيده.
    const lineBase = headerDescTouched ? nextHeaderDesc : "";
    setLines((prev) => {
      let changed = false;
      const next = prev.map((l, i) => {
        if (l.descriptionTouched || !narration[i]) return l;
        const want = buildLineNarration(narration[i], lineBase);
        if (want === l.description) return l;
        changed = true;
        return { ...l, description: want };
      });
      return changed ? next : prev;
    });
  }, [lines, accounts, partners, header.description, headerDescTouched, posted, loading, toNarrationLine]);

  /* ── N3-T1: account balance lookup helper (يَستخدم getGeneralLedger مع YTD) ── */
  const showAccountBalance = useCallback(async (lineIdx: number, accountId: string) => {
    if (!accountId) return;
    if (tooltipTimerRef.current) clearTimeout(tooltipTimerRef.current);
    setBalanceTooltip({ lineIdx, balance: '...' });
    try {
      const today = new Date();
      const ledger = await accountingApi.getGeneralLedger({
        account_id: accountId,
        start_date: `${today.getFullYear()}-01-01`,
        end_date: today.toISOString().split('T')[0],
      });
      const closing = Number((ledger as { closing_balance?: number | string })?.closing_balance ?? 0);
      const fmt = (v: number) => formatMoney(v);
      const label = `الرصيد: ${fmt(Math.abs(closing))} ${closing >= 0 ? 'مدين' : 'دائن'}`;
      setBalanceTooltip({ lineIdx, balance: label });
      tooltipTimerRef.current = setTimeout(() => setBalanceTooltip(null), 4000);
    } catch {
      setBalanceTooltip({ lineIdx, balance: 'تعذّر جلب الرصيد' });
      tooltipTimerRef.current = setTimeout(() => setBalanceTooltip(null), 3000);
    }
  }, []);

  /* ── line helpers ── */
  const updateLine = (i: number, patch: Partial<LineState>) => {
    if (posted) return;
    setTouched(true);
    setLines((prev) => {
      const next = [...prev];
      const row = { ...next[i], ...patch };
      if (patch.debit && parseFloat(patch.debit) > 0) row.credit = "";
      if (patch.credit && parseFloat(patch.credit) > 0) row.debit = "";
      next[i] = row;
      if (i === next.length - 1 && (row.accountId || row.debit || row.credit)) {
        next.push(emptyLine());
      }
      return next;
    });
  };

  /* ── الوضع البسيط: كتابةٌ على السطرين الأوّلين بلا إضافة سطرٍ ثالث ──
   * خانة «المبلغ» الواحدة القديمة استُبدلت بشريط القيد السريع بثلاث خانات
   * (T-JQE، issue #133) — أدناه `handleQuickAmountChange`. */

  const updateSimpleSide = (idx: number, patch: Partial<LineState>) => {
    if (posted) return;
    setTouched(true);
    setLines((prev) => {
      const next = [...prev];
      while (next.length < MIN_LINES) next.push(emptyLine());
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
  };

  /** كتابة رقمٍ في إحدى الخانات الثلاث (T-JQE، issue #133): يُفرغ الخانتين
      الأخريين (لا قيدَ يزعم قبضاً ودفعاً معاً)، يملأ طرفَي القيد البسيط
      بالمبلغ نفسه، ويقترح حساب الصندوق الافتراضي على الجهة المناسبة —
      مقبوضات على المدين، مدفوعات على الدائن، وعمليات ذمم بلا اقتراح على أيٍّ
      منهما — ما لم يكن المستخدم قد لمس تلك الجهة بيده. */
  const handleQuickAmountChange = (kind: QuickEntryKind, value: string) => {
    if (posted) return;
    setTouched(true);
    setQuickKind(kind);
    setQuickAmounts((prev) => applyQuickEntryAmount(prev, kind, value));
    const amt = parseFloat(value) || 0;
    setLines((prev) => {
      const next = [...prev];
      while (next.length < MIN_LINES) next.push(emptyLine());
      next[SIMPLE_DEBIT] = { ...next[SIMPLE_DEBIT], debit: value, credit: "" };
      next[SIMPLE_CREDIT] = { ...next[SIMPLE_CREDIT], credit: value, debit: "" };
      const debitId = next[SIMPLE_DEBIT].accountId ? Number(next[SIMPLE_DEBIT].accountId) : null;
      const creditId = next[SIMPLE_CREDIT].accountId ? Number(next[SIMPLE_CREDIT].accountId) : null;
      const sides = suggestQuickEntrySides({
        kind,
        // الخانة النشطة قبل هذه الكتابة — تُقرأ من الحالة قبل أن يحدّثها
        // `setQuickKind(kind)` أعلاه، فتحمل «السابقة» فعلاً لا الجديدة.
        previousKind: quickKind,
        amount: amt,
        defaultCashAccountId,
        touched: quickTouched,
        current: { debitAccountId: debitId, creditAccountId: creditId },
      });
      // المقارنة بالقيمة القديمة تشمل التراجع إلى `null` أيضاً — لا فرقاً
      // من طرازٍ واحد يتجاهل الحساب حين يُفرَغ. `sides.*AccountId` يحمل
      // القيمة النهائية سواءٌ أكانت اقتراحاً جديداً أم تراجعاً إلى بلا حساب.
      if (sides.debitAccountId !== debitId) {
        next[SIMPLE_DEBIT] = {
          ...next[SIMPLE_DEBIT],
          accountId: sides.debitAccountId != null ? String(sides.debitAccountId) : "",
        };
      }
      if (sides.creditAccountId !== creditId) {
        next[SIMPLE_CREDIT] = {
          ...next[SIMPLE_CREDIT],
          accountId: sides.creditAccountId != null ? String(sides.creditAccountId) : "",
        };
      }
      return next;
    });
  };

  /** الانتقال بين الوضعين — الطيّ إلى البسيط لا يقع إلا على قيدٍ يسعه. */
  const switchEntryMode = (m: "simple" | "advanced") => {
    // القيد المرحَّل يبدَّل عرضه لا محتواه — رؤية طرفيه في الشبكة حقُّ قارئه.
    if (m === entryMode) return;
    if (m === "simple") {
      if (!isSimpleShape(lines)) return;
      const normalized = normalizeToSimple(lines);
      setLines(normalized);
      // قيدٌ يُركَّب في المتصفح لا محمَّلٌ من الخادم — لا يُفرَض «ملموس» على
      // الجهتين (انظر تعليق `inferQuickEntryDisplay`)، وإلا جمّد الطيّ من
      // المتقدّم كلَّ اقتراحٍ لاحق بقية الجلسة.
      const disp = inferQuickEntryDisplay(normalized, defaultCashAccountId, { forceTouched: false });
      setQuickKind(disp.kind);
      setQuickAmounts(disp.amounts);
      setQuickTouched(disp.touched);
    }
    setEntryMode(m);
  };

  /** حساب ذمم عامّ (غير مربوط بطرف) — القيد عليه يلزمه اختيار الجهة. */
  const accountNeedsPartner = (accountId: string): boolean => {
    const a = accounts.find((x) => String(x.id) === accountId);
    return !!a && PARTNER_SUB_TYPES.has(String(a.sub_type || "")) && !a.linked_partner;
  };

  const removeLine = (i: number) => {
    if (posted) return;
    setTouched(true);
    setLines((prev) => {
      const next = prev.filter((_, idx) => idx !== i);
      return next.length ? next : [emptyLine()];
    });
  };

  /* ── totals ── */
  const totalDebit = lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0);
  const totalCredit = lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0);
  const diff = totalDebit - totalCredit;
  const balanced = Math.abs(diff) < 0.005 && totalDebit > 0;

  /* ── validation ── */
  const validate = (): string | null => {
    if (!header.transaction_date) return "التاريخ مطلوب";
    if (!header.description.trim()) return "البيان مطلوب";
    const active = lines.filter(
      (l) => l.accountId && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)
    );
    if (active.length < 2) return "يجب طرفان على الأقل بمبالغ";
    if (!balanced) return `القيد غير متوازن (فرق ${formatMoney(diff)})`;
    return null;
  };

  /* ── payload ── */
  const buildPayload = () => {
    const active = lines.filter(
      (l) => l.accountId && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)
    );
    return {
      transaction_date: header.transaction_date,
      description: header.description.trim(),
      reference_type: header.reference_type.trim() || null,
      reference_id: header.reference_id.trim() ? parseInt(header.reference_id, 10) : null,
      is_posted: false,
      currency: header.currency ? parseInt(header.currency, 10) : null,
      exchange_rate: parseFloat(header.exchange_rate) || 1,
      lines: active.map((l) => {
        const line: Record<string, unknown> = {
          account: parseInt(l.accountId, 10),
          debit: parseFloat(l.debit) || 0,
          credit: parseFloat(l.credit) || 0,
          partner: l.partnerId ? parseInt(l.partnerId, 10) : null,
          cost_center: l.costCenterId ? parseInt(l.costCenterId, 10) : null,
          description: l.description.trim() || null,
        };
        if (l.id) line.id = l.id;
        return line;
      }),
    };
  };

  /* ── save / post ── */
  const saveOnly = async () => {
    const v = validate();
    if (v) { setErr(v); return; }
    setSaving(true);
    setErr(null);
    try {
      const payload = buildPayload();
      if (journalId != null) await accountingApi.updateJournal(journalId, payload);
      else await accountingApi.createJournal(payload);
      // الشاشة تُغلق فوراً بعد الحفظ، فلافتة النجاح داخلها لا تُرى — التأكيد
      // يخرج كـ toast كي ينجو من الانتقال بدل أن يُحفظ القيد بلا أي إشعار.
      toast(journalId != null ? "تم حفظ القيد" : "تم إنشاء القيد", "success");
      onBack();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل الحفظ"));
    } finally { setSaving(false); }
  };

  const saveAndPost = async () => {
    const v = validate();
    if (v) { setErr(v); return; }
    setSaving(true);
    setErr(null);
    try {
      const payload = buildPayload();
      let id = journalId;
      if (id != null) await accountingApi.updateJournal(id, payload);
      else {
        const created = await accountingApi.createJournal(payload);
        id = created.id;
      }
      if (id != null) await accountingApi.postJournal(id);
      toast("تم حفظ القيد وترحيله", "success");
      onBack();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل الحفظ أو الترحيل"));
    } finally { setSaving(false); }
  };

  /* ── loading state ── */
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-[var(--color-text-muted)]">
        <Loader2 className="w-6 h-6 animate-spin ml-2" />
        جاري التحميل…
      </div>
    );
  }

  /* ── N3-T1: KitGrid columns for journal lines ── */
  const journalGridColumns: KitGridColumn<LineState & { _idx: number }>[] = [
    { key: 'seq',         header: '#',          width: '40px',  align: 'center', readOnly: true },
    { key: 'account',     header: 'الحساب',      width: '22%' },
    { key: 'description', header: 'البيان',      width: '20%' },
    { key: 'partner',     header: 'الجهة',       width: '13%' },
    { key: 'costCenter',  header: 'مركز التكلفة', width: '13%' },
    { key: 'debit',       header: 'مدين (Dr)',    width: '110px', align: 'center', type: 'number' },
    { key: 'credit',      header: 'دائن (Cr)',    width: '110px', align: 'center', type: 'number' },
    { key: 'del',         header: '',            width: '36px',  align: 'center' },
  ];

  type GridLine = LineState & { _idx: number };

  const gridLines: GridLine[] = lines.map((l, i) => ({ ...l, _idx: i }));

  const gridGetCell = (row: GridLine, key: string): string | number => {
    switch (key) {
      case 'seq':    return row._idx + 1;
      case 'debit':  return row.debit;
      case 'credit': return row.credit;
      case 'description': return row.description;
      default: return '';
    }
  };

  const renderCostCenterCell = (row: GridLine) => {
    if (posted) return <span className="text-xs">{costCenters.find((c) => String(c.id) === row.costCenterId)?.name || '—'}</span>;
    return (
      <select
        className="ktra-input"
        value={row.costCenterId}
        onChange={(e) => updateLine(row._idx, { costCenterId: e.target.value })}
      >
        <option value="">—</option>
        {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
    );
  };

  const gridOnChange = (rowIndex: number, key: string, value: string) => {
    // تفريغ البيان يدوياً يعيده إلى التوليد التلقائي.
    if (key === 'description') updateLine(rowIndex, { description: value, descriptionTouched: !!value.trim() });
    else if (key === 'debit')  updateLine(rowIndex, { debit: value });
    else if (key === 'credit') updateLine(rowIndex, { credit: value });
  };

  const renderAccountCell = (row: GridLine) => {
    const acc = accounts.find((a) => String(a.id) === row.accountId);
    const label = acc ? `${acc.code} — ${acc.name}` : '— اختر الحساب —';
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', position: 'relative' }}>
        <button
          type="button"
          className="ktra-cell-picker"
          disabled={posted}
          data-ktra-key="1"
          title="+ فتح شجرة الحسابات  |  * عرض الرصيد"
          onKeyDown={(e) => {
            if (e.key === '+') { e.preventDefault(); setPickerTargetLine(row._idx); setShowAccountPicker(true); }
            if (e.key === '*') { e.preventDefault(); void showAccountBalance(row._idx, row.accountId); }
          }}
          onClick={() => { if (!posted) { setPickerTargetLine(row._idx); setShowAccountPicker(true); } }}
        >
          {label}
        </button>
        {balanceTooltip?.lineIdx === row._idx && (
          <span style={{
            position: 'absolute', top: '100%', right: 0, zIndex: 50,
            background: 'var(--ktra-bg, #fffbf5)',
            border: '1px solid var(--ktra-border, #c8b99a)',
            borderRadius: '4px', padding: '3px 8px',
            fontSize: '11px', whiteSpace: 'nowrap', fontWeight: 600,
            boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
          }}>
            {balanceTooltip.balance}
          </span>
        )}
      </div>
    );
  };

  const renderDebitCell = (row: GridLine) => {
    const isDebit = parseFloat(row.debit) > 0;
    if (posted) return (
      <span className={`block text-center text-xs font-mono font-semibold ${isDebit ? 'ktra-text-accent' : 'ktra-text-soft'}`}>
        {isDebit ? fmtAmount(row.debit) : ''}
      </span>
    );
    return (
      <input
        type="number" step="0.01" min="0" placeholder="0.00"
        className="ktra-input ktra-num"
        data-ktra-field="remaining-amount"
        data-ktra-key="1"
        data-line-idx={String(row._idx)}
        data-side="debit"
        value={row.debit}
        onChange={(e) => updateLine(row._idx, { debit: e.target.value })}
        title="Space = تعبئة الفرق تلقائياً"
        style={{ color: isDebit ? 'var(--color-primary, #3b5bdb)' : undefined }}
      />
    );
  };

  const renderCreditCell = (row: GridLine) => {
    const isCredit = parseFloat(row.credit) > 0;
    if (posted) return (
      <span className={`block text-center text-xs font-mono font-semibold ${isCredit ? 'ktra-text-ink' : 'ktra-text-soft'}`}>
        {isCredit ? fmtAmount(row.credit) : ''}
      </span>
    );
    return (
      <input
        type="number" step="0.01" min="0" placeholder="0.00"
        className="ktra-input ktra-num"
        data-ktra-field="remaining-amount"
        data-ktra-key="1"
        data-line-idx={String(row._idx)}
        data-side="credit"
        value={row.credit}
        onChange={(e) => updateLine(row._idx, { credit: e.target.value })}
        title="Space = تعبئة الفرق تلقائياً"
        style={{ color: isCredit ? 'var(--color-danger, #e03131)' : undefined }}
      />
    );
  };

  const renderPartnerCell = (row: GridLine) => {
    if (posted) return <span className="text-xs">{partners.find((p) => String(p.id) === row.partnerId)?.name || '—'}</span>;
    return (
      <select
        className="ktra-input"
        value={row.partnerId}
        onChange={(e) => updateLine(row._idx, { partnerId: e.target.value })}
      >
        <option value="">—</option>
        {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    );
  };

  const renderDelCell = (row: GridLine) =>
    (!posted && lines.length > 1) ? (
      <button type="button" className="ktra-iconbtn ktra-iconbtn--danger" onClick={() => removeLine(row._idx)} title="حذف السطر">
        <Trash2 className="h-3 w-3" />
      </button>
    ) : null;

  journalGridColumns[1].render = renderAccountCell;     // الحساب
  journalGridColumns[3].render = renderPartnerCell;     // الجهة
  journalGridColumns[4].render = renderCostCenterCell;  // مركز التكلفة
  journalGridColumns[5].render = renderDebitCell;       // مدين
  journalGridColumns[6].render = renderCreditCell;      // دائن
  journalGridColumns[7].render = renderDelCell;         // حذف

  /* ── render ── */
  /* ── render ── */
  const activeDealRef: DealRef | null = dealRef ?? (
    header.reference_type === "LOGISTICS_PAYMENT" && (header.reference_summary || header.deal_ref_number)
      ? {
          dealId: "",
          dealNumber: header.deal_ref_number || "",
          displayName: header.reference_summary || header.deal_ref_number || "",
        }
      : null
  );

  /**
   * مسار المستند المصدر (فاتورة/سند/قيد أصلي). `reference_id` نصّ في الحالة،
   * والمرجع غير الرقمي لا مسار له فيسقط إلى null.
   */
  const sourceRefId = Number(header.reference_id);
  const sourceDocumentPath =
    header.reference_type && Number.isFinite(sourceRefId) && sourceRefId > 0
      ? entityPathForReference(header.reference_type, sourceRefId)
      : null;

  /** A3: قيد كتبه المستخدم بيده (لا مستند مصدر) — وحده يقبل وسم «تسوية». */
  const isManualEntry =
    !header.reference_type ||
    header.reference_type === 'MANUAL' ||
    header.reference_type === 'ADJUSTMENT';
  const isAdjustment = header.reference_type === 'ADJUSTMENT';

  /**
   * حقل البيان — واحدٌ لا اثنان: يسكن ترويسة المستند في الوضع المتقدّم،
   * ويصعد بارزاً فوق سطر القيد في الوضع البسيط. نفس الحالة ونفس منطق
   * «تلقائي/يدوي» في الموضعين.
   */
  const renderNarrationInput = (prominent: boolean) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <input
        className={prominent ? 'ktra-input ktra-input--lg' : 'ktra-input'}
        style={{ flex: 1 }}
        disabled={posted}
        placeholder="يتولد تلقائياً: من ح/ … إلى ح/ …"
        value={header.description}
        onChange={(e) => {
          // تفريغ البيان يدوياً يعيده إلى التوليد التلقائي.
          setHeaderDescTouched(!!e.target.value.trim());
          setTouched(true);
          setHeader((h) => ({ ...h, description: e.target.value }));
        }}
      />
      {!posted && headerDescTouched && (
        <button
          type="button"
          className="ktra-iconbtn"
          title="إرجاع البيان إلى التوليد التلقائي حسب الحسابات"
          onClick={() => {
            setHeaderDescTouched(false);
            setLines((prev) => prev.map((l) => ({ ...l, descriptionTouched: false })));
          }}
        >
          <RefreshCw className="h-3 w-3" />
        </button>
      )}
    </div>
  );

  /** طرفٌ من طرفَي القيد البسيط: حسابٌ يُختار من الشجرة + جهةٌ عند الحاجة. */
  const renderSimpleSide = (idx: number, label: string, hint: string) => {
    const row = lines[idx] || emptyLine();
    const acc = accounts.find((a) => String(a.id) === row.accountId);
    const needsPartner = accountNeedsPartner(row.accountId);
    return (
      <div>
        <span className="ktra-field-label mb-1 block">{label}</span>
        {posted ? (
          <span className="ktra-input flex items-center text-xs">
            {acc ? `${acc.code} — ${acc.name}` : '—'}
          </span>
        ) : (
          /* غلافٌ بمظهر الحقل: `.ktra-cell-picker` شفافٌ عمداً لأنه ابن خليةٍ
             في الشبكة، وهنا هو الحقل نفسه فيلزمه إطاره. */
          <div className="ktra-input flex items-center overflow-hidden">
            <button
              type="button"
              className="ktra-cell-picker text-start"
              title="فتح شجرة الحسابات"
              onClick={() => { setPickerTargetLine(idx); setShowAccountPicker(true); }}
            >
              {acc ? `${acc.code} — ${acc.name}` : hint}
            </button>
          </div>
        )}
        {/* الجهة تظهر عند حساب ذمم عامّ وحده — رقمٌ عليه بلا طرف لا صاحب له */}
        {needsPartner && (
          posted ? (
            <span className="mt-1 block text-xs text-[var(--ktra-ink-soft)]">
              {partners.find((p) => String(p.id) === row.partnerId)?.name || 'بلا جهة'}
            </span>
          ) : (
            <select
              className="ktra-input mt-1 block w-full"
              value={row.partnerId}
              onChange={(e) => updateSimpleSide(idx, { partnerId: e.target.value })}
              title="حساب ذمم — اختر الجهة كي يظهر الرقم في كشف حسابها"
            >
              <option value="">— اختر الجهة —</option>
              {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )
        )}
      </div>
    );
  };

  const canFoldToSimple = isSimpleShape(lines);

  const isShipmentLink =
    relatedKind === "shipment" ||
    (relatedKind == null &&
      header.reference_type === "LOGISTICS_PAYMENT" &&
      /\bشحنة\b/i.test(header.description || ""));

  /* ISSUE #120: الحفظ المحلي فشل فعلاً — لافتة تطلب حفظاً يدوياً بدل الانتظار
     الصامت حتى تحاول المغادرة. */
  const draftSaveFailedBanner = draftSaveFailed && !posted ? (
    <div
      role="alert"
      aria-live="assertive"
      data-testid="draft-save-failed-banner"
      className="sticky top-0 z-40 flex items-center gap-2 border-b border-red-200 bg-red-100 px-4 py-2 text-sm font-medium text-red-800"
    >
      <AlertCircle className="h-4 w-4 shrink-0" />
      <span>تعذّر حفظ نسخة محلية من هذا القيد — اضغط «تخزين» يدوياً كي لا يضيع عملك.</span>
    </div>
  ) : null;

  /* ISSUE #118: شريط الاستعادة التلقائية — إخبارٌ لا سؤال، ومعه «تراجع» وحده. */
  const draftRestoreBanner = draftBanner ? (
    <div className="ktra-banner ktra-banner--warn" role="status" data-testid="draft-restored-banner">
      <Info className="w-4 h-4" style={{ marginInlineEnd: '6px' }} />
      <span>
        {draftBanner.eligibility === "restore" &&
          `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "stale" &&
          `تغيّر القيد بعد مسودتك (مسودتُك ${formatTimeValue(draftBanner.updatedAt)})`}
        {draftBanner.eligibility === "posted" &&
          `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(draftBanner.updatedAt)}) لهذا القيد المرحَّل — للاطّلاع فقط.`}
      </span>
      {draftBanner.eligibility === "restore" && (
        <button
          type="button"
          className="ktra-toolbtn"
          onClick={() => void handleUndoDraft()}
          data-testid="draft-restored-undo"
        >
          <Undo2 className="h-4 w-4" /> تراجع
        </button>
      )}
      {draftBanner.eligibility === "stale" && (
        <>
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={() => onRestoreDraft(draftBanner.payload)}
            data-testid="draft-stale-preview"
          >
            استعرض مسودتي
          </button>
          <button
            type="button"
            className="ktra-toolbtn"
            onClick={() => void discardDraft()}
            data-testid="draft-stale-discard"
          >
            تجاهلها
          </button>
        </>
      )}
    </div>
  ) : null;

  /* شريط اليتامى (issue #119 §٧): مسودّات قيدٍ جديد أخرى تُركت في تبويبات أخرى. */
  const orphanDraftsBanner = orphanDrafts.length > 0 && !orphanBarDismissed ? (
    <div className="ktra-banner" role="status" data-testid="orphan-drafts-banner">
      <Info className="w-4 h-4" style={{ marginInlineEnd: '6px' }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <span>{orphanDraftsBannerText(orphanDrafts.length)}</span>
        <ul style={{ listStyle: 'disc', paddingInlineStart: '16px', fontSize: '11px' }}>
          {orphanDrafts.map((o) => (
            <li key={o.key}>{formatTimeValue(o.updatedAt)} — {o.previewLine || "—"}</li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        className="ktra-toolbtn"
        style={{ marginInlineStart: 'auto' }}
        onClick={() => setOrphanBarDismissed(true)}
        data-testid="orphan-drafts-dismiss"
      >
        <X className="w-4 h-4" /> إخفاء
      </button>
    </div>
  ) : null;

  return (
    <div
      style={{ minHeight: 'calc(100vh - 5rem)', display: 'flex', flexDirection: 'column' }}
    >
    <KitDocumentShell
      title="قيود المحاسبة"
      state={journalId ? `قيد #${journalId}` : 'قيد جديد'}
      nav={nav}
      actions={[
        {
          key: 'save',
          label: posted ? 'مرحَّل' : 'تخزين',
          icon: <Save />,
          onClick: !posted ? saveAndPost : undefined,
          disabled: posted,
        },
        {
          key: 'reload',
          label: 'تحديث',
          icon: <RefreshCw />,
          onClick: load,
          separatorBefore: true,
        },
        {
          key: 'back',
          label: 'خروج',
          icon: <X />,
          onClick: onBack,
          danger: true,
          separatorBefore: true,
        },
        {
          key: 'print',
          label: 'طباعة',
          icon: <Printer />,
          onClick: () => window.print(),
        },
      ]}
      header={
        <>
          {/* رقم القيد */}
          <label className="ktra-field">
            <span className="ktra-field-label">رقم القيد</span>
            <input className="ktra-input" readOnly value={journalId ? `#${journalId}` : '— جديد —'} />
          </label>
          {/* التاريخ */}
          <label className="ktra-field">
            <span className="ktra-field-label">التاريخ</span>
            <input
              className="ktra-input"
              type="date"
              disabled={posted}
              value={header.transaction_date}
              onChange={(e) => { setTouched(true); setHeader((h) => ({ ...h, transaction_date: e.target.value })); }}
            />
          </label>
          {/* العملة */}
          <label className="ktra-field">
            <span className="ktra-field-label">العملة</span>
            <select
              className="ktra-input"
              disabled={posted}
              value={header.currency}
              onChange={(e) => {
                const sel = currencies.find((c) => String(c.CurrencyID) === e.target.value);
                setTouched(true);
                setHeader((h) => ({
                  ...h,
                  currency: e.target.value,
                  exchange_rate: sel?.IsBaseCurrency ? '1' : h.exchange_rate,
                  currency_code: sel?.Code || '',
                }));
              }}
            >
              <option value="">— اختر —</option>
              {currencies.map((c) => (
                <option key={c.CurrencyID} value={c.CurrencyID}>
                  {c.Code} {c.IsBaseCurrency ? '(أساسية)' : ''}
                </option>
              ))}
            </select>
          </label>
          {/* سعر العملة */}
          <label className="ktra-field">
            <span className="ktra-field-label">سعر العملة</span>
            <input
              className="ktra-input"
              type="number"
              step="0.000001"
              min="0"
              disabled={posted || !!currencies.find((c) => String(c.CurrencyID) === header.currency)?.IsBaseCurrency}
              value={header.exchange_rate}
              onChange={(e) => { setTouched(true); setHeader((h) => ({ ...h, exchange_rate: e.target.value })); }}
            />
          </label>
          {/* نوع المرجع — يحدده النظام من مصدر القيد ولا يُدخَل يدوياً */}
          <label className="ktra-field">
            <span className="ktra-field-label">نوع المرجع</span>
            <input
              className="ktra-input"
              readOnly
              value={header.reference_type
                ? refTypeLabel(header.reference_type, header.description, header.source_label)
                : '—'}
            />
          </label>
          {/* A3: وسم «قيد تسوية» — يدويٌّ فقط، ويجعل القيد قابلاً للتصفية في الدفتر */}
          {isManualEntry && (
            <label className="ktra-field">
              <span className="ktra-field-label">قيد تسوية</span>
              <div
                className="ktra-input"
                style={{ display: 'flex', alignItems: 'center', gap: '6px', minHeight: '28px' }}
              >
                <input
                  type="checkbox"
                  disabled={posted}
                  checked={isAdjustment}
                  onChange={(e) => {
                    setTouched(true);
                    setHeader((h) => ({
                      ...h,
                      reference_type: e.target.checked ? 'ADJUSTMENT' : 'MANUAL',
                    }));
                  }}
                />
                <span style={{ fontSize: '11px' }}>قيد تسوية محاسبية</span>
              </div>
            </label>
          )}
          {/* البيان الإجمالي — يتولد من الحسابات ما لم يُكتب يدوياً.
              في الوضع البسيط يصعد إلى صدر الشاشة بارزاً بدل أن يُدفن هنا. */}
          {entryMode === 'advanced' && (
            <label className="ktra-field" style={{ gridColumn: 'span 2' }}>
              <span className="ktra-field-label">
                البيان الإجمالي {headerDescTouched ? '(يدوي)' : '(تلقائي)'}
              </span>
              {renderNarrationInput(false)}
            </label>
          )}
        </>
      }
      status={
        <>
          <span className="ktra-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
          <span className="ktra-status-item">الحالة <b>{posted ? 'مرحَّل' : 'مسودة'}</b></span>
          {journalId && <span className="ktra-status-item">رقم القيد <b>{journalId}</b></span>}
          <span className="ktra-status-item">
            مدين <b className="ktra-num">{formatMoney(totalDebit)}</b>
          </span>
          <span className="ktra-status-item">
            دائن <b className="ktra-num">{formatMoney(totalCredit)}</b>
          </span>
          {!balanced && totalDebit > 0 && (
            <span className="ktra-status-item" style={{ color: 'var(--ktra-err, #c0392b)' }}>
              فرق <b>{formatMoney(Math.abs(diff))}</b>
            </span>
          )}
          {balanced && totalDebit > 0 && (
            <span className="ktra-status-item" style={{ color: 'var(--ktra-ok, #27ae60)' }}>
              متوازن ✓
            </span>
          )}
          {/* issue #121: مؤشّر دائم كي لا يضغط المستخدم «تخزين» احتياطاً كل دقيقة. */}
          {draftSavedAt && !posted && (
            <span className="ktra-status-item" data-testid="draft-saved-indicator">
              مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
            </span>
          )}
        </>
      }
    >
    {draftSaveFailedBanner}
    {draftRestoreBanner}
    {orphanDraftsBanner}
    <div style={{ height: '100%', overflow: 'auto', padding: '8px 12px', background: 'var(--ktra-bg, #fffbf5)' }}>

      {/* ── ارتباط بصفقة/شحنة (تنقّل) ── */}
      {activeDealRef && (
        <div className="ktra-banner" style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 12px' }}>
          <Handshake className="w-4 h-4" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontSize: '11px', color: 'var(--ktra-ink-soft)' }}>
              {isShipmentLink ? 'مرتبط بشحنة:' : 'مرتبط بصفقة:'}
            </span>
            <span style={{ fontWeight: 600, marginInlineStart: '6px' }}>{activeDealRef.displayName}</span>
          </div>
          {isShipmentLink && activeDealRef.dealId && onNavigateToShipment && /^\d+$/.test(String(activeDealRef.dealId).trim()) && (
            <button type="button" className="ktra-toolbtn" onClick={() => onNavigateToShipment(String(activeDealRef.dealId).trim())}>
              <ExternalLink className="w-3 h-3" /> فتح الشحنة
            </button>
          )}
          {!isShipmentLink && (activeDealRef.dealId || activeDealRef.dealNumber) && onNavigateToDeal && (
            <button type="button" className="ktra-toolbtn" onClick={() => onNavigateToDeal(activeDealRef.dealId || activeDealRef.dealNumber)}>
              <ExternalLink className="w-3 h-3" /> فتح الصفقة
            </button>
          )}
        </div>
      )}

      {/* ── خطأ ── */}
      {err && (
        <div className="ktra-banner ktra-banner--err" style={{ marginBottom: '8px' }}>
          <AlertTriangle className="w-4 h-4" style={{ marginInlineEnd: '6px' }} />
          {err}
        </div>
      )}

      {/* ── مصدر القيد: يعرضه النظام ولا يُدخَل يدوياً ── */}
      <div className="ktra-input" style={{ display: 'flex', alignItems: 'center', minHeight: '28px', marginBottom: '8px', background: 'var(--ktra-surface-2, #f4ede0)' }}>
        <Info className="w-3 h-3" style={{ marginInlineEnd: '6px', color: 'var(--ktra-ink-soft)' }} />
        <span style={{ fontSize: '12px' }}>
          {!isManualEntry
            ? `مصدر القيد: ${refTypeLabel(header.reference_type, header.description, header.source_label)}${header.reference_id ? ' · #' + header.reference_id : ''}`
            : isAdjustment
              ? 'قيد تسوية يدوي — لا مستند مصدر'
              : 'قيد يدوي — لا مستند مصدر'}
        </span>
        {/* القفزة الثالثة في التنقيب: من القيد إلى المستند الذي أنشأه. */}
        {sourceDocumentPath && (
          <button
            type="button"
            className="ktra-toolbtn"
            style={{ marginInlineStart: 'auto' }}
            title="فتح المستند المصدر"
            onClick={() => navigate(sourceDocumentPath)}
          >
            <ExternalLink className="w-3 h-3" /> فتح المستند
          </button>
        )}
      </div>

      {/* ── مبدّل الوضع: بسيط (طرفان) · متقدم (شبكة كاملة) ── */}
      <div className="ktra-tabs" style={{ marginBottom: '8px' }}>
        <button
          type="button"
          className={`ktra-tab${entryMode === 'simple' ? ' ktra-tab--active' : ''}`}
          disabled={entryMode !== 'simple' && !canFoldToSimple}
          title={canFoldToSimple
            ? 'قيد بطرفين: بيانٌ واحد وحسابان ومبلغٌ يُكتب مرّة'
            : 'هذا القيد أكثر من طرفين — يُحرَّر في الوضع المتقدّم'}
          onClick={() => switchEntryMode('simple')}
        >
          بسيط
        </button>
        <button
          type="button"
          className={`ktra-tab${entryMode === 'advanced' ? ' ktra-tab--active' : ''}`}
          title="شبكة القيد الكاملة — ثلاثة أطراف فأكثر، مراكز تكلفة، بيان لكل سطر"
          onClick={() => switchEntryMode('advanced')}
        >
          متقدم
        </button>
      </div>

      {entryMode === 'simple' ? (
        /* ── الوضع البسيط: بيان · شريط قيدٍ سريع بثلاث خانات · مدين/دائن ── */
        <div className="rounded-md border border-[var(--ktra-border,#c8b99a)] bg-[var(--ktra-surface,#fffdf8)] p-3">
          {/* الملاحظة بارزة وللقيد كلّه — لا ملاحظةً لكل سطر */}
          <div className="mb-3">
            <span className="ktra-field-label">
              البيان — ملاحظة القيد كلّه {headerDescTouched ? '(يدوي)' : '(تلقائي)'}
            </span>
            <div className="mt-1">{renderNarrationInput(true)}</div>
          </div>

          {/* ── T-JQE (issue #133): شريط القيد السريع — مقبوضات · مدفوعات ·
              عمليات ذمم، متمانعة: رقمٌ في خانة يُفرغ الخانتين الأخريين. ── */}
          <div className="mb-3">
            <div className="grid gap-3 md:grid-cols-3">
              {(
                [
                  { kind: 'receipts' as QuickEntryKind, label: 'مقبوضات' },
                  { kind: 'payments' as QuickEntryKind, label: 'مدفوعات' },
                  { kind: 'receivable' as QuickEntryKind, label: 'عمليات ذمم' },
                ]
              ).map(({ kind, label }) => (
                <div key={kind}>
                  <span className="ktra-field-label mb-1 block">
                    {label}{header.currency_code ? ` (${header.currency_code})` : ''}
                  </span>
                  {posted ? (
                    <span className="ktra-input ktra-num flex items-center font-bold">
                      {quickKind === kind ? fmtAmount(quickAmounts[kind]) : '—'}
                    </span>
                  ) : (
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder="0.00"
                      className="ktra-input ktra-num block w-full font-bold"
                      data-ktra-field={`quick-amount-${kind}`}
                      value={quickAmounts[kind]}
                      onChange={(e) => handleQuickAmountChange(kind, e.target.value)}
                    />
                  )}
                </div>
              ))}
            </div>
            {!posted && !defaultCashAccountId && (
              <p className="mt-1 text-[11px] text-[var(--ktra-ink-soft)]">
                لا صندوق افتراضي مُعرَّف للشركة — عرّفه من{' '}
                <button
                  type="button"
                  className="underline"
                  onClick={() => navigate('/cash-boxes')}
                >
                  شاشة الصناديق
                </button>{' '}
                ليُقترح تلقائياً على المقبوضات والمدفوعات؛ الحقول تعمل الآن بلا اقتراح.
              </p>
            )}
            <p className="mt-1 text-[11px] text-[var(--ktra-ink-soft)]">
              يُكتب المبلغ في خانةٍ واحدة — يُقيَّد مديناً ودائناً تلقائياً.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            {renderSimpleSide(SIMPLE_DEBIT, 'الحساب المدين (منه)', '— اختر الحساب المدين —')}
            {renderSimpleSide(SIMPLE_CREDIT, 'الحساب الدائن (له)', '— اختر الحساب الدائن —')}
          </div>

          {/* ── مراجعة ما أُدخل قبل الحفظ ── */}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[var(--ktra-ink-soft)]">
                  <th className="px-1 py-1 text-start font-normal">الحساب</th>
                  <th className="px-1 py-1 text-center font-normal">مدين</th>
                  <th className="px-1 py-1 text-center font-normal">دائن</th>
                </tr>
              </thead>
              <tbody>
                {[SIMPLE_DEBIT, SIMPLE_CREDIT].map((idx) => {
                  const row = lines[idx] || emptyLine();
                  const acc = accounts.find((a) => String(a.id) === row.accountId);
                  return (
                    <tr key={idx} className="border-t border-[var(--ktra-border,#c8b99a)]">
                      <td className="px-1 py-1">{acc ? `${acc.code} — ${acc.name}` : '—'}</td>
                      <td className="px-1 py-1 text-center ktra-num">
                        {parseFloat(row.debit) > 0 ? fmtAmount(row.debit) : ''}
                      </td>
                      <td className="px-1 py-1 text-center ktra-num">
                        {parseFloat(row.credit) > 0 ? fmtAmount(row.credit) : ''}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-[var(--ktra-border,#c8b99a)] font-semibold">
                  <td className="px-1 py-1">الإجمالي</td>
                  <td className="px-1 py-1 text-center ktra-num">{fmtAmount(totalDebit)}</td>
                  <td className="px-1 py-1 text-center ktra-num">{fmtAmount(totalCredit)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      ) : (
      <>
      {/* ── KitGrid لبنود القيد ── */}
      <KitGrid<GridLine>
        columns={journalGridColumns}
        rows={gridLines}
        getCell={gridGetCell}
        getRowKey={(r) => r._idx}
        onChange={gridOnChange}
        onAddRow={() => { setTouched(true); setLines((prev) => [...prev, emptyLine()]); }}
        variant="journal"
        emptyHint="ابدأ إدخال بنود القيد — Enter للسطر التالي"
      />

      {/* ── إجمالي/فرق row ── */}
      <div className="ktra-total-row ktra-total-row--grand" style={{ marginTop: '6px', display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: '12px', padding: '8px 12px' }}>
        <span style={{ fontSize: '12px', color: 'var(--ktra-ink-soft)' }}>
          {lines.filter((l) => l.accountId && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)).length} سطر نشط
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--ktra-ink-soft)' }}>مدين</span>
          <span className="ktra-num" style={{ fontWeight: 700, color: 'var(--color-primary, #3b5bdb)' }}>{fmtAmount(totalDebit)}</span>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--ktra-ink-soft)' }}>دائن</span>
          <span className="ktra-num" style={{ fontWeight: 700, color: 'var(--color-danger, #e03131)' }}>{fmtAmount(totalCredit)}</span>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--ktra-ink-soft)' }}>{balanced ? 'متوازن' : 'فرق'}</span>
          <span className="ktra-num" style={{
            fontWeight: 700,
            color: balanced && totalDebit > 0 ? 'var(--ktra-ok, #2d7d46)' : 'var(--ktra-err, #c0392b)',
          }}>
            {balanced && totalDebit > 0 ? '✓' : fmtAmount(Math.abs(diff))}
          </span>
        </span>
      </div>
      </>
      )}

      {/* ── أزرار سفلية ── */}
      {!posted && (
        <div style={{ display: 'flex', gap: '8px', marginTop: '10px', justifyContent: 'flex-end' }}>
          {entryMode === 'advanced' && (
            <button
              type="button"
              className="ktra-toolbtn"
              onClick={() => { setTouched(true); setLines((prev) => [...prev, emptyLine()]); }}
            >
              <Plus className="w-3 h-3" /> سطر جديد
            </button>
          )}
          <button
            type="button"
            className="ktra-toolbtn"
            disabled={saving}
            onClick={saveOnly}
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            حفظ مسودة
          </button>
          <OfflineGuard
            action="ترحيل القيد"
            warningMessage="الترحيل يتطلب اتصالاً — أرقام القيود تُولَّد على الـserver"
          >
            <button
              type="button"
              className="ktra-toolbtn"
              disabled={saving || !balanced || totalDebit <= 0}
              onClick={saveAndPost}
              title={!balanced ? 'يجب توازن القيد أولاً (F12)' : 'F12 = حفظ وترحيل'}
              style={{
                background: balanced && totalDebit > 0 ? 'var(--ktra-ok, #2d7d46)' : undefined,
                color: balanced && totalDebit > 0 ? '#fff' : undefined,
              }}
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
              حفظ وترحيل (F12)
            </button>
          </OfflineGuard>
        </div>
      )}

      {posted && (
        <div className="ktra-banner" style={{ marginTop: '10px', background: 'var(--ktra-ok-bg, #e3f6e9)', color: 'var(--ktra-ok, #2d7d46)' }}>
          <CheckCircle className="w-3 h-3" style={{ marginInlineEnd: '6px' }} />
          هذا القيد مرحَّل — لا يمكن تعديله.
        </div>
      )}
    </div>

    {/* ── T-DEFACC: شجرة الحسابات (تُفتح بـ + على خلية الحساب) ──
        THA-111: أي حساب يصلح لسطر القيد، لكن الترحيل لا يقع إلا على ورقة نشطة —
        الحساب الأب يظهر للتصفّح ولا يُختار. */}
    <AccountTreePicker
      open={showAccountPicker}
      accounts={accounts}
      value={pickerTargetLine != null && lines[pickerTargetLine]?.accountId
        ? Number(lines[pickerTargetLine].accountId)
        : null}
      purpose="any"
      title="شجرة الحسابات"
      onSelect={(a) => {
        if (pickerTargetLine != null) {
          // الوضع البسيط يكتب على السطرين وحدهما — لا يُلحق سطراً ثالثاً.
          if (entryMode === 'simple') {
            updateSimpleSide(pickerTargetLine, { accountId: String(a.id) });
            // T-JQE: تعديلٌ يدويٌّ لحساب الجهة — لا يعود اقتراح الصندوق
            // الافتراضي يدهسه حين يتغيّر المبلغ لاحقاً.
            if (pickerTargetLine === SIMPLE_DEBIT) setQuickTouched((t) => ({ ...t, debit: true }));
            else if (pickerTargetLine === SIMPLE_CREDIT) setQuickTouched((t) => ({ ...t, credit: true }));
          }
          else updateLine(pickerTargetLine, { accountId: String(a.id) });
        }
        setShowAccountPicker(false);
        setPickerTargetLine(null);
      }}
      onClose={() => { setShowAccountPicker(false); setPickerTargetLine(null); }}
    />
    </KitDocumentShell>
    </div>
  );
};
