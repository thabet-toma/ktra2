/**
 * N5-T5 — SupplierManagement (L5) — AseelDenseTable للموردين
 * يستخدم partners API (partner_type=Supplier) من accountingApi.
 */
import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { RefreshCw, Search, Plus } from "lucide-react";
import { SupplierModal } from "../common/SupplierModal";
import { useNavigate } from "react-router-dom";

type Partner = {
  id: number;
  name: string;
  partner_type: string;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  credit_limit?: string | null;
  linked_account?: number | null;
  linked_account_code?: string | null;
};

export interface SupplierManagementProps {
  initialPartnerId?: number | null;
  onInitialPartnerConsumed?: () => void;
}

export const SupplierManagement: React.FC<SupplierManagementProps> = ({
  initialPartnerId,
  onInitialPartnerConsumed,
}) => {
  const navigate = useNavigate();
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<number | null>(initialPartnerId ?? null);
  const [showAddModal, setShowAddModal] = useState(false);

  useEffect(() => {
    if (initialPartnerId != null) {
      setSelected(initialPartnerId);
      onInitialPartnerConsumed?.();
    }
  }, [initialPartnerId, onInitialPartnerConsumed]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const all = (await accountingApi.getPartners()) as Partner[];
      setPartners(all.filter((p) => p.partner_type === "Supplier" || p.partner_type === "supplier"));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = partners.filter((p) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      p.name.toLowerCase().includes(s) ||
      (p.phone || "").includes(s) ||
      (p.email || "").toLowerCase().includes(s)
    );
  });

  const columns: DenseColumn<Partner>[] = [
    { key: "id", header: "#", width: "55px", align: "center", render: (p) => <>{p.id}</> },
    { key: "name", header: "اسم المورد",
      render: (p) => (
        <button
          type="button"
          className="text-xs font-semibold text-blue-700 hover:underline text-right"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/partners/${p.id}`);
          }}
        >
          {p.name}
        </button>
      ) },
    { key: "acct", header: "رقم الحساب", width: "110px",
      render: (p) => <>{p.linked_account_code || p.linked_account || "—"}</> },
    { key: "phone", header: "الهاتف", width: "130px", render: (p) => <>{p.phone || "—"}</> },
    { key: "email", header: "البريد الإلكتروني", render: (p) => <>{p.email || "—"}</> },
    { key: "limit", header: "حد الائتمان", width: "110px", align: "center", numeric: true,
      render: (p) => <>{p.credit_limit ?? "—"}</> },
  ];

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }} data-skin="aseel">
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          إدارة الموردين
        </strong>
        <span className="aseel-status-item">الإجمالي: <b>{partners.length}</b></span>
        <div style={{ flex: 1 }} />
        <div style={{ position: "relative" }}>
          <Search style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", width: 14, height: 14, color: "var(--aseel-ink-soft)" }} />
          <input className="aseel-input" style={{ width: 200, paddingRight: 24 }}
            placeholder="بحث بالاسم / الهاتف…"
            value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <button className="aseel-toolbtn" onClick={load} title="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <button className="aseel-toolbtn" onClick={() => setShowAddModal(true)} title="إضافة مورد">
          <Plus className="h-4 w-4" /> إضافة
        </button>
      </div>

      {err && <div className="aseel-banner aseel-banner--err">{err}</div>}

      <AseelDenseTable<Partner>
        columns={columns}
        rows={filtered}
        getRowKey={(p) => p.id}
        loading={loading}
        selectable
        selectedKey={selected}
        onSelect={(k) => setSelected(k as number | null)}
        onRowDoubleClick={(r) => navigate(`/partners/${r.id}`)}
        emptyHint="لا يوجد موردون"
      />

      {showAddModal && (
        <SupplierModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onSaveSuccess={() => {
            setShowAddModal(false);
            load();
          }}
        />
      )}
    </div>
  );
};
