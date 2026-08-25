import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import type { TrialBalanceRow, CurrencyDto } from "../../types/accounting";
import {
  KitDocumentShell,
  KitReportTable,
} from "../kit";
import type { KitToolbarAction, KitTab, ReportColumn } from "../kit";
import { Search } from "lucide-react";

interface BalanceSheetRow {
  code: string | null;
  name: string | null;
  account_type: string | null;
  amount: number;
  side: "asset" | "liability";
}

export const BalanceSheetPage: React.FC = () => {
  const today = new Date();
  const [asOf, setAsOf] = useState(today.toISOString().split("T")[0]);
  const [rows, setRows] = useState<BalanceSheetRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [currencies, setCurrencies] = useState<CurrencyDto[]>([]);
  const [currencyId, setCurrencyId] = useState("");

  useEffect(() => {
    accountingApi.getCurrencies().then((c) => setCurrencies(c as CurrencyDto[])).catch(() => setCurrencies([]));
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await accountingApi.getTrialBalance({
        start_date: `${new Date(asOf).getFullYear()}-01-01`,
        end_date: asOf,
        show_all: "false",
      });
      const tbRows: TrialBalanceRow[] = Array.isArray(resp)
        ? (resp as TrialBalanceRow[])
        : (resp as { rows: TrialBalanceRow[] }).rows || [];

      const bsRows: BalanceSheetRow[] = tbRows
        .filter((r) => ["Asset", "Liability", "Equity"].includes(r.account_type || ""))
        .map((r) => {
          const closingDebit = r.closing_debit ?? r.total_debit ?? 0;
          const closingCredit = r.closing_credit ?? r.total_credit ?? 0;
          const isAsset = r.account_type === "Asset";
          const amount = isAsset
            ? closingDebit - closingCredit
            : closingCredit - closingDebit;
          return {
            code: r.code,
            name: r.name,
            account_type: r.account_type,
            amount,
            side: (isAsset ? "asset" : "liability") as "asset" | "liability",
          };
        })
        .filter((r) => Math.abs(r.amount) > 0.001);

      setRows(bsRows);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
    } finally {
      setLoading(false);
    }
  }, [asOf]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fmt = (n: number) => formatMoney(n);

  const assets = rows.filter((r) => r.side === "asset");
  const liabilities = rows.filter((r) => r.side === "liability");
  const totalAssets = assets.reduce((s, r) => s + r.amount, 0);
  const totalLiabilities = liabilities.reduce((s, r) => s + r.amount, 0);
  const isBalanced = Math.abs(totalAssets - totalLiabilities) < 0.01;

  const assetColumns: ReportColumn<BalanceSheetRow>[] = [
    { key: "code", header: "كود", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.code}</span> },
    { key: "name", header: "الأصول", render: (r) => r.name },
    { key: "amount", header: "المبلغ", numeric: true, render: (r) => fmt(r.amount) },
  ];

  const liabilityColumns: ReportColumn<BalanceSheetRow>[] = [
    { key: "code", header: "كود", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.code}</span> },
    { key: "name", header: "الخصوم وحقوق الملكية", render: (r) => r.name },
    { key: "amount", header: "المبلغ", numeric: true, render: (r) => fmt(r.amount) },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="ktra-field">
        <label className="ktra-field-label">التاريخ (كما في)</label>
        <input type="date" className="ktra-input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
      </div>
      <div className="ktra-field" style={{ minWidth: "140px" }}>
        <label className="ktra-field-label">العملة</label>
        <select className="ktra-input" value={currencyId} onChange={(e) => setCurrencyId(e.target.value)}>
          <option value="">الأساسية</option>
          {currencies.map((c) => (
            <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>
          ))}
        </select>
      </div>
      <button type="button" className="ktra-toolbtn" onClick={fetchData} style={{ marginTop: "18px" }}>
        <Search className="w-4 h-4" />عرض
      </button>
    </div>
  );

  const reportContent = (
    <>
      {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      {!isBalanced && rows.length > 0 && (
        <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>
          تحذير: الأصول ({fmt(totalAssets)}) ≠ الخصوم وحقوق الملكية ({fmt(totalLiabilities)})
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
        <div>
          <div style={{ fontWeight: "bold", padding: "8px 0", borderBottom: "2px solid var(--ktra-border)", marginBottom: "8px" }}>
            الأصول
          </div>
          <KitReportTable<BalanceSheetRow>
            filterBar={filterBar}
            columns={assetColumns}
            rows={assets}
            totals={assets.length > 0 ? { amount: fmt(totalAssets) } : undefined}
            exportable={false}
            loading={loading}
            emptyHint="لا بيانات"
            getRowKey={(r, idx) => `asset-${r.code || idx}`}
          />
          <div className="ktra-total-row ktra-total-row--grand" style={{ marginTop: "4px" }}>
            <span>إجمالي الأصول</span>
            <span className="ktra-total-value">{fmt(totalAssets)}</span>
          </div>
        </div>
        <div>
          <div style={{ fontWeight: "bold", padding: "8px 0", borderBottom: "2px solid var(--ktra-border)", marginBottom: "8px" }}>
            الخصوم وحقوق الملكية
          </div>
          <KitReportTable<BalanceSheetRow>
            columns={liabilityColumns}
            rows={liabilities}
            totals={liabilities.length > 0 ? { amount: fmt(totalLiabilities) } : undefined}
            exportable={false}
            loading={loading}
            emptyHint="لا بيانات"
            getRowKey={(r, idx) => `liab-${r.code || idx}`}
          />
          <div className="ktra-total-row ktra-total-row--grand" style={{ marginTop: "4px" }}>
            <span>إجمالي الخصوم وحقوق الملكية</span>
            <span className="ktra-total-value">{fmt(totalLiabilities)}</span>
          </div>
        </div>
      </div>
    </>
  );

  const shellActions: KitToolbarAction[] = [
    { key: "run", label: "عرض", icon: <Search className="w-4 h-4" />, onClick: fetchData },
  ];

  const tabs: KitTab[] = [
    { key: "bs", label: "الميزانية العمومية", content: reportContent },
  ];

  return (
    <div>
      <KitDocumentShell
        title="الميزانية العمومية"
        actions={shellActions}
        header={filterBar}
        tabs={tabs}
        status={
          rows.length > 0 ? (
            <span className="ktra-status-item">
              {isBalanced ? "متوازنة ✓" : "غير متوازنة ✗"} | كما في {asOf}
            </span>
          ) : undefined
        }
      >
        <></>
      </KitDocumentShell>
    </div>
  );
};
