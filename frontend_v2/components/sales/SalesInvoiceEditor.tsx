import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  attachPaymentVoucher,
  createCustomerPayment,
  createSalesInvoice,
  duplicateSalesInvoice,
  getCreditPreview,
  getCustomerPriceList,
  resolveSalePrice,
  postCustomerPayment,
  getNextInvoiceNumber,
  getSalesInvoice,
  patchSalesInvoice,
  postSalesInvoice,
  unpostSalesInvoice,
  type CreditPreviewResponse,
  type SalesInvoiceDetail,
  type SalesInvoiceRow,
} from "../../services/salesApi";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { useConfirm } from "../../contexts/ConfirmContext";
import { usePriceVisibility } from "../../contexts/PriceVisibilityContext";
import { useStaleConfirm } from "../offline/StaleDataConfirm";
import { DocumentPaymentsTab } from "../shared/DocumentPaymentsTab";
import { AseelDatePicker } from "../ui/AseelDatePicker";

import { ProductCardModal } from "../shared/ProductCardModal";
import { Item } from "../../types";
import db from "../../services/offline/db";
import { computeInvoiceTotals, type LineInput } from "../../utils/salesInvoiceMath";
import { formatMoney } from "../../utils/formatNumber";
import { openInNewTab } from "../../utils/openInNewTab";
import { clientLogger } from "../../services/logger";
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
  Undo2,
  Info,
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
  /** FEAT-2 edit-protection: مضبوط عندما يحرّر المستخدم سعر السطر يدوياً.
   *  السعر المقترح لا يُدَس على سطر مَلموس عند تغيير العميل. */
  priceTouched?: boolean;
  /** DEF-005: مصدر السعر المقترح للشارة — آخر فاتورة / عرض كرت الزبون / عرض واجهة العروض. */
  priceSource?: "last_invoice" | "quote" | "sales_quote" | null;
  /** رابط فتح مصدر السعر عند النقر (عرض العروض أو تبويب عرض السعر بكرت الزبون). */
  priceSourceLink?: string | null;
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
  initialCustomerId?: number;
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
    /** T-R3: تنبيه عند تكرار الصنف على سطر جديد (الافتراضي مُفعّل). */
    warn_on_duplicate_item?: boolean;
    /** منع حفظ/ترحيل فاتورة بيع بخسارة (الافتراضي مُعطّل). */
    block_loss_invoices?: boolean;
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
  initialCustomerId,
}) => {
  const confirm = useConfirm();
  // الربح الإجمالي يتبع زر العين (الخصوصية): يختفي حين تُخفى الأسعار/الأرباح.
  const { visible: profitVisible } = usePriceVisibility();
  const [draftId, setDraftId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<boolean>(!!draftToEditId);
  const [invoiceNumber, setInvoiceNumber] = useState<string>("");
  const [customerId, setCustomerId] = useState<number | "">(initialCustomerId || "");
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
  // DEF-007/008: بطاقة الصنف (مودال مشترك) — تُفتح من الشجرة/القائمة/سطر الفاتورة.
  const [cardProductId, setCardProductId] = useState<number | null>(null);
  // «موافق» (إضافة للفاتورة) يظهر فقط عند فتح البطاقة من الشجرة، لا من أيقونة (i).
  const [cardCanAdd, setCardCanAdd] = useState(false);
  // T-R2: السعر المقترح ومصدره — يُحسبان عند فتح البطاقة من الشجرة لعرضهما داخلها.
  const [cardSuggestedPrice, setCardSuggestedPrice] = useState<number | null>(null);
  const [cardPriceSource, setCardPriceSource] = useState<DraftLine["priceSource"]>(null);
  const [invoiceStatus, setInvoiceStatus] = useState<string>("draft");
  const [postedJournalId, setPostedJournalId] = useState<number | null>(null);
  // task18: المدفوع/الإجمالي المحفوظان — لحساب المتبقي عند تسجيل سند قبض على فاتورة مرحّلة.
  const [paidAmount, setPaidAmount] = useState(0);
  const [savedGrandTotal, setSavedGrandTotal] = useState(0);
  const [creatingReceipt, setCreatingReceipt] = useState(false);
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
    if (!stockOnPost) return [] as { name: string; qty: number; available: number }[];
    const out: { name: string; qty: number; available: number }[] = [];
    for (const l of lines) {
      if (l.product === "") continue;
      const pr = productsById.get(Number(l.product));
      if (!pr) continue;
      const q = Number(l.quantity) || 0;
      const avail = Number(pr.quantity_on_hand) || 0;
      if (q > avail + 1e-6) out.push({ name: pr.name_ar || pr.name_en || pr.sku, qty: q, available: avail });
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

  // T-CASH2: في البيع النقدي «المبلغ نقداً» = إجمالي الفاتورة دائماً (للعرض فقط؛
  // التسوية تتمّ خادمياً بالكامل بسند قبض مستقل عند الترحيل). يبقى الحقل مُعطَّلاً
  // ومتزامناً مع الإجمالي. لا يلمس فواتير «الذمم» (قيمتها يدوية).
  useEffect(() => {
    if (invoiceStatus === "posted" || invType !== "cash") return;
    const g = String(totals.grandTotal || 0);
    setAttachedCashAmount((prev) => (prev === g ? prev : g));
  }, [invType, totals.grandTotal, invoiceStatus]);

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

  // T-A4: صندوق الدفعة النقدية المرفقة يتبع «الصندوق الافتراضي» من إعدادات المبيعات
  // تلقائياً — لا اختيار صندوق لكل فاتورة (أُزيل المنتقي من الشاشة).
  useEffect(() => {
    if (attachedCashAccountId !== "") return;
    if (salesSettings?.default_cash_account) setAttachedCashAccountId(salesSettings.default_cash_account);
    else if (cashboxAccounts.length) setAttachedCashAccountId(cashboxAccounts[0].id);
  }, [attachedCashAccountId, salesSettings?.default_cash_account, cashboxAccounts]);

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
    setPaidAmount(Number((d as { amount_paid?: number | string }).amount_paid ?? 0));
    setSavedGrandTotal(Number((d as { grand_total?: number | string }).grand_total ?? 0));
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
        // FEAT-2: أسعار فاتورة محمَّلة مُثبّتة — لا يُعاد تسعيرها عند تغيير العميل.
        priceTouched: true,
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
    setViewMode(true);
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
  const readOnly = isPosted || viewMode;

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
            // FEAT-2: أسعار مستعادة من المسودة مُثبّتة — لا يُعاد تسعيرها تلقائياً.
            priceTouched: true,
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

  // منع فاتورة الخسارة (إعداد اختياري) — يُطابق الحارس الخادمي في post_sales_invoice.
  // يُرجع رسالة الخطأ إن كان البيع بخسارة والمنع مُفعّل، وإلا null.
  const lossBlockMessage = (): string | null => {
    if (
      salesSettings?.block_loss_invoices &&
      journalPreview.cogs > 0 &&
      journalPreview.grossProfit < 0
    ) {
      return (
        `لا يُسمح بحفظ فاتورة بخسارة (الربح الإجمالي ${fmt(journalPreview.grossProfit)}). ` +
        "سعر البيع أقل من التكلفة — عدّل الأسعار أو عطّل المنع من إعدادات المبيعات."
      );
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
    const lossErr = lossBlockMessage();
    if (lossErr) {
      setLocalErr(lossErr);
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

      // Auto-save payment voucher — للفواتير الآجلة فقط. البيع النقدي يُسوّى
      // خادمياً بالكامل (سند قبض تلقائي) فلا حاجة لسند نقدي مرفق (T-CASH2).
      if (activeDraftId && invType !== "cash") {
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
    const lossErr = lossBlockMessage();
    if (lossErr) {
      setLocalErr(lossErr);
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
      // T-CASH2: تسوية البيع النقدي تتمّ خادمياً ذرّياً مع الترحيل (سند قبض مستقل).
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

  // Feature 1: التراجع عن الترحيل — حذف قيود الفاتورة وإرجاعها مسودة قابلة للتعديل/الحذف.
  const handleUnpost = async () => {
    if (!draftId) return;
    if (!(await confirm({
      message:
        "هذا المستند مرحَّل. سيؤدي التراجع عن الترحيل إلى حذف كل قيود اليومية " +
        "وحركات المخزون الخاصة بهذه الفاتورة وإرجاعها مسودة. متابعة؟",
      confirmText: "متابعة",
    }))) return;
    setLocalErr(null);
    setMsg(null);
    setPosting(true);
    try {
      const inv = await unpostSalesInvoice(draftId);
      setInvoiceStatus(inv.status || "draft");
      setPostedJournalId(inv.journal ?? null);
      setMsg("تم التراجع عن الترحيل وحذف القيود. الفاتورة الآن مسودة.");
      onInvoiceSaved();
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "تعذر التراجع عن الترحيل");
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
    setInvType("credit");
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

  // T-R4: حارس التغييرات غير المحفوظة — يُستدعى من «إضافة/جديدة» و«إلغاء». بدل
  // التجاهل الصامت للعمل، يسأل المستخدم ويُتيح الحفظ قبل المغادرة (سلوك احترافي).
  const guardedReset = async () => {
    const hasContent = lines.some((l) => l.product !== "" && l.product !== -1);
    if (!isPosted && dirtyRef.current && hasContent) {
      const proceed = await confirm({
        message: "لديك تغييرات غير محفوظة في هذه الفاتورة. المتابعة بفاتورة جديدة؟",
        confirmText: "متابعة",
        cancelText: "عودة",
        danger: false,
      });
      if (!proceed) return;
      const save = await confirm({
        message: "هل تريد حفظ هذه الفاتورة قبل البدء بفاتورة جديدة؟",
        confirmText: "حفظ ثم جديدة",
        cancelText: "تجاهل التغييرات",
        danger: false,
      });
      if (save) {
        await handleSaveDraft();
        resetForm();
        return;
      }
    }
    resetForm();
  };

  const addRow = () => {
    if (readOnly) return;
    setLines((prev) => [...prev, makeEmptyLine()]);
    markDirty();
  };

  /** يُدرج صنفاً في أول سطر فارغ (أو سطر جديد) ثم يجلب سعره — مدخل موحّد
   *  للشجرة وزر «موافق» في بطاقة الصنف. */
  const insertProductIntoInvoice = (
    productId: number,
    opts?: { quantity?: number; unitPrice?: number; source?: DraftLine["priceSource"] }
  ) => {
    if (!productId || readOnly || isPosted) return;
    // T-R3/M5: Duplicate checking logic has been moved to onSelectProduct 
    // to unify behavior across both tree picker and inline combobox.
    let targetKey = "";
    setLines((prev) => {
      const emptyIdx = prev.findIndex((l) => l.product === "" && !l.description);
      if (emptyIdx >= 0) {
        targetKey = prev[emptyIdx].key;
        const next = [...prev];
        next[emptyIdx] = { ...next[emptyIdx], product: -1 };
        return next;
      }
      const newLine = makeEmptyLine();
      newLine.product = -1;
      targetKey = newLine.key;
      return [...prev, newLine];
    });
    setTimeout(() => onSelectProduct(targetKey, productId, opts), 0);
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
      // T-R1: أبقِ سطراً فارغاً واحداً فقط في الذيل. أضِف سطراً جديداً عندما يكتسب
      // آخر سطر صنفاً حقيقياً فقط — لا بناءً على الكمية. (الخلل السابق: makeEmptyLine
      // يبدأ بالكمية "1" فكان كل سطر فارغ يُحسب «ممتلئاً» وتتكاثر السطور الوهمية.)
      const lastHasProduct = lastLine && lastLine.product !== "" && lastLine.product !== -1;
      if (lastHasProduct) {
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

  // DEF-005: ترجمة نوع مصدر السعر من الـ resolver إلى شارة السطر.
  const priceSourceFromResolve = (docType?: string): DraftLine["priceSource"] => {
    if (docType === "SALES_INVOICE") return "last_invoice";
    if (docType === "SALES_QUOTATION") return "sales_quote";
    if (docType === "CUSTOMER_QUOTE") return "quote";
    return null;
  };
  // رابط فتح مصدر السعر: عرض «واجهة العروض» أو تبويب «عرض السعر» بكرت الزبون.
  const priceSourceLinkFromResolve = (
    source?: { document_type?: string; document_id?: number | null },
  ): string | null => {
    if (source?.document_type === "SALES_QUOTATION" && source.document_id != null)
      return `/sales/quotations?open=${source.document_id}`;
    if (source?.document_type === "CUSTOMER_QUOTE" && customerId !== "")
      return `/partners/${customerId}?tab=price_list`;
    return null;
  };

  const onSelectProduct = async (
    key: string,
    productId: number,
    opts?: { quantity?: number; unitPrice?: number; source?: DraftLine["priceSource"] }
  ) => {
    const pr = productsById.get(productId);

    // T-R3 / M5: تنبيه عند تكرار الصنف (نفس سلوك فاتورة الشراء)
    const isDuplicate = lines.some(
      (l) => l.key !== key && l.product !== "" && l.product !== -1 && Number(l.product) === Number(productId)
    );
    if (isDuplicate && (salesSettings?.warn_on_duplicate_item ?? true)) {
      const merge = await confirm({
        message: `الصنف «${pr?.name_ar || productId}» مضاف مسبقاً في الفاتورة. اختر الإجراء:`,
        confirmText: "دمج الكمية",
        cancelText: "سطر جديد مستقل",
        danger: false,
      });
      if (merge) {
        // ابحث عن السطر الأصلي الذي يحوي هذا الصنف واجمع الكميات
        setLines((prev) => {
          const next = [...prev];
          const dupIndex = next.findIndex(
            (l) => l.key !== key && l.product !== "" && l.product !== -1 && Number(l.product) === Number(productId)
          );
          if (dupIndex >= 0) {
            const addedQty = opts?.quantity ?? 1;
            next[dupIndex] = {
              ...next[dupIndex],
              quantity: String((Number(next[dupIndex].quantity) || 0) + addedQty),
            };
          }
          // أفرغ السطر الحالي (الذي اختار فيه المستخدم الصنف المكرر)
          const currentIdx = next.findIndex((l) => l.key === key);
          if (currentIdx >= 0) {
            next[currentIdx] = { ...next[currentIdx], product: "", quantity: "0", unit_price: "0", priceTouched: false };
          }
          return next;
        });
        markDirty();
        return;
      }
    }

    // T-R2: عند تمرير سعر من بطاقة الصنف نستخدمه ونثبّته (priceTouched) فلا يدهسه
    // الـ resolver؛ وإلا نبدأ بسعر البيع الافتراضي ثم نقترح عبر الـ resolver.
    const price =
      opts?.unitPrice != null
        ? String(opts.unitPrice)
        : pr?.online_price != null && pr.online_price !== ""
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
      priceSource: opts?.source ?? null,
      // سعر مُدخَل من البطاقة = مُثبّت (لا يُعاد تسعيره تلقائياً).
      ...(opts?.unitPrice != null ? { quantity: String(opts.quantity ?? 1), priceTouched: true } : {}),
    });
    // FEAT-2 / DEF-005: اقترح سعر الوحدة عبر PriceResolver المشترك — آخر سعر
    // دفعه هذا العميل لهذا الصنف (يفوز دائماً)، ثم عرض السعر اليدوي، ثم سعر البيع
    // الافتراضي، ثم فارغ. القيمة تبقى قابلة للتعديل، ولا تُدَس على سطر حرّره
    // المستخدم يدوياً (edit-protection). الشارة تعكس مصدر السعر.
    if (networkOnline && opts?.unitPrice == null) {
      resolveSalePrice({
        product: productId,
        customer: customerId,
        currency: currencyId,
        exchange_rate: exchangeRate,
        tax_inclusive: pricesIncludeTax,
      })
        .then((res) => {
          if (res?.unit_price == null) return;
          const src = priceSourceFromResolve(res.source?.document_type);
          const link = priceSourceLinkFromResolve(res.source);
          // DEF-003: عرض السعر المقترح بمنزلتين (يبقى قابلاً للتحرير).
          const shown = Number(res.unit_price);
          const priceStr = Number.isNaN(shown) ? String(res.unit_price) : shown.toFixed(2);
          setLines((prev) =>
            prev.map((r) =>
              r.key === key && !r.priceTouched
                ? { ...r, unit_price: priceStr, priceSource: src, priceSourceLink: link }
                : r,
            ),
          );
        })
        .catch(() => { /* لا سجل سابق — نُبقي السعر الافتراضي */ });
    }
  };

  // FEAT-2: عند تغيير العميل بعد وجود بنود، أعِد تسعير الأسطر غير المَلموسة فقط
  // (أسعار محمَّلة/مُحرَّرة يدوياً = priceTouched، فلا تُمَسّ). أول تحميل/عميل
  // افتراضي بلا بنود = لا عملية.
  const prevCustomerRef = React.useRef<number | "" | null>(null);
  useEffect(() => {
    if (prevCustomerRef.current === null) {
      prevCustomerRef.current = customerId;
      return;
    }
    if (prevCustomerRef.current === customerId) return;
    prevCustomerRef.current = customerId;
    if (customerId === "" || !networkOnline) return;
    let cancelled = false;
    // اقرأ اللقطة الحالية للأسطر دون إعادة رندر (إرجاع نفس المرجع).
    setLines((snapshot) => {
      snapshot
        .filter((l) => l.product !== "" && !l.priceTouched)
        .forEach((l) => {
          resolveSalePrice({
            product: Number(l.product),
            customer: customerId,
            currency: currencyId,
            exchange_rate: exchangeRate,
            tax_inclusive: pricesIncludeTax,
          })
            .then((res) => {
              if (cancelled || res?.unit_price == null) return;
              const src = priceSourceFromResolve(res.source?.document_type);
              const link = priceSourceLinkFromResolve(res.source);
              const shown = Number(res.unit_price);
              const priceStr = Number.isNaN(shown) ? String(res.unit_price) : shown.toFixed(2);
              setLines((cur) =>
                cur.map((r) =>
                  r.key === l.key && !r.priceTouched
                    ? { ...r, unit_price: priceStr, priceSource: src, priceSourceLink: link }
                    : r,
                ),
              );
            })
            .catch(() => { /* لا سجل سابق للعميل الجديد — نُبقي السعر */ });
        });
      return snapshot;
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId]);

  const handleBarcodeEnter = (raw: string) => {
    const t = raw.trim();
    if (!t) return;
    const byBar = products.find((p) => (p.barcode || "").trim() === t || p.sku === t || String(p.id) === t);
    if (byBar) {
      const emptyIdx = lines.findIndex((l) => l.product === "");
      let key = "";
      if (emptyIdx >= 0) {
        key = lines[emptyIdx].key;
      } else {
        const newLine = makeEmptyLine();
        setLines((prev) => [...prev, newLine]);
        key = newLine.key;
      }
      onSelectProduct(key, byBar.id);
      setProductFilter("");
    }
  };

  // G1: عرض موحّد بلا أصفار عشرية زائدة (مع فاصل آلاف للمبالغ).
  const fmt = (n: number) => formatMoney(n);

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
        setActiveTabKey("financial_movements");
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
    // FEAT-2: تحرير السعر يدوياً يضع علامة «مَلموس» فلا يُعاد تسعيره تلقائياً.
    else if (key === "unit_price") updateLine(row.key, { unit_price: value, priceTouched: true, priceSource: null });
    else if (key === "line_discount") updateLine(row.key, { line_discount: value });
  };

  /* task24: خريطة سعر العميل (آخر بيع/عرض سعر) لكامل الكتالوج — تُجلب دفعة واحدة
     عند تغيّر العميل لعرض السعر داخل خيارات المنتقي بلا نقر. */
  const [customerPriceMap, setCustomerPriceMap] = useState<
    Map<number, { price: string; source: "last_invoice" | "quote"; prices?: any[] }>
  >(new Map());
  useEffect(() => {
    if (customerId === "" || !networkOnline) { setCustomerPriceMap(new Map()); return; }
    let cancelled = false;
    getCustomerPriceList(customerId)
      .then((rows) => {
        if (cancelled) return;
        const m = new Map<number, { price: string; source: "last_invoice" | "quote"; prices?: any[] }>();
        for (const r of rows) {
          if (r.price != null && Number(r.price) > 0) {
            m.set(r.product_id, { price: r.price, source: r.source, prices: r.prices });
          }
        }
        setCustomerPriceMap(m);
      })
      .catch(() => { if (!cancelled) setCustomerPriceMap(new Map()); });
    return () => { cancelled = true; };
  }, [customerId, networkOnline]);

  /* task13 M5: منتقي مدمج — الكتابة في الخلية تفلتر الأصناف فورياً وتعبئ
     السطر (المودال الكامل يبقى متاحاً من زر «…» واختصار +). لا خيار «صنف حر»
     هنا لأن سطر فاتورة المبيعات يتطلب صنفاً معرّفاً في المخزون. */
  const productOptions = useMemo(
    () => products.map((p) => {
      // task24: السعر المقترح يظهر داخل الخيار مباشرة (بلا نقر): آخر بيع/عرض سعر
      // لهذا العميل من خريطة العميل، وإلا سعر البيع الافتراضي للصنف.
      const cp = customerPriceMap.get(p.id);
      let price: string | undefined;
      let priceLabel: string | undefined;
      let prices: any[] | undefined;
      if (cp) {
        price = formatMoney(Number(cp.price));
        priceLabel = cp.source === "quote" ? "عرض سعر" : "آخر بيع";
        prices = cp.prices?.map((pr: any) => ({
          label: pr.label,
          value: formatMoney(Number(pr.unit_price)),
          link: pr.document_id ? `/sales/invoices/${pr.document_id}` : undefined,
        }));
      } else if (p.online_price != null && p.online_price !== "" && Number(p.online_price) > 0) {
        price = formatMoney(Number(p.online_price));
        priceLabel = "افتراضي";
      } else {
        // لا آخر بيع لهذا العميل ولا عرض سعر ولا سعر بيع افتراضي.
        priceLabel = "بدون سعر";
      }
      return {
        id: p.id,
        label: formatProductPrimaryName(p),
        price,
        priceLabel,
        prices,
      };
    }),
    [products, customerPriceMap],
  );

  const renderProductCell = (row: DraftLine, ri: number) => {
    const selectedId = row.product && Number(row.product) > 0 ? Number(row.product) : null;
    return (
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <AseelAutocomplete
        value={(() => {
          const pr = row.product ? productsById.get(Number(row.product)) : undefined;
          return pr ? formatProductPrimaryName(pr) : "";
        })()}
        options={productOptions}
        disabled={readOnly}
        placeholder="اكتب اسم الصنف…"
        onPick={(id) => {
          void onSelectProduct(row.key, Number(id));
          setTimeout(() => {
            document.getElementById(`aseel-grid-input-${ri}-quantity`)?.focus();
          }, 50);
        }}
        onInfo={(id) => { setCardCanAdd(false); setCardProductId(Number(id)); }}
      />
      {/* DEF-008: أيقونة (i) بجانب المنتج المختار على السطر → بطاقة الصنف */}
      {selectedId != null && (
        <button
          type="button"
          className="aseel-ellipsis"
          onClick={() => { setCardCanAdd(false); setCardProductId(selectedId); }}
          title="بطاقة الصنف"
        ><Info className="w-3.5 h-3.5" /></button>
      )}
      {/* DEF-005: شارة مصدر السعر المقترح */}
      {row.priceSource === "last_invoice" && (
        <span className="aseel-price-badge aseel-price-badge--last" title="السعر من آخر فاتورة لهذا العميل">من آخر فاتورة</span>
      )}
      {(row.priceSource === "quote" || row.priceSource === "sales_quote") && (() => {
        // sales_quote ⇒ عرض «واجهة العروض»؛ quote ⇒ عرض كرت الزبون (رابط احتياطي).
        const link = row.priceSourceLink
          ?? (row.priceSource === "quote" && customerId !== "" ? `/partners/${customerId}?tab=price_list` : null);
        const title = row.priceSource === "sales_quote" ? "فتح عرض السعر في واجهة العروض" : "فتح عرض السعر في كرت الزبون";
        return link ? (
          <button
            type="button"
            className="aseel-price-badge aseel-price-badge--quote"
            style={{ cursor: "pointer", textDecoration: "underline" }}
            title={title}
            onClick={() => {
              clientLogger.info("invoice.open_quote", { source: row.priceSource, link });
              openInNewTab(link);
            }}
          >من عرض السعر</button>
        ) : (
          <span className="aseel-price-badge aseel-price-badge--quote" title="السعر من عرض السعر">من عرض السعر</span>
        );
      })()}
      <button
        type="button"
        className="aseel-ellipsis"
        disabled={readOnly}
        onClick={() => setProductPickerLineKey(row.key)}
        title="فهرس الأصناف الكامل (+)"
      >…</button>
    </div>
    );
  };

  const renderUnitPriceCell = (row: DraftLine) => {
    const p = row.product ? productsById.get(Number(row.product)) : undefined;
    const cost = p ? Number(p.avg_cost || 0) : 0;
    const price = Number(row.unit_price || 0);
    const belowCost = cost > 0 && price > 0 && price < cost;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "2px", alignItems: "center" }}>
        <input
          className={`aseel-input ${belowCost ? "border-red-500 focus:ring-red-500" : ""}`}
          type="text"
          inputMode="decimal"
          value={row.unit_price}
          disabled={readOnly || isPosted}
          style={{ textAlign: "center", ...(belowCost ? { color: "#ef4444", borderColor: "#ef4444" } : {}) }}
          onChange={(e) => {
            updateLine(row.key, { unit_price: e.target.value, priceTouched: true, priceSource: null });
          }}
        />
        {belowCost && (
          <span style={{ color: "#ef4444", fontSize: "0.65rem", whiteSpace: "nowrap", fontWeight: "bold" }}>
            أقل من التكلفة ({fmt(cost)})
          </span>
        )}
      </div>
    );
  };


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
  gridColumns[4].render = renderUnitPriceCell;
  gridColumns[6].render = renderTaxCell;
  gridColumns[8].render = renderDeleteCell;

  // task18: تسجيل «سند قبض» على فاتورة مرحّلة (CustomerPayment مستقل مُخصَّص لها).
  // يعالج بلاغ المالك: بعد الترحيل لا يمكن تحصيل فاتورة آجلة من داخل الشاشة.
  const remainingDue = Math.max(savedGrandTotal - paidAmount, 0);
  const handleCreateReceipt = async () => {
    if (!draftId || customerId === "") return;
    if (remainingDue <= 0) {
      setMsg("الفاتورة مسدَّدة بالكامل — لا متبقٍّ.");
      return;
    }
    const cashAcc = salesSettings?.default_cash_account ?? cashboxAccounts[0]?.id;
    if (!cashAcc) {
      setLocalErr("لا يوجد حساب صندوق — عيّنه في إعدادات المبيعات.");
      return;
    }
    const amtStr = window.prompt(
      `مبلغ سند القبض (المتبقي على الفاتورة ${remainingDue.toFixed(2)}):`,
      remainingDue.toFixed(2),
    );
    if (amtStr == null) return;
    const amt = Number(amtStr);
    if (!(amt > 0) || amt > remainingDue + 0.001) {
      setLocalErr("مبلغ غير صالح (يجب أن يكون بين 0 والمتبقي).");
      return;
    }
    setCreatingReceipt(true);
    setLocalErr(null);
    setMsg(null);
    try {
      const pay = await createCustomerPayment({
        partner: Number(customerId),
        payment_date: new Date().toISOString().slice(0, 10),
        amount: amt,
        currency: Number(currencyId),
        exchange_rate: Number(exchangeRate) || 1,
        cash_or_bank_account: Number(cashAcc),
        notes: `سند قبض فاتورة ${invoiceNumber}`,
        allocations: [{ invoice: draftId, amount: amt }],
      });
      await postCustomerPayment(pay.id);
      setMsg("تم تسجيل سند القبض وترحيله، وخُصِم من رصيد الفاتورة.");
      await loadInvoice(draftId); // يحدّث amount_paid/payment_status
      onInvoiceSaved();
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "تعذّر تسجيل سند القبض");
    } finally {
      setCreatingReceipt(false);
    }
  };

  const toolbarActions: AseelToolbarAction[] = [
    // task16: زر صريح للعودة لقائمة الفواتير (إلى جانب ✕ إغلاق في الإطار)
    ...(onClose
      ? [{ key: "back", label: "الفواتير", icon: <ArrowRight />, onClick: onClose } as AseelToolbarAction]
      : []),
    { key: "new", label: "إضافة", icon: <Plus />, onClick: guardedReset },
    ...(viewMode && !isPosted ? [{
      key: "edit",
      label: "تحرير",
      icon: <Pencil />,
      onClick: () => setViewMode(false),
      separatorBefore: true,
    } as AseelToolbarAction] : []),
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
      key: "unpost",
      label: posting ? "...تراجع" : "تراجع عن الترحيل",
      icon: posting ? <Loader2 className="animate-spin" /> : <Undo2 />,
      onClick: isPosted && !posting ? () => void handleUnpost() : undefined,
      disabled: !isPosted || posting,
    },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: !isPosted ? guardedReset : undefined,
      disabled: isPosted,
      danger: true,
    },
    {
      // task18: على المسودة يفتح تبويب السند المرفق؛ على الفاتورة المرحّلة
      // يُنشئ سند قبض مستقلاً ويُرحّله (تحصيل الآجل من داخل الشاشة).
      key: "receipt",
      label: isPosted
        ? creatingReceipt
          ? "...سند قبض"
          : remainingDue > 0
            ? "سند قبض"
            : "مسدَّدة"
        : "سند مالي",
      icon: creatingReceipt ? <Loader2 className="animate-spin" /> : <Receipt />,
      onClick: isPosted
        ? remainingDue > 0 && !creatingReceipt
          ? () => void handleCreateReceipt()
          : undefined
        : () => setActiveTabKey("financial_movements"),
      disabled: isPosted && (remainingDue <= 0 || creatingReceipt),
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
            .map((w) => `«${w.name}» (المطلوب ${w.qty} / المتوفر ${w.available})`)
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
        onClick={async () => {
          if (dirtyRef.current) {
            const confirmed = await confirm({
              message: "لديك تعديلات غير محفوظة حالياً. هل أنت متأكد من استعادة المسودة وفقدان هذه التعديلات؟",
              confirmText: "استعادة",
              cancelText: "إلغاء",
              danger: false,
            });
            if (!confirmed) return;
          }
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
            disabled={readOnly || isPosted || invType === "cash"}
            title={invType === "cash" ? "بيع نقدي — مدفوع بالكامل ويُسوّى تلقائياً عند الترحيل" : undefined}
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
          {/* T-A4: الصندوق الافتراضي من الإعدادات (للعرض فقط) — لا اختيار لكل فاتورة. */}
          <input
            className="aseel-input"
            readOnly
            title="الصندوق الافتراضي مضبوط في إعدادات المبيعات"
            value={(() => {
              const a = attachedCashAccountId !== "" ? accountsById.get(Number(attachedCashAccountId)) : undefined;
              return a ? `${a.code || ""} — ${a.name || ""}` : "الصندوق الافتراضي (من الإعدادات)";
            })()}
          />
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
          <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 p-1.5 flex flex-col gap-1 w-full shadow-sm">
            <div className="flex flex-col xl:flex-row gap-2 items-start">
              
              {/* Customer Section */}
              <div className="flex-1 flex flex-col gap-1 xl:border-l border-gray-100 dark:border-gray-700 pl-2 w-full">
                <div className="flex items-center gap-1">
                  <span className="font-bold text-gray-800 dark:text-gray-100 min-w-[35px] text-xs">العميل</span>
                  <div className="flex-1 relative min-w-[120px]">
                    <input 
                      className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded px-1.5 py-0.5 text-xs focus:ring-1 focus:ring-emerald-500 outline-none cursor-pointer"
                      readOnly 
                      disabled={readOnly} 
                      value={selectedCustomer ? `#${selectedCustomer.id} - ${selectedCustomer.name}` : ""} 
                      placeholder="اختر عميلاً..." 
                      onClick={() => !readOnly && setCustomerPickerOpen(true)}
                    />
                  </div>
                  {selectedCustomer && (
                    <button
                      type="button"
                      className="shrink-0 text-emerald-600 hover:text-emerald-700 text-[10px] underline px-1"
                      title="فتح بطاقة العميل في تبويب جديد"
                      onClick={() => openInNewTab(`/partners/${selectedCustomer.id}`)}
                    >
                      بطاقة
                    </button>
                  )}
                  <select
                    className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-xs rounded px-1 py-0.5 focus:ring-1 focus:ring-emerald-500 outline-none"
                    disabled={readOnly}
                    value={invType}
                    onChange={(e) => { setInvType(e.target.value as "cash" | "credit"); markDirty(); }}
                  >
                    <option value="credit">أجل</option>
                    <option value="cash">نقدي</option>
                  </select>
                </div>

                {selectedCustomer && creditHint && (() => {
                  const bal = Number(creditHint.open_balance);
                  const isDebtor = bal > 0.005;
                  const isCreditor = bal < -0.005;
                  const statusLabel = isDebtor ? "عليه" : isCreditor ? "له" : "متوازن";
                  const color = isDebtor ? "text-red-600 dark:text-red-400" : isCreditor ? "text-emerald-600 dark:text-emerald-400" : "text-gray-500";
                  const ledgerAcct = selectedCustomer?.linked_account ?? null;
                  const canDrill = Boolean(onOpenGeneralLedger && ledgerAcct);

                  const balAfterRaw = bal + totals.grandTotal - (Number(attachedCashAmount) || 0) - attachedCheques.reduce((s, c) => s + (Number(c.amount) || 0), 0);
                  const isDebtorAfter = balAfterRaw > 0.005;
                  const isCreditorAfter = balAfterRaw < -0.005;
                  const statusLabelAfter = isDebtorAfter ? "عليه" : isCreditorAfter ? "له" : "متوازن";
                  const colorAfter = isDebtorAfter ? "text-red-600 dark:text-red-400" : isCreditorAfter ? "text-emerald-600 dark:text-emerald-400" : "text-gray-500";

                  return (
                    <div className="flex items-center flex-wrap gap-x-2 gap-y-0.5 text-[11px]">
                      <div className="flex items-center gap-1">
                        <span className="text-gray-500">سابق:</span>
                        {canDrill ? (
                          <button type="button" className={`font-bold hover:underline ${color}`} onClick={() => onOpenGeneralLedger!(ledgerAcct as number)}>
                            {fmt(Math.abs(bal))} <span className="font-normal opacity-80">{statusLabel}</span>
                          </button>
                        ) : (
                          <span className={`font-bold ${color}`}>
                            {fmt(Math.abs(bal))} <span className="font-normal opacity-80">{statusLabel}</span>
                          </span>
                        )}
                      </div>
                      <span className="text-gray-300 dark:text-gray-600 hidden sm:inline">|</span>
                      <div className="flex items-center gap-1">
                        <span className="text-gray-500">متوقع:</span>
                        <span className={`font-bold ${colorAfter}`}>
                          {fmt(Math.abs(balAfterRaw))} <span className="font-normal opacity-80">{statusLabelAfter}</span>
                        </span>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* Barcode Search */}
              <div className="w-full xl:w-[250px] shrink-0 flex flex-col gap-0.5 xl:border-l border-gray-100 dark:border-gray-700 pl-2 justify-center">
                 <div className="flex justify-between items-end">
                   <label className="text-[10px] font-bold text-emerald-700 dark:text-emerald-400">بحث سريع / باركود (F6)</label>
                 </div>
                 <div className="relative">
                   <div className="absolute inset-y-0 right-0 flex items-center pr-1.5 pointer-events-none">
                     <Search className="w-3 h-3 text-emerald-500" />
                   </div>
                   <input
                    className="w-full bg-emerald-50/50 dark:bg-emerald-900/10 border border-emerald-300 dark:border-emerald-800/60 rounded px-2 py-0.5 pr-6 text-xs font-bold focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 outline-none placeholder:text-gray-400 placeholder:font-normal"
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
                    placeholder="الاسم/SKU/الباركود ⏎"
                  />
                 </div>
              </div>

              {/* Invoice Metadata */}
              <div className="w-full xl:w-[280px] shrink-0 flex flex-col gap-1">
                <div className="flex justify-between items-center text-xs pb-0.5 border-b border-gray-100 dark:border-gray-700">
                  <span className="font-bold text-gray-800 dark:text-gray-100">الفاتورة</span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-extrabold">{invoiceNumber || "جديدة"}</span>
                </div>
                <div className="flex gap-1">
                  <div className="flex items-center gap-1 flex-1">
                    <span className="text-gray-500 text-[10px] min-w-[30px]">تاريخ</span>
                    <input type="date" className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-emerald-500 text-[11px]" disabled={readOnly} value={invDate} onChange={(e) => { setInvDate(e.target.value); markDirty(); }} />
                  </div>
                  <div className="flex items-center gap-1 flex-1">
                    <span className="text-gray-500 text-[10px] min-w-[35px]">استحقاق</span>
                    <input type="date" className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded px-1 py-0.5 outline-none focus:ring-1 focus:ring-emerald-500 text-[11px]" disabled={readOnly} value={dueDate} onChange={(e) => { setDueDate(e.target.value); markDirty(); }} />
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-1">
                    <span className="text-gray-500 text-[10px] min-w-[30px]">عملة</span>
                    <select className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded px-1 py-0.5 text-[11px] outline-none focus:ring-1 focus:ring-emerald-500" disabled={readOnly} value={currencyId} onChange={(e) => { setCurrencyId(e.target.value ? Number(e.target.value) : ""); markDirty(); }}>
                      <option value="">—</option>
                      {currencies.map((c) => (<option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>))}
                    </select>
                  </div>
                  <label className="flex items-center gap-1 text-[11px] font-bold cursor-pointer text-gray-700 dark:text-gray-300">
                    <input type="checkbox" className="rounded text-emerald-600 focus:ring-emerald-500 w-3 h-3" disabled={readOnly} checked={pricesIncludeTax} onChange={(e) => { setPricesIncludeTax(e.target.checked); markDirty(); }} /> 
                    شامل الضريبة
                  </label>
                </div>
              </div>

            </div>
          </div>
        }
        activeTab={activeTabKey}
        onTabChange={setActiveTabKey}
        tabs={[
          {
            // task18: إعادة تبويب «ملاحظات» (نُقل سابقاً للأسفل) — المفتاح يطابق activeTabKey الافتراضي.
            key: "notes",
            label: "ملاحظات",
            content: (
              <textarea
                className="aseel-input"
                style={{ width: "100%", minHeight: "90px" }}
                placeholder="ملاحظات الفاتورة…"
                disabled={readOnly}
                value={notes}
                onChange={(e) => { setNotes(e.target.value); markDirty(); }}
              />
            ),
          },
          {
            // task18: تبويب «أرصدة العميل» (الرصيد الحالي/بعد الفاتورة من الـ subledger).
            key: "balances",
            label: "أرصدة العميل",
            content: (
              <div className="text-sm" style={{ padding: "8px", display: "flex", flexDirection: "column", gap: "6px" }}>
                {!selectedCustomer ? (
                  <span className="text-gray-500">اختر عميلاً لعرض رصيده.</span>
                ) : creditHint ? (
                  <>
                    <div className="aseel-total-row"><span>الرصيد الحالي</span><span className="aseel-total-value">{fmt(Number(creditHint.open_balance))}</span></div>
                    <div className="aseel-total-row"><span>الرصيد المتوقع بعد الفاتورة</span><span className="aseel-total-value">{fmt(Number(creditHint.projected_balance))}</span></div>
                    {creditHint.would_exceed && <span className="aseel-err-text">⚠ يتجاوز حد الائتمان</span>}
                  </>
                ) : (
                  <span className="text-gray-500">جارٍ حساب الرصيد…</span>
                )}
              </div>
            ),
          },
          {
            key: "accounts",
            label: "الحسابات / مركز التكلفة",
            content: journalTab,
          },
          { key: "other", label: "بيانات أخرى", content: otherTab },
          ...(draftId && Number(draftId) > 0 ? [{
            key: "financial_movements",
            label: "الحركات المالية المرتبطة",
            content: (
              <DocumentPaymentsTab 
                referenceType="SALES_INVOICE" 
                referenceId={draftId} 
                searchQuery={invoiceNumber}
              />
            ),
          }] : []),
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
            {profitVisible && journalPreview.revenue > 0 && journalPreview.cogs > 0 && (
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
                {readOnly || isPosted || invType === "cash" ? (
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
                    onClick={() => setActiveTabKey("financial_movements")}
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
        {/* الشجرة انتقلت إلى الشريط الجانبي (aside) ليرتفع لأعلى المستند. */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "8px" }}>
            <AseelGrid<DraftLine>
              columns={gridColumns}
              rows={lines}
              getCell={gridGetCell}
              getRowKey={(r) => r.key}
              onChange={readOnly ? undefined : gridOnChange}
              onAddRow={readOnly ? undefined : addRow}
              emptyHint="لا توجد بنود — أضف صنفاً (+ فهرس الأصناف)"
            />
            {/* DEF-006: السطر الجديد يُضاف فقط عبر هذا الزر الصريح (لا من نقر خارجي/شجرة). */}
            {!readOnly && (
              <button type="button" className="aseel-addrow" onClick={addRow}>
                <Plus className="h-3 w-3" /> إضافة سطر
              </button>
            )}

            {/* INLINE FOOTER: Payments, Notes, and GL Preview instead of Tabs */}
            <div style={{ display: "flex", gap: "16px", background: "var(--aseel-panel)", padding: "8px", border: "1px solid var(--aseel-border)" }}>
              {/* Cash & Notes Area */}
              <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "8px" }}>
                <div style={{ display: "flex", gap: "8px" }}>
                  <label className="aseel-field" style={{ flex: 1 }}>
                    <span className="aseel-field-label">المبلغ نقداً</span>
                    <input
                      className="aseel-input"
                      disabled={readOnly || isPosted || invType === "cash"}
                      title={invType === "cash" ? "بيع نقدي — مدفوع بالكامل ويُسوّى تلقائياً عند الترحيل" : undefined}
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
                  <label className="aseel-field" style={{ flex: 1 }}>
                    <span className="aseel-field-label">حساب الصندوق</span>
                    {/* T-A4: الصندوق الافتراضي من الإعدادات (للعرض فقط) — لا اختيار لكل فاتورة. */}
                    <input
                      className="aseel-input"
                      readOnly
                      title="الصندوق الافتراضي مضبوط في إعدادات المبيعات"
                      value={(() => {
                        const a = attachedCashAccountId !== "" ? accountsById.get(Number(attachedCashAccountId)) : undefined;
                        return a ? `${a.code || ""} — ${a.name || ""}` : "الصندوق الافتراضي (من الإعدادات)";
                      })()}
                    />
                  </label>
                </div>
                <label className="aseel-field">
                  <span className="aseel-field-label">الملاحظات</span>
                  <textarea
                    className="aseel-input"
                    rows={2}
                    disabled={readOnly}
                    value={notes}
                    onChange={(e) => {
                      setNotes(e.target.value);
                      markDirty();
                    }}
                  />
                </label>
              </div>

              {/* Cheques Area */}
              <div style={{ flex: 1, borderRight: "1px solid var(--aseel-border)", paddingRight: "16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                  <strong>الشيكات المرفقة ({attachedCheques.length})</strong>
                  {!(readOnly || isPosted) && (
                    <button
                      type="button"
                      className="aseel-toolbtn"
                      onClick={() => {
                        setAttachedCheques((cs) => [
                          ...cs,
                          { cheque_number: "", bank_name: "", amount: "0.00", status: "Draft" },
                        ]);
                        markDirty();
                      }}
                    >
                      <Plus className="w-3 h-3" /> إضافة
                    </button>
                  )}
                </div>
                {attachedCheques.length === 0 ? (
                  <div className="text-sm text-gray-500 mt-2">لا توجد شيكات.</div>
                ) : (
                  <div style={{ maxHeight: "80px", overflowY: "auto" }}>
                    {attachedCheques.map((c, i) => (
                      <div key={i} style={{ display: "flex", gap: "4px", marginBottom: "4px" }}>
                        <input
                          className="aseel-input"
                          placeholder="رقم الشيك"
                          disabled={readOnly || isPosted}
                          value={c.cheque_number}
                          onChange={(e) => {
                            setAttachedCheques((arr) => arr.map((x, j) => j === i ? { ...x, cheque_number: e.target.value } : x));
                            markDirty();
                          }}
                        />
                        <input
                          className="aseel-input"
                          placeholder="المبلغ"
                          disabled={readOnly || isPosted}
                          value={c.amount}
                          onChange={(e) => {
                            setAttachedCheques((arr) => arr.map((x, j) => j === i ? { ...x, amount: e.target.value } : x));
                            markDirty();
                          }}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            {/* Warnings */}
            {revenueAccounts.length === 0 && (
              <div className="aseel-note aseel-note--err">لا توجد حسابات إيراد. شغّل seed_professional_coa.</div>
            )}
            {salesTaxRates.length === 0 && (
              <div className="aseel-note aseel-note--warn">لا توجد نسبة ضريبة مبيعات مسجلة في الإعدادات.</div>
            )}
          </div>
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

      {/* DEF-007/008: بطاقة الصنف المشتركة */}
      {cardProductId != null && (
        <ProductCardModal
          productId={cardProductId}
          productName={(() => { const p = products.find((x) => x.id === cardProductId); return p ? (p.name_ar || p.name_en || p.sku) : undefined; })()}
          addMode={cardCanAdd && !readOnly && !isPosted}
          suggestedPrice={cardSuggestedPrice}
          priceSource={cardPriceSource}
          onConfirm={cardCanAdd && !readOnly && !isPosted ? (opts) => insertProductIntoInvoice(cardProductId, opts) : undefined}
          onClose={() => setCardProductId(null)} />
      )}

      {/* Attached payment voucher modal removed - now a bottom tab */}
      {/* P3-2-b: stale-data confirmation portal for offline product picks */}
      {staleModal}
    </div>
  );
};

// وظائف duplicate غير مستخدمة هنا ولكن تبقى معروفة (duplicateSalesInvoice)
export { duplicateSalesInvoice };
