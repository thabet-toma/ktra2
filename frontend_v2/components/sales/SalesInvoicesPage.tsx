/**
 * N4-T1 — SalesInvoicesPage (L7) Kit inside-out
 * KitDocumentShell + KitDenseTable + شريط فلاتر + useKitIndexKeymap
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
  listSalesInvoicesPage,
  postSalesInvoice,
  deleteSalesInvoice,
  getSalesSettings,
  type DeliveryStatus,
  type SalesInvoiceRow,
  type SalesSettings,
} from "../../services/salesApi";
import { DeliverGoodsModal } from "./DeliverGoodsModal";
import { apiGetList } from "../../services/restApi";
import { listPickerProducts } from "../../services/inventoryApi";
import {
  Loader2,
  RefreshCw,
  Send,
  Truck,
  Trash2,
  Plus,
  Printer,
  FileText,
  Wallet,
} from "lucide-react";
import { SalesInvoiceEditor, type PartnerRow, type ProductRow } from "./SalesInvoiceEditor";
import { resolveTenantId } from "../../utils/tenantContext";
import { eventBus } from "../../utils/eventBus";
import { openInNewTab } from "../../utils/openInNewTab";
import { isOfflineRecordForTenant } from "../../utils/offlineTenantScope";
import { clientLogger } from "../../services/logger";
import { PaymentStatusBadge } from "../shared/PaymentStatusBadge";
import { deriveInvoiceSettlement } from "../shared/DocumentPaymentPanel";
import {
  KitDocumentShell,
  KitDenseTable,
  KitDateInput,
  useKitIndexKeymap,
  type DenseColumn,
  type KitToolbarAction,
} from "../kit";

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

/** شارات حالة التسليم — نفس ألوان الحالات في باقي الشاشات. */
const DELIVERY_BADGE: Record<DeliveryStatus, { label: string; color: string }> = {
  not_delivered: { label: "غير مسلَّمة", color: "var(--ktra-warn, #b06800)" },
  partially_delivered: { label: "مسلَّمة جزئياً", color: "var(--ktra-accent, #2563eb)" },
  delivered: { label: "مسلَّمة", color: "var(--ktra-ok, #2d7d46)" },
};

import { formatMoney } from "@/utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { useSimpleUi } from "../../hooks/useSimpleUi";
const fmtNum = (s: string | number | undefined | null) => formatMoney(s, "—");

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
  // الفاتورة المفتوحة في نافذة التسليم (إرسالية) — null = مغلقة.
  const [deliverFor, setDeliverFor] = useState<ExtRow | null>(null);

  // filters
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterPaymentStatus, setFilterPaymentStatus] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [totalRows, setTotalRows] = useState(0);
  const pageSize = 50;

  const loadRows = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const result = await listSalesInvoicesPage({
        page,
        page_size: pageSize,
        search: search.trim() || undefined,
        status: filterStatus || undefined,
        payment_status: filterPaymentStatus || undefined,
        invoice_type: filterType || undefined,
        date_from: filterFrom || undefined,
        date_to: filterTo || undefined,
      });
      setRows(result.results as ExtRow[]);
      setTotalRows(result.count);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل تحميل فواتير المبيعات");
    } finally {
      setLoading(false);
    }
  }, [filterFrom, filterPaymentStatus, filterStatus, filterTo, filterType, page, search]);

  const loadMasterData = useCallback(async () => {
    const tenantId = resolveTenantId();
    const parts = ["العملاء", "المنتجات", "العملات", "الحسابات", "الضرائب"] as const;
    const settled = await Promise.allSettled([
      apiGetList<PartnerRow>("partners/lookup/", { tenantId, query: { limit: 500 } }),
      listPickerProducts<ProductRow>(tenantId),
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
    if (settled[0].status === "fulfilled") setPartners(settled[0].value);
    if (settled[1].status === "fulfilled") setProducts(settled[1].value);
    if (settled[2].status === "fulfilled") setCurrencies(settled[2].value);
    if (settled[3].status === "fulfilled") setAccounts(settled[3].value.filter((a) => a.id));
    if (settled[4].status === "fulfilled") setTaxRates(settled[4].value);
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
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadRows(); }, 250);
    return () => window.clearTimeout(timer);
  }, [loadRows]);

  useEffect(() => { void loadMasterData(); }, [loadMasterData]);

  useEffect(() => {
    const unsubscribe = eventBus.subscribe((event) => {
      const tenantId = resolveTenantId();
      if (event.type === "settings") {
        getSalesSettings().then(setSalesSettings).catch(() => {});
      } else if (event.type === "partners") {
        apiGetList<PartnerRow>("partners/lookup/", { tenantId, query: { limit: 500 } }).then(setPartners).catch(() => {});
      } else if (event.type === "products") {
        listPickerProducts<ProductRow>(tenantId).then(setProducts).catch(() => {});
      }
    });
    return unsubscribe;
  }, []);

  // P4-3: pull pending sales-invoice mutations from the offline queue so
  // local drafts show up alongside posted records with a «معلَّقة» badge.
  const [pendingDrafts, setPendingDrafts] = useState<ExtRow[]>([]);
  useEffect(() => {
    let cancelled = false;
    const tenantId = resolveTenantId();
    (async () => {
      try {
        const db = (await import("../../services/offline/db")).default;
        const queued = await db.mutation_queue
          .where("endpoint")
          .startsWith("sales/invoices")
          .filter((m) =>
            isOfflineRecordForTenant(m, tenantId) && m.status !== "synced"
          )
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

  const filteredRows = [...(page === 1 ? pendingDrafts : []), ...rows];

  // task16 A8: قائمة الفواتير (/sales/invoices) وتفصيل فاتورة واحدة
  // (/sales/invoices/:id) لهما مساران مستقلان — الـ URL هو مصدر الحقيقة لفتح
  // المحرر. فتح/إغلاق المحرر يتم عبر التنقّل، وتأثير المزامنة أدناه يضبط الحالة.
  const openNew = () => {
    openInNewTab("/sales/invoices/new");
  };

  /** فتح الفاتورة — تُفتح على وضع العرض، والتحرير من زر «تحرير» داخلها. */
  const openInvoice = (id: number) => {
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

  useKitIndexKeymap({
    F2: () => {
      if (selectedKey != null) {
        const row = rows.find((r) => r.id === selectedKey);
        if (row && row.status === "draft") openInvoice(row.id);
      }
    },
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-ktra-field="search"]');
      el?.focus();
    },
    CtrlIns: openNew,
    Enter: () => {
      if (selectedKey != null) {
        const row = rows.find((r) => r.id === selectedKey);
        if (row && row.status === "draft") openInvoice(row.id);
      }
    },
  });

  const handlePostRow = async (id: number) => {
    setErr(null);
    setMsg(null);
    try {
      await postSalesInvoice(id);
      setMsg(`تم ترحيل الفاتورة #${id}`);
      await loadRows();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  const handleDelivered = async (message: string) => {
    setDeliverFor(null);
    setErr(null);
    setMsg(message);
    await loadRows();
  };

  const handleDeleteDraft = async (id: number) => {
    if (!(await confirm({ title: "حذف المسودة", message: "حذف هذه المسودة نهائياً؟" }))) return;
    setErr(null);
    setMsg(null);
    try {
      await deleteSalesInvoice(id);
      setMsg("تم حذف المسودة.");
      await loadRows();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  /* T-SIMPL2: قناع أعمدة القائمة من السِّجل الواحد (`utils/uiMode.ts`) — لا
     قائمةَ إخفاءٍ ثانية تسكن هذا الملف وتفترق عنه. */
  const { show: showAdv, columns: maskColumns } = useSimpleUi();

  const allColumns: DenseColumn<ExtRow>[] = [
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
                openInvoice(r.id);
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
      render: (r) => <span className="text-xs">{formatDateLocalized(r.invoice_date) || "—"}</span>,
    },
    {
      key: "customer",
      header: "العميل",
      render: (r) => (
        // task16 A4: اسم العميل رابط يفتح صفحة العملاء
        <button
          type="button"
          className="text-xs text-blue-700 hover:underline"
          data-ctx-partner-id={r.customer ?? undefined}
          data-ctx-partner-name={r.customer_name || ""}
          data-ctx-partner-kind="customer"
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
      width: "90px",
      align: "center",
      render: (r) => (
        // T-RETURNUI: مرجع البيع يُميَّز بشارة حمراء — لا يُقرأ كفاتورة عادية.
        r.invoice_kind === "sale_return" ? (
          <span
            style={{
              fontSize: "11px",
              fontWeight: 700,
              color: "var(--ktra-err, #c0392b)",
              border: "1px solid currentColor",
              borderRadius: "4px",
              padding: "0 4px",
            }}
          >
            مرجع بيع
          </span>
        ) : (
          <span style={{ fontSize: "11px" }}>{r.invoice_type === "cash" ? "نقدي" : "آجل"}</span>
        )
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
                ? "var(--ktra-ok, #2d7d46)"
                : r.status === "draft"
                ? "var(--ktra-warn, #b06800)"
                : "var(--ktra-ink-soft, #777)",
          }}
        >
          {r.status === "posted" ? "مرحَّلة" : r.status === "draft" ? "مسودة" : r.status}
        </span>
      ),
    },
    {
      key: "delivery_status",
      header: "التسليم",
      width: "100px",
      align: "center",
      render: (r) => {
        const st = (r.delivery_status || "not_delivered") as DeliveryStatus;
        return (
          <span
            style={{
              fontSize: "11px",
              fontWeight: 600,
              color: DELIVERY_BADGE[st].color,
            }}
            title="حالة تسليم البضاعة للعميل"
          >
            {r.delivery_status_display || DELIVERY_BADGE[st].label}
          </span>
        );
      },
    },
    {
      key: "grand_total",
      header: "الإجمالي",
      width: "110px",
      align: "left",
      numeric: true,
      render: (r) => <span className="ktra-num font-mono text-xs font-semibold">{fmtNum(r.grand_total)}</span>,
    },
    {
      key: "payment_status",
      header: "حالة الدفع",
      width: "125px",
      align: "center",
      render: (r) => {
        const settlement = deriveInvoiceSettlement({
          grandTotal: Number(r.grand_total || 0),
          paid: Number(r.amount_paid || 0),
          pendingIntent: Number(r.pending_payment_total || 0),
          isPosted: r.status === "posted",
        });
        return (
          <PaymentStatusBadge
            status={r.payment_status}
            label={r.payment_status_display}
            isOverdue={r.is_overdue}
            daysOverdue={r.days_overdue}
            pendingIntent={settlement.pendingIntent}
            intentCoversAll={settlement.intentCoversAll}
          />
        );
      },
    },
    {
      key: "amount_paid",
      header: "المدفوع",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => <span className="ktra-num font-mono text-xs">{fmtNum(r.amount_paid)}</span>,
    },
    {
      key: "balance",
      header: "المتبقي",
      width: "100px",
      align: "left",
      numeric: true,
      render: (r) => {
        // T-INTENT: مسودةٌ سُجِّلت عليها دفعة تُظهر متبقّيها بعدها — وإلا بدت
        // القائمة تكذّب الشاشة التي أدخل فيها المستخدم الدفعة. الوسم بجانبها
        // يقول إنّها لم تدخل الدفاتر بعد.
        const settlement = deriveInvoiceSettlement({
          grandTotal: Number(r.grand_total || 0),
          paid: Number(r.amount_paid || 0),
          pendingIntent: Number(r.pending_payment_total || 0),
          isPosted: r.status === "posted",
        });
        const bal = settlement.remainingAfterIntent;
        return (
          <span className="inline-flex items-center gap-1">
            <span
              className="ktra-num font-mono text-xs font-semibold"
              style={{
                color: bal > 0 ? "var(--ktra-warn, #b06800)" : "var(--ktra-ok, #2d7d46)",
              }}
            >
              {fmtNum(bal)}
            </span>
            {settlement.pendingIntent > 0.009 && (
              <span
                title={`دفعة ${fmtNum(settlement.pendingIntent)} مسجَّلة ولم تُرحَّل بعد`}
                className="inline-flex rounded bg-amber-500 px-1 py-0.5 text-[9px] font-bold text-white"
              >
                غير مرحّلة
              </span>
            )}
          </span>
        );
      },
    },
    {
      key: "customer_balance",
      header: "رصيد العميل",
      width: "110px",
      align: "left",
      numeric: true,
      render: (r) => <span className="ktra-num font-mono text-xs">{fmtNum(r.customer_balance)}</span>,
    },
    {
      key: "vat_statement",
      header: "الكشف",
      width: "80px",
      align: "center",
      render: (r) => (
        <span className="text-xs" style={{ color: "var(--ktra-ink-soft)" }}>
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
                className="ktra-toolbtn"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => { e.stopPropagation(); handlePostRow(r.id); }}
                title="ترحيل"
              >
                <Send className="w-3 h-3" />
              </button>
              <button
                type="button"
                className="ktra-toolbtn ktra-toolbtn--danger"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => { e.stopPropagation(); handleDeleteDraft(r.id); }}
                title="حذف"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </>
          )}
          {/* T-PAYFULL: «مدفوعة» من القائمة — تفتح الفاتورة ولوحة التحصيل
              معبّأة بالمتبقّي كاملاً (مرآة زرّ فواتير الشراء). */}
          {r.status === "posted"
            // المرجع لا يُحصَّل — ولوحةُ التحصيل مخفيّة عليه في المحرّر، فزرٌّ
            // هنا كان سيقود إلى طريقٍ مسدود.
            && r.invoice_kind !== "sale_return"
            && Number(r.grand_total || 0) - Number(r.amount_paid || 0) > 0.009 && (
            <button
              type="button"
              className="ktra-toolbtn"
              style={{ fontSize: "10px", padding: "2px 6px" }}
              onClick={(e) => {
                e.stopPropagation();
                openInNewTab(`/sales/invoices/${r.id}?pay=full`);
              }}
              title="تحصيل كامل المتبقّي"
            >
              <Wallet className="w-3 h-3" /> مدفوعة
            </button>
          )}
          {r.status === "posted" && !r.stock_on_post && r.delivery_status !== "delivered" && (
            <>
              <button
                type="button"
                className="ktra-toolbtn"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => { e.stopPropagation(); setDeliverFor(r); }}
                title="تسليم سريع (اختيار البنود)"
              >
                <Truck className="w-3 h-3" /> تسليم
              </button>
              {/* المحرّر الكامل في شاشة الإرساليات بهذه الفاتورة مربوطةً مسبقاً. */}
              <button
                type="button"
                className="ktra-toolbtn"
                style={{ fontSize: "10px", padding: "2px 6px" }}
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/sales/delivery-notes/new?invoice=${r.id}`);
                }}
                title="إرسالية جديدة"
              >
                <FileText className="w-3 h-3" />
              </button>
            </>
          )}
        </div>
      ),
    },
  ];

  /* الأعمدة بعد القناع. القائمة كاملةٌ في الوضع المتقدّم حرفياً كما كانت. */
  const columns = maskColumns(allColumns, "sales-invoices");

  const filterBar = (
    <div className="ktra-print-hidden" style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <label className="ktra-field" style={{ flex: 1, minWidth: "200px" }}>
        <span className="ktra-field-label">بحث (رقم / عميل)</span>
        <input
          className="ktra-input"
          data-ktra-field="search"
          placeholder="بحث... (F6)"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
      </label>
      {/* T-SIMPL2: فلتر النوع يُطوى في السهل — ويعود متى كان مفعّلاً فعلاً،
          فلا تبقى قائمةٌ مُرشَّحة بفلترٍ لا يراه صاحبها ولا يستطيع رفعه. */}
      {showAdv("list.type-filter", Boolean(filterType)) && (
        <label className="ktra-field" style={{ minWidth: "100px" }}>
          <span className="ktra-field-label">النوع</span>
          <select className="ktra-input" value={filterType} onChange={(e) => { setFilterType(e.target.value); setPage(1); }}>
            {TYPE_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
          </select>
        </label>
      )}
      <label className="ktra-field" style={{ minWidth: "100px" }}>
        <span className="ktra-field-label">الحالة</span>
        <select className="ktra-input" value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}>
          {STATUS_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
      </label>
      <label className="ktra-field" style={{ minWidth: "125px" }}>
        <span className="ktra-field-label">حالة الدفع</span>
        <select
          className="ktra-input"
          value={filterPaymentStatus}
          onChange={(e) => {
            const value = e.target.value;
            clientLogger.info("sales_invoice.payment_filter_changed", { paymentStatus: value || "all" });
            setFilterPaymentStatus(value);
            setPage(1);
          }}
        >
          <option value="">الكل</option>
          <option value="unpaid">غير مدفوعة</option>
          <option value="partially_paid">مدفوعة جزئياً</option>
          <option value="paid">مدفوعة بالكامل</option>
          {/* T-DUE: خيارٌ فوق الثلاثة لا رابعٌ بينها — «عليها متبقٍّ واستحقاقها مضى». */}
          <option value="overdue">متأخرة</option>
        </select>
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">من تاريخ</span>
        <KitDateInput value={filterFrom} onChange={(value) => { clientLogger.info("sales_invoice.date_filter_changed", { boundary: "from", hasValue: Boolean(value) }); setFilterFrom(value); setPage(1); }} />
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">إلى تاريخ</span>
        <KitDateInput value={filterTo} onChange={(value) => { clientLogger.info("sales_invoice.date_filter_changed", { boundary: "to", hasValue: Boolean(value) }); setFilterTo(value); setPage(1); }} />
      </label>
    </div>
  );

  const toolbarActions: KitToolbarAction[] = [
    { key: "new", label: "فاتورة جديدة (Ctrl+Ins)", icon: <Plus />, onClick: openNew },
    {
      key: "refresh",
      label: "تحديث",
      icon: loading ? <Loader2 className="animate-spin" /> : <RefreshCw />,
      onClick: () => void loadRows(),
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
    <div style={{ minHeight: "calc(100vh - 5rem)", display: "flex", flexDirection: "column" }}>
      {!editorOpen ? (
        <KitDocumentShell
          title="فواتير المبيعات"
          state={loading ? "جاري التحميل…" : `${filteredRows.length} في الصفحة من ${totalRows}`}
          actions={toolbarActions}
          header={filterBar}
          status={
            <>
              <span className="ktra-status-item">العدد <b>{filteredRows.length}</b></span>
              <span className="ktra-status-item">الإجمالي <b className="ktra-num">{fmtNum(totalSum)}</b></span>
              <span className="ktra-status-item">المدفوع <b className="ktra-num">{fmtNum(paidSum)}</b></span>
              <span
                className="ktra-status-item"
                style={{ color: balanceSum > 0 ? "#fbbf24" : "#34d399" }}
              >
                المتبقي <b className="ktra-num" style={{ backgroundColor: balanceSum > 0 ? "rgba(251,191,36,0.15)" : "rgba(52,211,153,0.15)" }}>{fmtNum(balanceSum)}</b>
              </span>
            </>
          }
        >
          <div style={{ padding: "8px" }}>
            {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
            {msg && <div className="ktra-banner" style={{ marginBottom: "8px", color: "var(--ktra-ok, #2d7d46)" }}>{msg}</div>}
            <KitDenseTable<ExtRow>
              columns={columns}
              rows={filteredRows}
              getRowKey={(r) => r.id}
              loading={loading}
              emptyHint="لا توجد فواتير — اضغط Ctrl+Ins للإضافة"
              selectable
              selectedKey={selectedKey}
              onSelect={(k) => setSelectedKey(k as number | null)}
              onRowClick={(r) => openInvoice(r.id)}
              onRowDoubleClick={(r) => openInvoice(r.id)}
              pagination={{ page, pageSize, total: totalRows, onChange: setPage }}
            />
          </div>
        </KitDocumentShell>
      ) : (
        <div
          style={{
            background: "var(--ktra-bg, #fffbf5)",
            flex: 1,
            position: "relative",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ padding: "8px", borderBottom: "1px solid var(--ktra-border)", display: "flex", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="ktra-toolbtn ktra-toolbtn--danger"
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
              void loadRows();
            }}
            invoiceList={rows}
            onOpenGeneralLedger={onOpenGeneralLedger}
            salesSettings={salesSettings}
            initialCustomerId={new URLSearchParams(location.search).get("customer_id") ? Number(new URLSearchParams(location.search).get("customer_id")) : undefined}
            /* T-PAYFULL: `?pay=full` من زرّ «مدفوعة» في القائمة. */
            autoFillCollectFull={new URLSearchParams(location.search).get("pay") === "full"}
          />
        </div>
      )}
      {deliverFor && (
        <DeliverGoodsModal
          invoiceId={deliverFor.id}
          invoiceNumber={deliverFor.invoice_number}
          onClose={() => setDeliverFor(null)}
          onDelivered={handleDelivered}
        />
      )}
    </div>
  );
};
