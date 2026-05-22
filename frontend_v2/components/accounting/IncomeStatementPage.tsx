import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { TrialBalanceRow } from "../../types/accounting";
import {
  AseelDocumentShell,
  AseelReportTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, ReportColumn } from "../aseel";
import { Search } from "lucide-react";

interface IncomeRow {
  code: string | null;
  name: string | null;
  account_type: string | null;
  revenue: number;
  expense: number;
  net: number;
}

export const IncomeStatementPage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(`${today.getFullYear()}-01-01`);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [rows, setRows] = useState<IncomeRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await accountingApi.getTrialBalance({
        start_date: start,
        end_date: end,
        show_all: "false",
      });
      const tbRows: TrialBalanceRow[] = Array.isArray(resp)
        ? (resp as TrialBalanceRow[])
        : (resp as { rows: TrialBalanceRow[] }).rows || [];

      const isRows: IncomeRow[] = tbRows
        .filter((r) => ["Revenue", "Expense"].includes(r.account_type || ""))
        .map((r) => {
          const pd = r.period_debit ?? r.total_debit ?? 0;
          const pc = r.period_credit ?? r.total_credit ?? 0;
          const isRevenue = r.account_type === "Revenue";
          const revenue = isRevenue ? pc - pd : 0;
          const expense = !isRevenue ? pd - pc : 0;
          const net = revenue - expense;
          return {
            code: r.code,
            name: r.name,
            account_type: r.account_type,
            revenue,
            expense,
            net,
          };
        })
        .filter((r) => Math.abs(r.revenue) > 0.001 || Math.abs(r.expense) > 0.001);

      setRows(isRows);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fmt = (n: number) =>
    n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const totalRevenue = rows.reduce((s, r) => s + r.revenue, 0);
  const totalExpense = rows.reduce((s, r) => s + r.expense, 0);
  const netProfit = totalRevenue - totalExpense;

  const columns: ReportColumn<IncomeRow>[] = [
    { key: "code", header: "كود", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.code}</span> },
    { key: "name", header: "الحساب", render: (r) => r.name },
    {
      key: "account_type", header: "النوع",
      render: (r) => (
        <span style={{
          padding: "1px 8px", borderRadius: "10px",
          background: r.account_type === "Revenue" ? "#dcfce715" : "#fee2e215",
          color: r.account_type === "Revenue" ? "#16a34a" : "#dc2626",
          fontSize: "0.75rem",
        }}>
          {r.account_type === "Revenue" ? "إيرادات" : "مصروفات"}
        </span>
      ),
    },
    {
      key: "revenue", header: "الإيرادات", numeric: true,
      render: (r) => r.revenue > 0 ? fmt(r.revenue) : "—",
    },
    {
      key: "expense", header: "المصروفات", numeric: true,
      render: (r) => r.expense > 0 ? fmt(r.expense) : "—",
    },
    {
      key: "net", header: "الصافي", numeric: true,
      render: (r) => (
        <span style={{ color: r.net >= 0 ? "#16a34a" : "#dc2626", fontWeight: "600" }}>
          {fmt(r.net)}
        </span>
      ),
    },
  ];

  const totals = rows.length > 0 ? {
    revenue: fmt(totalRevenue),
    expense: fmt(totalExpense),
    net: fmt(netProfit),
  } : undefined;

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="aseel-field">
        <label className="aseel-field-label">من</label>
        <input type="date" className="aseel-input" value={start} onChange={(e) => setStart(e.target.value)} />
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">إلى</label>
        <input type="date" className="aseel-input" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <button type="button" className="aseel-toolbtn" onClick={fetchData} style={{ marginTop: "18px" }}>
        <Search className="w-4 h-4" />عرض
      </button>
    </div>
  );

  const reportContent = (
    <>
      {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <AseelReportTable<IncomeRow>
        filterBar={filterBar}
        columns={columns}
        rows={rows}
        totals={totals}
        exportable={true}
        loading={loading}
        emptyHint="لا بيانات إيرادات أو مصروفات في الفترة"
        getRowKey={(r, idx) => `${r.code || idx}`}
      />
      {rows.length > 0 && (
        <div style={{ marginTop: "12px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <div style={{ padding: "10px 16px", borderRadius: "8px", border: "1px solid #dcfce7", background: "#dcfce715", minWidth: "160px" }}>
            <div style={{ fontSize: "0.75rem", color: "#16a34a", marginBottom: "4px" }}>إجمالي الإيرادات</div>
            <div style={{ fontWeight: "bold", fontSize: "1.1rem" }}>{fmt(totalRevenue)}</div>
          </div>
          <div style={{ padding: "10px 16px", borderRadius: "8px", border: "1px solid #fee2e2", background: "#fee2e215", minWidth: "160px" }}>
            <div style={{ fontSize: "0.75rem", color: "#dc2626", marginBottom: "4px" }}>إجمالي المصروفات</div>
            <div style={{ fontWeight: "bold", fontSize: "1.1rem" }}>{fmt(totalExpense)}</div>
          </div>
          <div style={{
            padding: "10px 16px", borderRadius: "8px", minWidth: "160px",
            border: netProfit >= 0 ? "1px solid #dcfce7" : "1px solid #fee2e2",
            background: netProfit >= 0 ? "#dcfce715" : "#fee2e215",
          }}>
            <div style={{ fontSize: "0.75rem", color: netProfit >= 0 ? "#16a34a" : "#dc2626", marginBottom: "4px" }}>
              {netProfit >= 0 ? "صافي الأرباح" : "صافي الخسائر"}
            </div>
            <div style={{ fontWeight: "bold", fontSize: "1.1rem", color: netProfit >= 0 ? "#16a34a" : "#dc2626" }}>
              {fmt(Math.abs(netProfit))}
            </div>
          </div>
        </div>
      )}
    </>
  );

  const shellActions: AseelToolbarAction[] = [
    { key: "run", label: "عرض", icon: <Search className="w-4 h-4" />, onClick: fetchData },
  ];

  const tabs: AseelTab[] = [
    { key: "is", label: "كشف الإيرادات والمصروفات", content: reportContent },
  ];

  return (
    <div data-skin="aseel">
      <AseelDocumentShell
        title="كشف الإيرادات والمصروفات"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          rows.length > 0 ? (
            <span className="aseel-status-item"
              style={{ color: netProfit >= 0 ? "var(--color-success,#16a34a)" : "var(--color-danger,#dc2626)" }}>
              {netProfit >= 0 ? "ربح" : "خسارة"}: {fmt(Math.abs(netProfit))}
            </span>
          ) : undefined
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
