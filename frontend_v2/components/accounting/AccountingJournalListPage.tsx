/**
 * N3-T2 — AccountingJournalListPage (L15) inside-out
 * AseelDenseTable + شريط فلاتر + useAseelIndexKeymap
 * Ref: المحاسبة.txt:48-69
 */
import React, { useEffect, useState, useCallback, useRef } from "react";
import { accountingApi } from "../../services/accountingApi";
import { Plus, RefreshCw, Printer } from "lucide-react";
import {
  AseelDenseTable,
  AseelDocumentShell,
  useAseelIndexKeymap,
  type DenseColumn,
  type AseelToolbarAction,
} from "../aseel";
import type { AseelTab } from "../aseel";

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
}

const REF_LABELS: Record<string, string> = {
  LOGISTICS_PAYMENT: "دفعة لوجستية",
  PURCHASE_RECEIPT: "استلام مخزون",
  JOURNAL_REVERSAL: "عكس قيد",
  LOGISTICS_EXPENSE: "مصروف لوجستي",
  LOGISTICS_SHIPMENT: "شحنة دولية",
  LOGISTICS_CLEARANCE_PAYMENT: "دفعة تخليص",
  SALES_INVOICE: "فاتورة مبيعات",
  SALES_DELIVERY_COGS: "تكلفة بضاعة مباعة",
  CUSTOMER_PAYMENT: "تحصيل عميل",
  PURCHASE_INVOICE: "فاتورة شراء",
  MANUAL: "قيد يدوي",
};
function refLabel(rt: string | null | undefined) {
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

interface Props {
  onNew: () => void;
  onOpen: (id: number, dealRefNumber?: string | null, referenceSummary?: string | null) => void;
  onNavigateToDeal?: (dealRefNumber: string) => void;
}

export const AccountingJournalListPage: React.FC<Props> = ({
  onNew,
  onOpen,
}) => {
  const [rows, setRows] = useState<JournalListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [refType, setRefType] = useState("");
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const searchRef = useRef(search);
  searchRef.current = search;

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {};
      if (dateFrom.trim()) params.date_from = dateFrom.trim();
      if (dateTo.trim()) params.date_to = dateTo.trim();
      if (refType.trim()) params.reference_type = refType.trim();
      const sq = searchRef.current.trim();
      if (sq) params.search = sq;
      const data = (await accountingApi.getJournals(
        Object.keys(params).length ? params : undefined
      )) as JournalListItem[];
      setRows(data);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, refType]);

  useEffect(() => { void load(); }, [load]);

  const openSelected = useCallback(() => {
    if (selectedKey == null) return;
    const row = rows.find((r) => r.id === selectedKey);
    if (row) onOpen(row.id, row.deal_ref_number, row.reference_summary);
  }, [selectedKey, rows, onOpen]);

  useAseelIndexKeymap({
    F2: openSelected,
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    CtrlIns: onNew,
    Enter: openSelected,
  });

  const columns: DenseColumn<JournalListItem>[] = [
    {
      key: "id",
      header: "رقم القيد",
      width: "90px",
      align: "center",
      render: (r) => <span className="aseel-num font-mono text-xs">{r.id}</span>,
    },
    {
      key: "transaction_date",
      header: "تاريخ القيد",
      width: "110px",
      align: "center",
      render: (r) => <span className="text-xs">{fmtDate(r.transaction_date)}</span>,
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
      key: "ref_type",
      header: "النوع",
      width: "130px",
      render: (r) => (
        <span className="text-xs text-[var(--aseel-ink-soft)]">
          {refLabel(r.reference_type)}
          {r.reference_id ? ` #${r.reference_id}` : ""}
        </span>
      ),
    },
    {
      key: "currency",
      header: "العملة",
      width: "70px",
      align: "center",
      render: (r) => <span className="text-xs">{r.currency_code || "—"}</span>,
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
            color: r.is_posted ? "var(--aseel-ok, #2d7d46)" : "var(--aseel-warn, #b06800)",
          }}
        >
          {r.is_posted ? "مرحَّل" : "مسودة"}
        </span>
      ),
    },
    {
      key: "action",
      header: "",
      width: "60px",
      align: "center",
      render: (r) => (
        <button
          type="button"
          className="aseel-toolbtn"
          style={{ fontSize: "11px", padding: "2px 8px" }}
          onClick={() => onOpen(r.id, r.deal_ref_number, r.reference_summary)}
        >
          فتح
        </button>
      ),
    },
  ];

  const toolbarActions: AseelToolbarAction[] = [
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
      <label className="aseel-field" style={{ flex: "1", minWidth: "160px" }}>
        <span className="aseel-field-label">بحث</span>
        <input
          className="aseel-input"
          data-aseel-field="search"
          placeholder="رقم القيد / البيان / مرجع"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void load()}
        />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">من تاريخ</span>
        <input
          className="aseel-input"
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">إلى تاريخ</span>
        <input
          className="aseel-input"
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
        />
      </label>
      <label className="aseel-field">
        <span className="aseel-field-label">نوع المرجع</span>
        <select
          className="aseel-input"
          value={refType}
          onChange={(e) => setRefType(e.target.value)}
        >
          <option value="">الكل</option>
          {Object.entries(REF_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="aseel-toolbtn"
        onClick={() => void load()}
        style={{ alignSelf: "flex-end" }}
      >
        <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
        تطبيق
      </button>
    </div>
  );

  const tabs: AseelTab[] = [
    {
      key: "list",
      label: "دفتر اليومية",
      content: (
        <div style={{ padding: "8px" }}>
          {filterBar}
          {err && (
            <div className="aseel-banner aseel-banner--err" style={{ marginTop: "8px" }}>
              {err}
            </div>
          )}
          <div style={{ marginTop: "8px" }}>
            <AseelDenseTable<JournalListItem>
              columns={columns}
              rows={rows}
              getRowKey={(r) => r.id}
              loading={loading}
              emptyHint="لا توجد قيود — أضف قيداً جديداً (Ctrl+Ins)"
              selectable
              selectedKey={selectedKey}
              onSelect={(k) => setSelectedKey(k as number | null)}
              onRowDoubleClick={(r) => onOpen(r.id, r.deal_ref_number, r.reference_summary)}
            />
          </div>
        </div>
      ),
    },
  ];

  return (
    <div data-skin="aseel" style={{ height: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="دفتر اليومية"
        state={loading ? "جاري التحميل…" : `${rows.length} قيد`}
        actions={toolbarActions}
        header={<></>}
        tabs={tabs}
        status={
          <>
            <span className="aseel-status-item">
              الإجمالي <b>{rows.length}</b>
            </span>
            <span className="aseel-status-item">
              مرحَّل <b>{rows.filter((r) => r.is_posted).length}</b>
            </span>
            <span className="aseel-status-item">
              مسودات <b>{rows.filter((r) => !r.is_posted).length}</b>
            </span>
          </>
        }
      />
    </div>
  );
};
