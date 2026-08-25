/**
 * N6-T3 — LocalShippingPage (L10) — KitDenseTable للشحن المحلي
 * المرجع: task5.md:797 + الإرساليات.txt:91-109
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useConfirm } from "../../contexts/ConfirmContext";
import {
  Plus,
  Pencil,
  Trash2,
  Send,
  RotateCcw,
  Link as LinkIcon,
  RefreshCw,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  listLocalShipments,
  deleteLocalShipment,
  postLocalShipment,
  unpostLocalShipment,
  type LocalShipmentRow,
  type LocalShipmentStatus,
} from "@/services/localShippingApi";
import { KitDenseTable, type DenseColumn } from "../kit/KitDenseTable";
import { useKitIndexKeymap } from "../kit/useKitIndexKeymap";
import { openInNewTab } from "@/utils/openInNewTab";
import { apiGetList } from "@/services/restApi";
import { resolveTenantId } from "@/utils/tenantContext";
import { buildShipmentOptionLabel, type ShipmentLabelInput } from "@/utils/shipmentLabel";

const STATUS_LABEL: Record<LocalShipmentStatus, string> = {
  pending:    "قيد الانتظار",
  in_transit: "قيد النقل",
  delivered:  "تم التسليم",
  cancelled:  "ملغية",
};

const STATUS_COLORS: Record<LocalShipmentStatus, string> = {
  pending:    "var(--ktra-warn, #b8800a)",
  in_transit: "var(--ktra-accent, #1857a4)",
  delivered:  "var(--ktra-ok, #267346)",
  cancelled:  "var(--ktra-danger, #c00)",
};

import { formatMoney } from "../../utils/formatNumber";
const fmt = (s: string | number) => formatMoney(s);

export const LocalShippingPage: React.FC = () => {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [rows, setRows] = useState<LocalShipmentRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<LocalShipmentStatus | "all">("all");
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  // «نقل محلي جديد» = اختيار شحنة الاستيراد أولاً ثم فتح تبويب النقل المحلي في رحلتها
  const [shipmentPickerOpen, setShipmentPickerOpen] = useState(false);
  const [shipmentOptions, setShipmentOptions] = useState<ShipmentLabelInput[]>([]);

  const openShipmentPicker = useCallback(async () => {
    setShipmentPickerOpen(true);
    if (shipmentOptions.length > 0) return;
    try {
      const rowsApi = await apiGetList<any>("logistics/shipments/", { tenantId: resolveTenantId() });
      setShipmentOptions(rowsApi.map((r: any) => ({
        id: Number(r.id),
        shipment_number: r.shipment_number || `S-${r.id}`,
        shipment_name: (r.shipment_name && String(r.shipment_name).trim()) || "",
        agent_shipment_number: (r.agent_shipment_number && String(r.agent_shipment_number).trim()) || "",
        israeli_side_name: (r.israeli_side_name && String(r.israeli_side_name).trim()) || "",
      })));
    } catch {
      setErr("تعذّر تحميل قائمة الشحنات");
    }
  }, [shipmentOptions.length]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await listLocalShipments();
      setRows(r || []);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totalsByStatus = useMemo(() => {
    const out: Record<LocalShipmentStatus, { count: number; amount: number }> = {
      pending:    { count: 0, amount: 0 },
      in_transit: { count: 0, amount: 0 },
      delivered:  { count: 0, amount: 0 },
      cancelled:  { count: 0, amount: 0 },
    };
    for (const r of rows) {
      out[r.status].count += 1;
      out[r.status].amount += Number(r.amount || 0);
    }
    return out;
  }, [rows]);

  const filteredRows = useMemo(() => {
    let result = rows;
    if (search) {
      const s = search.toLowerCase();
      result = result.filter(r =>
        r.shipment_number?.includes(s) ||
        r.carrier_name?.toLowerCase().includes(s) ||
        r.origin?.toLowerCase().includes(s) ||
        r.destination?.toLowerCase().includes(s)
      );
    }
    if (statusFilter !== "all") {
      result = result.filter(r => r.status === statusFilter);
    }
    return result;
  }, [rows, search, statusFilter]);

  const handlePost = async (id: number) => {
    if (!(await confirm({ title: "ترحيل النقل المحلي", message: "ترحيل القيد المحاسبي؟", confirmText: "ترحيل" }))) return;
    setErr(null); setMsg(null);
    try {
      await postLocalShipment(id);
      setMsg(`تم ترحيل الشحنة #${id}`);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  const handleUnpost = async (id: number) => {
    if (!(await confirm({ title: "إلغاء ترحيل النقل المحلي", message: "سيُحذف قيد المصروف ويعود السجل مسودة.", confirmText: "إلغاء الترحيل" }))) return;
    setErr(null);
    try {
      await unpostLocalShipment(id);
      setMsg("تم إلغاء الترحيل");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل إلغاء الترحيل");
    }
  };

  const handleDelete = async (r: LocalShipmentRow) => {
    if (r.is_posted) { setErr("السجل مرحّل — ألغِ الترحيل أولاً."); return; }
    if (!(await confirm({ title: "حذف الشحنة", message: `حذف الشحنة ${r.shipment_number}؟` }))) return;
    setErr(null);
    try {
      await deleteLocalShipment(r.id);
      setMsg("تم الحذف");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const columns: DenseColumn<LocalShipmentRow>[] = [
    {
      key: "shipment_number",
      header: "رقم الشحنة",
      width: "110px",
      render: (r) => <b style={{ fontFamily: "monospace" }}>{r.shipment_number}</b>,
    },
    {
      key: "date",
      header: "التاريخ",
      width: "90px",
      render: (r) => <>{r.pickup_date || r.delivery_date || "—"}</>,
    },
    {
      key: "carrier",
      header: "الناقل",
      width: "160px",
      render: (r) => (
        <div>
          <div>{r.carrier_name || `#${r.carrier}`}</div>
          {r.driver_name && (
            <div style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)" }}>
              {r.driver_name}{r.vehicle_number ? ` • ${r.vehicle_number}` : ""}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "clearance",
      header: "التخليص",
      width: "120px",
      render: (r) => (
        <span style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ink-soft)" }}>
          {r.clearance_number ? `بيان ${r.clearance_number}` : r.shipment_number_source || "—"}
        </span>
      ),
    },
    {
      key: "route",
      header: "من ← إلى",
      render: (r) => (
        <span style={{ fontSize: "var(--ktra-fs-sm)" }}>
          {r.origin || "—"} ← {r.destination || "—"}
        </span>
      ),
    },
    {
      key: "amount",
      header: "المبلغ",
      width: "120px",
      align: "right",
      numeric: true,
      render: (r) => (
        <span style={{ fontFamily: "monospace" }}>
          {fmt(r.amount)} {r.currency_code || ""}
        </span>
      ),
    },
    {
      key: "status",
      header: "الحالة",
      width: "110px",
      render: (r) => (
        <span style={{ color: STATUS_COLORS[r.status] || "inherit", fontWeight: 500 }}>
          {STATUS_LABEL[r.status]}
        </span>
      ),
    },
    {
      key: "posted",
      header: "الترحيل",
      width: "130px",
      align: "center",
      render: (r) => (
        <div>
          {r.is_posted
            ? <span style={{ fontSize: "var(--ktra-fs-sm)", color: "var(--ktra-ok, #267346)" }}>مرحّلة #{r.journal}</span>
            : <span style={{ color: "var(--ktra-ink-soft)" }}>—</span>
          }
          {r.purchase_invoice && (
            <div style={{ fontSize: "10px", color: "var(--ktra-accent, #1857a4)", marginTop: 2 }}>
              فاتورة {r.purchase_invoice_number || `#${r.purchase_invoice}`}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "110px",
      align: "center",
      render: (r) => (
        <span style={{ display: "inline-flex", gap: 2, flexWrap: "wrap", justifyContent: "center" }}>
          {!r.is_posted && !r.purchase_invoice && r.shipment != null && (
            <>
              <button
                className="ktra-toolbtn"
                style={{ padding: "2px 4px" }}
                onClick={() => openInNewTab(`/import-flow/${r.shipment}?tab=local`)}
                title="التعديل — يفتح رحلة الاستيراد (تبويب النقل المحلي)"
              >
                <Pencil style={{ width: 13, height: 13 }} />
              </button>
              <button
                className="ktra-toolbtn"
                style={{ padding: "2px 4px", color: "var(--ktra-ok, #267346)" }}
                onClick={() => void handlePost(r.id)}
                title="ترحيل"
              >
                <Send style={{ width: 13, height: 13 }} />
              </button>
            </>
          )}
          {r.is_posted && (
            <button
              className="ktra-toolbtn"
              style={{ padding: "2px 4px", color: "var(--ktra-warn, #b8800a)" }}
              onClick={() => void handleUnpost(r.id)}
              title="إلغاء الترحيل"
            >
              <RotateCcw style={{ width: 13, height: 13 }} />
            </button>
          )}
          {!r.is_posted && !r.purchase_invoice && r.shipment != null && (
            <button
              className="ktra-toolbtn"
              style={{ padding: "2px 4px" }}
              onClick={() => openInNewTab(`/import-flow/${r.shipment}?tab=local`)}
              title="نقل التكلفة إلى فاتورة المشتريات — من رحلة الاستيراد"
            >
              <LinkIcon style={{ width: 13, height: 13 }} />
            </button>
          )}
          {!r.is_posted && (
            <button
              className="ktra-toolbtn"
              style={{ padding: "2px 4px", color: "var(--ktra-danger, #c00)" }}
              onClick={() => void handleDelete(r)}
              title="حذف"
            >
              <Trash2 style={{ width: 13, height: 13 }} />
            </button>
          )}
        </span>
      ),
    },
  ];

  useKitIndexKeymap(
    {
      CtrlIns: () => void openShipmentPicker(),
      F6: () => searchInputRef.current?.focus(),
      F5: () => void load(),
      Escape: () => { setShipmentPickerOpen(false); setSearch(""); setStatusFilter("all"); },
    },
  );

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 6, padding: "8px 12px" }}>
      {/* شريط العنوان */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", paddingBottom: 4, borderBottom: "1px solid var(--ktra-border)" }}>
        <strong style={{ fontSize: "var(--ktra-fs-title, 14px)", color: "var(--ktra-ink)" }}>
          الشحن المحلي
        </strong>
        {(Object.keys(STATUS_LABEL) as LocalShipmentStatus[]).map((s) => (
          <span key={s} className="ktra-status-item">
            {STATUS_LABEL[s]}: <b>{totalsByStatus[s].count}</b>
          </span>
        ))}
        <div style={{ flex: 1 }} />
        <input
          ref={searchInputRef}
          className="ktra-input"
          style={{ width: 190 }}
          placeholder="بحث في الشحنات… (F6)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="ktra-input"
          style={{ width: 140 }}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as LocalShipmentStatus | "all")}
        >
          <option value="all">كل الحالات</option>
          {(Object.keys(STATUS_LABEL) as LocalShipmentStatus[]).map((s) => (
            <option key={s} value={s}>{STATUS_LABEL[s]}</option>
          ))}
        </select>
        <button
          className="ktra-toolbtn"
          onClick={() => void load()}
          title="تحديث"
        >
          <RefreshCw style={{ width: 14, height: 14 }} className={loading ? "animate-spin" : ""} />
        </button>
        <button
          className="ktra-toolbtn"
          onClick={() => void openShipmentPicker()}
          title="اختر شحنة الاستيراد ثم يُفتح تبويب «النقل المحلي» في رحلتها (Ctrl+Ins)"
        >
          <Plus style={{ width: 14, height: 14 }} /> نقل محلي جديد
        </button>
      </div>

      {/* موضع التسجيل الموحّد: رحلة الاستيراد — هذه القائمة للمتابعة والترحيل */}
      <p className="ktra-text-soft" style={{ fontSize: "var(--ktra-fs-sm, 12px)", margin: 0 }}>
        النقل المحلي يُسجَّل ويُعدَّل داخل «رحلة الاستيراد» لشحنته (تبويب النقل المحلي) —
        نقرة مزدوجة على أي سجل تفتحها. هذه القائمة للمتابعة والترحيل والحذف.
      </p>

      {/* رسائل النجاح/الخطأ */}
      {err && (
        <div style={{ padding: "6px 10px", background: "var(--ktra-danger-bg, #fef2f2)", color: "var(--ktra-danger, #c00)", borderRadius: 4, fontSize: "var(--ktra-fs-sm)" }}>
          {err}
        </div>
      )}
      {msg && (
        <div style={{ padding: "6px 10px", background: "var(--ktra-ok-bg, #f0fdf4)", color: "var(--ktra-ok, #267346)", borderRadius: 4, fontSize: "var(--ktra-fs-sm)" }}>
          {msg}
        </div>
      )}

      {/* جدول الشحنات المحلية */}
      <KitDenseTable<LocalShipmentRow>
        columns={columns}
        rows={filteredRows}
        getRowKey={(r) => r.id}
        loading={loading}
        emptyHint="لا توجد سجلات نقل محلي بعد — اضغط «نقل محلي جديد»"
        onRowDoubleClick={(row) => {
          if (row.shipment != null) openInNewTab(`/import-flow/${row.shipment}?tab=local`);
          else setErr("هذا السجل غير مرتبط بشحنة استيراد — لا رحلة لفتحها.");
        }}
        footer={
          filteredRows.length > 0 ? (
            <span style={{ fontFamily: "monospace", fontSize: "var(--ktra-fs-sm)" }}>
              الإجمالي: <b>{fmt(filteredRows.reduce((s, r) => s + Number(r.amount || 0), 0))}</b>
            </span>
          ) : undefined
        }
      />

      {shipmentPickerOpen && (
        <div style={{ position: "fixed", inset: 0, zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.3)" }} onClick={() => setShipmentPickerOpen(false)}>
          <div style={{ background: "var(--ktra-bg, #fff)", borderRadius: 8, padding: 16, maxWidth: 520, width: "90%", maxHeight: "70vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
            <h4 style={{ fontWeight: 600, marginBottom: 4 }}>اختر شحنة الاستيراد</h4>
            <p className="ktra-text-soft" style={{ fontSize: "var(--ktra-fs-sm)", marginBottom: 8 }}>
              يُفتح تبويب «النقل المحلي» في رحلة استيراد الشحنة المختارة لإضافة السجل هناك.
            </p>
            {shipmentOptions.length === 0 && (
              <p className="ktra-text-soft" style={{ padding: 8 }}>جاري تحميل الشحنات…</p>
            )}
            {shipmentOptions.map((s) => (
              <div key={s.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--ktra-border, #eee)", cursor: "pointer" }}
                onClick={() => { setShipmentPickerOpen(false); openInNewTab(`/import-flow/${s.id}?tab=local`); }}>
                <span>{buildShipmentOptionLabel(s)}</span>
                <span className="ktra-toolbtn">فتح الرحلة</span>
              </div>
            ))}
            <div style={{ marginTop: 8, textAlign: "center" }}>
              <button type="button" className="ktra-toolbtn" onClick={() => setShipmentPickerOpen(false)}>إلغاء</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LocalShippingPage;
