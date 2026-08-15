import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import type { TrialBalanceResponse, TrialBalanceRow } from "../../types/accounting";
import {
  AseelDocumentShell,
  AseelReportTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, ReportColumn } from "../aseel";
import { Search, CheckCircle2, AlertTriangle } from "lucide-react";

export interface AccountingTrialBalancePageProps {
  /** التنقيب: نقر صف الحساب يفتح الأستاذ العام مفلتراً عليه. */
  onOpenAccount?: (accountId: number) => void;
}

export const AccountingTrialBalancePage: React.FC<AccountingTrialBalancePageProps> = ({
  onOpenAccount,
}) => {
  const today = new Date();
  const [start, setStart] = useState(`${today.getFullYear()}-01-01`);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [unposted, setUnposted] = useState(false);
  const [showZero, setShowZero] = useState(false);
  const [data, setData] = useState<TrialBalanceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [search, setSearch] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {
        start_date: start,
        end_date: end,
        show_all: showZero ? "true" : "false",
      };
      if (unposted) params.include_unposted = "true";
      const resp = await accountingApi.getTrialBalance(params);
      // backward compat: legacy response was an array
      if (Array.isArray(resp)) {
        setData({
          start_date: start,
          end_date: end,
          rows: resp as TrialBalanceRow[],
          totals: {
            period_debit: 0,
            period_credit: 0,
            closing_debit: 0,
            closing_credit: 0,
            balanced: true,
            period_difference: 0,
            closing_difference: 0,
          },
        });
      } else {
        setData(resp as TrialBalanceResponse);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end, unposted, showZero]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fmt = (n: number | undefined) => formatMoney(n);

  const rows = (data?.rows || []).filter((r) => {
    if (typeFilter && (r.account_type || "") !== typeFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      if (
        !String(r.code || "").toLowerCase().includes(s) &&
        !String(r.name || "").toLowerCase().includes(s)
      )
        return false;
    }
    return true;
  });

  const types = Array.from(
    new Set((data?.rows || []).map((r) => r.account_type).filter(Boolean)),
  ) as string[];

  const totals = data?.totals;
  const pd = totals?.period_debit || 0;
  const pc = totals?.period_credit || 0;
  const cd = totals?.closing_debit || 0;
  const cc = totals?.closing_credit || 0;

  const columns: ReportColumn<TrialBalanceRow>[] = [
    {
      key: "code", header: "كود",
      // الكود بلون رابط حين يكون الصف قابلاً للتنقيب — وإلا بقيت النقرة سرّاً لا يكتشفه أحد.
      render: (r) => (
        <span
          style={{ fontFamily: "monospace" }}
          className={onOpenAccount ? "text-blue-700 hover:underline" : undefined}
        >
          {r.code}
        </span>
      ),
    },
    { key: "name", header: "الاسم", render: (r) => r.name },
    { key: "account_type", header: "النوع", render: (r) => r.account_type },
    {
      key: "period_debit", header: "مدين الفترة", numeric: true,
      render: (r) => fmt(r.period_debit ?? r.total_debit ?? 0),
      exportValue: (r) => r.period_debit ?? r.total_debit ?? 0,
    },
    {
      key: "period_credit", header: "دائن الفترة", numeric: true,
      render: (r) => fmt(r.period_credit ?? r.total_credit ?? 0),
      exportValue: (r) => r.period_credit ?? r.total_credit ?? 0,
    },
    {
      key: "closing_debit", header: "مدين الختامي", numeric: true, render: (r) => fmt(r.closing_debit),
      exportValue: (r) => r.closing_debit ?? 0,
    },
    {
      key: "closing_credit", header: "دائن الختامي", numeric: true, render: (r) => fmt(r.closing_credit),
      exportValue: (r) => r.closing_credit ?? 0,
    },
  ];

  const reportTotals = {
    period_debit: fmt(pd),
    period_credit: fmt(pc),
    closing_debit: fmt(cd),
    closing_credit: fmt(cc),
  };

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
        <label className="aseel-field-label">نوع</label>
        <select className="aseel-input" style={{ minWidth: "120px" }} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">الكل</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="aseel-field" style={{ flex: "1", minWidth: "180px" }}>
        <label className="aseel-field-label">بحث</label>
        <input type="text" className="aseel-input" placeholder="كود أو اسم..."
          value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <label className="flex items-center gap-2 text-sm" style={{ paddingTop: "18px" }}>
        <input type="checkbox" checked={unposted} onChange={(e) => setUnposted(e.target.checked)} />
        تضمين غير المرحّل
      </label>
      <label className="flex items-center gap-2 text-sm" style={{ paddingTop: "18px" }}>
        <input type="checkbox" checked={showZero} onChange={(e) => setShowZero(e.target.checked)} />
        عرض بدون حركة
      </label>
      <button type="button" className="aseel-toolbtn" onClick={fetchData} style={{ marginTop: "18px" }}>
        <Search className="w-4 h-4" />تحديث
      </button>
    </div>
  );

  const reportContent = (
    <>
      {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <AseelReportTable<TrialBalanceRow>
        filterBar={filterBar}
        columns={columns}
        rows={rows}
        totals={rows.length > 0 ? reportTotals : undefined}
        exportable={true}
        exportFilename={`trial-balance-${start}_${end}`}
        loading={loading}
        emptyHint="لا بيانات"
        getRowKey={(r) => r.id}
        onRowClick={onOpenAccount ? (r) => onOpenAccount(r.id) : undefined}
        rowTitle="فتح الأستاذ العام لهذا الحساب"
      />
    </>
  );

  const shellActions: AseelToolbarAction[] = [
    { key: "run", label: "تحديث", icon: <Search className="w-4 h-4" />, onClick: fetchData },
  ];

  const tabs: AseelTab[] = [
    { key: "balance", label: "ميزان المراجعة", content: reportContent },
  ];

  return (
    <div>
      <AseelDocumentShell
        title="ميزان المراجعة"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          totals ? (
            <span className="aseel-status-item">
              {totals.balanced ? (
                <CheckCircle2 className="w-3 h-3" style={{ color: "var(--color-success,#16a34a)" }} />
              ) : (
                <AlertTriangle className="w-3 h-3" style={{ color: "var(--color-danger,#dc2626)" }} />
              )}
              {totals.balanced ? "متوازن" : `فرق ${fmt(totals.period_difference)}`}
            </span>
          ) : undefined
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
