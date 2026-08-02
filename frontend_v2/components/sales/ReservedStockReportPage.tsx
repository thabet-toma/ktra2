import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { getReservedStock, type ReservedStockRow } from "../../services/salesApi";
import { formatMoney, formatNumber } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { AseelDocumentShell, AseelReportTable } from "../aseel";
import type { AseelToolbarAction, AseelTab, ReportColumn } from "../aseel";

/**
 * T-RESERVEGUARD: «تقرير المحجوزات» — ما هو محجوز الآن ولمن وحتى متى.
 *
 * الصفوف من نفس مصدر الحارس الذي يرفض ترحيل فاتورة تسحب كمية محجوزة لزبون آخر،
 * فما يُقرأ هنا هو بعينه ما يُمنَع هناك. الحجز المنتهي/الملغى لا يظهر لأنه لم
 * يعد يمنع شيئاً.
 */
export const ReservedStockReportPage: React.FC = () => {
  const [rows, setRows] = useState<ReservedStockRow[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setRows(await getReservedStock());
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل تحميل التقرير");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchData(); }, [fetchData]);

  const shown = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((row) => (
      row.customer_name.toLowerCase().includes(term)
      || row.product_name.toLowerCase().includes(term)
      || row.product_sku.toLowerCase().includes(term)
      || row.order_number.toLowerCase().includes(term)
    ));
  }, [rows, search]);

  const totals = useMemo(() => shown.reduce(
    (acc, row) => {
      acc.quantity += Number(row.quantity) || 0;
      acc.line_total += Number(row.line_total) || 0;
      return acc;
    },
    { quantity: 0, line_total: 0 },
  ), [shown]);

  const columns: ReportColumn<ReservedStockRow>[] = [
    { key: "order_number", header: "رقم الطلبية", render: (r) => r.order_number },
    { key: "customer_name", header: "الزبون", render: (r) => r.customer_name },
    { key: "product_name", header: "الصنف", render: (r) => r.product_name },
    { key: "product_sku", header: "الرمز", render: (r) => r.product_sku || "—" },
    { key: "quantity", header: "المحجوز", numeric: true, render: (r) => formatNumber(r.quantity) },
    {
      key: "quantity_on_hand", header: "الرصيد", numeric: true,
      render: (r) => formatNumber(r.quantity_on_hand),
    },
    {
      key: "available_quantity", header: "المتاح للبيع", numeric: true,
      // المتاح السالب = حجوزات تتجاوز الرصيد — يجب أن يُرى لا أن يُبتلع.
      render: (r) => (
        <span style={Number(r.available_quantity) < 0
          ? { color: "var(--aseel-danger, #c00)", fontWeight: 700 }
          : undefined}>
          {formatNumber(r.available_quantity)}
        </span>
      ),
    },
    { key: "line_total", header: "قيمة المحجوز", numeric: true, render: (r) => formatMoney(r.line_total) },
    {
      key: "reserved_until", header: "الحجز حتى",
      render: (r) => formatDateLocalized(r.reserved_until) || "—",
    },
    {
      key: "days_left", header: "المتبقي",
      render: (r) => (
        r.days_left == null ? "—"
          : <span style={r.days_left <= 2
            ? { color: "var(--aseel-warn, #b06800)", fontWeight: 600 }
            : undefined}>
            {formatNumber(r.days_left)} يوم
          </span>
      ),
    },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="aseel-field" style={{ flex: "1", minWidth: "200px" }}>
        <label className="aseel-field-label">الزبون / الصنف / رقم الطلبية</label>
        <input
          type="text"
          className="aseel-input"
          placeholder="بحث…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <button type="button" className="aseel-toolbtn" onClick={() => void fetchData()}>
        <Search className="w-4 h-4" />تحديث
      </button>
    </div>
  );

  const reportContent = (
    <>
      {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <AseelReportTable<ReservedStockRow>
        filterBar={filterBar}
        columns={columns}
        rows={shown}
        totals={shown.length > 0 ? {
          quantity: formatNumber(totals.quantity),
          line_total: formatMoney(totals.line_total),
        } : undefined}
        exportable
        loading={loading}
        emptyHint="لا حجوزات سارية — الطلبيات المؤكَّدة وحدها تحجز، والحجز المنتهي يُفرَج عنه تلقائياً."
        getRowKey={(r) => `${r.order_id}-${r.product_id}`}
      />
    </>
  );

  const shellActions: AseelToolbarAction[] = [
    { key: "run", label: "تحديث", icon: <Search className="w-4 h-4" />, onClick: () => void fetchData() },
  ];

  const tabs: AseelTab[] = [
    { key: "reserved", label: "المحجوزات", content: reportContent },
  ];

  return (
    <AseelDocumentShell
      title="تقرير المحجوزات"
      actions={shellActions}
      header={<></>}
      tabs={tabs}
      status={
        <span className="aseel-status-item">
          عدد الحجوزات: {shown.length} · إجمالي القيمة: {formatMoney(totals.line_total)}
        </span>
      }
    >
      <></>
    </AseelDocumentShell>
  );
};

export default ReservedStockReportPage;
