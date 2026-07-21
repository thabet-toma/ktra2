import React, { useState, useEffect, useCallback } from "react";
import { getInvoiceProfits, type InvoiceProfitRow, type InvoiceProfitsResponse } from "../../services/salesApi";
import { formatMoney } from "../../utils/formatNumber";
import { AseelDocumentShell, AseelReportTable } from "../aseel";
import type { AseelToolbarAction, AseelTab, ReportColumn } from "../aseel";
import { Search } from "lucide-react";

/**
 * task18 DEF-C4: تقرير أرباح الفواتير — إيراد/تكلفة/ربح لكل فاتورة بيع مرحَّلة
 * مع فلترة بالتاريخ والعميل وإجماليات. التكلفة من حركات مخزون البيع المسجَّلة
 * وقت الترحيل (تكلفة تاريخية)، فتتطابق الأرقام مع بنود الفاتورة.
 */
export const InvoiceProfitsPage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(`${today.getFullYear()}-01-01`);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [search, setSearch] = useState("");
  const [data, setData] = useState<InvoiceProfitsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await getInvoiceProfits({ dateFrom: start, dateTo: end });
      setData(resp);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const fmt = (n: string | number | undefined) => formatMoney(n);

  // فلترة العميل/الرقم محلياً (بحث نصّي) فوق نتيجة المدى الزمني من الخادم.
  const rows = (data?.rows || []).filter((r) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      String(r.customer_name || "").toLowerCase().includes(s) ||
      String(r.invoice_number || "").toLowerCase().includes(s)
    );
  });

  // إجماليات الصفوف المعروضة (تُعاد حسابها مع بحث العميل).
  const shown = rows.reduce(
    (acc, r) => {
      acc.revenue += Number(r.revenue) || 0;
      acc.cost += Number(r.cost) || 0;
      acc.profit += Number(r.profit) || 0;
      return acc;
    },
    { revenue: 0, cost: 0, profit: 0 },
  );

  const columns: ReportColumn<InvoiceProfitRow>[] = [
    { key: "invoice_number", header: "رقم الفاتورة", render: (r) => r.invoice_number },
    { key: "invoice_date", header: "التاريخ", render: (r) => r.invoice_date || "—" },
    { key: "customer_name", header: "العميل", render: (r) => r.customer_name || "—" },
    { key: "revenue", header: "الإيراد", numeric: true, render: (r) => fmt(r.revenue) },
    { key: "cost", header: "التكلفة", numeric: true, render: (r) => fmt(r.cost) },
    { key: "profit", header: "الربح", numeric: true, render: (r) => fmt(r.profit) },
    { key: "margin_pct", header: "هامش %", numeric: true, render: (r) => fmt(r.margin_pct) },
  ];

  const reportTotals = {
    revenue: fmt(shown.revenue),
    cost: fmt(shown.cost),
    profit: fmt(shown.profit),
    margin_pct: shown.revenue > 0 ? fmt((shown.profit / shown.revenue) * 100) : "0.00",
  };

  const setQuickDate = (range: 'today' | 'week' | 'month' | 'year') => {
    const endD = new Date();
    const format = (d: Date) => {
       const y = d.getFullYear();
       const m = String(d.getMonth() + 1).padStart(2, '0');
       const day = String(d.getDate()).padStart(2, '0');
       return `${y}-${m}-${day}`;
    };
    const endStr = format(endD);
    let startStr = endStr;

    if (range === 'week') {
      const startD = new Date(endD);
      // Let's assume the work week starts on Sunday (day 0) or Saturday (day 6). 
      // Subtracting the current day number brings us to Sunday.
      const diff = startD.getDate() - startD.getDay();
      startD.setDate(diff);
      startStr = format(startD);
    } else if (range === 'month') {
      const startD = new Date(endD.getFullYear(), endD.getMonth(), 1);
      startStr = format(startD);
    } else if (range === 'year') {
      const startD = new Date(endD.getFullYear(), 0, 1);
      startStr = format(startD);
    }

    setStart(startStr);
    setEnd(endStr);
    // fetchData() will be called automatically if we wrap it, but start/end are state.
    // Wait, fetchData relies on start and end. Since setState is async, we can just let the user click "تحديث" or trigger it.
    // Actually, setting state and then fetching is better. We can use a useEffect to fetch when start/end change, but the user might not want that.
    // The current code requires clicking "تحديث" (fetchData). Let's let them click it or we can auto-fetch.
    // Let's auto-fetch by calling it? We can't because state isn't updated immediately.
  };

  const filterBar = (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
        <button type="button" className="aseel-btn" onClick={() => setQuickDate('today')}>اليوم</button>
        <button type="button" className="aseel-btn" onClick={() => setQuickDate('week')}>أول الأسبوع</button>
        <button type="button" className="aseel-btn" onClick={() => setQuickDate('month')}>أول الشهر</button>
        <button type="button" className="aseel-btn" onClick={() => setQuickDate('year')}>أول السنة</button>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
        <div className="aseel-field">
          <label className="aseel-field-label">من</label>
          <input type="date" className="aseel-input" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">إلى</label>
          <input type="date" className="aseel-input" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <div className="aseel-field" style={{ flex: "1", minWidth: "180px" }}>
          <label className="aseel-field-label">العميل/الرقم</label>
          <input type="text" className="aseel-input" placeholder="اسم العميل أو رقم الفاتورة..."
            value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <button type="button" className="aseel-toolbtn" onClick={fetchData} style={{ marginTop: "18px" }}>
          <Search className="w-4 h-4" />تحديث
        </button>
      </div>
    </div>
  );

  const reportContent = (
    <>
      {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <AseelReportTable<InvoiceProfitRow>
        filterBar={filterBar}
        columns={columns}
        rows={rows}
        totals={rows.length > 0 ? reportTotals : undefined}
        exportable={true}
        loading={loading}
        emptyHint="لا فواتير مرحّلة في المدى المحدد"
        getRowKey={(r) => r.invoice}
      />
    </>
  );

  const shellActions: AseelToolbarAction[] = [
    { key: "run", label: "تحديث", icon: <Search className="w-4 h-4" />, onClick: fetchData },
  ];

  const tabs: AseelTab[] = [
    { key: "profits", label: "أرباح الفواتير", content: reportContent },
  ];

  return (
    <div>
      <AseelDocumentShell
        title="أرباح الفواتير"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          data ? (
            <span className="aseel-status-item">
              عدد الفواتير: {rows.length} · إجمالي الربح: {fmt(shown.profit)}
            </span>
          ) : undefined
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
