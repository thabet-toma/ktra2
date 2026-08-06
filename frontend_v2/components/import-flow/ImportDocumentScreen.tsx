import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { useSearchParams } from "react-router-dom";
import { Save, Plus, FileText, Pencil } from "lucide-react";
import { apiGetList, apiGetObject, apiPatchObject, apiPostObject } from "@/services/restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { listClearances, ClearanceRow, listClearancePayments, ClearancePaymentRow, updateClearance, createClearance, payClearanceFromCashBox, postClearanceAccrual, unpostClearanceAccrual } from "@/services/clearanceApi";
import { accountingApi, type CashBoxLedgerLink } from "@/services/accountingApi";
import type { ClearanceLine } from "@/constants/clearanceDefaults";
import { listLocalShipments, LocalShipmentRow, createLocalShipment, updateLocalShipment, deleteLocalShipment, postLocalShipment, payLocalShipmentFromCashBox } from "@/services/localShippingApi";
import { AseelDocumentShell, useRecordNavigation, AseelToolbarAction, AseelTab, AseelDateInput } from "@/components/aseel";
import { effectiveDealTitleForDisplay } from "@/utils/dealTitleDisplay";
import { getShippingWorkflowLabel } from "@/utils/shippingWorkflowLabels";
import { CompactTimeline } from "./CompactTimeline";
import OfflineGuard from "@/components/offline/OfflineGuard";
import { DocumentPaymentsTab } from "@/components/shared/DocumentPaymentsTab";
import { formatMoney } from "@/utils/formatNumber";
import { getImportJourneyGuidance, getMissingDealMeasureRefs, type ImportJourneyAction } from "./importJourneyGuidance";
import { ImportPartyDuesPanel, type ImportPartyDue } from "./ImportPartyDuesPanel";
import { purchaseInvoiceApi } from "@/services/purchaseInvoiceApi";
import { shipmentsService } from "@/services/shipmentsService";
import { openInNewTab } from "@/utils/openInNewTab";
import { captureScrollPosition, restoreScrollPosition as applyScrollPosition, type ScrollPositionSnapshot } from "@/utils/scrollPosition";
import { formatDateLocalized } from "../../utils/formatDate";
const tid = () => resolveTenantId();
const fmt = (v: number | string | null | undefined) => formatMoney(v, "—");

/** أسماء افتراضية لأنواع بنود التخليص — تُقترَح كـ«بيان» عند اختيار النوع لبند بلا بيان. */
const CLEARANCE_LINE_TYPE_LABELS: Record<string, string> = {
  vat: "ضريبة القيمة المضافة",
  declaration_fee: "رسوم البيان",
  terminal: "محطة الشحن",
  permits: "تصاريح",
  broker_commission: "عمولة المخلص",
  customs_system: "نظام الجمارك",
  "شحن محلي": "شحن محلي",
  other: "أخرى",
};

// G6: تحقّق حقلي — عند تمرير `error` يُحاط الحقل بإطار أحمر وتظهر الرسالة أسفله.
const fld = (label: string, node: React.ReactNode, error?: string | null) => (
  <label
    className="aseel-field"
    style={error ? { outline: "1.5px solid var(--aseel-danger, #c0392b)", outlineOffset: 2, borderRadius: 4 } : undefined}
  >
    <span className="aseel-field-label">{label}</span>
    {node}
    {error ? (
      <span role="alert" style={{ color: "var(--aseel-danger, #c0392b)", fontSize: "11px", marginTop: 2 }}>{error}</span>
    ) : null}
  </label>
);

interface ImportDocumentScreenProps {
  shipmentId: string | null;
  onClose?: () => void;
}

/** دفعة وكيل شحن (LogisticsPayment بدون صفقة) كما تعود من مُسلسِل الشحنة */
interface AgentPaymentApiRow {
  id: number;
  payment_number?: number;
  title?: string;
  amount?: string | number;
  usd_to_ils?: string | number;
  transfer_cost?: string | number;
  transfer_date?: string | null;
  due_date?: string | null;
  status?: string;
  notes?: string | null;
  confirmed_by_supplier?: boolean;
  bank_swift_image?: string | null;
  cash_box_external_id?: string | null;
  is_posted?: boolean;
  journal?: number | null;
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
  chargeable_unit?: "cbm" | "kg" | null;
  freight_rate?: number | null;
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
  shipment_deal_allocations?: Array<{ id: number; deal: number; deal_name?: string; deal_ref?: string; deal_title?: string; allocated_shipping_cost?: number; deal_total_cbm?: number | string; deal_total_weight_kg?: number | string }>;
  payments?: AgentPaymentApiRow[];
}

type ShipmentDealAllocation = NonNullable<ShipmentApiRow["shipment_deal_allocations"]>[number];

interface DealRow {
  id: number;
  deal_name?: string;
  deal_number?: string;
  ref_number?: string;
  description?: string | null;
  notes?: string | null;
  original_offer_number?: string | null;
  partner_name?: string | null;
  shipping_workflow_status?: string | null;
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

interface ShipmentDealAllocationRowProps {
  dealId: number;
  dealRef?: string;
  dealTitle?: string;
  dealName?: string;
  cbm: number;
  kg: number;
  allocatedShippingCost: number;
  freightUnit: "cbm" | "kg";
  busy: boolean;
  disabled: boolean;
  onUpdateMeasure: (dealId: number, patch: { total_cbm?: number; total_weight_kg?: number }) => void;
  onUpdateAllocation: (dealId: number, value: number) => void;
  onUnlink: (dealId: number) => void;
}

const ShipmentDealAllocationRow = React.memo(function ShipmentDealAllocationRow({
  dealId,
  dealRef,
  dealTitle,
  dealName,
  cbm,
  kg,
  allocatedShippingCost,
  freightUnit,
  busy,
  disabled,
  onUpdateMeasure,
  onUpdateAllocation,
  onUnlink,
}: ShipmentDealAllocationRowProps) {
  const [cbmDraft, setCbmDraft] = useState(String(cbm));
  const [kgDraft, setKgDraft] = useState(String(kg));
  const [allocationDraft, setAllocationDraft] = useState(String(allocatedShippingCost));

  useEffect(() => setCbmDraft(String(cbm)), [cbm]);
  useEffect(() => setKgDraft(String(kg)), [kg]);
  useEffect(() => setAllocationDraft(String(allocatedShippingCost)), [allocatedShippingCost]);

  const activeValue = freightUnit === "kg" ? kg : cbm;
  const missing = activeValue <= 0;
  const rowDisabled = disabled || busy;

  return (
    <tr data-testid={`shipment-allocation-row-${dealId}`} aria-busy={busy || undefined}>
      <td style={{ padding: "2px 4px", fontFamily: "monospace" }}>{dealRef || `#${dealId}`}</td>
      <td style={{ padding: "2px 4px" }}>{dealTitle || dealName || "—"}</td>
      <td style={{ padding: "2px 4px", textAlign: "center" }}>
        <input
          className="aseel-input"
          type="number"
          step="0.001"
          min="0"
          value={cbmDraft}
          disabled={rowDisabled}
          onChange={(event) => setCbmDraft(event.target.value)}
          onBlur={() => {
            const value = Number(cbmDraft);
            if (Number.isFinite(value) && value !== cbm) onUpdateMeasure(dealId, { total_cbm: value });
          }}
          data-testid={`shipment-deal-cbm-${dealId}`}
          title="حجم الصفقة (CBM) — عبّئه من هنا مباشرة"
          style={{ width: 62, textAlign: "center", fontWeight: freightUnit === "cbm" ? 700 : 400, ...(freightUnit === "cbm" && missing ? { borderColor: "var(--aseel-danger, #c0392b)", color: "var(--aseel-danger, #c0392b)" } : {}) }}
        />
      </td>
      <td style={{ padding: "2px 4px", textAlign: "center" }}>
        <input
          className="aseel-input"
          type="number"
          step="0.001"
          min="0"
          value={kgDraft}
          disabled={rowDisabled}
          onChange={(event) => setKgDraft(event.target.value)}
          onBlur={() => {
            const value = Number(kgDraft);
            if (Number.isFinite(value) && value !== kg) onUpdateMeasure(dealId, { total_weight_kg: value });
          }}
          data-testid={`shipment-deal-kg-${dealId}`}
          title="وزن الصفقة (KG) — عبّئه من هنا مباشرة"
          style={{ width: 62, textAlign: "center", fontWeight: freightUnit === "kg" ? 700 : 400, ...(freightUnit === "kg" && missing ? { borderColor: "var(--aseel-danger, #c0392b)", color: "var(--aseel-danger, #c0392b)" } : {}) }}
        />
      </td>
      <td style={{ padding: "2px 4px", textAlign: "center" }}>
        <button
          type="button"
          className="aseel-toolbtn"
          onClick={() => openInNewTab(`/deals/${dealId}`)}
          disabled={rowDisabled}
          title="فتح الصفقة وتعديل منتجاتها وقيمها"
        >
          <Pencil size={13} /> تعديل
        </button>
      </td>
      <td style={{ padding: "2px 4px", textAlign: "center" }}>
        <input
          className="aseel-input"
          type="number"
          step="0.01"
          value={allocationDraft}
          disabled={rowDisabled}
          onChange={(event) => setAllocationDraft(event.target.value)}
          onBlur={() => {
            const value = Number(allocationDraft);
            if (Number.isFinite(value) && value !== allocatedShippingCost) onUpdateAllocation(dealId, value);
          }}
          data-testid={`shipment-deal-allocation-${dealId}`}
          style={{ width: 90, textAlign: "center" }}
        />
      </td>
      <td style={{ padding: "2px 4px", textAlign: "center" }}>
        <button
          type="button"
          className="aseel-toolbtn"
          onClick={() => onUnlink(dealId)}
          disabled={rowDisabled}
          style={{ color: "var(--aseel-danger, #c0392b)", padding: "0 4px" }}
          title="فك ربط الصفقة من الشحنة"
        >
          ✕
        </button>
      </td>
    </tr>
  );
});

/** بنود تخليص تمثل نقلاً محلياً (مسار قديم) — المصدر الموحّد تبويب «النقل المحلي».
 *  تطابق LOCAL_SHIPPING_CLEARANCE_LINE_LABELS في logistics/landed_cost.py. */
const LOCAL_SHIPPING_LINE_LABELS = ["شحن محلي", "الشحن المحلي", "شحن داخلي"];
const isLocalShippingClearanceLabel = (s: string | null | undefined) =>
  LOCAL_SHIPPING_LINE_LABELS.includes(String(s || "").trim());

export function ImportDocumentScreen({ shipmentId, onClose }: ImportDocumentScreenProps) {
  // ── All hooks MUST be declared before any early return (React rules-of-hooks). ──
  const [searchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") || "deals";
  const initialTab = ["accounts", "financial_movements", "clearance_financial_movements"].includes(requestedTab)
    ? "financial"
    : requestedTab === "attachments" ? "notes" : requestedTab;
  const confirm = useConfirm();
  const toast = useToast();
  const [shipment, setShipment] = useState<ShipmentApiRow | null>(null);
  const [shipmentForm, setShipmentForm] = useState<ShipmentApiRow | null>(null);
  const [clearance, setClearance] = useState<ClearanceRow | null>(null);
  const [clearanceForm, setClearanceForm] = useState<ClearanceRow | null>(null);
  const [localShipments, setLocalShipments] = useState<LocalShipmentRow[]>([]);
  const [clearancePayments, setClearancePayments] = useState<ClearancePaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingDealIds, setSavingDealIds] = useState<ReadonlySet<number>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  // G6: خريطة «حقل الشحنة → رسالة» لإبراز الحقل الناقص عند فشل الحفظ خادمياً.
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState(initialTab);
  // Deals tab state
  const [linkPickerOpen, setLinkPickerOpen] = useState(false);
  const [availableDeals, setAvailableDeals] = useState<DealRow[]>([]);
  // M2: freight chargeable-unit basis (CBM/KG) + rate — switching recomputes cleanly.
  const [freightUnit, setFreightUnit] = useState<"cbm" | "kg">("cbm");
  const [freightRate, setFreightRate] = useState("");
  // Local tab state (D)
  const [editingLocalId, setEditingLocalId] = useState<number | null>(null);
  const [localForm, setLocalForm] = useState<Partial<LocalShipmentRow> | null>(null);
  const [payingLocalId, setPayingLocalId] = useState<number | null>(null);
  const [localPayAmount, setLocalPayAmount] = useState("");
  const [localPayDate, setLocalPayDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [localPayNotes, setLocalPayNotes] = useState("");
  const [showAdvancedLocal, setShowAdvancedLocal] = useState(false);
  // Payments tab state (E)
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [payDate, setPayDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [payNotes, setPayNotes] = useState("");
  const [cashBoxes, setCashBoxes] = useState<CashBoxLedgerLink[]>([]);
  const [payCashBoxId, setPayCashBoxId] = useState("");
  // «تسجيل سريع» لتكلفة التخليص: إجمالي واحد بدون بنود مفصّلة
  const [quickClearanceTotal, setQuickClearanceTotal] = useState("");
  const [showAdvancedShipment, setShowAdvancedShipment] = useState(false);
  const [showAdvancedClearance, setShowAdvancedClearance] = useState(false);
  const [showClearanceBreakdown, setShowClearanceBreakdown] = useState(false);
  // دفعات وكيل الشحن الدولي (USD) — شرط الاستيراد لفاتورة دولية
  const [showAgentPayForm, setShowAgentPayForm] = useState(false);
  const [agentPayAmount, setAgentPayAmount] = useState("");
  const [agentPayRate, setAgentPayRate] = useState("3.6");
  const [freightAccrualRate, setFreightAccrualRate] = useState("3.6");
  const [agentPayDate, setAgentPayDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [agentPayConfirmed, setAgentPayConfirmed] = useState(true);
  const [agentPayNotes, setAgentPayNotes] = useState("");
  // الناقلون المحليون (بدل إدخال «رقم الناقل» يدوياً)
  const [carriers, setCarriers] = useState<Array<{ id: number; name: string; partner_type?: string }>>([]);
  // إنشاء سريع لوكيل شحن / مخلص جمركي — الحقلان كانا readOnly بلا أي مسار إنشاء (ج7)
  const [quickAddType, setQuickAddType] = useState<null | "FreightForwarder" | "CustomsBroker" | "LocalTransporter">(null);
  const [quickAddName, setQuickAddName] = useState("");
  const scrollPositionRef = React.useRef<ScrollPositionSnapshot | null>(null);
  // Empty nav (single-record view) — shell expects a nav prop but we don't browse here yet.
  const nav = useRecordNavigation({ items: [] as ShipmentApiRow[], getId: () => 0, currentId: null, onSelect: () => {} });

  const saveScrollPosition = useCallback(() => {
    const appContent = document.querySelector<HTMLElement>("main.app-content");
    scrollPositionRef.current = captureScrollPosition(appContent, window.scrollY);
  }, []);

  const restoreScrollPosition = useCallback(() => {
    const snapshot = scrollPositionRef.current;
    scrollPositionRef.current = null;
    if (!snapshot) return;
    window.requestAnimationFrame(() => {
      applyScrollPosition(snapshot, (top) => window.scrollTo(0, top));
    });
  }, []);

  const setDealSaving = useCallback((dealId: number, value: boolean) => {
    setSavingDealIds((current) => {
      const next = new Set(current);
      if (value) next.add(dealId);
      else next.delete(dealId);
      return next;
    });
  }, []);

  const loadAll = useCallback(async (id: number | string) => {
    setLoading(true); setError(null);
    try {
      const s = await apiGetObject<ShipmentApiRow>(`logistics/shipments/${id}/`, { tenantId: tid() });
      setShipment(s);
      setShipmentForm({ ...s });
      // القائمتان مستقلتان ومفلترتان خادمياً بالشحنة؛ زمنهما = الأبطأ منهما
      // بدلاً من مجموعهما، ولا ننزل مستندات شحنات أخرى.
      const [cls, locs] = await Promise.all([
        listClearances({ shipment: s.id }),
        listLocalShipments({ shipment: s.id }),
      ]);
      const matched = cls.find((c) => c.shipment === s.id) || null;
      setClearance(matched);
      setClearanceForm(matched ? { ...matched } : null);
      setLocalShipments(locs);
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

  useEffect(() => {
    const refreshAfterDealEdit = () => {
      if (shipmentId && shipmentId !== "new") void loadAll(shipmentId);
    };
    window.addEventListener("focus", refreshAfterDealEdit);
    return () => window.removeEventListener("focus", refreshAfterDealEdit);
  }, [shipmentId, loadAll]);

  // ── Shipment form helpers ──
  const setSF = useCallback(
    (patch: Partial<ShipmentApiRow>) => {
      setShipmentForm((prev) => (prev ? { ...prev, ...patch } : prev));
      // G6: امسح إبراز الخطأ عن أي حقل عدّله المستخدم.
      setFieldErrors((prev) => {
        const keys = Object.keys(patch);
        if (!keys.some((k) => k in prev)) return prev;
        const next = { ...prev };
        keys.forEach((k) => delete next[k]);
        return next;
      });
    },
    [],
  );

  const reconcileShipmentInvoices = useCallback(async (id: number) => {
    const result = await purchaseInvoiceApi.recalculateLandedCost({
      shipment_id: id,
      auto_repost: true,
    });
    const reconciliation = result.reconciliation;
    if (reconciliation?.left_draft) {
      toast(reconciliation.warnings.join(" · "), "info");
    } else if (result.updated) {
      toast(
        reconciliation?.reposted
          ? `تم تحديث ${result.updated} فاتورة وإعادة ترحيل ${reconciliation.reposted}.`
          : `تم تحديث ${result.updated} فاتورة مرتبطة وبقيت المسودات مسودات.`,
        "success",
      );
    }
    return result;
  }, [toast]);

  const handleSaveShipment = useCallback(async () => {
    if (!shipmentForm) return;
    setSaving(true); setError(null); setFieldErrors({});
    try {
      if (shipmentForm.id) {
        const patched = await apiPatchObject<ShipmentApiRow>(
          `logistics/shipments/${shipmentForm.id}/`,
          shipmentForm,
          { tenantId: tid() },
        );
        setShipment(patched);
        setShipmentForm({ ...patched });
        await reconcileShipmentInvoices(patched.id);
      } else {
        const created = await apiPostObject<ShipmentApiRow>(
          "logistics/shipments/",
          shipmentForm,
          { tenantId: tid() },
        );
        setShipment(created);
        setShipmentForm({ ...created });
        // كان الرابط يبقى /import-flow/new فيضيع السجل عند التحديث — نثبّته على المعرّف الجديد
        window.history.replaceState(null, "", `/import-flow/${created.id}`);
        toast("تم إنشاء الشحنة — الخطوة التالية: اربط الصفقات الجاهزة للشحن.", "success");
        setActiveTab("deals");
        void loadAll(created.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      // G6: أبرِز الحقول التي رفضها الخادم (خريطة مرفقة على الاستثناء من restApi).
      const fe = (e as { fieldErrors?: Record<string, string> })?.fieldErrors;
      if (fe && Object.keys(fe).length) setFieldErrors(fe);
    } finally {
      setSaving(false);
    }
  }, [shipmentForm, toast, loadAll, reconcileShipmentInvoices]);

  const isShipmentDirty = useMemo(() => {
    if (!shipmentForm) return false;
    // شحنة جديدة (لا يوجد سجل محفوظ): زر التخزين متاح دائماً — الشرط القديم
    // كان يتطلب shipment محفوظة فيبقى الزر معطلاً إلى الأبد على /new.
    if (!shipment) return true;
    return JSON.stringify(shipment) !== JSON.stringify(shipmentForm);
  }, [shipment, shipmentForm]);

  // Browser warning on close while dirty (تعديل على سجل محفوظ فقط —
  // الشحنة الجديدة الفارغة لا تستحق تحذير مغادرة)
  useEffect(() => {
    if (!isShipmentDirty || !shipment) return undefined;
    const onUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [isShipmentDirty, shipment]);

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

  const handleSaveClearance = useCallback(async (formOverride?: ClearanceRow): Promise<boolean> => {
    const f = formOverride ?? clearanceForm;
    if (!f || !f.id) return false;
    setSaving(true); setError(null);
    try {
      const patched = await updateClearance(f.id, {
        declaration_number: f.declaration_number,
        clearance_date: f.clearance_date,
        transaction_time: f.transaction_time,
        second_date: f.second_date,
        settlement_invoice_number: f.settlement_invoice_number,
        licensed_dealer_no: f.licensed_dealer_no,
        customs_broker: f.customs_broker,
        currency: f.currency,
        exchange_rate: f.exchange_rate,
        subtotal_no_vat: f.subtotal_no_vat,
        vat_total: f.vat_total,
        grand_total: f.grand_total,
        cost_lines: (f.lines || []).map((l) => ({
          label: l.description,
          amount: (l.debit || 0) - (l.credit || 0),
          type: l.line_type,
        })),
      });
      setClearance(patched);
      setClearanceForm({ ...patched });
      if (patched.shipment) await reconcileShipmentInvoices(Number(patched.shipment));
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setSaving(false);
    }
  }, [clearanceForm, reconcileShipmentInvoices]);

  /** «تسجيل سريع»: إجمالي تخليص واحد بدون بنود — يُخزَّن كبند وحيد ويُحفظ فوراً */
  const applyQuickClearanceTotal = useCallback(async () => {
    if (!clearanceForm || !clearanceForm.id) return;
    const v = Number(quickClearanceTotal);
    if (!Number.isFinite(v) || v <= 0) return;
    const existingSum = (clearanceForm.lines || []).reduce(
      (sum, l) => sum + ((Number(l.debit) || 0) - (Number(l.credit) || 0)), 0,
    );
    if (existingSum !== 0 && !(await confirm({
      title: "استبدال بنود التخليص",
      message: `يوجد بنود بمجموع ${existingSum} ₪ — استبدالها ببند إجمالي واحد بقيمة ${v} ₪؟`,
      confirmText: "استبدال",
    }))) return;
    const next: ClearanceRow = {
      ...clearanceForm,
      grand_total: v,
      lines: [{
        id: -1, seq: 1, line_type: "other",
        description: "تكلفة التخليص (إجمالي)",
        debit: v, credit: 0, vat_percent: 0,
      }],
    };
    setClearanceForm(next);
    if (await handleSaveClearance(next)) {
      setQuickClearanceTotal("");
      toast(`سُجّلت تكلفة التخليص الإجمالية (${v} ₪) وحُفظت.`, "success");
    }
  }, [clearanceForm, quickClearanceTotal, confirm, handleSaveClearance, toast]);

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

  // Deals missing their measure in the chosen unit → freight can't be allocated.
  const missingMeasureRefs = useMemo(() => {
    return getMissingDealMeasureRefs(shipmentDeals, freightUnit);
  }, [shipmentDeals, freightUnit]);

  const openLinkPicker = useCallback(async () => {
    if (!shipment) return;
    setLinkPickerOpen(true);
    try {
      const rows = await apiGetList<DealRow>("logistics/deals/", { tenantId: tid() });
      const linkedIds = new Set(shipmentDeals.map((d) => d.deal));
      const unlinked = rows.filter((r) => !linkedIds.has(r.id));
      // الجاهزات للشحن (المصنع سلّم للوكيل) أولاً — هي المرشح الطبيعي للربط
      unlinked.sort(
        (a, b) =>
          Number(b.shipping_workflow_status === "sw_wait_intl_ship") -
          Number(a.shipping_workflow_status === "sw_wait_intl_ship"),
      );
      setAvailableDeals(unlinked);
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
      await reconcileShipmentInvoices(refreshed.id);
      setLinkPickerOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment, reconcileShipmentInvoices]);

  // ج8 (M5): قدوم من زر «الخطوة التالية» في الصفقة (?join_deal=ID) — بمجرد
  // وجود شحنة محفوظة، افتح فاتح ضمّ الصفقات على تبويب الصفقات تلقائياً (بلا
  // ربط صامت — المستخدم يؤكد اختيار الصفقة). يُنفَّذ مرة واحدة لكل قدوم.
  const joinDealParam = searchParams.get("join_deal");
  const joinHandledRef = React.useRef(false);
  React.useEffect(() => {
    if (!joinDealParam || joinHandledRef.current) return;
    if (!shipment?.id) return;
    const alreadyLinked = shipmentDeals.some(
      (d) => String(d.deal) === String(joinDealParam),
    );
    joinHandledRef.current = true;
    if (alreadyLinked) return;
    setActiveTab("deals");
    void openLinkPicker();
  }, [joinDealParam, shipment, shipmentDeals, openLinkPicker]);

  const handleUnlinkDeal = useCallback(async (dealId: number) => {
    const currentShipmentId = shipment?.id;
    if (!currentShipmentId) return;
    if (!(await confirm({ title: "فك ربط الصفقة", message: "هل تريد فك ربط هذه الصفقة من الشحنة؟", confirmText: "فك الربط" }))) return;
    setSaving(true); setError(null);
    try {
      await apiPostObject(
        `logistics/shipments/${currentShipmentId}/remove_deal/`,
        { deal_id: dealId },
        { tenantId: tid() },
      );
      const refreshed = await apiGetObject<ShipmentApiRow>(`logistics/shipments/${currentShipmentId}/`, { tenantId: tid() });
      setShipment(refreshed);
      setShipmentForm({ ...refreshed });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment?.id, confirm]);

  const handleRedistributeAllocations = useCallback(async () => {
    if (!shipment) return;
    saveScrollPosition();
    setSaving(true); setError(null);
    try {
      await apiPostObject(`logistics/shipments/${shipment.id}/recalculate-distribution/`, {}, { tenantId: tid() });
      const refreshed = await apiGetObject<ShipmentApiRow>(`logistics/shipments/${shipment.id}/`, { tenantId: tid() });
      setShipment(refreshed);
      setShipmentForm({ ...refreshed });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
      restoreScrollPosition();
    }
  }, [shipment, saveScrollPosition, restoreScrollPosition]);

  // M2: keep the freight basis controls in sync with the loaded shipment.
  React.useEffect(() => {
    const cu = (shipment?.chargeable_unit as "cbm" | "kg" | undefined) || "cbm";
    setFreightUnit(cu === "kg" ? "kg" : "cbm");
    setFreightRate(shipment?.freight_rate != null ? String(shipment.freight_rate) : "");
  }, [shipment?.id, shipment?.chargeable_unit, shipment?.freight_rate]);

  const handleSetFreight = useCallback(async (unit: "cbm" | "kg", rate: string) => {
    if (!shipment) return;
    saveScrollPosition();
    setSaving(true); setError(null);
    try {
      const patched = await apiPatchObject<ShipmentApiRow>(
        `logistics/shipments/${shipment.id}/freight/`,
        { chargeable_unit: unit, freight_rate: rate ? Number(rate) : 0 },
        { tenantId: tid() },
      );
      setShipment(patched);
      setShipmentForm({ ...patched });
      await reconcileShipmentInvoices(patched.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
      restoreScrollPosition();
    }
  }, [shipment, reconcileShipmentInvoices, saveScrollPosition, restoreScrollPosition]);

  // Edit a deal's CBM/KG inline from the shipment — no need to leave for the deal
  // screen. Saves to the deal, then (once every deal has the chosen measure and a
  // rate is set) recomputes the freight total + shares automatically.
  const handleUpdateDealMeasure = useCallback(
    async (dealId: number, patch: { total_cbm?: number; total_weight_kg?: number }) => {
      const currentShipmentId = shipment?.id;
      if (!currentShipmentId) return;
      saveScrollPosition();
      setDealSaving(dealId, true); setError(null);
      try {
        await apiPatchObject(`logistics/deals/${dealId}/`, patch, { tenantId: tid() });
        let refreshed = await apiGetObject<ShipmentApiRow>(
          `logistics/shipments/${currentShipmentId}/`, { tenantId: tid() });
        const allocs = refreshed.shipment_deal_allocations || [];
        const num = (v: number | string | undefined) => {
          const n = typeof v === "string" ? parseFloat(v) : v ?? 0;
          return Number.isFinite(n as number) ? (n as number) : 0;
        };
        const stillMissing = allocs.some(
          (d) => num(freightUnit === "kg" ? d.deal_total_weight_kg : d.deal_total_cbm) <= 0);
        // كل الصفقات صار إلها قياس + في سعر شحن → أعِد حساب الإجمالي والحصص تلقائياً.
        if (!stillMissing && Number(freightRate) > 0) {
          refreshed = await apiPatchObject<ShipmentApiRow>(
            `logistics/shipments/${currentShipmentId}/freight/`,
            { chargeable_unit: freightUnit, freight_rate: Number(freightRate) },
            { tenantId: tid() });
        }
        setShipment(refreshed);
        setShipmentForm({ ...refreshed });
        await reconcileShipmentInvoices(refreshed.id);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setDealSaving(dealId, false);
        restoreScrollPosition();
      }
    },
    [shipment?.id, freightUnit, freightRate, reconcileShipmentInvoices, saveScrollPosition, restoreScrollPosition, setDealSaving],
  );

  const handleUpdateAllocation = useCallback(async (dealId: number, newAlloc: number) => {
    const currentShipmentId = shipment?.id;
    if (!currentShipmentId) return;
    saveScrollPosition();
    setDealSaving(dealId, true); setError(null);
    try {
      // Use the existing deal_allocations write-only field on the shipment serializer.
      const patched = await apiPatchObject<ShipmentApiRow>(
        `logistics/shipments/${currentShipmentId}/`,
        { deal_allocations: [{ deal_id: dealId, allocated_shipping_cost: newAlloc }] },
        { tenantId: tid() },
      );
      setShipment(patched);
      setShipmentForm({ ...patched });
      await reconcileShipmentInvoices(patched.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDealSaving(dealId, false);
      restoreScrollPosition();
    }
  }, [shipment?.id, reconcileShipmentInvoices, saveScrollPosition, restoreScrollPosition, setDealSaving]);

  // ── D: Local shipment helpers ──
  const reloadLocal = useCallback(async () => {
    if (!shipment) return;
    try {
      const locs = await listLocalShipments();
      setLocalShipments(locs.filter((l) => l.shipment === shipment.id));
    } catch { /* ignore */ }
  }, [shipment]);

  /** قائمة الناقلين للاختيار — بدل مطالبة المستخدم بحفظ «رقم الناقل» */
  const ensureCarriers = useCallback(async () => {
    if (carriers.length > 0) return;
    try {
      const rows = await apiGetList<{ id: number; name: string; partner_type?: string }>(
        "partners/lookup/?limit=500", { tenantId: tid() },
      );
      const rank = (t?: string) =>
        t === "LocalTransporter" ? 0 : t === "FreightForwarder" ? 1 : t === "Supplier" ? 2 : 3;
      const out = rows
        .filter((p) => p.partner_type !== "Customer")
        .sort((a, b) => rank(a.partner_type) - rank(b.partner_type) || String(a.name).localeCompare(String(b.name), "ar"));
      setCarriers(out);
    } catch { /* تبقى القائمة فارغة — يظهر تلميح في النموذج */ }
  }, [carriers.length]);

  // قوائم الوكيل/المخلص في رأس الشحنة وتبويب التخليص تحتاج الشركاء فوراً
  useEffect(() => { void ensureCarriers(); }, [ensureCarriers]);

  const handleQuickAddPartner = useCallback(async () => {
    const nm = quickAddName.trim();
    if (!quickAddType || !nm) return;
    setSaving(true); setError(null);
    try {
      const created = await apiPostObject<{ id: number; name?: string }>(
        "partners/",
        { name: nm, partner_type: quickAddType },
        { tenantId: tid() },
      );
      const row = { id: created.id, name: created.name || nm, partner_type: quickAddType };
      setCarriers((prev) => [...prev, row]);
      if (quickAddType === "FreightForwarder") {
        setSF({ shipping_agent: created.id, agent_name: row.name } as Partial<ShipmentApiRow>);
      } else if (quickAddType === "LocalTransporter") {
        setLocalForm((prev) => (prev ? { ...prev, carrier: created.id } : prev));
      } else {
        setCF({ customs_broker: created.id, broker_name: row.name } as Partial<ClearanceRow>);
      }
      const typeLabel = quickAddType === "FreightForwarder" ? "وكيل الشحن" : quickAddType === "LocalTransporter" ? "الناقل المحلي" : "المخلِّص";
      toast(`تمت إضافة ${typeLabel} «${row.name}» واختياره`, "success");
      setQuickAddType(null);
      setQuickAddName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [quickAddType, quickAddName, setSF, setCF, toast]);

  const handleEditLocal = useCallback((ls: LocalShipmentRow) => {
    setEditingLocalId(ls.id);
    setLocalForm({ ...ls });
    setShowAdvancedLocal(Boolean(ls.driver_name || ls.vehicle_number || ls.origin || ls.pickup_date || ls.notes));
    void ensureCarriers();
  }, [ensureCarriers]);

  const handleNewLocal = useCallback(() => {
    setEditingLocalId(0);
    setLocalForm({ id: 0, shipment: (shipment || shipmentForm)?.id ?? null, carrier: 0, amount: "0", currency: 0, exchange_rate: "1", status: "pending", payment_type: "credit", capitalize_to_inventory: true, is_posted: false, purchase_invoice: null, shipment_number: "" } as Partial<LocalShipmentRow>);
    setShowAdvancedLocal(false);
    void ensureCarriers();
  }, [shipment, shipmentForm, ensureCarriers]);

  const handleCancelLocal = useCallback(() => {
    setEditingLocalId(null);
    setLocalForm(null);
    setShowAdvancedLocal(false);
  }, []);

  const setLF = useCallback((patch: Partial<LocalShipmentRow>) =>
    setLocalForm((prev) => (prev ? { ...prev, ...patch } : prev)), []);

  const handleSaveLocal = useCallback(async () => {
    if (!localForm || !shipment) return;
    // Carrier is a required FK on LocalShipment — reject early so we don't
    // round-trip a 400 just to learn the user missed the field.
    if (!localForm.carrier || Number(localForm.carrier) <= 0) {
      setError("الناقل مطلوب — أدخل رقم تعريف الناقل قبل الحفظ.");
      return;
    }
    setSaving(true); setError(null);
    try {
      if (editingLocalId && editingLocalId > 0) {
        const updated = await updateLocalShipment(editingLocalId, {
          carrier: localForm.carrier, driver_name: localForm.driver_name,
          vehicle_number: localForm.vehicle_number, origin: localForm.origin,
          destination: localForm.destination, pickup_date: localForm.pickup_date,
          delivery_date: localForm.delivery_date, amount: localForm.amount || "0",
          currency: localForm.currency || 1, exchange_rate: localForm.exchange_rate || "1",
          payment_type: (localForm.payment_type as "credit" | "cash") || "credit",
          status: localForm.status as LocalShipmentRow["status"],
          notes: localForm.notes,
        });
        setLocalShipments((prev) => prev.map((l) => l.id === editingLocalId ? updated : l));
        setEditingLocalId(null); setLocalForm(null);
      } else {
        const created = await createLocalShipment({
          shipment: shipment.id, carrier: Number(localForm.carrier),
          driver_name: localForm.driver_name, vehicle_number: localForm.vehicle_number,
          origin: localForm.origin, destination: localForm.destination,
          pickup_date: localForm.pickup_date, delivery_date: localForm.delivery_date,
          amount: localForm.amount || "0",
          currency: localForm.currency || 1, exchange_rate: localForm.exchange_rate || "1",
          payment_type: (localForm.payment_type as "credit" | "cash") || "credit",
          status: localForm.status as LocalShipmentRow["status"],
          notes: localForm.notes,
        });
        setLocalShipments((prev) => [...prev, created]);
        setEditingLocalId(null); setLocalForm(null);
      }
      void reloadLocal();
      await reconcileShipmentInvoices(shipment.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [localForm, editingLocalId, shipment, reloadLocal, reconcileShipmentInvoices]);

  const handleDeleteLocal = useCallback(async (id: number) => {
    if (!(await confirm({ title: "حذف النقل المحلي", message: "هل تريد حذف سجل النقل المحلي؟" }))) return;
    setSaving(true); setError(null);
    try {
      await deleteLocalShipment(id);
      setLocalShipments((prev) => prev.filter((l) => l.id !== id));
      if (editingLocalId === id) { setEditingLocalId(null); setLocalForm(null); }
      if (shipment) await reconcileShipmentInvoices(shipment.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [editingLocalId, shipment, reconcileShipmentInvoices]);

  const handlePostLocal = useCallback(async (id: number) => {
    setSaving(true); setError(null);
    try {
      const updated = await postLocalShipment(id);
      setLocalShipments((prev) => prev.map((l) => l.id === id ? updated : l));
      toast("تم إثبات استحقاق النقل على ذمم الناقل. الدفع منفصل ويمكن تسجيله من نفس السطر.", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [toast]);

  const openLocalPayment = useCallback((row: LocalShipmentRow) => {
    setPayingLocalId(row.id);
    setLocalPayAmount(String(row.remaining_balance ?? Math.max(0, Number(row.amount) - Number(row.amount_paid || 0))));
    setLocalPayDate(new Date().toISOString().slice(0, 10));
    setLocalPayNotes("");
  }, []);

  const handlePayLocal = useCallback(async () => {
    if (!payingLocalId || !payCashBoxId || Number(localPayAmount) <= 0) return;
    setSaving(true); setError(null);
    try {
      await payLocalShipmentFromCashBox(payingLocalId, {
        amount: Number(localPayAmount),
        cash_box_external_id: payCashBoxId,
        payment_date: localPayDate || undefined,
        notes: localPayNotes || undefined,
      });
      setPayingLocalId(null);
      setLocalPayAmount("");
      setLocalPayNotes("");
      await reloadLocal();
      toast("تم تسجيل دفعة الناقل وبقيت داخل رحلة الاستيراد.", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [payingLocalId, payCashBoxId, localPayAmount, localPayDate, localPayNotes, reloadLocal, toast]);

  // ── تراجع عن الترحيل (task17 — كانت الـ endpoints جاهزة backend بلا واجهة) ──
  const handleUnpostShipment = useCallback(async () => {
    if (!shipment) return;
    if (!(await confirm({
      title: "تراجع عن ترحيل الشحنة",
      message: "سيُحذف قيد الشحنة وتُعكس حركات استلام مخزونها وتعود مسودة.\nيُمنع التراجع إن كانت مبيعات لاحقة استهلكت مخزونها (حارس الاعتمادية).",
      confirmText: "تراجع عن الترحيل",
    }))) return;
    setSaving(true); setError(null);
    try {
      await apiPostObject(`logistics/shipments/${shipment.id}/unpost/`, {}, { tenantId: tid() });
      toast("تم التراجع عن ترحيل الشحنة — حُذف القيد وعُكست حركات المخزون.", "success");
      await loadAll(shipment.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment, confirm, toast]);

  const handleUnpostClearance = useCallback(async () => {
    if (!clearance) return;
    if (!(await confirm({
      title: "تراجع عن ترحيل دفعات التخليص",
      message: "سيُحذف قيد كل دفعات التخليص المرحّلة وتعود الدفعات مسودات قابلة للتعديل.",
      confirmText: "تراجع عن الترحيل",
    }))) return;
    setSaving(true); setError(null);
    try {
      await apiPostObject(`logistics/clearances/${clearance.id}/unpost/`, {}, { tenantId: tid() });
      toast("تم التراجع عن ترحيل دفعات التخليص وحذف قيودها.", "success");
      if (shipment) await loadAll(shipment.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [clearance, shipment, confirm, toast]);

  const handleUnpostLocal = useCallback(async (id: number) => {
    if (!(await confirm({
      title: "تراجع عن ترحيل النقل المحلي",
      message: "سيُحذف قيد المصروف ويعود سجل النقل المحلي مسودة (فيمكن نقله إلى الفاتورة أو تعديله).",
      confirmText: "تراجع عن الترحيل",
    }))) return;
    setSaving(true); setError(null);
    try {
      await apiPostObject(`logistics/local-shipments/${id}/unpost/`, {}, { tenantId: tid() });
      toast("تم التراجع عن ترحيل النقل المحلي وحذف قيده.", "success");
      await reloadLocal();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [confirm, toast]);

  // ── E: Payment helpers ──
  const reloadPayments = useCallback(async () => {
    if (!clearance) return;
    try {
      const pays = await listClearancePayments(clearance.id);
      setClearancePayments(pays);
    } catch { /* ignore */ }
  }, [clearance]);

  // Load cash boxes once (used in E-payment form)
  useEffect(() => {
    if (cashBoxes.length > 0) return;
    void accountingApi.getCashBoxLedgers().then((rows) => {
      setCashBoxes(rows);
      if (rows.length > 0 && !payCashBoxId) setPayCashBoxId(rows[0].external_id);
    }).catch(() => { /* ignore — surfaced when user opens the form */ });
  }, [cashBoxes.length, payCashBoxId]);

  const handleAddPayment = useCallback(async () => {
    if (!clearance || !payAmount || Number(payAmount) <= 0) return;
    if (!payCashBoxId) {
      setError("اختر الصندوق قبل تسجيل الدفعة.");
      return;
    }
    setSaving(true); setError(null);
    try {
      await payClearanceFromCashBox(clearance.id, {
        amount: Number(payAmount),
        cash_box_external_id: payCashBoxId,
        payment_kind: "clearance",
        payment_date: payDate || undefined,
        notes: payNotes || undefined,
      });
      setShowPaymentForm(false);
      setPayAmount("");
      setPayDate(new Date().toISOString().slice(0, 10));
      setPayNotes("");
      await reloadPayments();
      toast("تم تسجيل دفعة المخلّص. بقيت في رحلة الاستيراد ولم تُفتح شاشة القيود.", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [clearance, payAmount, payDate, payNotes, payCashBoxId, reloadPayments, toast]);

  const openClearancePayment = useCallback(() => {
    const total = (clearanceForm?.lines || []).reduce(
      (sum, line) => sum + Math.max(0, (Number(line.debit) || 0) - (Number(line.credit) || 0)),
      0,
    );
    const paid = clearancePayments
      .filter((payment) => payment.payment_purpose !== "shipping" && payment.is_posted)
      .reduce((sum, payment) => sum + (Number(payment.amount) || 0), 0);
    setPayAmount(String(Math.max(0, total - paid)));
    setShowPaymentForm(true);
    setActiveTab("payments");
  }, [clearanceForm, clearancePayments]);

  const handlePostClearance = useCallback(async () => {
    if (!clearanceForm?.id) return;
    if (!(await handleSaveClearance())) return;
    setSaving(true); setError(null);
    try {
      const result = await postClearanceAccrual(clearanceForm.id);
      toast(result.message, "success");
      if (shipment) await loadAll(shipment.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [clearanceForm, handleSaveClearance, shipment, loadAll, toast]);

  const handleUnpostClearanceAccrual = useCallback(async () => {
    if (!clearance?.id) return;
    if (!(await confirm({
      title: "تراجع عن استحقاق التخليص",
      message: "سيُحذف قيد استحقاق التخليص فقط. دفعات المخلّص تبقى بقيودها المستقلة.",
      confirmText: "تراجع",
    }))) return;
    setSaving(true); setError(null);
    try {
      const result = await unpostClearanceAccrual(clearance.id);
      toast(result.message, "success");
      if (shipment) await loadAll(shipment.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [clearance, shipment, loadAll, confirm, toast]);

  // ── دفعات وكيل الشحن (LogisticsPayment على الشحنة، بدون صفقة) ──
  // كانت بلا أي واجهة رغم أن استيراد الفاتورة الدولية مشروط باكتمالها بالدولار.
  const handleAddAgentPayment = useCallback(async () => {
    if (!shipment) return;
    const amt = Number(agentPayAmount);
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("أدخل مبلغ الدفعة بالدولار (أكبر من صفر).");
      return;
    }
    setSaving(true); setError(null);
    try {
      // المطابقة في الخادم تتم بـ payment_number — نمرّر الدفعات القائمة كما هي + الجديدة
      const existing = (shipment.payments || []).map((p, idx) => ({
        id: p.id,
        payment_number: Number(p.payment_number) > 0 ? Number(p.payment_number) : idx + 1,
        title: p.title || `Payment ${idx + 1}`,
        amount: Number(p.amount || 0),
        transfer_date: p.transfer_date ? String(p.transfer_date).slice(0, 10) : null,
        due_date: (p.due_date || p.transfer_date) ? String(p.due_date || p.transfer_date).slice(0, 10) : null,
        status: p.status || "Pending",
        notes: p.notes || "",
        confirmed_by_supplier: Boolean(p.confirmed_by_supplier),
        usd_to_ils: Number(p.usd_to_ils || 3.6),
        transfer_cost: Number(p.transfer_cost || 0),
      }));
      const nextNo = existing.reduce((m, p) => Math.max(m, p.payment_number), 0) + 1;
      const rows = [
        ...existing,
        {
          payment_number: nextNo,
          title: `دفعة شحن ${nextNo}`,
          amount: amt,
          transfer_date: agentPayDate || null,
          due_date: agentPayDate || null,
          status: agentPayConfirmed ? "Confirmed" : "Pending",
          notes: agentPayNotes || "",
          confirmed_by_supplier: agentPayConfirmed,
          usd_to_ils: Number(agentPayRate) || 3.6,
          transfer_cost: 0,
        },
      ];
      const patched = await apiPatchObject<ShipmentApiRow>(
        `logistics/shipments/${shipment.id}/`,
        { payments: rows },
        { tenantId: tid() },
      );
      setShipment(patched);
      setShipmentForm({ ...patched });
      await reconcileShipmentInvoices(patched.id);
      setShowAgentPayForm(false);
      setAgentPayAmount("");
      setAgentPayNotes("");
      toast(
        agentPayConfirmed
          ? "سُجّلت دفعة وكيل الشحن (مؤكّدة) — تُحتسب ضمن شرط الاستيراد."
          : "سُجّلت الدفعة كمعلّقة — لن تُحتسب لشرط الاستيراد حتى تأكيدها.",
        "success",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment, agentPayAmount, agentPayRate, agentPayDate, agentPayConfirmed, agentPayNotes, toast, reconcileShipmentInvoices]);

  // ── استحقاق شحن الوكيل: قيد مستقل تماماً عن دفعاته ──
  const refetchShipment = useCallback(async (shipmentId: number) => {
    const fresh = await apiGetObject<ShipmentApiRow>(
      `logistics/shipments/${shipmentId}/`, { tenantId: tid() },
    );
    setShipment(fresh);
    setShipmentForm({ ...fresh });
  }, []);

  const handlePostFreightAccrual = useCallback(async () => {
    if (!shipment) return;
    const rate = Number(freightAccrualRate);
    if (!Number.isFinite(rate) || rate <= 0) {
      setError("أدخل سعر صرف الدولار للشيكل (أكبر من صفر).");
      return;
    }
    setSaving(true); setError(null);
    try {
      const res = await shipmentsService.postShipmentFreightAccrual(String(shipment.id), rate);
      // تحديث فوري من ردّ الترحيل: لا ننتظر إعادة الجلب حتى تتقدّم الخطوة بلا لبس.
      const accrued = { freight_is_posted: true, freight_exchange_rate: rate };
      setShipment((prev) => (prev ? { ...prev, ...accrued } : prev));
      setShipmentForm((prev) => (prev ? { ...prev, ...accrued } : prev));
      await refetchShipment(shipment.id);
      toast(`أُثبت استحقاق الشحن على الوكيل (${res.amount_ils || ""} ₪) — الدفع لاحقاً ومستقل.`, "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment, freightAccrualRate, refetchShipment, toast]);

  const handleUnpostFreightAccrual = useCallback(async () => {
    if (!shipment) return;
    setSaving(true); setError(null);
    try {
      await shipmentsService.unpostShipmentFreightAccrual(String(shipment.id));
      const cleared = { freight_is_posted: false, freight_exchange_rate: null };
      setShipment((prev) => (prev ? { ...prev, ...cleared } : prev));
      setShipmentForm((prev) => (prev ? { ...prev, ...cleared } : prev));
      await refetchShipment(shipment.id);
      toast("تم التراجع عن استحقاق الشحن — دفعات الوكيل المرحّلة لم تتأثر.", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }, [shipment, refetchShipment, toast]);

  // ── F: Convert to purchase invoice ──
  const [convertedInvoices, setConvertedInvoices] = useState<Array<{
    id: number;
    invoice_number: string;
    deal?: number | null;
    shipment?: number;
  }>>([]);
  const checkConvertedInvoice = useCallback(async () => {
    if (!shipment || !shipment.id) return;
    try {
      // الخادم يفلتر بـ shipment (أُضيف في task12) — أي فاتورة راجعة تخص هذه الشحنة
      const invoices = await apiGetList<{ id: number; invoice_number: string; deal?: number | null; shipment?: number }>(
        "logistics/purchase-invoices/",
        { tenantId: tid(), query: { shipment: shipment.id } },
      );
      setConvertedInvoices(invoices.filter((inv) => Number(inv.shipment) === Number(shipment.id)));
    } catch { /* ignore */ }
  }, [shipment]);

  useEffect(() => { void checkConvertedInvoice(); }, [checkConvertedInvoice]);
  useEffect(() => {
    window.addEventListener("focus", checkConvertedInvoice);
    return () => window.removeEventListener("focus", checkConvertedInvoice);
  }, [checkConvertedInvoice]);

  const convertedPiId = convertedInvoices[0]?.id || null;
  const convertedDealIds = useMemo(
    () => new Set(convertedInvoices.map((invoice) => Number(invoice.deal)).filter((id) => Number.isFinite(id) && id > 0)),
    [convertedInvoices],
  );
  const remainingDealsCount = shipmentDeals.filter((deal) => !convertedDealIds.has(Number(deal.deal))).length;
  const allDealsConverted = shipmentDeals.length > 0 && remainingDealsCount === 0;

  // ── Derived values ──
  const timelineSteps = useMemo(
    () => buildTimelineSteps(shipment?.shipping_workflow_status, shipment?.shipping_type),
    [shipment],
  );

  // ── Early returns AFTER all hooks ──
  if (loading) {
    return <div className="p-8 text-center aseel-text-soft">جاري تحميل الشحنة…</div>;
  }
  if (error && !shipmentForm) {
    return (
      <div className="p-8 text-center text-red-700">
        <p>{error}</p>
        <button
          type="button"
          className="mt-3 rounded border border-red-300 px-4 py-2 hover:bg-red-50"
          onClick={() => { if (shipmentId) void loadAll(shipmentId); }}
        >
          إعادة المحاولة
        </button>
      </div>
    );
  }
  if (!shipmentId) {
    return (
      <div className="p-8 text-center aseel-text-soft">
        <p>لم يتم اختيار شحنة.</p>
        <p style={{ marginTop: 8 }}>افتح صفحة «الشحنات» واختر سجلاً لفتحه هنا.</p>
      </div>
    );
  }
  const s = shipment || shipmentForm;
  if (!s || !shipmentForm) {
    return <div className="p-8 text-center aseel-text-soft">لم يتم العثور على الشحنة</div>;
  }

  // ── Render ──
  // دفعات وكيل الشحن: «المستقرة» = مؤكّدة/مدفوعة أو بسليب أو من صندوق (نفس payment_settled في الخادم)
  const agentPayments: AgentPaymentApiRow[] = shipment?.payments || [];
  const isAgentPaymentSettled = (p: AgentPaymentApiRow) =>
    Boolean(p.confirmed_by_supplier) ||
    Boolean(String(p.bank_swift_image || "").trim()) ||
    Boolean(String(p.cash_box_external_id || "").trim()) ||
    ["confirmed", "paid"].includes(String(p.status || "").toLowerCase());
  const freightTotalUsd = Number(s.total_shipping_cost_usd) || 0;
  const freightPaidUsd = agentPayments
    .filter(isAgentPaymentSettled)
    .reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const freightFullyPaid = freightTotalUsd > 0 && freightPaidUsd >= freightTotalUsd - 0.02;
  // بوابة الاستيراد صارت «التكلفة مُثبتة» لا «مدفوعة»: قيد الاستحقاق يثبّت تكلفة
  // الشحن وسعر صرفها، فلا داعي لدفع الوكيل — ولا لدفعة وهمية عندما تكون التكلفة صفراً.
  const freightAccrued = Boolean((s as { freight_is_posted?: boolean }).freight_is_posted);
  /** الفائض عن تكلفة الشحن = دفعة مقدمة لدى الوكيل (يصبح مديناً لنا) */
  const freightAgentAdvanceUsd = Math.max(0, freightPaidUsd - freightTotalUsd);
  const freightCostEstablished = freightAccrued || freightFullyPaid || freightTotalUsd <= 0;

  const paidShipping = clearancePayments
    .filter((p) => p.payment_purpose === "shipping" && p.is_posted)
    .reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const paidClearance = clearancePayments
    .filter((p) => p.payment_purpose !== "shipping" && p.is_posted)
    .reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const clearanceCostTotal = (clearanceForm?.lines || []).reduce(
    (sum, line) => sum + Math.max(0, (Number(line.debit) || 0) - (Number(line.credit) || 0)),
    0,
  );
  const clearanceRemaining = Math.max(0, clearanceCostTotal - paidClearance);
  /** الفائض عن استحقاق التخليص = دفعة مقدمة لدى المخلّص (يصبح مديناً لنا) */
  const clearanceAdvance = Math.max(0, paidClearance - clearanceCostTotal);
  const guidance = getImportJourneyGuidance({
    shipmentSaved: Boolean(s.id),
    invoiceEligible: s.shipment_type !== "transport",
    dealsCount: shipmentDeals.length,
    freightTotalUsd,
    freightCostEstablished,
    clearanceExists: Boolean(clearance),
    clearanceCostTotal,
    convertedInvoiceId: convertedPiId,
    remainingDealsCount,
  });
  const executeGuidanceAction = (action: ImportJourneyAction) => {
    if (action === "save_shipment") void handleSaveShipment();
    if (action === "link_deals") {
      setActiveTab("deals");
      void openLinkPicker();
    }
    if (action === "pay_freight") setActiveTab("payments");
    if (action === "create_clearance") {
      setActiveTab("clearance");
      void handleCreateClearance();
    }
    if (action === "enter_clearance_costs") {
      setActiveTab("clearance");
      setShowClearanceBreakdown(false);
    }
    if (action === "manage_local_transport") {
      setActiveTab("local");
      if (localShipments.length === 0) handleNewLocal();
    }
    if (action === "create_invoice" && shipment?.id) {
      window.open(`/international-invoices?import_shipment=${shipment.id}`, "_blank");
    }
    if (action === "view_invoice" && convertedPiId) {
      window.open(`/purchase-invoices/${convertedPiId}`, "_blank");
    }
  };
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
      <div className="aseel-total-row"><span>{clearance ? `تكلفة التخليص #${clearance.id}` : "تكلفة التخليص"}</span><span className="aseel-total-value">{clearance ? fmt(clearanceCostTotal) : "—"}</span></div>
      {clearance && <div className="aseel-total-row"><span>مدفوع تخليص</span><span className="aseel-total-value">{fmt(paidClearance)}</span></div>}
      {clearance && <div className="aseel-total-row"><span>متبقي تخليص</span><span className="aseel-total-value">{fmt(clearanceRemaining)}</span></div>}
      {clearance && <div className="aseel-total-row"><span>مدفوع شحن</span><span className="aseel-total-value">{fmt(paidShipping)}</span></div>}
      {localShipments.map((ls) => (
        <div className="aseel-total-row" key={ls.id}><span>نقل محلي #{ls.shipment_number} · متبقي</span><span className="aseel-total-value">{fmt(ls.remaining_balance ?? ls.amount)}</span></div>
      ))}
    </>
  );

  const statusBar = (
    <>
      <span className="aseel-status-item">الحالة <b>{s.shipping_workflow_status || "—"}</b></span>
      {s.transit_journal && <span className="aseel-status-item">رقم القيد <b>#{s.transit_journal}</b></span>}
      <span className="aseel-status-item">رقم الشحنة <b>{s.shipment_number || "—"}</b></span>
      {isShipmentDirty && <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b45309)" }}>● غير محفوظ</span>}
      <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
    </>
  );

  const sfText = (key: keyof ShipmentApiRow) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setSF({ [key]: e.target.value });

  const headerBand = (
    <div className="grid w-full grid-cols-1 gap-x-2 gap-y-1 py-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
      {fld("رقم الشحنة", <input className="aseel-input" readOnly value={shipmentForm.shipment_number || (shipmentForm.id ? `#${shipmentForm.id}` : "— جديدة —")} />)}
      {fld("تاريخ", <AseelDateInput value={shipmentForm.shipment_date ? String(shipmentForm.shipment_date).slice(0, 10) : ""} onChange={(v) => setSF({ shipment_date: v })} />, fieldErrors.shipment_date)}
      {showAdvancedShipment && <>
        {fld("الساعة", <input className="aseel-input" type="time" value={shipmentForm.transaction_time ? String(shipmentForm.transaction_time).slice(0, 5) : ""} onChange={sfText("transaction_time")} />)}
        {fld("تاريخ ثاني", <AseelDateInput value={shipmentForm.second_date ? String(shipmentForm.second_date).slice(0, 10) : ""} onChange={(v) => setSF({ second_date: v })} />)}
      </>}
      {fld("وكيل الشحن", <span style={{ display: "flex", gap: 2 }}>
        <select
          className="aseel-input"
          value={shipmentForm.shipping_agent ?? ""}
          onChange={(e) => {
            const v = e.target.value ? Number(e.target.value) : null;
            const p = carriers.find((c) => c.id === v);
            setSF({ shipping_agent: v, agent_name: p?.name || "" } as Partial<ShipmentApiRow>);
          }}
        >
          <option value="">— بلا وكيل —</option>
          {carriers.filter((c) => c.partner_type === "FreightForwarder").map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
          {shipmentForm.shipping_agent &&
            !carriers.some((c) => c.id === shipmentForm.shipping_agent) && (
              <option value={shipmentForm.shipping_agent}>
                {shipmentForm.agent_name || `#${shipmentForm.shipping_agent}`}
              </option>
            )}
        </select>
        <button type="button" className="aseel-ellipsis" title="إضافة وكيل شحن جديد" onClick={() => { setQuickAddType("FreightForwarder"); setQuickAddName(""); }}>+</button>
      </span>, fieldErrors.shipping_agent)}
      {showAdvancedShipment && <>
        {fld("اسم الوكيل", <input className="aseel-input" readOnly value={shipmentForm.agent_name || "—"} />)}
        {fld("نوع الشحنة", <select className="aseel-input" value={shipmentForm.shipment_type || "invoice"} onChange={sfText("shipment_type")}>
          <option value="invoice">فاتورة (تتحول لفاتورة شراء)</option>
          <option value="transport">نقل فقط</option>
        </select>)}
      </>}
      {fld("نوع الشحن", <select className="aseel-input" value={shipmentForm.shipping_type || ""} onChange={sfText("shipping_type")}>
        <option value="">—</option>
        <option value="sea">بحري</option>
        <option value="air">جوي</option>
        <option value="land">بري</option>
      </select>, fieldErrors.shipping_type)}
      {fld("رقم البوليصة", <input className="aseel-input" value={shipmentForm.bill_of_lading || ""} onChange={sfText("bill_of_lading")} />, fieldErrors.bill_of_lading)}
      {fld("رقم الحاوية", <input className="aseel-input" value={shipmentForm.container_number || ""} onChange={sfText("container_number")} />, fieldErrors.container_number)}
      {fld("المغادرة", <AseelDateInput value={shipmentForm.departure_date ? String(shipmentForm.departure_date).slice(0, 10) : ""} onChange={(v) => setSF({ departure_date: v })} />, fieldErrors.departure_date)}
      {fld("الوصول", <AseelDateInput value={shipmentForm.arrival_date ? String(shipmentForm.arrival_date).slice(0, 10) : ""} onChange={(v) => setSF({ arrival_date: v })} />, fieldErrors.arrival_date)}
      {showAdvancedShipment && <>
        {fld("السفينة / الرحلة", <input className="aseel-input" value={shipmentForm.ship_name || shipmentForm.flight_number || ""} onChange={(e) => setSF({ ship_name: e.target.value, flight_number: e.target.value })} />)}
        {fld("رقم الحركة", <input className="aseel-input" value={shipmentForm.agent_shipment_number || ""} onChange={sfText("agent_shipment_number")} />)}
        {fld("رقم الفاتورة", <input className="aseel-input" readOnly value={shipmentForm.invoice_number || "—"} />)}
        {fld("الحجم / الوزن", <input className="aseel-input" readOnly value={`${fmt(shipmentForm.total_volume)} / ${fmt(shipmentForm.total_weight_kg)}`} />)}
        {fld("المخلِّص", <span style={{ display: "flex", gap: 2 }}>
        <select
          className="aseel-input"
          value={clearanceForm?.customs_broker ?? ""}
          onChange={(e) => {
            const val = e.target.value;
            const v = val && val !== "null" ? Number(val) : null;
            const p = carriers.find((c) => c.id === v);
            if (clearanceForm) {
              const updated = { ...clearanceForm, customs_broker: v, broker_name: p?.name || "" } as ClearanceRow;
              setClearanceForm(updated);
              void handleSaveClearance(updated);
            }
          }}
          disabled={!clearanceForm}
          title={!clearanceForm ? "يجب إنشاء بيان تخليص أولاً (من تبويب التخليص الجمركي)" : ""}
        >
          <option value="">{clearanceForm ? "— بلا مخلِّص —" : "أضف بيان تخليص أولاً"}</option>
          {carriers.filter((c) => c.partner_type === "CustomsBroker").map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
          {clearanceForm?.customs_broker != null && String(clearanceForm.customs_broker) !== "null" &&
            !carriers.some((c) => String(c.id) === String(clearanceForm.customs_broker)) && (
              <option value={clearanceForm.customs_broker}>
                {clearanceForm.broker_name || `#${clearanceForm.customs_broker}`}
              </option>
            )}
        </select>
        <button type="button" className="aseel-ellipsis" title="إضافة مخلِّص جمركي جديد" disabled={!clearanceForm} onClick={() => { setQuickAddType("CustomsBroker"); setQuickAddName(""); }}>+</button>
        </span>)}
        {fld("رقم البيان", <input className="aseel-input" readOnly value={clearance?.declaration_number || "—"} />)}
        {fld("تاريخ التخليص", <input className="aseel-input" type="date" readOnly value={clearance?.clearance_date ? String(clearance.clearance_date).slice(0, 10) : ""} />)}
        {fld("فاتورة المقاصة", <input className="aseel-input" readOnly value={clearance?.settlement_invoice_number || "—"} />)}
        {fld("كشف الضريبة", <input className="aseel-input" readOnly value={clearance?.vat_statement != null ? String(clearance.vat_statement) : "—"} />)}
        {fld("محرَّر", <input className="aseel-input" readOnly value={shipmentForm.editable ? "نعم" : "لا"} />)}
      </>}
      <div className="col-span-full flex justify-end">
        <button type="button" className="aseel-toolbtn" onClick={() => setShowAdvancedShipment((value) => !value)}>
          {showAdvancedShipment ? "إخفاء تفاصيل الشحنة" : "إظهار تفاصيل الشحنة المتقدمة"}
        </button>
      </div>
    </div>
  );

  const dealsContent = (
    <div style={{ padding: "4px 8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600 }}>صفقات هذه الشحنة ({shipmentDeals.length})</h4>
        <span style={{ display: "inline-flex", gap: 4 }}>
          <button type="button" className="aseel-toolbtn" onClick={() => void handleRedistributeAllocations()} disabled={!shipment || saving || shipmentDeals.length === 0} title="توزيع تكلفة الشحن الدولي على الصفقات حسب الحجم/الوزن">⟳ إعادة توزيع الحصص</button>
          <button type="button" className="aseel-toolbtn" onClick={() => void openLinkPicker()} disabled={!shipment || saving}>+ ضمّ صفقة</button>
        </span>
      </div>
      <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)", margin: "0 0 4px" }}>
        كل صف = صفقة شراء مضمومة لهذه الشحنة. «حصة الشحن» = نصيب الصفقة من تكلفة الشحن
        الدولي (يتوزع حسب الوحدة المختارة تلقائياً — عدّله يدوياً أو اضغط «إعادة توزيع الحصص»).
      </p>
      {/* M2: أساس تسعير الشحن — CBM أو KG (اختيار يدوي)؛ التبديل يعيد الحساب كاملاً بلا بقايا */}
      {shipment && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "4px 6px", marginBottom: 4, background: "var(--aseel-bg-strip, #f5f5f5)", borderRadius: 6, fontSize: "var(--aseel-fs-sm, 12px)" }}>
          <b>أساس الشحن:</b>
          <span style={{ display: "inline-flex", border: "1px solid var(--aseel-border)", borderRadius: 6, overflow: "hidden" }}>
            {(["cbm", "kg"] as const).map((u) => (
              <button key={u} type="button" className="aseel-toolbtn"
                onClick={() => { setFreightUnit(u); void handleSetFreight(u, freightRate); }}
                disabled={saving}
                style={{ borderRadius: 0, padding: "2px 12px", background: freightUnit === u ? "var(--aseel-accent, #1857a4)" : "transparent", color: freightUnit === u ? "#fff" : "var(--aseel-ink)" }}>
                {u.toUpperCase()}
              </button>
            ))}
          </span>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            سعر/{freightUnit.toUpperCase()}:
            <input className="aseel-input" type="number" step="0.0001" min="0" style={{ width: 90 }}
              value={freightRate} onChange={(e) => setFreightRate(e.target.value)}
              onBlur={() => void handleSetFreight(freightUnit, freightRate)} disabled={saving} />
          </label>
          <span className="aseel-text-soft">
            الإجمالي = السعر × مجموع {freightUnit.toUpperCase()} ={" "}
            <b>{fmt(shipmentForm?.total_shipping_cost_usd)}</b> USD
          </span>
        </div>
      )}
      {/* تحذير واضح: صفقات بلا حجم/وزن → الشحن ما بيتوزّع حتى تُعبّأ */}
      {shipment && missingMeasureRefs.length > 0 && (
        <div style={{ padding: "6px 10px", marginBottom: 4, borderRadius: 6, fontSize: "var(--aseel-fs-sm, 12px)", background: "var(--aseel-warn-bg, #fdf3e3)", color: "var(--aseel-warn, #8a5a00)", border: "1px solid var(--aseel-warn, #d9a441)" }}>
          ⚠ صفقات بلا {freightUnit === "kg" ? "وزن (KG)" : "حجم (CBM)"}: <b>{missingMeasureRefs.join("، ")}</b>.
          {" "}عبّئ القيمة مباشرة في عمود {freightUnit === "kg" ? "KG" : "CBM"} بالجدول أدناه — يُحفظ في الصفقة
          ويُعاد توزيع الشحن تلقائياً بمجرّد اكتمال كل الصفقات.
        </div>
      )}
      {linkPickerOpen && (
        <div style={{ position: "fixed", inset: 0, zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.3)" }}>
          <div style={{ background: "#fff", borderRadius: 8, padding: 16, maxWidth: 500, width: "90%", maxHeight: "70vh", overflowY: "auto" }}>
            <h4 style={{ fontWeight: 600, marginBottom: 8 }}>اختر صفقة للربط</h4>
            {availableDeals.length === 0 && <p className="aseel-text-soft">لا توجد صفقات متاحة</p>}
            {availableDeals.map((d) => {
              const title = effectiveDealTitleForDisplay({
                description: d.description,
                notes: d.notes,
                original_offer_number: d.original_offer_number,
                ref_number: d.ref_number || d.deal_number,
              });
              const ready = d.shipping_workflow_status === "sw_wait_intl_ship";
              const stageLabel = d.shipping_workflow_status
                ? getShippingWorkflowLabel(d.shipping_workflow_status)
                : "";
              return (
                <div key={d.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid #eee", cursor: "pointer" }}
                  onClick={() => void handleLinkDeal(d.id)}>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: "block", fontWeight: 600 }}>{title}</span>
                    <span className="aseel-text-soft" style={{ fontSize: 11, fontFamily: "monospace" }}>
                      {d.ref_number || d.deal_number || `#${d.id}`}
                      {d.partner_name ? ` · ${d.partner_name}` : ""}
                    </span>
                    {ready ? (
                      <span style={{ marginInlineStart: 6, fontSize: 10, fontWeight: 700, color: "var(--aseel-ok, #267346)", border: "1px solid var(--aseel-ok, #267346)", borderRadius: 8, padding: "0 6px" }}>
                        جاهزة للشحن
                      </span>
                    ) : stageLabel ? (
                      <span className="aseel-text-soft" style={{ marginInlineStart: 6, fontSize: 10 }}>{stageLabel}</span>
                    ) : null}
                  </span>
                  <span className="aseel-toolbtn" style={{ flexShrink: 0 }}>ربط</span>
                </div>
              );
            })}
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
          <th style={{ padding: "2px 4px", textAlign: "center", width: 70 }}>CBM</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 70 }}>KG</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 90 }}>الصفقة</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 110 }}>حصة الشحن (USD)</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 60 }}>إلغاء</th>
        </tr></thead>
        <tbody>
          {shipmentDeals.map((d: ShipmentDealAllocation) => (
            <ShipmentDealAllocationRow
              key={d.id}
              dealId={d.deal}
              dealRef={d.deal_ref}
              dealTitle={d.deal_title}
              dealName={d.deal_name}
              cbm={Number(d.deal_total_cbm ?? 0)}
              kg={Number(d.deal_total_weight_kg ?? 0)}
              allocatedShippingCost={Number(d.allocated_shipping_cost ?? 0)}
              freightUnit={freightUnit}
              busy={savingDealIds.has(d.deal)}
              disabled={saving}
              onUpdateMeasure={handleUpdateDealMeasure}
              onUpdateAllocation={handleUpdateAllocation}
              onUnlink={handleUnlinkDeal}
            />
          ))}
          {shipmentDeals.length === 0 && (
            <tr><td colSpan={7} style={{ padding: "8px 4px", textAlign: "center", color: "#999" }}>لا توجد صفقات مرتبطة</td></tr>
          )}
        </tbody>
      </table>
      {shipmentDeals.length > 0 && (
        <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)", padding: "4px 0" }}>
          مجموع الحصص: <b>{fmt(shipmentDeals.reduce((sum, d) => sum + Number(d.allocated_shipping_cost ?? 0), 0))}</b> USD
          {shipmentForm.total_shipping_cost_usd != null && (
            <> · إجمالي الشحن: <b>{fmt(shipmentForm.total_shipping_cost_usd)}</b></>
          )}
        </p>
      )}
    </div>
  );

  const cfText = (key: keyof ClearanceRow) => (e: React.ChangeEvent<HTMLInputElement>) => setCF({ [key]: e.target.value });

  const clearanceContent = clearanceForm ? (
    <div style={{ padding: "4px 8px" }}>
      <div className="mb-3 grid grid-cols-1 gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 sm:grid-cols-3">
        <div><span className="block text-xs text-[var(--color-text-muted)]">إجمالي الاستحقاق</span><b>{fmt(clearanceCostTotal)} ₪</b></div>
        <div><span className="block text-xs text-[var(--color-text-muted)]">المدفوع للمخلّص</span><b className="text-emerald-700">{fmt(paidClearance)} ₪</b></div>
        <div><span className="block text-xs text-[var(--color-text-muted)]">المتبقي</span><b className="text-amber-700">{fmt(clearanceRemaining)} ₪</b></div>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {!clearanceForm.journal ? (
          <button type="button" className="aseel-toolbtn" onClick={() => void handlePostClearance()} disabled={saving || clearanceCostTotal <= 0}>
            إثبات استحقاق التخليص
          </button>
        ) : (
          <>
            <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">الاستحقاق مرحّل · قيد #{clearanceForm.journal}</span>
            <button type="button" className="aseel-toolbtn" onClick={() => void handleUnpostClearanceAccrual()} disabled={saving}>تراجع عن الاستحقاق</button>
          </>
        )}
        <button
          type="button" className="aseel-toolbtn" onClick={openClearancePayment}
          disabled={saving || !clearanceForm.customs_broker}
          title="دفع للمخلّص من الصندوق بقيد مستقل — يجوز تجاوز المتبقي (يصير دفعة مقدمة)"
        >
          تسجيل دفعة للمخلّص
        </button>
        <span className="text-xs text-[var(--color-text-muted)]">
          {clearanceForm.journal
            ? "الإفراج وإثبات الاستحقاق لا يتطلبان دفع المبلغ كاملاً."
            : "الاستحقاق يُثبَّت تلقائياً عند ترحيل الشحنة إلى فاتورة — أو أثبِته الآن يدوياً."}
        </span>
      </div>
      <div className="aseel-headband" style={{ marginBottom: 4 }}>
        {fld("رقم البيان", <input className="aseel-input" value={clearanceForm.declaration_number || ""} onChange={cfText("declaration_number")} />)}
        {fld("تاريخ التخليص", <input className="aseel-input" type="date" value={clearanceForm.clearance_date ? String(clearanceForm.clearance_date).slice(0, 10) : ""} onChange={cfText("clearance_date")} />)}
        {fld("المخلِّص", <span style={{ display: "flex", gap: 2 }}>
          <select
            className="aseel-input"
            value={clearanceForm.customs_broker ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              const v = val && val !== "null" ? Number(val) : null;
              const p = carriers.find((c) => c.id === v);
              const updated = { ...clearanceForm, customs_broker: v, broker_name: p?.name || "" } as ClearanceRow;
              setCF(updated);
              void handleSaveClearance(updated);
            }}
          >
            <option value="">— بلا مخلِّص —</option>
            {carriers.filter((c) => c.partner_type === "CustomsBroker").map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
            {clearanceForm.customs_broker != null && String(clearanceForm.customs_broker) !== "null" &&
              !carriers.some((c) => String(c.id) === String(clearanceForm.customs_broker)) && (
                <option value={clearanceForm.customs_broker}>
                  {clearanceForm.broker_name || `#${clearanceForm.customs_broker}`}
                </option>
              )}
          </select>
          <button type="button" className="aseel-ellipsis" title="إضافة مخلِّص جمركي جديد" onClick={() => { setQuickAddType("CustomsBroker"); setQuickAddName(""); }}>+</button>
        </span>)}
        {showAdvancedClearance && <>
          {fld("الوقت", <input className="aseel-input" type="time" value={clearanceForm.transaction_time ? String(clearanceForm.transaction_time).slice(0, 5) : ""} onChange={cfText("transaction_time")} />)}
          {fld("تاريخ ثاني", <input className="aseel-input" type="date" value={clearanceForm.second_date ? String(clearanceForm.second_date).slice(0, 10) : ""} onChange={cfText("second_date")} />)}
          {fld("مشتغل مرخص", <input className="aseel-input" value={clearanceForm.licensed_dealer_no || ""} onChange={cfText("licensed_dealer_no")} />)}
          {fld("رقم فاتورة المقاصة", <input className="aseel-input" value={clearanceForm.settlement_invoice_number || ""} onChange={cfText("settlement_invoice_number")} />)}
          {fld("العملة", <input className="aseel-input" value={clearanceForm.currency != null ? String(clearanceForm.currency) : ""} onChange={(e) => setCF({ currency: e.target.value ? Number(e.target.value) : null })} />)}
          {fld("سعر العملة", <input className="aseel-input" type="number" step="0.000001" value={clearanceForm.exchange_rate != null ? String(clearanceForm.exchange_rate) : ""} onChange={(e) => setCF({ exchange_rate: e.target.value ? Number(e.target.value) : null })} />)}
          {fld("مجموع بدون ضريبة", <input className="aseel-input" type="number" step="0.01" value={clearanceForm.subtotal_no_vat != null ? String(clearanceForm.subtotal_no_vat) : ""} onChange={(e) => setCF({ subtotal_no_vat: e.target.value ? Number(e.target.value) : null })} />)}
          {fld("مجموع الضريبة", <input className="aseel-input" type="number" step="0.01" value={clearanceForm.vat_total != null ? String(clearanceForm.vat_total) : ""} onChange={(e) => setCF({ vat_total: e.target.value ? Number(e.target.value) : null })} />)}
          {fld("الإجمالي", <input className="aseel-input" type="number" step="0.01" value={clearanceForm.grand_total != null ? String(clearanceForm.grand_total) : ""} onChange={(e) => setCF({ grand_total: e.target.value ? Number(e.target.value) : null })} />)}
        </>}
      </div>
      <div className="mb-2 flex justify-end">
        <button type="button" className="aseel-toolbtn" onClick={() => setShowAdvancedClearance((value) => !value)}>
          {showAdvancedClearance ? "إخفاء تفاصيل البيان" : "إظهار تفاصيل البيان المتقدمة"}
        </button>
      </div>
      {/* تسجيل سريع: إجمالي واحد بدون بنود مفصّلة — يُخزَّن كبند وحيد كي يدخل في
          توزيع التكلفة (حقل «الإجمالي» أعلاه للعرض ولا يُوزَّع على الفواتير) */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", margin: "0 0 8px", padding: "6px 8px", border: "1px dashed var(--aseel-border, #bbb)", borderRadius: 6, fontSize: "var(--aseel-fs-sm, 12px)" }}>
        <b>تسجيل سريع:</b>
        <span>عندك إجمالي واحد بدون تفاصيل؟</span>
        <input
          className="aseel-input"
          type="number"
          step="0.01"
          placeholder="تكلفة التخليص الإجمالية ₪"
          style={{ width: 180 }}
          value={quickClearanceTotal}
          onChange={(e) => setQuickClearanceTotal(e.target.value)}
        />
        <button
          type="button"
          className="aseel-toolbtn"
          onClick={() => void applyQuickClearanceTotal()}
          disabled={saving || !quickClearanceTotal || Number(quickClearanceTotal) <= 0}
        >
          اعتماد وحفظ
        </button>
        <span className="aseel-text-soft">
          يُسجَّل كبند واحد «تكلفة التخليص (إجمالي)» — أو فصّل بالبنود أدناه.
        </span>
      </div>
      {/* بنود التكلفة ببساطة: بند + مبلغ. مدين/دائن شأن القيد المحاسبي الداخلي لا المستخدم
          (شكوى المالك: «شو هاد دائن ومدين — كان بنود») — المبلغ يُخزَّن debit والخادم يحوّله. */}
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-xs">
        <span>
          {clearanceForm.lines?.length
            ? `${clearanceForm.lines.length} بند تفصيلي · المجموع ${fmt(clearanceCostTotal)} ₪`
            : "لا توجد بنود تفصيلية — استخدم الإجمالي السريع أو أضف بنوداً"}
        </span>
        <button type="button" className="aseel-toolbtn" onClick={() => setShowClearanceBreakdown((value) => !value)}>
          {showClearanceBreakdown ? "إخفاء تفصيل الرسوم" : "تفصيل الرسوم والبنود"}
        </button>
      </div>
      {showClearanceBreakdown && <>
      <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)", tableLayout: "fixed" }}>
        <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
          <th style={{ padding: "2px 4px", textAlign: "start", width: 130 }}>النوع</th>
          <th style={{ padding: "2px 4px", textAlign: "start" }}>البيان</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 120 }}>المبلغ (₪)</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 40 }}>حذف</th>
        </tr></thead>
        <tbody>
          {(clearanceForm.lines || []).map((l, i) => (
            <tr key={l.id ?? i}>
              <td style={{ padding: "2px 4px" }}>
                <select
                  className="aseel-input"
                  value={l.line_type}
                  onChange={(e) => {
                    const nextType = e.target.value;
                    // بند بلا بيان بعد: اقترح اسماً افتراضياً من النوع (يبقى قابلاً للتعديل).
                    const nextDescription = l.description.trim()
                      ? l.description
                      : (CLEARANCE_LINE_TYPE_LABELS[nextType] || l.description);
                    updateClearanceLine(i, { line_type: nextType, description: nextDescription });
                  }}
                >
                  <option value="vat">ضريبة القيمة المضافة</option>
                  <option value="declaration_fee">رسوم البيان</option>
                  <option value="terminal">محطة الشحن</option>
                  <option value="permits">تصاريح</option>
                  <option value="broker_commission">عمولة المخلص</option>
                  <option value="customs_system">نظام الجمارك</option>
                  <option value="شحن محلي">شحن محلي</option>
                  <option value="other">أخرى</option>
                </select>
              </td>
              <td style={{ padding: "2px 4px" }}>
                <input className="aseel-input" value={l.description} onChange={(e) => updateClearanceLine(i, { description: e.target.value })} style={{ width: "100%" }} />
              </td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <input
                  className="aseel-input"
                  type="number"
                  step="0.01"
                  value={String((Number(l.debit) || 0) - (Number(l.credit) || 0))}
                  onChange={(e) => updateClearanceLine(i, { debit: Number(e.target.value) || 0, credit: 0 })}
                  style={{ width: 105, textAlign: "center" }}
                />
              </td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <button type="button" className="aseel-toolbtn" onClick={() => deleteClearanceLine(i)} style={{ color: "var(--aseel-danger, #c0392b)", padding: "0 4px" }}>✕</button>
              </td>
            </tr>
          ))}
          {(!clearanceForm.lines || clearanceForm.lines.length === 0) && (
            <tr><td colSpan={4} style={{ padding: "8px 4px", textAlign: "center", color: "#999" }}>لا توجد بنود تخليص</td></tr>
          )}
        </tbody>
      </table>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "4px 0", fontSize: "var(--aseel-fs-sm, 12px)" }}>
        <span>
          مجموع البنود:{" "}
          <b style={{ fontFamily: "monospace" }}>
            {fmt((clearanceForm.lines || []).reduce((sum, l) => sum + ((Number(l.debit) || 0) - (Number(l.credit) || 0)), 0))}
          </b>{" "}₪
        </span>
        <button
          type="button"
          className="aseel-toolbtn"
          style={{ fontSize: "11px" }}
          onClick={() => setCF({
            grand_total: (clearanceForm.lines || []).reduce(
              (sum, l) => sum + ((Number(l.debit) || 0) - (Number(l.credit) || 0)), 0,
            ),
          })}
          title="ينسخ مجموع البنود إلى حقل «الإجمالي» أعلاه"
        >
          اعتماده كـ«الإجمالي»
        </button>
        <span className="aseel-text-soft">
          هذه البنود هي «تكلفة التخليص» التي تتوزع على فواتير الصفقات عند الاستيراد.
        </span>
      </div>
      {(clearanceForm.lines || []).some((l) => isLocalShippingClearanceLabel(l.description)) && (
        <p style={{ fontSize: "var(--aseel-fs-sm, 12px)", padding: "4px 6px", margin: "4px 0", borderRadius: 4, background: "var(--aseel-warn-bg, #fdf3e0)", color: "var(--aseel-warn, #b45309)", border: "1px solid var(--aseel-warn, #b45309)" }}>
          يوجد بند «شحن محلي» ضمن بنود التخليص — هذا مسار قديم. المكان الموحّد لتسجيل النقل
          المحلي هو تبويب «النقل المحلي» (ناقل + مبلغ + ترحيل أو نقل للفاتورة). عند وجود نقل
          محلي مرحّل ومُرسمَل للمخزون تُستبعد هذه البنود تلقائياً من تكلفة الاستيراد لمنع الازدواج.
        </p>
      )}
      </>}
      <div style={{ display: "flex", gap: 8, padding: "4px 0" }}>
        {showClearanceBreakdown && <button type="button" className="aseel-toolbtn" onClick={addClearanceLine}>+ إضافة بند</button>}
        <button type="button" className="aseel-toolbtn" onClick={() => void handleSaveClearance()} disabled={saving}>تخزين التخليص</button>
      </div>
    </div>
  ) : (
    <div style={{ padding: "8px", textAlign: "center" }}>
      <p className="aseel-text-soft" style={{ marginBottom: 8 }}>لا يوجد سجل تخليص لهذه الشحنة</p>
      <button type="button" className="aseel-toolbtn" onClick={() => void handleCreateClearance()} disabled={saving || !shipment}>إنشاء سجل تخليص</button>
    </div>
  );

  const localContent = (
    <div style={{ padding: "4px 8px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600 }}>الشحنات المحلية ({localShipments.length})</h4>
        <button type="button" className="aseel-toolbtn" onClick={handleNewLocal} disabled={!shipment || saving}><Plus size={14} /> إضافة نقل محلي</button>
      </div>
      <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)" }}>
        <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
          <th style={{ padding: "2px 4px", textAlign: "start" }}>رقم</th>
          <th style={{ padding: "2px 4px", textAlign: "start" }}>الناقل</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>المبلغ</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>المدفوع</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>المتبقي</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 60 }}>الحالة</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 50 }}>مرحَّلة</th>
          <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}></th>
        </tr></thead>
        <tbody>
          {localShipments.map((ls) => (
            <tr key={ls.id} onClick={() => handleEditLocal(ls)} style={{ cursor: "pointer" }}>
              <td style={{ padding: "2px 4px" }}>{ls.shipment_number}</td>
              <td style={{ padding: "2px 4px" }}>{ls.carrier_name || "—"}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{fmt(ls.amount)}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{fmt(ls.amount_paid || 0)}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{fmt(ls.remaining_balance ?? ls.amount)}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{ls.status || "—"}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>{ls.is_posted ? "✓" : "—"}</td>
              <td style={{ padding: "2px 4px", textAlign: "center" }}>
                <span style={{ display: "inline-flex", gap: 4 }}>
                  {!ls.is_posted && (
                    <button type="button" className="aseel-toolbtn" onClick={(e) => { e.stopPropagation(); void handlePostLocal(ls.id); }} disabled={saving} style={{ fontSize: "11px", backgroundColor: "var(--aseel-primary)", color: "white", padding: "2px 6px" }} title="مدين تكلفة نقل محلي / دائن ذمم الناقل.">إثبات الاستحقاق</button>
                  )}
                  <button type="button" className="aseel-toolbtn" onClick={(e) => { e.stopPropagation(); openLocalPayment(ls); }} disabled={saving} style={{ fontSize: "11px" }} title="دفع للناقل من الصندوق بقيد مستقل — يجوز تجاوز المتبقي (يصير دفعة مقدمة)">تسجيل دفعة</button>
                  {ls.is_posted && (
                    <button type="button" className="aseel-toolbtn" onClick={(e) => { e.stopPropagation(); void handleUnpostLocal(ls.id); }} disabled={saving} style={{ fontSize: "11px" }} title="يحذف قيد المصروف ويعيد السجل مسودة">تراجع عن الترحيل</button>
                  )}
                </span>
              </td>
            </tr>
          ))}
          {localShipments.length === 0 && (
            <tr><td colSpan={8} style={{ padding: "8px 4px", textAlign: "center", color: "#999" }}>لا توجد شحنات محلية</td></tr>
          )}
        </tbody>
      </table>
      {localShipments.some((l) => !l.is_posted) && (
        <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)", padding: "4px 0" }}>
          الاستحقاق («ارسالية») يُثبَّت تلقائياً عند ترحيل الشحنة إلى فاتورة فيصير الناقل دائناً — أو أثبِته الآن يدوياً. «تسجيل دفعة» يخصم من ذممه بقيد منفصل.
        </p>
      )}
      {payingLocalId && (
        <div className="my-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
          <h5 className="mb-2 text-sm font-semibold">تسجيل دفعة للناقل · نقل #{payingLocalId}</h5>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
            {fld("المبلغ", <input className="aseel-input" type="number" step="0.01" value={localPayAmount} onChange={(e) => setLocalPayAmount(e.target.value)} />)}
            {fld("الصندوق", <select className="aseel-input" value={payCashBoxId} onChange={(e) => setPayCashBoxId(e.target.value)}><option value="">— اختر —</option>{cashBoxes.map((box) => <option key={box.external_id} value={box.external_id}>{box.name} ({box.currency_code})</option>)}</select>)}
            {fld("التاريخ", <input className="aseel-input" type="date" value={localPayDate} onChange={(e) => setLocalPayDate(e.target.value)} />)}
            {fld("ملاحظات", <input className="aseel-input" value={localPayNotes} onChange={(e) => setLocalPayNotes(e.target.value)} />)}
          </div>
          <div className="mt-2 flex gap-2">
            <button type="button" className="aseel-toolbtn" onClick={() => void handlePayLocal()} disabled={saving || !payCashBoxId || Number(localPayAmount) <= 0}>تأكيد الدفعة</button>
            <button type="button" className="aseel-toolbtn" onClick={() => setPayingLocalId(null)}>إلغاء</button>
          </div>
        </div>
      )}
      {localForm && (
        <div style={{ marginTop: 8, border: "1px solid var(--aseel-border, #ddd)", padding: 8, borderRadius: 4 }}>
          <h5 style={{ fontWeight: 600, marginBottom: 4, fontSize: "var(--aseel-fs-sm, 12px)" }}>
            {editingLocalId && editingLocalId > 0 ? `تعديل النقل المحلي #${editingLocalId}` : "إضافة نقل محلي جديد"}
          </h5>
          <div className="mb-1 grid grid-cols-1 gap-x-2 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
            {fld("الناقل", carriers.length > 0 ? (
              <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <select className="aseel-input" value={localForm.carrier ? String(localForm.carrier) : ""} onChange={(e) => setLF({ carrier: Number(e.target.value) || 0 })}>
                  <option value="">— اختر الناقل المحلي —</option>
                  {carriers.filter((c) => c.partner_type === "LocalTransporter").map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                  {/* الناقل المحفوظ سابقاً قد يكون من نوع مختلف (بيانات قديمة) — أبقِه ظاهراً كي لا يُفقَد. */}
                  {localForm.carrier &&
                    !carriers.some((c) => c.partner_type === "LocalTransporter" && c.id === localForm.carrier) &&
                    carriers.some((c) => c.id === localForm.carrier) && (
                      <option value={String(localForm.carrier)}>
                        {carriers.find((c) => c.id === localForm.carrier)?.name}
                      </option>
                    )}
                </select>
                <button type="button" className="aseel-ellipsis" title="إضافة ناقل محلي جديد" onClick={() => { setQuickAddType("LocalTransporter"); setQuickAddName(""); }}>+</button>
              </span>
            ) : (
              <input className="aseel-input" type="number" placeholder="رقم الناقل (لم تُحمَّل قائمة الشركاء)" value={localForm.carrier ?? ""} onChange={(e) => setLF({ carrier: Number(e.target.value) })} />
            ))}
            {fld("إلى", <input className="aseel-input" value={localForm.destination || ""} onChange={(e) => setLF({ destination: e.target.value })} />)}
            {fld("تاريخ التسليم", <input className="aseel-input" type="date" value={localForm.delivery_date ? String(localForm.delivery_date).slice(0, 10) : ""} onChange={(e) => setLF({ delivery_date: e.target.value })} />)}
            {fld("المبلغ", <input className="aseel-input" type="number" step="0.01" value={localForm.amount ? String(localForm.amount) : "0"} onChange={(e) => setLF({ amount: e.target.value })} />)}
            {showAdvancedLocal && <>
              {fld("السائق", <input className="aseel-input" value={localForm.driver_name || ""} onChange={(e) => setLF({ driver_name: e.target.value })} />)}
              {fld("المركبة", <input className="aseel-input" value={localForm.vehicle_number || ""} onChange={(e) => setLF({ vehicle_number: e.target.value })} />)}
              {fld("من", <input className="aseel-input" value={localForm.origin || ""} onChange={(e) => setLF({ origin: e.target.value })} />)}
              {fld("تاريخ التحميل", <input className="aseel-input" type="date" value={localForm.pickup_date ? String(localForm.pickup_date).slice(0, 10) : ""} onChange={(e) => setLF({ pickup_date: e.target.value })} />)}
              {fld("الحالة", <select className="aseel-input" value={localForm.status || "pending"} onChange={(e) => setLF({ status: e.target.value as LocalShipmentRow["status"] })}>
                <option value="pending">قيد الانتظار</option>
                <option value="in_transit">قيد النقل</option>
                <option value="delivered">تم التسليم</option>
                <option value="cancelled">ملغي</option>
              </select>)}
              {fld("ملاحظات", <input className="aseel-input" value={localForm.notes || ""} onChange={(e) => setLF({ notes: e.target.value })} />)}
            </>}
          </div>
          <button type="button" className="aseel-toolbtn" onClick={() => setShowAdvancedLocal((value) => !value)}>
            {showAdvancedLocal ? "إخفاء تفاصيل النقل" : "إضافة تفاصيل السائق والمركبة"}
          </button>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <button type="button" className="aseel-toolbtn" onClick={() => void handleSaveLocal()} disabled={saving}>
              {editingLocalId && editingLocalId > 0 ? "تحديث" : "إضافة"}
            </button>
            <button type="button" className="aseel-toolbtn" onClick={handleCancelLocal}>إلغاء</button>
            {editingLocalId && editingLocalId > 0 && (
              <button type="button" className="aseel-toolbtn" onClick={() => void handleDeleteLocal(editingLocalId)} disabled={saving} style={{ color: "var(--aseel-danger, #c0392b)" }}>حذف</button>
            )}
          </div>
        </div>
      )}
    </div>
  );

  /* ذمم أطراف الاستيراد الثلاثة بلغة واحدة (مستحق ← مدفوع ← متبقٍ). المصادر
     هي نفسها التي تغذّي الجداول أدناه — بلا حساب موازٍ ينحرف عنها. */
  const localDueTotal = localShipments.reduce((sum, row) => sum + Number(row.amount || 0), 0);
  const localPaidTotal = localShipments.reduce((sum, row) => sum + Number(row.amount_paid || 0), 0);
  const importPartyDues: ImportPartyDue[] = [
    {
      key: "freight",
      role: "وكيل الشحن الدولي",
      party: s.agent_name || null,
      symbol: "$",
      due: freightTotalUsd,
      paid: freightPaidUsd,
      accrued: freightCostEstablished,
      note: freightTotalUsd <= 0
        ? "لا تكلفة شحن على هذه الشحنة."
        : freightAccrued
          ? `سعر الاستحقاق ${fmt(Number(s.freight_exchange_rate) || 0)} ₪/$ هو الذي يحكم التكلفة.`
          : "أثبت الاستحقاق بسعر الصرف — الدفع لاحقاً ولا يشترطه الاستيراد.",
      accrueLabel: "أثبت استحقاق الشحن",
      onAccrue: freightTotalUsd > 0 ? () => void handlePostFreightAccrual() : undefined,
      onPay: freightTotalUsd > 0
        ? () => {
            setShowAgentPayForm(true);
            const remaining = Math.max(0, freightTotalUsd - freightPaidUsd);
            setAgentPayAmount(remaining > 0 ? String(Math.round(remaining * 100) / 100) : "");
          }
        : undefined,
    },
    ...(clearance ? [{
      key: "broker",
      role: "المخلّص الجمركي",
      party: clearanceForm?.broker_name || null,
      symbol: "₪",
      due: clearanceCostTotal,
      paid: paidClearance,
      accrued: Boolean(clearanceForm?.journal),
      note: clearanceCostTotal <= 0 ? "أدخل تكلفة التخليص أولاً." : undefined,
      accrueLabel: "أثبت استحقاق التخليص",
      onAccrue: clearanceCostTotal > 0 ? () => void handlePostClearance() : undefined,
      onPay: clearanceForm?.customs_broker ? openClearancePayment : undefined,
    } as ImportPartyDue] : []),
    ...(localShipments.length > 0 ? [{
      key: "carrier",
      role: "الناقل المحلي",
      party: localShipments.map((row) => row.carrier_name).filter(Boolean).join("، ") || null,
      symbol: "₪",
      due: localDueTotal,
      paid: localPaidTotal,
      accrued: localShipments.every((row) => row.is_posted),
      note: "التكلفة تدخل حصص الفواتير، والدفع للناقل يبقى مستقلاً.",
      payLabel: "إدارة النقل والدفعات",
      onPay: () => setActiveTab("local"),
    } as ImportPartyDue] : []),
  ];

  const paymentsContent = (
    <div style={{ padding: "4px 8px" }}>
      {/* ملخّص واحد لأطراف الاستيراد الثلاثة — كان المستخدم يجمعه من تبويبين */}
      <ImportPartyDuesPanel busy={saving} parties={importPartyDues} />

      {/* ── ٠) استحقاق شحن الوكيل — منفصل عن الدفع، وهو ما يثبّت التكلفة ── */}
      <div style={{ marginBottom: 10, border: "1px solid var(--aseel-border, #ddd)", borderRadius: 4, padding: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600 }}>
            استحقاق شحن الوكيل — يجعله دائناً (مستقل عن الدفع)
          </h4>
          {freightAccrued && (
            <span style={{ color: "var(--aseel-ok, #267346)", fontWeight: 700, fontSize: "var(--aseel-fs-sm, 12px)" }}>
              ✓ مُستحق بسعر {fmt(Number(s.freight_exchange_rate) || 0)} ₪/$
            </span>
          )}
        </div>
        {freightTotalUsd <= 0 ? (
          <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)" }}>
            تكلفة الشحن صفر — لا استحقاق ولا دفعة، والاستيراد متاح مباشرة.
          </p>
        ) : (
          <>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              {fld("سعر الصرف (₪/$)", (
                <input
                  className="aseel-input" type="number" step="0.001"
                  value={freightAccrualRate}
                  disabled={freightAccrued}
                  onChange={(e) => setFreightAccrualRate(e.target.value)}
                />
              ))}
              <span style={{ fontSize: "var(--aseel-fs-sm, 12px)" }}>
                الاستحقاق:{" "}
                <b style={{ fontFamily: "monospace" }}>
                  {fmt(freightTotalUsd * (Number(freightAccrualRate) || 0))} ₪
                </b>{" "}
                (${fmt(freightTotalUsd)})
              </span>
              {freightAccrued ? (
                <button type="button" className="aseel-toolbtn" disabled={saving} onClick={() => void handleUnpostFreightAccrual()}>
                  تراجع عن الاستحقاق
                </button>
              ) : (
                <button
                  type="button" className="aseel-toolbtn"
                  disabled={saving || !(Number(freightAccrualRate) > 0)}
                  onClick={() => void handlePostFreightAccrual()}
                >
                  ترحيل الاستحقاق
                </button>
              )}
            </div>
            <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)", marginTop: 4 }}>
              مدين «مصاريف الشحن الدولي» / دائن «ذمم الوكيل». هذا السعر هو الذي يحكم تكلفة الشحن
              بالشيكل في تكلفة الاستيراد — بلا حاجة لأي دفعة. ادفع للوكيل لاحقاً متى شئت.
            </p>
          </>
        )}
      </div>

      {/* ── ١) دفعات وكيل الشحن الدولي (USD) — سداد الذمّة، لا شرط للاستيراد ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600 }}>
          دفعات وكيل الشحن — الشحن الدولي بالدولار ({agentPayments.length})
        </h4>
        <button
          type="button"
          className="aseel-toolbtn"
          onClick={() => {
            const opening = !showAgentPayForm;
            setShowAgentPayForm(opening);
            if (opening) {
              const remaining = Math.max(0, freightTotalUsd - freightPaidUsd);
              setAgentPayAmount(remaining > 0 ? String(Math.round(remaining * 100) / 100) : "");
            }
          }}
          disabled={!shipment || saving}
        >
          <Plus size={14} /> دفعة شحن دولي
        </button>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, fontSize: "var(--aseel-fs-sm, 12px)" }}>
        <span>
          مدفوع ومؤكّد: <b style={{ fontFamily: "monospace" }}>${fmt(freightPaidUsd)}</b>
          {" من "}
          <b style={{ fontFamily: "monospace" }}>${fmt(freightTotalUsd)}</b>
        </span>
        {freightTotalUsd > 0 && (
          freightAgentAdvanceUsd > 0 ? (
            // الدفع الزائد واقعة صحيحة: الوكيل يصبح مديناً لنا بالفائض.
            <span style={{ color: "var(--aseel-ok, #267346)", fontWeight: 700 }}>
              ✓ مسدَّد بالكامل · دفعة مقدمة لدى الوكيل ${fmt(freightAgentAdvanceUsd)} (رصيد لصالحنا)
            </span>
          ) : freightFullyPaid ? (
            <span style={{ color: "var(--aseel-ok, #267346)", fontWeight: 700 }}>✓ مسدَّد بالكامل</span>
          ) : (
            <span className="aseel-text-soft">
              متبقٍ للوكيل ${fmt(freightTotalUsd - freightPaidUsd)} — الدفع اختياري ولا يعطّل الاستيراد
            </span>
          )
        )}
        {freightTotalUsd <= 0 && (
          <span className="aseel-text-soft">حدّد «تكلفة الشحن» في بيانات الشحنة أولاً</span>
        )}
      </div>
      {showAgentPayForm && (
        <div style={{ marginBottom: 8, border: "1px solid var(--aseel-border, #ddd)", padding: 8, borderRadius: 4 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "2px 8px", marginBottom: 4 }}>
            {fld("المبلغ (USD)", <input className="aseel-input" type="number" step="0.01" value={agentPayAmount} onChange={(e) => setAgentPayAmount(e.target.value)} />)}
            {fld("سعر الصرف (₪/$)", <input className="aseel-input" type="number" step="0.001" value={agentPayRate} onChange={(e) => setAgentPayRate(e.target.value)} />)}
            {fld("تاريخ التحويل", <input className="aseel-input" type="date" value={agentPayDate} onChange={(e) => setAgentPayDate(e.target.value)} />)}
            {fld("ملاحظات", <input className="aseel-input" value={agentPayNotes} onChange={(e) => setAgentPayNotes(e.target.value)} />)}
            <label className="aseel-field" style={{ justifyContent: "end" }}>
              <span className="aseel-field-label">مؤكّدة (دُفعت فعلاً)</span>
              <input type="checkbox" checked={agentPayConfirmed} onChange={(e) => setAgentPayConfirmed(e.target.checked)} style={{ width: 16, height: 16 }} />
            </label>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" className="aseel-toolbtn" onClick={() => void handleAddAgentPayment()} disabled={saving || !agentPayAmount || Number(agentPayAmount) <= 0}>تسجيل دفعة الشحن</button>
            <button type="button" className="aseel-toolbtn" onClick={() => setShowAgentPayForm(false)}>إلغاء</button>
          </div>
          <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)", marginTop: 4 }}>
            الدفع للوكيل مستقل عن الاستحقاق ولا يشترطه الاستيراد. يجوز الدفع بأكثر من تكلفة الشحن — الفائض دفعة مقدمة تُسوّى على شحنة لاحقة.
          </p>
        </div>
      )}
      {agentPayments.length > 0 && (
        <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)", marginBottom: 10 }}>
          <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
            <th style={{ padding: "2px 4px", textAlign: "start", width: 40 }}>#</th>
            <th style={{ padding: "2px 4px", textAlign: "start" }}>التاريخ</th>
            <th style={{ padding: "2px 4px", textAlign: "center", width: 90 }}>المبلغ $</th>
            <th style={{ padding: "2px 4px", textAlign: "center", width: 70 }}>الصرف</th>
            <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>الحالة</th>
            <th style={{ padding: "2px 4px", textAlign: "center", width: 70 }}>القيد</th>
          </tr></thead>
          <tbody>
            {agentPayments.map((p, idx) => (
              <tr key={p.id ?? idx}>
                <td style={{ padding: "2px 4px", fontFamily: "monospace" }}>{p.payment_number ?? idx + 1}</td>
                <td style={{ padding: "2px 4px" }}>{p.transfer_date ? String(p.transfer_date).slice(0, 10) : "—"}</td>
                <td style={{ padding: "2px 4px", textAlign: "center", fontFamily: "monospace" }}>{fmt(p.amount)}</td>
                <td style={{ padding: "2px 4px", textAlign: "center", fontFamily: "monospace" }}>{fmt(p.usd_to_ils)}</td>
                <td style={{ padding: "2px 4px", textAlign: "center" }}>
                  {isAgentPaymentSettled(p)
                    ? <span style={{ color: "var(--aseel-ok, #267346)", fontWeight: 600 }}>مؤكّدة</span>
                    : <span style={{ color: "var(--aseel-warn, #b45309)" }}>معلّقة</span>}
                </td>
                <td style={{ padding: "2px 4px", textAlign: "center" }}>{p.journal ? `#${p.journal}` : p.is_posted ? "✓" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {localShipments.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border aseel-border-soft bg-[var(--color-surface-2)] px-3 py-2 text-xs">
          <div className="flex flex-wrap gap-4">
            <span>استحقاق النقل المحلي: <b>{fmt(localShipments.reduce((sum, row) => sum + Number(row.amount || 0), 0))} ₪</b></span>
            <span>المدفوع للناقل: <b className="text-emerald-700">{fmt(localShipments.reduce((sum, row) => sum + Number(row.amount_paid || 0), 0))} ₪</b></span>
            <span>المتبقي للناقل: <b className="text-amber-700">{fmt(localShipments.reduce((sum, row) => sum + Number(row.remaining_balance ?? row.amount ?? 0), 0))} ₪</b></span>
          </div>
          <div className="flex items-center gap-2">
            <span className="aseel-text-soft">التكلفة تدخل حصص الفواتير، أمّا الدفع للناقل فيبقى مستقلاً.</span>
            <button type="button" className="aseel-toolbtn" onClick={() => setActiveTab("local")}>إدارة دفعات النقل</button>
          </div>
        </div>
      )}

      {/* ── ٢) دفعات التخليص (من الصندوق) ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, borderTop: "1px solid var(--aseel-border, #ddd)", paddingTop: 8 }}>
        <h4 style={{ fontSize: "var(--aseel-fs-sm, 12px)", fontWeight: 600 }}>دفعات المخلّص ({clearancePayments.length})</h4>
        {clearance && <button type="button" className="aseel-toolbtn" onClick={openClearancePayment} disabled={saving}><Plus size={14} /> تسجيل دفعة للمخلّص</button>}
      </div>
      {clearance && (
        <div className="mb-2 flex flex-wrap gap-4 rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-xs">
          <span>إجمالي الاستحقاق: <b>{fmt(clearanceCostTotal)} ₪</b></span>
          <span>المدفوع: <b className="text-emerald-700">{fmt(paidClearance)} ₪</b></span>
          {/* الفائض عن الاستحقاق دفعة مقدمة: المخلّص يصير مديناً لنا، فنعرضه
              صراحةً بدل «متبقي 0» الذي يخفي أن له رصيداً عندنا. */}
          {clearanceAdvance > 0 ? (
            <span>دفعة مقدمة لدى المخلّص: <b className="text-sky-700">{fmt(clearanceAdvance)} ₪</b></span>
          ) : (
            <span>المتبقي: <b className="text-amber-700">{fmt(clearanceRemaining)} ₪</b></span>
          )}
          <span className="text-[var(--color-text-muted)]">الدفع لا يغيّر مرحلة الإفراج ولا يشترط لإصدار الفاتورة الدولية.</span>
        </div>
      )}
      {showPaymentForm && (
        <div style={{ marginBottom: 8, border: "1px solid var(--aseel-border, #ddd)", padding: 8, borderRadius: 4 }}>
          <div className="mb-1 grid grid-cols-1 gap-x-2 gap-y-1 sm:grid-cols-2 lg:grid-cols-4">
            {/* بلا max: الدفع الزائد مسموح ويصبح دفعة مقدمة — المخلّص يصير مديناً
                لنا بالفائض (قرار المالك). كان الحقل والزر يمنعانه رغم قبول الخادم. */}
            {fld(`المبلغ (المتبقي ${fmt(clearanceRemaining)} ₪)`, <input className="aseel-input" type="number" step="0.01" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} />)}
            {fld("الصندوق", <select className="aseel-input" value={payCashBoxId} onChange={(e) => setPayCashBoxId(e.target.value)}>
              <option value="">— اختر —</option>
              {cashBoxes.map((cb) => (
                <option key={cb.external_id} value={cb.external_id}>{cb.name} ({cb.currency_code})</option>
              ))}
            </select>)}
            {fld("التاريخ", <input className="aseel-input" type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} />)}
            {fld("ملاحظات", <input className="aseel-input" value={payNotes} onChange={(e) => setPayNotes(e.target.value)} />)}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <OfflineGuard
              action="تسجيل دفعة تخليص"
              warningMessage="تسجيل الدفعة يتطلب اتصالاً — يُولَّد قيد محاسبي على الـserver"
            >
              <button type="button" className="aseel-toolbtn" onClick={() => void handleAddPayment()} disabled={saving || !payAmount || Number(payAmount) <= 0 || !payCashBoxId}>تأكيد دفعة المخلّص</button>
            </OfflineGuard>
            <button type="button" className="aseel-toolbtn" onClick={() => setShowPaymentForm(false)}>إلغاء</button>
          </div>
          {cashBoxes.length === 0 && (
            <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm, 12px)", marginTop: 4, color: "var(--aseel-warn, #b45309)" }}>
              لا يوجد صندوق مَربوط بحساب محاسبي — افتح «المحاسبة → ربط صناديق Firestore» قبل تسجيل دفعة.
            </p>
          )}
        </div>
      )}
      {clearancePayments.length > 0 ? (
        <table className="aseel-input" style={{ width: "100%", fontSize: "var(--aseel-fs-sm, 12px)" }}>
          <thead><tr style={{ background: "var(--aseel-bg-strip, #f5f5f5)", fontWeight: 600 }}>
            <th style={{ padding: "2px 4px", textAlign: "start" }}>التاريخ</th>
            <th style={{ padding: "2px 4px", textAlign: "start" }}>الغرض</th>
            <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>المبلغ</th>
            <th style={{ padding: "2px 4px", textAlign: "center", width: 60 }}>مرحَّلة</th>
            <th style={{ padding: "2px 4px", textAlign: "center", width: 80 }}>القيد</th>
          </tr></thead>
          <tbody>
            {clearancePayments.map((p) => (
              <tr key={p.id}>
                <td style={{ padding: "2px 4px" }}>{formatDateLocalized(p.payment_date) || "—"}</td>
                <td style={{ padding: "2px 4px" }}>{p.payment_purpose || "—"}</td>
                <td style={{ padding: "2px 4px", textAlign: "center" }}>{fmt(p.amount)}</td>
                <td style={{ padding: "2px 4px", textAlign: "center" }}>{p.is_posted ? "✓" : "—"}</td>
                <td style={{ padding: "2px 4px", textAlign: "center" }}>{p.journal ? `#${p.journal}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="aseel-text-soft" style={{ padding: 8 }}>لا توجد دفعات</p>}
    </div>
  );

  const accountsContent = (
    <div style={{ padding: "4px 8px", fontSize: "var(--aseel-fs-sm, 12px)" }}>
      <div className="aseel-total-row"><span>قيد التحويل (الشحنة):</span><span><b>{s.transit_journal ? `#${s.transit_journal}` : "—"}</b></span></div>
      <div className="aseel-total-row"><span>قيد استحقاق التخليص:</span><span><b>{clearance?.journal ? `#${clearance.journal}` : "—"}</b></span></div>
      <div className="aseel-total-row"><span>كشف الضريبة:</span><span><b>{clearance?.vat_statement ?? "—"}</b></span></div>
      {/* إجراءات التراجع عن الترحيل — نفس نمط فاتورة الشراء (task17) */}
      <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--aseel-border, #ddd)" }}>
        <h5 style={{ fontWeight: 600, marginBottom: 4 }}>تراجع عن الترحيل</h5>
        <p className="aseel-text-soft" style={{ marginBottom: 6 }}>
          يحذف القيود ويعيد المستند مسودة (لا قيود عكسية). حارس الاعتمادية يمنع التراجع
          إن كانت مبيعات لاحقة استهلكت المخزون.
        </p>
        <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
          <button
            type="button" className="aseel-toolbtn"
            onClick={() => void handleUnpostShipment()}
            disabled={!shipment || saving}
            title="يحذف قيد الشحنة (LOGISTICS_SHIPMENT) ويعكس حركات استلام المخزون"
          >
            تراجع عن ترحيل الشحنة
          </button>
          <button
            type="button" className="aseel-toolbtn"
            onClick={() => void handleUnpostClearance()}
            disabled={!clearance || saving || !clearancePayments.some((p) => p.is_posted)}
            title={clearancePayments.some((p) => p.is_posted)
              ? "يحذف قيود كل دفعات التخليص المرحّلة ويعيدها مسودات"
              : "لا توجد دفعات تخليص مرحّلة"}
          >
            تراجع عن ترحيل دفعات التخليص
          </button>
        </span>
      </div>
    </div>
  );

  const financialContent = (
    <div className="space-y-3 p-2">
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <h4 className="border-b border-[var(--color-border)] px-3 py-2 text-sm font-semibold">ملخص القيود وإجراءات التراجع</h4>
        {accountsContent}
      </section>
      {s.id > 0 && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
          <h4 className="border-b border-[var(--color-border)] px-3 py-2 text-sm font-semibold">حركات الشحنة المالية</h4>
          <DocumentPaymentsTab referenceType="SHIPMENT" referenceId={s.id} searchQuery={s.shipment_number || ""} />
        </section>
      )}
      {clearance?.id && (
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
          <h4 className="border-b border-[var(--color-border)] px-3 py-2 text-sm font-semibold">حركات التخليص المالية</h4>
          <DocumentPaymentsTab referenceType="CLEARANCE" referenceId={clearance.id} searchQuery={clearance.declaration_number || ""} />
        </section>
      )}
    </div>
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
    { key: "deals", label: "الصفقات والشحن", content: dealsContent },
    { key: "clearance", label: "التخليص", content: clearanceContent },
    { key: "local", label: "النقل المحلي", content: localContent },
    { key: "payments", label: "الدفعات", content: paymentsContent },
    { key: "financial", label: "السجل المالي", content: financialContent },
    { key: "notes", label: "ملاحظات", content: notesContent },
  ];

  const toolbarActions: AseelToolbarAction[] = [
    { key: "save", label: "تخزين (F12)", icon: <Save />, onClick: () => void handleSaveShipment(), disabled: !isShipmentDirty || saving },
    {
      key: "to-invoice", label: allDealsConverted ? `فتح الفاتورة #${convertedPiId}` : remainingDealsCount < shipmentDeals.length ? `إنشاء الفواتير المتبقية (${remainingDealsCount})` : "إنشاء الفاتورة الدولية", icon: <FileText />,
      onClick: () => {
        if (allDealsConverted && convertedPiId) {
          window.open(`/purchase-invoices/${convertedPiId}`, "_blank");
        } else if (shipment?.id) {
          // كان يفتح /purchase-invoices/new?shipment= ولا أحد يقرأ البارامتر (T12-A4)
          // — الآن يفتح مودال «استيراد من تخليص جمركي» مسبق الاختيار على هذه الشحنة.
          window.open(`/international-invoices?import_shipment=${shipment.id}`, "_blank");
        }
      },
      disabled: !shipment?.id || shipment?.shipment_type === "transport" || saving || (!allDealsConverted && (!clearance || !freightCostEstablished || clearanceCostTotal <= 0)),
    },
    ...(onClose ? [{ key: "back", label: "رجوع", onClick: onClose }] : []),
  ];

  // ── شريط خطوات الرحلة: يجيب دائماً على «وين أنا وشو الخطوة الجاية؟» ──
  const journeySteps: Array<{
    key: string; label: string; sub: string;
    state: "done" | "todo" | "optional"; onClick?: () => void;
  }> = [
    {
      key: "ship", label: "١. إنشاء الشحنة",
      sub: s.id ? `#${s.shipment_number || s.id}` : "املأ البيانات ثم «تخزين» (F12)",
      state: s.id ? "done" : "todo",
    },
    {
      key: "deals", label: "٢. ضمّ الصفقات",
      sub: shipmentDeals.length
        ? `${shipmentDeals.length} صفقة في الشحنة`
        : "ضُمّ الصفقات الجاهزة للشحن (تُنشأ مسبقاً من شاشة «الصفقات»)",
      state: shipmentDeals.length ? "done" : "todo",
      onClick: () => setActiveTab("deals"),
    },
    {
      key: "freight", label: "٣. استحقاق الشحن للوكيل",
      sub: freightTotalUsd <= 0
        ? "لا توجد تكلفة شحن — لا حاجة لاستحقاق ولا دفعة"
        : freightAccrued
          ? `مُستحق على الوكيل · مدفوع $${fmt(freightPaidUsd)} من $${fmt(freightTotalUsd)}`
          : "أثبت الاستحقاق بسعر الصرف (الدفع لاحقاً ومستقل)",
      state: freightCostEstablished ? "done" : "todo",
      onClick: () => setActiveTab("payments"),
    },
    {
      key: "clearance", label: "٤. التخليص الجمركي",
      sub: !clearance
        ? "أنشئ سجل التخليص وسجّل بنوده"
        : clearanceCostTotal > 0
          ? `بيان ${clearance.declaration_number || `#${clearance.id}`} · ${fmt(clearanceCostTotal)} ₪`
          : "سجل التخليص موجود وينقصه إدخال التكلفة",
      state: clearance && clearanceCostTotal > 0 ? "done" : "todo",
      onClick: () => setActiveTab("clearance"),
    },
    {
      key: "local", label: "٥. النقل المحلي",
      sub: localShipments.length ? `${localShipments.length} سجل` : "اختياري",
      state: localShipments.length ? "done" : "optional",
      onClick: () => setActiveTab("local"),
    },
    {
      key: "invoice", label: "٦. الفواتير الدولية",
      sub: allDealsConverted
        ? `${convertedInvoices.length} فاتورة — اكتمل تحويل كل الصفقات`
        : convertedInvoices.length > 0
          ? `${convertedInvoices.length} فاتورة منشأة · بقيت ${remainingDealsCount} صفقة`
        : !clearance
          ? "تتطلب التخليص أولاً"
          : clearanceCostTotal <= 0
            ? "أدخل تكلفة التخليص أولاً"
          : !freightCostEstablished
            ? "أثبت استحقاق الشحن (أو أكمل دفعه) ثم أنشئها"
            : "جاهزة — لا يشترط دفع الشحن أو التخليص أو النقل المحلي",
      state: allDealsConverted ? "done" : "todo",
      onClick: () => {
        if (allDealsConverted && convertedPiId) {
          window.open(`/purchase-invoices/${convertedPiId}`, "_blank");
        } else if (!clearance) {
          setActiveTab("clearance");
        } else if (clearanceCostTotal <= 0) {
          setActiveTab("clearance");
        } else if (!freightCostEstablished) {
          setActiveTab("payments");
        } else if (shipment?.id) {
          window.open(`/international-invoices?import_shipment=${shipment.id}`, "_blank");
        }
      },
    },
  ];

  const guidanceJourneyKey: Record<ImportJourneyAction, string> = {
    save_shipment: "ship",
    link_deals: "deals",
    pay_freight: "freight",
    create_clearance: "clearance",
    enter_clearance_costs: "clearance",
    manage_local_transport: "local",
    create_invoice: "invoice",
    view_invoice: "invoice",
  };

  const guidancePanel = (
    <div className="m-2 rounded-xl border border-blue-200 bg-gradient-to-l from-blue-50 to-white p-4 shadow-sm">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <span className="text-xs font-semibold text-blue-700">الخطوة التالية · {guidance.step} من 6</span>
          <h3 className="mt-1 text-base font-bold text-[var(--color-text)]">{guidance.title}</h3>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">{guidance.description}</p>
        </div>
        <button
          type="button"
          className="aseel-toolbtn shrink-0 bg-blue-700 px-4 py-2 font-semibold text-white hover:bg-blue-800"
          onClick={() => executeGuidanceAction(guidance.action)}
          disabled={saving}
        >
          {guidance.actionLabel}
        </button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 border-t border-blue-100 pt-3 text-xs">
        <span className={`rounded-full px-3 py-1 font-medium ${freightCostEstablished ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
          الشحن الدولي: {
            freightTotalUsd <= 0 ? "بلا تكلفة"
              : freightAccrued ? "مُستحق"
              : freightFullyPaid ? "مدفوع"
              : `$${fmt(freightPaidUsd)} من $${fmt(freightTotalUsd)}`
          }
        </span>
        <span className={`rounded-full px-3 py-1 font-medium ${clearanceCostTotal > 0 ? "bg-emerald-100 text-emerald-800" : "bg-[var(--color-surface-3)] text-[var(--color-text-muted)]"}`}>
          التخليص: {clearanceCostTotal > 0 ? `${fmt(clearanceCostTotal)} ₪` : "بانتظار التكلفة"}
        </span>
        <span className="rounded-full bg-[var(--color-surface-3)] px-3 py-1 font-medium text-[var(--color-text-muted)]">النقل المحلي: اختياري</span>
      </div>
    </div>
  );

  const journeyStrip = (
    <div className="grid grid-cols-2 gap-1 border-b border-[var(--color-border)] px-2 pb-2 sm:grid-cols-3 xl:grid-cols-6">
      {journeySteps.map((st) => (
        <button
          key={st.key}
          type="button"
          onClick={st.onClick}
          disabled={!st.onClick}
          className={`rounded-lg border px-2 py-2 text-right text-xs transition-colors ${
            guidanceJourneyKey[guidance.action] === st.key
              ? "border-blue-500 bg-blue-50 text-blue-900 ring-1 ring-blue-200"
              : st.state === "done"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)]"
          }`}
          title={st.sub}
        >
          <span className="block font-semibold">
            {st.state === "done" ? "✓" : st.state === "optional" ? "○" : "●"} {st.label}
          </span>
        </button>
      ))}
    </div>
  );

  const routeTimeline = (
    <details className="mx-2 mb-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-xs">
      <summary className="cursor-pointer px-3 py-2 font-semibold text-[var(--color-text)]">عرض مسار حركة الشحنة والميناء</summary>
      <CompactTimeline steps={timelineSteps} />
    </details>
  );

  return (
    <>
      {error && (
        <div style={{ background: "var(--aseel-err-bg, #fde8e8)", color: "var(--aseel-err, #c0392b)", padding: "4px 12px", borderBottom: "1px solid var(--aseel-err, #c0392b)", fontSize: "var(--aseel-fs-sm, 12px)" }}>
          {error}
        </div>
      )}
      <AseelDocumentShell
        title={`رحلة الاستيراد — ${s.shipment_name || (s.shipment_number ? `شحنة ${s.shipment_number}` : "شحنة جديدة")}`}
        state={s.shipment_number ? `شحنة #${s.shipment_number}` : "شحنة جديدة"}
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
        {guidancePanel}
        {journeyStrip}
        {routeTimeline}
      </AseelDocumentShell>
      {quickAddType && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.5)", padding: 16 }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) setQuickAddType(null); }}
          dir="rtl"
        >
          <div style={{ background: "var(--aseel-panel, #fff)", borderRadius: 8, padding: 16, minWidth: 320, boxShadow: "0 8px 30px rgba(0,0,0,0.25)" }}>
            <h3 style={{ fontWeight: 700, marginBottom: 8 }}>
              {quickAddType === "FreightForwarder" ? "إضافة وكيل شحن جديد" : quickAddType === "LocalTransporter" ? "إضافة ناقل محلي جديد" : "إضافة مخلِّص جمركي جديد"}
            </h3>
            <input
              className="aseel-input"
              autoFocus
              placeholder="الاسم"
              value={quickAddName}
              onChange={(e) => setQuickAddName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void handleQuickAddPartner(); if (e.key === "Escape") setQuickAddType(null); }}
              style={{ width: "100%", marginBottom: 10 }}
            />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-start" }}>
              <button type="button" className="aseel-toolbtn" disabled={saving || !quickAddName.trim()} onClick={() => void handleQuickAddPartner()}>حفظ واختيار</button>
              <button type="button" className="aseel-toolbtn" onClick={() => setQuickAddType(null)}>إلغاء</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
