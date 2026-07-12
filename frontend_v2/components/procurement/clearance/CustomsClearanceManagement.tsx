import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatMoney } from "../../../utils/formatNumber";
import {
  Plus,
  RefreshCw,
  Truck,
  Printer,
} from "lucide-react";
import { User } from "@/types";
import {
  listClearances,
  formatClearanceShipmentLine,
  type ClearanceRow,
} from "@/services/clearanceApi";
import { apiGetList } from "@/services/restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { buildShipmentOptionLabel, ShipmentLabelInput } from "@/utils/shipmentLabel";
import {
  AseelDocumentShell,
  useRecordNavigation,
  useAseelKeymap,
  AseelDenseTable,
} from "../../aseel";

type ShipmentPick = ShipmentLabelInput;
type BrokerPick = { id: number; name: string; partner_type?: string };

export const CustomsClearanceManagement: React.FC<{ currentUser: User }> = ({ currentUser }) => {
  const [clearances, setClearances] = useState<ClearanceRow[]>([]);
  const [shipments, setShipments] = useState<ShipmentPick[]>([]);
  const [brokers, setBrokers] = useState<BrokerPick[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<ClearanceRow | null>(null);
  // «إضافة تخليص» = اختيار شحنة بلا تخليص ثم فتح رحلتها — لا شاشة شحنة جديدة فارغة
  const [shipmentPickerOpen, setShipmentPickerOpen] = useState(false);

  const navigate = useNavigate();

  const reload = useCallback(async () => {
    setErr(null); setLoading(true);
    try {
      const [cl, sh, pr] = await Promise.all([
        listClearances(),
        apiGetList<any>("logistics/shipments/", { tenantId: resolveTenantId() }),
        apiGetList<BrokerPick>("partners/", { tenantId: resolveTenantId() }),
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
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const shipmentById = useMemo(() => { const m = new Map<number, ShipmentPick>(); shipments.forEach((s) => m.set(s.id, s)); return m; }, [shipments]);

  /** التخليص واحد لكل شحنة — المرشّحات للإضافة هي الشحنات التي بلا تخليص بعد */
  const shipmentsWithoutClearance = useMemo(() => {
    const has = new Set(clearances.map((c) => Number(c.shipment)));
    return shipments.filter((s) => !has.has(s.id));
  }, [shipments, clearances]);

  const clearanceShipmentTitle = useCallback((c: ClearanceRow) => {
    if ((c.shipment_name || "").trim() || (c.shipment_number || "").trim()) return formatClearanceShipmentLine(c);
    const s = shipmentById.get(Number(c.shipment));
    if (s) return buildShipmentOptionLabel(s);
    return c.shipment_number ? `شحنة ${c.shipment_number}` : `شحنة #${c.shipment}`;
  }, [shipmentById]);

  const nav = useRecordNavigation<ClearanceRow>({
    items: clearances, getId: (c) => c.id || 0, currentId: selected?.id || null,
    onSelect: async (id) => {
      if (id === null) { setShipmentPickerOpen(true); }
      else {
        const row = clearances.find((c) => c.id === id);
        if (row) setSelected(row);
      }
    },
  });

  useAseelKeymap({
    F5: () => reload(),
    F6: () => { const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]'); el?.focus(); },
    Escape: () => { setShipmentPickerOpen(false); setSelected(null); },
    CtrlIns: () => setShipmentPickerOpen(true),
  });

  if (currentUser.role !== "manager" && currentUser.role !== "procurement") {
    return <div className="p-8 text-center aseel-text-soft dark:aseel-text-soft">لا تملك صلاحية عرض التخليص الجمركي.</div>;
  }

  const sumLines = (lines: { amount?: number }[]) => lines.reduce((s, r) => s + (Number(r.amount) || 0), 0);

  const listColumns = [
    { key: "shipment", header: "الشحنة", width: "30%", render: (row: ClearanceRow) => <div className="font-bold">{clearanceShipmentTitle(row)}</div> },
    { key: "broker", header: "المخلص", render: (row: ClearanceRow) => row.broker_name || "—" },
    { key: "total", header: "الإجمالي", render: (row: ClearanceRow) => formatMoney(sumLines(row.cost_lines || [])) },
    { key: "status", header: "الحالة", render: (row: ClearanceRow) => row.status },
  ];

  const toolbarActions = [
    { key: "new", label: "إضافة تخليص لشحنة", icon: <Plus />, onClick: () => setShipmentPickerOpen(true) },
    { key: "import-flow", label: "رحلة الاستيراد", icon: <Truck />, onClick: () => { if (selected) navigate(`/import-flow/${selected.shipment}?tab=clearance`); }, disabled: !selected, separatorBefore: true },
    { key: "reload", label: "تحديث (F5)", icon: <RefreshCw />, onClick: () => reload(), separatorBefore: true },
    { key: "print", label: "طباعة (F2)", icon: <Printer />, onClick: () => window.print(), separatorBefore: true },
  ];

  return (
    <div id="clearance-print" dir="rtl">
      <AseelDocumentShell
        title="فاتورة البيان الجمركي"
        state={selected ? `بيان #${selected.declaration_number || selected.id}` : "قائمة"}
        nav={nav}
        actions={toolbarActions}
        header={
          selected ? (
            <div style={{ display: "flex", gap: 24, padding: "8px 0", fontSize: "var(--aseel-fs-sm)" }}>
              <span><b>الشحنة:</b> {clearanceShipmentTitle(selected)}</span>
              <span><b>المخلّص:</b> {selected.broker_name || "—"}</span>
              <span><b>الحالة:</b> {selected.status}</span>
              <span><b>الإجمالي:</b> {sumLines(selected.cost_lines || []).toLocaleString()}</span>
            </div>
          ) : (
            <p className="aseel-text-soft text-sm" style={{ padding: 8 }}>
              التخليص يُنشأ ويُحرَّر من داخل «رحلة الاستيراد» لشحنته — نقرة تختار السجل،
              ونقرة مزدوجة (أو زر «رحلة الاستيراد») تفتح التحرير هناك.
            </p>
          )
        }
        status={
          <>
            <span className="aseel-status-item">المستخدم <b>{currentUser?.name || "—"}</b></span>
            <span className="aseel-status-item">{clearances.length} بيان</span>
          </>
        }
      >
        {err && (
          <div className="p-4 rounded-xl aseel-bg-panel aseel-text-state text-sm border aseel-border-soft" style={{ marginBottom: 8 }}>
            {err}
          </div>
        )}

        <AseelDenseTable<ClearanceRow>
          columns={listColumns}
          rows={clearances}
          getRowKey={(r) => r.id}
          onRowClick={(row) => setSelected(row)}
          onRowDoubleClick={(row) => navigate(`/import-flow/${row.shipment}?tab=clearance`)}
          selectedKey={selected?.id ?? null}
          onSelect={(key) => { if (key != null) { const row = clearances.find((c) => c.id === key); if (row) setSelected(row); } }}
        />

        {shipmentPickerOpen && (
          <div style={{ position: "fixed", inset: 0, zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.3)" }} onClick={() => setShipmentPickerOpen(false)}>
            <div style={{ background: "var(--aseel-bg, #fff)", borderRadius: 8, padding: 16, maxWidth: 520, width: "90%", maxHeight: "70vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
              <h4 style={{ fontWeight: 600, marginBottom: 4 }}>اختر الشحنة لإنشاء تخليصها</h4>
              <p className="aseel-text-soft" style={{ fontSize: "var(--aseel-fs-sm)", marginBottom: 8 }}>
                لكل شحنة تخليص واحد — تُعرض الشحنات التي بلا تخليص بعد، ويُفتح تبويب
                «التخليص» في رحلة الاستيراد مباشرة.
              </p>
              {shipmentsWithoutClearance.length === 0 && (
                <p className="aseel-text-soft" style={{ padding: 8 }}>
                  كل الشحنات لديها تخليص بالفعل — أنشئ شحنة جديدة من صفحة «الشحنات» أولاً.
                </p>
              )}
              {shipmentsWithoutClearance.map((s) => (
                <div key={s.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--aseel-border, #eee)", cursor: "pointer" }}
                  onClick={() => { setShipmentPickerOpen(false); navigate(`/import-flow/${s.id}?tab=clearance`); }}>
                  <span>{buildShipmentOptionLabel(s)}</span>
                  <span className="aseel-toolbtn">فتح الرحلة</span>
                </div>
              ))}
              <div style={{ marginTop: 8, textAlign: "center" }}>
                <button type="button" className="aseel-toolbtn" onClick={() => setShipmentPickerOpen(false)}>إلغاء</button>
              </div>
            </div>
          </div>
        )}
      </AseelDocumentShell>
    </div>
  );
};
