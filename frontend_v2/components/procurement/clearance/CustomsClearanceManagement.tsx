import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  FileText,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Truck,
  Loader2,
  Split,
  Search,
  CheckCircle2,
  X,
  Printer,
} from "lucide-react";
import { User } from "@/types";
import { DEFAULT_CLEARANCE_COST_LINES, type ClearanceCostLine } from "@/constants/clearanceDefaults";
import {
  listClearances,
  getClearance,
  createClearance,
  updateClearance,
  listClearancePayments,
  payClearanceFromCashBox,
  formatClearanceShipmentLine,
  type ClearancePaymentRow,
  type ClearanceRow,
} from "@/services/clearanceApi";
import { apiGetList } from "@/services/restApi";
import { accountingApi, type CashBoxLedgerLink } from "@/services/accountingApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { buildShipmentOptionLabel, ShipmentLabelInput } from "@/utils/shipmentLabel";
import { validatePaymentInput } from "@/utils/usePaymentForm";
import {
  AseelDocumentShell,
  useRecordNavigation,
  useAseelKeymap,
  AseelIndexPicker,
  AseelGrid,
  AseelDenseTable,
  type AseelGridColumn,
  type AseelToolbarAction,
} from "../../aseel";

type ShipmentPick = ShipmentLabelInput;
type BrokerPick = { id: number; name: string; partner_type?: string };

const SHIPPING_COST_LINE_LABEL = "دفعة الشحن (الناقل)";
const LUMP_CLEARANCE_LINE_LABEL = "إجمالي تكلفة التخليص";

function notesMeanShippingPayment(notes: string | null | undefined): boolean {
  const n = String(notes ?? "").trimStart();
  return n.startsWith("[شحن]") || n.startsWith("شحن");
}

function sumLines(lines: ClearanceCostLine[]): number {
  return lines.reduce((s, r) => s + (Number(r.amount) || 0), 0);
}

function distributeTotalEqually(lines: ClearanceCostLine[], total: number): ClearanceCostLine[] {
  const n = lines.length;
  if (n === 0) return lines;
  const cents = Math.round(Number(total) * 100);
  const base = Math.floor(cents / n);
  const rem = cents - base * n;
  return lines.map((row, i) => ({ ...row, amount: (base + (i < rem ? 1 : 0)) / 100 }));
}

const STATUS_OPTIONS = [
  { value: "Processing", label: "قيد المعالجة" },
  { value: "Cleared", label: "تم التخليص" },
  { value: "Hold", label: "معلّق" },
];

export const CustomsClearanceManagement: React.FC<{ currentUser: User }> = ({ currentUser }) => {
  const [clearances, setClearances] = useState<ClearanceRow[]>([]);
  const [shipments, setShipments] = useState<ShipmentPick[]>([]);
  const [brokers, setBrokers] = useState<BrokerPick[]>([]);
  const [transportPartners, setTransportPartners] = useState<BrokerPick[]>([]);
  const [showBrokerPicker, setShowBrokerPicker] = useState(false);

  const handleNewClearance = () => {
    setSelected(null);
    setFormBroker("");
    setFormDecl("");
    setFormDate(new Date().toISOString().slice(0, 10));
    setFormStatus("Processing");
    setFormNotes("");
    setFormLines([...DEFAULT_CLEARANCE_COST_LINES]);
    setShippingLineAmount(0);
    setNewOpen(true);
  };

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<ClearanceRow | null>(null);
  const [formBroker, setFormBroker] = useState<number | "">("");
  const [formDecl, setFormDecl] = useState("");
  const [formDate, setFormDate] = useState("");
  const [formStatus, setFormStatus] = useState("Processing");
  const [formNotes, setFormNotes] = useState("");
  const [formLines, setFormLines] = useState<ClearanceCostLine[]>(() => DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x })));
  const [distributeInput, setDistributeInput] = useState("");
  const [quickLumpTotal, setQuickLumpTotal] = useState("");
  const [shippingLineAmount, setShippingLineAmount] = useState(0);
  const [newOpen, setNewOpen] = useState(false);
  const [newShipmentId, setNewShipmentId] = useState<number | "">("");
  const [newBrokerId, setNewBrokerId] = useState<number | "">("");
  const [shipmentPickerOpen, setShipmentPickerOpen] = useState(false);
  const [shipmentSearch, setShipmentSearch] = useState("");
  const [payments, setPayments] = useState<ClearancePaymentRow[]>([]);
  const [cashLedgers, setCashLedgers] = useState<CashBoxLedgerLink[]>([]);
  const [payAmount, setPayAmount] = useState("");
  const [payDate, setPayDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [payCashBoxId, setPayCashBoxId] = useState("");
  const [payNotes, setPayNotes] = useState("");
  const [paying, setPaying] = useState(false);

  const nav = useRecordNavigation<ClearanceRow>({
    items: clearances, getId: (c) => c.id || 0, currentId: selected?.id || null,
    onSelect: async (id) => {
      if (id === null) { handleNewClearance(); }
      else {
        try {
          const loaded = await getClearance(Number(id));
          await loadDetail(loaded);
        } catch (err) { console.error('Error loading clearance:', err); }
      }
    },
  });

  useAseelKeymap({
    F2: () => window.print(), F5: () => reload(),
    F6: () => { const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]'); el?.focus(); },
    F12: () => { if (!saving && selected) handleSave(); },
    Escape: () => { if (showBrokerPicker) { setShowBrokerPicker(false); return; } setNewOpen(false); setSelected(null); },
    plus: () => { const ae = document.activeElement; if (ae?.getAttribute?.('data-aseel-key') === '1') setShowBrokerPicker(true); },
    CtrlHome: () => nav?.first?.(), CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(), CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => { setNewOpen(true); setSelected(null); },
  }, { enabled: !showBrokerPicker });

  const reload = useCallback(async () => {
    setErr(null); setLoading(true);
    try {
      const [cl, sh, pr, ledgers] = await Promise.all([
        listClearances(),
        apiGetList<any>("logistics/shipments/", { tenantId: resolveTenantId() }),
        apiGetList<BrokerPick>("partners/", { tenantId: resolveTenantId() }),
        accountingApi.getCashBoxLedgers(),
      ]);
      setClearances(cl);
      const mapped: ShipmentPick[] = sh.map((r: any) => ({
        id: Number(r.id), shipment_number: String(r.shipment_number || `S-${r.id}`),
        shipment_name: (r.shipment_name && String(r.shipment_name).trim()) || "",
        agent_shipment_number: (r.agent_shipment_number && String(r.agent_shipment_number).trim()) || "",
        israeli_side_name: (r.israeli_side_name && String(r.israeli_side_name).trim()) || "",
      }));
      mapped.sort((a, b) => buildShipmentOptionLabel(a).localeCompare(buildShipmentOptionLabel(b), "ar"));
      setShipments(mapped);
      setBrokers(pr.filter((p) => (p.partner_type || "") === "CustomsBroker"));
      setTransportPartners(pr.filter((p) => { const t = (p.partner_type || "").trim(); return t === "LocalTransporter" || t === "FreightForwarder"; }));
      setCashLedgers(ledgers || []);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const usedShipmentIds = useMemo(() => new Set(clearances.map((c) => Number(c.shipment))), [clearances]);
  const availableShipments = useMemo(() => shipments.filter((s) => !usedShipmentIds.has(s.id)), [shipments, usedShipmentIds]);
  const filteredAvailableShipments = useMemo(() => {
    const q = shipmentSearch.trim().toLowerCase();
    if (!q) return availableShipments;
    return availableShipments.filter((s) => buildShipmentOptionLabel(s).toLowerCase().includes(q));
  }, [availableShipments, shipmentSearch]);

  const shipmentById = useMemo(() => { const m = new Map<number, ShipmentPick>(); shipments.forEach((s) => m.set(s.id, s)); return m; }, [shipments]);

  const cashBoxDisplayName = useMemo(() => {
    const m = new Map<string, string>();
    cashLedgers.forEach((l) => { m.set(l.external_id, `${l.name} (${l.account_code})`); });
    return (externalId: string | undefined | null) => { const id = (externalId || "").trim(); if (!id) return "—"; return m.get(id) ?? id; };
  }, [cashLedgers]);

  const clearanceShipmentTitle = useCallback((c: ClearanceRow) => {
    if ((c.shipment_name || "").trim() || (c.shipment_number || "").trim()) return formatClearanceShipmentLine(c);
    const s = shipmentById.get(Number(c.shipment));
    if (s) return buildShipmentOptionLabel(s);
    return c.shipment_number ? `شحنة ${c.shipment_number}` : `شحنة #${c.shipment}`;
  }, [shipmentById]);

  const loadDetail = async (row: ClearanceRow) => {
    setErr(null);
    try {
      const fresh = await getClearance(row.id);
      setSelected(fresh);
      setFormBroker(fresh.customs_broker ?? "");
      setFormDecl(fresh.declaration_number || "");
      setFormDate(fresh.clearance_date ? String(fresh.clearance_date).slice(0, 10) : "");
      setFormStatus(fresh.status || "Processing");
      setFormNotes(fresh.notes || "");
      const rawLines = (fresh.cost_lines?.length ? fresh.cost_lines : DEFAULT_CLEARANCE_COST_LINES).map((x) => ({ label: x.label, amount: Number(x.amount) || 0 }));
      let shipFromLines = 0;
      const clearanceOnly = rawLines.filter((l) => { if (l.label.trim() === SHIPPING_COST_LINE_LABEL) { shipFromLines += Number(l.amount) || 0; return false; } return true; });
      const payRows = await listClearancePayments(row.id);
      setPayments(payRows);
      const paidShip = (payRows || []).reduce((s, p) => s + (notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0), 0);
      const paidClearance = (payRows || []).reduce((s, p) => s + (!notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0), 0);
      const shipLineEffective = shipFromLines > 0 ? shipFromLines : paidShip > 0 ? paidShip : 0;
      setShippingLineAmount(shipLineEffective);
      setFormLines(clearanceOnly.length ? clearanceOnly : DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x })));
      const clearanceLinesForTotal = clearanceOnly.length > 0 ? clearanceOnly : DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x }));
      const clearancePartTotal = sumLines(clearanceLinesForTotal);
      setPayAmount(String(Math.max(0, Number((clearancePartTotal - paidClearance).toFixed(2)))));
      setPayCashBoxId((payRows[0]?.cash_box_external_id || ""));
      setPayNotes(""); setDistributeInput(""); setQuickLumpTotal("");
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  };

  const openDetail = async (row: ClearanceRow) => { await loadDetail(row); };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true); setErr(null);
    try {
      const updated = await updateClearance(selected.id, {
        customs_broker: formBroker === "" ? null : Number(formBroker),
        declaration_number: formDecl.trim() || undefined,
        clearance_date: formDate || null, status: formStatus, notes: formNotes.trim() || "",
        cost_lines: [...formLines.filter((l) => l.label.trim() !== ""), ...(shippingLineAmount > 0 ? [{ label: SHIPPING_COST_LINE_LABEL, amount: Number(shippingLineAmount) || 0 }] : [])],
      });
      setSelected(updated); await reload();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setSaving(false); }
  };

  const handleCreate = async () => {
    if (newShipmentId === "") { alert("اختر الشحنة"); return; }
    setSaving(true); setErr(null);
    try {
      await createClearance({ shipment: Number(newShipmentId), customs_broker: newBrokerId === "" ? null : Number(newBrokerId), cost_lines: [{ label: LUMP_CLEARANCE_LINE_LABEL, amount: 0 }] });
      setNewOpen(false); setNewShipmentId(""); setNewBrokerId("");
      await reload();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setSaving(false); }
  };

  const applyDistribute = () => {
    const total = parseFloat(distributeInput.replace(/,/g, ""));
    if (!Number.isFinite(total) || total < 0) { alert("أدخل مبلغاً رقماً صالحاً للتوزيع"); return; }
    const active = formLines.filter((l) => l.label.trim() !== "");
    if (active.length === 0) { alert("أضف بنداً واحداً على الأقل (أو استخدم «التكلفة الكلية» أعلاه)"); return; }
    setFormLines(distributeTotalEqually(active, total));
  };

  const applyQuickLumpTotal = () => {
    const n = parseFloat(quickLumpTotal.replace(/,/g, ""));
    if (!Number.isFinite(n) || n < 0) { alert("أدخل مبلغاً صالحاً للتكلفة الكلية"); return; }
    setFormLines([{ label: LUMP_CLEARANCE_LINE_LABEL, amount: n }]); setQuickLumpTotal("");
  };

  const totalClearance = useMemo(() => sumLines(formLines) + (Number(shippingLineAmount) || 0), [formLines, shippingLineAmount]);
  const totalPaid = useMemo(() => payments.reduce((s, p) => s + Number(p.amount || 0), 0), [payments]);
  const paidShippingIls = useMemo(() => payments.reduce((s, p) => s + (notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0), 0), [payments]);
  const paidClearanceIls = useMemo(() => payments.reduce((s, p) => s + (!notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0), 0), [payments]);
  const clearancePaymentRows = useMemo(() => payments.filter((p) => !notesMeanShippingPayment(p.notes)), [payments]);
  const shippingPaymentRows = useMemo(() => payments.filter((p) => notesMeanShippingPayment(p.notes)), [payments]);
  const clearanceBudgetIls = useMemo(() => sumLines(formLines), [formLines]);
  const shippingBudgetIls = Number(shippingLineAmount) || 0;
  const remainingClearanceOnly = Math.max(0, Number((clearanceBudgetIls - paidClearanceIls).toFixed(2)));
  const remainingShippingOnly = Math.max(0, Number((shippingBudgetIls - paidShippingIls).toFixed(2)));
  const remaining = Math.max(0, Number((totalClearance - totalPaid).toFixed(2)));
  const clearancePayClosed = clearanceBudgetIls > 0.005 && remainingClearanceOnly <= 0.005;
  const shippingPayClosed = shippingBudgetIls > 0.005 && remainingShippingOnly <= 0.005;

  const handlePostPayment = async () => {
    if (!selected) return;
    if (clearancePayClosed) { alert("لا يوجد متبقي على التخليص — السداد مكتمل لهذا الأصل."); return; }
    if (!selected.customs_broker && formBroker === "") { alert("حدد المخلّص أولاً واربطه بحساب محاسبي."); return; }
    if (!payCashBoxId) { alert("اختر الصندوق أولاً."); return; }
    const vErr = validatePaymentInput({ amount: payAmount, date: payDate });
    if (vErr.amount || vErr.date) { alert(vErr.amount || vErr.date); return; }
    const amount = Number(payAmount || 0);
    setPaying(true); setErr(null);
    try {
      if (selected.customs_broker !== (formBroker === "" ? null : Number(formBroker))) {
        const updated = await updateClearance(selected.id, { customs_broker: formBroker === "" ? null : Number(formBroker) });
        setSelected(updated);
      }
      const res = await payClearanceFromCashBox(selected.id, { amount, cash_box_external_id: payCashBoxId, payment_date: payDate || undefined, notes: payNotes || undefined });
      const rows = await listClearancePayments(selected.id);
      setPayments(rows);
      alert(`✅ ${res.status}${res.journal_id ? ` (قيد #${res.journal_id})` : ""}`);
      setPayNotes("");
      const nextPaidClearance = rows.reduce((s, p) => s + (!notesMeanShippingPayment(p.notes) ? Number(p.amount) || 0 : 0), 0);
      setPayAmount(String(Math.max(0, Number((sumLines(formLines) - nextPaidClearance).toFixed(2)))));
    } catch (e) { const msg = e instanceof Error ? e.message : String(e); setErr(msg); alert(msg); }
    finally { setPaying(false); }
  };

  if (currentUser.role !== "manager" && currentUser.role !== "procurement") {
    return <div className="p-8 text-center aseel-text-soft dark:aseel-text-soft">لا تملك صلاحية عرض التخليص الجمركي.</div>;
  }

  const fmt = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const fld = (label: string, node: React.ReactNode) => (
    <label className="aseel-field">
      <span className="aseel-field-label">{label}</span>
      {node}
    </label>
  );

  /* ───────────── أعمدة قائمة التخليص (AseelDenseTable) ───────────── */
  const listColumns = [
    { key: "shipment", header: "الشحنة", width: "30%", render: (row: ClearanceRow) => <div className="font-bold">{clearanceShipmentTitle(row)}</div> },
    { key: "broker", header: "المخلص", render: (row: ClearanceRow) => row.broker_name || "—" },
    { key: "total", header: "الإجمالي", render: (row: ClearanceRow) => `${sumLines(row.cost_lines || []).toLocaleString(undefined, { minimumFractionDigits: 2 })}` },
    { key: "status", header: "الحالة", render: (row: ClearanceRow) => row.status },
  ];

  /* ───────────── أعمدة بنود التخليص (AseelGrid) ───────────── */
  const costLineColumns: AseelGridColumn<ClearanceCostLine>[] = [
    { key: "label", header: "البند", width: "60%" },
    { key: "amount", header: "المبلغ (₪)", width: "120px", align: "center", type: "number" },
    { key: "del", header: "", width: "36px", align: "center" },
  ];

  const costLineGetCell = (row: ClearanceCostLine, key: string): string | number => {
    switch (key) {
      case "label": return row.label || "";
      case "amount": return row.amount || 0;
      default: return "";
    }
  };

  const costLineOnChange = (rowIndex: number, key: string, value: string) => {
    const updated = [...formLines];
    if (key === "label") updated[rowIndex] = { ...updated[rowIndex], label: value };
    else if (key === "amount") updated[rowIndex] = { ...updated[rowIndex], amount: Number(value) || 0 };
    setFormLines(updated);
  };

  const addCostLine = () => setFormLines([...formLines, { label: "بند جديد", amount: 0 }]);
  const removeCostLine = (idx: number) => setFormLines(formLines.filter((_, i) => i !== idx));

  const renderLabelCell = (row: ClearanceCostLine, idx: number) => (
    <input value={row.label} onChange={(e) => { const v = e.target.value; setFormLines((rows) => rows.map((r, i) => i === idx ? { ...r, label: v } : r)); }} className="aseel-input" style={{ width: "100%" }} />
  );

  const renderDeleteCell = (_row: ClearanceCostLine, idx: number) => (
    <button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => removeCostLine(idx)} title="حذف البند"><Trash2 className="w-4 h-4" /></button>
  );

  costLineColumns[0].render = renderLabelCell;
  costLineColumns[2].render = renderDeleteCell;

  /* ───────────── تبويبات ──────────── */
  const notesTab = (
    <textarea className="aseel-input" rows={3} style={{ width: "100%" }} value={formNotes} onChange={(e) => setFormNotes(e.target.value)} />
  );

  const otherTab = (
    <div className="aseel-other">
      <p className="aseel-hint">إدارة النقل المحلي انتقلت إلى صفحة «الشحن المحلي». السجلات التاريخية رُحِّلت تلقائياً.</p>
    </div>
  );

  const toolbarActions: AseelToolbarAction[] = [
    { key: "new", label: "إضافة", icon: <Plus />, onClick: handleNewClearance },
    { key: "reload", label: "تحديث (F5)", icon: <RefreshCw />, onClick: () => reload(), separatorBefore: true },
    { key: "print", label: "طباعة (F2)", icon: <Printer />, onClick: () => window.print(), separatorBefore: true },
  ];

  const selectedBroker = brokers.find((b) => b.id === formBroker);

  return (
    <div id="clearance-print" dir="rtl" style={{ height: "calc(100vh - 13rem)", minHeight: 560 }}>
      <AseelDocumentShell
        title="فاتورة البيان الجمركي"
        state={selected ? `بيان #${selected.declaration_number || selected.id}` : "بيان جديد"}
        nav={nav}
        actions={toolbarActions}
        header={
          selected ? (
            <>
              {fld("رقم البيان", <input className="aseel-input" readOnly value={selected.declaration_number || `#${selected.id}`} />)}
              {fld("التاريخ", <input className="aseel-input" type="date" value={formDate} onChange={(e) => setFormDate(e.target.value)} />)}
              {fld("رقم القيد", <input className="aseel-input" readOnly value={selected.journal_id ? `#${selected.journal_id}` : "—"} />)}
              {fld("كشف الضريبة", <input className="aseel-input" readOnly value={selected.vat_statement_no || "—"} />)}
              {fld("المخلّص", <div className="aseel-pickfield">
                <input className="aseel-input aseel-input--hl" data-aseel-field="broker" data-aseel-key="1" readOnly value={selectedBroker ? `#${selectedBroker.id}` : ""} placeholder="+ للفهرس" onClick={() => setShowBrokerPicker(true)} />
                <button type="button" className="aseel-ellipsis" onClick={() => setShowBrokerPicker(true)} title="فهرس المخلّصين (+)">…</button>
              </div>)}
              {fld("الاسم", <input className="aseel-input" readOnly value={selectedBroker?.name || selected.broker_name || ""} />)}
              {fld("رقم فاتورة المقاصة", <input className="aseel-input" value={formDecl} onChange={(e) => setFormDecl(e.target.value)} placeholder="رقم البيان / الإقرار" />)}
              {fld("الحالة", <select className="aseel-input" value={formStatus} onChange={(e) => setFormStatus(e.target.value)}>
                {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>)}
              {fld("الشحنة", <input className="aseel-input" readOnly value={clearanceShipmentTitle(selected)} />)}
            </>
          ) : (
            <p className="aseel-text-soft text-sm" style={{ padding: 8 }}>اختر سجلاً من القائمة أو أضف تخليص جديد</p>
          )
        }
        tabs={selected ? [
          { key: "notes", label: "الملاحظات", content: notesTab },
          { key: "other", label: "بيانات أخرى", content: otherTab },
        ] : []}
        totals={
          selected ? (
            <>
              <div className="aseel-total-row"><span>مجموع بنود التخليص</span><span className="aseel-total-value">{fmt(clearanceBudgetIls)}</span></div>
              <div className="aseel-total-row"><span>الشحن المحلي</span><span className="aseel-total-value">{fmt(shippingBudgetIls)}</span></div>
              <div className="aseel-total-row"><span>المدفوع</span><span className="aseel-total-value">{fmt(totalPaid)}</span></div>
              <div className="aseel-total-row aseel-total-row--grand"><span>الإجمالي (تخليص + نقل)</span><span className="aseel-total-value">{fmt(totalClearance)}</span></div>
              <div className="aseel-total-row"><span>المتبقي</span><span className="aseel-total-value">{fmt(remaining)}</span></div>
            </>
          ) : null
        }
        status={
          <>
            <span className="aseel-status-item">المستخدم <b>{currentUser?.name || "—"}</b></span>
            <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
            <span className="aseel-status-item">{clearances.length} بيان</span>
          </>
        }
      >
        {err && (
          <div className="p-4 rounded-xl aseel-bg-panel aseel-text-state text-sm border aseel-border-soft" style={{ marginBottom: 8 }}>
            {err}
          </div>
        )}

        {/* قائمة التخليص */}
        <div style={{ marginBottom: selected ? 12 : 0 }}>
          <AseelDenseTable<ClearanceRow>
            columns={listColumns}
            rows={clearances}
            getRowKey={(r) => r.id}
            onRowClick={(row) => openDetail(row)}
            selectedKey={selected?.id ?? null}
            onSelect={(key) => { if (key != null) { const row = clearances.find((c) => c.id === key); if (row) openDetail(row); } }}
          />
        </div>

        {/* تفاصيل التخليص المحدد */}
        {selected && (
          <>
            {/* بنود التخليص */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <strong>بنود التخليص (₪)</strong>
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="button" onClick={() => setFormLines(DEFAULT_CLEARANCE_COST_LINES.map((x) => ({ ...x })))} className="aseel-toolbtn" style={{ fontSize: "var(--aseel-fs-sm)" }}>استعادة الافتراضي</button>
                  <button type="button" onClick={addCostLine} className="aseel-toolbtn" style={{ fontSize: "var(--aseel-fs-sm)" }}>+ بند</button>
                </div>
              </div>
              {/* التكلفة الكلية كبند واحد */}
              <div style={{ display: "flex", gap: 8, alignItems: "end", marginBottom: 8, padding: 8, background: "var(--aseel-panel)", border: "1px solid var(--aseel-border-soft)", borderRadius: "var(--aseel-radius)" }}>
                <label style={{ flex: 1 }}>
                  <span style={{ fontSize: "var(--aseel-fs-xs)", color: "var(--aseel-ink-soft)" }}>التكلفة الكلية للتخليص (₪) — بند واحد</span>
                  <input type="number" step="0.01" min="0" value={quickLumpTotal} onChange={(e) => setQuickLumpTotal(e.target.value)} placeholder="مثال: 14487" className="aseel-input" style={{ width: "100%", marginTop: 4 }} />
                </label>
                <button type="button" onClick={applyQuickLumpTotal} className="aseel-toolbtn">تطبيق كإجمالي</button>
              </div>
              {/* توزيع تلقائي */}
              <details style={{ marginBottom: 8, padding: 8, background: "var(--aseel-surface-2)", border: "1px dashed var(--aseel-border-soft)", borderRadius: "var(--aseel-radius)" }}>
                <summary style={{ cursor: "pointer", fontSize: "var(--aseel-fs-xs)", color: "var(--aseel-ink-soft)" }}>توزيع تلقائي بالتساوي على البنود الحالية (اختياري)</summary>
                <div style={{ display: "flex", gap: 8, alignItems: "end", marginTop: 8 }}>
                  <label style={{ flex: 1 }}>
                    <span style={{ fontSize: "var(--aseel-fs-xs)" }}>مبلغ يُقسَّم بالتساوي</span>
                    <input type="number" step="0.01" min="0" value={distributeInput} onChange={(e) => setDistributeInput(e.target.value)} placeholder="مثال: 1500" className="aseel-input" style={{ width: "100%", marginTop: 4 }} />
                  </label>
                  <button type="button" onClick={applyDistribute} className="aseel-toolbtn"><Split className="w-4 h-4" /> وزّع</button>
                </div>
              </details>
              <AseelGrid<ClearanceCostLine>
                columns={costLineColumns}
                rows={formLines}
                getCell={costLineGetCell}
                getRowKey={(_r, idx) => idx}
                onChange={costLineOnChange}
                emptyHint="لا توجد بنود — أضف بنداً"
              />
            </div>

            {/* دفع للمخلّص */}
            {!clearancePayClosed && (
              <div style={{ marginBottom: 12, padding: 12, background: "var(--aseel-panel)", border: "1px solid var(--aseel-border-soft)", borderRadius: "var(--aseel-radius)" }}>
                <span style={{ fontSize: "var(--aseel-fs-sm)", fontWeight: "bold", color: "var(--aseel-ink)" }}>دفع للمخلّص</span>
                <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", gap: 8, marginTop: 8, alignItems: "end" }}>
                  <label>
                    <span style={{ fontSize: "var(--aseel-fs-xs)", color: "var(--aseel-ink-soft)" }}>الصندوق</span>
                    <select value={payCashBoxId} onChange={(e) => setPayCashBoxId(e.target.value)} className="aseel-input" style={{ width: "100%" }}>
                      <option value="">اختر…</option>
                      {cashLedgers.map((l) => <option key={l.id} value={l.external_id}>{l.name} ({l.account_code})</option>)}
                    </select>
                  </label>
                  <label>
                    <span style={{ fontSize: "var(--aseel-fs-xs)", color: "var(--aseel-ink-soft)" }}>التاريخ</span>
                    <input type="date" value={payDate} onChange={(e) => setPayDate(e.target.value)} className="aseel-input" style={{ width: "100%" }} />
                  </label>
                  <label>
                    <span style={{ fontSize: "var(--aseel-fs-xs)", color: "var(--aseel-ink-soft)" }}>₪</span>
                    <input type="number" min="0" step="0.01" value={payAmount} onChange={(e) => setPayAmount(e.target.value)} className="aseel-input" style={{ width: "100%" }} />
                  </label>
                  <button type="button" onClick={handlePostPayment} disabled={paying} className="aseel-toolbtn" style={{ minWidth: 80 }}>
                    {paying ? <Loader2 className="w-4 h-4 animate-spin" /> : null} دفع
                  </button>
                </div>
                <details style={{ marginTop: 8 }}>
                  <summary style={{ cursor: "pointer", fontSize: "var(--aseel-fs-xs)", color: "var(--aseel-ink-soft)" }}>ملاحظات الدفع (اختياري)</summary>
                  <input value={payNotes} onChange={(e) => setPayNotes(e.target.value)} className="aseel-input" style={{ width: "100%", marginTop: 4 }} placeholder="اختياري" />
                </details>
              </div>
            )}
            {clearancePayClosed && (
              <p style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-success)", marginBottom: 12 }}>تم سداد التخليص بالكامل — لا دفع إضافي ضمن هذا الأصل.</p>
            )}

            {/* جدول الدفعات */}
            {clearancePaymentRows.length > 0 && (
              <div style={{ marginBottom: 12, overflowX: "auto" }}>
                <table className="aseel-grid" style={{ width: "100%", fontSize: "var(--aseel-fs-xs)" }}>
                  <thead>
                    <tr><th>التاريخ</th><th>الصندوق</th><th>المبلغ</th><th>ملاحظة</th><th>القيد</th></tr>
                  </thead>
                  <tbody>
                    {clearancePaymentRows.map((p) => (
                      <tr key={p.id}>
                        <td>{p.payment_date || "-"}</td>
                        <td>{cashBoxDisplayName(p.cash_box_external_id)}</td>
                        <td>{p.currency_code === "USD" ? `$${Number(p.amount || 0).toLocaleString()}` : `₪${Number(p.amount || 0).toLocaleString()}`}</td>
                        <td>{p.notes || "—"}</td>
                        <td>#{p.journal_id_display || p.journal || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* النقل المحلي — قراءة فقط */}
            {!!selected?.local_shipments?.length && (
              <div style={{ marginBottom: 12, padding: 12, background: "var(--aseel-surface-2)", border: "1px solid var(--aseel-border-soft)", borderRadius: "var(--aseel-radius)" }}>
                <p style={{ fontSize: "var(--aseel-fs-sm)", fontWeight: "bold", marginBottom: 8 }}>سجلات الشحن المحلي الرسمية المرتبطة:</p>
                <ul style={{ fontSize: "var(--aseel-fs-xs)", listStyle: "none", padding: 0 }}>
                  {selected.local_shipments.map((ls) => (
                    <li key={ls.id} style={{ display: "flex", justifyContent: "space-between", gap: 8, borderBottom: "1px solid var(--aseel-border-subtle)", paddingBottom: 4, marginBottom: 4 }}>
                      <span className="font-mono">{ls.shipment_number}</span>
                      <span>{Number(ls.amount).toLocaleString()}</span>
                      <span>{ls.status}</span>
                      <span style={{ color: ls.is_posted ? "var(--aseel-success)" : "var(--aseel-ink-soft)" }}>{ls.is_posted ? "مُرحّل" : "غير مُرحّل"}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* زر الحفظ */}
            <button type="button" onClick={handleSave} disabled={saving} className="aseel-toolbtn" style={{ padding: "8px 24px", fontSize: "var(--aseel-fs-base)", fontWeight: "bold" }}>
              {saving ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />} حفظ التعديلات
            </button>
          </>
        )}
      </AseelDocumentShell>

      {/* نافذة إنشاء تخليص جديد */}
      {newOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="aseel-bg-field dark:aseel-bg-panel rounded-2xl shadow-2xl max-w-xl w-full p-6 border aseel-border-soft dark:aseel-border-soft space-y-4">
            <h3 className="font-bold text-lg aseel-text-ink dark:text-white">تخليص جديد من شحنة</h3>
            <p className="text-xs aseel-text-soft">عند الإنشاء تُحدَّث مرحلة الصفقات المرتبطة بالشحنة.</p>
            <label className="block text-sm space-y-1">
              <span>الشحنة</span>
              <button type="button" onClick={() => setShipmentPickerOpen(true)} className="w-full rounded-xl border aseel-border-soft dark:aseel-border-soft px-3 py-2 aseel-bg-field dark:aseel-bg-panel text-right hover:aseel-border-soft">
                {newShipmentId === "" ? "اختر…" : buildShipmentOptionLabel(availableShipments.find((s) => s.id === newShipmentId) || shipments.find((s) => s.id === newShipmentId) || { id: Number(newShipmentId), shipment_number: `S-${newShipmentId}` })}
              </button>
            </label>
            <label className="block text-sm space-y-1">
              <span>المخلص (اختياري)</span>
              <select value={newBrokerId === "" ? "" : String(newBrokerId)} onChange={(e) => setNewBrokerId(e.target.value === "" ? "" : Number(e.target.value))} className="w-full rounded-xl border aseel-border-soft dark:aseel-border-soft px-3 py-2 aseel-bg-field dark:aseel-bg-panel">
                <option value="">— لاحقاً —</option>
                {brokers.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </label>
            <div className="flex gap-2 justify-end pt-2">
              <button type="button" onClick={() => setNewOpen(false)} className="px-4 py-2 rounded-xl border aseel-border-soft dark:aseel-border-soft aseel-text-ink dark:aseel-text-soft">إلغاء</button>
              <button type="button" onClick={handleCreate} disabled={saving || newShipmentId === ""} className="px-5 py-2 rounded-xl aseel-bg-panel text-white font-bold disabled:opacity-50">إنشاء</button>
            </div>
          </div>
        </div>
      )}

      {/* فهرس الشاحنات */}
      {newOpen && shipmentPickerOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="aseel-bg-field dark:aseel-bg-panel rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col border aseel-border-soft dark:aseel-border-soft">
            <div className="p-4 border-b aseel-border-soft dark:aseel-border-soft flex items-center justify-between">
              <h4 className="font-bold aseel-text-ink dark:text-white">اختر الشحنة للتخليص</h4>
              <button type="button" onClick={() => setShipmentPickerOpen(false)} className="p-2 rounded-full hover:aseel-bg-panel dark:hover:aseel-bg-panel aseel-text-soft"><X className="w-4 h-4" /></button>
            </div>
            <div className="p-4 border-b aseel-border-soft dark:aseel-border-soft">
              <div className="relative">
                <Search className="w-4 h-4 aseel-text-soft absolute right-3 top-1/2 -translate-y-1/2" />
                <input value={shipmentSearch} onChange={(e) => setShipmentSearch(e.target.value)} placeholder="ابحث بالاسم أو رقم الشحنة أو المرجع..." className="w-full rounded-xl border aseel-border-soft dark:aseel-border-soft pr-9 pl-3 py-2 aseel-bg-field dark:aseel-bg-panel text-sm" />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2 aseel-bg-panel/50 dark:bg-black/20">
              {filteredAvailableShipments.length === 0 ? (
                <div className="text-center text-sm aseel-text-soft py-12">لا توجد شحنات متاحة تطابق البحث</div>
              ) : (
                filteredAvailableShipments.map((s) => {
                  const selectedRow = newShipmentId === s.id;
                  return (
                    <button key={s.id} type="button" onClick={() => { setNewShipmentId(s.id); setShipmentPickerOpen(false); }} className={`w-full text-right p-3 rounded-xl border transition-all ${selectedRow ? "aseel-bg-panel aseel-border-soft dark:aseel-bg-panel/20 dark:aseel-border-soft" : "aseel-bg-field dark:aseel-bg-panel aseel-border-soft dark:aseel-border-soft hover:aseel-border-soft"}`}>
                      <div className="flex items-center gap-2">
                        <div className={`w-5 h-5 rounded-full border flex items-center justify-center ${selectedRow ? "aseel-border-soft aseel-text-soft" : "aseel-border-soft text-transparent"}`}>
                          <CheckCircle2 className="w-4 h-4" />
                        </div>
                        <span className="font-semibold aseel-text-ink dark:text-white leading-snug">{buildShipmentOptionLabel(s)}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* فهرس المخلّصين */}
      <AseelIndexPicker<BrokerPick>
        open={showBrokerPicker}
        title="فهرس المخلّصين الجمركيين"
        rows={brokers}
        columns={[
          { key: 'id', header: 'الرقم', width: '90px', value: (r) => r.id },
          { key: 'name', header: 'الاسم', value: (r) => r.name },
          { key: 'type', header: 'النوع', width: '140px', value: (r) => r.partner_type ?? '—' },
        ]}
        getRowKey={(r) => r.id}
        searchValue={(r) => `${r.id} ${r.name}`}
        onSelect={(r) => { setFormBroker(String(r.id)); setShowBrokerPicker(false); }}
        onClose={() => setShowBrokerPicker(false)}
      />
    </div>
  );
};
