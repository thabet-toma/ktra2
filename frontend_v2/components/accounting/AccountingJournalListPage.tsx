/**
 * N3-T2 — AccountingJournalListPage (L15) inside-out
 * KitDenseTable + شريط فلاتر + useKitIndexKeymap
 * Ref: المحاسبة.txt:48-69
 */
import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { accountingApi } from "../../services/accountingApi";
import { Plus, RefreshCw, Printer } from "lucide-react";
import { invoicePathForReference } from "../../utils/entityLinks";
import { usePermissions } from "../../contexts/PermissionsContext";
import {
  KitDenseTable,
  KitDocumentShell,
  useKitIndexKeymap,
  type DenseColumn,
  type KitToolbarAction,
} from "../kit";
import type { KitTab } from "../kit";

export interface JournalListItem {
  id: number;
  transaction_date: string | null;
  description?: string | null;
  reference_type?: string | null;
  reference_id?: number | null;
  reference_summary?: string | null;
  deal_ref_number?: string | null;
  is_posted: boolean;
  currency_code?: string | null;
  exchange_rate?: string | number;
  tenant_name?: string | null;
  source_label?: string | null;
  created_at?: string | null;
  created_by_name?: string | null;
  total_debit?: string | number | null;
  total_credit?: string | number | null;
  lines?: Array<{ debit?: string | number; credit?: string | number }>;
}

const REF_LABELS: Record<string, string> = {
  LOGISTICS_PAYMENT: "دفعة لوجستية",
  PURCHASE_RECEIPT: "استلام مخزون",
  JOURNAL_REVERSAL: "عكس قيد",
  LOGISTICS_EXPENSE: "مصروف لوجستي",
  LOGISTICS_SHIPMENT: "شحنة دولية",
  SHIPMENT_FREIGHT_ACCRUAL: "استحقاق شحن الوكيل",
  LOGISTICS_CLEARANCE_PAYMENT: "دفعة تخليص",
  // ISSUE #82: "SALES_INVOICE" مقصودةٌ غائبة من هنا — اسمها من المعجم
  // (`refLabel` أدناه) لأنه يتبدّل بقالب الشركة.
  SALES_DELIVERY_COGS: "تكلفة بضاعة مباعة",
  CUSTOMER_PAYMENT: "تحصيل عميل",
  PURCHASE_INVOICE: "فاتورة شراء",
  MANUAL: "قيد يدوي",
  // A3: القيد الذي وسمه المحاسب «تسوية» — نوع مرجع مستقل ليُصفّى وحده.
  ADJUSTMENT: "قيد تسوية",
};
function refLabel(rt: string | null | undefined, salesInvoiceTerm: string) {
  if (rt === "SALES_INVOICE") return salesInvoiceTerm;
  return REF_LABELS[rt || ""] || (rt ? rt : "عام / يدوي");
}
function fmtDate(raw: string | null | undefined) {
  if (!raw) return "—";
  const s = String(raw).slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    const [y, m, d] = s.split("-");
    return `${d}/${m}/${y}`;
  }
  return raw;
}

function fmtTime(raw: string | null | undefined) {
  if (!raw) return "—";
  // expect ISO with time portion, e.g. 2024-12-01T13:45:00Z
  const m = String(raw).match(/T(\d{2}:\d{2})/);
  return m ? m[1] : "—";
}

import { formatMoney } from "../../utils/formatNumber";

function fmtAmount(v: string | number | null | undefined) {
  return formatMoney(v, "—");
}

function journalAmount(j: JournalListItem): number {
  if (j.total_debit != null) return Number(j.total_debit);
  if (j.lines && j.lines.length) {
    return j.lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  }
  return 0;
}

interface Props {
  onNew: () => void;
  onOpen: (id: number, dealRefNumber?: string | null, referenceSummary?: string | null) => void;
  onNavigateToDeal?: (dealRefNumber: string) => void;
}

export const AccountingJournalListPage: React.FC<Props> = ({
  onNew,
  onOpen,
}) => {
  const navigate = useNavigate();
  // ISSUE #82: اسم فاتورة المبيعات من المعجم — يتبدّل باسمه البديل في مكتب المحاسبة.
  const { term } = usePermissions();
  const [rows, setRows] = useState<JournalListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [refType, setRefType] = useState("");
  // A3: تصفية بالحساب وبالمستخدم — سؤالا المحاسب الأولان على دفتر اليومية.
  const [accountId, setAccountId] = useState("");
  const [userId, setUserId] = useState("");
  const [accounts, setAccounts] = useState<Array<{ id: number; code?: string | null; name?: string | null }>>([]);
  const [users, setUsers] = useState<Array<{ id: number; name: string }>>([]);
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const searchRef = useRef(search);
  searchRef.current = search;

  // صيانة الأداء 2026-07: كانت الشاشة تجلب دفتر اليومية كاملاً (آلاف القيود)
  // بكل تحميل. الآن ترقيم دفعات 100 + «تحميل المزيد» — الفلاتر تبقى على الخادم.
  const PAGE_SIZE = 100;
  const [totalCount, setTotalCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const pageRef = useRef(1);

  const buildParams = useCallback((page: number): Record<string, string> => {
    const params: Record<string, string> = {
      page: String(page),
      page_size: String(PAGE_SIZE),
    };
    if (dateFrom.trim()) params.date_from = dateFrom.trim();
    if (dateTo.trim()) params.date_to = dateTo.trim();
    if (refType.trim()) params.reference_type = refType.trim();
    if (accountId.trim()) params.account = accountId.trim();
    if (userId.trim()) params.user = userId.trim();
    const sq = searchRef.current.trim();
    if (sq) params.search = sq;
    return params;
  }, [dateFrom, dateTo, refType, accountId, userId]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      pageRef.current = 1;
      const data = await accountingApi.getJournalsPaged(buildParams(1));
      setRows(data.results as JournalListItem[]);
      setTotalCount(data.count);
      setHasNext(data.hasNext);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  const loadMore = useCallback(async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    try {
      const next = pageRef.current + 1;
      const data = await accountingApi.getJournalsPaged(buildParams(next));
      pageRef.current = next;
      setRows((prev) => [...prev, ...(data.results as JournalListItem[])]);
      setTotalCount(data.count);
      setHasNext(data.hasNext);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoadingMore(false);
    }
  }, [buildParams, loadingMore]);

  useEffect(() => { void load(); }, [load]);

  // A3: خيارات فلترَي الحساب والمستخدم — تُجلب مرة واحدة، وفشلها لا يعطّل الدفتر.
  useEffect(() => {
    void (async () => {
      const [acc, usr] = await Promise.all([
        accountingApi.getAccounts().catch(() => []),
        accountingApi.getJournalUsers().catch(() => []),
      ]);
      setAccounts(acc as Array<{ id: number; code?: string | null; name?: string | null }>);
      setUsers(usr);
    })();
  }, []);

  const openSelected = useCallback(() => {
    if (selectedKey == null) return;
    const row = rows.find((r) => r.id === selectedKey);
    if (row) onOpen(row.id, row.deal_ref_number, row.reference_summary);
  }, [selectedKey, rows, onOpen]);

  useKitIndexKeymap({
    F2: openSelected,
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-ktra-field="search"]');
      el?.focus();
    },
    CtrlIns: onNew,
    Enter: openSelected,
  });

  const columns: DenseColumn<JournalListItem>[] = [
    {
      key: "id",
      header: "رقم القيد",
      width: "80px",
      align: "center",
      render: (r) => <span className="ktra-num font-mono text-xs">{r.id}</span>,
    },
    {
      key: "transaction_date",
      header: "تاريخ القيد",
      width: "100px",
      align: "center",
      render: (r) => <span className="text-xs">{fmtDate(r.transaction_date)}</span>,
    },
    {
      key: "time",
      header: "الساعة",
      width: "70px",
      align: "center",
      render: (r) => <span className="text-xs ktra-num font-mono">{fmtTime(r.created_at)}</span>,
    },
    {
      key: "amount",
      header: "مبلغ القيد",
      width: "120px",
      align: "left",
      numeric: true,
      render: (r) => <span className="text-xs ktra-num font-mono font-semibold">{fmtAmount(journalAmount(r))}</span>,
      exportValue: (r) => journalAmount(r),
    },
    {
      key: "currency",
      header: "العملة",
      width: "60px",
      align: "center",
      render: (r) => <span className="text-xs">{r.currency_code || "—"}</span>,
    },
    {
      key: "description",
      header: "بيان القيد الإجمالي",
      render: (r) => (
        <span className="text-xs" title={r.description || ""}>
          {r.description || "—"}
        </span>
      ),
    },
    {
      key: "user",
      header: "المستخدم",
      width: "110px",
      render: (r) => (
        <span className="text-xs text-[var(--ktra-ink-soft)]">{r.created_by_name || "—"}</span>
      ),
    },
    {
      key: "ref_type",
      header: "النوع",
      width: "120px",
      render: (r) => {
        // task16 A6: مرجع فاتورة البيع/الشراء في القيد رابط يفتح الفاتورة
        const href = invoicePathForReference(r.reference_type, r.reference_id);
        const label = `${refLabel(r.reference_type, term("doc.sales_invoice"))}${r.reference_id ? ` #${r.reference_id}` : ""}`;
        if (!href) {
          return <span className="text-xs text-[var(--ktra-ink-soft)]">{label}</span>;
        }
        return (
          <button
            type="button"
            className="text-xs text-blue-700 hover:underline"
            onClick={(e) => {
              e.stopPropagation();
              navigate(href);
            }}
            title="فتح الفاتورة المرتبطة"
          >
            {label}
          </button>
        );
      },
    },
    {
      key: "status",
      header: "الحالة",
      width: "70px",
      align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: r.is_posted ? "var(--ktra-ok, #2d7d46)" : "var(--ktra-warn, #b06800)",
          }}
        >
          {r.is_posted ? "مرحَّل" : "مسودة"}
        </span>
      ),
    },
    {
      key: "action",
      header: "",
      width: "56px",
      align: "center",
      render: (r) => (
        <button
          type="button"
          className="ktra-toolbtn"
          style={{ fontSize: "11px", padding: "2px 8px" }}
          onClick={() => onOpen(r.id, r.deal_ref_number, r.reference_summary)}
        >
          فتح
        </button>
      ),
    },
  ];

  const toolbarActions: KitToolbarAction[] = [
    { key: "new", label: "قيد جديد", icon: <Plus />, onClick: onNew },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: () => void load(),
      separatorBefore: true,
    },
    {
      key: "print",
      label: "طباعة",
      icon: <Printer />,
      onClick: () => window.print(),
    },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <label className="ktra-field" style={{ flex: "1", minWidth: "160px" }}>
        <span className="ktra-field-label">بحث</span>
        <input
          className="ktra-input"
          data-ktra-field="search"
          placeholder="رقم القيد / البيان / مرجع"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void load()}
        />
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">من تاريخ</span>
        <input
          className="ktra-input"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">إلى تاريخ</span>
        <input
          className="ktra-input"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
        />
      </label>
      <label className="ktra-field">
        <span className="ktra-field-label">نوع المرجع</span>
        <select
          className="ktra-input"
          value={refType}
          onChange={(e) => setRefType(e.target.value)}
        >
          <option value="">الكل</option>
          {Object.entries(REF_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </label>
      {/* A3: الحساب — «أرِني قيود هذا الحساب وحده» */}
      <label className="ktra-field" style={{ minWidth: "180px" }}>
        <span className="ktra-field-label">الحساب</span>
        <select
          className="ktra-input"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
        >
          <option value="">كل الحسابات</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.code ? `${a.code} — ` : ""}{a.name || `#${a.id}`}
            </option>
          ))}
        </select>
      </label>
      {/* A3: المستخدم — مَن أنشأ القيد (القيود الأقدم من هذا العمود بلا مستخدم) */}
      <label className="ktra-field">
        <span className="ktra-field-label">المستخدم</span>
        <select
          className="ktra-input"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
        >
          <option value="">كل المستخدمين</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
      </label>
      {/* A3: شارة قيود التسوية — سؤال يتكرر كل إقفال، فلا يُدفن في قائمة الأنواع */}
      <button
        type="button"
        className="ktra-toolbtn"
        aria-pressed={refType === "ADJUSTMENT"}
        title="عرض قيود التسوية وحدها"
        onClick={() => setRefType((t) => (t === "ADJUSTMENT" ? "" : "ADJUSTMENT"))}
        style={{
          alignSelf: "flex-end",
          fontWeight: refType === "ADJUSTMENT" ? 700 : undefined,
          borderColor: refType === "ADJUSTMENT" ? "var(--ktra-ok, #2d7d46)" : undefined,
          color: refType === "ADJUSTMENT" ? "var(--ktra-ok, #2d7d46)" : undefined,
        }}
      >
        قيود التسوية {refType === "ADJUSTMENT" ? "✓" : ""}
      </button>
      <button
        type="button"
        className="ktra-toolbtn"
        onClick={() => void load()}
        style={{ alignSelf: "flex-end" }}
      >
        <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
        تطبيق
      </button>
    </div>
  );

  const tabs: KitTab[] = [
    {
      key: "list",
      label: "دفتر اليومية",
      content: (
        <div style={{ padding: "8px" }}>
          {filterBar}
          {err && (
            <div className="ktra-banner ktra-banner--err" style={{ marginTop: "8px" }}>
              {err}
            </div>
          )}
          <div style={{ marginTop: "8px" }}>
            <KitDenseTable<JournalListItem>
              columns={columns}
              rows={rows}
              getRowKey={(r) => r.id}
              loading={loading}
              emptyHint="لا توجد قيود — أضف قيداً جديداً (Ctrl+Ins)"
              selectable
              selectedKey={selectedKey}
              onSelect={(k) => setSelectedKey(k as number | null)}
              onRowDoubleClick={(r) => onOpen(r.id, r.deal_ref_number, r.reference_summary)}
              exportable
              exportFilename={`daybook-${dateFrom || "all"}_${dateTo || "all"}`}
            />
          </div>
          {hasNext && (
            <div style={{ display: "flex", justifyContent: "center", padding: "8px" }}>
              <button
                type="button"
                className="ktra-toolbtn"
                disabled={loadingMore}
                onClick={() => void loadMore()}
              >
                {loadingMore
                  ? "جاري التحميل…"
                  : `تحميل المزيد (${rows.length} من ${totalCount})`}
              </button>
            </div>
          )}
        </div>
      ),
    },
  ];

  return (
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <KitDocumentShell
        title="دفتر اليومية"
        state={loading ? "جاري التحميل…" : `${totalCount || rows.length} قيد`}
        actions={toolbarActions}
        header={<></>}
        tabs={tabs}
        status={
          <>
            <span className="ktra-status-item">
              الإجمالي <b>{totalCount || rows.length}</b>
            </span>
            <span className="ktra-status-item">
              مرحَّل <b>{rows.filter((r) => r.is_posted).length}</b>
            </span>
            <span className="ktra-status-item">
              مسودات <b>{rows.filter((r) => !r.is_posted).length}</b>
            </span>
          </>
        }
      />
    </div>
  );
};
