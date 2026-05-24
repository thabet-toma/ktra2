import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Save } from "lucide-react";
import { apiGetObject, apiPatchObject, apiPostObject } from "@/services/restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { listClearances, ClearanceRow, listClearancePayments, ClearancePaymentRow, updateClearance, createClearance } from "@/services/clearanceApi";
import { listLocalShipments, LocalShipmentRow, createLocalShipment, updateLocalShipment, postLocalShipment } from "@/services/localShippingApi";
import { AseelDocumentShell, useRecordNavigation, AseelToolbarAction, AseelTab } from "@/components/aseel";
import { CompactTimeline } from "./CompactTimeline";

const tid = () => resolveTenantId();
const fmt = (v: number | string | null | undefined) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
};

const fld = (label: string, node: React.ReactNode) => (
  <label className="aseel-field">
    <span className="aseel-field-label">{label}</span>
    {node}
  </label>
);

interface ImportDocumentScreenProps {
  shipmentId: string | null;
  onClose?: () => void;
}

/** Raw shipment shape from the API (subset of LogisticsShipment) */
interface ShipmentApiRow {
  id: number;
  shipment_number?: string;
  shipment_name?: string;
  shipment_date?: string;
  transaction_time?: string;
  second_date?: string;
  shipment_type?: string;
  shipping_agent?: number | null;
  agent_name?: string;
  shipping_type?: string;
  shipping_company?: string;
  bill_of_lading?: string;
  container_number?: string;
  departure_date?: string;
  arrival_date?: string;
  ship_name?: string;
  flight_number?: string;
  from_term?: string;
  to_term?: string;
  agent_shipment_number?: string;
  invoice_number?: string;
  total_shipping_cost_usd?: number;
  total_volume?: number;
  total_weight_kg?: number;
  subtotal?: number;
  vat_total?: number;
  grand_total?: number;
  remaining_amount?: number;
  vat_statement?: number | null;
  transit_journal?: number | null;
  editable?: boolean;
  shipping_workflow_status?: string;
  notes?: string;
  deals_count?: number;
  deals_preview?: string | null;
}

const ROUTE_LABELS: Record<string, string> = {
  agent_warehouse: "مستودع الوكيل",
  china_customs_clearance: "جمارك الصين",
  on_board: "الشحن",
  at_sea: "البحر",
  arrived_port: "الميناء",
  arrived_airport: "المطار",
  departed: "غادر",
  israel_customs_clearance: "جمارك إسرائيل",
  released: "مفرج",
  delivered_local: "محلي",
};

const STATUS_ORDER_SEA = ["agent_warehouse","china_customs_clearance","on_board","at_sea","arrived_port","israel_customs_clearance","released","delivered_local"];
const STATUS_ORDER_AIR = ["agent_warehouse","china_customs_clearance","departed","arrived_airport","israel_customs_clearance","released","delivered_local"];

function buildTimelineSteps(sw: string | undefined | null, shipType: string | undefined): { key: string; label: string; status: "done" | "current" | "pending" }[] {
  const order = shipType === "air" ? STATUS_ORDER_AIR : STATUS_ORDER_SEA;
  const idx = order.indexOf(sw || "");
  return order.map((k, i) => ({
    key: k,
    label: ROUTE_LABELS[k] || k,
    status: (i < idx ? "done" : i === idx ? "current" : "pending") as "done" | "current" | "pending",
  }));
}

export function ImportDocumentScreen({ shipmentId, onClose }: ImportDocumentScreenProps) {
  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "deals";
  const [shipment, setShipment] = useState<ShipmentApiRow | null>(null);
  const [shipmentForm, setShipmentForm] = useState<ShipmentApiRow | null>(null);
  const [clearance, setClearance] = useState<ClearanceRow | null>(null);
  const [clearanceForm, setClearanceForm] = useState<ClearanceRow | null>(null);
  const [localShipments, setLocalShipments] = useState<LocalShipmentRow[]>([]);
  const [localForm, setLocalForm] = useState<LocalShipmentRow | null>(null);
  const [clearancePayments, setClearancePayments] = useState<ClearancePaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(initialTab);

  const loadAll = useCallback(async (id: number | string) => {
    setLoading(true); setError(null);
    try {
      const s = await apiGetObject<ShipmentApiRow>(`logistics/shipments/${id}/`, { tenantId: tid() });
      setShipment(s);
      setShipmentForm({ ...s });
      const cls = await listClearances();
      const matched = cls.find((c) => c.shipment === s.id) || null;
      setClearance(matched);
      setClearanceForm(matched ? { ...matched } : null);
      const locs = await listLocalShipments();
      setLocalShipments(locs.filter((l) => l.shipment === s.id));
      if (matched) {
        const pays = await listClearancePayments(matched.id);
        setClearancePayments(pays);
      } else {
        setClearancePayments([]);
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!shipmentId || shipmentId === "new") {
      setLoading(false);
      if (shipmentId === "new") {
        setShipment(null);
        setShipmentForm({ id: 0, shipment_number: "", shipment_date: new Date().toISOString().slice(0, 10), editable: true } as ShipmentApiRow);
      } else {
        setShipment(null);
        setShipmentForm(null);
      }
      setClearance(null);
      setClearanceForm(null);
      setLocalShipments([]);
      setLocalForm(null);
      setClearancePayments([]);
      return;
    }
    loadAll(shipmentId);
  }, [shipmentId, loadAll]);

  // Empty nav (single-record view) — shell expects a nav prop but we don't browse here yet.
  const nav = useRecordNavigation({ items: [] as ShipmentApiRow[], getId: () => 0, currentId: null, onSelect: () => {} });
  const timelineSteps = useMemo(() => buildTimelineSteps(shipment?.shipping_workflow_status, shipment?.shipping_type), [shipment]);

  if (loading) return <div className="p-8 text-center aseel-text-soft">جاري تحميل الإرسالية…</div>;
  if (error) return <div className="p-8 text-center" style={{ color: "var(--aseel-danger, #c0392b)" }}>{error}</div>;
  if (!shipmentId) {
    return (
      <div className="p-8 text-center aseel-text-soft">
        <p>لم يتم اختيار إرسالية.</p>
        <p style={{ marginTop: 8 }}>افتح صفحة «الشحنات» واختر سجلاً لفتحه هنا.</p>
      </div>
    );
  }
  const s = shipment || shipmentForm;
  if (!s) return <div className="p-8 text-center aseel-text-soft">لم يتم العثور على الإرسالية</div>;
  const paidShipping = clearancePayments
    .filter((p) => p.payment_purpose === "shipping" && p.is_posted)
    .reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const paidClearance = clearancePayments
    .filter((p) => p.payment_purpose !== "shipping" && p.is_posted)
    .reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const shipmentPaid =
    s.grand_total != null && s.remaining_amount != null
      ? Number(s.grand_total) - Number(s.remaining_amount)
      : null;

  const totals = (
    <>
      <div className="aseel-total-row"><span>تكلفة الشحن</span><span className="aseel-total-value">{fmt(s.total_shipping_cost_usd)}</span></div>
      <div className="aseel-total-row"><span>المجموع بدون ضريبة</span><span className="aseel-total-value">{fmt(s.subtotal)}</span></div>
      <div className="aseel-total-row"><span>مجموع الضريبة</span><span className="aseel-total-value">{fmt(s.vat_total)}</span></div>
      <div className="aseel-total-row aseel-total-row--grand"><span>الإجمالي</span><span className="aseel-total-value">{fmt(s.grand_total)}</span></div>
      <div className="aseel-total-row"><span>المدفوع</span><span className="aseel-total-value">{shipmentPaid != null ? fmt(shipmentPaid) : "—"}</span></div>
      <div className="aseel-total-row"><span>المتبقي</span><span className="aseel-total-value">{fmt(s.remaining_amount)}</span></div>
      <hr style={{ margin: "4px 0", border: "none", borderTop: "1px solid var(--aseel-border, #ddd)" }} />
      <div className="aseel-total-row"><span>{clearance ? `تخليص #${clearance.id}` : "تخليص"}</span><span className="aseel-total-value">{clearance ? fmt(clearance.grand_total) : "—"}</span></div>
      {clearance && <div className="aseel-total-row"><span>مدفوع تخليص</span><span className="aseel-total-value">{fmt(paidClearance)}</span></div>}
      {clearance && <div className="aseel-total-row"><span>مدفوع شحن</span><span className="aseel-total-value">{fmt(paidShipping)}</span></div>}
      {localShipments.map((ls) => (
        <div className="aseel-total-row" key={ls.id}><span>نقل محلي #{ls.shipment_number}</span><span className="aseel-total-value">{fmt(ls.amount)}</span></div>
      ))}
    </>
  );

  const statusBar = (
    <>
      <span className="aseel-status-item">الحالة <b>{s.shipping_workflow_status || "—"}</b></span>
      {s.transit_journal && <span className="aseel-status-item">رقم القيد <b>#{s.transit_journal}</b></span>}
      <span className="aseel-status-item">رقم الإرسالية <b>{s.shipment_number || "—"}</b></span>
      <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
    </>
  );

  const setSF = (patch: Partial<ShipmentApiRow>) => setShipmentForm(prev => prev ? { ...prev, ...patch } : prev);
  const sfOn = (key: keyof ShipmentApiRow) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setSF({ [key]: e.target.value });

  const headerBand = shipmentForm ? (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "2px 8px", padding: "4px 0" }}>
      {fld("رقم الإرسالية", <input className="aseel-input" readOnly value={shipmentForm.shipment_number || `#${shipmentForm.id}`} />)}
      {fld("تاريخ", <input className="aseel-input" type="date" value={shipmentForm.shipment_date ? String(shipmentForm.shipment_date).slice(0, 10) : ""} onChange={sfOn("shipment_date")} />)}
      {fld("الساعة", <input className="aseel-input" type="time" value={shipmentForm.transaction_time ? String(shipmentForm.transaction_time).slice(0, 5) : ""} onChange={sfOn("transaction_time")} />)}
      {fld("تاريخ ثاني", <input className="aseel-input" type="date" value={shipmentForm.second_date ? String(shipmentForm.second_date).slice(0, 10) : ""} onChange={sfOn("second_date")} />)}
      {fld("الوكيل", <input className="aseel-input" readOnly value={shipmentForm.shipping_agent ? `#${shipmentForm.shipping_agent}` : "—"} />)}
      {fld("اسم الوكيل", <input className="aseel-input" readOnly value={shipmentForm.agent_name || "—"} />)}
      {fld("نوع الإرسالية", <select className="aseel-input" value={shipmentForm.shipment_type || "invoice"} onChange={sfOn("shipment_type")}>
        <option value="invoice">فاتورة</option>
        <option value="transport">نقل</option>
      </select>)}
      {fld("نوع الشحن", <select className="aseel-input" value={shipmentForm.shipping_type || ""} onChange={sfOn("shipping_type")}>
        <option value="">—</option>
        <option value="sea">بحري</option>
        <option value="air">جوي</option>
        <option value="land">بري</option>
      </select>)}
      {fld("رقم البوليصة", <input className="aseel-input" value={shipmentForm.bill_of_lading || ""} onChange={sfOn("bill_of_lading")} />)}
      {fld("رقم الحاوية", <input className="aseel-input" value={shipmentForm.container_number || ""} onChange={sfOn("container_number")} />)}
      {fld("المغادرة", <input className="aseel-input" type="date" value={shipmentForm.departure_date ? String(shipmentForm.departure_date).slice(0, 10) : ""} onChange={sfOn("departure_date")} />)}
      {fld("الوصول", <input className="aseel-input" type="date" value={shipmentForm.arrival_date ? String(shipmentForm.arrival_date).slice(0, 10) : ""} onChange={sfOn("arrival_date")} />)}
      {fld("السفينة / الرحلة", <input className="aseel-input" value={shipmentForm.ship_name || shipmentForm.flight_number || ""} onChange={(e) => setSF({ ship_name: e.target.value, flight_number: e.target.value })} />)}
      {fld("رقم الحركة", <input className="aseel-input" value={shipmentForm.agent_shipment_number || ""} onChange={sfOn("agent_shipment_number")} />)}
      {fld("رقم الفاتورة", <input className="aseel-input" readOnly value={shipmentForm.invoice_number || "—"} />)}
      {fld("الحجم / الوزن", <input className="aseel-input" readOnly value={`${fmt(shipmentForm.total_volume)} / ${fmt(shipmentForm.total_weight_kg)}`} />)}
      {fld("المخلِّص", <input className="aseel-input" readOnly value={clearance ? (clearance.broker_name || `#${clearance.customs_broker}`) : "—"} />)}
      {fld("رقم البيان", <input className="aseel-input" readOnly value={clearance?.declaration_number || "—"} />)}
      {fld("تاريخ التخليص", <input className="aseel-input" type="date" readOnly value={clearance?.clearance_date ? String(clearance.clearance_date).slice(0, 10) : ""} />)}
      {fld("فاتورة المقاصة", <input className="aseel-input" readOnly value={clearance?.settlement_invoice_number || "—"} />)}
      {fld("كشف الضريبة", <input className="aseel-input" readOnly value={clearance?.vat_statement != null ? String(clearance.vat_statement) : "—"} />)}
      {fld("محرَّر", <input className="aseel-input" readOnly value={shipmentForm.editable ? "نعم" : "لا"} />)}
    </div>
  ) : <p className="aseel-text-soft" style={{ padding: 8 }}>...جاري تحميل الحقول</p>;

  const dealsContent = (
    <div style={{ padding: "4px 8px" }}>
      <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600, marginBottom: 4 }}>
        الصفقات المرتبطة ({s.deals_count || 0})
      </h4>
      <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)" }}>
        {s.deals_preview || "لا توجد صفقات مرتبطة بهذه الإرسالية"}
      </p>
    </div>
  );

  const clearanceContent = clearance ? (
    <div style={{ padding: "4px 8px" }}>
      <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600, marginBottom: 4 }}>بنود التخليص</h4>
      <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)" }}>
        <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
          <th style={{ padding: "2px 4px", textAlign: "start" }}>البيان</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>مدين</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>دائن</th>
        </tr></thead>
        <tbody>
          {(clearance.lines || []).map((l) => (
            <tr key={l.id}>
              <td style={{ padding: "2px 4px" }}>{l.description}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{l.debit ? fmt(l.debit) : "—"}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{l.credit ? fmt(l.credit) : "—"}</td>
            </tr>
          ))}
          {(!clearance.lines || clearance.lines.length === 0) && (
            <tr><td colSpan={3} style={{ padding: "8px 4px", textAlign: "center", color: "#999" }}>لا توجد بنود تخليص</td></tr>
          )}
        </tbody>
      </table>
    </div>
  ) : <p className="aseel-text-soft" style={{ padding: 8 }}>لا يوجد تخليص مرتبط</p>;

  const localContent = localShipments.length > 0 ? (
    <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)" }}>
      <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
        <th style={{ padding: "2px 4px", textAlign: "start" }}>رقم</th>
        <th style={{ padding: "2px 4px", textAlign: "start" }}>الناقل</th>
        <th style={{ padding: "2px 4px", textAlign: "center" }}>السائق</th>
        <th style={{ padding: "2px 4px", textAlign: "center" }}>المركبة</th>
        <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>المبلغ</th>
        <th style={{ padding: "2px 4px", textAlign: "center", width: 60 }}>الحالة</th>
      </tr></thead>
      <tbody>
        {localShipments.map((ls) => (
          <tr key={ls.id}>
            <td style={{ padding: "2px 4px" }}>{ls.shipment_number}</td>
            <td style={{ padding: "2px 4px" }}>{ls.carrier_name || "—"}</td>
            <td style={{ padding: "2px 4px", textAlign: "center" }}>{ls.driver_name || "—"}</td>
            <td style={{ padding: "2px 4px", textAlign: "center" }}>{ls.vehicle_number || "—"}</td>
            <td style={{ padding: "2px 4px", textAlign: "center" }}>{fmt(ls.amount)}</td>
            <td style={{ padding: "2px 4px", textAlign: "center" }}>{ls.status || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  ) : <p className="aseel-text-soft" style={{ padding: 8 }}>لا توجد شحنات محلية</p>;

  const paymentsContent = clearance && clearancePayments.length > 0 ? (
    <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)" }}>
      <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
        <th style={{ padding: "2px 4px", textAlign: "start" }}>التاريخ</th>
        <th style={{ padding: "2px 4px", textAlign: "start" }}>الغرض</th>
        <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>المبلغ</th>
        <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>مرحَّلة</th>
        <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>القيد</th>
      </tr></thead>
      <tbody>
        {clearancePayments.map((p) => (
          <tr key={p.id}>
            <td style={{ padding: "2px 4px" }}>{p.payment_date || "—"}</td>
            <td style={{ padding: "2px 4px" }}>{p.payment_purpose || "—"}</td>
            <td style={{ padding: "2px 4px", textAlign: "center" }}>{fmt(p.amount)}</td>
            <td style={{ padding: "2px 4px", textAlign: "center" }}>{p.is_posted ? "✓" : "—"}</td>
            <td style={{ padding: "2px 4px", textAlign: "center" }}>{p.journal ? `#${p.journal}` : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  ) : <p className="aseel-text-soft" style={{ padding: 8 }}>لا توجد دفعات</p>;

  const accountsContent = (
    <div style={{ padding: "4px 8px", fontSize: "var(--aseel-fs-sm, 12px)" }}>
      <div className="aseel-total-row"><span>قيد التحويل (الإرسالية):</span><span><b>{s.transit_journal ? `#${s.transit_journal}` : "—"}</b></span></div>
      <div className="aseel-total-row"><span>قيد التخليص:</span><span><b>{clearance?.journal ? `#${clearance.journal}` : "—"}</b></span></div>
      <div className="aseel-total-row"><span>كشف الضريبة:</span><span><b>{clearance?.vat_statement ?? "—"}</b></span></div>
    </div>
  );

  const attachmentsContent = (
    <p className="aseel-text-soft" style={{ padding: 8 }}>المرفقات (placeholder) — سَيُربط لاحقاً بـ`Attachment` polymorphic (راجع docs/decisions/attachments_model.md).</p>
  );

  const notesContent = (
    <textarea className="aseel-input" readOnly value={s.notes || clearance?.notes || ""} style={{ width: "100%", height: "100%", minHeight: 80, resize: "none", border: "none", padding: 8 }} />
  );

  const tabsConfig: AseelTab[] = [
    { key: "deals", label: "الصفقات", content: dealsContent },
    { key: "clearance", label: "التخليص", content: clearanceContent },
    { key: "local", label: "النقل المحلي", content: localContent },
    { key: "payments", label: "الدفعات", content: paymentsContent },
    { key: "accounts", label: "الحسابات", content: accountsContent },
    { key: "attachments", label: "المرفقات", content: attachmentsContent },
    { key: "notes", label: "ملاحظات", content: notesContent },
  ];

  const handleSaveShipment = useCallback(async () => {
    if (!shipmentForm) return;
    setSaving(true); setError(null);
    try {
      if (shipmentForm.id) {
        const patched = await apiPatchObject<ShipmentApiRow>(`logistics/shipments/${shipmentForm.id}/`, shipmentForm, { tenantId: tid() });
        setShipment(patched);
        setShipmentForm({ ...patched });
      } else {
        const created = await apiPostObject<ShipmentApiRow>("logistics/shipments/", shipmentForm, { tenantId: tid() });
        setShipment(created);
        setShipmentForm({ ...created });
      }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setSaving(false); }
  }, [shipmentForm]);

  const isShipmentDirty = useMemo(() => {
    if (!shipment || !shipmentForm) return false;
    return JSON.stringify(shipment) !== JSON.stringify(shipmentForm);
  }, [shipment, shipmentForm]);

  useEffect(() => {
    if (isShipmentDirty) {
      const onUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); };
      window.addEventListener("beforeunload", onUnload);
      return () => window.removeEventListener("beforeunload", onUnload);
    }
  }, [isShipmentDirty]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "F12") { e.preventDefault(); handleSaveShipment(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleSaveShipment]);

  const toolbarActions: AseelToolbarAction[] = [
    { key: "save", label: "تخزين (F12)", icon: <Save />, onClick: handleSaveShipment, disabled: !isShipmentDirty || saving },
    ...(onClose ? [{ key: "back", label: "رجوع", onClick: onClose }] : []),
  ];

  return (
    <AseelDocumentShell
      title={s.shipment_name || `إرسالية ${s.shipment_number || ""}`}
      state={s.shipment_number ? `شحنة #${s.shipment_number}` : "إرسالية جديدة"}
      nav={nav}
      actions={toolbarActions}
      header={headerBand}
      tabs={tabsConfig}
      initialTab={initialTab}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      totals={totals}
      status={statusBar}
    >
      <CompactTimeline steps={timelineSteps} />
    </AseelDocumentShell>
  );
}
