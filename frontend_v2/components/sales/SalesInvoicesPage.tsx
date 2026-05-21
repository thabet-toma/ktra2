import React, { useCallback, useEffect, useState } from "react";
import {
  listSalesInvoices,
  postSalesInvoice,
  createDeliveryOrder,
  deliverOrder,
  suggestFifoAllocations,
  duplicateSalesInvoice,
  deleteSalesInvoice,
  getSalesSettings,
  type SalesInvoiceRow,
  type FifoAllocationRow,
  type SalesSettings,
} from "../../services/salesApi";
import { apiGetList } from "../../services/restApi";
import {
  Loader2,
  RefreshCw,
  Receipt,
  Send,
  Truck,
  Pencil,
  Copy,
  Trash2,
} from "lucide-react";
import { SalesInvoiceEditor, type PartnerRow, type ProductRow } from "./SalesInvoiceEditor";
import { resolveTenantId } from "../../utils/tenantContext";
import { DataGrid, Toolbar, Badge } from "../../components/ui";

type CurrOpt = { CurrencyID: number; Code: string };
type AccountOpt = {
  id: number;
  code?: string | null;
  name?: string | null;
  account_type?: string | null;
};

/** فواتير المبيعات — محرر متعدد الأسطر، مخزون، عملات، ترحيل محاسبي */
export const SalesInvoicesPage: React.FC = () => {
  const [rows, setRows] = useState<SalesInvoiceRow[]>([]);
  const [partners, setPartners] = useState<PartnerRow[]>([]);
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [currencies, setCurrencies] = useState<CurrOpt[]>([]);
  const [accounts, setAccounts] = useState<AccountOpt[]>([]);
  const [taxRates, setTaxRates] = useState<
    {
      id: number;
      name: string;
      code: string;
      rate: string;
      tax_account?: number;
      direction?: string;
      tax_account_type?: string;
    }[]
  >([]);
  const [salesSettings, setSalesSettings] = useState<SalesSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [draftToEditId, setDraftToEditId] = useState<number | null>(null);

  const [fifoCustomerId, setFifoCustomerId] = useState<number | "">("");
  const [fifoAmount, setFifoAmount] = useState("");
  const [fifoRows, setFifoRows] = useState<FifoAllocationRow[]>([]);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    const parts = [
      "فواتير المبيعات",
      "العملاء",
      "الأصناف",
      "العملات",
      "الحسابات",
      "الضرائب",
    ] as const;
    const settled = await Promise.allSettled([
      listSalesInvoices(),
        apiGetList<PartnerRow>("partners/", { tenantId }),
      apiGetList<ProductRow>("inventory/products/", { tenantId }),
      apiGetList<CurrOpt>("accounting/currencies/", { tenantId }),
      apiGetList<AccountOpt>("accounting/accounts/", { tenantId }),
      apiGetList<{
        id: number;
        name: string;
        code: string;
        rate: string;
        tax_account?: number;
        direction?: string;
        tax_account_type?: string;
      }>("accounting/tax-rates/", { tenantId }),
    ]);
    const errs: string[] = [];
    settled.forEach((r, i) => {
      if (r.status === "rejected") {
        const msg =
          r.reason instanceof Error ? r.reason.message : String(r.reason ?? "خطأ");
        errs.push(`${parts[i]}: ${msg}`);
      }
    });
    if (settled[0].status === "fulfilled") setRows(settled[0].value);
    if (settled[1].status === "fulfilled") setPartners(settled[1].value);
    if (settled[2].status === "fulfilled") setProducts(settled[2].value);
    if (settled[3].status === "fulfilled") setCurrencies(settled[3].value);
    if (settled[4].status === "fulfilled")
      setAccounts(settled[4].value.filter((a) => a.id));
    if (settled[5].status === "fulfilled") setTaxRates(settled[5].value);
    try {
      const s = await getSalesSettings();
      setSalesSettings(s);
    } catch {
      // الإعدادات اختيارية — إن لم تكن موجودة نستمر بالقيم الافتراضية
    }
    if (errs.length) {
      setErr(
        errs.join(" — ") +
          (errs.some((e) => /401|مصادقة|Authentication|credentials/i.test(e))
            ? " (غالباً: سجّل الدخول في التطبيق أو انتهت صلاحية التوكن.)"
            : "")
      );
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fmt = (s: string | undefined) =>
    s ? Number(s).toLocaleString("en-US", { minimumFractionDigits: 2 }) : "—";

  const handleFifoSuggest = async () => {
    setErr(null);
    setFifoRows([]);
    if (fifoCustomerId === "" || !fifoAmount) {
      setErr("اختر العميل وأدخل مبلغ الدفعة لاقتراح FIFO.");
      return;
    }
    try {
      const rows = await suggestFifoAllocations({
        partner: Number(fifoCustomerId),
        amount: fifoAmount,
      });
      setFifoRows(rows);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الاقتراح");
    }
  };

  const handlePostRow = async (id: number) => {
    setErr(null);
    setMsg(null);
    try {
      await postSalesInvoice(id);
      setMsg(`تم ترحيل الفاتورة #${id}`);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  const handleDelivery = async (invoiceId: number, deliverNow = false) => {
    setErr(null);
    setMsg(null);
    try {
      const created = await createDeliveryOrder(invoiceId);
      if (deliverNow && created && typeof created.id === "number") {
        await deliverOrder(created.id);
        setMsg(
          `تم إنشاء أمر إخراج #${created.id} وتسليمه — خُصم المخزون وسُجِّل قيد COGS`,
        );
      } else {
        setMsg(`تم إنشاء أمر إخراج #${created.id} (قيد التنفيذ)`);
      }
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل أمر الإخراج");
    }
  };

  const handleDuplicate = async (id: number) => {
    setErr(null);
    setMsg(null);
    try {
      const d = await duplicateSalesInvoice(id);
      setMsg(`تم إنشاء نسخة مسودة ${d.invoice_number}`);
      setDraftToEditId(d.id);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل النسخ");
    }
  };

  const handleDeleteDraft = async (id: number) => {
    if (!window.confirm("حذف هذه المسودة نهائياً؟")) return;
    setErr(null);
    setMsg(null);
    try {
      await deleteSalesInvoice(id);
      setMsg("تم حذف المسودة.");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const fifoCustomers = partners.filter((p) => p.partner_type === "Customer");

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6" dir="rtl">
      <div className="flex items-center gap-3">
        <Receipt className="h-8 w-8 text-[var(--color-success)]" />
        <div>
          <h1 className="text-[var(--font-size-xl)] font-bold text-[var(--color-text)]">فواتير المبيعات</h1>
          <p className="text-[var(--font-size-sm)] text-[var(--color-text-muted)]">
            مسودة متعددة الأسطر → ترحيل محاسبي ومخزون — مرتبطة بالأصناف والعملات والعملاء
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="mr-auto inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-[var(--color-border)]"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          تحديث
        </button>
      </div>

      <Toolbar
        search={search}
        onSearch={setSearch}
        searchPlaceholder="بحث في الفواتير..."
      />

      {err && (
        <div className="p-4 rounded-lg bg-[var(--color-danger-light)] text-[var(--color-danger)]">{err}</div>
      )}
      {msg && (
        <div className="p-4 rounded-lg bg-[var(--color-success-light)] text-[var(--color-success)]">
          {msg}
        </div>
      )}

      <SalesInvoiceEditor
        products={products}
        partners={partners}
        currencies={currencies}
        accounts={accounts}
        taxRates={taxRates}
        draftToEditId={draftToEditId}
        onDraftEditConsumed={() => setDraftToEditId(null)}
        onInvoiceSaved={load}
        invoiceList={rows}
        salesSettings={salesSettings}
      />

      <section className="border border-dashed border-[var(--color-border)] rounded-xl p-4 space-y-3 bg-[var(--color-surface-2)]">
        <h2 className="font-semibold text-[var(--color-text)]">توزيع دفعة (FIFO)</h2>
        <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
          اقتراح تلقائي على الفواتير غير المسددة من الأقدم — يُنسخ لاحقاً عند تسجيل دفعة في الـ API.
        </p>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="flex flex-col gap-1 text-[var(--font-size-sm)]">
            <span>العميل</span>
            <select
              value={fifoCustomerId}
              onChange={(e) => setFifoCustomerId(e.target.value ? Number(e.target.value) : "")}
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-2 min-w-[200px]"
            >
              <option value="">—</option>
              {fifoCustomers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[var(--font-size-sm)]">
            <span>مبلغ الدفعة</span>
            <input
              value={fifoAmount}
              onChange={(e) => setFifoAmount(e.target.value)}
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-2 w-40"
              placeholder="0.00"
            />
          </label>
          <button
            type="button"
            onClick={handleFifoSuggest}
            className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--font-size-sm)]"
          >
            اقتراح FIFO
          </button>
        </div>
        {fifoRows.length > 0 && (
          <ul className="text-[var(--font-size-sm)] space-y-1 font-mono">
            {fifoRows.map((r) => (
              <li key={r.invoice}>{r.invoice_number}: {r.amount}</li>
            ))}
          </ul>
        )}
      </section>

      <DataGrid
        columns={[
          { key: "invoice_number", header: "رقم", render: (r) => <span className="font-mono">{r.invoice_number}</span> },
          { key: "customer", header: "العميل", render: (r) => r.customer_name || r.customer },
          { key: "invoice_date", header: "التاريخ" },
          { key: "invoice_type", header: "النوع", render: (r) => r.invoice_type === "cash" ? "نقدي" : "آجل" },
          { key: "status", header: "الحالة", render: (r) => <Badge variant={r.status === "posted" ? "success" : r.status === "draft" ? "warning" : "muted"}>{r.status === "posted" ? "مرحّلة" : r.status === "draft" ? "مسودة" : r.status}</Badge> },
          { key: "grand_total", header: "الإجمالي", render: (r) => <span className="font-mono">{fmt(r.grand_total)}</span> },
          { key: "amount_paid", header: "مدفوع", render: (r) => <span className="font-mono">{fmt(r.amount_paid)}</span> },
          { key: "balance", header: "متبقي", render: (r) => { const bal = Number(r.grand_total || 0) - Number(r.amount_paid || 0); return <span className={bal > 0 ? "text-[var(--color-danger)]" : "text-[var(--color-success)]"}>{bal.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>; } },
          { key: "actions", header: "إجراءات", align: "end", render: (r) => (
            <div className="flex flex-wrap gap-2 justify-end">
              {r.status === "draft" && (
                <>
                  <button type="button" onClick={() => setDraftToEditId(r.id)} className="inline-flex items-center gap-1 px-2 py-1 rounded border border-[var(--color-border)] text-[var(--font-size-xs)]" title="تعديل المسودة"><Pencil className="h-3 w-3" />تعديل</button>
                  <button type="button" onClick={() => handlePostRow(r.id)} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-[var(--color-primary)] text-white text-[var(--font-size-xs)]"><Send className="h-3 w-3" />ترحيل</button>
                  <button type="button" onClick={() => handleDuplicate(r.id)} className="inline-flex items-center gap-1 px-2 py-1 rounded border border-[var(--color-success)] text-[var(--color-success)] text-[var(--font-size-xs)]" title="نسخ إلى مسودة جديدة"><Copy className="h-3 w-3" />نسخ</button>
                  <button type="button" onClick={() => handleDeleteDraft(r.id)} className="inline-flex items-center gap-1 px-2 py-1 rounded border border-[var(--color-danger)] text-[var(--color-danger)] text-[var(--font-size-xs)]"><Trash2 className="h-3 w-3" />حذف</button>
                </>
              )}
              {r.status === "posted" && (
                <>
                  {!r.stock_on_post && <button type="button" onClick={() => { if (window.confirm("إصدار أمر إخراج وتسليم الآن؟ سيتم خصم المخزون وتسجيل قيد COGS.")) { handleDelivery(r.id, true); } }} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-[var(--color-primary)] text-white text-[var(--font-size-xs)]" title="إصدار أمر إخراج وتسليمه فوراً"><Truck className="h-3 w-3" />تسليم</button>}
                  <button type="button" onClick={() => handleDelivery(r.id, false)} className="inline-flex items-center gap-1 px-2 py-1 rounded border border-[var(--color-border)] text-[var(--font-size-xs)]" title="إنشاء أمر إخراج بدون تسليم"><Truck className="h-3 w-3" />أمر إخراج</button>
                  <button type="button" onClick={() => handleDuplicate(r.id)} className="inline-flex items-center gap-1 px-2 py-1 rounded border border-[var(--color-success)] text-[var(--color-success)] text-[var(--font-size-xs)]" title="نسخ إلى مسودة جديدة"><Copy className="h-3 w-3" />نسخ</button>
                </>
              )}
            </div>
          )},
        ]}
        data={rows.filter(r => !search || r.invoice_number?.includes(search) || r.customer_name?.includes(search) || r.customer?.includes(search))}
        loading={loading}
        emptyMessage={<div className="py-8 text-[var(--color-text-muted)]">لا توجد فواتير</div>}
      />
    </div>
  );
};
