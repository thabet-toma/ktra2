/**
 * إشعارات مدينة/دائنة — قسم المالية، على **أيّ طرف**: عميلٍ أو دائنٍ (مورد، مخلّص،
 * وكيل شحن، ناقل). كانت تحت المبيعات للعميل وحده والمقابل إيراداته إجبارياً.
 *
 * الدلالة من منظور ذمّة الطرف (`sales/services/orders.py` — `post_credit_debit_note`):
 * المدين Dr ذمّته (يزيد ما عليه أو ينقص ما له)، والدائن Cr ذمّته. المقابل يختاره
 * المستخدم من الشجرة (الافتراضيّ من الخادم: `default-account/`)، والربط بمستندٍ واحد
 * اختياريّ — فاتورة الشراء والتخليص والإرسالية واستحقاق الشحن يُطفئ الإشعارُ متبقّيها.
 * يُفتح من بطاقة الطرف وقائمة زر اليمين بـ`?action=new&partner_id=`.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  Ban,
  CheckCircle,
  Loader2,
  Plus,
  Printer,
  RefreshCw,
  Save,
  Split,
  Trash2,
  Undo2,
  X,
} from "lucide-react";

import { humanizeThrown } from "../../utils/drfError";
import { useConfirm } from "../../contexts/ConfirmContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import { KitSpinner } from "../kit/KitStates";
import { KitAutocomplete, type KitAutocompleteOption } from "../kit/KitAutocomplete";
import { KitDocumentShell, useKitKeymap, useRecordNavigation } from "../kit";
import { ShareRowButton } from "../shared/ShareRowButton";
import { DocumentDraftBanners } from "../shared/DocumentDraftBanners";
import { NoteAllocationModal } from "../shared/NoteAllocationModal";
import { AccountTreeField } from "./AccountTreePicker";
import { accountingApi } from "../../services/accountingApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import {
  CREDIT_DEBIT_NOTE_LINK_FIELD,
  createCreditDebitNote,
  creditDebitNoteAction,
  deleteCreditDebitNote,
  getCreditDebitNoteDefaultAccount,
  getPartnerBalance,
  listCreditDebitNotes,
  listSalesInvoices,
  updateCreditDebitNote,
  type CreditDebitNoteBody,
  type CreditDebitNoteLinkKind,
  type CreditDebitNoteRow,
} from "../../services/salesApi";
import { clientLogger } from "../../services/logger";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized, formatTimeValue } from "../../utils/formatDate";
import { printReport } from "../../utils/printReport";
import { CREDITOR_PARTNER_TYPES, partnerTypeLabel } from "../../utils/partnerActions";
import {
  noteBalanceDelta,
  noteExplanation,
  noteMeaning,
  partyBalancePhrase,
  type NoteType,
} from "../../utils/creditDebitNote";
import type { AccountNodeLike } from "../../utils/accountTree";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";

type PartnerOption = { id: number; name: string; partner_type?: string | null };
type CurrencyOption = { CurrencyID: number; Code: string; IsBaseCurrency?: boolean };

/** مستندٌ قابلٌ للربط: نوعه ومعرّفه ووسمه ومتبقّيه. */
type LinkDoc = { kind: CreditDebitNoteLinkKind; id: number; label: string; remaining?: string };

const PARTY_TYPES = ["Customer", ...CREDITOR_PARTNER_TYPES] as const;

/** وسم نوع المستند المربوط — فاتورة البيع بمصطلح الشركة (`term`). */
const LINK_KIND_LABEL: Record<Exclude<CreditDebitNoteLinkKind, "sales_invoice">, string> = {
  purchase_invoice: "فاتورة شراء",
  clearance: "تخليص",
  local_shipment: "إرسالية",
  freight: "استحقاق شحن",
};
const linkKindLabel = (kind: CreditDebitNoteLinkKind, term: (key: string) => string) =>
  kind === "sales_invoice" ? term("doc.sales_invoice") : LINK_KIND_LABEL[kind];
/** «تخليص #1 — SH-…» — وسم المستحق من الخادم يحمل نوعه أحياناً فلا يُكرَّر. */
const linkDocTitle = (kind: CreditDebitNoteLinkKind, label: string, term: (key: string) => string) => {
  const kindLabel = linkKindLabel(kind, term);
  return label.startsWith(kindLabel) ? label : `${kindLabel} ${label}`;
};

/** حسابات لا تكون مقابلاً — الخادم يرفضها أيضاً (`credit_debit_counter_account_error`):
 *  الذمم والمخزون، والنقد والبنوك والشيكات (الإشعار ليس دفعاً؛ `accounting.api.money_account_kind`). */
const BLOCKED_COUNTER_SUB_TYPES = new Set(["receivable", "payable", "inventory", "cash_box", "bank"]);
const CHEQUE_ACCOUNT_CODES = new Set(["1107", "1109", "2111"]);
const isCounterSelectable = (a: AccountNodeLike) =>
  !BLOCKED_COUNTER_SUB_TYPES.has(String(a.sub_type || "")) &&
  !CHEQUE_ACCOUNT_CODES.has(String(a.code || "")) &&
  !String(a.name || "").includes("شيكات");

const STATUS_LABEL: Record<string, string> = { draft: "مسودة", posted: "مرحّل", cancelled: "ملغي" };
const STATUS_CLASS: Record<string, string> = {
  draft: "ktra-bg-panel ktra-text-ink",
  posted: "bg-green-100 text-green-700",
  cancelled: "ktra-bg-panel ktra-text-state",
};

const linkKey = (doc: { kind: string; id: number }) => `${doc.kind}:${doc.id}`;
const isCreditorType = (t?: string | null) =>
  (CREDITOR_PARTNER_TYPES as readonly string[]).includes(String(t || ""));

/** ISSUE #121: حمولة المسودّة المحلية — تكفي وحدها لإعادة بناء النموذج. */
interface NoteDraftPayload {
  formType: NoteType;
  formPartner: string;
  formDate: string;
  formAmount: string;
  formTax: string;
  formCurrency: string;
  formRate: string;
  formCounter: string;
  formLink: string;
  formReason: string;
}

const today = () => new Date().toISOString().slice(0, 10);

export const CreditDebitNotesPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const { can, term } = usePermissions();
  const canCreate = can("accounting.journal.create");
  const canPost = can("accounting.journal.post");
  const canUnpost = can("accounting.journal.unpost");

  const [notes, setNotes] = useState<CreditDebitNoteRow[]>([]);
  const [partners, setPartners] = useState<PartnerOption[]>([]);
  const [accounts, setAccounts] = useState<AccountNodeLike[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  // تنبيه ما بعد الإجراء (إلغاء ترحيل إشعارٍ موزَّع يفكّ توزيعاته ويسمّيها).
  const [notice, setNotice] = useState<string | null>(null);
  // الإشعار المسوّي المفتوح في نافذة التوزيع.
  const [allocNote, setAllocNote] = useState<CreditDebitNoteRow | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formType, setFormType] = useState<NoteType>("debit");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [formPartner, setFormPartner] = useState("");
  const [formDate, setFormDate] = useState(today);
  const [formAmount, setFormAmount] = useState("");
  const [formTax, setFormTax] = useState("");
  const [formCurrency, setFormCurrency] = useState("");
  const [formRate, setFormRate] = useState("1");
  const [formCounter, setFormCounter] = useState("");
  /** اختاره المستخدم يدوياً — فلا يطغى عليه الافتراضيّ عند تغيير الطرف أو الربط. */
  const [counterChosen, setCounterChosen] = useState(false);
  const [formLink, setFormLink] = useState("");
  const [formReason, setFormReason] = useState("");
  const [linkDocs, setLinkDocs] = useState<LinkDoc[]>([]);
  const [balance, setBalance] = useState<{ before: number; after: number; creditor: boolean } | null>(null);
  const [defaultHint, setDefaultHint] = useState<string | null>(null);

  const [touched, setTouched] = useState(false);
  const markTouched = () => setTouched(true);

  const partner = partners.find((p) => String(p.id) === formPartner) || null;
  const creditor = isCreditorType(partner?.partner_type);
  const amount = Number(formAmount) || 0;
  const selectedNote = notes.find((n) => n.id === selectedId);
  const readOnly = Boolean(selectedNote && selectedNote.status !== "draft");

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [ns, parts, accs, curs] = await Promise.all([
        listCreditDebitNotes(),
        accountingApi.getPartners() as Promise<PartnerOption[]>,
        accountingApi.getAccounts() as Promise<AccountNodeLike[]>,
        accountingApi.getCurrencies() as Promise<CurrencyOption[]>,
      ]);
      setNotes(ns || []);
      setPartners(parts || []);
      setAccounts(accs || []);
      setCurrencies(curs || []);
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحميل"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const resetForm = useCallback((partnerId = "", noteType: NoteType = "debit") => {
    setSelectedId(null);
    setFormType(noteType);
    setFormPartner(partnerId);
    setFormDate(today());
    setFormAmount("");
    setFormTax("");
    setFormCurrency("");
    setFormRate("1");
    setFormCounter("");
    setCounterChosen(false);
    setFormLink("");
    setFormReason("");
    setBalance(null);
    setTouched(false);
  }, []);

  // بطاقة الطرف وقائمة زر اليمين: `?action=new&partner_id=83&note_type=debit`.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("action") !== "new") return;
    const noteType = params.get("note_type") === "credit" ? "credit" : "debit";
    resetForm(params.get("partner_id") || "", noteType);
    setShowForm(true);
    clientLogger.info("credit_debit_note.open_from_party", { hasPartner: Boolean(params.get("partner_id")) });
    navigate(location.pathname, { replace: true });
  }, [location.search, location.pathname, navigate, resetForm]);

  const loadIntoForm = useCallback((n: CreditDebitNoteRow) => {
    setSelectedId(n.id);
    setFormType(n.note_type);
    setFormPartner(String(n.partner));
    setFormDate(n.note_date?.slice(0, 10) || today());
    setFormAmount(n.amount);
    setFormTax(Number(n.tax_amount) ? String(n.tax_amount) : "");
    setFormCurrency(n.currency ? String(n.currency) : "");
    setFormRate(n.exchange_rate || "1");
    setFormCounter(n.counter_account ? String(n.counter_account) : "");
    setCounterChosen(Boolean(n.counter_account));
    setFormLink(n.linked_document ? linkKey(n.linked_document) : "");
    setFormReason(n.reason || "");
    setTouched(false);
    setShowForm(true);
  }, []);

  // رابط المستند إلى إشعاره (`entityLinks` — تبويب «الدفعات» في شاشة الاستيراد): `?note_id=`.
  const linkedNoteId = new URLSearchParams(location.search).get("note_id");
  useEffect(() => {
    if (!linkedNoteId || loading) return;
    const target = notes.find((n) => String(n.id) === linkedNoteId);
    if (target) loadIntoForm(target);
    else if (notes.length) setErr(`الإشعار #${linkedNoteId} غير موجود في هذه الشركة.`);
    else return;
    navigate(location.pathname, { replace: true });
  }, [linkedNoteId, loading, notes, loadIntoForm, navigate, location.pathname]);

  const nav = useRecordNavigation<CreditDebitNoteRow>({
    items: notes,
    getId: (n) => n.id || 0,
    currentId: selectedId,
    onSelect: async (id) => {
      if (id === null) {
        resetForm();
        setShowForm(true);
        return;
      }
      const found = notes.find((n) => n.id === id);
      if (found) loadIntoForm(found);
    },
  });

  // مستندات الطرف القابلة للربط: فواتير البيع المرحّلة للعميل، ومستحقّات الدائن
  // المفتوحة (فاتورة شراء، تخليص، استحقاق شحن، إرسالية) — مصدر كرت الطرف نفسه.
  useEffect(() => {
    if (!partner) {
      setLinkDocs([]);
      return;
    }
    let alive = true;
    const load = async () => {
      try {
        let docs: LinkDoc[];
        if (isCreditorType(partner.partner_type)) {
          const rows = await purchaseInvoiceApi.supplierAllocatableDocs(partner.id);
          docs = rows.map((r) => ({
            kind: r.target
              ? ({ clearance: "clearance", freight: "freight", local: "local_shipment" } as const)[r.target.kind]
              : "purchase_invoice",
            id: r.id,
            label: r.label,
            remaining: String(r.remaining),
          }));
        } else {
          const rows = await listSalesInvoices({ customer: partner.id, status: "posted", page_size: 200 });
          docs = (rows || []).map((r) => ({
            kind: "sales_invoice" as const,
            id: r.id,
            label: r.invoice_number || `#${r.id}`,
          }));
        }
        if (alive) setLinkDocs(docs);
      } catch (e: unknown) {
        if (alive) setLinkDocs([]);
        clientLogger.warn("credit_debit_note.link_docs_failed", { error: humanizeThrown(e, "") });
      }
    };
    void load();
    return () => {
      alive = false;
    };
  }, [partner]);

  // المستند المربوط المحفوظ يبقى خياراً ولو سُدِّد (القائمة المفتوحة لا تعرضه).
  const linkOptions = useMemo(() => {
    const saved = selectedNote?.linked_document;
    if (saved && !linkDocs.some((d) => linkKey(d) === linkKey(saved))) {
      return [{ kind: saved.kind, id: saved.id, label: saved.label }, ...linkDocs];
    }
    return linkDocs;
  }, [linkDocs, selectedNote]);

  const linked = linkOptions.find((d) => linkKey(d) === formLink) || null;

  // الحساب المقابل الافتراضي — من الخادم، ما لم يختره المستخدم بنفسه.
  useEffect(() => {
    if (!partner || counterChosen || readOnly) return;
    let alive = true;
    const link = linked ? { field: CREDIT_DEBIT_NOTE_LINK_FIELD[linked.kind], id: linked.id } : null;
    getCreditDebitNoteDefaultAccount(partner.id, link)
      .then((res) => {
        if (!alive) return;
        setFormCounter(res.account ? String(res.account.id) : "");
        setDefaultHint(res.account ? null : res.error || null);
      })
      .catch(() => {
        if (alive) setDefaultHint(null);
      });
    return () => {
      alive = false;
    };
  }, [partner, linked, counterChosen, readOnly]);

  // الرصيد قبل/بعد — `proposed_total` بإشارة أثر الإشعار على `open_balance`.
  const baseAmount = amount * (Number(formRate) || 1);
  useEffect(() => {
    if (!partner) {
      setBalance(null);
      return;
    }
    let alive = true;
    const delta = readOnly ? 0 : noteBalanceDelta(formType, creditor, baseAmount);
    getPartnerBalance({ partnerId: partner.id, proposedTotal: delta.toFixed(2) })
      .then((res) => {
        if (!alive) return;
        setBalance({
          before: Number(res.open_balance) || 0,
          after: Number(res.projected_balance) || 0,
          creditor: Boolean(res.is_creditor ?? creditor),
        });
      })
      .catch(() => {
        if (alive) setBalance(null);
      });
    return () => {
      alive = false;
    };
  }, [partner, formType, creditor, baseAmount, readOnly]);

  const partnerOptions = useMemo<KitAutocompleteOption[]>(
    () =>
      partners
        .filter((p) => !typeFilter || p.partner_type === typeFilter)
        .map((p) => ({ id: p.id, label: p.name, sub: partnerTypeLabel(p.partner_type) })),
    [partners, typeFilter],
  );

  const baseCurrencyId = currencies.find((c) => c.IsBaseCurrency)?.CurrencyID;
  const foreignCurrency = Boolean(formCurrency) && Number(formCurrency) !== baseCurrencyId;

  const handleSave = async () => {
    if (!formPartner || !(amount > 0)) {
      setErr("اختر الطرف واكتب مبلغاً أكبر من صفر.");
      return;
    }
    setSaving(true);
    setErr(null);
    const body: CreditDebitNoteBody = {
      note_type: formType,
      partner: Number(formPartner),
      note_date: formDate,
      amount: amount.toFixed(2),
      tax_amount: (Number(formTax) || 0).toFixed(2),
      currency: formCurrency ? Number(formCurrency) : null,
      exchange_rate: foreignCurrency ? formRate || "1" : "1",
      counter_account: formCounter ? Number(formCounter) : null,
      reason: formReason,
      related_invoice: null,
      related_purchase_invoice: null,
      related_clearance: null,
      related_local_shipment: null,
      related_shipment: null,
    };
    if (linked) {
      (body as Record<string, unknown>)[CREDIT_DEBIT_NOTE_LINK_FIELD[linked.kind]] = linked.id;
    }
    try {
      if (selectedId) {
        await updateCreditDebitNote(selectedId, body);
      } else {
        await createCreditDebitNote(body);
      }
      clientLogger.info("credit_debit_note.saved", { noteType: formType, creditor, linked: Boolean(linked) });
      resetForm();
      setShowForm(false);
      await loadAll();
      // ISSUE #118 §٥: حفظٌ صريحٌ ناجح ⇒ انتهت وظيفة المسودّة المحلية.
      void discardDraft();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل الحفظ"));
    } finally {
      setSaving(false);
    }
  };

  const runAction = async (n: CreditDebitNoteRow, action: "post" | "unpost" | "cancel" | "delete") => {
    const prompts = {
      post: { message: `ترحيل الإشعار ${n.note_number} على ${n.partner_name || "الطرف"}؟`, confirmText: "ترحيل", danger: false },
      unpost: { message: `إلغاء ترحيل الإشعار ${n.note_number}؟ يُحذف قيده ويعود مسودة.`, confirmText: "إلغاء الترحيل", danger: true },
      cancel: { message: `إلغاء الإشعار ${n.note_number}؟ لا يُرحَّل بعدها.`, confirmText: "إلغاء الإشعار", danger: true },
      delete: { message: `حذف مسودة الإشعار ${n.note_number} نهائياً؟`, confirmText: "حذف", danger: true },
    };
    if (!(await confirm({ title: "تأكيد", cancelText: "تراجع", ...prompts[action] }))) return;
    setBusyId(n.id);
    setErr(null);
    setNotice(null);
    try {
      if (action === "delete") {
        await deleteCreditDebitNote(n.id);
      } else {
        const res = await creditDebitNoteAction(n.id, action);
        if (res?.notice) setNotice(res.notice);
      }
      clientLogger.info("credit_debit_note.action", { action });
      if (selectedId === n.id) {
        setShowForm(false);
        setSelectedId(null);
      }
      await loadAll();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "تعذّر تنفيذ الإجراء"));
    } finally {
      setBusyId(null);
    }
  };

  const noteTypeLabel = (t: NoteType) => (t === "debit" ? "إشعار مدين" : "إشعار دائن");
  const money = (n: CreditDebitNoteRow) => `${formatMoney(n.amount)}${n.currency_code ? ` ${n.currency_code}` : ""}`;

  const printList = () => {
    const ok = printReport<CreditDebitNoteRow>({
      title: "إشعارات مدينة/دائنة",
      columns: [
        { header: "الرقم", value: (n) => n.note_number },
        { header: "النوع", value: (n) => noteTypeLabel(n.note_type) },
        { header: "الطرف", value: (n) => `${n.partner_name || ""} — ${partnerTypeLabel(n.partner_type)}` },
        { header: "المستند", value: (n) => (n.linked_document ? linkDocTitle(n.linked_document.kind, n.linked_document.label, term) : "") },
        { header: "التاريخ", value: (n) => formatDateLocalized(n.note_date) },
        { header: "المبلغ", value: (n) => money(n), numeric: true },
        { header: "الحالة", value: (n) => STATUS_LABEL[n.status] || n.status },
      ],
      rows: notes,
      emptyHint: "لا توجد إشعارات",
    });
    if (!ok) setErr("المتصفح منع نافذة الطباعة — اسمح بالنوافذ المنبثقة لهذا الموقع.");
  };

  const printNote = (n: CreditDebitNoteRow) => {
    const rows: { label: string; value: string }[] = [
      { label: "الطرف", value: `${n.partner_name || ""} — ${partnerTypeLabel(n.partner_type)}` },
      { label: "التاريخ", value: formatDateLocalized(n.note_date) },
      { label: "المبلغ", value: money(n) },
      ...(Number(n.tax_amount) ? [{ label: "منه ضريبة", value: formatMoney(n.tax_amount) }] : []),
      ...(n.linked_document
        ? [{ label: linkKindLabel(n.linked_document.kind, term), value: n.linked_document.label }]
        : []),
      ...(n.counter_account_code
        ? [{ label: "الحساب المقابل", value: `${n.counter_account_code} ${n.counter_account_name || ""}` }]
        : []),
      { label: "الحالة", value: STATUS_LABEL[n.status] || n.status },
    ];
    const ok = printReport({
      title: `${noteTypeLabel(n.note_type)} ${n.note_number}`,
      subtitle: noteExplanation(n.partner_name || "", n.note_type, Number(n.amount) || 0),
      columns: [
        { header: "البند", value: (r: { label: string; value: string }) => r.label },
        { header: "القيمة", value: (r: { label: string; value: string }) => r.value },
      ],
      rows,
      footer: n.reason ? `السبب: ${n.reason}` : undefined,
    });
    if (!ok) setErr("المتصفح منع نافذة الطباعة — اسمح بالنوافذ المنبثقة لهذا الموقع.");
  };

  useKitKeymap({
    F2: () => printList(),
    F5: () => loadAll(),
    F12: () => {
      if (showForm && !readOnly) void handleSave();
    },
    Escape: () => {
      setShowForm(false);
      setSelectedId(null);
    },
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => {
      if (!canCreate) return;
      resetForm();
      setShowForm(true);
    },
  });

  /* ISSUE #121: مسودّة محلية (IndexedDB، issue #118) — حمولةٌ خفيفة تعيد بناء النموذج. */
  const draftPayload = useMemo<NoteDraftPayload>(
    () => ({
      formType, formPartner, formDate, formAmount, formTax, formCurrency, formRate,
      formCounter, formLink, formReason,
    }),
    [formType, formPartner, formDate, formAmount, formTax, formCurrency, formRate, formCounter, formLink, formReason],
  );

  const onRestoreDraft = useCallback((restored: NoteDraftPayload) => {
    // مسودّةٌ من الشاشة القديمة (عميلٌ وحده) تحمل `formCustomer`.
    const legacy = restored as NoteDraftPayload & { formCustomer?: string };
    setFormType(restored.formType === "credit" ? "credit" : "debit");
    setFormPartner(restored.formPartner ?? legacy.formCustomer ?? "");
    setFormDate(restored.formDate || today());
    setFormAmount(restored.formAmount || "");
    setFormTax(restored.formTax || "");
    setFormCurrency(restored.formCurrency || "");
    setFormRate(restored.formRate || "1");
    setFormCounter(restored.formCounter || "");
    setCounterChosen(Boolean(restored.formCounter));
    setFormLink(restored.formLink || "");
    setFormReason(restored.formReason || "");
    setShowForm(true);
    setTouched(true);
  }, []);

  const draftApi = useDocumentDraft<NoteDraftPayload>({
    docType: "credit_debit_note",
    docId: selectedId,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    isPosted: readOnly,
    docUpdatedAt: selectedNote?.updated_at ?? null,
  });
  const { draftSavedAt, draftSaveFailed, discardDraft } = draftApi;

  /* ISSUE #120: الحارسُ يعترض المغادرةَ فقط إن فشل الحفظُ المحلّيّ فعلاً. */
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

  const handleUndoDraft = useCallback(() => {
    const found = selectedId != null ? notes.find((n) => n.id === selectedId) : undefined;
    if (found) loadIntoForm(found);
    else resetForm();
    setTouched(false);
    void discardDraft();
  }, [selectedId, notes, discardDraft, loadIntoForm, resetForm]);

  const openNew = () => {
    resetForm();
    setShowForm(true);
  };

  return (
    <div className="flex min-h-[calc(100vh-5rem)] flex-col">
      <KitDocumentShell
        title="إشعارات مدينة/دائنة"
        state={selectedNote ? `إشعار ${selectedNote.note_number}` : "إشعارات"}
        nav={nav}
        actions={[
          ...(canCreate
            ? [{ key: "new", label: "إشعار جديد", icon: <Plus />, onClick: openNew }]
            : []),
          { key: "reload", label: "تحديث", icon: <RefreshCw />, onClick: () => loadAll(), separatorBefore: true },
          { key: "print", label: "طباعة", icon: <Printer />, onClick: printList },
        ]}
        header={<></>}
        status={
          <>
            <span className="ktra-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="ktra-status-item">{notes.length} إشعار</span>
            {showForm && draftSavedAt && (
              <span className="ktra-status-item" data-testid="draft-saved-indicator">
                مسودة محلية <b>حُفظ {formatTimeValue(draftSavedAt)}</b>
              </span>
            )}
          </>
        }
      >
        <div className="ktra-bg-field h-full space-y-4 overflow-auto p-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold">إشعارات مدينة/دائنة</h2>
              <p className="text-xs ktra-text-soft">
                لأيّ طرف: المدين يزيد ما عليه أو ينقص ما له، والدائن عكسه.
              </p>
            </div>
            {canCreate && (
              <button onClick={openNew} className="flex items-center gap-2 px-4 py-2 ktra-btn-primary">
                <Plus className="h-4 w-4" /> إشعار جديد
              </button>
            )}
          </div>

          {err && <div className="rounded-lg p-3 ktra-bg-panel ktra-text-state">{err}</div>}
          {notice && <div className="rounded-lg p-3 text-sm ktra-bg-panel">{notice}</div>}

          {loading ? (
            <KitSpinner />
          ) : (
            <div className="overflow-x-auto rounded-lg shadow ktra-bg-field">
              <table className="w-full text-sm">
                <thead className="ktra-bg-panel">
                  <tr>
                    <th className="p-3 text-right">رقم الإشعار</th>
                    <th className="p-3 text-right">النوع</th>
                    <th className="p-3 text-right">الطرف</th>
                    <th className="p-3 text-right">المستند</th>
                    <th className="p-3 text-right">التاريخ</th>
                    <th className="p-3 text-right">المبلغ</th>
                    <th className="p-3 text-right">الحالة</th>
                    <th className="p-3 text-right">إجراءات</th>
                  </tr>
                </thead>
                <tbody>
                  {notes.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="p-6 text-center ktra-text-soft">لا توجد إشعارات</td>
                    </tr>
                  ) : (
                    notes.map((n) => (
                      <tr key={n.id} className="border-t hover:ktra-bg-panel">
                        <td className="p-3 font-mono">
                          <button className="ktra-text-accent hover:underline" onClick={() => loadIntoForm(n)}>
                            {n.note_number}
                          </button>
                        </td>
                        <td className="p-3">
                          <span
                            className={`rounded px-2 py-0.5 text-xs ${
                              n.note_type === "debit" ? "bg-amber-50 text-amber-800" : "bg-green-100 text-green-700"
                            }`}
                          >
                            {noteTypeLabel(n.note_type)}
                          </span>
                        </td>
                        <td className="p-3">
                          {n.partner_name || "—"}
                          <span className="ms-1 text-xs ktra-text-soft">{partnerTypeLabel(n.partner_type)}</span>
                        </td>
                        <td className="p-3 text-xs">
                          {n.linked_document
                            ? linkDocTitle(n.linked_document.kind, n.linked_document.label, term)
                            : "—"}
                        </td>
                        <td className="p-3">{formatDateLocalized(n.note_date)}</td>
                        <td className="p-3 font-mono">
                          {money(n)}
                          {n.status === "posted" && n.settles && Number(n.unallocated_amount) > 0 && (
                            <span className="block text-xs text-[var(--ktra-warn)]">
                              تحت الحساب {formatMoney(n.unallocated_amount)}
                            </span>
                          )}
                        </td>
                        <td className="p-3">
                          <span className={`rounded px-2 py-0.5 text-xs ${STATUS_CLASS[n.status] || STATUS_CLASS.draft}`}>
                            {STATUS_LABEL[n.status] || n.status}
                          </span>
                        </td>
                        <td className="p-3">
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            {busyId === n.id && <Loader2 className="h-3 w-3 animate-spin" />}
                            {n.status === "draft" && canPost && (
                              <button onClick={() => runAction(n, "post")} className="flex items-center gap-1 text-green-700 hover:underline">
                                <CheckCircle className="h-3 w-3" /> ترحيل
                              </button>
                            )}
                            {n.status === "posted" && n.settles && canPost && (
                              <button onClick={() => setAllocNote(n)} className="flex items-center gap-1 ktra-text-accent hover:underline">
                                <Split className="h-3 w-3" /> توزيع
                              </button>
                            )}
                            {n.status === "posted" && canUnpost && (
                              <button onClick={() => runAction(n, "unpost")} className="flex items-center gap-1 ktra-text-state hover:underline">
                                <Undo2 className="h-3 w-3" /> إلغاء الترحيل
                              </button>
                            )}
                            {n.status === "draft" && canCreate && (
                              <>
                                <button onClick={() => runAction(n, "cancel")} className="flex items-center gap-1 ktra-text-soft hover:underline">
                                  <Ban className="h-3 w-3" /> إلغاء
                                </button>
                                <button onClick={() => runAction(n, "delete")} className="flex items-center gap-1 ktra-text-state hover:underline">
                                  <Trash2 className="h-3 w-3" /> حذف
                                </button>
                              </>
                            )}
                            <button onClick={() => printNote(n)} className="flex items-center gap-1 ktra-text-accent hover:underline">
                              <Printer className="h-3 w-3" /> طباعة
                            </button>
                            <ShareRowButton
                              docType="credit_debit_note"
                              docId={n.id}
                              docLabel={`إشعار ${n.note_number}`}
                              partyName={n.partner_name || undefined}
                              className="text-blue-600 hover:underline text-xs"
                            />
                            {n.journal && <span className="ktra-text-soft">قيد #{n.journal}</span>}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {showForm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-xl p-6 shadow-lg ktra-bg-field">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-lg font-bold">
                    {selectedNote
                      ? `${noteTypeLabel(selectedNote.note_type)} ${selectedNote.note_number}${readOnly ? ` — ${STATUS_LABEL[selectedNote.status]}` : ""}`
                      : "إشعار جديد"}
                  </h3>
                  <button onClick={() => setShowForm(false)} className="rounded p-1 hover:ktra-bg-panel" aria-label="إغلاق">
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <DocumentDraftBanners draft={draftApi} onApplyDraft={onRestoreDraft} onUndo={handleUndoDraft} isTouched={touched} />

                <fieldset disabled={readOnly} className="grid grid-cols-2 gap-3">
                  <label className="block">
                    <span className="mb-1 block text-xs font-medium">نوع الإشعار</span>
                    <select
                      aria-label="نوع الإشعار"
                      value={formType}
                      onChange={(e) => { markTouched(); setFormType(e.target.value as NoteType); }}
                      className="w-full rounded border p-1.5 text-sm"
                    >
                      <option value="debit">إشعار مدين</option>
                      <option value="credit">إشعار دائن</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs font-medium">التاريخ</span>
                    <input
                      type="date"
                      value={formDate}
                      onChange={(e) => { markTouched(); setFormDate(e.target.value); }}
                      className="w-full rounded border p-1.5 text-sm"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium">نوع الطرف</span>
                    <select
                      aria-label="نوع الطرف"
                      value={typeFilter}
                      onChange={(e) => setTypeFilter(e.target.value)}
                      className="w-full rounded border p-1.5 text-sm"
                    >
                      <option value="">كل الأطراف</option>
                      {PARTY_TYPES.map((t) => <option key={t} value={t}>{partnerTypeLabel(t)}</option>)}
                    </select>
                  </label>
                  <div className="block">
                    <span className="mb-1 block text-xs font-medium">الطرف *</span>
                    <KitAutocomplete
                      value={partner ? `${partner.name} — ${partnerTypeLabel(partner.partner_type)}` : ""}
                      options={partnerOptions}
                      maxResults={12}
                      placeholder="اكتب اسم الطرف…"
                      disabled={readOnly}
                      onPick={(id) => {
                        markTouched();
                        setFormPartner(String(id));
                        setFormLink("");
                        setCounterChosen(false);
                      }}
                    />
                  </div>

                  {partner && (
                    <div
                      data-testid="note-explanation"
                      className={`col-span-2 rounded border p-3 text-sm ${
                        formType === "debit" ? "border-amber-200 bg-amber-50 text-amber-800" : "border-green-200 bg-green-50 text-green-800"
                      }`}
                    >
                      <div className="font-bold">{noteExplanation(partner.name, formType, amount)}</div>
                      <div className="text-xs">{noteMeaning(formType, creditor)}</div>
                      {balance && (
                        <div className="mt-2 flex flex-wrap gap-4 text-xs" data-testid="note-balance">
                          <span>الرصيد الآن: <b>{partyBalancePhrase(balance.before, balance.creditor)}</b></span>
                          {!readOnly && (
                            <span>بعد الإشعار: <b>{partyBalancePhrase(balance.after, balance.creditor)}</b></span>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium">المبلغ (شاملاً الضريبة) *</span>
                    <input
                      type="number" step="0.01" min="0"
                      value={formAmount}
                      onChange={(e) => { markTouched(); setFormAmount(e.target.value); }}
                      className="w-full rounded border p-1.5 font-mono text-sm"
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-xs font-medium">
                      منه ضريبة (اختياري) — {creditor ? "مدخلات" : "مخرجات"}
                    </span>
                    <input
                      type="number" step="0.01" min="0"
                      value={formTax}
                      onChange={(e) => { markTouched(); setFormTax(e.target.value); }}
                      className="w-full rounded border p-1.5 font-mono text-sm"
                    />
                  </label>

                  <label className="block">
                    <span className="mb-1 block text-xs font-medium">العملة</span>
                    <select
                      aria-label="العملة"
                      value={formCurrency}
                      onChange={(e) => { markTouched(); setFormCurrency(e.target.value); }}
                      className="w-full rounded border p-1.5 text-sm"
                    >
                      <option value="">العملة الأساسية</option>
                      {currencies.map((c) => <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>)}
                    </select>
                  </label>
                  {foreignCurrency ? (
                    <label className="block">
                      <span className="mb-1 block text-xs font-medium">سعر الصرف</span>
                      <input
                        type="number" step="0.000001" min="0"
                        value={formRate}
                        onChange={(e) => { markTouched(); setFormRate(e.target.value); }}
                        className="w-full rounded border p-1.5 font-mono text-sm"
                      />
                      <span className="text-[11px] ktra-text-soft">بالعملة الأساسية: {formatMoney(baseAmount)}</span>
                    </label>
                  ) : <div />}

                  <label className="col-span-2 block">
                    <span className="mb-1 block text-xs font-medium">ربط بمستند (اختياري)</span>
                    <select
                      aria-label="المستند المربوط"
                      value={formLink}
                      onChange={(e) => { markTouched(); setFormLink(e.target.value); setCounterChosen(false); }}
                      className="w-full rounded border p-1.5 text-sm"
                      disabled={readOnly || !partner}
                    >
                      <option value="">بلا ربط — يبقى رصيداً عاماً على الطرف</option>
                      {linkOptions.map((d) => (
                        <option key={linkKey(d)} value={linkKey(d)}>
                          {linkDocTitle(d.kind, d.label, term)}
                          {d.remaining != null ? ` — متبقٍّ ${formatMoney(d.remaining)}` : ""}
                        </option>
                      ))}
                    </select>
                    <span className="text-[11px] ktra-text-soft">
                      {linked && linked.kind !== "sales_invoice"
                        ? "الإشعار المرحَّل يُطفئ متبقّي هذا المستند (المدين) أو يزيد مستحقّه (الدائن)."
                        : linked
                          ? `ربط ${term("doc.sales_invoice")} مرجعٌ فقط — الإشعار يبقى في رصيد العميل.`
                          : ""}
                    </span>
                  </label>

                  <label className="col-span-2 block">
                    <span className="mb-1 block text-xs font-medium">الحساب المقابل</span>
                    <AccountTreeField
                      accounts={accounts}
                      value={formCounter ? Number(formCounter) : null}
                      onChange={(id) => { markTouched(); setFormCounter(id ? String(id) : ""); setCounterChosen(Boolean(id)); }}
                      isSelectable={isCounterSelectable}
                      title="اختيار الحساب المقابل"
                      placeholder="— الافتراضي حسب الطرف —"
                      disabled={readOnly}
                    />
                    {defaultHint && <span className="text-[11px] ktra-text-state">{defaultHint}</span>}
                  </label>

                  <label className="col-span-2 block">
                    <span className="mb-1 block text-xs font-medium">السبب / البيان</span>
                    <textarea
                      data-testid="note-reason"
                      value={formReason}
                      onChange={(e) => { markTouched(); setFormReason(e.target.value); }}
                      className="w-full rounded border p-2 text-sm"
                      rows={3}
                    />
                  </label>
                </fieldset>

                <div className="mt-4 flex justify-end gap-3">
                  <button onClick={() => setShowForm(false)} className="rounded-lg px-4 py-2 ktra-bg-panel hover:ktra-bg-grid-head">
                    إغلاق
                  </button>
                  {!readOnly && canCreate && (
                    <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 ktra-btn-primary disabled:opacity-50">
                      {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                      {saving ? "جاري الحفظ..." : "حفظ مسودة"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </KitDocumentShell>
      {allocNote && (
        <NoteAllocationModal
          noteId={allocNote.id}
          partnerLabel={allocNote.partner_name || "الطرف"}
          onClose={() => setAllocNote(null)}
          onSaved={() => {
            setAllocNote(null);
            void loadAll();
          }}
        />
      )}
    </div>
  );
};
