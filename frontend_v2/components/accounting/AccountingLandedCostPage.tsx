import React, { useState, useEffect, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { LandedCostReport, LandedCostShipment } from "../../types/accounting";
import {
  AseelDocumentShell,
  AseelReportTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, ReportColumn } from "../aseel";
import { Search, ChevronRight, ChevronDown, Package, AlertCircle } from "lucide-react";
import { Spinner } from "../ui";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";

export const AccountingLandedCostPage: React.FC = () => {
  const today = new Date();
  const [start, setStart] = useState(() => {
    const d = new Date(today.getFullYear(), today.getMonth() - 3, 1);
    return d.toISOString().split("T")[0];
  });
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [data, setData] = useState<LandedCostReport | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [detail, setDetail] = useState<LandedCostShipment | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const resp = await accountingApi.getLandedCostReport({
        start_date: start,
        end_date: end,
      });
      setData(resp as LandedCostReport);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end]);

  const openDetail = useCallback(async (shipmentId: number) => {
    if (expanded === shipmentId) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(shipmentId);
    setDetail(null);
    try {
      const resp = (await accountingApi.getLandedCostReport({
        shipment_id: String(shipmentId),
      })) as LandedCostReport;
      if (resp.shipments && resp.shipments.length > 0) {
        setDetail(resp.shipments[0]);
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  }, [expanded]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  // مبالغ مالية — يحذف الأصفار العشرية غير الدالّة عبر المُنسّق الموحّد.
  const fmt = (n: number | null | undefined) => formatMoney(n, "0");

  const shipments = data?.shipments || [];

  // For AseelReportTable we need flat rows
  const columns: ReportColumn<LandedCostShipment>[] = [
    {
      key: "expand", header: "",
      render: (r) => (
        <button type="button" style={{ background: "none", border: "none", cursor: "pointer" }}
          onClick={() => openDetail(r.shipment_id)}>
          {expanded === r.shipment_id
            ? <ChevronDown className="w-4 h-4" />
            : <ChevronRight className="w-4 h-4" />}
        </button>
      ),
    },
    { key: "shipment_number", header: "الشحنة", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.shipment_number}</span> },
    { key: "arrival_date", header: "الوصول", render: (r) => formatDateLocalized(r.arrival_date) || "—" },
    { key: "status", header: "الحالة", render: (r) => r.status },
    { key: "total_merchandise", header: "البضاعة", numeric: true, render: (r) => fmt(r.total_merchandise) },
    { key: "total_shipping_cost_usd", header: "شحن دولي (USD)", numeric: true, render: (r) => fmt(r.total_shipping_cost_usd) },
    { key: "clearance_total", header: "تخليص", numeric: true, render: (r) => fmt(r.clearance_total) },
    { key: "capitalized_fees_total", header: "رسوم مرسملة", numeric: true, render: (r) => fmt(r.capitalized_fees_total) },
    {
      key: "grand_landed_cost_approx", header: "إجمالي Landed", numeric: true,
      render: (r) => <strong>{fmt(r.grand_landed_cost_approx)}</strong>,
    },
  ];

  const totals = shipments.length > 0 ? {
    total_merchandise: fmt(shipments.reduce((s, sh) => s + sh.total_merchandise, 0)),
    total_shipping_cost_usd: fmt(shipments.reduce((s, sh) => s + sh.total_shipping_cost_usd, 0)),
    clearance_total: fmt(shipments.reduce((s, sh) => s + sh.clearance_total, 0)),
    capitalized_fees_total: fmt(shipments.reduce((s, sh) => s + sh.capitalized_fees_total, 0)),
    grand_landed_cost_approx: fmt(shipments.reduce((s, sh) => s + sh.grand_landed_cost_approx, 0)),
  } : undefined;

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="aseel-field">
        <label className="aseel-field-label">وصول من</label>
        <input type="date" className="aseel-input" value={start} onChange={(e) => setStart(e.target.value)} />
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">وصول إلى</label>
        <input type="date" className="aseel-input" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <button type="button" className="aseel-toolbtn" onClick={fetchReport} style={{ marginTop: "18px" }}>
        <Search className="w-4 h-4" />تحديث
      </button>
    </div>
  );

  // Custom table because we need expand rows — we'll render a custom section after AseelReportTable
  const reportContent = (
    <>
      {err && (
        <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px", display: "flex", gap: "8px", alignItems: "center" }}>
          <AlertCircle className="w-4 h-4" />{err}
        </div>
      )}
      <AseelReportTable<LandedCostShipment>
        filterBar={filterBar}
        columns={columns}
        rows={shipments}
        totals={totals}
        exportable={true}
        loading={loading}
        emptyHint="لا توجد شحنات في الفترة"
        getRowKey={(r) => r.shipment_id}
      />
      {/* Expand detail panel */}
      {expanded != null && (
        <div style={{ marginTop: "8px", border: "1px solid var(--aseel-border)", borderRadius: "var(--aseel-radius)", padding: "12px" }}>
          {detail ? (
            <ShipmentDetail sh={detail} fmt={fmt} />
          ) : (
            <div style={{ padding: "16px", textAlign: "center" }}><Spinner size="sm" /></div>
          )}
        </div>
      )}
    </>
  );

  const shellActions: AseelToolbarAction[] = [
    { key: "run", label: "تحديث", icon: <Search className="w-4 h-4" />, onClick: fetchReport },
  ];

  const tabs: AseelTab[] = [
    { key: "landed", label: "التكلفة المستوردة", content: reportContent },
  ];

  return (
    <div>
      <AseelDocumentShell
        title="تقرير التكلفة المستوردة"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          data ? (
            <span className="aseel-status-item">{shipments.length} شحنة</span>
          ) : undefined
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};

const ShipmentDetail: React.FC<{
  sh: LandedCostShipment;
  fmt: (n: number | null | undefined) => string;
}> = ({ sh, fmt }) => (
  <div className="space-y-4">
    {sh.deals.map((d) => (
      <div key={d.deal_id}
        style={{ background: "var(--aseel-surface)", border: "1px solid var(--aseel-border)", borderRadius: "var(--aseel-radius)", padding: "12px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "12px", marginBottom: "8px" }}>
          <Package className="w-4 h-4" style={{ color: "var(--color-primary,#3b82f6)" }} />
          <span style={{ fontWeight: "600" }}>صفقة {d.ref_number || `#${d.deal_id}`}</span>
          <span style={{ fontSize: "0.8rem", color: "var(--aseel-ink-soft)" }}>{d.partner_name} — {d.currency}</span>
          <span style={{ fontSize: "0.8rem", marginInlineStart: "auto" }}>
            بضاعة: {fmt(d.merchandise_total)} | شحن مُخصَّص: {fmt(d.allocated_shipping_cost_usd)} USD
          </span>
        </div>

        {d.purchase_invoice ? (
          <div style={{ marginTop: "8px" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", fontSize: "0.75rem", marginBottom: "8px" }}>
              <span style={{ padding: "2px 8px", background: "#dcfce715", borderRadius: "10px", color: "#16a34a" }}>
                فاتورة: {d.purchase_invoice.invoice_number || "—"}
              </span>
              {d.purchase_invoice.is_posted && (
                <span style={{ padding: "2px 8px", background: "#dbeafe15", borderRadius: "10px", color: "#2563eb" }}>مرحّلة</span>
              )}
              <span style={{ padding: "2px 8px", background: "#fef9c315", borderRadius: "10px", color: "#ca8a04" }}>
                رسوم مرسملة: {fmt(d.purchase_invoice.capitalized_fees_total)}
              </span>
            </div>
            {d.purchase_invoice.items.length > 0 && (
              <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--aseel-surface-2,#f8f9fa)" }}>
                    <th style={{ padding: "4px 8px", textAlign: "right" }}>الصنف</th>
                    <th style={{ padding: "4px 8px", textAlign: "right" }}>الكمية</th>
                    <th style={{ padding: "4px 8px", textAlign: "right" }}>سعر الصفقة</th>
                    <th style={{ padding: "4px 8px", textAlign: "right" }}>Landed/وحدة (ILS)</th>
                    <th style={{ padding: "4px 8px", textAlign: "right" }}>Landed إجمالي (ILS)</th>
                  </tr>
                </thead>
                <tbody>
                  {d.purchase_invoice.items.map((it) => (
                    <tr key={it.id} style={{ borderTop: "1px solid var(--aseel-border)" }}>
                      <td style={{ padding: "4px 8px" }}>{it.name}</td>
                      <td style={{ padding: "4px 8px", textAlign: "right" }}>{formatQuantity(it.quantity)}</td>
                      <td style={{ padding: "4px 8px", textAlign: "right" }}>{fmt(it.unit_price)}</td>
                      <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: "600" }}>
                        {it.landed_unit_price_ils != null ? fmt(it.landed_unit_price_ils) : "—"}
                      </td>
                      <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: "600" }}>
                        {it.landed_line_total_ils != null ? fmt(it.landed_line_total_ils) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ) : (
          <div style={{ fontSize: "0.8rem", color: "#ca8a04", background: "#fef9c315", padding: "8px", borderRadius: "6px", marginTop: "4px" }}>
            لا توجد فاتورة شراء مرتبطة — استورد من التخليص لحساب Landed Cost.
          </div>
        )}
      </div>
    ))}

    {sh.clearance && (
      <div style={{ background: "var(--aseel-surface)", border: "1px solid var(--aseel-border)", borderRadius: "var(--aseel-radius)", padding: "12px" }}>
        <div style={{ fontWeight: "600", marginBottom: "8px" }}>
          التخليص الجمركي #{sh.clearance.id}
          {sh.clearance.declaration_number && ` — بيان ${sh.clearance.declaration_number}`}
        </div>
        <div style={{ fontSize: "0.8rem", color: "var(--aseel-ink-soft)", marginBottom: "8px" }}>
          {sh.clearance.broker_name} · {sh.clearance.status} · دفعات مرحّلة: {fmt(sh.clearance.posted_payments_total)}
        </div>
        {sh.clearance.cost_lines.length > 0 && (
          <table style={{ width: "100%", fontSize: "0.8rem", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--aseel-surface-2,#f8f9fa)" }}>
                <th style={{ padding: "4px 8px", textAlign: "right" }}>البند</th>
                <th style={{ padding: "4px 8px", textAlign: "right" }}>المبلغ</th>
              </tr>
            </thead>
            <tbody>
              {sh.clearance.cost_lines.map((ln, i) => (
                <tr key={i} style={{ borderTop: "1px solid var(--aseel-border)" }}>
                  <td style={{ padding: "4px 8px" }}>{ln.label}</td>
                  <td style={{ padding: "4px 8px", textAlign: "right" }}>{fmt(ln.amount)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: "600", borderTop: "1px solid var(--aseel-border)" }}>
                <td style={{ padding: "4px 8px" }}>الإجمالي</td>
                <td style={{ padding: "4px 8px", textAlign: "right" }}>{fmt(sh.clearance.cost_lines_total)}</td>
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    )}
  </div>
);
