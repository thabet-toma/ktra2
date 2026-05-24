import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Save } from "lucide-react";
import { apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "@/services/restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { listClearances, ClearanceRow, listClearancePayments, ClearancePaymentRow, updateClearance, createClearance } from "@/services/clearanceApi";
import type { ClearanceLine } from "@/constants/clearanceDefaults";
import { listLocalShipments, LocalShipmentRow } from "@/services/localShippingApi";
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
  shipment_deal_allocations?: Array<{ id: number; deal: number; deal_name?: string; allocated_shipping_cost?: number }>;
}

interface DealRow {
  id: number;
  deal_name?: string;
  deal_number?: string;
  ref_number?: string;
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

const STATUS_ORDER_SEA = ["agent_warehouse", "china_customs_clearance", "on_board", "at_sea", "arrived_port", "israel_customs_clearance", "released", "delivered_local"];
const STATUS_ORDER_AIR = ["agent_warehouse", "china_customs_clearance", "departed", "arrived_airport", "israel_customs_clearance", "released", "delivered_local"];

function buildTimelineSteps(sw: string | undefined | null, shipType: string | undefined): { key: string; label: string; status: "done" | "current" | "pending" }[] {
  const order = shipType === "air" ? STATUS_ORDER_AIR : STATUS_ORDER_SEA;
  const idx = order.indexOf(sw || "");
  return order.map((k, i) => ({
    key: k,
    label: ROUTE_LABELS[k] || k,
    status: (i < idx ? "done" : i === idx ? "current" : "pending") as "done" | "current" | "pending",
  }));
}

const EMPTY_SHIPMENT_ALLOCS: ShipmentApiRow["shipment_deal_allocations"] = [];

export function ImportDocumentScreen({ shipmentId, onClose }: ImportDocumentScreenProps) {
  // ── All hooks MUST be declared before any early return (React rules-of-hooks). ──
  const [searchParams] = useSearchParams();
  const initialTab = searchParams.get("tab") || "deals";
  const [shipment, setShipment] = useState<ShipmentApiRow | null>(null);
  const [shipmentForm, setShipmentForm] = useState<ShipmentApiRow | null>(null);
  const [clearance, setClearance] = useState<ClearanceRow | null>(null);
  const [clearanceForm, setClearanceForm] = useState<ClearanceRow | null>(null);
  const [localShipments, setLocalShipments] = useState<LocalShipmentRow[]>([]);
  const [clearancePayments, setClearancePayments] = useState<ClearancePaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState(initialTab);
  // Deals tab state
  const [linkPickerOpen, setLinkPickerOpen] = useState(false);
  const [availableDeals, setAvailableDeals] = useState<DealRow[]>([]);

  // Empty nav (single-record view) — shell expects a nav prop but we don't browse here yet.
  const nav = useRecordNavigation({ items: [] as ShipmentApiRow[], getId: () => 0, currentId: null, onSelect: () => {} });

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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!shipmentId || shipmentId === "new") {
      setLoading(false);
      if (shipmentId === "new") {
        setShipment(null);
        setShipmentForm({
          id: 0,
          shipment_number: "",
          shipment_date: new Date().toISOString().slice(0, 10),
          editable: true,
        } as ShipmentApiRow);
      } else {
        setShipment(null);
        setShipmentForm(null);
      }
      setClearance(null);
      setClearanceForm(null);
      setLocalShipments([]);
      setClearancePayments([]);
      return;
    }
    void loadAll(shipmentId);
  }, [shipmentId, loadAll]);

  // ── Shipment form helpers ──
  const setSF = useCallback(
    (patch: Partial<ShipmentApiRow>) =>
      setShipmentForm((prev) => (prev ? { ...prev, ...patch } : prev)),
    [],
  );

  const handleSaveShipment = useCallback(async () => {
    if (!shipmentForm) return;
    setSaving(true); setError(null);
    try {
      if (shipmentForm.id) {
        const patched = await apiPatchObject<ShipmentApiRow>(
          `logistics/shipments/${shipmentForm.id}/`,
          shipmentForm,
          { tenantId: tid() },
        );
        setShipment(patched);
        setShipmentForm({ ...patched });
      } else {
        const created = await apiPostObject<ShipmentApiRow>(
          "logistics/shipments/",
          shipmentForm,
          { tenantId: tid() },
        );
        setShipment(created);
        setShipmentForm({ ...created });
        // Note: route stays /import-flow/new; caller can navigate to /import-flow/<created.id>
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipmentForm]);

  const isShipmentDirty = useMemo(() => {
    if (!shipment || !shipmentForm) return false;
    return JSON.stringify(shipment) !== JSON.stringify(shipmentForm);
  }, [shipment, shipmentForm]);

  // Browser warning on close while dirty
  useEffect(() => {
    if (!isShipmentDirty) return undefined;
    const onUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [isShipmentDirty]);

  // F12 → save
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "F12") { e.preventDefault(); void handleSaveShipment(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleSaveShipment]);

  // ── Clearance form helpers ──
  const setCF = useCallback(
    (patch: Partial<ClearanceRow>) =>
      setClearanceForm((prev) => (prev ? { ...prev, ...patch } : prev)),
    [],
  );

  const addClearanceLine = useCallback(() => {
    setClearanceForm((prev) => {
      if (!prev) return prev;
      const lines = prev.lines || [];
      const maxSeq = lines.reduce((m, l) => Math.max(m, l.seq || 0), 0);
      return {
        ...prev,
        lines: [
          ...lines,
          { id: -(lines.length + 1), seq: maxSeq + 1, line_type: "other", description: "", debit: 0, credit: 0, vat_percent: 0 },
        ],
      };
    });
  }, []);

  const updateClearanceLine = useCallback((idx: number, patch: Partial<ClearanceLine>) => {
    setClearanceForm((prev) => {
      if (!prev) return prev;
      const lines = (prev.lines || []).map((l, i) => (i === idx ? { ...l, ...patch } : l));
      return { ...prev, lines };
    });
  }, []);

  const deleteClearanceLine = useCallback((idx: number) => {
    setClearanceForm((prev) => {
      if (!prev) return prev;
      return { ...prev, lines: (prev.lines || []).filter((_, i) => i !== idx) };
    });
  }, []);

  const handleSaveClearance = useCallback(async () => {
    if (!clearanceForm || !clearanceForm.id) return;
    setSaving(true); setError(null);
    try {
      const patched = await updateClearance(clearanceForm.id, {
        declaration_number: clearanceForm.declaration_number,
        clearance_date: clearanceForm.clearance_date,
        transaction_time: clearanceForm.transaction_time,
        second_date: clearanceForm.second_date,
        settlement_invoice_number: clearanceForm.settlement_invoice_number,
        licensed_dealer_no: clearanceForm.licensed_dealer_no,
        customs_broker: clearanceForm.customs_broker,
        currency: clearanceForm.currency,
        exchange_rate: clearanceForm.exchange_rate,
        subtotal_no_vat: clearanceForm.subtotal_no_vat,
        vat_total: clearanceForm.vat_total,
        grand_total: clearanceForm.grand_total,
        cost_lines: (clearanceForm.lines || []).map((l) => ({
          label: l.description,
          amount: (l.debit || 0) - (l.credit || 0),
        })),
      });
      setClearance(patched);
      setClearanceForm({ ...patched });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [clearanceForm]);

  const handleCreateClearance = useCallback(async () => {
    if (!shipment) return;
    setSaving(true); setError(null);
    try {
      const created = await createClearance({ shipment: shipment.id });
      setClearance(created);
      setClearanceForm({ ...created });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment]);

  // ── Deals tab helpers (linking only — unlink/allocate need backend endpoints) ──
  const shipmentDeals = useMemo(
    () => (shipment?.shipment_deal_allocations as ShipmentApiRow["shipment_deal_allocations"]) || EMPTY_SHIPMENT_ALLOCS,
    [shipment],
  );

  const openLinkPicker = useCallback(async () => {
    if (!shipment) return;
    setLinkPickerOpen(true);
    try {
      const rows = await apiGetList<DealRow>("logistics/deals/", { tenantId: tid() });
      const linkedIds = new Set(shipmentDeals.map((d) => d.deal));
      setAvailableDeals(rows.filter((r) => !linkedIds.has(r.id)));
    } catch {
      setAvailableDeals([]);
    }
  }, [shipment, shipmentDeals]);

  const handleLinkDeal = useCallback(async (dealId: number) => {
    if (!shipment) return;
    setSaving(true); setError(null);
    try {
      await apiPostObject(
        `logistics/shipments/${shipment.id}/add_deal/`,
        { deal_id: dealId },
        { tenantId: tid() },
      );
      // Refresh shipment to get updated allocations
      const refreshed = await apiGetObject<ShipmentApiRow>(`logistics/shipments/${shipment.id}/`, { tenantId: tid() });
      setShipment(refreshed);
      setShipmentForm({ ...refreshed });
      setLinkPickerOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment]);

  const handleUnlinkDeal = useCallback(() => {
    // [QUESTION] no remove_deal endpoint exists on LogisticsShipmentViewSet.
    // Unlinking requires a backend addition (task6.1 phase C — flagged in commit 8df2ac8).
    setError("إلغاء ربط الصفقة غير متاح حالياً — يتطلب endpoint جديد في الـbackend.");
  }, []);

  // ── Derived values ──
  const timelineSteps = useMemo(
    () => buildTimelineSteps(shipment?.shipping_workflow_status, shipment?.shipping_type),
    [shipment],
  );

  // ── Early returns AFTER all hooks ──
  if (loading) {
    return <div className="p-8 text-center aseel-text-soft">جاري تحميل الإرسالية…</div>;
  }
  if (error && !shipmentForm) {
    return <div className="p-8 text-center" style={{ color: "var(--aseel-danger, #c0392b)" }}>{error}</div>;
  }
  if (!shipmentId) {
    return (
      <div className="p-8 text-center aseel-text-soft">
        <p>لم يتم اختيار إرسالية.</p>
        <p style={{ marginTop: 8 }}>افتح صفحة «الشحنات» واختر سجلاً لفتحه هنا.</p>
      </div>
    );
  }
  const s = shipment || shipmentForm;
  if (!s || !shipmentForm) {
    return <div className="p-8 text-center aseel-text-soft">لم يتم العثور على الإرسالية</div>;
  }

  // ── Render ──
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
      {isShipmentDirty && <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b45309)" }}>● غير محفوظ</span>}
      <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
    </>
  );

  const sfText = (key: keyof ShipmentApiRow) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setSF({ [key]: e.target.value });

  const headerBand = (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "2px 8px", padding: "4px 0" }}>
      {fld("رقم الإرسالية", <input className="aseel-input" readOnly value={shipmentForm.shipment_number || (shipmentForm.id ? `#${shipmentForm.id}` : "— جديدة —")} />)}
      {fld("تاريخ", <input className="aseel-input" type="date" value={shipmentForm.shipment_date ? String(shipmentForm.shipment_date).slice(0, 10) : ""} onChange={sfText("shipment_date")} />)}
      {fld("الساعة", <input className="aseel-input" type="time" value={shipmentForm.transaction_time ? String(shipmentForm.transaction_time).slice(0, 5) : ""} onChange={sfText("transaction_time")} />)}
      {fld("تاريخ ثاني", <input className="aseel-input" type="date" value={shipmentForm.second_date ? String(shipmentForm.second_date).slice(0, 10) : ""} onChange={sfText("second_date")} />)}
      {fld("الوكيل", <input className="aseel-input" readOnly value={shipmentForm.shipping_agent ? `#${shipmentForm.shipping_agent}` : "—"} />)}
      {fld("اسم الوكيل", <input className="aseel-input" readOnly value={shipmentForm.agent_name || "—"} />)}
      {fld("نوع الإرسالية", <select className="aseel-input" value={shipmentForm.shipment_type || "invoice"} onChange={sfText("shipment_type")}>
        <option value="invoice">فاتورة</option>
        <option value="transport">نقل</option>
      </select>)}
      {fld("نوع الشحن", <select className="aseel-input" value={shipmentForm.shipping_type || ""} onChange={sfText("shipping_type")}>
        <option value="">—</option>
        <option value="sea">بحري</option>
        <option value="air">جوي</option>
        <option value="land">بري</option>
      </select>)}
      {fld("رقم البوليصة", <input className="aseel-input" value={shipmentForm.bill_of_lading || ""} onChange={sfText("bill_of_lading")} />)}
      {fld("رقم الحاوية", <input className="aseel-input" value={shipmentForm.container_number || ""} onChange={sfText("container_number")} />)}
      {fld("المغادرة", <input className="aseel-input" type="date" value={shipmentForm.departure_date ? String(shipmentForm.departure_date).slice(0, 10) : ""} onChange={sfText("departure_date")} />)}
      {fld("الوصول", <input className="aseel-input" type="date" value={shipmentForm.arrival_date ? String(shipmentForm.arrival_date).slice(0, 10) : ""} onChange={sfText("arrival_date")} />)}
      {fld("السفينة / الرحلة", <input className="aseel-input" value={shipmentForm.ship_name || shipmentForm.flight_number || ""} onChange={(e) => setSF({ ship_name: e.target.value, flight_number: e.target.value })} />)}
      {fld("رقم الحركة", <input className="aseel-input" value={shipmentForm.agent_shipment_number || ""} onChange={sfText("agent_shipment_number")} />)}
      {fld("رقم الفاتورة", <input className="aseel-input" readOnly value={shipmentForm.invoice_number || "—"} />)}
      {fld("الحجم / الوزن", <input className="aseel-input" readOnly value={`${fmt(shipmentForm.total_volume)} / ${fmt(shipmentForm.total_weight_kg)}`} />)}
      {fld("المخلِّص", <input className="aseel-input" readOnly value={clearance ? (clearance.broker_name || `#${clearance.customs_broker}`) : "—"} />)}
      {fld("رقم البيان", <input className="aseel-input" readOnly value={clearance?.declaration_number || "—"} />)}
      {fld("تاريخ التخليص", <input className="aseel-input" type="date" readOnly value={clearance?.clearance_date ? String(clearance.clearance_date).slice(0, 10) : ""} />)}
      {fld("فاتورة المقاصة", <input className="aseel-input" readOnly value={clearance?.settlement_invoice_number || "—"} />)}
      {fld("كشف الضريبة", <input className="aseel-input" readOnly value={clearance?.vat_statement != null ? String(clearance.vat_statement) : "—"} />)}
      {fld("محرَّر", <input className="aseel-input" readOnly value={shipmentForm.editable ? "نعم" : "لا"} />)}
    </div>
  );

  const dealsContent = (
    <div style={{ padding: "4px 8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600 }}>الصفقات المرتبطة ({shipmentDeals.length})</h4>
        <button type="button" className="aseel-toolbtn" onClick={() => void openLinkPicker()} disabled={!shipment || saving}>+ ربط صفقة</button>
      </div>
      {linkPickerOpen && (
        <div style={{ position: "fixed", inset: 0, zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.3)" }}>
          <div style={{ background: "#fff", borderRadius: 8, padding: 16, maxWidth: 500, width: "90%", maxHeight: "70vh", overflowY: "auto" }}>
            <h4 style={{ fontWeight: 600, marginBottom: 8 }}>اختر صفقة للربط</h4>
            {availableDeals.length === 0 && <p className="aseel-text-soft">لا توجد صفقات متاحة</p>}
            {availableDeals.map((d) => (
              <div key={d.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid #eee", cursor: "pointer" }}
                onClick={() => void handleLinkDeal(d.id)}>
                <span>{d.deal_name || d.deal_number || d.ref_number || `#${d.id}`}</span>
                <span className="aseel-toolbtn">ربط</span>
              </div>
            ))}
            <div style={{ marginTop: 8, textAlign: "center" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setLinkPickerOpen(false)}>إلغاء</button>
            </div>
          </div>
        </div>
      )}
      <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)" }}>
        <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
          <th style={{ padding: "2px 4px", textAlign: "start" }}>رقم الصفقة</th>
          <th style={{ padding: "2px 4px", textAlign: "start" }}>الاسم</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>حصة التكلفة</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 60 }}>إلغاء</th>
        </tr></thead>
        <tbody>
          {shipmentDeals.map((d) => (
            <tr key={d.id}>
              <td style={{ padding: "2px 4px" }}>#{d.deal}</td>
              <td style={{ padding: "2px 4px" }}>{d.deal_name || "—"}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{fmt(d.allocated_shipping_cost)}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <button type="button" className="aseel-toolbtn" onClick={handleUnlinkDeal} style={{ color: "var(--aseel-danger, #c0392b)", padding: "0 4px" }} title="إلغاء الربط (يتطلب endpoint جديد)">✕</button>
              </td>
            </tr>
          ))}
          {shipmentDeals.length === 0 && (
            <tr><td colSpan={4} style={{ padding: "8px 4px", textAlign: "center", color: "#999" }}>لا توجد صفقات مرتبطة</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );

  const cfText = (key: keyof ClearanceRow) => (e: React.ChangeEvent<HTMLInputElement>) => setCF({ [key]: e.target.value });

  const clearanceContent = clearanceForm ? (
    <div style={{ padding: "4px 8px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "2px 8px", marginBottom: 8 }}>
        {fld("رقم البيان", <input className="aseel-input" value={clearanceForm.declaration_number || ""} onChange={cfText("declaration_number")} />)}
        {fld("تاريخ التخليص", <input className="aseel-input" type="date" value={clearanceForm.clearance_date ? String(clearanceForm.clearance_date).slice(0, 10) : ""} onChange={cfText("clearance_date")} />)}
        {fld("الوقت", <input className="aseel-input" type="time" value={clearanceForm.transaction_time ? String(clearanceForm.transaction_time).slice(0, 5) : ""} onChange={cfText("transaction_time")} />)}
        {fld("تاريخ ثاني", <input className="aseel-input" type="date" value={clearanceForm.second_date ? String(clearanceForm.second_date).slice(0, 10) : ""} onChange={cfText("second_date")} />)}
        {fld("مشتغل مرخص", <input className="aseel-input" value={clearanceForm.licensed_dealer_no || ""} onChange={cfText("licensed_dealer_no")} />)}
        {fld("رقم فاتورة المقاصة", <input className="aseel-input" value={clearanceForm.settlement_invoice_number || ""} onChange={cfText("settlement_invoice_number")} />)}
        {fld("المخلِّص", <input className="aseel-input" readOnly value={clearanceForm.broker_name || (clearanceForm.customs_broker ? `#${clearanceForm.customs_broker}` : "—")} />)}
        {fld("العملة", <input className="aseel-input" value={clearanceForm.currency != null ? String(clearanceForm.currency) : ""} onChange={(e) => setCF({ currency: e.target.value ? Number(e.target.value) : null })} />)}
        {fld("سعر العملة", <input className="aseel-input" type="number" step="0.000001" value={clearanceForm.exchange_rate != null ? String(clearanceForm.exchange_rate) : ""} onChange={(e) => setCF({ exchange_rate: e.target.value ? Number(e.target.value) : null })} />)}
        {fld("مجموع بدون ضريبة", <input className="aseel-input" type="number" step="0.01" value={clearanceForm.subtotal_no_vat != null ? String(clearanceForm.subtotal_no_vat) : ""} onChange={(e) => setCF({ subtotal_no_vat: e.target.value ? Number(e.target.value) : null })} />)}
        {fld("مجموع الضريبة", <input className="aseel-input" type="number" step="0.01" value={clearanceForm.vat_total != null ? String(clearanceForm.vat_total) : ""} onChange={(e) => setCF({ vat_total: e.target.value ? Number(e.target.value) : null })} />)}
        {fld("الإجمالي", <input className="aseel-input" type="number" step="0.01" value={clearanceForm.grand_total != null ? String(clearanceForm.grand_total) : ""} onChange={(e) => setCF({ grand_total: e.target.value ? Number(e.target.value) : null })} />)}
      </div>
      <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)", tableLayout: "fixed" }}>
        <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
          <th style={{ padding: "2px 4px", textAlign: "start", width: 80 }}>النوع</th>
          <th style={{ padding: "2px 4px", textAlign: "start" }}>البيان</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>مدين</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>دائن</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 60 }}>VAT%</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 40 }}>حذف</th>
        </tr></thead>
        <tbody>
          {(clearanceForm.lines || []).map((l, i) => (
            <tr key={l.id ?? i}>
              <td style={{ padding: "2px 4px" }}>
                <select className="aseel-input" value={l.line_type} onChange={(e) => updateClearanceLine(i, { line_type: e.target.value })}>
                  <option value="vat">ضريبة القيمة المضافة</option>
                  <option value="declaration_fee">رسوم البيان</option>
                  <option value="terminal">محطة الشحن</option>
                  <option value="permits">تصاريح</option>
                  <option value="broker_commission">عمولة المخلص</option>
                  <option value="customs_system">نظام الجمارك</option>
                  <option value="other">أخرى</option>
                </select>
              </td>
              <td style={{ padding: "2px 4px" }}>
                <input className="aseel-input" value={l.description} onChange={(e) => updateClearanceLine(i, { description: e.target.value })} style={{ width: "100%" }} />
              </td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <input className="aseel-input" type="number" step="0.01" value={String(l.debit || 0)} onChange={(e) => updateClearanceLine(i, { debit: Number(e.target.value) })} style={{ width: 70 }} />
              </td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <input className="aseel-input" type="number" step="0.01" value={String(l.credit || 0)} onChange={(e) => updateClearanceLine(i, { credit: Number(e.target.value) })} style={{ width: 70 }} />
              </td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <input className="aseel-input" type="number" step="0.01" value={String(l.vat_percent || 0)} onChange={(e) => updateClearanceLine(i, { vat_percent: Number(e.target.value) })} style={{ width: 50 }} />
              </td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <button type="button" className="aseel-toolbtn" onClick={() => deleteClearanceLine(i)} style={{ color: "var(--aseel-danger, #c0392b)", padding: "0 4px" }}>✕</button>
              </td>
            </tr>
          ))}
          {(!clearanceForm.lines || clearanceForm.lines.length === 0) && (
            <tr><td colSpan={6} style={{ padding: "8px 4px", textAlign: "center", color: "#999" }}>لا توجد بنود تخليص</td></tr>
          )}
        </tbody>
      </table>
      <div style={{ display: "flex", gap: 8, padding: "4px 0" }}>
        <button type="button" className="aseel-toolbtn" onClick={addClearanceLine}>+ إضافة بند</button>
        <button type="button" className="aseel-toolbtn" onClick={() => void handleSaveClearance()} disabled={saving}>تخزين التخليص</button>
      </div>
    </div>
  ) : (
    <div style={{ padding: "8px", textAlign: "center" }}>
      <p className="aseel-text-soft" style={{ marginBottom: 8 }}>لا يوجد سجل تخليص لهذه الشحنة</p>
      <button type="button" className="aseel-toolbtn" onClick={() => void handleCreateClearance()} disabled={saving || !shipment}>إنشاء سجل تخليص</button>
    </div>
  );

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
    <textarea
      className="aseel-input"
      value={shipmentForm.notes || ""}
      onChange={(e) => setSF({ notes: e.target.value })}
      style={{ width: "100%", height: "100%", minHeight: 80, resize: "none", border: "none", padding: 8 }}
    />
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

  const toolbarActions: AseelToolbarAction[] = [
    { key: "save", label: "تخزين (F12)", icon: <Save />, onClick: () => void handleSaveShipment(), disabled: !isShipmentDirty || saving },
    ...(onClose ? [{ key: "back", label: "رجوع", onClick: onClose }] : []),
  ];

  return (
    <>
      {error && (
        <div style={{ background: "var(--aseel-err-bg, #fde8e8)", color: "var(--aseel-err, #c0392b)", padding: "4px 12px", borderBottom: "1px solid var(--aseel-err, #c0392b)", fontSize: "var(--aseel-fs-sm, 12px)" }}>
          {error}
        </div>
      )}
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
    </>
  );
}
