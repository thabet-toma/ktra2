import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Truck,
  Plus,
  Pencil,
  Trash2,
  Send,
  RotateCcw,
  Package,
  AlertCircle,
  X,
  RefreshCw,
  Link as LinkIcon,
} from "lucide-react";
import {
  listLocalShipments,
  createLocalShipment,
  updateLocalShipment,
  deleteLocalShipment,
  postLocalShipment,
  unpostLocalShipment,
  importLocalShipmentToInvoice,
  type LocalShipmentRow,
  type LocalShipmentCreate,
  type LocalShipmentPaymentType,
  type LocalShipmentStatus,
} from "@/services/localShippingApi";
import {
  listClearances,
  formatClearanceShipmentLine,
  type ClearanceRow,
} from "@/services/clearanceApi";
import { accountingApi } from "@/services/accountingApi";
import { apiGetList } from "@/services/restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { getSalesSettings, type SalesSettings } from "@/services/salesApi";
import { validatePaymentInput } from "@/utils/usePaymentForm";
import { DataGrid, Toolbar, Drawer, Badge } from "../../components/ui";

type Partner = { id: number; name: string; partner_type?: string };
type Account = { id: number; code: string; name: string; account_type?: string };
type Currency = { CurrencyID: number; Code: string };
type PurchaseInvoiceMini = {
  id: number;
  invoice_number: string;
  status: string;
  is_posted?: boolean;
};

const STATUS_LABEL: Record<LocalShipmentStatus, string> = {
  pending: "قيد الانتظار",
  in_transit: "قيد النقل",
  delivered: "تم التسليم",
  cancelled: "ملغية",
};

export const LocalShippingPage: React.FC = () => {
  const [rows, setRows] = useState<LocalShipmentRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [clearances, setClearances] = useState<ClearanceRow[]>([]);
  const [invoices, setInvoices] = useState<PurchaseInvoiceMini[]>([]);
  const [settings, setSettings] = useState<SalesSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<LocalShipmentRow | null>(null);
  const [importFor, setImportFor] = useState<LocalShipmentRow | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    try {
      const [r, ps, accs, currs, cls, invs] = await Promise.all([
        listLocalShipments(),
        accountingApi.getPartners() as Promise<Partner[]>,
        accountingApi.getAccounts() as Promise<Account[]>,
        accountingApi.getCurrencies() as Promise<Currency[]>,
        listClearances(),
        apiGetList<PurchaseInvoiceMini>("logistics/purchase-invoices/", {
          tenantId,
        }),
      ]);
      setRows(r || []);
      setPartners(ps || []);
      setAccounts(accs || []);
      setCurrencies(currs || []);
      setClearances(cls || []);
      setInvoices(invs || []);
      try {
        const s = await getSalesSettings();
        setSettings(s);
      } catch {
        // الإعدادات اختيارية
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fmt = (s: string | number) =>
    Number(s || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const handlePost = async (id: number) => {
    if (!window.confirm("ترحيل القيد المحاسبي؟"))
      return;
    setErr(null);
    setMsg(null);
    try {
      await postLocalShipment(id);
      setMsg(`تم ترحيل الشحنة #${id}`);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  const handleUnpost = async (id: number) => {
    if (!window.confirm("إلغاء الترحيل؟")) return;
    setErr(null);
    try {
      await unpostLocalShipment(id);
      setMsg("تم إلغاء الترحيل");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل إلغاء الترحيل");
    }
  };

  const handleDelete = async (r: LocalShipmentRow) => {
    if (r.is_posted) {
      alert("ألغِ الترحيل أولاً.");
      return;
    }
    if (!window.confirm(`حذف الشحنة ${r.shipment_number}؟`)) return;
    setErr(null);
    try {
      await deleteLocalShipment(r.id);
      setMsg("تم الحذف");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const totalsByStatus = useMemo(() => {
    const out: Record<LocalShipmentStatus, { count: number; amount: number }> = {
      pending: { count: 0, amount: 0 },
      in_transit: { count: 0, amount: 0 },
      delivered: { count: 0, amount: 0 },
      cancelled: { count: 0, amount: 0 },
    };
    for (const r of rows) {
      out[r.status].count += 1;
      out[r.status].amount += Number(r.amount || 0);
    }
    return out;
  }, [rows]);

  const carriers = useMemo(
    () =>
      partners.filter(
        (p) =>
          !p.partner_type ||
          p.partner_type === "LocalTransporter" ||
          p.partner_type === "FreightForwarder" ||
          p.partner_type === "Supplier",
      ),
    [partners],
  );

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4" dir="rtl">
      <div className="flex items-center gap-3 p-4 bg-gradient-to-l from-[var(--color-primary)] to-[var(--color-surface-2)] text-[var(--color-inverse)] rounded-xl">
        <Truck className="w-8 h-8 text-[var(--color-primary-light)]" />
        <div className="flex-1">
          <h1 className="text-[var(--font-size-lg)] font-bold">الشحن المحلي</h1>
          <p className="text-[var(--font-size-xs)] text-[var(--color-inverse-muted)]">
            نقل البضاعة بين التخليص الجمركي والمستودع/الوجهة — ناقل، تكلفة، ترحيل
            محاسبي
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-[var(--font-size-sm)]"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          تحديث
        </button>
        <button
          type="button"
          onClick={() => {
            setEditing(null);
            setShowForm(true);
          }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-[var(--font-size-sm)] font-medium"
        >
          <Plus className="h-4 w-4" />
          شحنة محلية جديدة
        </button>
      </div>

      <Toolbar
        search={search}
        onSearch={setSearch}
        searchPlaceholder="بحث في الشحنات..."
      />

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {err}
        </div>
      )}
      {msg && (
        <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 text-sm">
          {msg}
        </div>
      )}

      {/* بطاقات الحالة */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {(Object.keys(STATUS_LABEL) as LocalShipmentStatus[]).map((s) => (
          <div key={s} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <div className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">{STATUS_LABEL[s]}</div>
            <div className="text-[var(--font-size-2xl)] font-bold">{totalsByStatus[s].count}</div>
            <div className="text-[11px] text-[var(--color-text-muted)] mt-1">{fmt(totalsByStatus[s].amount)}</div>
          </div>
        ))}
      </div>

      {/* الجدول */}
      <DataGrid
        columns={[
          { key: "shipment_number", header: "رقم", render: (r) => <span className="font-mono">{r.shipment_number}</span> },
          { key: "pickup_date", header: "التاريخ", render: (r) => <span className="text-[var(--font-size-xs)]">{r.pickup_date || r.delivery_date || "—"}</span> },
          { key: "carrier", header: "الناقل", render: (r) => (
            <div>
              <div>{r.carrier_name || `#${r.carrier}`}</div>
              {r.driver_name && <div className="text-[11px] text-[var(--color-text-muted)]">{r.driver_name}{r.vehicle_number ? ` • ${r.vehicle_number}` : ""}</div>}
            </div>
          )},
          { key: "clearance", header: "التخليص", render: (r) => <span className="text-[var(--font-size-xs)]">{r.clearance_number ? `بيان ${r.clearance_number}` : r.shipment_number_source || "—"}</span> },
          { key: "route", header: "من → إلى", render: (r) => <span className="text-[var(--font-size-xs)]">{r.origin || "—"} → {r.destination || "—"}</span> },
          { key: "amount", header: "المبلغ", render: (r) => <span className="font-mono">{fmt(r.amount)} {r.currency_code || ""}</span> },
          { key: "payment", header: "الدفع", render: (r) => (
            <div>
              <span>{r.payment_type === "cash" ? "نقدي" : "آجل"}</span>
              {r.capitalize_to_inventory && <div className="text-[10px] text-[var(--color-primary)]">Landed</div>}
            </div>
          )},
          { key: "status", header: "الحالة", render: (r) => <Badge variant={r.status === "delivered" ? "success" : r.status === "in_transit" ? "primary" : r.status === "cancelled" ? "danger" : "warning"}>{STATUS_LABEL[r.status]}</Badge> },
          { key: "posted", header: "الترحيل", align: "center", render: (r) => (
            <div>
              {r.is_posted ? <span className="text-[var(--font-size-xs)] px-2 py-1 bg-[var(--color-success-light)] text-[var(--color-success)] rounded">مرحّلة #{r.journal}</span> : <span className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">—</span>}
              {r.purchase_invoice && <div className="text-[10px] text-[var(--color-primary)] mt-1">استُورِدت للفاتورة {r.purchase_invoice_number || `#${r.purchase_invoice}`}</div>}
            </div>
          )},
          { key: "actions", header: "إجراءات", align: "end", render: (r) => (
            <div className="flex flex-wrap gap-1 justify-end">
              {!r.is_posted && !r.purchase_invoice && (
                <>
                  <button type="button" onClick={() => { setEditing(r); setShowForm(true); }} className="p-1.5 text-[var(--color-primary)] hover:bg-[var(--color-muted)] rounded" title="تعديل"><Pencil className="w-4 h-4" /></button>
                  <button type="button" onClick={() => handlePost(r.id)} className="p-1.5 text-[var(--color-success)] hover:bg-[var(--color-muted)] rounded" title="ترحيل"><Send className="w-4 h-4" /></button>
                </>
              )}
              {r.is_posted && <button type="button" onClick={() => handleUnpost(r.id)} className="p-1.5 text-[var(--color-warning)] hover:bg-[var(--color-muted)] rounded" title="إلغاء الترحيل"><RotateCcw className="w-4 h-4" /></button>}
              {!r.is_posted && !r.purchase_invoice && <button type="button" onClick={() => setImportFor(r)} className="p-1.5 text-[var(--color-primary)] hover:bg-[var(--color-muted)] rounded" title="نقل إلى فاتورة مشتريات"><LinkIcon className="w-4 h-4" /></button>}
              {!r.is_posted && <button type="button" onClick={() => handleDelete(r)} className="p-1.5 text-[var(--color-danger)] hover:bg-[var(--color-muted)] rounded" title="حذف"><Trash2 className="w-4 h-4" /></button>}
            </div>
          )},
        ]}
        data={rows.filter(r => !search || r.shipment_number?.includes(search) || r.carrier_name?.includes(search) || r.origin?.includes(search) || r.destination?.includes(search))}
        loading={loading}
        emptyMessage={<div className="flex flex-col items-center py-8"><Package className="w-12 h-12 text-[var(--color-text-muted)] mb-2" /><span>لا توجد شحنات محلية بعد — اضغط "شحنة محلية جديدة"</span></div>}
      />

      {showForm && (
        <LocalShipmentFormDrawer
          editing={editing}
          carriers={carriers}
          accounts={accounts}
          currencies={currencies}
          clearances={clearances}
          defaultOrigin={settings?.default_shipping_origin || ""}
          defaultDestination={settings?.default_shipping_destination || ""}
          onClose={() => {
            setShowForm(false);
            setEditing(null);
          }}
          onSaved={async () => {
            setShowForm(false);
            setEditing(null);
            await load();
          }}
        />
      )}

      {importFor && (
        <ImportToInvoiceDrawer
          shipment={importFor}
          invoices={invoices.filter((i) => !i.is_posted && i.status !== "archived")}
          onClose={() => setImportFor(null)}
          onDone={async () => {
            setImportFor(null);
            setMsg("تمّ استيراد الشحنة إلى الفاتورة");
            await load();
          }}
        />
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// Drawer إنشاء/تعديل
// ═══════════════════════════════════════════════════════════════════════════
const LocalShipmentFormDrawer: React.FC<{
  editing: LocalShipmentRow | null;
  carriers: Partner[];
  accounts: Account[];
  currencies: Currency[];
  clearances: ClearanceRow[];
  defaultOrigin?: string;
  defaultDestination?: string;
  onClose: () => void;
  onSaved: () => void;
}> = ({
  editing,
  carriers,
  accounts,
  currencies,
  clearances,
  defaultOrigin = "",
  defaultDestination = "",
  onClose,
  onSaved,
}) => {
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState<LocalShipmentCreate>(() => ({
    clearance: editing?.clearance ?? null,
    shipment: editing?.shipment ?? null,
    carrier: editing?.carrier ?? 0,
    driver_name: editing?.driver_name ?? "",
    vehicle_number: editing?.vehicle_number ?? "",
    origin: editing?.origin ?? defaultOrigin,
    destination: editing?.destination ?? defaultDestination,
    pickup_date: editing?.pickup_date ?? today,
    delivery_date: editing?.delivery_date ?? "",
    amount: editing?.amount ?? "",
    currency: editing?.currency ?? undefined,
    exchange_rate: editing?.exchange_rate ?? "1",
    payment_type: editing?.payment_type ?? "credit",
    expense_account: editing?.expense_account ?? null,
    cash_or_bank_account: editing?.cash_or_bank_account ?? null,
    capitalize_to_inventory: editing?.capitalize_to_inventory ?? true,
    status: editing?.status ?? "pending",
    notes: editing?.notes ?? "",
  }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editing) return;
    if (!form.currency && currencies.length) {
      const ils = currencies.find((c) => c.Code === "ILS");
      setForm((f) => ({
        ...f,
        currency: (ils?.CurrencyID ?? currencies[0].CurrencyID) as number,
      }));
    }
    if (!form.expense_account && accounts.length) {
      const defaultExp =
        accounts.find((a) => a.code === "5305") ||
        accounts.find((a) => a.code === "5301");
      if (defaultExp) setForm((f) => ({ ...f, expense_account: defaultExp.id }));
    }
  }, [editing, currencies, accounts, form.currency, form.expense_account]);

  const expenseAccounts = useMemo(
    () =>
      accounts.filter(
        (a) =>
          a.account_type === "Expense" ||
          (a.code && (a.code.startsWith("53") || a.code.startsWith("52"))),
      ),
    [accounts],
  );

  const cashAccounts = useMemo(
    () =>
      accounts.filter((a) => {
        const code = String(a.code || "");
        const name = (a.name || "").toLowerCase();
        return (
          a.account_type === "Asset" &&
          (code.startsWith("110") ||
            name.includes("صندوق") ||
            name.includes("بنك") ||
            name.includes("cash") ||
            name.includes("bank"))
        );
      }),
    [accounts],
  );

  const update = <K extends keyof LocalShipmentCreate>(k: K, v: LocalShipmentCreate[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const canSubmit =
    form.carrier &&
    (form.payment_type !== "cash" || form.cash_or_bank_account);

  const submit = async () => {
    setError(null);
    const vErr = validatePaymentInput({
      amount: String(form.amount ?? ""),
      date: String(form.pickup_date ?? ""),
    });
    if (vErr.amount || vErr.date) {
      setError(vErr.amount || vErr.date || "");
      return;
    }
    if (!canSubmit) {
      setError("اكمل الحقول المطلوبة (ناقل، حسابات)");
      return;
    }
    setSubmitting(true);
    try {
      if (editing) {
        await updateLocalShipment(editing.id, form);
      } else {
        await createLocalShipment(form);
      }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      open={true}
      onClose={onClose}
      title={editing ? `تعديل ${editing.shipment_number}` : "شحنة محلية جديدة"}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-[var(--font-size-sm)] rounded-lg border border-[var(--color-border)]"
          >
            إلغاء
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit || submitting}
            className="px-4 py-2 text-[var(--font-size-sm)] rounded-lg bg-[var(--color-primary)] text-white font-medium disabled:opacity-40"
          >
            {submitting ? "جاري الحفظ..." : "حفظ"}
          </button>
        </>
      }
    >
      <div className="space-y-4" dir="rtl">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">التخليص الجمركي (اختياري)</label>
            <select
              className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.clearance ?? ""}
              onChange={(e) => update("clearance", e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— بدون تخليص —</option>
              {clearances.map((c) => (
                <option key={c.id} value={c.id}>{formatClearanceShipmentLine(c)} · {c.status}</option>
              ))}
            </select>
            <p className="text-[11px] text-[var(--color-text-muted)] mt-1">إن اخترت تخليصاً ستُربط الشحنة الدولية تلقائياً</p>
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">الحالة</label>
            <select
              className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.status ?? "pending"}
              onChange={(e) => update("status", e.target.value as LocalShipmentStatus)}
            >
              {(Object.keys(STATUS_LABEL) as LocalShipmentStatus[]).map((s) => (
                <option key={s} value={s}>{STATUS_LABEL[s]}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">الناقل *</label>
            <select
              className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.carrier || ""}
              onChange={(e) => update("carrier", Number(e.target.value))}
            >
              <option value="">اختر...</option>
              {carriers.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
            </select>
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">السائق</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.driver_name || ""} onChange={(e) => update("driver_name", e.target.value)} />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">رقم المركبة</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.vehicle_number || ""} onChange={(e) => update("vehicle_number", e.target.value)} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">من (نقطة الانطلاق)</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.origin || ""} onChange={(e) => update("origin", e.target.value)} placeholder="مخزن التخليص، الميناء..." />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">إلى (الوجهة)</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.destination || ""} onChange={(e) => update("destination", e.target.value)} placeholder="المستودع، عنوان العميل..." />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">تاريخ الاستلام</label>
            <input type="date" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.pickup_date || ""} onChange={(e) => update("pickup_date", e.target.value)} />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">تاريخ التسليم</label>
            <input type="date" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.delivery_date || ""} onChange={(e) => update("delivery_date", e.target.value)} />
          </div>
        </div>

        <div className="border-t border-[var(--color-border)] pt-3">
          <h3 className="text-[var(--font-size-sm)] font-semibold mb-3">المالي والمحاسبي</h3>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">المبلغ *</label>
              <input type="number" step="0.01" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={String(form.amount ?? "")} onChange={(e) => update("amount", e.target.value)} />
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">العملة</label>
              <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.currency ?? ""} onChange={(e) => update("currency", e.target.value ? Number(e.target.value) : undefined)}>
                {currencies.map((c) => (<option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>))}
              </select>
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">سعر الصرف</label>
              <input type="number" step="0.000001" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={String(form.exchange_rate ?? "1")} onChange={(e) => update("exchange_rate", e.target.value)} />
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">طريقة الدفع</label>
              <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.payment_type} onChange={(e) => update("payment_type", e.target.value as LocalShipmentPaymentType)}>
                <option value="credit">آجل (على ذمة الناقل)</option>
                <option value="cash">نقدي (من الصندوق)</option>
              </select>
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">حساب المصروف</label>
              <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.expense_account ?? ""} onChange={(e) => update("expense_account", e.target.value ? Number(e.target.value) : null)}>
                <option value="">— افتراضي 5305 الشحن المحلي —</option>
                {expenseAccounts.map((a) => (<option key={a.id} value={a.id}>{a.code} {a.name}</option>))}
              </select>
            </div>
            {form.payment_type === "cash" && (
              <div>
                <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">الصندوق / البنك *</label>
                <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={form.cash_or_bank_account ?? ""} onChange={(e) => update("cash_or_bank_account", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">اختر...</option>
                  {cashAccounts.map((a) => (<option key={a.id} value={a.id}>{a.code} {a.name}</option>))}
                </select>
              </div>
            )}
          </div>
          <label className="flex items-center gap-2 text-[var(--font-size-sm)] mt-3">
            <input type="checkbox" checked={form.capitalize_to_inventory ?? true} onChange={(e) => update("capitalize_to_inventory", e.target.checked)} />
            <span>رسملة على <strong>Landed Cost</strong> (تُضاف لتكلفة المخزون المستورد)</span>
          </label>
        </div>

        <div>
          <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">ملاحظات</label>
          <textarea className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" rows={2} value={form.notes || ""} onChange={(e) => update("notes", e.target.value)} />
        </div>

        {error && <div className="p-2 rounded bg-[var(--color-danger-light)] text-[var(--color-danger)] text-[var(--font-size-sm)]">{error}</div>}
      </div>
    </Drawer>
  );
};

// ═══════════════════════════════════════════════════════════════════════════
// Drawer استيراد إلى فاتورة مشتريات
// ═══════════════════════════════════════════════════════════════════════════
const ImportToInvoiceDrawer: React.FC<{
  shipment: LocalShipmentRow;
  invoices: PurchaseInvoiceMini[];
  onClose: () => void;
  onDone: () => void;
}> = ({ shipment, invoices, onClose, onDone }) => {
  const [invId, setInvId] = useState<number | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!invId) {
      setError("اختر الفاتورة");
      return;
    }
    setSubmitting(true);
    try {
      await importLocalShipmentToInvoice(shipment.id, Number(invId));
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Drawer
      open={true}
      onClose={onClose}
      title="نقل إلى فاتورة مشتريات"
      footer={
        <>
          <button type="button" onClick={onClose} className="px-4 py-2 text-[var(--font-size-sm)] rounded-lg border border-[var(--color-border)]">إلغاء</button>
          <button type="button" onClick={submit} disabled={!invId || submitting} className="px-4 py-2 text-[var(--font-size-sm)] rounded-lg bg-[var(--color-primary)] text-white font-medium disabled:opacity-40">
            {submitting ? "..." : "استيراد"}
          </button>
        </>
      }
    >
      <div className="space-y-3" dir="rtl">
        <div className="text-[var(--font-size-sm)]">الشحنة: <strong>{shipment.shipment_number}</strong> — {Number(shipment.amount).toLocaleString()} {shipment.currency_code || ""}</div>
        <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">ستُضاف قيمة الشحن كـ<strong> رسم</strong> على الفاتورة المختارة{shipment.capitalize_to_inventory ? " — مرسمل على Landed Cost." : " — كمصروف فترة."}</p>
        <div>
          <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">فاتورة المشتريات *</label>
          <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]" value={invId} onChange={(e) => setInvId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">اختر...</option>
            {invoices.map((i) => (<option key={i.id} value={i.id}>{i.invoice_number} · {i.status}</option>))}
          </select>
          {invoices.length === 0 && <p className="text-[var(--font-size-xs)] text-[var(--color-warning)] mt-1">لا توجد فواتير مشتريات غير مرحّلة — أنشئ فاتورة أولاً.</p>}
        </div>
        {error && <div className="p-2 rounded bg-[var(--color-danger-light)] text-[var(--color-danger)] text-[var(--font-size-sm)]">{error}</div>}
      </div>
    </Drawer>
  );
};

export default LocalShippingPage;
