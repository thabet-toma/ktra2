import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Search, RotateCcw, Pencil, Ban } from "lucide-react";
import {
  cancelSalesOrder,
  getReservedStock,
  type ReservedStockRow,
} from "../../services/salesApi";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney, formatNumber } from "../../utils/formatNumber";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
import { openInNewTab } from "../../utils/openInNewTab";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { clientLogger } from "../../services/logger";
import { AseelDocumentShell, AseelReportTable } from "../aseel";
import type { AseelToolbarAction, ReportColumn } from "../aseel";

/**
 * T-RESERVEGUARD: «تقرير المحجوزات» — ما هو محجوز الآن ولمن وحتى متى.
 *
 * الصفوف من نفس مصدر الحارس الذي يرفض ترحيل فاتورة تسحب كمية محجوزة لزبون آخر،
 * فما يُقرأ هنا هو بعينه ما يُمنَع هناك. الحجز المنتهي/الملغى لا يظهر لأنه لم
 * يعد يمنع شيئاً.
 *
 * T-RESERVEOPS: التقرير كان قراءةً فقط — يرى المستخدم الحجز الذي يمنع بيعه ولا
 * يملك من الشاشة نفسها أن يفكّه، ولا أن يحصر نافذته الزمنية. صار فيه:
 *   • فلترة «الحجز حتى» (من/إلى) + الزبون + بحث نصّي،
 *   • «تعديل» يفتح الطلبية نفسها (`?open=`) لا قائمةً يُبحث فيها عنها،
 *   • «إلغاء الحجز» = إلغاء الطلبية (نفس خدمة الخادم) — الحجز ليس كياناً مستقلاً
 *     يُفكّ وحده، فالتأكيد يقول ذلك صراحةً.
 */

const addDays = (days: number): string => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

type Customer = { id: number; name: string };

export const ReservedStockReportPage: React.FC = () => {
  const confirm = useConfirm();
  const toast = useToast();

  const [rows, setRows] = useState<ReservedStockRow[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [customerId, setCustomerId] = useState<number | "">("");
  const [loading, setLoading] = useState(false);
  const [busyOrderId, setBusyOrderId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setRows(await getReservedStock({
        customer: customerId === "" ? undefined : Number(customerId),
        from: dateFrom || undefined,
        to: dateTo || undefined,
      }));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل تحميل التقرير");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [customerId, dateFrom, dateTo]);

  useEffect(() => { void fetchData(); }, [fetchData]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        // T-PARTYPURE: الحجز حجز زبون — القائمة زبائن فقط.
        const list = await accountingApi.getPartners("Customer") as Customer[];
        if (alive) setCustomers(list || []);
      } catch { /* الفلتر يبقى «كل الزبائن» — التقرير نفسه لا يتوقف */ }
    })();
    return () => { alive = false; };
  }, []);

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

  /** مؤشّرات تُقرأ قبل الجدول: ما حجمه، ولمن، وما الذي يوشك أن ينتهي أو يتجاوز الرصيد. */
  const kpis = useMemo(() => ({
    orders: new Set(shown.map((r) => r.order_id)).size,
    customers: new Set(shown.map((r) => r.customer_id)).size,
    products: new Set(shown.map((r) => r.product_id)).size,
    endingSoon: shown.filter((r) => r.days_left != null && r.days_left <= 2).length,
    negative: new Set(
      shown.filter((r) => Number(r.available_quantity) < 0).map((r) => r.product_id),
    ).size,
  }), [shown]);

  const resetFilters = () => {
    setSearch("");
    setDateFrom("");
    setDateTo("");
    setCustomerId("");
  };

  const openOrder = (row: ReservedStockRow) => {
    clientLogger.info("reserved_stock.open_order", { order: row.order_id });
    openInNewTab(`/sales/orders?open=${row.order_id}`);
  };

  const releaseReservation = async (row: ReservedStockRow) => {
    const ok = await confirm({
      title: "إلغاء الحجز",
      message: `سيُلغى المستند ${row.order_number} (${row.customer_name}) بالكامل — بكل بنوده — ويُفرَج عن الكمية المحجوزة فوراً. الطلبية تبقى في السجل «ملغاة» ولا تُحذف. متابعة؟`,
      confirmText: "إلغاء الحجز والطلبية",
      cancelText: "تراجع",
      danger: true,
    });
    if (!ok) return;
    setBusyOrderId(row.order_id);
    try {
      await cancelSalesOrder(row.order_id, "إلغاء الحجز من تقرير المحجوزات");
      clientLogger.info("reserved_stock.cancel_order", { order: row.order_id });
      toast(`تم إلغاء الطلبية ${row.order_number} والإفراج عن الحجز`, "success");
      await fetchData();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر إلغاء الحجز");
    } finally {
      setBusyOrderId(null);
    }
  };

  const columns: ReportColumn<ReservedStockRow>[] = [
    { key: "order_number", header: "رقم الطلبية", width: "120px", render: (r) => <b>{r.order_number}</b> },
    { key: "order_date", header: "تاريخ الطلبية", width: "110px",
      render: (r) => formatDateLocalized(r.order_date) || "—" },
    { key: "customer_name", header: "الزبون", render: (r) => r.customer_name },
    { key: "product_name", header: "الصنف", render: (r) => r.product_name },
    { key: "product_sku", header: "الرمز", width: "100px", render: (r) => r.product_sku || "—" },
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
      key: "reserved_until", header: "الحجز حتى", width: "110px",
      render: (r) => formatDateLocalized(r.reserved_until) || "—",
    },
    {
      key: "days_left", header: "المتبقي", width: "90px",
      render: (r) => (
        r.days_left == null ? "—"
          : <span style={r.days_left <= 2
            ? { color: "var(--aseel-warn, #b06800)", fontWeight: 600 }
            : undefined}>
            {formatNumber(r.days_left)} يوم
          </span>
      ),
    },
    {
      key: "actions", header: "إجراءات", width: "170px", align: "center",
      render: (r) => (
        <div className="flex items-center justify-center gap-2 text-xs">
          <button
            type="button"
            className="aseel-text-accent inline-flex items-center gap-1 hover:underline"
            title={`فتح الطلبية ${r.order_number} للتعديل`}
            onClick={() => openOrder(r)}
          ><Pencil className="h-3 w-3" />تعديل</button>
          <button
            type="button"
            className="inline-flex items-center gap-1 text-amber-600 hover:underline disabled:opacity-50"
            title="إلغاء الطلبية والإفراج عن الكمية المحجوزة"
            disabled={busyOrderId === r.order_id}
            onClick={() => void releaseReservation(r)}
          ><Ban className="h-3 w-3" />
            {busyOrderId === r.order_id ? "جارٍ…" : "إلغاء الحجز"}</button>
        </div>
      ),
    },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="aseel-field" style={{ flex: "1", minWidth: "180px" }}>
        <label className="aseel-field-label">الزبون / الصنف / رقم الطلبية</label>
        <input
          type="text"
          className="aseel-input"
          placeholder="بحث…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <div className="aseel-field" style={{ minWidth: "170px" }}>
        <label className="aseel-field-label">الزبون</label>
        <select
          className="aseel-input"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">كل الزبائن</option>
          {customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div className="aseel-field" style={{ minWidth: "140px" }}>
        <label className="aseel-field-label">الحجز حتى — من</label>
        <input type="date" className="aseel-input" value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)} />
      </div>
      <div className="aseel-field" style={{ minWidth: "140px" }}>
        <label className="aseel-field-label">الحجز حتى — إلى</label>
        <input type="date" className="aseel-input" value={dateTo}
          onChange={(e) => setDateTo(e.target.value)} />
      </div>
      {/* نوافذ جاهزة: «ما ينتهي هذا الأسبوع» سؤال يومي لا يستحق كتابة تاريخين. */}
      <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
        <button type="button" className="aseel-btn"
          onClick={() => { setDateFrom(todayIso()); setDateTo(addDays(2)); }}
          title="الحجوزات التي تنتهي خلال يومين">ينتهي خلال يومين</button>
        <button type="button" className="aseel-btn"
          onClick={() => { setDateFrom(todayIso()); setDateTo(addDays(7)); }}
          title="الحجوزات التي تنتهي خلال أسبوع">هذا الأسبوع</button>
        <button type="button" className="aseel-toolbtn" onClick={resetFilters} title="مسح الفلاتر">
          <RotateCcw className="w-4 h-4" />مسح
        </button>
        <button type="button" className="aseel-toolbtn" onClick={() => void fetchData()}>
          <Search className="w-4 h-4" />تحديث
        </button>
      </div>
    </div>
  );

  const kpiCard = (label: string, value: string, tone?: "warn" | "danger") => (
    <div
      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
      style={{ minWidth: "120px" }}
    >
      <div className="text-[11px] text-[var(--color-text-muted)]">{label}</div>
      <div
        className="text-lg font-bold"
        style={{
          color: tone === "danger" ? "var(--aseel-danger, #c00)"
            : tone === "warn" ? "var(--aseel-warn, #b06800)" : undefined,
        }}
      >{value}</div>
    </div>
  );

  const kpiBand = (
    <div className="flex flex-wrap gap-2 p-2">
      {kpiCard("عدد الحجوزات", formatNumber(shown.length))}
      {kpiCard("الطلبيات", formatNumber(kpis.orders))}
      {kpiCard("الزبائن", formatNumber(kpis.customers))}
      {kpiCard("الأصناف", formatNumber(kpis.products))}
      {kpiCard("الكمية المحجوزة", formatNumber(totals.quantity))}
      {kpiCard("قيمة المحجوز", formatMoney(totals.line_total))}
      {kpiCard("ينتهي خلال يومين", formatNumber(kpis.endingSoon), kpis.endingSoon > 0 ? "warn" : undefined)}
      {kpiCard("أصناف بمتاح سالب", formatNumber(kpis.negative), kpis.negative > 0 ? "danger" : undefined)}
    </div>
  );

  const shellActions: AseelToolbarAction[] = [
    { key: "run", label: "تحديث", icon: <Search className="w-4 h-4" />, onClick: () => void fetchData() },
    { key: "reset", label: "مسح الفلاتر", icon: <RotateCcw className="w-4 h-4" />, onClick: resetFilters },
  ];

  return (
    <AseelDocumentShell
      title="تقرير المحجوزات"
      state={
        dateFrom || dateTo
          ? `الحجز حتى ${dateFrom ? formatDateLocalized(dateFrom) : "…"} — ${dateTo ? formatDateLocalized(dateTo) : "…"}`
          : "كل الحجوزات السارية"
      }
      actions={shellActions}
      header={kpiBand}
      status={
        <span className="aseel-status-item">
          عدد الحجوزات: {shown.length} · إجمالي القيمة: {formatMoney(totals.line_total)}
          {" · "}إلغاء الحجز = إلغاء الطلبية بكل بنودها
        </span>
      }
    >
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
        emptyHint="لا حجوزات سارية في هذا النطاق — الطلبيات المؤكَّدة وحدها تحجز، والحجز المنتهي يُفرَج عنه تلقائياً."
        getRowKey={(r) => `${r.order_id}-${r.product_id}`}
      />
    </AseelDocumentShell>
  );
};

export default ReservedStockReportPage;
