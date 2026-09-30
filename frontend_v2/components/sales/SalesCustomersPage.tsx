/**
 * N4-T2 — SalesCustomersPage (L8) Kit inside-out
 * KitDocumentShell + KitDenseTable + شريط فلاتر + modal CRUD
 * Ref: task5.md:677-680
 *
 * حقول Partner الجديدة (N8-T8 backend): default_cost_center،
 *   end_of_dealing_date، assigned_price_tier — يَظهروا في النموذج
 *   كحقول optional (يَتم تجاهلها إذا backend لا يَدعمها).
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiDelete, apiGetPagedList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { Plus, Pencil, Trash2, RefreshCw } from "lucide-react";
import {
  KitDocumentShell,
  KitDenseTable,
  useKitIndexKeymap,
  type DenseColumn,
  type KitToolbarAction,
  type KitTab,
} from "../kit";
import { openInNewTab } from "@/utils/openInNewTab";
import { useConfirm } from "../../contexts/ConfirmContext";
import { PartnerEditorModal } from "../partners/PartnerEditorModal";

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
  is_active?: boolean;
};

const PRICE_TIERS = [
  { v: "", l: "—" },
  { v: "1", l: "تجزئة" },
  { v: "2", l: "جملة" },
  { v: "3", l: "موزّع" },
  { v: "4", l: "VIP" },
];

import { formatMoney } from "@/utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { useKeepOnce, useSimpleUi } from "../../hooks/useSimpleUi";
const fmtMoney = (s: string | null | undefined) =>
  s != null && s !== "" ? formatMoney(s, "—") : "—";

export const SalesCustomersPage: React.FC = () => {
  const confirm = useConfirm();
  const [rows, setRows] = useState<PartnerApi[]>([]);
  const { show: showAdv, columns: maskColumns } = useSimpleUi();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  // #73/#69: الفلاترُ والصفحةُ والصفُّ المختار في الرابط — العميلُ يُفتح بتبويبٍ جديد
  // يحمل هذا الرابطَ (`TabHandoff.openerPath`)، فـ«رجوع» منه يعيد القائمةَ كما تُركت
  // لا رأسَها، وتحديثُ الصفحة لا يُضيّع الفلترة.
  const [params, setParams] = useSearchParams();
  const urlSearch = params.get("q") ?? "";
  const filterTier = params.get("tier") ?? "";
  const showInactive = params.get("inactive") === "1";
  const page = Math.max(1, Math.floor(Number(params.get("page"))) || 1);
  const selParam = Number(params.get("sel"));
  const selectedKey = Number.isInteger(selParam) && selParam > 0 ? selParam : null;
  const patchParams = useCallback((patch: Record<string, string | null>) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      Object.entries(patch).forEach(([k, v]) => { if (v) next.set(k, v); else next.delete(k); });
      return next;
    }, { replace: true });
  }, [setParams]);
  const setPage = (p: number) => patchParams({ page: p > 1 ? String(p) : null });
  const setSelectedKey = (k: number | null) => patchParams({ sel: k != null ? String(k) : null });
  // حقلُ البحث محلّيٌّ أثناء الكتابة ويُكتب في الرابط بعد توقّفها؛ ويتبع الرابطَ إن تغيّر من خارجه.
  const [search, setSearch] = useState(urlSearch);
  const writtenSearchRef = useRef(urlSearch);
  useEffect(() => {
    if (urlSearch !== writtenSearchRef.current) {
      writtenSearchRef.current = urlSearch;
      setSearch(urlSearch);
    }
  }, [urlSearch]);
  useEffect(() => {
    if (search.trim() === urlSearch.trim()) return;
    const timer = window.setTimeout(() => {
      writtenSearchRef.current = search;
      patchParams({ q: search.trim() ? search : null, page: null });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [patchParams, search, urlSearch]);
  const [total, setTotal] = useState(0);
  const pageSize = 50;

  const [modalOpen, setModalOpen] = useState(false);

  const tenantId = useMemo(() => resolveTenantId(), []);

  // حارسُ الاستجابة القديمة: ردٌّ على فلترٍ سابقٍ وصل متأخّراً لا يكتب فوق نتيجة الفلتر الحالي.
  const requestRef = useRef(0);
  const loadRows = useCallback(async () => {
    const request = ++requestRef.current;
    setLoading(true);
    setErr(null);
    try {
      const result = await apiGetPagedList<PartnerApi>("partners/", {
        tenantId,
        query: {
          page, page_size: pageSize, partner_type: "Customer",
          search: urlSearch.trim() || undefined,
          assigned_price_tier: filterTier || undefined,
          include_inactive: showInactive ? 1 : undefined,
        },
      });
      if (request !== requestRef.current) return;
      setRows(result.results);
      setTotal(result.count);
    } catch (e: unknown) {
      if (request !== requestRef.current) return;
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }, [filterTier, page, urlSearch, showInactive, tenantId]);

  useEffect(() => { void loadRows(); }, [loadRows]);

  // العائدُ إلى القائمة يجد صفَّه في مجال النظر — مرّةً بعد كلّ تحميل، لا مع كلّ اختيار.
  useEffect(() => {
    if (selectedKey == null) return;
    document.querySelector(`[data-row-key="${selectedKey}"]`)?.scrollIntoView({ block: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const filtered = rows;

  const openNew = () => {
    setModalOpen(true);
    setErr(null);
    setMsg(null);
  };

  // الاختيارُ يُكتب في الرابط **قبل** الفتح: التبويبُ الجديد يحمل مسارَنا وجهةً لـ«رجوع».
  const openEdit = (p: PartnerApi) => {
    setSelectedKey(p.id);
    openInNewTab(`/partners/${p.id}?tab=edit`);
  };

  useKitIndexKeymap({
    F2: () => {
      if (selectedKey != null) {
        const r = rows.find((x) => x.id === selectedKey);
        if (r) openEdit(r);
      }
    },
    F6: () => document.querySelector<HTMLInputElement>('[data-ktra-field="search"]')?.focus(),
    CtrlIns: openNew,
    Enter: () => {
      if (selectedKey != null) {
        const r = rows.find((x) => x.id === selectedKey);
        if (r) openEdit(r);
      }
    },
  }, { enabled: !modalOpen });

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

  const allColumns: DenseColumn<PartnerApi>[] = [
    {
      key: "name",
      header: "الاسم",
      render: (r) => (
        <div style={{ display: "flex", flexDirection: "column" }}>
          <button
            type="button"
            className="text-xs font-semibold text-blue-700 hover:underline text-right"
            data-ctx-partner-id={r.id}
            data-ctx-partner-name={r.name}
            data-ctx-partner-kind="customer"
            onClick={(e) => {
              e.stopPropagation();
              setSelectedKey(r.id);
              openInNewTab(`/partners/${r.id}`);
            }}
          >
            {r.name}
            {r.is_active === false && (
              <span className="mr-1 rounded bg-gray-200 px-1 text-[10px] font-normal text-gray-700">موقوف</span>
            )}
          </button>
          {r.legal_name && <span className="text-[10px]" style={{ color: "var(--ktra-ink-soft)" }}>{r.legal_name}</span>}
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
        <span className="text-xs" style={{ color: "var(--ktra-ink-soft)" }}>
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
      render: (r) => <span className="ktra-num font-mono text-xs">{fmtMoney(r.credit_limit)}</span>,
    },
    {
      key: "end_date",
      header: "نهاية التعامل",
      width: "110px",
      align: "center",
      render: (r) => <span className="text-xs">{formatDateLocalized(r.end_of_dealing_date) || "—"}</span>,
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
            className="ktra-toolbtn"
            style={{ fontSize: "10px", padding: "2px 6px" }}
            onClick={(e) => { e.stopPropagation(); openEdit(r); }}
            title="تعديل (F2)"
          >
            <Pencil className="w-3 h-3" /> تعديل
          </button>
          <button
            type="button"
            className="ktra-toolbtn ktra-toolbtn--danger"
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

  /* T-SIMPL2: الرقم الضريبي وفئة السعر يُطويان في الوضع السهل، وحدُّ الائتمان
     يعود متى ضُبط على أحد العملاء فعلاً — سقفُ دَينٍ مفروضٌ لا يُخفى. */
  /* القائمة مرقَّمة، و`rows` صفحةٌ واحدة — الحقيقة تُثبَّت بعد رؤيتها فلا يختفي
     عمودُ حدِّ ائتمانٍ رآه المستخدم في الصفحة السابقة. */
  const anyCreditLimit = useKeepOnce(rows.some((r) => Number(r.credit_limit || 0) > 0));
  const columns = maskColumns(
    allColumns,
    "sales-customers",
    anyCreditLimit ? ["credit_limit"] : [],
  );

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <label className="ktra-field" style={{ flex: 1, minWidth: "200px" }}>
        <span className="ktra-field-label">بحث (اسم/هاتف/بريد/ضريبي)</span>
        <input
          className="ktra-input"
          data-ktra-field="search"
          placeholder="بحث... (F6)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      {/* T-SIMPL2: فلتر فئة السعر يتبع عمودها في الطيّ — ويعود متى كان مفعّلاً
          فعلاً، فلا تبقى قائمةٌ مُرشَّحة بفلترٍ لا يراه صاحبها. */}
      {showAdv("list.type-filter", Boolean(filterTier)) && (
        <label className="ktra-field" style={{ minWidth: "120px" }}>
          <span className="ktra-field-label">فئة السعر</span>
          <select className="ktra-input" value={filterTier} onChange={(e) => patchParams({ tier: e.target.value || null, page: null })}>
            <option value="">الكل</option>
            {PRICE_TIERS.filter((t) => t.v).map((t) => (
              <option key={t.v} value={t.v}>{t.l}</option>
            ))}
          </select>
        </label>
      )}
      <label className="flex items-center gap-1 pb-2 text-xs">
        <input
          type="checkbox"
          data-testid="show-inactive-partners"
          checked={showInactive}
          onChange={(e) => patchParams({ inactive: e.target.checked ? "1" : null, page: null })}
        />
        إظهار الموقوفين
      </label>
    </div>
  );

  const toolbarActions: KitToolbarAction[] = [
    { key: "new", label: "عميل جديد (Ctrl+Ins)", icon: <Plus />, onClick: openNew },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: () => void loadRows(),
      separatorBefore: true,
    },
  ];

  const tabs: KitTab[] = [
    {
      key: "list",
      label: "العملاء",
      content: (
        <div style={{ padding: "8px" }}>
          {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
          {msg && <div className="ktra-banner" style={{ marginBottom: "8px", color: "var(--ktra-ok, #2d7d46)" }}>{msg}</div>}
          <KitDenseTable<PartnerApi>
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
    <div style={{ minHeight: "calc(100vh - 5rem)" }}>
      <KitDocumentShell
        title="عملاء المبيعات"
        state={loading ? "جاري التحميل…" : `${filtered.length} في الصفحة من ${total}`}
        actions={toolbarActions}
        header={filterBar}
        tabs={tabs}
        status={
          <span className="ktra-status-item">
            عميل <b>{total}</b>
          </span>
        }
      />

      <PartnerEditorModal
        open={modalOpen}
        fixedType="Customer"
        onClose={() => setModalOpen(false)}
        onSaved={() => {
          setModalOpen(false);
          setMsg("تم إضافة العميل.");
          void loadRows();
        }}
      />
    </div>
  );
};
