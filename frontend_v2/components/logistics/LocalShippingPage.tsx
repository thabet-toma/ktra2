/**
 * N6-T3 — LocalShippingPage (L10) — AseelDenseTable للشحن المحلي
 * المرجع: task5.md:797 + الإرساليات.txt:91-109
 * يَبقى المصدر المستقل (T1-01) — كل منطق الـAPI بلا تغيير.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Plus,
  Pencil,
  Trash2,
  Send,
  RotateCcw,
  Link as LinkIcon,
  RefreshCw,
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
import { Drawer } from "../../components/ui";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { useAseelIndexKeymap } from "../aseel/useAseelIndexKeymap";

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
  pending:    "قيد الانتظار",
  in_transit: "قيد النقل",
  delivered:  "تم التسليم",
  cancelled:  "ملغية",
};

const STATUS_COLORS: Record<LocalShipmentStatus, string> = {
  pending:    "var(--aseel-warn, #b8800a)",
  in_transit: "var(--aseel-accent, #1857a4)",
  delivered:  "var(--aseel-ok, #267346)",
  cancelled:  "var(--aseel-danger, #c00)",
};

const fmt = (s: string | number) =>
  Number(s || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

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
  const [statusFilter, setStatusFilter] = useState<LocalShipmentStatus | "all">("all");
  const searchInputRef = useRef<HTMLInputElement | null>(null);

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
        apiGetList<PurchaseInvoiceMini>("logistics/purchase-invoices/", { tenantId }),
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

  useEffect(() => { load(); }, [load]);

  const carriers = useMemo(
    () => partners.filter(
      (p) =>
        !p.partner_type ||
        p.partner_type === "LocalTransporter" ||
        p.partner_type === "FreightForwarder" ||
        p.partner_type === "Supplier",
    ),
    [partners],
  );

  const totalsByStatus = useMemo(() => {
    const out: Record<LocalShipmentStatus, { count: number; amount: number }> = {
      pending:    { count: 0, amount: 0 },
      in_transit: { count: 0, amount: 0 },
      delivered:  { count: 0, amount: 0 },
      cancelled:  { count: 0, amount: 0 },
    };
    for (const r of rows) {
      out[r.status].count += 1;
      out[r.status].amount += Number(r.amount || 0);
    }
    return out;
  }, [rows]);

  const filteredRows = useMemo(() => {
    let result = rows;
    if (search) {
      const s = search.toLowerCase();
      result = result.filter(r =>
        r.shipment_number?.includes(s) ||
        r.carrier_name?.toLowerCase().includes(s) ||
        r.origin?.toLowerCase().includes(s) ||
        r.destination?.toLowerCase().includes(s)
      );
    }
    if (statusFilter !== "all") {
      result = result.filter(r => r.status === statusFilter);
    }
    return result;
  }, [rows, search, statusFilter]);

  const handlePost = async (id: number) => {
    if (!window.confirm("ترحيل القيد المحاسبي؟")) return;
    setErr(null); setMsg(null);
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
    if (r.is_posted) { alert("ألغِ الترحيل أولاً."); return; }
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

  const columns: DenseColumn<LocalShipmentRow>[] = [
    {
      key: "shipment_number",
      header: "رقم الشحنة",
      width: "110px",
      render: (r) => <b style={{ fontFamily: "monospace" }}>{r.shipment_number}</b>,
    },
    {
      key: "date",
      header: "التاريخ",
      width: "90px",
      render: (r) => <>{r.pickup_date || r.delivery_date || "—"}</>,
    },
    {
      key: "carrier",
      header: "الناقل",
      width: "160px",
      render: (r) => (
        <div>
          <div>{r.carrier_name || `#${r.carrier}`}</div>
          {r.driver_name && (
            <div style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>
              {r.driver_name}{r.vehicle_number ? ` • ${r.vehicle_number}` : ""}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "clearance",
      header: "التخليص",
      width: "120px",
      render: (r) => (
        <span style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>
          {r.clearance_number ? `بيان ${r.clearance_number}` : r.shipment_number_source || "—"}
        </span>
      ),
    },
    {
      key: "route",
      header: "من ← إلى",
      render: (r) => (
        <span style={{ fontSize: "var(--aseel-fs-sm)" }}>
          {r.origin || "—"} ← {r.destination || "—"}
        </span>
      ),
    },
    {
      key: "amount",
      header: "المبلغ",
      width: "120px",
      align: "right",
      numeric: true,
      render: (r) => (
        <span style={{ fontFamily: "monospace" }}>
          {fmt(r.amount)} {r.currency_code || ""}
        </span>
      ),
    },
    {
      key: "status",
      header: "الحالة",
      width: "110px",
      render: (r) => (
        <span style={{ color: STATUS_COLORS[r.status] || "inherit", fontWeight: 500 }}>
          {STATUS_LABEL[r.status]}
        </span>
      ),
    },
    {
      key: "posted",
      header: "الترحيل",
      width: "130px",
      align: "center",
      render: (r) => (
        <div>
          {r.is_posted
            ? <span style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ok, #267346)" }}>مرحّلة #{r.journal}</span>
            : <span style={{ color: "var(--aseel-ink-soft)" }}>—</span>
          }
          {r.purchase_invoice && (
            <div style={{ fontSize: "10px", color: "var(--aseel-accent, #1857a4)", marginTop: 2 }}>
              فاتورة {r.purchase_invoice_number || `#${r.purchase_invoice}`}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "110px",
      align: "center",
      render: (r) => (
        <span style={{ display: "inline-flex", gap: 2, flexWrap: "wrap", justifyContent: "center" }}>
          {!r.is_posted && !r.purchase_invoice && (
            <>
              <button
                className="aseel-toolbtn"
                style={{ padding: "2px 4px" }}
                onClick={() => { setEditing(r); setShowForm(true); }}
                title="تعديل"
              >
                <Pencil style={{ width: 13, height: 13 }} />
              </button>
              <button
                className="aseel-toolbtn"
                style={{ padding: "2px 4px", color: "var(--aseel-ok, #267346)" }}
                onClick={() => void handlePost(r.id)}
                title="ترحيل"
              >
                <Send style={{ width: 13, height: 13 }} />
              </button>
            </>
          )}
          {r.is_posted && (
            <button
              className="aseel-toolbtn"
              style={{ padding: "2px 4px", color: "var(--aseel-warn, #b8800a)" }}
              onClick={() => void handleUnpost(r.id)}
              title="إلغاء الترحيل"
            >
              <RotateCcw style={{ width: 13, height: 13 }} />
            </button>
          )}
          {!r.is_posted && !r.purchase_invoice && (
            <button
              className="aseel-toolbtn"
              style={{ padding: "2px 4px" }}
              onClick={() => setImportFor(r)}
              title="نقل إلى فاتورة مشتريات"
            >
              <LinkIcon style={{ width: 13, height: 13 }} />
            </button>
          )}
          {!r.is_posted && (
            <button
              className="aseel-toolbtn"
              style={{ padding: "2px 4px", color: "var(--aseel-danger, #c00)" }}
              onClick={() => void handleDelete(r)}
              title="حذف"
            >
              <Trash2 style={{ width: 13, height: 13 }} />
            </button>
          )}
        </span>
      ),
    },
  ];

  // N0-T7 — keymap لقائمة الشحن المحلي
  useAseelIndexKeymap(
    {
      CtrlIns: () => { setEditing(null); setShowForm(true); },
      F6: () => searchInputRef.current?.focus(),
      F5: () => void load(),
      Escape: () => { setSearch(""); setStatusFilter("all"); },
    },
    { enabled: !showForm && !importFor },
  );

  return (
    <div dir="rtl" data-skin="aseel" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 6, padding: "8px 12px" }}>
      {/* شريط العنوان */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", paddingBottom: 4, borderBottom: "1px solid var(--aseel-border)" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          الشحن المحلي
        </strong>
        {(Object.keys(STATUS_LABEL) as LocalShipmentStatus[]).map((s) => (
          <span key={s} className="aseel-status-item">
            {STATUS_LABEL[s]}: <b>{totalsByStatus[s].count}</b>
          </span>
        ))}
        <div style={{ flex: 1 }} />
        <input
          ref={searchInputRef}
          className="aseel-input"
          style={{ width: 190 }}
          placeholder="بحث في الشحنات… (F6)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="aseel-input"
          style={{ width: 140 }}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as LocalShipmentStatus | "all")}
        >
          <option value="all">كل الحالات</option>
          {(Object.keys(STATUS_LABEL) as LocalShipmentStatus[]).map((s) => (
            <option key={s} value={s}>{STATUS_LABEL[s]}</option>
          ))}
        </select>
        <button
          className="aseel-toolbtn"
          onClick={() => void load()}
          title="تحديث"
        >
          <RefreshCw style={{ width: 14, height: 14 }} className={loading ? "animate-spin" : ""} />
        </button>
        <button
          className="aseel-toolbtn"
          onClick={() => { setEditing(null); setShowForm(true); }}
          title="شحنة محلية جديدة (Ctrl+Ins)"
        >
          <Plus style={{ width: 14, height: 14 }} /> شحنة محلية جديدة
        </button>
      </div>

      {/* رسائل النجاح/الخطأ */}
      {err && (
        <div style={{ padding: "6px 10px", background: "var(--aseel-danger-bg, #fef2f2)", color: "var(--aseel-danger, #c00)", borderRadius: 4, fontSize: "var(--aseel-fs-sm)" }}>
          {err}
        </div>
      )}
      {msg && (
        <div style={{ padding: "6px 10px", background: "var(--aseel-ok-bg, #f0fdf4)", color: "var(--aseel-ok, #267346)", borderRadius: 4, fontSize: "var(--aseel-fs-sm)" }}>
          {msg}
        </div>
      )}

      {/* جدول الشحنات المحلية */}
      <AseelDenseTable<LocalShipmentRow>
        columns={columns}
        rows={filteredRows}
        getRowKey={(r) => r.id}
        loading={loading}
        emptyHint="لا توجد شحنات محلية بعد — اضغط «شحنة محلية جديدة»"
        footer={
          filteredRows.length > 0 ? (
            <span style={{ fontFamily: "monospace", fontSize: "var(--aseel-fs-sm)" }}>
              الإجمالي: <b>{fmt(filteredRows.reduce((s, r) => s + Number(r.amount || 0), 0))}</b>
            </span>
          ) : undefined
        }
      />

      {/* Drawer إنشاء/تعديل */}
      {showForm && (
        <LocalShipmentFormDrawer
          editing={editing}
          carriers={carriers}
          accounts={accounts}
          currencies={currencies}
          clearances={clearances}
          defaultOrigin={settings?.default_shipping_origin || ""}
          defaultDestination={settings?.default_shipping_destination || ""}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={async () => { setShowForm(false); setEditing(null); await load(); }}
        />
      )}

      {/* Drawer استيراد إلى فاتورة */}
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
  editing, carriers, accounts, currencies, clearances,
  defaultOrigin = "", defaultDestination = "", onClose, onSaved,
}) => {
  const today = new Date().toISOString().split("T")[0];
  const [form, setForm] = useState<LocalShipmentCreate>(() => ({
    clearance:               editing?.clearance ?? null,
    shipment:                editing?.shipment ?? null,
    carrier:                 editing?.carrier ?? 0,
    driver_name:             editing?.driver_name ?? "",
    vehicle_number:          editing?.vehicle_number ?? "",
    origin:                  editing?.origin ?? defaultOrigin,
    destination:             editing?.destination ?? defaultDestination,
    pickup_date:             editing?.pickup_date ?? today,
    delivery_date:           editing?.delivery_date ?? "",
    amount:                  editing?.amount ?? "",
    currency:                editing?.currency ?? undefined,
    exchange_rate:           editing?.exchange_rate ?? "1",
    payment_type:            editing?.payment_type ?? "credit",
    expense_account:         editing?.expense_account ?? null,
    cash_or_bank_account:    editing?.cash_or_bank_account ?? null,
    capitalize_to_inventory: editing?.capitalize_to_inventory ?? true,
    status:                  editing?.status ?? "pending",
    notes:                   editing?.notes ?? "",
  }));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (editing) return;
    if (!form.currency && currencies.length) {
      const ils = currencies.find((c) => c.Code === "ILS");
      setForm((f) => ({ ...f, currency: (ils?.CurrencyID ?? currencies[0].CurrencyID) as number }));
    }
    if (!form.expense_account && accounts.length) {
      const defaultExp = accounts.find((a) => a.code === "5305") || accounts.find((a) => a.code === "5301");
      if (defaultExp) setForm((f) => ({ ...f, expense_account: defaultExp.id }));
    }
  }, [editing, currencies, accounts, form.currency, form.expense_account]);

  const expenseAccounts = useMemo(
    () => accounts.filter((a) =>
      a.account_type === "Expense" ||
      (a.code && (a.code.startsWith("53") || a.code.startsWith("52")))
    ),
    [accounts],
  );

  const cashAccounts = useMemo(
    () => accounts.filter((a) => {
      const code = String(a.code || "");
      const name = (a.name || "").toLowerCase();
      return (
        a.account_type === "Asset" &&
        (code.startsWith("110") || name.includes("صندوق") || name.includes("بنك") ||
          name.includes("cash") || name.includes("bank"))
      );
    }),
    [accounts],
  );

  const update = <K extends keyof LocalShipmentCreate>(k: K, v: LocalShipmentCreate[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const canSubmit = form.carrier && (form.payment_type !== "cash" || form.cash_or_bank_account);

  const submit = async () => {
    setError(null);
    const vErr = validatePaymentInput({
      amount: String(form.amount ?? ""),
      date: String(form.pickup_date ?? ""),
    });
    if (vErr.amount || vErr.date) { setError(vErr.amount || vErr.date || ""); return; }
    if (!canSubmit) { setError("اكمل الحقول المطلوبة (ناقل، حسابات)"); return; }
    setSubmitting(true);
    try {
      if (editing) { await updateLocalShipment(editing.id, form); }
      else { await createLocalShipment(form); }
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
          <button type="button" onClick={onClose} className="px-4 py-2 text-[var(--font-size-sm)] rounded-lg border border-[var(--color-border)]">
            إلغاء
          </button>
          <button type="button" onClick={submit} disabled={!canSubmit || submitting}
            className="px-4 py-2 text-[var(--font-size-sm)] rounded-lg bg-[var(--color-primary)] text-white font-medium disabled:opacity-40">
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
              {carriers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">السائق</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.driver_name || ""} onChange={(e) => update("driver_name", e.target.value)} />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">رقم المركبة</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.vehicle_number || ""} onChange={(e) => update("vehicle_number", e.target.value)} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">من (نقطة الانطلاق)</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.origin || ""} onChange={(e) => update("origin", e.target.value)} placeholder="مخزن التخليص، الميناء..." />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">إلى (الوجهة)</label>
            <input type="text" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.destination || ""} onChange={(e) => update("destination", e.target.value)} placeholder="المستودع، عنوان العميل..." />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">تاريخ الاستلام</label>
            <input type="date" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.pickup_date || ""} onChange={(e) => update("pickup_date", e.target.value)} />
          </div>
          <div>
            <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">تاريخ التسليم</label>
            <input type="date" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
              value={form.delivery_date || ""} onChange={(e) => update("delivery_date", e.target.value)} />
          </div>
        </div>

        <div className="border-t border-[var(--color-border)] pt-3">
          <h3 className="text-[var(--font-size-sm)] font-semibold mb-3">المالي والمحاسبي</h3>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">المبلغ *</label>
              <input type="number" step="0.01" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
                value={String(form.amount ?? "")} onChange={(e) => update("amount", e.target.value)} />
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">العملة</label>
              <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
                value={form.currency ?? ""} onChange={(e) => update("currency", e.target.value ? Number(e.target.value) : undefined)}>
                {currencies.map((c) => <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">سعر الصرف</label>
              <input type="number" step="0.000001" className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
                value={String(form.exchange_rate ?? "1")} onChange={(e) => update("exchange_rate", e.target.value)} />
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">طريقة الدفع</label>
              <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
                value={form.payment_type} onChange={(e) => update("payment_type", e.target.value as LocalShipmentPaymentType)}>
                <option value="credit">آجل (على ذمة الناقل)</option>
                <option value="cash">نقدي (من الصندوق)</option>
              </select>
            </div>
            <div>
              <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">حساب المصروف</label>
              <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
                value={form.expense_account ?? ""} onChange={(e) => update("expense_account", e.target.value ? Number(e.target.value) : null)}>
                <option value="">— افتراضي 5305 الشحن المحلي —</option>
                {expenseAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}
              </select>
            </div>
            {form.payment_type === "cash" && (
              <div>
                <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">الصندوق / البنك *</label>
                <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
                  value={form.cash_or_bank_account ?? ""} onChange={(e) => update("cash_or_bank_account", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">اختر...</option>
                  {cashAccounts.map((a) => <option key={a.id} value={a.id}>{a.code} {a.name}</option>)}
                </select>
              </div>
            )}
          </div>
          <label className="flex items-center gap-2 text-[var(--font-size-sm)] mt-3">
            <input type="checkbox" checked={form.capitalize_to_inventory ?? true}
              onChange={(e) => update("capitalize_to_inventory", e.target.checked)} />
            <span>رسملة على <strong>Landed Cost</strong> (تُضاف لتكلفة المخزون المستورد)</span>
          </label>
        </div>

        <div>
          <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">ملاحظات</label>
          <textarea className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
            rows={2} value={form.notes || ""} onChange={(e) => update("notes", e.target.value)} />
        </div>

        {error && (
          <div className="p-2 rounded bg-[var(--color-danger-light)] text-[var(--color-danger)] text-[var(--font-size-sm)]">{error}</div>
        )}
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
    if (!invId) { setError("اختر الفاتورة"); return; }
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
          <button type="button" onClick={submit} disabled={!invId || submitting}
            className="px-4 py-2 text-[var(--font-size-sm)] rounded-lg bg-[var(--color-primary)] text-white font-medium disabled:opacity-40">
            {submitting ? "..." : "استيراد"}
          </button>
        </>
      }
    >
      <div className="space-y-3" dir="rtl">
        <div className="text-[var(--font-size-sm)]">
          الشحنة: <strong>{shipment.shipment_number}</strong> — {Number(shipment.amount).toLocaleString()} {shipment.currency_code || ""}
        </div>
        <p className="text-[var(--font-size-xs)] text-[var(--color-text-muted)]">
          ستُضاف قيمة الشحن كـ<strong> رسم</strong> على الفاتورة المختارة
          {shipment.capitalize_to_inventory ? " — مرسمل على Landed Cost." : " — كمصروف فترة."}
        </p>
        <div>
          <label className="block text-[var(--font-size-xs)] text-[var(--color-text-muted)] mb-1">فاتورة المشتريات *</label>
          <select className="w-full border rounded-lg px-3 py-2 bg-[var(--color-surface)] border-[var(--color-border)]"
            value={invId} onChange={(e) => setInvId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">اختر...</option>
            {invoices.map((i) => <option key={i.id} value={i.id}>{i.invoice_number} · {i.status}</option>)}
          </select>
          {invoices.length === 0 && (
            <p className="text-[var(--font-size-xs)] text-[var(--color-warning)] mt-1">
              لا توجد فواتير مشتريات غير مرحّلة — أنشئ فاتورة أولاً.
            </p>
          )}
        </div>
        {error && (
          <div className="p-2 rounded bg-[var(--color-danger-light)] text-[var(--color-danger)] text-[var(--font-size-sm)]">{error}</div>
        )}
      </div>
    </Drawer>
  );
};

export default LocalShippingPage;
