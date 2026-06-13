import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  attachPaymentVoucher,
  createSalesInvoice,
  duplicateSalesInvoice,
  getCreditPreview,
  getNextInvoiceNumber,
  getSalesInvoice,
  patchSalesInvoice,
  postSalesInvoice,
  type CreditPreviewResponse,
  type SalesInvoiceDetail,
  type SalesInvoiceRow,
} from "../../services/salesApi";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { useStaleConfirm } from "../offline/StaleDataConfirm";
import { AseelDatePicker } from "../ui/AseelDatePicker";
import db from "../../services/offline/db";
import { computeInvoiceTotals, type LineInput } from "../../utils/salesInvoiceMath";
import { apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Pencil,
  Plus,
  Printer,
  Receipt,
  Save,
  Search,
  Send,
  Trash2,
  X,
  CreditCard,
  ArrowRight,
} from "lucide-react";
import { SalesProductPickerModal, formatProductPrimaryName } from "./SalesProductPickerModal";
import { CustomerQuickAddModal } from "./CustomerQuickAddModal";
import {
  AseelDocumentShell,
  AseelGrid,
  AseelIndexPicker,
  AseelAutocomplete,
  useAseelKeymap,
  useRecordNavigation,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../aseel";

export type ProductRow = {
  id: number;
  sku: string;
  barcode?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  quantity_on_hand: string;
  online_price?: string | null;
  avg_cost?: string | null;
};

export type PartnerRow = {
  id: number;
  name: string;
  partner_type: string;
  credit_limit?: string | null;
  /** M5: customer's linked GL account — enables ledger drill-down. */
  linked_account?: number | null;
};

export type CurrRow = { CurrencyID: number; Code: string; Name?: string | null };
export type AccountRow = {
  id: number;
  code?: string | null;
  name?: string | null;
  account_type?: string | null;
};
export type TaxRow = {
  id: number;
  name: string;
  code: string;
  rate: string;
  tax_account?: number;
  direction?: string;
  tax_account_type?: string;
};

type DraftLine = {
  key: string;
  id?: number;
  product: number | "";
  quantity: string;
  unit_price: string;
  line_discount: string;
  tax_rate: number | "" | null;
};

const newLineKey = () => `ln-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

const initialBlankLine = (): DraftLine => ({
  key: newLineKey(),
  product: "",
  quantity: "1",
  unit_price: "0",
  line_discount: "0",
  tax_rate: "",
});

type Props = {
  products: ProductRow[];
  partners: PartnerRow[];
  currencies: CurrRow[];
  accounts: AccountRow[];
  taxRates: TaxRow[];
  draftToEditId: number | null;
  onDraftEditConsumed: () => void;
  onInvoiceSaved: () => void;
  /** task16: العودة لقائمة الفواتير (زر صريح في الشريط + إغلاق المحرر). */
  onClose?: () => void;
  /** قائمة الفواتير الحالية (لتنقّل السجلات الأول/السابق/التالي/الأخير). */
  invoiceList?: SalesInvoiceRow[];
  /** اسم/رقم المستخدم الحالي لشريط الحالة (اختياري). */
  currentUserName?: string;
  /** M5: فتح الأستاذ العام لحساب العميل المرتبط (drill-down من رصيد العميل). */
  onOpenGeneralLedger?: (accountId: number) => void;
  salesSettings?: {
    default_customer: number | null;
    default_currency: number | null;
    default_payment_type: "cash" | "credit";
    default_cash_account: number | null;
    default_revenue_account_product: number | null;
    stock_on_post_default: boolean;
    default_vat_rate: number | null;
    prices_include_tax: boolean;
    auto_post_invoices: boolean;
    show_journal_preview: boolean;
  } | null;
};

/** هل الحساب صندوق/بنك مناسب لاستلام نقد؟
 *  قواعد (ترتيب الأولوية):
 *    - نوع الحساب Asset
 *    - الكود يبدأ بـ 1101 / 1102 (الصناديق) أو 1103 (البنوك) حسب COA المقترح
 *    - أو الاسم يحتوي: صندوق، بنك، نقدية، cash، bank
 */
const isCashboxAccount = (a: AccountRow): boolean => {
  if (a.account_type && a.account_type !== "Asset") return false;
  const code = (a.code || "").trim();
  if (/^110[123]\b/.test(code) || /^(1101|1102|1103)/.test(code)) return true;
  const name = (a.name || "").toLowerCase();
  if (/صندوق|نقد|بنك|cash|bank|till|petty/i.test(name)) return true;
  return false;
};

/** هل الحساب حساب إيراد مناسب لفاتورة مبيعات؟ */
const isRevenueAccount = (a: AccountRow): boolean => {
  if (a.account_type === "Revenue") return true;
  // أحياناً account_type لم يُعبَّأ — نستخدم الكود كـ fallback (4xxx = Revenue في COA)
  if (!a.account_type) {
    const code = (a.code || "").trim();
    return /^4/.test(code);
  }
  return false;
};

export const SalesInvoiceEditor: React.FC<Props> = ({
  products,
  partners,
  currencies,
  accounts,
  taxRates,
  draftToEditId,
  onDraftEditConsumed,
  onInvoiceSaved,
  onClose,
  invoiceList = [],
  currentUserName,
  onOpenGeneralLedger,
  salesSettings,
}) => {
  const [draftId, setDraftId] = useState<number | null>(null);
  const [invoiceNumber, setInvoiceNumber] = useState<string>("");
  const [customerId, setCustomerId] = useState<number | "">("");
  const [invDate, setInvDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [dueDate, setDueDate] = useState("");
  const [invType, setInvType] = useState<"cash" | "credit">("credit");
  const [currencyId, setCurrencyId] = useState<number | "">("");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [invoiceDiscount, setInvoiceDiscount] = useState("0");
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [revenueAccountId, setRevenueAccountId] = useState<number | "">("");
  const [stockOnPost, setStockOnPost] = useState(true);
  const [notes, setNotes] = useState("");
  // ── M2-T1: Aseel header fields ─────────────────────────────────────────
  const [bookNumber, setBookNumber] = useState<string>("0");
  const [secondDate, setSecondDate] = useState<string>("");
  const [licensedDealerNo, setLicensedDealerNo] = useState<string>("");
  const [settlementInvoiceNo, setSettlementInvoiceNo] = useState<string>("");
  const [pricesIncludeTax, setPricesIncludeTax] = useState(false);
  const [discountPercent, setDiscountPercent] = useState<string>("0");
  // ── M2-T3: Attached payment voucher (cash + cheques) ───────────────────
  const [attachedCashAmount, setAttachedCashAmount] = useState<string>("0");
  const [attachedCashAccountId, setAttachedCashAccountId] = useState<number | "">("");
  const [attachedCheques, setAttachedCheques] = useState<
    Array<{
      id?: number;
      cheque_number: string;
      bank_name?: string;
      amount: string;
      due_date?: string | null;
      issue_date?: string | null;
      payee_name?: string;
      notes?: string;
      status?: string;
    }>
  >([]);
  const [activeTabKey, setActiveTabKey] = useState("notes");
  // ── M2-T4: Source discount overrides (null = use customer default) ─────
  const [sourceDiscountPctOverride, setSourceDiscountPctOverride] = useState<string>("");
  const [sourceDiscountAmtOverride, setSourceDiscountAmtOverride] = useState<string>("");
  const [lines, setLines] = useState<DraftLine[]>(() => [initialBlankLine()]);
  const [productFilter, setProductFilter] = useState("");
  const [taxEditKey, setTaxEditKey] = useState<string | null>(null);
  const [taxPercentDraft, setTaxPercentDraft] = useState<Record<string, string>>({});
  const [taxSavingKey, setTaxSavingKey] = useState<string | null>(null);
  const [productPickerLineKey, setProductPickerLineKey] = useState<string | null>(null);
  const [invoiceStatus, setInvoiceStatus] = useState<string>("draft");
  const [postedJournalId, setPostedJournalId] = useState<number | null>(null);
  // P3-2-b wiring: offline status + stale-data confirm for line additions.
  const { online: networkOnline } = useOnlineStatus();
  const { confirm: confirmStale, modal: staleModal } = useStaleConfirm();

  const [saving, setSaving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [creditHint, setCreditHint] = useState<CreditPreviewResponse | null>(null);
  const [showPreview, setShowPreview] = useState(true);
  /** آخر مفتاح اختصار ضُغط (يُعرض في شريط الحالة — سلوك الأصيل). */
  const [lastKey, setLastKey] = useState<string>("—");
  /** فهرس الحسابات (العميل) منبثق بمفتاح + أو زر «…». */
  const [customerPickerOpen, setCustomerPickerOpen] = useState(false);
  const [showAddCustomerModal, setShowAddCustomerModal] = useState(false);
  const navLoadingRef = useRef(false);

  const dirtyRef = useRef(false);

  const customers = useMemo(() => partners.filter((p) => p.partner_type === "Customer"), [partners]);

  const productsById = useMemo(() => {
    const m = new Map<number, ProductRow>();
    products.forEach((p) => m.set(p.id, p));
    return m;
  }, [products]);

  // M3: selling below available stock is ALLOWED — but we surface a
  // non-blocking warning so the user is aware the stock will go negative.
  const overSellWarnings = useMemo(() => {
    if (!stockOnPost) return [] as { sku: string; qty: number; available: number }[];
    const out: { sku: string; qty: number; available: number }[] = [];
    for (const l of lines) {
      if (l.product === "") continue;
      const pr = productsById.get(Number(l.product));
      if (!pr) continue;
      const q = Number(l.quantity) || 0;
      const avail = Number(pr.quantity_on_hand) || 0;
      if (q > avail + 1e-6) out.push({ sku: pr.sku, qty: q, available: avail });
    }
    return out;
    // lines/quantities are strings in state; recompute whenever they change
  }, [lines, productsById, stockOnPost]);

  /** نسب الضرائب المسموحة للمبيعات: direction ∈ {sales, both} أو بدون direction (قديم). */
  const salesTaxRates = useMemo(
    () =>
      taxRates.filter((t) => {
        const d = (t.direction || "both").toLowerCase();
        return d === "sales" || d === "both";
      }),
    [taxRates]
  );

  const taxRateMap = useMemo(() => {
    const m = new Map<number, number>();
    taxRates.forEach((t) => m.set(t.id, Number(t.rate)));
    return m;
  }, [taxRates]);

  const taxRateById = useMemo(() => {
    const m = new Map<number, TaxRow>();
    taxRates.forEach((t) => m.set(t.id, t));
    return m;
  }, [taxRates]);

  const accountsById = useMemo(() => {
    const m = new Map<number, AccountRow>();
    accounts.forEach((a) => m.set(a.id, a));
    return m;
  }, [accounts]);

  const cashboxAccounts = useMemo(
    () => accounts.filter(isCashboxAccount).sort((a, b) => (a.code || "").localeCompare(b.code || "")),
    [accounts]
  );
  const revenueAccounts = useMemo(
    () => accounts.filter(isRevenueAccount).sort((a, b) => (a.code || "").localeCompare(b.code || "")),
    [accounts]
  );

  /** نسبة ض.ق.م الافتراضية من الإعدادات أو الافتراضي 16% */
  const defaultVatRateId = useMemo(() => {
    if (salesSettings?.default_vat_rate) {
      const settingRate = Number(salesSettings.default_vat_rate);
      const bySettings = salesTaxRates.find((t) => Math.abs(Number(t.rate) - settingRate) < 0.02);
      if (bySettings) return bySettings.id;
    }
    const byCode = salesTaxRates.find((t) => t.code === "VAT16");
    if (byCode) return byCode.id;
    const byRate = salesTaxRates.find((t) => Math.abs(Number(t.rate) - 16) < 0.02);
    return byRate?.id;
  }, [salesTaxRates, salesSettings?.default_vat_rate]);

  const makeEmptyLine = useCallback((): DraftLine => {
    return {
      key: newLineKey(),
      product: "",
      quantity: "1",
      unit_price: "0",
      line_discount: "0",
      tax_rate: defaultVatRateId ?? "",
    };
  }, [defaultVatRateId]);

  const lineInputsForMath: LineInput[] = useMemo(
    () =>
      lines.map((l) => ({
        quantity: l.quantity,
        unit_price: l.unit_price,
        line_discount: l.line_discount,
        tax_rate_id: l.tax_rate === "" || l.tax_rate === null ? null : Number(l.tax_rate),
      })),
    [lines]
  );

  const totals = useMemo(
    () => computeInvoiceTotals(lineInputsForMath, taxRateMap, invoiceDiscount),
    [lineInputsForMath, taxRateMap, invoiceDiscount]
  );

  /** حساب افتراضي لحساب الإيراد عند وصول قائمة الحسابات (أول Revenue). */
  useEffect(() => {
    if (revenueAccountId !== "") return;
    if (salesSettings?.default_revenue_account_product) {
      setRevenueAccountId(salesSettings.default_revenue_account_product);
      return;
    }
    if (!revenueAccounts.length) return;
    setRevenueAccountId(revenueAccounts[0].id);
  }, [revenueAccounts, revenueAccountId, salesSettings?.default_revenue_account_product]);

  /** تطبيق القيم الافتراضية من الإعدادات عند أول تحميل. */
  useEffect(() => {
    if (!salesSettings) return;
    if (draftId) return; // لا تُغير فاتورة موجودة قيد التحرير
    if (customerId === "" && salesSettings.default_customer) {
      setCustomerId(salesSettings.default_customer);
    }
    if (currencyId === "" && salesSettings.default_currency) {
      setCurrencyId(salesSettings.default_currency);
    }
    // نوع الدفع — نُطبّقه مرة واحدة فقط إذا كان افتراضنا credit
    if (salesSettings.default_payment_type && invType !== salesSettings.default_payment_type) {
      setInvType(salesSettings.default_payment_type);
    }
    // إخفاء/إظهار معاينة القيد
    setShowPreview(salesSettings.show_journal_preview);
    // افتراضي تخفيض المخزون عند الترحيل
    setStockOnPost(salesSettings.stock_on_post_default);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [salesSettings?.default_customer, salesSettings?.default_currency, salesSettings?.show_journal_preview]);

  useEffect(() => {
    if (!salesSettings) return;
    if (draftId || draftToEditId) return;
    setPricesIncludeTax(Boolean(salesSettings.prices_include_tax));
  }, [salesSettings?.prices_include_tax, draftId, draftToEditId]);

  /** حساب افتراضي للصندوق عند التحويل إلى نقدي. */
  useEffect(() => {
    if (invType !== "cash") return;
    if (cashAccountId !== "") return;
    if (salesSettings?.default_cash_account) {
      setCashAccountId(salesSettings.default_cash_account);
      return;
    }
    if (!cashboxAccounts.length) return;
    setCashAccountId(cashboxAccounts[0].id);
  }, [invType, cashboxAccounts, cashAccountId, salesSettings?.default_cash_account]);

  /** معاينة القيد المحاسبي المباشرة — تطابق منطق post_sales_invoice في الخادم. */
  type PreviewLine = {
    accountId: number | null;
    accountLabel: string;
    debit: number;
    credit: number;
    description?: string;
  };

  const journalPreview = useMemo((): {
    lines: PreviewLine[];
    totalDebit: number;
    totalCredit: number;
    balanced: boolean;
    errors: string[];
    revenue: number;
    cogs: number;
    grossProfit: number;
    marginPct: number;
  } => {
    const errors: string[] = [];
    const out: PreviewLine[] = [];
    const grand = totals.grandTotal;
    const net = totals.subtotalExclTax;
    const tax = totals.taxAmount;

    if (grand <= 0) {
      return {
        lines: [],
        totalDebit: 0,
        totalCredit: 0,
        balanced: true,
        errors: [],
        revenue: 0,
        cogs: 0,
        grossProfit: 0,
        marginPct: 0,
      };
    }

    // 1) المدين — دائماً يُقيّد على ذمم العميل أولاً
    const custName =
      customerId !== "" ? customers.find((c) => c.id === Number(customerId))?.name : "";
    const arLabel = custName
      ? `ذمم مدينة — ${custName}`
      : "ذمم مدينة (سيُحدَّد تلقائياً من linked_account للعميل)";
    
    out.push({
      accountId: null,
      accountLabel: arLabel,
      debit: grand,
      credit: 0,
      description: "إثبات ذمم",
    });

    // 2) تسوية الدفعة النقدية إن وجدت
    if (invType === "cash") {
      if (cashAccountId === "") {
        errors.push("لم يُحدَّد حساب الصندوق/البنك الافتراضي — عيّنه في إعدادات المبيعات.");
      } else {
        const a = accountsById.get(Number(cashAccountId));
        out.push({
          accountId: Number(cashAccountId),
          accountLabel: a ? `${a.code || ""} — ${a.name || ""}` : `#${cashAccountId}`,
          debit: grand,
          credit: 0,
          description: "تحصيل نقدي",
        });
        out.push({
          accountId: null,
          accountLabel: arLabel,
          debit: 0,
          credit: grand,
          description: "تسوية ذمم (تحصيل نقدي)",
        });
      }
    }

    // 2) الدائن — الإيراد
    if (revenueAccountId === "") {
      errors.push("لم يُحدَّد حساب الإيراد الافتراضي — عيّنه في إعدادات المبيعات.");
    } else if (net > 0) {
      const a = accountsById.get(Number(revenueAccountId));
      out.push({
        accountId: Number(revenueAccountId),
        accountLabel: a ? `${a.code || ""} — ${a.name || ""}` : `#${revenueAccountId}`,
        debit: 0,
        credit: net,
        description: "إيراد مبيعات",
      });
    }

    // 3) الدائن — ضرائب مخرجات (تجميع حسب الحساب)
    const taxBuckets = new Map<number, number>();
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (l.tax_rate === "" || l.tax_rate === null) continue;
      const tr = taxRateById.get(Number(l.tax_rate));
      if (!tr || !tr.tax_account) continue;
      const d = (tr.direction || "both").toLowerCase();
      if (d !== "sales" && d !== "both") {
        errors.push(`الضريبة "${tr.code}" اتجاهها ${d} — غير صالحة للمبيعات.`);
        continue;
      }
      const amt = totals.perLine[i]?.lineTax || 0;
      if (amt > 0) {
        taxBuckets.set(tr.tax_account, (taxBuckets.get(tr.tax_account) || 0) + amt);
      }
    }
    taxBuckets.forEach((amt, accId) => {
      const a = accountsById.get(accId);
      out.push({
        accountId: accId,
        accountLabel: a ? `${a.code || ""} — ${a.name || ""}` : `#${accId}`,
        debit: 0,
        credit: amt,
        description: "ضريبة مخرجات",
      });
    });
    // تحقق تقريبي: مجموع الضريبة المحلوظة مقابل total tax
    const taxSum = Array.from(taxBuckets.values()).reduce((s, v) => s + v, 0);
    if (Math.abs(taxSum - tax) > 0.02 && tax > 0) {
      errors.push(
        `ضريبة غير مُسجَّلة: إجمالي الضريبة ${tax.toFixed(2)} لا يطابق ما سيُقيَّد ${taxSum.toFixed(
          2
        )}. تأكد من وجود tax_account لكل نسبة.`
      );
    }

    // 4) COGS / Inventory (إن كان خصم المخزون عند الترحيل)
    // M5: cost is computed unconditionally so gross profit can be shown even
    // when stock is not deducted at post-time; the journal lines below are
    // still only emitted when stock_on_post is enabled.
    let cogsTotal = 0;
    for (const l of lines) {
      if (l.product === "") continue;
      const p = productsById.get(Number(l.product));
      if (!p) continue;
      const avg = Number(p.avg_cost || 0);
      const qty = Number(l.quantity || 0);
      if (avg > 0 && qty > 0) {
        cogsTotal += avg * qty;
      }
    }
    if (stockOnPost) {
      if (cogsTotal > 0) {
        out.push({
          accountId: null,
          accountLabel: "تكلفة مبيعات (COGS) — يُحدَّد من فئة المنتج",
          debit: cogsTotal,
          credit: 0,
          description: "COGS",
        });
        out.push({
          accountId: null,
          accountLabel: "المخزون — يُحدَّد من فئة المنتج (أو 1104)",
          debit: 0,
          credit: cogsTotal,
          description: "صرف مخزون",
        });
      }
    }

    const totalDebit = out.reduce((s, r) => s + r.debit, 0);
    const totalCredit = out.reduce((s, r) => s + r.credit, 0);
    const balanced = Math.abs(totalDebit - totalCredit) < 0.02;
    if (!balanced && out.length > 0) {
      errors.push(
        `القيد غير متوازن: مدين ${totalDebit.toFixed(2)} ≠ دائن ${totalCredit.toFixed(2)}`
      );
    }
    // M5: gross profit = net revenue − cost of goods (estimate from WAC).
    const revenue = net;
    const grossProfit = revenue - cogsTotal;
    const marginPct = revenue > 0 ? (grossProfit / revenue) * 100 : 0;
    return {
      lines: out,
      totalDebit,
      totalCredit,
      balanced,
      errors,
      revenue,
      cogs: cogsTotal,
      grossProfit,
      marginPct,
    };
  }, [
    invType,
    cashAccountId,
    customerId,
    customers,
    revenueAccountId,
    lines,
    totals,
    taxRateById,
    accountsById,
    stockOnPost,
    productsById,
  ]);

  const applyDetail = useCallback((d: SalesInvoiceDetail) => {
    setInvoiceNumber(d.invoice_number || "");
    setCustomerId(d.customer);
    setInvDate(d.invoice_date);
    setDueDate(d.due_date || "");
    setInvType(d.invoice_type);
    setCurrencyId(d.currency);
    setExchangeRate(String(d.exchange_rate ?? 1));
    setInvoiceDiscount(String(d.invoice_discount ?? 0));
    setStockOnPost(d.stock_on_post !== false);
    setNotes(d.notes || "");
    setCashAccountId(d.cash_or_bank_account ?? "");
    setRevenueAccountId(d.revenue_account ?? "");
    setDraftId(d.id);
    setInvoiceStatus(d.status || "draft");
    setPostedJournalId(d.journal ?? null);
    setProductPickerLineKey(null);
    setTaxEditKey(null);
    setTaxPercentDraft({});
    // M2-T1
    setBookNumber(String(d.book_number ?? 0));
    setSecondDate(d.second_date || "");
    setLicensedDealerNo(d.licensed_dealer_no || "");
    setSettlementInvoiceNo(d.settlement_invoice_no || "");
    setPricesIncludeTax(Boolean(d.prices_include_tax));
    setDiscountPercent(String(d.discount_percent ?? 0));
    // M2-T3
    setAttachedCashAmount(String(d.attached_cash_amount ?? 0));
    setAttachedCashAccountId(d.attached_cash_account ?? "");
    setAttachedCheques(
      (d.cheques ?? []).map((c) => ({
        id: c.id,
        cheque_number: c.cheque_number,
        bank_name: c.bank_name || "",
        amount: c.amount,
        due_date: c.due_date,
        issue_date: c.issue_date,
        payee_name: c.payee_name || "",
        notes: c.notes || "",
        status: c.status,
      }))
    );
    // M2-T4
    setSourceDiscountPctOverride(
      d.source_discount_percent_override == null
        ? ""
        : String(d.source_discount_percent_override)
    );
    setSourceDiscountAmtOverride(
      d.source_discount_amount_override == null
        ? ""
        : String(d.source_discount_amount_override)
    );
    setLines(
      d.lines.map((ln) => ({
        key: newLineKey(),
        id: ln.id,
        product: ln.product,
        quantity: String(ln.quantity),
        unit_price: String(ln.unit_price),
        line_discount: String(ln.line_discount ?? 0),
        tax_rate: ln.tax_rate != null ? ln.tax_rate : null,
      }))
    );
    dirtyRef.current = false;
  }, []);

  const fetchNextInvoiceNumber = useCallback(async (bookNumStr: string) => {
    try {
      const next = await getNextInvoiceNumber(Number(bookNumStr) || 0);
      if (next) setInvoiceNumber(next);
    } catch (e) {
      console.warn("Failed to fetch next invoice number preview:", e);
    }
  }, []);

  useEffect(() => {
    if (draftId || draftToEditId) return;
    fetchNextInvoiceNumber(bookNumber);
  }, [bookNumber, draftId, draftToEditId, fetchNextInvoiceNumber]);

  useEffect(() => {
    if (draftToEditId == null) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await getSalesInvoice(draftToEditId);
        if (!cancelled) applyDetail(d);
        setMsg(null);
        setLocalErr(null);
      } catch (e) {
        if (!cancelled) {
          const raw = e instanceof Error ? e.message : "فشل تحميل الفاتورة";
          const friendly =
            /not found|404|غير موجود/i.test(raw) || /^\.?\s*not\s*found/i.test(raw)
              ? "الفاتورة غير موجودة أو حُذفت."
              : raw;
          setLocalErr(friendly);
        }
      } finally {
        if (!cancelled) onDraftEditConsumed();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [draftToEditId, applyDetail, onDraftEditConsumed]);

  useEffect(() => {
    if (!currencies.length) return;
    if (draftToEditId != null) return;
    setCurrencyId((prev) => {
      if (prev === "") return currencies[0].CurrencyID;
      const ok = currencies.some((c) => c.CurrencyID === prev);
      return ok ? prev : currencies[0].CurrencyID;
    });
  }, [currencies, draftToEditId]);

  useEffect(() => {
    if (defaultVatRateId == null) return;
    if (draftToEditId != null) return;
    if (draftId != null) return;
    setLines((prev) =>
      prev.map((l) => (l.tax_rate === "" ? { ...l, tax_rate: defaultVatRateId } : l))
    );
  }, [defaultVatRateId, draftToEditId, draftId]);

  // M5: fetch the customer's balance as soon as a customer is selected (for
  // both cash and credit invoices) so the current balance + debtor/creditor
  // status can be shown immediately. The credit-limit warning still only
  // applies to credit invoices (handled at the display layer).
  useEffect(() => {
    if (customerId === "") {
      setCreditHint(null);
      return;
    }
    const t = window.setTimeout(() => {
      getCreditPreview({
        customer: Number(customerId),
        proposed_total: totals.grandTotal.toFixed(2),
        excludeInvoice: draftId ?? undefined,
      })
        .then(setCreditHint)
        .catch(() => setCreditHint(null));
    }, 400);
    return () => clearTimeout(t);
  }, [customerId, totals.grandTotal, draftId]);

  // ── M4: beforeunload guard ─────────────────────────────────────────────
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current && invoiceStatus === "draft") {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [invoiceStatus]);

  const markDirty = () => {
    dirtyRef.current = true;
  };

  const isPosted = invoiceStatus === "posted";
  const readOnly = isPosted;

  const buildPayload = useCallback(() => {
    const body: Record<string, unknown> = {
      customer: customerId,
      invoice_date: invDate,
      due_date: dueDate || null,
      invoice_type: invType,
      currency: currencyId,
      exchange_rate: Number(exchangeRate) || 1,
      invoice_discount: Number(invoiceDiscount) || 0,
      stock_on_post: stockOnPost,
      notes: notes || "",
      lines: lines
        .filter((l) => l.product !== "")
        .map((l) => ({
          ...(l.id ? { id: l.id } : {}),
          product: l.product,
          quantity: l.quantity,
          unit_price: l.unit_price,
          line_discount: Number(l.line_discount) || 0,
          tax_rate: l.tax_rate === "" || l.tax_rate === null ? null : l.tax_rate,
        })),
      // ── M2-T1: Aseel header fields ───────────────────────────────
      book_number: Number(bookNumber) || 0,
      second_date: secondDate || null,
      licensed_dealer_no: licensedDealerNo || "",
      settlement_invoice_no: settlementInvoiceNo || "",
      prices_include_tax: pricesIncludeTax,
      discount_percent: Number(discountPercent) || 0,
      // ── M2-T4: Source discount overrides (null = use customer default) ─
      source_discount_percent_override:
        sourceDiscountPctOverride === "" ? null : Number(sourceDiscountPctOverride),
      source_discount_amount_override:
        sourceDiscountAmtOverride === "" ? null : Number(sourceDiscountAmtOverride),
    };
    if (invType === "cash" && cashAccountId !== "") body.cash_or_bank_account = cashAccountId;
    if (revenueAccountId !== "") body.revenue_account = revenueAccountId;
    return body;
  }, [
    customerId,
    invDate,
    dueDate,
    invType,
    currencyId,
    exchangeRate,
    invoiceDiscount,
    stockOnPost,
    notes,
    lines,
    cashAccountId,
    revenueAccountId,
    bookNumber,
    secondDate,
    licensedDealerNo,
    settlementInvoiceNo,
    pricesIncludeTax,
    discountPercent,
    sourceDiscountPctOverride,
    sourceDiscountAmtOverride,
  ]);

  // ── M4: local-draft persistence (Dexie) ────────────────────────────────
  const localDraftKey = draftId ? String(draftId) : "new";

  const clearLocalDraft = useCallback(async () => {
    try {
      await db.invoice_drafts.delete(localDraftKey);
    } catch {
      /* best-effort cleanup */
    }
  }, [localDraftKey]);

  // Debounced autosave: mirrors the in-progress draft to IndexedDB so an
  // accidental reload/close does not lose unsaved work. Declared AFTER
  // buildPayload so the dependency reference is past its TDZ.
  useEffect(() => {
    if (!dirtyRef.current || invoiceStatus !== "draft") return;
    const t = window.setTimeout(() => {
      void db.invoice_drafts
        .put({
          draft_id: localDraftKey,
          tenant_id: resolveTenantId(),
          data: JSON.stringify(buildPayload()),
          updated_at: new Date().toISOString(),
        })
        .catch((err) => console.error("Autosave to Dexie failed:", err));
    }, 2000);
    return () => clearTimeout(t);
  }, [buildPayload, localDraftKey, invoiceStatus]);

  // Restore-on-return: for a brand-new (unsaved) invoice, offer to recover the
  // last autosaved draft instead of silently discarding it.
  const [recoverableDraft, setRecoverableDraft] = useState<{
    data: Record<string, unknown>;
    updated_at: string;
  } | null>(null);

  useEffect(() => {
    if (draftToEditId != null || draftId != null) return;
    let cancelled = false;
    (async () => {
      try {
        const row = await db.invoice_drafts.get("new");
        if (cancelled || !row?.data) return;
        const parsed = JSON.parse(row.data) as Record<string, unknown>;
        const hasContent =
          Array.isArray(parsed.lines) && (parsed.lines as unknown[]).length > 0;
        if (hasContent) setRecoverableDraft({ data: parsed, updated_at: row.updated_at });
      } catch {
        /* corrupt/absent draft — ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
    // run once on mount for a fresh invoice
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hydrateFromLocalDraft = useCallback(
    (p: Record<string, unknown>) => {
      const s = (v: unknown, fb = "") => (v == null ? fb : String(v));
      setCustomerId((p.customer as number) ?? "");
      if (p.invoice_date) setInvDate(s(p.invoice_date));
      setDueDate(s(p.due_date));
      if (p.invoice_type === "cash" || p.invoice_type === "credit")
        setInvType(p.invoice_type);
      setCurrencyId((p.currency as number) ?? "");
      setExchangeRate(s(p.exchange_rate, "1"));
      setInvoiceDiscount(s(p.invoice_discount, "0"));
      setStockOnPost(p.stock_on_post !== false);
      setNotes(s(p.notes));
      setBookNumber(s(p.book_number, "0"));
      setSecondDate(s(p.second_date));
      setLicensedDealerNo(s(p.licensed_dealer_no));
      setSettlementInvoiceNo(s(p.settlement_invoice_no));
      setPricesIncludeTax(Boolean(p.prices_include_tax));
      setDiscountPercent(s(p.discount_percent, "0"));
      setSourceDiscountPctOverride(
        p.source_discount_percent_override == null
          ? ""
          : s(p.source_discount_percent_override)
      );
      setSourceDiscountAmtOverride(
        p.source_discount_amount_override == null
          ? ""
          : s(p.source_discount_amount_override)
      );
      if (p.cash_or_bank_account != null)
        setCashAccountId(p.cash_or_bank_account as number);
      if (p.revenue_account != null) setRevenueAccountId(p.revenue_account as number);
      const rawLines = Array.isArray(p.lines) ? (p.lines as Record<string, unknown>[]) : [];
      if (rawLines.length) {
        setLines(
          rawLines.map((ln) => ({
            key: newLineKey(),
            id: typeof ln.id === "number" ? ln.id : undefined,
            product: (ln.product as number) ?? "",
            quantity: s(ln.quantity, "0"),
            unit_price: s(ln.unit_price, "0"),
            line_discount: s(ln.line_discount, "0"),
            tax_rate:
              ln.tax_rate === "" || ln.tax_rate == null ? null : (ln.tax_rate as number),
          }))
        );
      }
      dirtyRef.current = true;
    },
    []
  );

  const validateClient = (): string | null => {
    if (customerId === "") return "اختر العميل.";
    if (currencyId === "") return "اختر العملة.";
    if (invType === "cash" && cashAccountId === "")
      return "حساب الصندوق/البنك غير مُعيَّن في إعدادات المبيعات.";
    if (revenueAccountId === "") return "حساب الإيراد غير مُعيَّن في إعدادات المبيعات.";
    const filled = lines.filter((l) => l.product !== "");
    if (!filled.length) return "أضف بنداً واحداً على الأقل.";
    for (const l of filled) {
      const q = Number(l.quantity);
      const p = Number(l.unit_price);
      if (!(q > 0)) return "الكمية يجب أن تكون أكبر من صفر في كل السطور المكتملة.";
      if (p < 0 || Number.isNaN(p)) return "سعر الوحدة غير صالح.";
      // M3: selling below available stock is permitted (business rule).
      // The backend enforces/logs the negative-stock policy; the client no
      // longer hard-blocks over-sell here.
    }
    return null;
  };

  const handleSaveDraft = async () => {
    setLocalErr(null);
    setMsg(null);
    const v = validateClient();
    if (v) {
      setLocalErr(v);
      return;
    }
    setSaving(true);
    try {
      const payload = buildPayload();
      let activeDraftId = draftId;
      if (draftId) {
        const updated = await patchSalesInvoice(draftId, payload);
        applyDetail(updated);
        setMsg("تم حفظ المسودة.");
      } else {
        const created = await createSalesInvoice(payload);
        activeDraftId = created.id;
        setDraftId(created.id);
        applyDetail(created);
        if (created.status === "posted") {
          setMsg(
            `تم إنشاء وترحيل الفاتورة ${created.invoice_number} (ترحيل تلقائي)`,
          );
        } else {
          setMsg(`تم إنشاء المسودة ${created.invoice_number}`);
        }
      }

      // Auto-save payment voucher
      if (activeDraftId) {
        try {
          const updatedWithVoucher = await attachPaymentVoucher(activeDraftId, {
            cash_amount: attachedCashAmount || "0",
            cash_account_id:
              attachedCashAccountId === ""
                ? null
                : Number(attachedCashAccountId),
            cheques: attachedCheques.map((c) => ({
              cheque_number: c.cheque_number,
              amount: c.amount,
              bank_name: c.bank_name || "",
              due_date: c.due_date || null,
              issue_date: c.issue_date || null,
              payee_name: c.payee_name || "",
              notes: c.notes || "",
            })),
          });
          applyDetail(updatedWithVoucher);
          setMsg((m) => (m ? m + " مع السند المالي المرفق." : "تم حفظ السند المالي."));
        } catch (voucherErr) {
          console.warn("Failed to auto-save payment voucher:", voucherErr);
          setLocalErr("تم حفظ الفاتورة بنجاح، لكن فشل حفظ السند المالي: " + (voucherErr instanceof Error ? voucherErr.message : String(voucherErr)));
        }
      }
      dirtyRef.current = false;
      // M4: the draft is now persisted server-side — drop the local recovery copy.
      void clearLocalDraft();
      setRecoverableDraft(null);
      onInvoiceSaved();
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const handlePost = async () => {
    if (!draftId) {
      setLocalErr("احفظ المسودة أولاً ثم رحّل.");
      return;
    }
    setLocalErr(null);
    setMsg(null);
    const v = validateClient();
    if (v) {
      setLocalErr(v);
      return;
    }
    if (!journalPreview.balanced || journalPreview.errors.length) {
      setLocalErr(
        "القيد غير صالح أو غير متوازن في المعاينة. صحّح الأخطاء المعروضة ثم أعد المحاولة."
      );
      return;
    }
    setPosting(true);
    try {
      if (dirtyRef.current) await patchSalesInvoice(draftId, buildPayload());
      const posted = await postSalesInvoice(draftId);
      setInvoiceStatus(posted.status || "posted");
      setPostedJournalId(posted.journal ?? null);
      setMsg(
        posted.journal
          ? `تم الترحيل — القيد #${posted.journal}`
          : "تم الترحيل بنجاح."
      );
      void clearLocalDraft();
      setRecoverableDraft(null);
      onInvoiceSaved();
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "فشل الترحيل");
    } finally {
      setPosting(false);
    }
  };

  const resetForm = () => {
    setDraftId(null);
    setInvoiceNumber("");
    setInvoiceStatus("draft");
    setPostedJournalId(null);
    // تطبيق العميل الافتراضي من الإعدادات
    setCustomerId(salesSettings?.default_customer ?? "");
    setInvDate(new Date().toISOString().slice(0, 10));
    setDueDate("");
    setInvType(salesSettings?.default_payment_type ?? "credit");
    if (salesSettings?.default_currency) setCurrencyId(salesSettings.default_currency);
    else if (currencies.length) setCurrencyId(currencies[0].CurrencyID);
    setExchangeRate("1");
    setInvoiceDiscount("0");
    setCashAccountId(salesSettings?.default_cash_account ?? "");
    if (salesSettings?.default_revenue_account_product)
      setRevenueAccountId(salesSettings.default_revenue_account_product);
    else if (revenueAccounts.length) setRevenueAccountId(revenueAccounts[0].id);
    else setRevenueAccountId("");
    setStockOnPost(salesSettings?.stock_on_post_default ?? true);
    setNotes("");
    setProductPickerLineKey(null);
    setTaxEditKey(null);
    setTaxPercentDraft({});
    setLines([makeEmptyLine()]);
    // M2 resets
    setBookNumber("0");
    setSecondDate("");
    setLicensedDealerNo("");
    setSettlementInvoiceNo("");
    setPricesIncludeTax(Boolean(salesSettings?.prices_include_tax));
    setDiscountPercent("0");
    setAttachedCashAmount("0");
    setAttachedCashAccountId("");
    setAttachedCheques([]);
    setSourceDiscountPctOverride("");
    setSourceDiscountAmtOverride("");
    setMsg(null);
    setLocalErr(null);
    fetchNextInvoiceNumber("0");
    dirtyRef.current = false;
  };

  const addRow = () => {
    if (readOnly) return;
    setLines((prev) => [...prev, makeEmptyLine()]);
    markDirty();
  };

  const removeRow = (key: string) => {
    if (readOnly) return;
    setLines((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.key !== key)));
    markDirty();
  };

  const updateLine = (key: string, patch: Partial<DraftLine>) => {
    if (readOnly) return;
    setLines((prev) => {
      const next = prev.map((r) => (r.key === key ? { ...r, ...patch } : r));
      const lastLine = next[next.length - 1];
      if (lastLine && (lastLine.product !== "" || (lastLine.quantity !== "" && lastLine.quantity !== "0"))) {
        return [...next, makeEmptyLine()];
      }
      return next;
    });
    markDirty();
  };

  const commitTaxPercent = async (lineKey: string) => {
    const raw = taxPercentDraft[lineKey];
    setTaxEditKey(null);
    const pct = raw === undefined || raw === "" ? NaN : Number(raw);
    if (!Number.isFinite(pct) || pct < 0) return;
    if (pct === 0) {
      updateLine(lineKey, { tax_rate: null });
      return;
    }
    const match = salesTaxRates.find((t) => Math.abs(Number(t.rate) - pct) < 0.02);
    if (match) {
      updateLine(lineKey, { tax_rate: match.id });
      return;
    }
    const base = salesTaxRates.find((t) => t.code === "VAT16") || salesTaxRates[0];
    const accId = base?.tax_account;
    if (accId == null) {
      setLocalErr(
        "لا يوجد حساب ضريبة مرجعي للمبيعات. حدّث الصفحة بعد تشغيل الترحيلات أو أضف نسبة من الإدارة."
      );
      return;
    }
    setTaxSavingKey(lineKey);
    setLocalErr(null);
    try {
      const code = `VAT_${pct}_${Date.now().toString(36)}`.slice(0, 20);
      const created = (await apiPostObject(
        "accounting/tax-rates/",
        {
          name: `ضريبة ${pct}%`,
          code,
          rate: String(pct),
          tax_account: accId,
          direction: "sales",
          is_active: true,
        },
        { tenantId: resolveTenantId() }
      )) as { id: number };
      onInvoiceSaved();
      updateLine(lineKey, { tax_rate: created.id });
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "فشل حفظ نسبة الضريبة");
    } finally {
      setTaxSavingKey(null);
    }
  };

  const onSelectProduct = async (key: string, productId: number) => {
    const pr = productsById.get(productId);
    const price =
      pr?.online_price != null && pr.online_price !== ""
        ? String(pr.online_price)
        : "0";
    // P3-2-b: when offline, warn the user if the product row is from the
    // local cache and older than 1 hour. The cached row may show a stale
    // quantity which the user is about to commit to a sale.
    if (!networkOnline) {
      try {
        const cached = await db.products.get(productId);
        if (cached) {
          const ageMs = Date.now() - new Date(cached.updated_at).getTime();
          if (ageMs > 3600_000) {
            const verdict = await confirmStale(
              pr?.name_ar || cached.sku || String(productId),
              "—",
              cached.updated_at,
            );
            if (verdict === "cancel") return;
          }
        }
      } catch { /* IndexedDB unavailable — fall through without blocking */ }
    }
    updateLine(key, {
      product: productId,
      unit_price: price,
    });
  };

  const handleBarcodeEnter = (raw: string) => {
    const t = raw.trim();
    if (!t) return;
    const byBar = products.find((p) => (p.barcode || "").trim() === t);
    if (byBar) {
      const emptyIdx = lines.findIndex((l) => l.product === "");
      const key = emptyIdx >= 0 ? lines[emptyIdx].key : lines[lines.length - 1].key;
      onSelectProduct(key, byBar.id);
      setProductFilter("");
    }
  };

  const fmt = (n: number) =>
    n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  /* ───────────── تنقّل السجلات (M1-T2) — نفس API: getSalesInvoice ───────────── */
  /** تحميل فاتورة بالمعرّف عبر نفس مسار getSalesInvoice الموجود (بلا API جديد). */
  const loadInvoice = useCallback(
    async (id: number) => {
      if (navLoadingRef.current) return;
      navLoadingRef.current = true;
      setLocalErr(null);
      setMsg(null);
      try {
        const d = await getSalesInvoice(id);
        applyDetail(d);
      } catch (e) {
        setLocalErr(e instanceof Error ? e.message : "فشل تحميل الفاتورة");
      } finally {
        navLoadingRef.current = false;
      }
    },
    [applyDetail]
  );

  const nav = useRecordNavigation<SalesInvoiceRow>({
    items: invoiceList,
    getId: (r) => r.id,
    currentId: draftId,
    onSelect: (id) => {
      if (id == null) resetForm();
      else void loadInvoice(Number(id));
    },
  });

  /* ───────────── اختصارات الأصيل (M1-T3) ───────────── */
  const noteKey = (k: string) => setLastKey(k);

  useAseelKeymap(
    {
      F2: () => {
        noteKey("F2 طباعة");
        window.print();
      },
      F3: () => {
        noteKey("F3 سند مالي");
        if (isPosted) {
          setMsg("الفاتورة مرحَّلة — السند مغلق.");
          return;
        }
        setActiveTabKey("payments");
      },
      F6: () => {
        noteKey("F6 بحث");
        const el = document.querySelector<HTMLInputElement>(
          '[data-aseel-field="barcode"]'
        );
        el?.focus();
      },
      F12: () => {
        noteKey("F12 تخزين");
        if (!readOnly && !saving) void handleSaveDraft();
      },
      Escape: () => {
        noteKey("Esc إلغاء");
        if (customerPickerOpen) {
          setCustomerPickerOpen(false);
          return;
        }
        if (productPickerLineKey) {
          setProductPickerLineKey(null);
          return;
        }
        if (!isPosted) resetForm();
      },
      plus: () => {
        // فهرس الحساب/الصنف حسب الحقل المركَّز عليه
        const active = document.activeElement as HTMLElement | null;
        const field = active?.getAttribute?.("data-aseel-field");
        if (field === "customer") {
          noteKey("+ فهرس الحسابات");
          setCustomerPickerOpen(true);
        } else {
          noteKey("+ فهرس الأصناف");
          const emptyIdx = lines.findIndex((l) => l.product === "");
          const key =
            emptyIdx >= 0 ? lines[emptyIdx].key : lines[lines.length - 1]?.key;
          if (key) setProductPickerLineKey(key);
        }
      },
      star: () => {
        // الحساب التالي داخل حقل العميل
        const active = document.activeElement as HTMLElement | null;
        if (active?.getAttribute?.("data-aseel-field") === "customer") {
          noteKey("* الحساب التالي");
          const idx = customers.findIndex((c) => c.id === Number(customerId));
          const nextC = customers[idx + 1] ?? customers[0];
          if (nextC) {
            setCustomerId(nextC.id);
            markDirty();
          }
        }
      },
      minus: () => {
        const active = document.activeElement as HTMLElement | null;
        if (active?.getAttribute?.("data-aseel-field") === "customer") {
          noteKey("- الحساب السابق");
          const idx = customers.findIndex((c) => c.id === Number(customerId));
          const prevC = customers[idx - 1] ?? customers[customers.length - 1];
          if (prevC) {
            setCustomerId(prevC.id);
            markDirty();
          }
        }
      },
      // N0-T11: Ctrl+nav handlers
      CtrlHome: () => { noteKey("Ctrl+Home الأول"); nav.first(); },
      CtrlEnd: () => { noteKey("Ctrl+End الأخير"); nav.last(); },
      CtrlPageUp: () => { noteKey("Ctrl+PgUp السابق"); nav.prev(); },
      CtrlPageDown: () => { noteKey("Ctrl+PgDn التالي"); nav.next(); },
      CtrlIns: () => { noteKey("Ctrl+Ins جديد"); resetForm(); },
    },
    { enabled: !customerPickerOpen && productPickerLineKey === null }
  );

  /* ───────────── شريحة الحالة + بيانات الرأس ───────────── */
  const docState = isPosted
    ? `فاتورة مرحّلة #${draftId ?? ""}`
    : draftId
      ? `مسودة #${draftId}`
      : "فاتورة جديدة";

  const selectedCustomer =
    customerId !== "" ? customers.find((c) => c.id === Number(customerId)) : undefined;

  const grandSubtotalBeforeDiscount = lines.reduce(
    (s, l) =>
      s +
      Math.max(
        (Number(l.quantity) || 0) * (Number(l.unit_price) || 0) -
          (Number(l.line_discount) || 0),
        0
      ),
    0
  );

  /* ───────────── أعمدة جدول البنود (AseelGrid) ───────────── */
  const gridColumns: AseelGridColumn<DraftLine>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    { key: "product", header: "بيان الصنف", width: "30%" },
    { key: "avail", header: "المتاح", width: "70px", align: "center", readOnly: true },
    { key: "quantity", header: "الكمية", width: "84px", align: "center", type: "number" },
    { key: "unit_price", header: "سعر الوحدة", width: "100px", align: "center", type: "number" },
    { key: "line_discount", header: "خصم سطر", width: "84px", align: "center", type: "number" },
    { key: "tax", header: "الضريبة", width: "150px" },
    { key: "line_total", header: "السعر الإجمالي", width: "110px", align: "center", readOnly: true },
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const gridGetCell = (row: DraftLine, key: string): string | number => {
    const idx = lines.findIndex((l) => l.key === row.key);
    const comp = idx >= 0 ? totals.perLine[idx] : undefined;
    switch (key) {
      case "seq":
        return idx + 1;
      case "quantity":
        return row.quantity;
      case "unit_price":
        return row.unit_price;
      case "line_discount":
        return row.line_discount;
      case "avail": {
        const pr = row.product ? productsById.get(Number(row.product)) : undefined;
        return pr ? fmt(Number(pr.quantity_on_hand)) : "—";
      }
      case "line_total":
        return comp ? fmt(comp.lineTotal) : "—";
      default:
        return "";
    }
  };

  const gridOnChange = (rowIndex: number, key: string, value: string) => {
    const row = lines[rowIndex];
    if (!row) return;
    if (key === "quantity") updateLine(row.key, { quantity: value });
    else if (key === "unit_price") updateLine(row.key, { unit_price: value });
    else if (key === "line_discount") updateLine(row.key, { line_discount: value });
  };

  /* task13 M5: منتقي مدمج — الكتابة في الخلية تفلتر الأصناف فورياً وتعبئ
     السطر (المودال الكامل يبقى متاحاً من زر «…» واختصار +). لا خيار «صنف حر»
     هنا لأن سطر فاتورة المبيعات يتطلب صنفاً معرّفاً في المخزون. */
  const productOptions = useMemo(
    () => products.map((p) => ({
      id: p.id,
      label: formatProductPrimaryName(p),
      sub: `${p.sku || ""} · رصيد ${Number(p.quantity_on_hand) || 0}`,
    })),
    [products],
  );

  const renderProductCell = (row: DraftLine) => (
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <AseelAutocomplete
        value={(() => {
          const pr = row.product ? productsById.get(Number(row.product)) : undefined;
          return pr ? formatProductPrimaryName(pr) : "";
        })()}
        options={productOptions}
        disabled={readOnly}
        placeholder="اكتب اسم الصنف…"
        onPick={(id) => void onSelectProduct(row.key, Number(id))}
      />
      <button
        type="button"
        className="aseel-ellipsis"
        disabled={readOnly}
        onClick={() => setProductPickerLineKey(row.key)}
        title="فهرس الأصناف الكامل (+)"
      >…</button>
    </div>
  );

  const renderTaxCell = (row: DraftLine) => {
    const isEdit = taxEditKey === row.key;
    return (
      <div className="aseel-cell-tax">
        {isEdit ? (
          <input
            className="aseel-input"
            type="number"
            min={0}
            max={100}
            step={0.01}
            disabled={taxSavingKey === row.key || readOnly}
            value={taxPercentDraft[row.key] ?? ""}
            onChange={(e) =>
              setTaxPercentDraft((d) => ({ ...d, [row.key]: e.target.value }))
            }
            onBlur={() => void commitTaxPercent(row.key)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void commitTaxPercent(row.key);
              }
            }}
            placeholder="%"
          />
        ) : (
          <select
            className="aseel-input"
            disabled={readOnly}
            value={row.tax_rate === null || row.tax_rate === "" ? "" : row.tax_rate}
            onChange={(e) =>
              updateLine(row.key, {
                tax_rate: e.target.value === "" ? null : Number(e.target.value),
              })
            }
          >
            <option value="">بدون</option>
            {salesTaxRates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.rate}%)
              </option>
            ))}
          </select>
        )}
        {!readOnly && (
          <button
            type="button"
            className="aseel-iconbtn"
            title="تعديل النسبة يدوياً %"
            onClick={() => {
              if (taxEditKey === row.key) {
                setTaxEditKey(null);
                return;
              }
              setTaxEditKey(row.key);
              const pctStr =
                row.tax_rate != null && row.tax_rate !== ""
                  ? String(salesTaxRates.find((t) => t.id === row.tax_rate)?.rate ?? "16")
                  : "16";
              setTaxPercentDraft((d) => ({ ...d, [row.key]: pctStr }));
            }}
          >
            <Pencil className="h-3 w-3" />
          </button>
        )}
      </div>
    );
  };

  const renderDeleteCell = (row: DraftLine) =>
    readOnly ? null : (
      <button
        type="button"
        className="aseel-iconbtn aseel-iconbtn--danger"
        onClick={() => removeRow(row.key)}
        title="حذف السطر"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    );

  // حقن الأعمدة المخصّصة (تستخدم render)
  gridColumns[1].render = renderProductCell;
  gridColumns[6].render = renderTaxCell;
  gridColumns[8].render = renderDeleteCell;

  const toolbarActions: AseelToolbarAction[] = [
    // task16: زر صريح للعودة لقائمة الفواتير (إلى جانب ✕ إغلاق في الإطار)
    ...(onClose
      ? [{ key: "back", label: "الفواتير", icon: <ArrowRight />, onClick: onClose } as AseelToolbarAction]
      : []),
    { key: "new", label: "إضافة", icon: <Plus />, onClick: resetForm },
    {
      key: "save",
      label: saving ? "...تخزين" : "تخزين",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: !readOnly && !saving ? () => void handleSaveDraft() : undefined,
      disabled: readOnly || saving,
    },
    {
      key: "post",
      // P3-1-b: posting requires a server-side document number + journal
      // post — block visually when offline so the user is not misled.
      label: posting ? "...ترحيل" : !networkOnline ? "ترحيل (يتطلب اتصال)" : "ترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Send />,
      onClick:
        networkOnline &&
        !isPosted &&
        draftId != null &&
        journalPreview.balanced &&
        journalPreview.errors.length === 0 &&
        !posting
          ? () => void handlePost()
          : undefined,
      disabled:
        !networkOnline ||
        isPosted ||
        draftId == null ||
        !journalPreview.balanced ||
        journalPreview.errors.length > 0 ||
        posting,
      separatorBefore: true,
    },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: !isPosted ? resetForm : undefined,
      disabled: isPosted,
      danger: true,
    },
    {
      key: "receipt",
      label: "سند مالي",
      icon: <Receipt />,
      onClick: () => setActiveTabKey("payments"),
      separatorBefore: true,
    },
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => window.print() },
  ];

  const banner =
    localErr || msg ? (
      <div className={`aseel-banner ${localErr ? "aseel-banner--err" : "aseel-banner--ok"}`}>
        {localErr ? (
          <AlertCircle className="h-4 w-4 shrink-0" />
        ) : (
          <CheckCircle2 className="h-4 w-4 shrink-0" />
        )}
        <span>{localErr || msg}</span>
      </div>
    ) : null;

  // M3: non-blocking warning when one or more lines exceed available stock.
  const stockWarningBanner =
    overSellWarnings.length > 0 ? (
      <div
        className="aseel-banner"
        role="status"
        style={{
          backgroundColor: "#fef9c3",
          color: "#854d0e",
          border: "1px solid #fde047",
        }}
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        <span>
          تنبيه: الكمية تتجاوز المتوفر وسيصبح المخزون بالسالب —{" "}
          {overSellWarnings
            .map((w) => `«${w.sku}» (المطلوب ${w.qty} / المتوفر ${w.available})`)
            .join("، ")}
          . البيع مسموح ويمكنك المتابعة.
        </span>
      </div>
    ) : null;

  // M4: recover an autosaved-but-unsaved draft (only offered for a fresh invoice).
  const restoreBanner = recoverableDraft ? (
    <div className="aseel-banner aseel-banner--ok" role="status">
      <AlertCircle className="h-4 w-4 shrink-0" />
      <span>
        توجد مسودة غير محفوظة محليّاً (
        {new Date(recoverableDraft.updated_at).toLocaleString("ar")}). هل تريد
        استعادتها؟
      </span>
      <button
        type="button"
        className="mr-3 underline font-semibold hover:no-underline"
        onClick={() => {
          hydrateFromLocalDraft(recoverableDraft.data);
          setRecoverableDraft(null);
        }}
      >
        استعادة
      </button>
      <button
        type="button"
        className="mr-3 underline font-semibold hover:no-underline"
        onClick={() => {
          void db.invoice_drafts.delete("new");
          setRecoverableDraft(null);
        }}
      >
        تجاهل
      </button>
    </div>
  ) : null;

  const fld = (label: string, node: React.ReactNode) => (
    <label className="aseel-field">
      <span className="aseel-field-label">{label}</span>
      {node}
    </label>
  );

  /* ───────────── تبويب: معاينة القيد (M1-T4) ───────────── */
  const journalTab = (
    <div className="aseel-journal">
      {journalPreview.errors.length > 0 && (
        <div className="aseel-journal-errs">
          {journalPreview.errors.map((e, i) => (
            <div key={i} className="aseel-journal-err">
              <AlertCircle className="h-3 w-3 shrink-0" />
              <span>{e}</span>
            </div>
          ))}
        </div>
      )}
      {journalPreview.lines.length === 0 ? (
        <p className="aseel-journal-empty">أدخل الأسطر والحسابات لعرض القيد المحاسبي.</p>
      ) : (
        <table className="aseel-grid" data-variant="journal">
          <thead>
            <tr>
              <th>الحساب</th>
              <th style={{ width: "90px" }}>مدين</th>
              <th style={{ width: "90px" }}>دائن</th>
              <th style={{ width: "120px" }}>البيان</th>
            </tr>
          </thead>
          <tbody>
            {journalPreview.lines.map((l, i) => (
              <tr key={i}>
                <td>{l.accountLabel}</td>
                <td className="aseel-num">{l.debit > 0 ? fmt(l.debit) : "—"}</td>
                <td className="aseel-num">{l.credit > 0 ? fmt(l.credit) : "—"}</td>
                <td>{l.description || "—"}</td>
              </tr>
            ))}
            <tr className="aseel-row--total">
              <td>الإجمالي</td>
              <td className="aseel-num">{fmt(journalPreview.totalDebit)}</td>
              <td className="aseel-num">{fmt(journalPreview.totalCredit)}</td>
              <td>
                {journalPreview.balanced ? (
                  <span className="aseel-ok-text">متوازن ✓</span>
                ) : (
                  <span className="aseel-err-text">غير متوازن</span>
                )}
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );

  /* ───────────── تبويب: بيانات أخرى (تنبيهات الإعداد) ───────────── */
  const otherTab = (
    <div className="aseel-other">
      {revenueAccounts.length === 0 && (
        <div className="aseel-note aseel-note--err">
          لا توجد حسابات إيراد (Revenue) في شجرة الحسابات. شغّل
          <code> python manage.py seed_professional_coa </code>
          لإنشاء شجرة الحسابات الاحترافية (يشمل حساب مبيعات 4101).
        </div>
      )}
      {invType === "cash" && cashboxAccounts.length === 0 && (
        <div className="aseel-note aseel-note--warn">
          لا توجد حسابات صناديق/بنوك (Asset بكود 1101/1102/1103 أو باسم يحتوي صندوق/بنك).
        </div>
      )}
      {salesTaxRates.length === 0 && (
        <div className="aseel-note aseel-note--warn">
          لا توجد نسب ضريبة مبيعات (direction=sales/both). يُنشأ تلقائياً سجل 16% بعد
          الترحيلات أو أضف من الإدارة.
        </div>
      )}
      <label className="aseel-field aseel-field--inline">
        <input
          type="checkbox"
          disabled={readOnly}
          checked={stockOnPost}
          onChange={(e) => {
            setStockOnPost(e.target.checked);
            markDirty();
          }}
        />
        <span className="aseel-field-label" style={{ flex: "unset" }}>
          خصم المخزون عند الترحيل (إن أُلغيَ يُرحَّل لاحقاً مع أمر التسليم)
        </span>
      </label>
      <p className="aseel-hint">
        تُسجَّل القيود المحاسبية (عملاء/صندوق، مبيعات، ضريبة، تكلفة) عند «ترحيل» فقط، وليس
        عند «تخزين» المسودة.{stockOnPost ? "" : " (الخصم مؤجّل للتسليم.)"}
      </p>
    </div>
  );

  const paymentsTab = (
    <div className="aseel-legacy-tab space-y-4 p-4 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
      {/* Cash */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <label className="aseel-field">
          <span className="aseel-field-label">المبلغ نقدا</span>
          <input
            className="aseel-input"
            disabled={readOnly || isPosted}
            data-aseel-key="1"
            type="number"
            min={0}
            step={0.01}
            value={attachedCashAmount}
            onChange={(e) => {
              setAttachedCashAmount(e.target.value);
              markDirty();
            }}
          />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">حساب الصندوق</span>
          <select
            className="aseel-input"
            disabled={readOnly || isPosted}
            value={attachedCashAccountId}
            onChange={(e) => {
              setAttachedCashAccountId(e.target.value ? Number(e.target.value) : "");
              markDirty();
            }}
          >
            <option value="">— اختر —</option>
            {cashboxAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {(a.code || "") + " — " + (a.name || "")}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Cheques list */}
      <div style={{ marginTop: 12 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 4,
          }}
        >
          <strong>الشيكات المرفقة</strong>
          {!(readOnly || isPosted) && (
            <button
              type="button"
              className="aseel-toolbtn"
              onClick={() => {
                setAttachedCheques((cs) => [
                  ...cs,
                  {
                    cheque_number: "",
                    bank_name: "",
                    amount: "0.00",
                    due_date: "",
                    issue_date: "",
                    status: "Draft",
                  },
                ]);
                markDirty();
              }}
            >
              <Plus /> إضافة شيك
            </button>
          )}
        </div>
        <table className="aseel-grid">
          <thead>
            <tr>
              <th style={{ width: 110 }}>رقم الشيك</th>
              <th>البنك</th>
              <th style={{ width: 110 }}>المبلغ</th>
              <th style={{ width: 130 }}>تاريخ الاستحقاق</th>
              <th style={{ width: 110 }}>الحالة</th>
              {!(readOnly || isPosted) && <th style={{ width: 36 }}></th>}
            </tr>
          </thead>
          <tbody>
            {attachedCheques.length === 0 ? (
              <tr>
                <td
                  colSpan={readOnly || isPosted ? 5 : 6}
                  style={{ textAlign: "center", padding: 10 }}
                >
                  لا توجد شيكات مرفقة
                </td>
              </tr>
            ) : (
              attachedCheques.map((c, i) => (
                <tr key={i}>
                  <td>
                    <input
                      className="aseel-input"
                      disabled={readOnly || isPosted}
                      value={c.cheque_number}
                      onChange={(e) => {
                        setAttachedCheques((arr) =>
                          arr.map((x, j) =>
                            j === i
                              ? { ...x, cheque_number: e.target.value }
                              : x
                          )
                        );
                        markDirty();
                      }}
                    />
                  </td>
                  <td>
                    <input
                      className="aseel-input"
                      disabled={readOnly || isPosted}
                      value={c.bank_name || ""}
                      onChange={(e) => {
                        setAttachedCheques((arr) =>
                          arr.map((x, j) =>
                            j === i
                              ? { ...x, bank_name: e.target.value }
                              : x
                          )
                        );
                        markDirty();
                      }}
                    />
                  </td>
                  <td>
                    <input
                      className="aseel-input"
                      disabled={readOnly || isPosted}
                      data-aseel-key="1"
                      type="number"
                      min={0}
                      step={0.01}
                      value={c.amount}
                      onChange={(e) => {
                        setAttachedCheques((arr) =>
                          arr.map((x, j) =>
                            j === i
                              ? { ...x, amount: e.target.value }
                              : x
                          )
                        );
                        markDirty();
                      }}
                    />
                  </td>
                  <td>
                    <AseelDatePicker
                      className="aseel-input"
                      disabled={readOnly || isPosted}
                      value={c.due_date || ""}
                      onChange={(val) => {
                        setAttachedCheques((arr) =>
                          arr.map((x, j) =>
                            j === i ? { ...x, due_date: val } : x
                          )
                        );
                        markDirty();
                      }}
                    />
                  </td>
                  <td style={{ fontSize: "var(--aseel-fs-sm)" }}>
                    {c.status || "Draft"}
                  </td>
                  {!(readOnly || isPosted) && (
                    <td>
                      <button
                        type="button"
                        className="aseel-iconbtn aseel-iconbtn--danger"
                        onClick={() => {
                          setAttachedCheques((arr) =>
                            arr.filter((_, j) => j !== i)
                          );
                          markDirty();
                        }}
                        title="حذف"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Summary */}
      <div
        style={{
          marginTop: 12,
          padding: 6,
          background: "var(--aseel-panel)",
          border: "1px solid var(--aseel-border-soft)",
          borderRadius: "var(--aseel-radius)",
        }}
      >
        <div className="aseel-total-row">
          <span>إجمالي الفاتورة</span>
          <span className="aseel-total-value">
            {fmt(totals.grandTotal)}
          </span>
        </div>
        <div className="aseel-total-row">
          <span>نقدي</span>
          <span className="aseel-total-value">
            {fmt(Number(attachedCashAmount) || 0)}
          </span>
        </div>
        <div className="aseel-total-row">
          <span>شيكات</span>
          <span className="aseel-total-value">
            {fmt(
              attachedCheques.reduce(
                (s, c) => s + (Number(c.amount) || 0),
                0
              )
            )}
          </span>
        </div>
        <div className="aseel-total-row aseel-total-row--grand">
          <span>متبقي على ذمم العميل</span>
          <span className="aseel-total-value">
            {fmt(
              Math.max(
                0,
                totals.grandTotal -
                  (Number(attachedCashAmount) || 0) -
                  attachedCheques.reduce(
                    (s, c) => s + (Number(c.amount) || 0),
                    0
                  )
              )
            )}
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <div
      id="sales-invoice-print"
      dir="rtl"
      style={{ height: "100%", minHeight: 0, display: "flex", flexDirection: "column" }}
    >
      <AseelDocumentShell
        title="فاتورة مبيعات"
        state={docState}
        company={
          postedJournalId != null ? `قيد محاسبي #${postedJournalId}` : undefined
        }
        nav={nav}
        actions={toolbarActions}
        header={
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1px 16px", width: "100%" }}>
              {/* العمود 1 — بيانات الفاتورة */}
              <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
                {fld("رقم الفاتورة", <input className="aseel-input" readOnly value={invoiceNumber || "— جديدة —"} />)}
                {fld("التاريخ", <AseelDatePicker className="aseel-input" disabled={readOnly} value={invDate} onChange={(val) => { setInvDate(val); markDirty(); }} />)}
                {fld("تاريخ الاستحقاق", <AseelDatePicker className="aseel-input" disabled={readOnly} value={dueDate} onChange={(val) => { setDueDate(val); markDirty(); }} />)}
                {fld("تاريخ ثاني", <AseelDatePicker className="aseel-input" disabled={readOnly} value={secondDate} onChange={(val) => { setSecondDate(val); markDirty(); }} />)}
                {fld("دفتر", <input className="aseel-input" data-aseel-key="1" type="number" min={0} disabled={readOnly} value={bookNumber} onChange={(e) => { setBookNumber(e.target.value); markDirty(); }} title="0 = ترقيم يدوي · >0 = مسلسل مستقل لكل دفتر" />)}
              </div>
              {/* العمود 2 — العميل والدفع */}
              <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
                {fld("رقم الحساب / العميل", <div className="aseel-pickfield"><input className="aseel-input aseel-input--hl" data-aseel-field="customer" data-aseel-key="1" readOnly disabled={readOnly} value={selectedCustomer ? `#${selectedCustomer.id}` : ""} placeholder="+ للفهرس" onClick={() => !readOnly && setCustomerPickerOpen(true)} /><button type="button" className="aseel-ellipsis" disabled={readOnly} onClick={() => setCustomerPickerOpen(true)} title="فهرس الحسابات (+)">…</button></div>)}
                {fld("الاسم", <input className="aseel-input" readOnly value={selectedCustomer?.name ?? ""} />)}
                {selectedCustomer && creditHint && (() => {
                  const bal = Number(creditHint.open_balance);
                  const isDebtor = bal > 0.005;
                  const isCreditor = bal < -0.005;
                  const statusLabel = isDebtor ? "مدين" : isCreditor ? "دائن" : "متوازن";
                  const color = isDebtor ? "var(--aseel-status-debit)" : isCreditor ? "var(--aseel-status-credit)" : "var(--aseel-ink-soft)";
                  const ledgerAcct = selectedCustomer?.linked_account ?? null;
                  const canDrill = Boolean(onOpenGeneralLedger && ledgerAcct);
                  return (
                    <div className="aseel-field" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "2px 4px", background: "var(--aseel-panel)", fontSize: "var(--aseel-fs-sm)" }}>
                      <span className="aseel-field-label" style={{ fontWeight: "normal" }}>رصيد العميل:</span>
                      <span style={{ fontWeight: "bold" }}>
                        {canDrill ? (
                          <button
                            type="button"
                            className="underline hover:no-underline cursor-pointer"
                            style={{ color, background: "none", border: "none", padding: 0, font: "inherit" }}
                            title="فتح الأستاذ العام لحساب العميل"
                            onClick={() => onOpenGeneralLedger!(ledgerAcct as number)}
                          >
                            {fmt(Math.abs(bal))} ({statusLabel})
                          </button>
                        ) : (
                          <span style={{ color }}>
                            {fmt(Math.abs(bal))} ({statusLabel})
                          </span>
                        )}
                      </span>
                    </div>
                  );
                })()}
                {fld("نوع الدفع", <select className="aseel-input" disabled={readOnly} value={invType} onChange={(e) => { setInvType(e.target.value as "cash" | "credit"); markDirty(); }}><option value="credit">آجل (ذمم)</option><option value="cash">نقدي</option></select>)}
                {/* task16 D13: حساب الصندوق/البنك يُقرأ من إعدادات المبيعات (default_cash_account) — أُزيل المحدد من الفاتورة */}
              </div>
              {/* العمود 3 — العملة والحسابات */}
              <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
                <div style={{ display: "flex", gap: "4px" }}>
                  <div style={{ flex: 1 }}>{fld("العملة", <select className="aseel-input" disabled={readOnly} value={currencyId} onChange={(e) => { setCurrencyId(e.target.value ? Number(e.target.value) : ""); markDirty(); }}><option value="">—</option>{currencies.map((c) => (<option key={c.CurrencyID} value={c.CurrencyID}>{c.Code} {c.Name ? `— ${c.Name}` : ""}</option>))}</select>)}</div>
                  <div style={{ width: "80px" }}>{fld("سعر العملة", <input className="aseel-input" data-aseel-key="1" disabled={readOnly} value={exchangeRate} onChange={(e) => { setExchangeRate(e.target.value); markDirty(); }} />)}</div>
                </div>
                {/* task16 D13: حساب الإيراد يُقرأ من إعدادات المبيعات (default_revenue_account_product) — أُزيل المحدد من الفاتورة */}
                {fld("مشتغل مرخص", <input className="aseel-input" disabled={readOnly} value={licensedDealerNo} onChange={(e) => { setLicensedDealerNo(e.target.value); markDirty(); }} placeholder="رقم المشتغل المرخص" />)}
                {fld("فاتورة مقاصة", <input className="aseel-input" disabled={readOnly} value={settlementInvoiceNo} onChange={(e) => { setSettlementInvoiceNo(e.target.value); markDirty(); }} placeholder="رقم فاتورة المقاصة" />)}
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  {fld("خصم %", <input className="aseel-input" data-aseel-key="1" type="number" min={0} max={100} step={0.01} disabled={readOnly} value={discountPercent} onChange={(e) => { setDiscountPercent(e.target.value); markDirty(); }} title="نسبة الخصم الإضافية على الفاتورة (بعد خصم المبلغ)" />)}
                  <label style={{ display: "flex", alignItems: "center", gap: "4px", whiteSpace: "nowrap", fontSize: "var(--aseel-fs-sm)" }}><input type="checkbox" disabled={readOnly} checked={pricesIncludeTax} onChange={(e) => { setPricesIncludeTax(e.target.checked); markDirty(); }} /> الأسعار تشمل ض.ق.م</label>
                </div>
              </div>
            </div>
            
            <div style={{ marginTop: "2px" }}>
              {fld(
                "بحث / باركود",
                <input
                  className="aseel-input"
                  data-aseel-field="barcode"
                  disabled={readOnly}
                  value={productFilter}
                  onChange={(e) => setProductFilter(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleBarcodeEnter(productFilter);
                    }
                  }}
                  placeholder="اسم/SKU/Barcode ثم Enter — أو F6"
                />
              )}
            </div>
          </>
        }
        activeTab={activeTabKey}
        onTabChange={setActiveTabKey}
        tabs={[
          {
            key: "notes",
            label: "الملاحظات",
            content: (
              <textarea
                className="aseel-input"
                rows={3}
                style={{ width: "100%" }}
                disabled={readOnly}
                value={notes}
                onChange={(e) => {
                  setNotes(e.target.value);
                  markDirty();
                }}
              />
            ),
          },
          {
            key: "payments",
            label: "المقبوضات / السند المالي",
            content: paymentsTab,
          },
          {
            key: "accounts",
            label: "الحسابات / مركز التكلفة",
            content: journalTab,
          },
          { key: "other", label: "بيانات أخرى", content: otherTab },
        ]}
        totals={
          <>
            <div className="aseel-total-row">
              <span>مجموع البنود (قبل الخصم)</span>
              <span className="aseel-total-value">{fmt(grandSubtotalBeforeDiscount)}</span>
            </div>
            <div className="aseel-total-row">
              <span>خصم الفاتورة</span>
              <input
                className="aseel-input aseel-total-input"
                type="number"
                step="0.01"
                min="0"
                disabled={isPosted}
                value={invoiceDiscount}
                onChange={(e) => {
                  setInvoiceDiscount(e.target.value);
                  markDirty();
                }}
              />
            </div>
            <div className="aseel-total-row">
              <span>المجموع قبل الضريبة</span>
              <span className="aseel-total-value">{fmt(totals.subtotalExclTax)}</span>
            </div>
            {Number(discountPercent) > 0 && (
              <div className="aseel-total-row">
                <span>خصم مكتسب %</span>
                <span className="aseel-total-value">{discountPercent}%</span>
              </div>
            )}
            <div className="aseel-total-row">
              <span>الضريبة المضافة</span>
              <span className="aseel-total-value">{fmt(totals.taxAmount)}</span>
            </div>
            {journalPreview.revenue > 0 && journalPreview.cogs > 0 && (
              <div className="aseel-total-row">
                <span>الربح الإجمالي</span>
                <span
                  className="aseel-total-value"
                  style={{
                    color:
                      journalPreview.grossProfit >= 0 ? "var(--aseel-status-credit)" : "var(--aseel-status-debit)",
                  }}
                >
                  {fmt(journalPreview.grossProfit)} (
                  {journalPreview.marginPct.toFixed(1)}%)
                </span>
              </div>
            )}
            {creditHint &&
              (() => {
                const bal = Number(creditHint.open_balance);
                const isDebtor = bal > 0.005;
                const isCreditor = bal < -0.005;
                const statusLabel = isDebtor ? "مدين" : isCreditor ? "دائن" : "متوازن";
                const color = isDebtor
                  ? "var(--aseel-status-debit)"
                  : isCreditor
                  ? "var(--aseel-status-credit)"
                  : "var(--aseel-ink-soft)";
                const ledgerAcct = selectedCustomer?.linked_account ?? null;
                const canDrill = Boolean(onOpenGeneralLedger && ledgerAcct);
                return (
                  <div className="aseel-total-row">
                    <span>رصيد العميل</span>
                    <span className="aseel-total-value" style={{ color }}>
                      {canDrill ? (
                        <button
                          type="button"
                          className="underline hover:no-underline cursor-pointer"
                          style={{ color, background: "none", border: "none", padding: 0, font: "inherit" }}
                          title="فتح الأستاذ العام لحساب العميل"
                          onClick={() => onOpenGeneralLedger!(ledgerAcct as number)}
                        >
                          {fmt(Math.abs(bal))} ({statusLabel})
                        </button>
                      ) : (
                        <>
                          {fmt(Math.abs(bal))} ({statusLabel})
                        </>
                      )}
                    </span>
                  </div>
                );
              })()}
            {invType === "credit" && creditHint && (
              <div
                className={`aseel-total-row ${
                  creditHint.would_exceed ? "aseel-total-row--warn" : ""
                }`}
              >
                <span>الرصيد بعد الفاتورة</span>
                <span className="aseel-total-value">
                  {fmt(Number(creditHint.projected_balance))}
                </span>
              </div>
            )}
            <div className="aseel-total-row aseel-total-row--grand">
              <span>مبلغ الفاتورة الإجمالي</span>
              <span className="aseel-total-value">{fmt(totals.grandTotal)}</span>
            </div>
            
            {/* F2: المدفوع نقداً وشيكات مباشرة تحت الإجمالي */}
            <div className="aseel-total-row">
              <span>مدفوع نقداً</span>
              <span className="aseel-total-value">
                {readOnly || isPosted ? (
                  fmt(Number(attachedCashAmount) || 0)
                ) : (
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="aseel-input aseel-total-input"
                    value={attachedCashAmount}
                    onChange={(e) => {
                      setAttachedCashAmount(e.target.value);
                      markDirty();
                    }}
                  />
                )}
              </span>
            </div>
            
            <div className="aseel-total-row">
              <span>مدفوع شيكات</span>
              <span className="aseel-total-value">
                {readOnly || isPosted ? (
                  fmt(
                    attachedCheques.reduce(
                      (s, c) => s + (Number(c.amount) || 0),
                      0
                    )
                  )
                ) : (
                  <button
                    type="button"
                    className="underline hover:no-underline text-left cursor-pointer"
                    style={{ color: "var(--aseel-accent)", background: "none", border: "none", padding: 0, font: "inherit" }}
                    onClick={() => setActiveTabKey("payments")}
                    title="تعديل الشيكات المرفقة"
                  >
                    {fmt(
                      attachedCheques.reduce(
                        (s, c) => s + (Number(c.amount) || 0),
                        0
                      )
                    )}
                  </button>
                )}
              </span>
            </div>
            
            <div className="aseel-total-row">
              <span>المتبقي على الحساب</span>
              <span className="aseel-total-value">
                {fmt(
                  Math.max(
                    0,
                    totals.grandTotal -
                      (Number(attachedCashAmount) || 0) -
                      attachedCheques.reduce(
                        (s, c) => s + (Number(c.amount) || 0),
                        0
                      )
                  )
                )}
              </span>
            </div>
          </>
        }
        status={
          <>
            <span className="aseel-status-item">
              المستخدم <b>{currentUserName || "—"}</b>
            </span>
            <span className="aseel-status-item">
              رقم القيد <b>{postedJournalId ?? "—"}</b>
            </span>
            <span className="aseel-status-item">
              الحالة <b>{isPosted ? "مرحّلة" : draftId ? "مسودة" : "جديدة"}</b>
            </span>
            <span className="aseel-status-item">
              السجل <b>{nav.position}/{nav.total}</b>
            </span>
            <span className="aseel-status-item">
              آخر مفتاح <b>{lastKey}</b>
            </span>
            <span className="aseel-status-item">
              {readOnly ? "للقراءة فقط" : "قابل للتعديل ✓"}
            </span>
          </>
        }
      >
        {banner}
        {stockWarningBanner}
        {restoreBanner}
        <AseelGrid<DraftLine>
          columns={gridColumns}
          rows={lines}
          getCell={gridGetCell}
          getRowKey={(r) => r.key}
          onChange={readOnly ? undefined : gridOnChange}
          onAddRow={readOnly ? undefined : addRow}
          emptyHint="لا توجد بنود — أضف صنفاً (+ فهرس الأصناف)"
        />
      </AseelDocumentShell>

      {/* فهرس الحسابات (العميل) */}
      <AseelIndexPicker<PartnerRow>
        open={customerPickerOpen}
        title="فهرس الحسابات — العملاء"
        rows={customers}
        columns={[
          { key: "id", header: "الرقم", width: "70px", value: (r) => r.id },
          { key: "name", header: "الاسم", value: (r) => r.name },
          {
            key: "limit",
            header: "حد الائتمان",
            width: "120px",
            value: (r) => r.credit_limit ?? "—",
          },
        ]}
        getRowKey={(r) => r.id}
        searchValue={(r) => `${r.id} ${r.name}`}
        actionButton={
          <button
            type="button"
            onClick={() => setShowAddCustomerModal(true)}
            className="flex items-center gap-1 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
          >
            <Plus className="w-4 h-4" /> إضافة عميل
          </button>
        }
        onSelect={(r) => {
          setCustomerId(r.id);
          markDirty();
          setCustomerPickerOpen(false);
        }}
        onClose={() => setCustomerPickerOpen(false)}
      />

      {showAddCustomerModal && (
        // task16: إصلاح — كان يفتح SupplierModal (يُنشئ مورداً!)؛ الآن يُنشئ عميلاً
        <CustomerQuickAddModal
          isOpen={showAddCustomerModal}
          onClose={() => setShowAddCustomerModal(false)}
          onSaveSuccess={(newCustomer) => {
            setShowAddCustomerModal(false);
            setCustomerId(newCustomer.id);
            markDirty();
            setCustomerPickerOpen(false);
          }}
        />
      )}

      {/* فهرس الأصناف */}
      <SalesProductPickerModal
        isOpen={productPickerLineKey !== null}
        products={products}
        onSelect={(productId) => {
          if (productPickerLineKey) onSelectProduct(productPickerLineKey, productId);
          setProductPickerLineKey(null);
        }}
        onClose={() => setProductPickerLineKey(null)}
      />

      {/* Attached payment voucher modal removed - now a bottom tab */}
      {/* P3-2-b: stale-data confirmation portal for offline product picks */}
      {staleModal}
    </div>
  );
};

// وظائف duplicate غير مستخدمة هنا ولكن تبقى معروفة (duplicateSalesInvoice)
export { duplicateSalesInvoice };
