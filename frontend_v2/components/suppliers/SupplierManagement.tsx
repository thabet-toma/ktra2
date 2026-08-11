/**
 * N5-T5 — SupplierManagement (L5) — AseelDenseTable للموردين
 * يستخدم partners API (partner_type=Supplier) من accountingApi.
 */
import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { AseelDenseTable, type DenseColumn } from "../aseel/AseelDenseTable";
import { RefreshCw, Search, Plus, Pencil } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { PartnerEditorModal, type SupplierScope } from "../partners/PartnerEditorModal";
import { partnerKindFromType } from "../../utils/partnerActions";

/** T-PARTYTYPE: تسمية نوع الطرف كما تظهر في العمود والفلتر. */
const PARTY_TYPE_LABELS: Record<string, string> = {
  Supplier: "مورد",
  FreightForwarder: "وكيل شحن",
  CustomsBroker: "مخلّص جمركي",
  LocalTransporter: "ناقل محلي",
  Carrier: "ناقل",
};

type Partner = {
  id: number;
  name: string;
  partner_type: string;
  supplier_scope?: SupplierScope | null;
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
  // T-IMPOFFER: فصل المورد الدولي عن المحلي. «غير مصنَّف» تبويب ظاهر كي يعرف
  // المستخدم مَن بقي بلا تصنيف بدل أن يختفوا بين الجانبين.
  const [scopeTab, setScopeTab] = useState<"all" | SupplierScope>("all");
  // T-PARTYTYPE: فلتر النوع — «هات لي الناقلين المحليين فقط».
  const [typeTab, setTypeTab] = useState<"all" | string>("all");
  const [selected, setSelected] = useState<number | null>(initialPartnerId ?? null);
  const [showAddModal, setShowAddModal] = useState(false);
  // تعديل بيانات المورد من نفس الشاشة (كان لا يوجد أي مسار تعديل — الاسم/النقر المزدوج
  // يفتحان بطاقة العرض فقط، والمودال كان يُفتح للإضافة حصراً).
  const [editingPartnerId, setEditingPartnerId] = useState<number | null>(null);

  const openEdit = useCallback((p: Partner) => {
    setEditingPartnerId(p.id);
  }, []);

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
      // T-PARTYTYPE: الشاشة تدير **أطراف الشراء** كلها لا «مورد» وحده — وكيل
      // الشحن والمخلّص والناقل يُضافون من هنا، وكانوا يختفون فور إضافتهم لأن
      // الفلتر كان يقبل Supplier فقط. `partnerKindFromType` هي نفس قاعدة
      // إجراءات كبسة اليمين — تعريف واحد لجانب الشراء.
      setPartners(all.filter((p) => partnerKindFromType(p.partner_type) === "supplier"));
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = partners.filter((p) => {
    if (typeTab !== "all" && p.partner_type !== typeTab) return false;
    if (scopeTab !== "all" && (p.supplier_scope || "") !== scopeTab) return false;
    if (!search) return true;
    const s = search.toLowerCase();
    return (
      p.name.toLowerCase().includes(s) ||
      (p.phone || "").includes(s) ||
      (p.email || "").toLowerCase().includes(s)
    );
  });

  const scopeTabs: Array<{ value: "all" | SupplierScope; label: string }> = [
    { value: "all", label: "الكل" },
    { value: "local", label: "محليون" },
    { value: "international", label: "دوليون (استيراد)" },
    { value: "", label: "غير مصنَّفين" },
  ];

  const typeTabs: Array<{ value: "all" | string; label: string }> = [
    { value: "all", label: "كل الأنواع" },
    ...Object.entries(PARTY_TYPE_LABELS).map(([value, label]) => ({ value, label })),
  ];

  const columns: DenseColumn<Partner>[] = [
    { key: "id", header: "#", width: "55px", align: "center", render: (p) => <>{p.id}</> },
    // T-PARTYTYPE: النوع ظاهر في الصف — بلا عمود لا يفرّق أحد بين مورد وناقل.
    { key: "type", header: "النوع", width: "100px", align: "center",
      render: (p) => (
        <span style={{
          fontSize: "10px",
          fontWeight: 700,
          padding: "1px 6px",
          borderRadius: "4px",
          color: p.partner_type === "Supplier" ? "#267346" : "var(--aseel-accent, #2563eb)",
          background: p.partner_type === "Supplier"
            ? "rgba(38,115,70,0.10)"
            : "rgba(37,99,235,0.10)",
        }}>
          {PARTY_TYPE_LABELS[p.partner_type] || p.partner_type}
        </span>
      ) },
    { key: "name", header: "اسم المورد",
      render: (p) => (
        <button
          type="button"
          className="text-xs font-semibold text-blue-700 hover:underline text-right"
          data-ctx-partner-id={p.id}
          data-ctx-partner-name={p.name}
          data-ctx-partner-kind="supplier"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/partners/${p.id}`);
          }}
        >
          {p.name}
        </button>
      ) },
    { key: "scope", header: "النطاق", width: "95px", align: "center",
      render: (p) => {
        const scope = p.supplier_scope || "";
        if (!scope) return <span className="text-[10px] aseel-text-soft">غير مصنَّف</span>;
        const isIntl = scope === "international";
        return (
          <span style={{
            fontSize: "10px",
            fontWeight: 700,
            padding: "1px 6px",
            borderRadius: "4px",
            color: isIntl ? "var(--aseel-accent, #2563eb)" : "#267346",
            background: isIntl ? "rgba(37,99,235,0.10)" : "rgba(38,115,70,0.10)",
          }}>
            {isIntl ? "دولي" : "محلي"}
          </span>
        );
      } },
    { key: "acct", header: "رقم الحساب", width: "110px",
      render: (p) => <>{p.linked_account_code || p.linked_account || "—"}</> },
    { key: "phone", header: "الهاتف", width: "130px", render: (p) => <>{p.phone || "—"}</> },
    { key: "email", header: "البريد الإلكتروني", render: (p) => <>{p.email || "—"}</> },
    { key: "limit", header: "حد الائتمان", width: "110px", align: "center", numeric: true,
      render: (p) => <>{p.credit_limit ?? "—"}</> },
    { key: "edit", header: "تعديل", width: "60px", align: "center",
      render: (p) => (
        <button
          type="button"
          className="aseel-toolbtn"
          title="تعديل بيانات المورد"
          onClick={(e) => { e.stopPropagation(); openEdit(p); }}
        >
          <Pencil className="h-4 w-4" />
        </button>
      ) },
  ];

  return (
    <div dir="rtl" style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8, padding: "8px 12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: "var(--aseel-fs-title, 14px)", color: "var(--aseel-ink)" }}>
          إدارة الموردين
        </strong>
        <span className="aseel-status-item">الإجمالي: <b>{partners.length}</b></span>
        <select
          className="aseel-input"
          style={{ width: 130 }}
          value={typeTab}
          onChange={(e) => setTypeTab(e.target.value)}
          title="فلترة بنوع الطرف"
        >
          {typeTabs.map((tab) => (
            <option key={tab.value} value={tab.value}>{tab.label}</option>
          ))}
        </select>
        <div style={{ display: "flex", gap: 2 }}>
          {scopeTabs.map((tab) => (
            <button
              key={tab.value || "unset"}
              type="button"
              className="aseel-toolbtn"
              onClick={() => setScopeTab(tab.value)}
              style={scopeTab === tab.value
                ? { background: "var(--aseel-panel-hover)", fontWeight: 700 }
                : undefined}
            >
              {tab.label}
            </button>
          ))}
        </div>
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
        <PartnerEditorModal
          open={showAddModal}
          // T-PARTYTYPE: `fixedType` كان يُخفي منتقي النوع ويفرض «مورد» — فالناقل
          // المحلي يُحفظ مورداً ولا يظهر في قوائم رحلة الاستيراد التي تفلتر بالنوع.
          initialType="Supplier"
          onClose={() => setShowAddModal(false)}
          onSaved={() => {
            setShowAddModal(false);
            load();
          }}
        />
      )}

      {editingPartnerId && (
        <PartnerEditorModal
          open={!!editingPartnerId}
          partnerId={editingPartnerId}
          // النوع قابل للتصحيح عند التعديل أيضاً — طرفٌ أُضيف بنوع خاطئ سابقاً
          // لا يمكن إصلاحه إن بقي المنتقي مخفياً.
          onClose={() => setEditingPartnerId(null)}
          onSaved={() => {
            setEditingPartnerId(null);
            load();
          }}
        />
      )}
    </div>
  );
};
