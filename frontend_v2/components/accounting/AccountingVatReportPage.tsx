import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { VatReportResponse, VatReportLine } from "../../types/accounting";
import {
  AseelDocumentShell,
  AseelReportTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, ReportColumn } from "../aseel";
import { Search } from "lucide-react";

export const AccountingVatReportPage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(() => {
    const d = new Date(today.getFullYear(), today.getMonth(), 1);
    return d.toISOString().split("T")[0];
  });
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [data, setData] = useState<VatReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [vatType, setVatType] = useState<"all" | "input" | "output">("all");

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await accountingApi.getVatReport({
        start_date: start,
        end_date: end,
      });
      setData(resp as VatReportResponse);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const fmt = (n: number | undefined | null) =>
    (Number(n) || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });

  const inputBalance = data?.input.balance || 0;
  const outputPayable = data?.output.balance_payable || 0;
  const net = data?.net_payable || 0;

  // Merge lines based on type filter
  const allLines: (VatReportLine & { vat_type: string })[] = [
    ...(data?.output_lines || []).map((l) => ({ ...l, vat_type: "output" as const })),
    ...(data?.input_lines || []).map((l) => ({ ...l, vat_type: "input" as const })),
  ];
  const lines = vatType === "all"
    ? allLines
    : allLines.filter((l) => l.vat_type === vatType);

  const columns: ReportColumn<VatReportLine & { vat_type: string }>[] = [
    { key: "date", header: "التاريخ", render: (r) => r.date || "—" },
    {
      key: "vat_type", header: "نوع",
      render: (r) => (
        <span style={{
          padding: "1px 8px", borderRadius: "10px",
          background: r.vat_type === "output" ? "#fee2e215" : "#dbeafe15",
          color: r.vat_type === "output" ? "#dc2626" : "#2563eb",
          fontSize: "0.75rem",
        }}>
          {r.vat_type === "output" ? "مخرجات" : "مدخلات"}
        </span>
      ),
    },
    { key: "journal_id", header: "رقم", render: (r) => `#${r.journal_id}` },
    { key: "description", header: "البيان", render: (r) => r.description },
    { key: "partner", header: "الشريك", render: (r) => r.partner || "—" },
    { key: "debit", header: "مدين", numeric: true, render: (r) => fmt(r.debit) },
    { key: "credit", header: "دائن", numeric: true, render: (r) => fmt(r.credit) },
  ];

  const totals = lines.length > 0 ? {
    debit: fmt(lines.reduce((s, l) => s + Number(l.debit), 0)),
    credit: fmt(lines.reduce((s, l) => s + Number(l.credit), 0)),
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
      <div className="aseel-field">
        <label className="aseel-field-label">نوع الضريبة</label>
        <select className="aseel-input" value={vatType} onChange={(e) => setVatType(e.target.value as "all" | "input" | "output")}>
          <option value="all">الكل</option>
          <option value="output">مخرجات</option>
          <option value="input">مدخلات</option>
        </select>
      </div>
      <button type="button" className="aseel-toolbtn" onClick={fetchReport} style={{ marginTop: "18px" }}>
        <Search className="w-4 h-4" />تحديث
      </button>
    </div>
  );

  const summaryBand = data ? (
    <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", padding: "8px 0" }}>
      <div style={{ flex: "1", minWidth: "140px", padding: "10px", borderRadius: "8px", border: "1px solid #dbeafe", background: "#dbeafe15" }}>
        <div style={{ fontSize: "0.75rem", color: "#2563eb", marginBottom: "4px" }}>ضريبة مدخلات (خصم)</div>
        <div style={{ fontWeight: "bold", fontSize: "1.1rem" }}>{fmt(inputBalance)}</div>
      </div>
      <div style={{ flex: "1", minWidth: "140px", padding: "10px", borderRadius: "8px", border: "1px solid #fee2e2", background: "#fee2e215" }}>
        <div style={{ fontSize: "0.75rem", color: "#dc2626", marginBottom: "4px" }}>ضريبة مخرجات (مستحقة)</div>
        <div style={{ fontWeight: "bold", fontSize: "1.1rem" }}>{fmt(outputPayable)}</div>
      </div>
      <div style={{ flex: "1", minWidth: "140px", padding: "10px", borderRadius: "8px", border: net >= 0 ? "1px solid #fef9c3" : "1px solid #dcfce7", background: net >= 0 ? "#fef9c315" : "#dcfce715" }}>
        <div style={{ fontSize: "0.75rem", color: net >= 0 ? "#ca8a04" : "#16a34a", marginBottom: "4px" }}>
          {net >= 0 ? "صافي المستحق للحكومة" : "رصيد دائن (قابل للاسترداد)"}
        </div>
        <div style={{ fontWeight: "bold", fontSize: "1.1rem" }}>{fmt(Math.abs(net))}</div>
      </div>
    </div>
  ) : null;

  const reportContent = (
    <>
      {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      {summaryBand}
      <AseelReportTable<VatReportLine & { vat_type: string }>
        filterBar={filterBar}
        columns={columns}
        rows={lines}
        totals={totals}
        exportable={true}
        loading={loading}
        emptyHint="لا توجد حركات في الفترة"
        getRowKey={(r, idx) => `${r.journal_id}-${idx}`}
      />
    </>
  );

  const shellActions: AseelToolbarAction[] = [
    { key: "run", label: "تحديث", icon: <Search className="w-4 h-4" />, onClick: fetchReport },
  ];

  const tabs: AseelTab[] = [
    { key: "vat", label: "تقرير الضريبة", content: reportContent },
  ];

  return (
    <div data-skin="aseel">
      <AseelDocumentShell
        title="تقرير ضريبة القيمة المضافة"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          data ? (
            <span className="aseel-status-item">
              {lines.length} حركة | صافي: {fmt(net)}
            </span>
          ) : undefined
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
