/**
 * N6-T3 — LocalShippingPage (L10) — AseelDenseTable للشحن المحلي
 * المرجع: task5.md:797 + الإرساليات.txt:91-109
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { useAseelIndexKeymap } from "../aseel/useAseelIndexKeymap";

const STATUS_LABEL: Record<LocalShipmentStatus, string> = {
  pending:    "قيد الانتظار",
  in_transit: "قيد النقل",
  delivered:  "تم التسليم",
  cancelled:  "ملغية",
};

const STATUS_COLORS: Record<LocalShipmentStatus, string> = {
  pending:    "var(--aseel-warn, #b8800a)",
  in_transit: "var(--aseel-accent, #1857a4)",
  delivered:  "var(--aseel-ok, #267346)",
  cancelled:  "var(--aseel-danger, #c00)",
};

const fmt = (s: string | number) =>
  Number(s || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export const LocalShippingPage: React.FC = () => {
  const navigate = useNavigate();
  const [rows, setRows] = useState<LocalShipmentRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<LocalShipmentStatus | "all">("all");
  const searchInputRef = useRef<HTMLInputElement | null>(null);

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
    if (!window.confirm("ترحيل القيد المحاسبي؟")) return;
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
    if (!window.confirm("إلغاء الترحيل؟")) return;
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
    if (r.is_posted) { alert("ألغِ الترحيل أولاً."); return; }
    if (!window.confirm(`حذف الشحنة ${r.shipment_number}؟`)) return;
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
            <div style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>
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
        <span style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ink-soft)" }}>
          {r.clearance_number ? `بيان ${r.clearance_number}` : r.shipment_number_source || "—"}
        </span>
      ),
    },
    {
      key: "route",
      header: "من ← إلى",
      render: (r) => (
        <span style={{ fontSize: "var(--aseel-fs-sm)" }}>
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
            ? <span style={{ fontSize: "var(--aseel-fs-sm)", color: "var(--aseel-ok, #267346)" }}>مرحّلة #{r.journal}</span>
            : <span style={{ color: "var(--aseel-ink-soft)" }}>—</span>
          }
          {r.purchase_invoice && (
            <div style={{ fontSize: "10px", color: "var(--aseel-accent, #1857a4)", marginTop: 2 }}>
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
          {!r.is_posted && !r.purchase_invoice && (
            <>
              <button
                className="aseel-toolbtn"
                style={{ padding: "2px 4px" }}
                onClick={() => navigate(`/import-flow/${r.shipment}?tab=local`)}
                title="تعديل"
              >
                <Pencil style={{ width: 13, height: 13 }} />
              </button>
              <button
                className="aseel-toolbtn"
                style={{ padding: "2px 4px", color: "var(--aseel-ok, #267346)" }}
                onClick={() => void handlePost(r.id)}
                title="ترحيل"
              >
                <Send style={{ width: 13, height: 13 }} />
              </button>
            </>
          )}
          {r.is_posted && (
            <button
              className="aseel-toolbtn"
              style={{ padding: "2px 4px", color: "var(--aseel-warn, #b8800a)" }}
              onClick={() => void handleUnpost(r.id)}
              title="إلغاء الترحيل"
            >
              <RotateCcw style={{ width: 13, height: 13 }} />
            </button>
          )}
          {!r.is_posted && !r.purchase_invoice && (
            <button
              className="aseel-toolbtn"
              style={{ padding: "2px 4px" }}
              onClick={() => navigate(`/import-flow/${r.shipment}?tab=local`)}
              title="نقل إلى فاتورة مشتريات"
            >
              <LinkIcon style={{ width: 13, height: 13 }} />
            </button>
          )}
          {!r.is_posted && (
            <button
              className="aseel-toolbtn"
              style={{ padding: "2px 4px", color: "var(--aseel-danger, #c00)" }}
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

  useAseelIndexKeymap(
    {
      CtrlIns: () => navigate("/import-flow/new?tab=local"),
      F6: () => searchInputRef.current?.focus(),
      F5: () => void load(),
      Escape: () => { setSearch(""); setStatusFilter("all"); },
    },
  );

  return (
    <div dir="rtl" data-skin="aseel" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 6, padding: "8px 12px" }}>
      {/* شريط العنوان */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", paddingBottom: 4, borderBottom: "1px solid var(--aseel-border)" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          الشحن المحلي
        </strong>
        {(Object.keys(STATUS_LABEL) as LocalShipmentStatus[]).map((s) => (
          <span key={s} className="aseel-status-item">
            {STATUS_LABEL[s]}: <b>{totalsByStatus[s].count}</b>
          </span>
        ))}
        <div style={{ flex: 1 }} />
        <input
          ref={searchInputRef}
          className="aseel-input"
          style={{ width: 190 }}
          placeholder="بحث في الشحنات… (F6)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="aseel-input"
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
          className="aseel-toolbtn"
          onClick={() => void load()}
          title="تحديث"
        >
          <RefreshCw style={{ width: 14, height: 14 }} className={loading ? "animate-spin" : ""} />
        </button>
        <button
          className="aseel-toolbtn"
          onClick={() => navigate("/import-flow/new?tab=local")}
          title="شحنة محلية جديدة (Ctrl+Ins)"
        >
          <Plus style={{ width: 14, height: 14 }} /> شحنة محلية جديدة
        </button>
      </div>

      {/* رسائل النجاح/الخطأ */}
      {err && (
        <div style={{ padding: "6px 10px", background: "var(--aseel-danger-bg, #fef2f2)", color: "var(--aseel-danger, #c00)", borderRadius: 4, fontSize: "var(--aseel-fs-sm)" }}>
          {err}
        </div>
      )}
      {msg && (
        <div style={{ padding: "6px 10px", background: "var(--aseel-ok-bg, #f0fdf4)", color: "var(--aseel-ok, #267346)", borderRadius: 4, fontSize: "var(--aseel-fs-sm)" }}>
          {msg}
        </div>
      )}

      {/* جدول الشحنات المحلية */}
      <AseelDenseTable<LocalShipmentRow>
        columns={columns}
        rows={filteredRows}
        getRowKey={(r) => r.id}
        loading={loading}
        emptyHint="لا توجد شحنات محلية بعد — اضغط «شحنة محلية جديدة»"
        onRowClick={(row) => navigate(`/import-flow/${row.shipment}?tab=local`)}
        footer={
          filteredRows.length > 0 ? (
            <span style={{ fontFamily: "monospace", fontSize: "var(--aseel-fs-sm)" }}>
              الإجمالي: <b>{fmt(filteredRows.reduce((s, r) => s + Number(r.amount || 0), 0))}</b>
            </span>
          ) : undefined
        }
      />
    </div>
  );
};

export default LocalShippingPage;
