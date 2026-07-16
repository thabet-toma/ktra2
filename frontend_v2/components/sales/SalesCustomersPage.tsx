/**
 * N4-T2 — SalesCustomersPage (L8) Aseel inside-out
 * AseelDocumentShell + AseelDenseTable + شريط فلاتر + modal CRUD
 * Ref: task5.md:677-680
 *
 * حقول Partner الجديدة (N8-T8 backend): default_cost_center،
 *   end_of_dealing_date، assigned_price_tier — يَظهروا في النموذج
 *   كحقول optional (يَتم تجاهلها إذا backend لا يَدعمها).
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiDelete, apiGetList, apiGetPagedList, apiPatchObject, apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { Plus, Pencil, Trash2, RefreshCw, Save, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  AseelDocumentShell,
  AseelDenseTable,
  useAseelIndexKeymap,
  type DenseColumn,
  type AseelToolbarAction,
  type AseelTab,
} from "../aseel";
import { openInNewTab } from "@/utils/openInNewTab";
import { useConfirm } from "../../contexts/ConfirmContext";

type PartnerApi = {
  id: number;
  name: string;
  legal_name?: string | null;
  partner_type: string;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  country?: string | null;
  street_address?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  tax_number?: string | null;
  credit_limit?: string | null;
  currency?: number | null;
  // N8-T8 fields (optional from backend)
  default_cost_center?: number | null;
  end_of_dealing_date?: string | null;
  assigned_price_tier?: number | null;
};

type CurrRow = { CurrencyID: number; Code: string; Name?: string | null };
type CostCenterRow = { id: number; name: string };

const PRICE_TIERS = [
  { v: "", l: "—" },
  { v: "1", l: "تجزئة" },
  { v: "2", l: "جملة" },
  { v: "3", l: "موزّع" },
  { v: "4", l: "VIP" },
];

const emptyForm = () => ({
  name: "",
  legal_name: "",
  phone: "",
  email: "",
  tax_number: "",
  street_address: "",
  city: "",
  state_or_province: "",
  postal_code: "",
  country: "",
  credit_limit: "",
  currency: "" as number | "",
  default_cost_center: "" as number | "",
  end_of_dealing_date: "",
  assigned_price_tier: "",
});

import { formatMoney } from "@/utils/formatNumber";
const fmtMoney = (s: string | null | undefined) =>
  s != null && s !== "" ? formatMoney(s, "—") : "—";

export const SalesCustomersPage: React.FC = () => {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [rows, setRows] = useState<PartnerApi[]>([]);
  const [currencies, setCurrencies] = useState<CurrRow[]>([]);
  const [costCenters, setCostCenters] = useState<CostCenterRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterTier, setFilterTier] = useState("");
  const [selectedKey, setSelectedKey] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 50;

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const tenantId = useMemo(() => resolveTenantId(), []);

  const loadRows = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const result = await apiGetPagedList<PartnerApi>("partners/", {
        tenantId,
        query: {
          page, page_size: pageSize, partner_type: "Customer",
          search: search.trim() || undefined,
          assigned_price_tier: filterTier || undefined,
        },
      });
      setRows(result.results);
      setTotal(result.count);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [filterTier, page, search, tenantId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadRows(); }, 250);
    return () => window.clearTimeout(timer);
  }, [loadRows]);

  useEffect(() => {
    void Promise.allSettled([
      apiGetList<CurrRow>("accounting/currencies/", { tenantId }).then(setCurrencies),
      apiGetList<CostCenterRow>("accounting/cost-centers/", { tenantId }).then(setCostCenters),
    ]);
  }, [tenantId]);

  const filtered = rows;

  const openNew = () => {
    setEditingId(null);
    setForm(emptyForm());
    setModalOpen(true);
    setErr(null);
    setMsg(null);
  };

  const openEdit = (p: PartnerApi) => {
    setEditingId(p.id);
    setForm({
      name: p.name || "",
      legal_name: p.legal_name || "",
      phone: p.phone || "",
      email: p.email || "",
      tax_number: p.tax_number || "",
      street_address: p.street_address || "",
      city: p.city || "",
      state_or_province: p.state_or_province || "",
      postal_code: p.postal_code || "",
      country: p.country || "",
      credit_limit: p.credit_limit != null ? String(p.credit_limit) : "",
      currency: p.currency ?? "",
      default_cost_center: p.default_cost_center ?? "",
      end_of_dealing_date: p.end_of_dealing_date || "",
      assigned_price_tier: p.assigned_price_tier != null ? String(p.assigned_price_tier) : "",
    });
    setModalOpen(true);
    setErr(null);
    setMsg(null);
  };

  useAseelIndexKeymap({
    F2: () => {
      if (selectedKey != null) {
        const r = rows.find((x) => x.id === selectedKey);
        if (r) openEdit(r);
      }
    },
    F6: () => document.querySelector<HTMLInputElement>('[data-aseel-field="search"]')?.focus(),
    CtrlIns: openNew,
    Enter: () => {
      if (selectedKey != null) {
        const r = rows.find((x) => x.id === selectedKey);
        if (r) openEdit(r);
      }
    },
  }, { enabled: !modalOpen });

  const handleSave = async () => {
    if (!form.name.trim()) {
      setErr("اسم العميل مطلوب.");
      return;
    }
    setSaving(true);
    setErr(null);
    setMsg(null);
    try {
      const credit = form.credit_limit.trim() === "" ? null : Number(form.credit_limit);
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        partner_type: "Customer",
        legal_name: form.legal_name.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        tax_number: form.tax_number.trim() || null,
        street_address: form.street_address.trim() || null,
        city: form.city.trim() || null,
        state_or_province: form.state_or_province.trim() || null,
        postal_code: form.postal_code.trim() || null,
        country: form.country.trim() || null,
        credit_limit: credit != null && !Number.isNaN(credit) ? String(credit) : null,
        currency: form.currency === "" ? null : form.currency,
        // N8-T8 optional fields — backend will ignore unknown keys gracefully
        default_cost_center: form.default_cost_center === "" ? null : form.default_cost_center,
        end_of_dealing_date: form.end_of_dealing_date || null,
        assigned_price_tier: form.assigned_price_tier || null,
      };
      if (editingId) {
        await apiPatchObject(`partners/${editingId}/`, payload, { tenantId });
        setMsg("تم تحديث بيانات العميل.");
      } else {
        await apiPostObject("partners/", payload, { tenantId });
        setMsg("تم إضافة العميل.");
      }
      setModalOpen(false);
      await loadRows();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (p: PartnerApi) => {
    if (!(await confirm({ title: "حذف العميل", message: `حذف العميل «${p.name}»؟` }))) return;
    setErr(null); setMsg(null);
    try {
      await apiDelete(`partners/${p.id}/`, { tenantId });
      setMsg("تم الحذف.");
      await loadRows();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const columns: DenseColumn<PartnerApi>[] = [
    {
      key: "name",
      header: "الاسم",
      render: (r) => (
        <div style={{ display: "flex", flexDirection: "column" }}>
          <button
            type="button"
            className="text-xs font-semibold text-blue-700 hover:underline text-right"
            onClick={(e) => {
              e.stopPropagation();
              openInNewTab(`/partners/${r.id}`);
            }}
          >
            {r.name}
          </button>
          {r.legal_name && <span className="text-[10px]" style={{ color: "var(--aseel-ink-soft)" }}>{r.legal_name}</span>}
        </div>
      ),
    },
    { key: "phone", header: "الهاتف", width: "120px", render: (r) => <span className="font-mono text-xs">{r.phone || "—"}</span> },
    { key: "email", header: "البريد", width: "180px", render: (r) => <span className="text-xs">{r.email || "—"}</span> },
    { key: "city", header: "المدينة", width: "100px", render: (r) => <span className="text-xs">{r.city || "—"}</span> },
    { key: "tax_number", header: "الرقم الضريبي", width: "120px", render: (r) => <span className="font-mono text-xs">{r.tax_number || "—"}</span> },
    {
      key: "tier",
      header: "الفئة",
      width: "80px",
      align: "center",
      render: (r) => (
        <span className="text-xs" style={{ color: "var(--aseel-ink-soft)" }}>
          {PRICE_TIERS.find((t) => t.v === String(r.assigned_price_tier ?? ""))?.l || "—"}
        </span>
      ),
    },
    {
      key: "credit_limit",
      header: "حد الائتمان",
      width: "110px",
      align: "left",
      numeric: true,
      render: (r) => <span className="aseel-num font-mono text-xs">{fmtMoney(r.credit_limit)}</span>,
    },
    {
      key: "end_date",
      header: "نهاية التعامل",
      width: "110px",
      align: "center",
      render: (r) => <span className="text-xs">{r.end_of_dealing_date || "—"}</span>,
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "130px",
      align: "center",
      render: (r) => (
        <div style={{ display: "flex", gap: "4px", justifyContent: "center" }}>
          <button
            type="button"
            className="aseel-toolbtn"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            onClick={(e) => { e.stopPropagation(); openEdit(r); }}
            title="تعديل (F2)"
          >
            <Pencil className="w-3 h-3" /> تعديل
          </button>
          <button
            type="button"
            className="aseel-toolbtn aseel-toolbtn--danger"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            onClick={(e) => { e.stopPropagation(); handleDelete(r); }}
            title="حذف"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      ),
    },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <label className="aseel-field" style={{ flex: 1, minWidth: "200px" }}>
        <span className="aseel-field-label">بحث (اسم/هاتف/بريد/ضريبي)</span>
        <input
          className="aseel-input"
          data-aseel-field="search"
          placeholder="بحث... (F6)"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
      </label>
      <label className="aseel-field" style={{ minWidth: "120px" }}>
        <span className="aseel-field-label">فئة السعر</span>
        <select className="aseel-input" value={filterTier} onChange={(e) => { setFilterTier(e.target.value); setPage(1); }}>
          <option value="">الكل</option>
          {PRICE_TIERS.filter((t) => t.v).map((t) => (
            <option key={t.v} value={t.v}>{t.l}</option>
          ))}
        </select>
      </label>
    </div>
  );

  const toolbarActions: AseelToolbarAction[] = [
    { key: "new", label: "عميل جديد (Ctrl+Ins)", icon: <Plus />, onClick: openNew },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: () => void loadRows(),
      separatorBefore: true,
    },
  ];

  const tabs: AseelTab[] = [
    {
      key: "list",
      label: "العملاء",
      content: (
        <div style={{ padding: "8px" }}>
          {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
          {msg && <div className="aseel-banner" style={{ marginBottom: "8px", color: "var(--aseel-ok, #2d7d46)" }}>{msg}</div>}
          <AseelDenseTable<PartnerApi>
            columns={columns}
            rows={filtered}
            getRowKey={(r) => r.id}
            loading={loading}
            emptyHint="لا عملاء — اضغط Ctrl+Ins للإضافة"
            selectable
            selectedKey={selectedKey}
            onSelect={(k) => setSelectedKey(k as number | null)}
            onRowDoubleClick={(r) => openEdit(r)}
            pagination={{ page, pageSize, total, onChange: setPage }}
          />
        </div>
      ),
    },
  ];

  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="عملاء المبيعات"
        state={loading ? "جاري التحميل…" : `${filtered.length} في الصفحة من ${total}`}
        actions={toolbarActions}
        header={filterBar}
        tabs={tabs}
        status={
          <span className="aseel-status-item">
            عميل <b>{total}</b>
          </span>
        }
      />

      {/* Add/Edit modal */}
      {modalOpen && (
        <div
          className="fixed inset-0 z-[60] bg-black/40"
          style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "16px" }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) setModalOpen(false); }}
        >
          <div
            style={{
              background: "var(--aseel-surface, #fff)",
              border: "1px solid var(--aseel-border, #c8b99a)",
              borderRadius: "var(--aseel-radius, 6px)",
              width: "100%",
              maxWidth: "640px",
              maxHeight: "90vh",
              overflow: "auto",
              padding: "16px",
            }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid var(--aseel-border)", paddingBottom: "8px" }}>
              <h3 style={{ fontWeight: 600, fontSize: "14px" }}>
                {editingId ? `تعديل عميل #${editingId}` : "عميل جديد"}
              </h3>
              <button type="button" className="aseel-toolbtn" onClick={() => setModalOpen(false)}>
                <X className="w-3 h-3" />
              </button>
            </div>

            {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              <label className="aseel-field" style={{ gridColumn: "span 2" }}>
                <span className="aseel-field-label">الاسم *</span>
                <input className="aseel-input" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
              </label>
              <label className="aseel-field" style={{ gridColumn: "span 2" }}>
                <span className="aseel-field-label">الاسم القانوني</span>
                <input className="aseel-input" value={form.legal_name} onChange={(e) => setForm((f) => ({ ...f, legal_name: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">الهاتف</span>
                <input className="aseel-input" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">البريد الإلكتروني</span>
                <input className="aseel-input" type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">الرقم الضريبي</span>
                <input className="aseel-input" value={form.tax_number} onChange={(e) => setForm((f) => ({ ...f, tax_number: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">حد الائتمان</span>
                <input className="aseel-input aseel-num" type="number" value={form.credit_limit} onChange={(e) => setForm((f) => ({ ...f, credit_limit: e.target.value }))} />
              </label>
              <label className="aseel-field" style={{ gridColumn: "span 2" }}>
                <span className="aseel-field-label">العنوان</span>
                <input className="aseel-input" value={form.street_address} onChange={(e) => setForm((f) => ({ ...f, street_address: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">المدينة</span>
                <input className="aseel-input" value={form.city} onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">المحافظة</span>
                <input className="aseel-input" value={form.state_or_province} onChange={(e) => setForm((f) => ({ ...f, state_or_province: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">الرمز البريدي</span>
                <input className="aseel-input" value={form.postal_code} onChange={(e) => setForm((f) => ({ ...f, postal_code: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">الدولة</span>
                <input className="aseel-input" value={form.country} onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))} />
              </label>
              <label className="aseel-field">
                <span className="aseel-field-label">العملة</span>
                <select className="aseel-input" value={form.currency} onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value === "" ? "" : Number(e.target.value) }))}>
                  <option value="">—</option>
                  {currencies.map((c) => (
                    <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>
                  ))}
                </select>
              </label>

              {/* N8-T8 fields */}
              <div style={{ gridColumn: "span 2", marginTop: "8px", padding: "8px", background: "var(--aseel-surface-2, #f4ede0)", borderRadius: "4px" }}>
                <div style={{ fontSize: "11px", color: "var(--aseel-ink-soft)", marginBottom: "6px", fontWeight: 600 }}>
                  حقول متقدمة (N8-T8 backend optional)
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
                  <label className="aseel-field">
                    <span className="aseel-field-label">مركز التكلفة الافتراضي</span>
                    <select
                      className="aseel-input"
                      value={form.default_cost_center}
                      onChange={(e) => setForm((f) => ({ ...f, default_cost_center: e.target.value === "" ? "" : Number(e.target.value) }))}
                    >
                      <option value="">—</option>
                      {costCenters.map((cc) => <option key={cc.id} value={cc.id}>{cc.name}</option>)}
                    </select>
                  </label>
                  <label className="aseel-field">
                    <span className="aseel-field-label">نهاية التعامل</span>
                    <input
                      type="date"
                      className="aseel-input"
                      value={form.end_of_dealing_date}
                      onChange={(e) => setForm((f) => ({ ...f, end_of_dealing_date: e.target.value }))}
                    />
                  </label>
                  <label className="aseel-field">
                    <span className="aseel-field-label">فئة السعر</span>
                    <select
                      className="aseel-input"
                      value={form.assigned_price_tier}
                      onChange={(e) => setForm((f) => ({ ...f, assigned_price_tier: e.target.value }))}
                    >
                      {PRICE_TIERS.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
                    </select>
                  </label>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setModalOpen(false)}>إلغاء</button>
              <button
                type="button"
                className="aseel-toolbtn"
                disabled={saving}
                onClick={handleSave}
                style={{ background: "var(--aseel-ok, #2d7d46)", color: "#fff" }}
              >
                <Save className="w-3 h-3" /> {saving ? "..." : "حفظ"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
