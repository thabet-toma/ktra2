import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { accountingApi } from "../../services/accountingApi";
import { postCustomerPayment } from "../../services/salesApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { formatMoney } from "../../utils/formatNumber";
import type {
  AccountingPartner,
  BankAccountDto,
  ChequeBatchRejection,
  ChequeDepositSlip,
  ChequeDto,
  ChequeMovementDto,
  ChequeSourceDocument,
} from "../../types/accounting";
import { printReport } from "../../utils/printReport";
import { ChequeWalletPanel } from "./ChequeWalletPanel";
import { ChequeMaturityPanel } from "./ChequeMaturityPanel";
import { NewPaymentModal } from "../sales/SalesCustomerPaymentsPage";
import { NewSupplierPaymentModal } from "../sales/NewSupplierPaymentModal";
import {
  AseelDocumentShell,
  AseelDenseTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, DenseColumn } from "../aseel";
import { Plus, X, ArrowRightLeft, Loader2, Upload, Banknote, Printer } from "lucide-react";
import OfflineGuard from "../offline/OfflineGuard";
import { formatDateLocalized, formatDateTimeValue } from "../../utils/formatDate";

const DIRECTIONS = [
  { v: "", l: "الكل" },
  { v: "Incoming", l: "وارد" },
  { v: "Outgoing", l: "صادر" },
];

/**
 * CHQ-4: الحالات التي ما تزال الورقة فيها «مفتوحة» — لها استحقاق ينتظر.
 * مرآة `CHEQUE_OPEN_STATUSES` في `accounting/services.py`؛ تُستعمل للتلوين
 * وحده (لا لقرار مالي) فبقاؤها هنا لا يخلق مصدر حقيقة ثانياً للقيود.
 */
const OPEN_CHEQUE_STATUSES = new Set([
  "Draft", "Received", "Under_Collection", "Bounced",
]);

export const AccountingChequesPage: React.FC = () => {
  const navigate = useNavigate();
  const [rows, setRows] = useState<ChequeDto[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  // CHQ-4: التظهير يُسدَّد به مورد — قيدُه مدين ذممه، فالقائمة موردون لا كل الأطراف.
  const [suppliers, setSuppliers] = useState<AccountingPartner[]>([]);
  // T-BANKS: حساب الإيداع/الصرف يُختار من حسابات الشركة عند التحويل.
  const [bankAccounts, setBankAccounts] = useState<BankAccountDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const toast = useToast();
  // الحذف والتحويل يولّدان حركة محاسبية على الشيك؛ قفل أثناء التنفيذ يمنع
  // إرسال الطلب مرتين، وتأكيد النجاح يمنع ظنّ المستخدم أن شيئاً لم يحدث.
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();
  // T-CHQ3: أي سند يُفتح للإدخال — سند قبض للوارد وسند صرف للصادر.
  const [voucher, setVoucher] = useState<"Incoming" | "Outgoing" | null>(null);

  // Filters — تاريخ الاستحقاق + شريك + حالة + اتجاه (per N3-T4 spec).
  // CHQ-4: صارت كلها خادمية — كانت تُطبَّق على جدولٍ مسحوبٍ بكامله في المتصفح.
  const [filterDirection, setFilterDirection] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDueFrom, setFilterDueFrom] = useState("");
  const [filterDueTo, setFilterDueTo] = useState("");
  const [filterPartner, setFilterPartner] = useState("");
  // CHQ-4: رقم الشيك هو المفتاح الطبيعي للبحث في أي نظام شيكات — ولم يكن موجوداً.
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [ordering, setOrdering] = useState("-due_date");
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [activeTab, setActiveTab] = useState("list");
  const PAGE_SIZE = 50;

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  // أي تغيير في الفلاتر يعيدنا إلى الصفحة الأولى — البقاء على صفحة 7 بعد
  // تضييق النتائج إلى صفحتين يعطي جدولاً فارغاً بلا سبب ظاهر.
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, filterDirection, filterStatus, filterDueFrom, filterDueTo,
      filterPartner, ordering]);

  // Transfer dialog — task11 R2-A3: الحركة (وليست الحالة) هي ما يُرسل للسيرفر،
  // فيمر التحويل بآلة الانتقالات ويُرحَّل القيد المحاسبي المرافق.
  const [transferCheque, setTransferCheque] = useState<ChequeDto | null>(null);
  const [newMovement, setNewMovement] = useState("");
  const [transferDate, setTransferDate] = useState(new Date().toISOString().split("T")[0]);
  const [transferNotes, setTransferNotes] = useState("");
  const [transferBankAccount, setTransferBankAccount] = useState("");
  // CHQ-4: المستفيد من التظهير — يُطلب فقط حين تعلن الحركة `requires_endorsee`.
  const [transferEndorsee, setTransferEndorsee] = useState("");
  // T-CHQ2: مسار الشيك — الحركات كانت تُسجَّل في الخادم ولا تُعرض في أي مكان.
  const [movements, setMovements] = useState<ChequeMovementDto[]>([]);
  const [walletKey, setWalletKey] = useState(0);

  // CHQ-4: إيداع الصباح حزمةٌ لا ورقة — التحديد المتعدد ونافذة الدفعة وقسيمتها.
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [depositOpen, setDepositOpen] = useState(false);
  const [depositBank, setDepositBank] = useState("");
  const [depositDate, setDepositDate] = useState(new Date().toISOString().split("T")[0]);
  const [depositNotes, setDepositNotes] = useState("");
  const [depositRejected, setDepositRejected] = useState<ChequeBatchRejection[]>([]);

  // CHQ-4: لا جدول انتقالات ولا جدول تسميات في الواجهة بعد اليوم. الحركات
  // المتاحة وتسمياتها وما تطلبه من مدخلات تصل مع كل شيك (`allowed_movements`)،
  // فحالةٌ جديدة في الخادم تظهر هنا، وحركةٌ مُنعت هناك تختفي من الشاشة بدل أن
  // تبقى زرّاً يعطي 400.
  const moves = transferCheque?.allowed_movements ?? [];
  const selectedMove = moves.find((m) => m.value === newMovement) || null;

  // CHQ-4: حركةٌ تحتاج بنكاً على ورقةٍ نعرف أين أُودعت ⇒ نفتح على بنك إيداعها.
  // اقتراحٌ لا قفل: يُملأ ما دام الحقل فارغاً، ويبقى للمستخدم تغييره.
  useEffect(() => {
    if (!transferCheque || !selectedMove?.requires_bank_account) return;
    if (newMovement === "deposit" || transferBankAccount) return;
    const suggested = transferCheque.deposit_bank_account;
    if (suggested) setTransferBankAccount(String(suggested));
  }, [transferCheque, selectedMove, newMovement, transferBankAccount]);

  // CHQ-4: تسمية الحالة بدلالة الاتجاه — تُقرأ من الشيكات المحمّلة نفسها
  // (`status_label` من الخادم)، فالمحفظة والقائمة والنافذة تنطق بتسمية واحدة.
  // CHQ-4: تُراكَم عبر التحميلات ولا تُبنى من الصفحة الحالية وحدها. بعد أن صارت
  // الفلترة خادمية، اختيارُ حالةٍ يجعل الصفحة كلها من تلك الحالة — فبناءُ
  // المنسدلة من الصفوف المعروضة كان سيُفقرها إلى خيارٍ واحد ويحبس المستخدم فيه.
  const [statusLabels, setStatusLabels] = useState<Map<string, string>>(new Map());
  useEffect(() => {
    setStatusLabels((prev) => {
      let changed = false;
      const next = new Map(prev);
      for (const r of rows) {
        const key = `${r.direction}|${r.status}`;
        if (r.status_label && next.get(key) !== r.status_label) {
          next.set(key, r.status_label);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [rows]);

  const statusLabelFor = useCallback(
    (direction: string, status: string) =>
      statusLabels.get(`${direction}|${status}`) || status,
    [statusLabels],
  );

  // فلتر الحالة يعرض الحالات الموجودة فعلاً في هذا الاتجاه — بتسمياتها الصحيحة.
  // حالةٌ مختارة لم تعد ضمنها تبقى معروضة كي لا يتغيّر فلتر المستخدم من تحته.
  const statusOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const [key, label] of statusLabels) {
      const [direction, status] = key.split("|");
      if (filterDirection && direction !== filterDirection) continue;
      if (!seen.has(status)) seen.set(status, label);
    }
    if (filterStatus && !seen.has(filterStatus)) {
      seen.set(filterStatus, statusLabelFor(filterDirection || "Incoming", filterStatus));
    }
    return [...seen.entries()].map(([v, l]) => ({ v, l }));
  }, [statusLabels, filterDirection, filterStatus, statusLabelFor]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      // CHQ-4: القوائم المساندة كانت تُبتلع أخطاؤها بـ`catch(() => [])` صامتاً،
      // فتظهر منسدلة البنوك فارغةً بلا سبب معروف. الفشل يبقى غير قاتل (الشيكات
      // تُعرض) لكنه يُقال الآن: تحذير في الكونسول وسطر تنبيه للمستخدم.
      const missing: string[] = [];
      const soft = async <T,>(label: string, p: Promise<T>): Promise<T | []> => {
        try {
          return await p;
        } catch (e) {
          console.warn(`تعذّر تحميل ${label} في شاشة الشيكات`, e);
          missing.push(label);
          return [];
        }
      };
      const [ch, pr, ba, sup] = await Promise.all([
        accountingApi.getChequesPage({
          search: debouncedSearch,
          status: filterStatus,
          direction: filterDirection,
          partner: filterPartner,
          due_from: filterDueFrom,
          due_to: filterDueTo,
          ordering,
          page,
          page_size: PAGE_SIZE,
        }),
        soft("الأطراف", accountingApi.getPartners()),
        soft("الحسابات البنكية", accountingApi.getBankAccounts({ activeOnly: true })),
        soft("الموردين", accountingApi.getPartners("Supplier")),
      ]);
      setRows(ch.results);
      setTotalCount(ch.count);
      setPartners(pr as AccountingPartner[]);
      setBankAccounts(ba as BankAccountDto[]);
      setSuppliers(sup as AccountingPartner[]);
      if (missing.length) {
        setErr(`تعذّر تحميل: ${missing.join("، ")} — بعض القوائم ستظهر فارغة.`);
      }
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحميل"));
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, filterStatus, filterDirection, filterPartner,
      filterDueFrom, filterDueTo, ordering, page]);

  useEffect(() => {
    load();
  }, [load]);

  /** CHQ-4: فتح المستند المصدر في شاشته — الشيك ورقةٌ داخل سند، لا مستند وحده. */
  const openSourceDocument = useCallback(
    (doc: ChequeSourceDocument) => {
      const path = {
        customer_payment: "/sales/customer-payments",
        supplier_payment: "/supplier-payments",
        sales_invoice: `/sales/invoices/${doc.id}`,
        purchase_invoice: `/purchase-invoices/${doc.id}`,
      }[doc.type];
      navigate(path);
    },
    [navigate],
  );

  /** CHQ-4: ترحيل سند الشيك من هنا — كان الطريق مسدوداً: ورقةٌ بلا حركة
   *  ممكنة، ولا شيء في الشاشة يقول أي سند يُرحَّل ولا أين هو. الفواتير
   *  مستثناة عمداً: ترحيلها يمسّ المخزون والضريبة فلا يُطلق من شاشة شيكات. */
  const postSourceDocument = useCallback(
    async (doc: ChequeSourceDocument) => {
      if (busy) return;
      if (doc.type === "sales_invoice" || doc.type === "purchase_invoice") {
        openSourceDocument(doc);
        return;
      }
      // `ConfirmDialog` افتراضه `danger` فيكتب «حذف» على زرّه بالأحمر — نصٌّ
      // كاذب ومخيف لعمليةٍ تُدخل مستنداً الدفاتر. الترحيل تأكيدٌ عاديّ.
      if (!(await confirm({
        title: "ترحيل السند",
        message: `ترحيل ${doc.label} ${doc.number}؟ سيدخل الشيك الدفاتر بترحيله.`,
        confirmText: "ترحيل",
        danger: false,
      }))) return;
      setBusy(true);
      setErr(null);
      try {
        if (doc.type === "customer_payment") await postCustomerPayment(doc.id);
        else await purchaseInvoiceApi.postSupplierPayment(doc.id);
        toast(`تم ترحيل ${doc.label} ${doc.number}`, "success");
        setWalletKey((k) => k + 1);
        await load();
      } catch (e: unknown) {
        setErr(humanizeThrown(e, "فشل ترحيل السند"));
      } finally {
        setBusy(false);
      }
    },
    [busy, confirm, load, openSourceDocument, toast],
  );

  /** CHQ-4: ما يقبله الخادم في دفعة إيداع — وارد، مستلَم، وسنده مرحّل. الشرط
   *  نفسه المكتوب في `deposit_cheques_batch`، فلا يُعرض مربع اختيار لورقة
   *  سيرفضها الخادم ويُبطل الدفعة كلها. */
  const canDeposit = useCallback(
    (r: ChequeDto) =>
      r.direction === "Incoming" && r.status === "Received" && !r.needs_document_post,
    [],
  );

  const printDepositSlip = useCallback((slip: ChequeDepositSlip) => {
    const bank = slip.bank_account;
    const opened = printReport({
      title: "قسيمة إيداع شيكات",
      subtitle: bank ? `${bank.bank_name} — ${bank.name}` : undefined,
      meta: [
        { label: "تاريخ الإيداع", value: formatDateLocalized(slip.slip_date) || slip.slip_date },
        ...(bank ? [{ label: "رقم الحساب", value: bank.account_number || "—" }] : []),
        { label: "عدد الشيكات", value: String(slip.cheques.length) },
        { label: "مرجع الدفعة", value: slip.batch_ref },
        ...(slip.notes ? [{ label: "ملاحظات", value: slip.notes }] : []),
      ],
      columns: [
        { header: "رقم الشيك", value: (c) => c.cheque_number },
        { header: "البنك المسحوب عليه", value: (c) => c.drawer_bank },
        { header: "الاسم على الشيك", value: (c) => c.payee_name || c.partner_name },
        { header: "الاستحقاق", value: (c) => formatDateLocalized(c.due_date) || c.due_date },
        { header: `المبلغ (${slip.currency_code})`, value: (c) => formatMoney(c.amount), numeric: true },
      ],
      rows: slip.cheques,
      totals: ["الإجمالي", "", "", "", formatMoney(slip.total)],
      footer: "توقيع المستلم: ____________________",
    });
    if (!opened) {
      toast("تعذّر فتح نافذة الطباعة — اسمح بالنوافذ المنبثقة لطباعة القسيمة.", "error");
    }
  }, [toast]);

  const doDepositBatch = async () => {
    if (busy || selectedIds.size === 0) return;
    setBusy(true);
    setErr(null);
    setDepositRejected([]);
    try {
      const result = await accountingApi.depositChequesBatch({
        cheque_ids: [...selectedIds],
        bank_account: depositBank ? parseInt(depositBank, 10) : null,
        movement_date: depositDate,
        notes: depositNotes,
      });
      setDepositOpen(false);
      setSelectedIds(new Set());
      setDepositNotes("");
      setWalletKey((k) => k + 1);
      toast(`تم إيداع ${result.deposited_count} شيكاً`, "success");
      printDepositSlip(result.slip);
      await load();
    } catch (e: unknown) {
      // الدفعة ذرّية: الرفض يعني أن لا شيء أُودع — والقائمة تسمّي ما يُستثنى.
      const body = (e as { data?: { rejected?: ChequeBatchRejection[] } })?.data;
      if (body?.rejected?.length) setDepositRejected(body.rejected);
      setErr(humanizeThrown(e, "تعذّر إيداع الدفعة"));
    } finally {
      setBusy(false);
    }
  };

  const doTransfer = async () => {
    if (!transferCheque || !newMovement || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.transferCheque(transferCheque.id, {
        movement_type: newMovement,
        movement_date: transferDate,
        notes: transferNotes,
        ...(selectedMove?.requires_bank_account && transferBankAccount
          ? { bank_account: parseInt(transferBankAccount, 10) } : {}),
        ...(selectedMove?.requires_endorsee && transferEndorsee
          ? { endorsed_to: parseInt(transferEndorsee, 10) } : {}),
      });
      setTransferCheque(null);
      setTransferNotes("");
      setTransferBankAccount("");
      setTransferEndorsee("");
      setWalletKey((k) => k + 1);
      toast("تم تحويل حالة الشيك", "success");
      await load();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحويل"));
    } finally {
      setBusy(false);
    }
  };

  // CHQ-4: الفلترة كلها في الخادم — ما يصل هو ما يُعرض. كانت تُكرَّر هنا على
  // جدولٍ مسحوبٍ بكامله، فبحثٌ لا يجد شيئاً في الصفحة يبدو كأن لا نتيجة له.
  const filteredRows = rows;

  const getPartnerName = (id: number | null | undefined) => {
    if (!id) return "—";
    const p = partners.find((x) => x.id === id);
    return p?.name || String(id);
  };

  // CHQ-4: أوراق هذه الصفحة القابلة للإيداع — عليها وحدها يعمل «تحديد الكل».
  const depositableRows = filteredRows.filter(canDeposit);
  const selectedRows = rows.filter((r) => selectedIds.has(r.id));
  const selectedTotal = selectedRows.reduce(
    (sum, r) => sum + (parseFloat(r.amount) || 0), 0,
  );

  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  /** CHQ-4: إلحاح الورقة — «متأخر» متجاوزٌ استحقاقه وما زال مفتوحاً، و«قريب»
   *  يستحق خلال أسبوع. الحالات المغلقة (محصَّل، مسوّى…) لا إلحاح لها. */
  const dueUrgency = (r: ChequeDto): "overdue" | "soon" | null => {
    if (!r.due_date) return null;
    if (!OPEN_CHEQUE_STATUSES.has(r.status)) return null;
    const today = new Date().toISOString().split("T")[0];
    if (r.due_date < today) return "overdue";
    const weekAhead = new Date(Date.now() + 7 * 86400000).toISOString().split("T")[0];
    return r.due_date <= weekAhead ? "soon" : null;
  };

  const columns: DenseColumn<ChequeDto>[] = [
    // CHQ-4: مربع الاختيار على الورقة المؤهَّلة وحدها — الدفعة ذرّية، فورقةٌ
    // غير مؤهَّلة في التحديد تُبطل الدفعة كلها لا نفسها.
    {
      key: "select", header: "", width: "34px",
      render: (r) => (
        canDeposit(r) ? (
          <input
            type="checkbox"
            data-testid="cheque-select"
            aria-label={`تحديد الشيك ${r.cheque_number} للإيداع`}
            checked={selectedIds.has(r.id)}
            onClick={(e) => e.stopPropagation()}
            onChange={() => toggleSelected(r.id)}
          />
        ) : null
      ),
    },
    { key: "cheque_number", header: "رقم الشيك", width: "100px", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.cheque_number}</span> },
    { key: "account_number", header: "حساب الساحب", width: "120px", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.account_number || "—"}</span> },
    { key: "bank_name", header: "البنك المسحوب عليه", width: "120px", render: (r) => r.bank_display || r.bank_name || "—" },
    // T-CHQ3: الاسم المكتوب على الورقة (صاحب الشيك في الوارد / المستفيد في الصادر).
    { key: "payee_name", header: "الاسم على الشيك", width: "140px", render: (r) => r.payee_name || "—" },
    { key: "bank_branch", header: "الفرع", width: "100px", render: (r) => r.bank_branch_display || r.bank_branch || "—" },
    // CHQ-4: أين الورقة الآن — البنك الذي أُودعت فيه. الدفاتر لا تحمل الجواب
    // (قيد الإيداع 1107 ÷ 1109 بحسابٍ واحد)، فهذا العمود هو مصدره الوحيد.
    {
      key: "deposit_bank", header: "بنك الإيداع", width: "130px",
      render: (r) => r.deposit_bank_account_name || "—",
    },
    { key: "amount", header: "المبلغ", width: "110px", numeric: true, sortable: true, render: (r) => formatMoney(r.amount) },
    // CHQ-4: شيكٌ استحقاقه أمس كان يبدو كشيكٍ استحقاقه بعد سنة — نصٌّ رماديّ
    // واحد للجميع. المتأخر والمستحق قريباً هما كل ما يُنظر إليه في هذه القائمة.
    {
      key: "due_date", header: "تاريخ الاستحقاق", width: "130px", sortable: true,
      render: (r) => {
        const urgency = dueUrgency(r);
        const text = formatDateLocalized(r.due_date) || "—";
        if (!urgency) return text;
        return (
          <span
            className={urgency === "overdue"
              ? "font-semibold text-[var(--color-danger,#dc2626)]"
              : "text-[var(--color-warning,#b45309)]"}
            data-testid={`cheque-due-${urgency}`}
            title={urgency === "overdue" ? "تجاوز تاريخ استحقاقه" : "يستحق خلال أسبوع"}
          >
            {text} {urgency === "overdue" ? "· متأخر" : "· قريب"}
          </span>
        );
      },
    },
    { key: "issue_date", header: "تاريخ الإصدار", width: "110px", render: (r) => formatDateLocalized(r.issue_date) || "—" },
    { key: "partner", header: "الشريك", width: "140px", render: (r) => getPartnerName(r.partner) },
    {
      key: "account", header: "الحساب", width: "110px",
      render: (r) => {
        const acc = (r as ChequeDto & { account_code?: string; account_name?: string });
        return acc.account_code ? `${acc.account_code}${acc.account_name ? ' — ' + acc.account_name : ''}` : "—";
      },
    },
    {
      key: "direction", header: "الاتجاه",
      render: (r) => (
        <span style={{
          padding: "2px 8px", borderRadius: "12px",
          background: r.direction === "Incoming" ? "var(--color-success,#22c55e)15" : "var(--color-primary,#3b82f6)15",
          color: r.direction === "Incoming" ? "var(--color-success,#16a34a)" : "var(--color-primary,#2563eb)",
          fontSize: "0.75rem",
        }}>
          {r.direction === "Incoming" ? "وارد" : "صادر"}
        </span>
      ),
    },
    {
      key: "status", header: "الحالة",
      render: (r) => (
        <span>
          {r.status_label || r.status}
          {r.needs_document_post && (
            <span
              className="mr-1 rounded px-1.5 py-0.5 text-[0.7rem] bg-amber-100 text-amber-800"
              title="الورقة خارج الدفاتر حتى يُرحَّل سندها"
              data-testid="cheque-awaiting-post"
            >
              بانتظار ترحيل السند
            </span>
          )}
        </span>
      ),
    },
    // CHQ-4: الشيك ورقةٌ داخل مستند — وغياب هذا العمود هو ما جعل ورقةَ السند
    // المسودة طريقاً مسدوداً: لا يُعرف أي سند يُرحَّل ولا كيف يُوصَل إليه.
    {
      key: "source_document", header: "المستند", width: "130px",
      render: (r) => {
        const doc = r.source_document;
        if (!doc) return <span title="ورقة قديمة بلا سند">—</span>;
        return (
          <button
            type="button"
            data-testid="cheque-source-link"
            className="text-[var(--color-accent,#2563eb)] underline-offset-2 hover:underline"
            title={`فتح ${doc.label} ${doc.number}`}
            onClick={(e) => { e.stopPropagation(); openSourceDocument(doc); }}
          >
            {doc.label} {doc.number}
          </button>
        );
      },
    },
    {
      key: "actions", header: "", width: "120px",
      render: (r) => {
        // الورقة تنتظر سندها: الحركات كلها مرفوضة في الخادم، فالزرّ الوحيد
        // المفيد هنا هو ترحيل السند نفسه.
        if (r.needs_document_post && r.source_document) {
          const doc = r.source_document;
          return (
            <button
              type="button"
              className="aseel-toolbtn"
              data-testid="cheque-post-document"
              disabled={busy}
              title={`ترحيل ${doc.label} ${doc.number}`}
              onClick={(e) => { e.stopPropagation(); void postSourceDocument(doc); }}
            >
              <Upload className="w-3 h-3" />
              ترحيل السند
            </button>
          );
        }
        // حالة نهائية: لا حركة ممكنة — زرٌّ يفتح نافذةً فارغة كان وعداً كاذباً.
        if ((r.allowed_movements ?? []).length === 0) {
          return (
            <span className="text-[0.75rem] text-[var(--aseel-ink-soft)]"
              title="لا حركات متاحة من هذه الحالة">نهائي</span>
          );
        }
        return (
          <button
            type="button"
            className="aseel-toolbtn"
            title="تحويل الشيك"
            onClick={(e) => {
              e.stopPropagation();
              setTransferCheque(r);
              setErr(null);
              setNewMovement("");
              setTransferDate(new Date().toISOString().split("T")[0]);
              setTransferNotes("");
              setTransferBankAccount("");
              setTransferEndorsee("");
              setMovements([]);
              accountingApi.getChequeMovements(r.id)
                .then((rows) => setMovements(rows as ChequeMovementDto[]))
                .catch((e2) => {
                  // فشل التحميل كان يبدو مطابقاً لـ«لا حركات سابقة».
                  setMovements([]);
                  setErr(humanizeThrown(e2, "تعذّر تحميل مسار الشيك"));
                });
            }}
          >
            <ArrowRightLeft className="w-3 h-3" />
            تحويل
          </button>
        );
      },
    },
  ];

  // T-CHQ3: الشيك ليس مستنداً مستقلاً — يدخل الدفاتر ضمن سنده كما في الأنظمة
  // المهنية. فزرّا الإدخال يفتحان سند القبض/الصرف نفسه المستعمل في بطاقة
  // الطرف وفي الفاتورة: بلا توزيع = دفعة على الحساب، وبتوزيع = تسوية فاتورة.
  const actions: AseelToolbarAction[] = [
    {
      key: "new-in", label: "شيك وارد (سند قبض)",
      icon: <Plus className="w-4 h-4" />, onClick: () => setVoucher("Incoming"),
    },
    {
      key: "new-out", label: "شيك صادر (سند صرف)",
      icon: <Plus className="w-4 h-4" />, onClick: () => setVoucher("Outgoing"),
    },
    // CHQ-4: القائمة تخرج ورقةً — لم يكن للشاشة أي مخرَج مطبوع.
    {
      key: "print",
      label: "طباعة القائمة",
      icon: <Printer className="w-4 h-4" />,
      onClick: () => {
        const opened = printReport<ChequeDto>({
          title: "قائمة الشيكات",
          subtitle: [
            filterDirection === "Incoming" ? "واردة"
              : filterDirection === "Outgoing" ? "صادرة" : "",
            filterStatus ? statusLabelFor(filterDirection || "Incoming", filterStatus) : "",
            debouncedSearch ? `بحث: ${debouncedSearch}` : "",
          ].filter(Boolean).join(" · ") || undefined,
          meta: [
            { label: "عدد الشيكات (الإجمالي)", value: String(totalCount) },
            { label: "المعروض في هذه الورقة", value: String(filteredRows.length) },
          ],
          columns: [
            { header: "رقم الشيك", value: (r) => r.cheque_number },
            { header: "البنك", value: (r) => r.bank_display || r.bank_name || "—" },
            { header: "الاسم على الشيك", value: (r) => r.payee_name || "—" },
            { header: "الطرف", value: (r) => getPartnerName(r.partner) },
            { header: "الاستحقاق", value: (r) => formatDateLocalized(r.due_date) || "—" },
            { header: "بنك الإيداع", value: (r) => r.deposit_bank_account_name || "—" },
            { header: "الحالة", value: (r) => r.status_label || r.status },
            { header: "المبلغ", value: (r) => formatMoney(r.amount), numeric: true },
          ],
          rows: filteredRows,
          totals: ["الإجمالي", "", "", "", "", "", "", formatMoney(
            filteredRows.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0))],
          emptyHint: "لا شيكات في هذا التصفية",
        });
        if (!opened) toast("اسمح بالنوافذ المنبثقة لطباعة القائمة.", "error");
      },
    },
    { key: "refresh", label: "تحديث", onClick: load },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      {/* CHQ-4: البحث برقم الشيك — المفتاح الأول في أي نظام شيكات، ولم يكن
          موجوداً. يبحث أيضاً في الاسم على الورقة والبنك وحساب الساحب والطرف. */}
      <div className="aseel-field" style={{ minWidth: "200px" }}>
        <label className="aseel-field-label">بحث</label>
        <input
          type="search"
          className="aseel-input"
          data-testid="cheque-search"
          placeholder="رقم الشيك، البنك، الاسم…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">الاتجاه</label>
        <select className="aseel-input" value={filterDirection} onChange={(e) => setFilterDirection(e.target.value)}>
          {DIRECTIONS.map((d) => <option key={d.v} value={d.v}>{d.l}</option>)}
        </select>
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">الحالة</label>
        <select className="aseel-input" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">الكل</option>
          {statusOptions.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
        </select>
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">استحقاق من</label>
        <input type="date" className="aseel-input" value={filterDueFrom} onChange={(e) => setFilterDueFrom(e.target.value)} />
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">استحقاق إلى</label>
        <input type="date" className="aseel-input" value={filterDueTo} onChange={(e) => setFilterDueTo(e.target.value)} />
      </div>
      <div className="aseel-field" style={{ minWidth: "160px" }}>
        <label className="aseel-field-label">الشريك</label>
        <select className="aseel-input" value={filterPartner} onChange={(e) => setFilterPartner(e.target.value)}>
          <option value="">الكل</option>
          {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
    </div>
  );

  const tableContent = (
    <>
      {/* CHQ-4: شريط الدفعة — يظهر حين يوجد ما يُودَع، ويقول كم وكم قبل الفعل. */}
      {(depositableRows.length > 0 || selectedIds.size > 0) && (
        <div
          data-testid="cheque-batch-bar"
          className="mb-2 flex flex-wrap items-center gap-3 rounded border border-[var(--aseel-border)] bg-[var(--aseel-surface)] px-3 py-2"
        >
          <label className="flex items-center gap-1.5 text-[0.8rem]">
            <input
              type="checkbox"
              data-testid="cheque-select-all"
              checked={
                depositableRows.length > 0
                && depositableRows.every((r) => selectedIds.has(r.id))
              }
              onChange={(e) => {
                const ids = depositableRows.map((r) => r.id);
                setSelectedIds((prev) => {
                  const next = new Set(prev);
                  if (e.target.checked) ids.forEach((id) => next.add(id));
                  else ids.forEach((id) => next.delete(id));
                  return next;
                });
              }}
            />
            تحديد الكل ({depositableRows.length} قابل للإيداع)
          </label>
          {selectedIds.size > 0 && (
            <>
              <span className="text-[0.8rem]" data-testid="cheque-batch-summary">
                المحدَّد: <strong>{selectedIds.size}</strong> شيك ·{" "}
                <strong>{formatMoney(selectedTotal)}</strong>
              </span>
              <button
                type="button"
                className="aseel-toolbtn"
                data-testid="cheque-deposit-open"
                onClick={() => {
                  setDepositRejected([]);
                  setErr(null);
                  setDepositDate(new Date().toISOString().split("T")[0]);
                  setDepositOpen(true);
                }}
              >
                <Banknote className="w-4 h-4" />
                إيداع المحدد في البنك
              </button>
              <button
                type="button"
                className="aseel-toolbtn"
                onClick={() => setSelectedIds(new Set())}
              >
                إلغاء التحديد
              </button>
            </>
          )}
        </div>
      )}
      <AseelDenseTable<ChequeDto>
        columns={columns}
        rows={filteredRows}
        getRowKey={(r) => r.id}
        loading={loading}
        emptyHint={
          debouncedSearch || filterStatus || filterDirection || filterPartner
            ? "لا شيكات تطابق البحث/الفلاتر"
            : "لا توجد شيكات"
        }
        // CHQ-4: الفرز خادميّ — على القائمة كلها لا على الصفحة المعروضة.
        sortKey={ordering.replace(/^-/, "")}
        sortDir={ordering.startsWith("-") ? "desc" : "asc"}
        onSort={(key, dir) => setOrdering(dir === "desc" ? `-${key}` : key)}
        pagination={{
          page,
          pageSize: PAGE_SIZE,
          total: totalCount,
          onChange: setPage,
        }}
        exportable
        exportFilename="cheques"
      />
    </>
  );

  const tabs: AseelTab[] = [
    { key: "list", label: "قائمة الشيكات", content: tableContent },
    {
      key: "wallet",
      label: "محفظة الشيكات",
      content: (
        <ChequeWalletPanel
          refreshKey={walletKey}
          statusLabel={statusLabelFor}
          onPickStatus={(direction, status) => {
            setFilterDirection(direction);
            setFilterStatus(status);
            setActiveTab("list");
          }}
        />
      ),
    },
    // CHQ-4: المحفظة تقول كم في اليد، وهذا التبويب يقول **متى** — أسبوعاً
    // بأسبوع بصافٍ تراكمي، من تقرير `cheques-maturity` كما يبنيه الخادم.
    {
      key: "maturity",
      label: "الاستحقاق والسيولة",
      content: <ChequeMaturityPanel refreshKey={walletKey} />,
    },
  ];

  return (
    <div>
      {/* CHQ-5: رفض الخادم كان يُكتب في `err` ولا يُعرض في أي مكان — والحارس
          الجديد (سند غير مرحّل، انتقال غير مسموح) يردّ هنا. الرسالة تظهر داخل
          نافذة التحويل حين تكون مفتوحة لأن النافذة تغطّي الصفحة، وعلى الصفحة
          نفسها حين يكون الفشل في التحميل أو الحذف. */}
      {err && !transferCheque && (
        <div className="aseel-banner aseel-banner--err" data-testid="cheque-page-error"
          style={{ marginBottom: "8px" }}>{err}</div>
      )}
      <AseelDocumentShell
        title="الشيكات"
        actions={actions}
        header={filterBar}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        status={
          <span className="aseel-status-item">
            {totalCount} شيك
            {totalCount > PAGE_SIZE
              && ` — صفحة ${page} من ${Math.ceil(totalCount / PAGE_SIZE)}`}
          </span>
        }
      >
        <></>
      </AseelDocumentShell>

      {/* T-CHQ3: إدخال الشيك عبر سنده — نفس النافذة المستعملة في بطاقة الطرف
          وفي الفاتورة، فلا يوجد مسار ثانٍ للشيك ولا قيد موازٍ. */}
      {voucher === "Incoming" && (
        <NewPaymentModal
          onClose={() => setVoucher(null)}
          onSaved={() => { setVoucher(null); void load(); }}
        />
      )}
      {voucher === "Outgoing" && (
        <NewSupplierPaymentModal
          onClose={() => setVoucher(null)}
          onSaved={() => { setVoucher(null); void load(); }}
        />
      )}

      {/* CHQ-4: نافذة الإيداع الجماعي — بنك واحد وتاريخ واحد لكل الحزمة،
          فالقسيمة ورقةٌ واحدة تُسلَّم مع الأوراق. */}
      {depositOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50"
          data-testid="cheque-deposit-dialog">
          <div style={{
            background: "var(--aseel-surface)", borderRadius: "var(--aseel-radius)",
            boxShadow: "0 8px 32px #0004", maxWidth: "460px", width: "100%",
            padding: "24px", border: "1px solid var(--aseel-border)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3 style={{ fontWeight: "bold" }}>إيداع {selectedIds.size} شيكاً في البنك</h3>
              <button type="button" className="aseel-toolbtn" onClick={() => setDepositOpen(false)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div style={{ display: "grid", gap: "10px" }}>
              <div style={{ fontSize: "0.85rem" }}>
                الإجمالي: <strong>{formatMoney(selectedTotal)}</strong>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">البنك المُودَع فيه</label>
                <select className="aseel-input" data-testid="cheque-deposit-bank"
                  value={depositBank} onChange={(e) => setDepositBank(e.target.value)}>
                  <option value="">— اختر البنك —</option>
                  {bankAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.bank_name} — {a.name} ({a.currency_code})
                    </option>
                  ))}
                </select>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">تاريخ الإيداع</label>
                <input type="date" className="aseel-input" value={depositDate}
                  onChange={(e) => setDepositDate(e.target.value)} />
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">ملاحظات القسيمة</label>
                <textarea className="aseel-input" rows={2} value={depositNotes}
                  onChange={(e) => setDepositNotes(e.target.value)} />
              </div>
              {/* الدفعة ذرّية: هذه القائمة تعني أن **لا شيء** أُودع بعد. */}
              {depositRejected.length > 0 && (
                <div className="aseel-banner aseel-banner--err" data-testid="cheque-deposit-rejected">
                  <div style={{ fontWeight: 700, marginBottom: "4px" }}>
                    لم تُودَع أي ورقة — استثنِ الآتي من التحديد:
                  </div>
                  <ul style={{ display: "grid", gap: "2px", fontSize: "0.8rem" }}>
                    {depositRejected.map((r, i) => (
                      <li key={`${r.cheque_id ?? "x"}-${i}`}>
                        {r.cheque_number ? `شيك ${r.cheque_number}: ` : ""}{r.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {err && depositRejected.length === 0 && (
                <div className="aseel-banner aseel-banner--err">{err}</div>
              )}
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setDepositOpen(false)}>إلغاء</button>
              <OfflineGuard
                action="إيداع الشيكات"
                warningMessage="الإيداع يُرحَّل له قيدٌ لكل ورقة على الخادم — يتطلب اتصالاً"
              >
                <button
                  type="button"
                  className="aseel-toolbtn"
                  data-testid="cheque-deposit-submit"
                  // البنك مطلوب متى وُجدت بنوك مسجَّلة — نفس شرط الخادم.
                  disabled={busy || selectedIds.size === 0 || (bankAccounts.length > 0 && !depositBank)}
                  onClick={doDepositBatch}
                >
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Banknote className="w-4 h-4" />}
                  إيداع وطباعة القسيمة
                </button>
              </OfflineGuard>
            </div>
          </div>
        </div>
      )}

      {/* Transfer dialog */}
      {transferCheque && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50"
          data-testid="cheque-transfer-dialog">
          <div style={{
            background: "var(--aseel-surface)", borderRadius: "var(--aseel-radius)",
            boxShadow: "0 8px 32px #0004", maxWidth: "420px", width: "100%",
            padding: "24px", border: "1px solid var(--aseel-border)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3 style={{ fontWeight: "bold" }}>تحويل الشيك #{transferCheque.cheque_number}</h3>
              <button type="button" className="aseel-toolbtn" onClick={() => setTransferCheque(null)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div style={{ display: "grid", gap: "10px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--aseel-ink-soft)" }}>
                {transferCheque.direction === "Incoming" ? "شيك وارد" : "شيك صادر"} ·
                الحالة الحالية: <strong>{transferCheque.status_label || transferCheque.status}</strong>
              </div>
              {/* CHQ-4: أهمّ ثلاث حقائق قبل تأكيد حركة مالية — كانت النافذة
                  تعرض رقم الشيك وحالته فقط، فيُحوَّل المستخدم ورقةً لا يرى
                  مبلغها ولا صاحبها ولا موعدها. */}
              <div
                data-testid="cheque-transfer-facts"
                style={{ fontSize: "0.85rem", display: "flex", flexWrap: "wrap", gap: "12px" }}
              >
                <span>المبلغ: <strong>{formatMoney(transferCheque.amount)}</strong></span>
                <span>الطرف: <strong>{getPartnerName(transferCheque.partner)}</strong></span>
                <span>الاستحقاق: <strong>{formatDateLocalized(transferCheque.due_date) || "—"}</strong></span>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">الحركة</label>
                <select className="aseel-input" data-testid="cheque-move-select"
                  value={newMovement} onChange={(e) => setNewMovement(e.target.value)}>
                  <option value="">— اختر الحركة —</option>
                  {moves.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
                {moves.length === 0 && (
                  <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                    حالة نهائية — لا حركات متاحة من «{transferCheque.status_label || transferCheque.status}»
                  </span>
                )}
              </div>
              {selectedMove?.requires_bank_account && (
                <div className="aseel-field">
                  <label className="aseel-field-label">
                    {newMovement === "deposit"
                      ? "البنك المُودَع فيه"
                      : "حساب الإيداع/التحصيل البنكي"}
                  </label>
                  <select className="aseel-input" data-testid="cheque-bank-select"
                    value={transferBankAccount}
                    onChange={(e) => setTransferBankAccount(e.target.value)}>
                    {/* CHQ-4: الإيداع لا صندوق افتراضي له — الورقة تُودَع في بنك
                        بعينه أو لا تُودَع. الخيار المحايد يبقى للحركات النقدية. */}
                    <option value="">
                      {newMovement === "deposit" ? "— اختر البنك —" : "— الصندوق الافتراضي —"}
                    </option>
                    {bankAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.bank_name} — {a.name} ({a.currency_code})
                      </option>
                    ))}
                  </select>
                  {/* CHQ-4: التحصيل يقترح البنك الذي أُودعت فيه الورقة — هو
                      المصدر الطبيعي للنقد، وكتابته من الذاكرة كل مرة خطأ ينتظر. */}
                  {transferCheque.deposit_bank_account_name && newMovement !== "deposit" && (
                    <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                      أُودِع في: {transferCheque.deposit_bank_account_name}
                    </span>
                  )}
                </div>
              )}
              {/* CHQ-4: التظهير يسدّد مورداً بالورقة بدل النقد — بلا مستفيدٍ لا
                  يكون للحركة قيد ذمم، فالحقل شرطٌ لا اختيار. */}
              {selectedMove?.requires_endorsee && (
                <div className="aseel-field">
                  <label className="aseel-field-label">المورد المستفيد من التظهير</label>
                  <select className="aseel-input" data-testid="cheque-endorsee-select"
                    value={transferEndorsee}
                    onChange={(e) => setTransferEndorsee(e.target.value)}>
                    <option value="">— اختر المورد —</option>
                    {suppliers.map((sup) => (
                      <option key={sup.id} value={sup.id}>{sup.name}</option>
                    ))}
                  </select>
                  {!transferEndorsee && (
                    <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                      تنخفض ذمة هذا المورد بقيمة الشيك عند التظهير.
                    </span>
                  )}
                </div>
              )}
              <div className="aseel-field">
                <label className="aseel-field-label">تاريخ التحويل</label>
                <input type="date" className="aseel-input" value={transferDate}
                  onChange={(e) => setTransferDate(e.target.value)} />
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">ملاحظات</label>
                <textarea className="aseel-input" rows={2} value={transferNotes}
                  onChange={(e) => setTransferNotes(e.target.value)} />
              </div>
              {/* T-CHQ2 · CHQ-4: مسار الشيك — كل خطوة بتاريخها ومنفّذها **وقيدها**.
                  رقم القيد رابطٌ إلى شاشة القيد ولا مبلغ بجانبه عمداً: سند قبض
                  موزَّع على فاتورتين يشقّ مبلغ الشيك على قيدين (THA-489)، فرقمٌ
                  هنا كان سيزعم أنه «قيد مبلغ هذا الشيك». القيد يتكلّم عن نفسه. */}
              <div style={{ borderTop: "1px solid var(--aseel-border)", paddingTop: "8px" }}>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--aseel-ink-soft)", marginBottom: "4px" }}>
                  مسار الشيك
                </div>
                {movements.length === 0 ? (
                  <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                    لا حركات سابقة.
                  </span>
                ) : (
                  <ol style={{ display: "grid", gap: "2px", fontSize: "0.8rem" }}>
                    {movements.map((m) => (
                      <li key={m.id} data-testid="cheque-movement-row"
                        style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
                        <span>
                          {m.movement_type_label || m.movement_type_display}
                          {m.notes ? ` — ${m.notes}` : ""}
                          {m.created_by_name ? ` (${m.created_by_name})` : ""}
                        </span>
                        <span style={{ color: "var(--aseel-ink-soft)", whiteSpace: "nowrap", display: "flex", gap: "8px" }}>
                          {m.journal ? (
                            <button
                              type="button"
                              data-testid="cheque-journal-link"
                              className="text-[var(--color-accent,#2563eb)] underline-offset-2 hover:underline"
                              title={`فتح القيد${m.journal_date ? ` — ${formatDateLocalized(m.journal_date)}` : ""}`}
                              onClick={() => navigate(`/accounting/journals/${m.journal}`)}
                            >
                              قيد {m.journal_number}
                            </button>
                          ) : (
                            <span title="خطوة لم تمسّ الدفاتر — لا قيد لها">بلا قيد</span>
                          )}
                          {formatDateTimeValue(m.created_at)}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
            {err && (
              <div className="aseel-banner aseel-banner--err" data-testid="cheque-transfer-error"
                style={{ marginTop: "12px" }}>{err}</div>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setTransferCheque(null)}>إلغاء</button>
              <OfflineGuard
                action="تحويل حالة الشيك"
                warningMessage="تَحويل حالة الشيك يتطلب اتصالاً — state machine يَنفَّذ على الـserver"
              >
                <button
                  type="button"
                  className="aseel-toolbtn"
                  data-testid="cheque-transfer-submit"
                  // CHQ-4: `requires_bank_account` كان يُعلَن ولا يُفرَض — الضغط
                  // بلا بنك يسقط على الصندوق الافتراضي في الخادم بصمت، فيقع قيد
                  // على حسابٍ لم يقصده أحد ولا يعرف المستخدم أنه حدث.
                  disabled={
                    busy || !newMovement
                    || (selectedMove?.requires_endorsee === true && !transferEndorsee)
                    || (selectedMove?.requires_bank_account === true && !transferBankAccount)
                  }
                  onClick={doTransfer}
                >
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRightLeft className="w-4 h-4" />}تحويل
                </button>
              </OfflineGuard>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
