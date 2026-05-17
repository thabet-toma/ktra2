import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createSalesInvoice,
  duplicateSalesInvoice,
  getCreditPreview,
  getSalesInvoice,
  patchSalesInvoice,
  postSalesInvoice,
  type CreditPreviewResponse,
  type SalesInvoiceDetail,
} from "../../services/salesApi";
import { computeInvoiceTotals, type LineInput } from "../../utils/salesInvoiceMath";
import { apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Pencil,
  Plus,
  Printer,
  Save,
  Trash2,
} from "lucide-react";
import { SalesProductPickerModal, formatProductPrimaryName } from "./SalesProductPickerModal";

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
  salesSettings,
}) => {
  const [draftId, setDraftId] = useState<number | null>(null);
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
  const [lines, setLines] = useState<DraftLine[]>(() => [initialBlankLine()]);
  const [productFilter, setProductFilter] = useState("");
  const [taxEditKey, setTaxEditKey] = useState<string | null>(null);
  const [taxPercentDraft, setTaxPercentDraft] = useState<Record<string, string>>({});
  const [taxSavingKey, setTaxSavingKey] = useState<string | null>(null);
  const [productPickerLineKey, setProductPickerLineKey] = useState<string | null>(null);
  const [invoiceStatus, setInvoiceStatus] = useState<string>("draft");
  const [postedJournalId, setPostedJournalId] = useState<number | null>(null);

  const [saving, setSaving] = useState(false);
  const [posting, setPosting] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [creditHint, setCreditHint] = useState<CreditPreviewResponse | null>(null);
  const [showPreview, setShowPreview] = useState(true);

  const dirtyRef = useRef(false);

  const customers = useMemo(() => partners.filter((p) => p.partner_type === "Customer"), [partners]);

  const productsById = useMemo(() => {
    const m = new Map<number, ProductRow>();
    products.forEach((p) => m.set(p.id, p));
    return m;
  }, [products]);

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

  /** نسبة ض.ق.م الافتراضية 16% — من سجل VAT16 أو أقرب نسبة 16 في قائمة المبيعات */
  const defaultVatRateId = useMemo(() => {
    const byCode = salesTaxRates.find((t) => t.code === "VAT16");
    if (byCode) return byCode.id;
    const byRate = salesTaxRates.find((t) => Math.abs(Number(t.rate) - 16) < 0.02);
    return byRate?.id;
  }, [salesTaxRates]);

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
  } => {
    const errors: string[] = [];
    const out: PreviewLine[] = [];
    const grand = totals.grandTotal;
    const net = totals.subtotalExclTax;
    const tax = totals.taxAmount;

    if (grand <= 0) {
      return { lines: [], totalDebit: 0, totalCredit: 0, balanced: true, errors: [] };
    }

    // 1) المدين — العميل (آجل) أو الصندوق (نقدي)
    if (invType === "cash") {
      if (cashAccountId === "") {
        errors.push("اختر حساب الصندوق/البنك لفاتورة نقدية.");
      } else {
        const a = accountsById.get(Number(cashAccountId));
        out.push({
          accountId: Number(cashAccountId),
          accountLabel: a ? `${a.code || ""} — ${a.name || ""}` : `#${cashAccountId}`,
          debit: grand,
          credit: 0,
          description: "تحصيل نقدي",
        });
      }
    } else {
      const custName =
        customerId !== "" ? customers.find((c) => c.id === Number(customerId))?.name : "";
      out.push({
        accountId: null,
        accountLabel: custName
          ? `ذمم مدينة — ${custName}`
          : "ذمم مدينة (سيُحدَّد تلقائياً من linked_account للعميل)",
        debit: grand,
        credit: 0,
        description: "ذمم",
      });
    }

    // 2) الدائن — الإيراد
    if (revenueAccountId === "") {
      errors.push("اختر حساب الإيراد (Sales Revenue).");
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
    if (stockOnPost) {
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
    return { lines: out, totalDebit, totalCredit, balanced, errors };
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

  useEffect(() => {
    if (invType !== "credit" || customerId === "") {
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
  }, [invType, customerId, totals.grandTotal, draftId]);

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
  ]);

  const validateClient = (): string | null => {
    if (customerId === "") return "اختر العميل.";
    if (currencyId === "") return "اختر العملة.";
    if (invType === "cash" && cashAccountId === "")
      return "فواتير النقدي تتطلب حساب صندوق/بنك.";
    if (revenueAccountId === "") return "اختر حساب الإيراد (مبيعات).";
    const filled = lines.filter((l) => l.product !== "");
    if (!filled.length) return "أضف بنداً واحداً على الأقل.";
    for (const l of filled) {
      const q = Number(l.quantity);
      const p = Number(l.unit_price);
      if (!(q > 0)) return "الكمية يجب أن تكون أكبر من صفر في كل السطور المكتملة.";
      if (p < 0 || Number.isNaN(p)) return "سعر الوحدة غير صالح.";
      if (stockOnPost) {
        const pr = productsById.get(Number(l.product));
        if (pr && q > Number(pr.quantity_on_hand) + 1e-6) {
          return `الصنف «${pr.sku}»: الكمية (${q}) تتجاوز المتوفر (${pr.quantity_on_hand}).`;
        }
      }
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
      if (draftId) {
        const updated = await patchSalesInvoice(draftId, payload);
        applyDetail(updated);
        setMsg("تم حفظ المسودة.");
      } else {
        const created = await createSalesInvoice(payload);
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
      dirtyRef.current = false;
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
      onInvoiceSaved();
    } catch (e) {
      setLocalErr(e instanceof Error ? e.message : "فشل الترحيل");
    } finally {
      setPosting(false);
    }
  };

  const resetForm = () => {
    setDraftId(null);
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
    setMsg(null);
    setLocalErr(null);
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
    setLines((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
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

  const onSelectProduct = (key: string, productId: number) => {
    const pr = productsById.get(productId);
    const price =
      pr?.online_price != null && pr.online_price !== ""
        ? String(pr.online_price)
        : "0";
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

  return (
    <div
      id="sales-invoice-print"
      className="border border-gray-200 dark:border-gray-700 rounded-2xl overflow-hidden bg-white dark:bg-gray-900 shadow-sm"
      dir="rtl"
    >
      <div
        className={`px-6 py-4 text-white flex flex-wrap items-center gap-3 ${
          isPosted
            ? "bg-gradient-to-l from-blue-600 to-blue-700"
            : "bg-gradient-to-l from-emerald-600 to-emerald-700"
        }`}
      >
        <h2 className="text-lg font-bold">فاتورة مبيعات</h2>
        {draftId && (
          <span className="text-sm bg-white/20 px-2 py-0.5 rounded font-mono">
            {isPosted ? "مرحّلة" : "مسودة"} #{draftId}
          </span>
        )}
        {isPosted && postedJournalId != null && (
          <span className="text-sm bg-white/25 px-2 py-0.5 rounded font-mono inline-flex items-center gap-1">
            <CheckCircle2 className="h-3.5 w-3.5" />
            قيد #{postedJournalId}
          </span>
        )}
        <div className="mr-auto flex flex-wrap gap-2 print:hidden">
          <button
            type="button"
            onClick={() => window.print()}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white/15 hover:bg-white/25 text-sm"
          >
            <Printer className="h-4 w-4" />
            طباعة / PDF
          </button>
          <button
            type="button"
            onClick={resetForm}
            className="px-3 py-1.5 rounded-lg bg-white/15 hover:bg-white/25 text-sm"
          >
            فاتورة جديدة
          </button>
        </div>
      </div>

      <div className="p-4 md:p-6 space-y-4">
        {localErr && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-200 text-sm">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <span>{localErr}</span>
          </div>
        )}
        {msg && (
          <div className="p-3 rounded-lg bg-emerald-50 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-200 text-sm">
            {msg}
          </div>
        )}

        {/* تنبيهات الإعداد */}
        {revenueAccounts.length === 0 && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-900 dark:bg-red-900/30 dark:text-red-200 text-sm">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <div>
              <strong>لا توجد حسابات إيراد (Revenue) في شجرة الحسابات.</strong>
              <p className="mt-1">
                شغّل الأمر
                {" "}
                <code className="font-mono bg-red-100 dark:bg-red-900/60 px-1 rounded">
                  python manage.py seed_professional_coa
                </code>
                {" "}
                لإنشاء شجرة الحسابات الاحترافية (يشمل حساب مبيعات 4101).
              </p>
            </div>
          </div>
        )}
        {invType === "cash" && cashboxAccounts.length === 0 && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 dark:bg-amber-900/30 dark:text-amber-200 text-sm">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <span>
              لا توجد حسابات صناديق/بنوك (Asset بكود 1101/1102/1103 أو باسم يحتوي صندوق/بنك).
              أضف حساب صندوق من شجرة الحسابات.
            </span>
          </div>
        )}

        {invType === "credit" && creditHint && (
          <div
            className={`p-3 rounded-lg text-sm ${
              creditHint.would_exceed
                ? "bg-amber-50 border border-amber-200 text-amber-900 dark:bg-amber-900/20 dark:border-amber-700"
                : "bg-slate-50 dark:bg-slate-800/60"
            }`}
          >
            <strong>ائتمان:</strong> مفتوح {fmt(Number(creditHint.open_balance))} — حد:{" "}
            {creditHint.credit_limit != null ? fmt(Number(creditHint.credit_limit)) : "غير محدد"} — بعد
            الفاتورة: {fmt(Number(creditHint.projected_balance))}
            {creditHint.would_exceed && (
              <span className="font-semibold mr-2"> — تنبيه: تجاوز محتمل للحد.</span>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-gray-600 dark:text-gray-400">العميل *</span>
            <select
              disabled={readOnly}
              value={customerId}
              onChange={(e) => {
                setCustomerId(e.target.value ? Number(e.target.value) : "");
                markDirty();
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
            >
              <option value="">— اختر —</option>
              {customers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                  {p.credit_limit != null && p.credit_limit !== ""
                    ? ` — حد: ${p.credit_limit}`
                    : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-600 dark:text-gray-400">تاريخ الفاتورة</span>
            <input
              disabled={readOnly}
              type="date"
              value={invDate}
              onChange={(e) => {
                setInvDate(e.target.value);
                markDirty();
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-600 dark:text-gray-400">تاريخ الاستحقاق</span>
            <input
              disabled={readOnly}
              type="date"
              value={dueDate}
              onChange={(e) => {
                setDueDate(e.target.value);
                markDirty();
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-600 dark:text-gray-400">نوع الدفع</span>
            <select
              disabled={readOnly}
              value={invType}
              onChange={(e) => {
                setInvType(e.target.value as "cash" | "credit");
                markDirty();
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
            >
              <option value="credit">آجل (ذمم)</option>
              <option value="cash">نقدي</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-600 dark:text-gray-400">العملة *</span>
            <select
              disabled={readOnly}
              value={currencyId}
              onChange={(e) => {
                setCurrencyId(Number(e.target.value));
                markDirty();
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
            >
              <option value="">—</option>
              {currencies.map((c) => (
                <option key={c.CurrencyID} value={c.CurrencyID}>
                  {c.Code} {c.Name ? `— ${c.Name}` : ""}
                </option>
              ))}
            </select>
            {currencies.length === 0 ? (
              <span className="text-xs text-amber-700 dark:text-amber-300">
                لا توجد عملات محمّلة. تحقق من الاتصال بالخادم أو أضف عملات من المحاسبة.
              </span>
            ) : null}
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-600 dark:text-gray-400">سعر الصرف</span>
            <input
              disabled={readOnly}
              value={exchangeRate}
              onChange={(e) => {
                setExchangeRate(e.target.value);
                markDirty();
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 font-mono disabled:opacity-60"
            />
          </label>
          {/* خصم الفاتورة انتقل لصندوق الملخص أسفل البنود */}
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-gray-600 dark:text-gray-400">
              حساب الإيراد (Sales Revenue) *
            </span>
            <select
              disabled={readOnly}
              value={revenueAccountId}
              onChange={(e) => {
                setRevenueAccountId(e.target.value ? Number(e.target.value) : "");
                markDirty();
              }}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
            >
              <option value="">— اختر حساب مبيعات —</option>
              {revenueAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {(a.code || "") + " — " + (a.name || "")}
                </option>
              ))}
            </select>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              سيُسجَّل صافي المبيعات في هذا الحساب (دائن).
            </span>
          </label>
          {invType === "cash" && (
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="text-gray-600 dark:text-gray-400">حساب الصندوق / البنك *</span>
              <select
                disabled={readOnly}
                value={cashAccountId}
                onChange={(e) => {
                  setCashAccountId(e.target.value ? Number(e.target.value) : "");
                  markDirty();
                }}
                className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
              >
                <option value="">— اختر —</option>
                {cashboxAccounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {(a.code || "") + " — " + (a.name || "")}
                  </option>
                ))}
              </select>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                فقط الحسابات من نوع Asset بكود 1101/1102/1103 أو اسم يحتوي «صندوق/بنك».
              </span>
            </label>
          )}
          <label className="flex items-center gap-2 sm:col-span-2">
            <input
              type="checkbox"
              disabled={readOnly}
              checked={stockOnPost}
              onChange={(e) => {
                setStockOnPost(e.target.checked);
                markDirty();
              }}
            />
            <span className="text-gray-700 dark:text-gray-300">
              خصم المخزون عند الترحيل (إن أُلغيَ يُرحَّل لاحقاً مع أمر التسليم)
            </span>
          </label>
        </div>

        {salesTaxRates.length === 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
            <strong>الضريبة:</strong> لا توجد نسب مبيعات (direction=sales/both) في النظام.
            بعد تشغيل الترحيلات يُنشأ تلقائياً سجل 16% (VAT16) مربوط بحساب ضريبة مخرجات؛ أو
            أضف من الإدارة.
          </div>
        )}

        <div className="flex flex-wrap gap-2 items-center text-sm">
          <span className="text-gray-600 dark:text-gray-400">بحث / باركود:</span>
          <input
            disabled={readOnly}
            value={productFilter}
            onChange={(e) => setProductFilter(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleBarcodeEnter(productFilter);
              }
            }}
            placeholder="اسم، SKU، أو Barcode ثم Enter"
            className="flex-1 min-w-[200px] rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 disabled:opacity-60"
          />
        </div>

        <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-100 dark:bg-gray-800/80 text-gray-700 dark:text-gray-300">
              <tr>
                <th className="p-2 text-right w-10">#</th>
                <th className="p-2 text-right min-w-[220px]">الصنف *</th>
                <th className="p-2 text-right whitespace-nowrap">المتاح</th>
                <th className="p-2 text-right">الكمية</th>
                <th className="p-2 text-right">سعر الوحدة</th>
                <th className="p-2 text-right">خصم سطر</th>
                <th className="p-2 text-right">ضريبة</th>
                <th className="p-2 text-right whitespace-nowrap">صافي السطر</th>
                <th className="p-2 w-10 print:hidden" />
              </tr>
            </thead>
            <tbody>
              {lines.map((line, idx) => {
                const pr = line.product ? productsById.get(Number(line.product)) : undefined;
                const avail = pr ? Number(pr.quantity_on_hand) : null;
                const comp = totals.perLine[idx];
                const over =
                  stockOnPost && pr && Number(line.quantity) > (avail ?? 0) + 1e-6;
                return (
                  <tr
                    key={line.key}
                    className="border-t border-gray-100 dark:border-gray-800 align-top"
                  >
                    <td className="p-2 text-gray-500">{idx + 1}</td>
                    <td className="p-2">
                      <button
                        type="button"
                        disabled={readOnly}
                        onClick={() => setProductPickerLineKey(line.key)}
                        className="w-full max-w-md text-right rounded-xl border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 hover:border-emerald-500 hover:bg-emerald-50/60 dark:hover:bg-emerald-950/30 flex items-center justify-between gap-2 min-h-[42px] disabled:opacity-60 disabled:cursor-not-allowed"
                      >
                        <span
                          className={`truncate text-sm ${
                            pr ? "text-gray-900 dark:text-white font-medium" : "text-gray-400"
                          }`}
                        >
                          {pr ? formatProductPrimaryName(pr) : "— اختر صنفاً —"}
                        </span>
                        <ChevronDown className="h-4 w-4 shrink-0 text-gray-400" />
                      </button>
                    </td>
                    <td className="p-2 font-mono text-xs whitespace-nowrap">
                      {avail != null ? fmt(avail) : "—"}
                    </td>
                    <td className="p-2">
                      <input
                        disabled={readOnly}
                        value={line.quantity}
                        onChange={(e) => updateLine(line.key, { quantity: e.target.value })}
                        className="w-20 rounded border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-2 py-1 font-mono disabled:opacity-60"
                      />
                      {over && <div className="text-xs text-red-600 mt-1">تجاوز المخزون</div>}
                    </td>
                    <td className="p-2">
                      <input
                        disabled={readOnly}
                        value={line.unit_price}
                        onChange={(e) => updateLine(line.key, { unit_price: e.target.value })}
                        className="w-24 rounded border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-2 py-1 font-mono disabled:opacity-60"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        disabled={readOnly}
                        value={line.line_discount}
                        onChange={(e) => updateLine(line.key, { line_discount: e.target.value })}
                        className="w-20 rounded border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-2 py-1 font-mono disabled:opacity-60"
                      />
                    </td>
                    <td className="p-2">
                      <div className="flex items-start gap-1">
                        <div className="flex-1 min-w-[88px]">
                          {taxEditKey === line.key ? (
                            <input
                              type="number"
                              min={0}
                              max={100}
                              step={0.01}
                              disabled={taxSavingKey === line.key || readOnly}
                              value={taxPercentDraft[line.key] ?? ""}
                              onChange={(e) =>
                                setTaxPercentDraft((d) => ({
                                  ...d,
                                  [line.key]: e.target.value,
                                }))
                              }
                              onBlur={() => void commitTaxPercent(line.key)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  void commitTaxPercent(line.key);
                                }
                              }}
                              className="w-full rounded border border-emerald-400 dark:border-emerald-600 bg-white dark:bg-gray-800 px-2 py-1 text-xs font-mono"
                              placeholder="%"
                            />
                          ) : (
                            <select
                              disabled={readOnly}
                              value={line.tax_rate === null || line.tax_rate === "" ? "" : line.tax_rate}
                              onChange={(e) =>
                                updateLine(line.key, {
                                  tax_rate: e.target.value === "" ? null : Number(e.target.value),
                                })
                              }
                              className="w-full min-w-[100px] rounded border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-2 py-1 text-xs disabled:opacity-60"
                            >
                              <option value="">بدون</option>
                              {salesTaxRates.map((t) => (
                                <option key={t.id} value={t.id}>
                                  {t.name} ({t.rate}%)
                                </option>
                              ))}
                            </select>
                          )}
                        </div>
                        {!readOnly && (
                          <button
                            type="button"
                            title="تعديل النسبة يدوياً %"
                            className="print:hidden shrink-0 p-1.5 rounded text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-900/30"
                            onClick={() => {
                              if (taxEditKey === line.key) {
                                setTaxEditKey(null);
                                return;
                              }
                              setTaxEditKey(line.key);
                              const pctStr =
                                line.tax_rate != null && line.tax_rate !== ""
                                  ? String(
                                      salesTaxRates.find((t) => t.id === line.tax_rate)?.rate ?? "16"
                                    )
                                  : "16";
                              setTaxPercentDraft((d) => ({ ...d, [line.key]: pctStr }));
                            }}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="p-2 font-mono text-xs whitespace-nowrap">
                      {comp ? fmt(comp.lineTotal) : "—"}
                    </td>
                    <td className="p-2">
                      {!readOnly && (
                        <button
                          type="button"
                          onClick={() => removeRow(line.key)}
                          className="p-1.5 rounded text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 print:hidden"
                          title="حذف السطر"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {!readOnly && (
          <button
            type="button"
            onClick={addRow}
            className="print:hidden inline-flex items-center gap-2 px-4 py-2 rounded-lg border-2 border-dashed border-emerald-400 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 text-sm font-medium"
          >
            <Plus className="h-4 w-4" />
            إضافة سطر
          </button>
        )}

        <label className="flex flex-col gap-1 max-w-2xl">
          <span className="text-sm text-gray-600 dark:text-gray-400">ملاحظات</span>
          <textarea
            disabled={readOnly}
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              markDirty();
            }}
            rows={2}
            className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 text-sm disabled:opacity-60"
          />
        </label>

        {/* معاينة القيد المحاسبي — تُخفى إن كان show_journal_preview=false */}
        {salesSettings?.show_journal_preview !== false && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <button
            type="button"
            onClick={() => setShowPreview((s) => !s)}
            className={`w-full px-4 py-2.5 text-sm font-semibold flex items-center justify-between ${
              journalPreview.balanced && journalPreview.errors.length === 0
                ? "bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-slate-100"
                : "bg-amber-50 dark:bg-amber-900/30 text-amber-900 dark:text-amber-100"
            }`}
          >
            <span className="inline-flex items-center gap-2">
              {journalPreview.balanced && journalPreview.errors.length === 0 ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              ) : (
                <AlertCircle className="h-4 w-4 text-amber-600" />
              )}
              معاينة القيد المحاسبي (ستُسجَّل عند الترحيل)
            </span>
            <ChevronDown
              className={`h-4 w-4 transition-transform ${showPreview ? "rotate-180" : ""}`}
            />
          </button>
          {showPreview && (
            <div className="p-4 bg-white dark:bg-gray-900 space-y-3">
              {journalPreview.errors.length > 0 && (
                <div className="text-xs text-amber-800 dark:text-amber-200 space-y-1">
                  {journalPreview.errors.map((e, i) => (
                    <div key={i} className="flex items-start gap-1">
                      <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                      <span>{e}</span>
                    </div>
                  ))}
                </div>
              )}
              {journalPreview.lines.length === 0 ? (
                <p className="text-xs text-gray-500">أدخل الأسطر والحسابات لعرض القيد.</p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300">
                    <tr>
                      <th className="p-2 text-right">الحساب</th>
                      <th className="p-2 text-right font-mono">مدين</th>
                      <th className="p-2 text-right font-mono">دائن</th>
                      <th className="p-2 text-right">البيان</th>
                    </tr>
                  </thead>
                  <tbody>
                    {journalPreview.lines.map((l, i) => (
                      <tr
                        key={i}
                        className="border-t border-gray-100 dark:border-gray-800"
                      >
                        <td className="p-2">{l.accountLabel}</td>
                        <td className="p-2 font-mono">
                          {l.debit > 0 ? fmt(l.debit) : "—"}
                        </td>
                        <td className="p-2 font-mono">
                          {l.credit > 0 ? fmt(l.credit) : "—"}
                        </td>
                        <td className="p-2 text-gray-600 dark:text-gray-400">
                          {l.description || "—"}
                        </td>
                      </tr>
                    ))}
                    <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-semibold bg-gray-50 dark:bg-gray-800/50">
                      <td className="p-2">الإجمالي</td>
                      <td className="p-2 font-mono">{fmt(journalPreview.totalDebit)}</td>
                      <td className="p-2 font-mono">{fmt(journalPreview.totalCredit)}</td>
                      <td className="p-2">
                        {journalPreview.balanced ? (
                          <span className="text-emerald-700 dark:text-emerald-400 inline-flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" />
                            متوازن
                          </span>
                        ) : (
                          <span className="text-red-700 dark:text-red-400">
                            غير متوازن
                          </span>
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
        )}

        <div className="flex flex-wrap justify-between gap-4 items-end border-t border-gray-200 dark:border-gray-700 pt-4">
          <div className="space-y-2 text-sm bg-gray-50 dark:bg-gray-800/50 rounded-xl p-4 min-w-[320px]">
            <div className="flex justify-between gap-8">
              <span className="text-gray-600 dark:text-gray-400">مجموع البنود (قبل الخصم)</span>
              <span className="font-mono font-semibold">
                {fmt(
                  lines.reduce(
                    (s, l) =>
                      s +
                      Math.max(
                        (Number(l.quantity) || 0) * (Number(l.unit_price) || 0) -
                          (Number(l.line_discount) || 0),
                        0
                      ),
                    0
                  )
                )}
              </span>
            </div>
            <div className="flex justify-between gap-8 items-center">
              <span className="text-gray-600 dark:text-gray-400">خصم الفاتورة</span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={invoiceDiscount}
                onChange={(e) => setInvoiceDiscount(e.target.value)}
                disabled={isPosted}
                className="w-32 text-right font-mono px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-800 dark:text-white disabled:opacity-60"
              />
            </div>
            <div className="flex justify-between gap-8 border-t border-gray-200 dark:border-gray-700 pt-2">
              <span className="text-gray-600 dark:text-gray-400">المجموع قبل الضريبة</span>
              <span className="font-mono font-semibold">{fmt(totals.subtotalExclTax)}</span>
            </div>
            <div className="flex justify-between gap-8">
              <span className="text-gray-600 dark:text-gray-400">الضريبة</span>
              <span className="font-mono font-semibold">{fmt(totals.taxAmount)}</span>
            </div>
            <div className="flex justify-between gap-8 text-base border-t border-gray-200 dark:border-gray-600 pt-2 mt-2">
              <span className="font-bold text-gray-800 dark:text-white">الإجمالي</span>
              <span className="font-mono font-bold text-emerald-700 dark:text-emerald-400">
                {fmt(totals.grandTotal)}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 print:hidden">
            {!isPosted && (
              <>
                <button
                  type="button"
                  disabled={saving}
                  onClick={handleSaveDraft}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  حفظ مسودة
                </button>
                <button
                  type="button"
                  disabled={
                    posting ||
                    !draftId ||
                    !journalPreview.balanced ||
                    journalPreview.errors.length > 0
                  }
                  onClick={handlePost}
                  title={
                    !draftId
                      ? "احفظ المسودة أولاً"
                      : !journalPreview.balanced || journalPreview.errors.length > 0
                        ? "صحّح أخطاء معاينة القيد أولاً"
                        : ""
                  }
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {posting ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  ترحيل محاسبي
                </button>
              </>
            )}
            {isPosted && (
              <button
                type="button"
                onClick={resetForm}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700"
              >
                <Plus className="h-4 w-4" />
                فاتورة جديدة
              </button>
            )}
          </div>
        </div>

        <p className="text-xs text-gray-500 dark:text-gray-400">
          يتم خصم المخزون والقيود المحاسبية (عملاء / صندوق، مبيعات، ضريبة، تكلفة) عند «ترحيل محاسبي» فقط،
          وليس عند حفظ المسودة.
          {stockOnPost ? null : " (الخصم مؤجّل للتسليم.)"}
        </p>

        <SalesProductPickerModal
          isOpen={productPickerLineKey !== null}
          onClose={() => setProductPickerLineKey(null)}
          products={products}
          initialSearch={productFilter}
          onSelect={(pid) => {
            if (productPickerLineKey) onSelectProduct(productPickerLineKey, pid);
          }}
        />
      </div>
    </div>
  );
};

// وظائف duplicate غير مستخدمة هنا ولكن تبقى معروفة (duplicateSalesInvoice)
export { duplicateSalesInvoice };
