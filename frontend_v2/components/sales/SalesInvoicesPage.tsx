/**
 * N4-T1 — SalesInvoicesPage (L7) Aseel inside-out
 * AseelDocumentShell + AseelDenseTable + شريط فلاتر + useAseelIndexKeymap
 * Ref: task5.md:673-676 + الفواتير.txt
 *
 * أعمدة (per spec): رقم / تاريخ / العميل / النوع / الحالة /
 *                    الإجمالي / المدفوع / المتبقي / الكشف / إجراءات
 * Ctrl+Ins = يَفتح SalesInvoiceEditor مسودة جديدة
 * F2 = drill (تعديل المسودة المختارة)
 * F6 = focus search
 */
import React, { useCallback, useEffect, useState } from "react";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useNavigate, useLocation } from "react-router-dom";
import {
  listSalesInvoices,
  postSalesInvoice,
  createDeliveryOrder,
  deliverOrder,
  deleteSalesInvoice,
  getSalesSettings,
  type SalesInvoiceRow,
  type SalesSettings,
} from "../../services/salesApi";
import { apiGetList } from "../../services/restApi";
import {
  Loader2,
  RefreshCw,
  Send,
  Truck,
  Pencil,
  Trash2,
  Plus,
  Printer,
} from "lucide-react";
import { SalesInvoiceEditor, type PartnerRow, type ProductRow } from "./SalesInvoiceEditor";
import { resolveTenantId } from "../../utils/tenantContext";
import { eventBus } from "../../utils/eventBus";
import { openInNewTab } from "../../utils/openInNewTab";
import {
  AseelDocumentShell,
  AseelDenseTable,
  useAseelIndexKeymap,
  type DenseColumn,
  type AseelToolbarAction,
} from "../aseel";

type CurrOpt = { CurrencyID: number; Code: string };
type AccountOpt = {
  id: number;
  code?: string | null;
  name?: string | null;
  account_type?: string | null;
};

type ExtRow = SalesInvoiceRow & { vat_statement_no?: string | null };

const STATUS_OPTIONS = [
  { v: "", l: "الكل" },
  { v: "draft", l: "مسودة" },
  { v: "posted", l: "مرحَّلة" },
];

const TYPE_OPTIONS = [
  { v: "", l: "الكل" },
  { v: "cash", l: "نقدي" },
  { v: "credit", l: "آجل" },
];

const fmtNum = (s: string | number | undefined | null) => {
  const n = Number(s);
  if (!isFinite(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

type SalesInvoicesPageProps = {
  /** M5: فتح الأستاذ العام لحساب العميل (drill-down من محرر الفاتورة). */
  onOpenGeneralLedger?: (accountId: number) => void;
};

export const SalesInvoicesPage: React.FC<SalesInvoicesPageProps> = ({
  onOpenGeneralLedger,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const confirm = useConfirm();
  const [rows, setRows] = useState<ExtRow[]>([]);
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
  const [editorOpen, setEditorOpen] = useState(false);

  // filters
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");
  const [selectedKey, setSelectedKey] = useState<number | null>(null);

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
        const m = r.reason instanceof Error ? r.reason.message : String(r.reason ?? "خطأ");
        errs.push(`${parts[i]}: ${m}`);
      }
    });
    if (settled[0].status === "fulfilled") setRows(settled[0].value as ExtRow[]);
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
      // optional
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

  useEffect(() => {
    const unsubscribe = eventBus.subscribe((event) => {
      const tenantId = resolveTenantId();
      if (event.type === "settings") {
        getSalesSettings().then(setSalesSettings).catch(() => {});
      } else if (event.type === "partners") {
        apiGetList<PartnerRow>("partners/", { tenantId }).then(setPartners).catch(() => {});
      } else if (event.type === "products") {
        apiGetList<ProductRow>("inventory/products/", { tenantId }).then(setProducts).catch(() => {});
      }
    });
    return unsubscribe;
  }, []);

  // P4-3: pull pending sales-invoice mutations from the offline queue so
  // local drafts show up alongside posted records with a «معلَّقة» badge.
  const [pendingDrafts, setPendingDrafts] = useState<ExtRow[]>([]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const db = (await import("../../services/offline/db")).default;
        const queued = await db.mutation_queue
          .where("endpoint")
          .startsWith("sales/invoices")
          .filter((m) => m.status !== "synced")
          .toArray();
        if (cancelled) return;
        const drafts: ExtRow[] = queued.map((m) => {
          let body: Record<string, unknown> = {};
          try { body = JSON.parse(m.body); } catch { /* ignore */ }
          const draft = {
            id: -(m.id ?? 0),
            invoice_number: (body.invoice_number as string) || `مسوّدة #${m.temp_id?.slice(-6) || ""}`,
            invoice_date: (body.invoice_date as string) || m.created_at.slice(0, 10),
            status: "draft",
            grand_total: (body.grand_total as number | undefined) ?? 0,
            amount_paid: 0,
            customer: (body.customer as number | null | undefined) ?? null,
            ...body,
            __pending: true,
          };
          return draft as unknown as ExtRow;
        });
        setPendingDrafts(drafts);
      } catch { /* IndexedDB unavailable — skip */ }
    })();
    return () => { cancelled = true; };
  }, [rows.length]);

  const filteredRows = [...pendingDrafts, ...rows].filter((r) => {
    if (search) {
      const s = search.toLowerCase();
      const hay = `${r.invoice_number || ""} ${r.customer_name || ""} ${r.customer || ""}`.toLowerCase();
      if (!hay.includes(s)) return false;
    }
    if (filterStatus && r.status !== filterStatus) return false;
    if (filterType && r.invoice_type !== filterType) return false;
    if (filterFrom && r.invoice_date && r.invoice_date < filterFrom) return false;
    if (filterTo && r.invoice_date && r.invoice_date > filterTo) return false;
    return true;
  });

  // task16 A8: قائمة الفواتير (/sales/invoices) وتفصيل فاتورة واحدة
  // (/sales/invoices/:id) لهما مساران مستقلان — الـ URL هو مصدر الحقيقة لفتح
  // المحرر. فتح/إغلاق المحرر يتم عبر التنقّل، وتأثير المزامنة أدناه يضبط الحالة.
  const openNew = () => {
    openInNewTab("/sales/invoices/new");
  };

  const openEdit = (id: number) => {
    openInNewTab(`/sales/invoices/${id}`);
  };

  const closeEditor = () => {
    navigate("/sales/invoices");
  };

  // مزامنة حالة المحرر من الـ URL (deep-link / back-forward / رابط رقم الفاتورة)
  useEffect(() => {
    const m = (location.pathname || "").match(/^\/sales\/invoices\/(.+?)\/?$/);
    const seg = m ? decodeURIComponent(m[1]) : "";
    if (!seg) {
      setEditorOpen(false);
      setDraftToEditId(null);
      return;
    }
    if (seg === "new") {
      setDraftToEditId(null);
      setEditorOpen(true);
      return;
    }
    const id = parseInt(seg, 10);
    if (!Number.isNaN(id)) {
      setDraftToEditId(id);
      setEditorOpen(true);
    }
  }, [location.pathname]);

  useAseelIndexKeymap({
    F2: () => {
      if (selectedKey != null) {
        const row = rows.find((r) => r.id === selectedKey);
        if (row && row.status === "draft") openEdit(row.id);
      }
    },
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    CtrlIns: openNew,
    Enter: () => {
      if (selectedKey != null) {
        const row = rows.find((r) => r.id === selectedKey);
        if (row && row.status === "draft") openEdit(row.id);
      }
    },
  });

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
        setMsg(`أمر إخراج #${created.id} — تسليم + COGS`);
      } else {
        setMsg(`أمر إخراج #${created.id} (قيد التنفيذ)`);
      }
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل أمر الإخراج");
    }
  };

  const handleDeleteDraft = async (id: number) => {
    if (!(await confirm({ title: "حذف المسودة", message: "حذف هذه المسودة نهائياً؟" }))) return;
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

  const columns: DenseColumn<ExtRow>[] = [
    {
      key: "invoice_number",
      header: "رقم",
      width: "120px",
      render: (r) => (
        <span className="font-mono text-xs flex items-center gap-1">
          {(r as ExtRow & { __pending?: boolean }).__pending && (
            <span
              className="inline-block w-2 h-2 rounded-full bg-amber-500"
              title="مسوَّدة محلية — لم تُرحَّل بعد"
              aria-label="مسوَّدة معلَّقة"
            />
          )}
          {/* task16 A7: رقم الفاتورة نفسه رابط يفتح الفاتورة */}
          {(r as ExtRow & { __pending?: boolean }).__pending ? (
            r.invoice_number
          ) : (
            <button
              type="button"
              className="text-blue-700 hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                openEdit(r.id);
              }}
              title="فتح الفاتورة"
            >
              {r.invoice_number}
            </button>
          )}
        </span>
      ),
    },
    {
      key: "invoice_date",
      header: "التاريخ",
      width: "100px",
      align: "center",
      render: (r) => <span className="text-xs">{r.invoice_date || "—"}</span>,
    },
    {
      key: "customer",
      header: "العميل",
      render: (r) => (
        // task16 A4: اسم العميل رابط يفتح صفحة العملاء
        <button
          type="button"
          className="text-xs text-blue-700 hover:underline"
          onClick={(e) => { e.stopPropagation(); navigate(`/partners/${r.customer}`); }}
          title="فتح ملف العميل"
        >
          {r.customer_name || `#${r.customer}`}
        </button>
      ),
    },
    {
      key: "invoice_type",
      header: "النوع",
      width: "60px",
      align: "center",
      render: (r) => (
        <span style={{ fontSize: "11px" }}>{r.invoice_type === "cash" ? "نقدي" : "آجل"}</span>
      ),
    },
    {
      key: "status",
      header: "الحالة",
      width: "80px",
      align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color:
              r.status === "posted"
                ? "var(--aseel-ok, #2d7d46)"
                : r.status === "draft"
                ? "var(--aseel-warn, #b06800)"
                : "var(--aseel-ink-soft, #777)",
          }}
        >
          {r.status === "posted" ? "مرحَّلة" : r.status === "draft" ? "مسودة" : r.status}
        </span>
      ),
    },
    {
      key: "grand_total",
      header: "الإجمالي",
      width: "110px",
      align: "left",
      numeric: true,
      render: (r) => <span className="aseel-num font-mono text-xs font-semibold">{fmtNum(r.grand_total)}</span>,
    },
    {
      key: "amount_paid",
      header: "المدفوع",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => <span className="aseel-num font-mono text-xs">{fmtNum(r.amount_paid)}</span>,
    },
    {
      key: "balance",
      header: "المتبقي",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => {
        const bal = Number(r.grand_total || 0) - Number(r.amount_paid || 0);
        return (
          <span
            className="aseel-num font-mono text-xs font-semibold"
            style={{
              color: bal > 0 ? "var(--aseel-warn, #b06800)" : "var(--aseel-ok, #2d7d46)",
            }}
          >
            {fmtNum(bal)}
          </span>
        );
      },
    },
    {
      key: "vat_statement",
      header: "الكشف",
      width: "80px",
      align: "center",
      render: (r) => (
        <span className="text-xs" style={{ color: "var(--aseel-ink-soft)" }}>
          {r.vat_statement_no || "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "200px",
      align: "center",
      render: (r) => (
        <div style={{ display: "flex", gap: "3px", flexWrap: "wrap", justifyContent: "center" }}>
          {r.status === "draft" && (
            <>
              <button
                type="button"
                className="aseel-toolbtn"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => { e.stopPropagation(); openEdit(r.id); }}
                title="تعديل"
              >
                <Pencil className="w-3 h-3" />
              </button>
              <button
                type="button"
                className="aseel-toolbtn"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => { e.stopPropagation(); handlePostRow(r.id); }}
                title="ترحيل"
              >
                <Send className="w-3 h-3" />
              </button>
              <button
                type="button"
                className="aseel-toolbtn aseel-toolbtn--danger"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => { e.stopPropagation(); handleDeleteDraft(r.id); }}
                title="حذف"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </>
          )}
          {r.status === "posted" && (
            <>
              {!r.stock_on_post && (
                <button
                  type="button"
                  className="aseel-toolbtn"
                  style={{ fontSize: "10px", padding: "2px 6px" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.confirm("تسليم الآن؟ خصم مخزون + قيد COGS.")) {
                      handleDelivery(r.id, true);
                    }
                  }}
                  title="تسليم"
                >
                  <Truck className="w-3 h-3" /> تسليم
                </button>
              )}
              <button
                type="button"
                className="aseel-toolbtn"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => { e.stopPropagation(); handleDelivery(r.id, false); }}
                title="أمر إخراج"
              >
                <Truck className="w-3 h-3" />
              </button>
            </>
          )}
        </div>
      ),
    },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <label className="aseel-field" style={{ flex: 1, minWidth: "200px" }}>
        <span className="aseel-field-label">بحث (رقم / عميل)</span>
        <input
          className="aseel-input"
          data-aseel-field="search"
          placeholder="بحث... (F6)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <label className="aseel-field" style={{ minWidth: "100px" }}>
        <span className="aseel-field-label">النوع</span>
        <select className="aseel-input" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
          {TYPE_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
      </label>
      <label className="aseel-field" style={{ minWidth: "100px" }}>
        <span className="aseel-field-label">الحالة</span>
        <select className="aseel-input" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          {STATUS_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">من تاريخ</span>
        <input type="date" className="aseel-input" value={filterFrom} onChange={(e) => setFilterFrom(e.target.value)} />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">إلى تاريخ</span>
        <input type="date" className="aseel-input" value={filterTo} onChange={(e) => setFilterTo(e.target.value)} />
      </label>
    </div>
  );

  const toolbarActions: AseelToolbarAction[] = [
    { key: "new", label: "فاتورة جديدة (Ctrl+Ins)", icon: <Plus />, onClick: openNew },
    {
      key: "refresh",
      label: "تحديث",
      icon: loading ? <Loader2 className="animate-spin" /> : <RefreshCw />,
      onClick: () => void load(),
      separatorBefore: true,
    },
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => window.print() },
  ];

  // Sum totals on filtered set
  const totalSum = filteredRows.reduce((s, r) => s + Number(r.grand_total || 0), 0);
  const paidSum = filteredRows.reduce((s, r) => s + Number(r.amount_paid || 0), 0);
  const balanceSum = totalSum - paidSum;

  // task11 M6: جدول الفواتير في منطقة gridwrap الرئيسية المرنة — كان محشوراً
  // في tab سفلي بارتفاع أقصى 220px تاركاً فراغاً أبيض ضخماً وسط الشاشة.
  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)", display: "flex", flexDirection: "column" }}>
      {!editorOpen ? (
        <AseelDocumentShell
          title="فواتير المبيعات"
          state={loading ? "جاري التحميل…" : `${filteredRows.length} من ${rows.length}`}
          actions={toolbarActions}
          header={filterBar}
          status={
            <>
              <span className="aseel-status-item">العدد <b>{filteredRows.length}</b></span>
              <span className="aseel-status-item">الإجمالي <b className="aseel-num">{fmtNum(totalSum)}</b></span>
              <span className="aseel-status-item">المدفوع <b className="aseel-num">{fmtNum(paidSum)}</b></span>
              <span
                className="aseel-status-item"
                style={{ color: balanceSum > 0 ? "#fbbf24" : "#34d399" }}
              >
                المتبقي <b className="aseel-num" style={{ backgroundColor: balanceSum > 0 ? "rgba(251,191,36,0.15)" : "rgba(52,211,153,0.15)" }}>{fmtNum(balanceSum)}</b>
              </span>
            </>
          }
        >
          <div style={{ padding: "8px" }}>
            {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
            {msg && <div className="aseel-banner" style={{ marginBottom: "8px", color: "var(--aseel-ok, #2d7d46)" }}>{msg}</div>}
            <AseelDenseTable<ExtRow>
              columns={columns}
              rows={filteredRows}
              getRowKey={(r) => r.id}
              loading={loading}
              emptyHint="لا توجد فواتير — اضغط Ctrl+Ins للإضافة"
              selectable
              selectedKey={selectedKey}
              onSelect={(k) => setSelectedKey(k as number | null)}
              onRowDoubleClick={(r) => {
                if (r.status === "draft") openEdit(r.id);
              }}
            />
          </div>
        </AseelDocumentShell>
      ) : (
        <div
          style={{
            background: "var(--aseel-bg, #fffbf5)",
            flex: 1,
            position: "relative",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ padding: "8px", borderBottom: "1px solid var(--aseel-border)", display: "flex", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="aseel-toolbtn aseel-toolbtn--danger"
              onClick={closeEditor}
            >
              ✕ إغلاق
            </button>
          </div>
          <SalesInvoiceEditor
            products={products}
            partners={partners}
            currencies={currencies}
            accounts={accounts}
            taxRates={taxRates}
            draftToEditId={draftToEditId}
            onDraftEditConsumed={() => setDraftToEditId(null)}
            onClose={closeEditor}
            onInvoiceSaved={() => {
              closeEditor();
            }}
            invoiceList={rows}
            onOpenGeneralLedger={onOpenGeneralLedger}
            salesSettings={salesSettings}
          />
        </div>
      )}
    </div>
  );
};
