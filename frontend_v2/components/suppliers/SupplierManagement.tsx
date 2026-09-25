/**
 * N5-T5 — SupplierManagement (L5) — صفحة الأطراف الدائنة (مورد/وكيل/مخلّص/ناقل).
 *
 * الفلترة من الخادم (`partners/?kinds=`) مع عدّاد لكل صنف (`partners/kind-counts/`)
 * — كانت الشاشة تحمّل 500 طرف وتفلترها في المتصفح فتفقد ما بعدها بصمت.
 */
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { apiGetObject, apiGetPagedList, apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { KitDenseTable, type DenseColumn } from "../kit/KitDenseTable";
import { RefreshCw, Search, Plus, Pencil, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { PartnerEditorModal, type PartnerType, type SupplierScope } from "../partners/PartnerEditorModal";
import { partnerTypeLabel } from "../../utils/partnerActions";
import { useSimpleUi } from "../../hooks/useSimpleUi";

type Partner = {
  id: number;
  name: string;
  partner_type: string;
  supplier_scope?: SupplierScope | null;
  phone?: string | null;
  email?: string | null;
  credit_limit?: string | null;
  linked_account?: number | null;
  linked_account_code?: string | null;
  is_active?: boolean;
};

/** أصناف الصفحة — المفاتيح نفسها التي يفهمها الخادم (`PARTNER_KINDS` في partners/views.py). */
const KINDS: Array<{ key: string; label: string; type: PartnerType; scope?: SupplierScope }> = [
  { key: "supplier_local", label: "مورد محلي", type: "Supplier", scope: "local" },
  { key: "supplier_international", label: "مورد دولي", type: "Supplier", scope: "international" },
  { key: "supplier_unscoped", label: "مورد غير مصنّف", type: "Supplier", scope: "" },
  { key: "FreightForwarder", label: "وكيل شحن", type: "FreightForwarder" },
  { key: "CustomsBroker", label: "مخلّص جمركي", type: "CustomsBroker" },
  { key: "LocalTransporter", label: "نقل محلي", type: "LocalTransporter" },
  { key: "Carrier", label: "ناقل", type: "Carrier" },
];
const ALL_KIND_KEYS = KINDS.map((k) => k.key);
/** «جديد» يُنشئ صنفاً محدّداً — «غير مصنّف» ليس خياراً يُقصد. */
const NEW_CHOICES = KINDS.filter((k) => k.key !== "supplier_unscoped");

const KINDS_STORAGE_KEY = "ktra.supplier-management.kinds";
const PAGE_SIZE = 50;

function readStoredKinds(): string[] {
  try {
    const raw = window.localStorage.getItem(KINDS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((k) => ALL_KIND_KEYS.includes(k)) : [];
  } catch {
    return [];
  }
}

function storeKinds(kinds: string[]) {
  try {
    window.localStorage.setItem(KINDS_STORAGE_KEY, JSON.stringify(kinds));
  } catch {
    /* تخزين محجوب (نافذة خاصّة) — الاختيار يبقى للجلسة وحدها */
  }
}

export interface SupplierManagementProps {
  initialPartnerId?: number | null;
  onInitialPartnerConsumed?: () => void;
}

export const SupplierManagement: React.FC<SupplierManagementProps> = ({
  initialPartnerId,
  onInitialPartnerConsumed,
}) => {
  const navigate = useNavigate();
  const tenantId = useMemo(() => resolveTenantId(), []);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const { columns: maskColumns } = useSimpleUi();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  // لا اختيار = كل الأصناف.
  const [kinds, setKinds] = useState<string[]>(readStoredKinds);
  const [showInactive, setShowInactive] = useState(false);
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<number | null>(initialPartnerId ?? null);
  const [chooserOpen, setChooserOpen] = useState(false);
  const [newChoice, setNewChoice] = useState<(typeof KINDS)[number] | null>(null);
  const [editingPartnerId, setEditingPartnerId] = useState<number | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);

  useEffect(() => {
    if (initialPartnerId != null) {
      setSelected(initialPartnerId);
      onInitialPartnerConsumed?.();
    }
  }, [initialPartnerId, onInitialPartnerConsumed]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const common = {
      search: search.trim() || undefined,
      include_inactive: showInactive ? 1 : undefined,
    };
    try {
      const [result, kindCounts] = await Promise.all([
        apiGetPagedList<Partner>("partners/", {
          tenantId,
          query: {
            ...common,
            kinds: (kinds.length ? kinds : ALL_KIND_KEYS).join(","),
            page,
            page_size: PAGE_SIZE,
          },
        }),
        apiGetObject<Record<string, number>>("partners/kind-counts/", { tenantId, query: common }),
      ]);
      setPartners(result.results);
      setTotal(result.count);
      setCounts(kindCounts || {});
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "خطأ في التحميل");
    } finally {
      setLoading(false);
    }
  }, [kinds, page, search, showInactive, tenantId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  const toggleKind = (key: string) => {
    setKinds((current) => {
      const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
      storeKinds(next);
      return next;
    });
    setPage(1);
    setChecked(new Set());
  };

  const clearKinds = () => {
    storeKinds([]);
    setKinds([]);
    setPage(1);
    setChecked(new Set());
  };

  const toggleChecked = (id: number) => {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const bulkClassify = async (scope: "local" | "international") => {
    if (!checked.size) return;
    setBulkBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await apiPostObject<{ updated: number }>(
        "partners/bulk-scope/", { ids: [...checked], supplier_scope: scope }, { tenantId },
      );
      setMsg(`صُنِّف ${res.updated} مورداً ${scope === "local" ? "محلياً" : "دولياً"}.`);
      setChecked(new Set());
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التصنيف");
    } finally {
      setBulkBusy(false);
    }
  };

  const allColumns: DenseColumn<Partner>[] = [
    { key: "pick", header: "", width: "32px", align: "center",
      render: (p) => p.partner_type === "Supplier" ? (
        <input
          type="checkbox"
          aria-label={`اختيار ${p.name}`}
          checked={checked.has(p.id)}
          onClick={(e) => e.stopPropagation()}
          onChange={() => toggleChecked(p.id)}
        />
      ) : null },
    { key: "id", header: "#", width: "55px", align: "center", render: (p) => <>{p.id}</> },
    // T-PARTYTYPE: النوع ظاهر في الصف — بلا عمود لا يفرّق أحد بين مورد وناقل.
    { key: "type", header: "النوع", width: "100px", align: "center",
      render: (p) => (
        <span className={`rounded px-1.5 py-px text-[10px] font-bold ${
          p.partner_type === "Supplier" ? "bg-green-700/10 text-green-800" : "bg-blue-600/10 text-blue-700"
        }`}>
          {partnerTypeLabel(p.partner_type)}
        </span>
      ) },
    { key: "name", header: "الاسم",
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
          {p.is_active === false && (
            <span className="mr-1 rounded bg-gray-200 px-1 text-[10px] font-normal text-gray-700">موقوف</span>
          )}
        </button>
      ) },
    { key: "scope", header: "النطاق", width: "95px", align: "center",
      render: (p) => {
        if (p.partner_type !== "Supplier") return <span className="text-[10px] ktra-text-soft">—</span>;
        const scope = p.supplier_scope || "";
        if (!scope) return <span className="text-[10px] ktra-text-soft">غير مصنَّف</span>;
        const isIntl = scope === "international";
        return (
          <span className={`rounded px-1.5 py-px text-[10px] font-bold ${
            isIntl ? "bg-blue-600/10 text-blue-700" : "bg-green-700/10 text-green-800"
          }`}>
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
    { key: "actions", header: "", width: "150px", align: "center",
      render: (p) => (
        <div className="flex justify-center gap-1">
          <button
            type="button"
            className="ktra-toolbtn text-[11px]"
            title="فتح بطاقة الطرف"
            onClick={(e) => { e.stopPropagation(); navigate(`/partners/${p.id}`); }}
          >
            <ExternalLink className="h-3.5 w-3.5" /> فتح البطاقة
          </button>
          <button
            type="button"
            className="ktra-toolbtn"
            title="تعديل البيانات"
            onClick={(e) => { e.stopPropagation(); setEditingPartnerId(p.id); }}
          >
            <Pencil className="h-4 w-4" />
          </button>
        </div>
      ) },
  ];

  /* T-SIMPL2: النطاق (محلي/دولي) ورقم الحساب المحاسبي يُطويان في الوضع السهل،
     وحدُّ الائتمان يعود متى ضُبط على أحد الموردين فعلاً — سقفٌ مفروضٌ لا يُخفى. */
  const anyCreditLimit = partners.some((p) => Number(p.credit_limit || 0) > 0);
  const columns = maskColumns(
    allColumns,
    "supplier-management",
    anyCreditLimit ? ["limit"] : [],
  );

  const kindsTotal = ALL_KIND_KEYS.reduce((sum, key) => sum + (counts[key] || 0), 0);

  return (
    <div dir="rtl" className="flex h-full flex-col gap-2 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="text-[length:var(--ktra-fs-title,14px)] text-[var(--ktra-ink)]">
          الموردون والأطراف الدائنة
        </strong>
        <span className="ktra-status-item">المعروض: <b>{total}</b></span>
        <div className="flex-1" />
        <label className="flex items-center gap-1 text-xs">
          <input
            type="checkbox"
            data-testid="show-inactive-partners"
            checked={showInactive}
            onChange={(e) => { setShowInactive(e.target.checked); setPage(1); }}
          />
          إظهار الموقوفين
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute right-1.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--ktra-ink-soft)]" />
          <input
            className="ktra-input w-[200px] pr-6"
            placeholder="بحث بالاسم / الهاتف…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <button className="ktra-toolbtn" onClick={() => void load()} title="تحديث">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <div className="relative">
          <button
            className="ktra-toolbtn"
            onClick={() => setChooserOpen((v) => !v)}
            title="إضافة طرف"
            aria-expanded={chooserOpen}
          >
            <Plus className="h-4 w-4" /> جديد
          </button>
          {chooserOpen && (
            <div
              role="menu"
              className="absolute left-0 top-full z-20 mt-1 w-48 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1 shadow-lg"
            >
              <div className="px-2 py-1 text-[11px] text-[var(--ktra-ink-soft)]">شو بدك تنشئ؟</div>
              {NEW_CHOICES.map((choice) => (
                <button
                  key={choice.key}
                  type="button"
                  role="menuitem"
                  className="block w-full rounded px-2 py-1.5 text-right text-xs hover:bg-[var(--ktra-panel-hover)]"
                  onClick={() => { setChooserOpen(false); setNewChoice(choice); }}
                >
                  {choice.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1" role="group" aria-label="أصناف الأطراف">
        <button
          type="button"
          aria-pressed={kinds.length === 0}
          className={`rounded-full border px-2.5 py-0.5 text-xs ${
            kinds.length === 0
              ? "border-blue-600 bg-blue-600 text-white"
              : "border-[var(--color-border)] hover:bg-[var(--ktra-panel-hover)]"
          }`}
          onClick={clearKinds}
        >
          الكل <span className="opacity-80">({kindsTotal})</span>
        </button>
        {KINDS.map((kind) => {
          const on = kinds.includes(kind.key);
          return (
            <button
              key={kind.key}
              type="button"
              aria-pressed={on}
              data-kind={kind.key}
              className={`rounded-full border px-2.5 py-0.5 text-xs ${
                on
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-[var(--color-border)] hover:bg-[var(--ktra-panel-hover)]"
              }`}
              onClick={() => toggleKind(kind.key)}
            >
              {kind.label} <span className="opacity-80">({counts[kind.key] ?? 0})</span>
            </button>
          );
        })}
      </div>

      {checked.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-blue-600/30 bg-blue-600/5 px-3 py-1.5 text-xs">
          <span>اختير <b>{checked.size}</b> مورداً:</span>
          <button type="button" className="ktra-toolbtn" disabled={bulkBusy} onClick={() => void bulkClassify("local")}>
            اجعلهم محليين
          </button>
          <button type="button" className="ktra-toolbtn" disabled={bulkBusy} onClick={() => void bulkClassify("international")}>
            اجعلهم دوليين
          </button>
          <button type="button" className="ktra-toolbtn" onClick={() => setChecked(new Set())}>
            إلغاء الاختيار
          </button>
        </div>
      )}

      {err && <div className="ktra-banner ktra-banner--err">{err}</div>}
      {msg && <div className="ktra-banner">{msg}</div>}

      <KitDenseTable<Partner>
        columns={columns}
        rows={partners}
        getRowKey={(p) => p.id}
        loading={loading}
        selectable
        selectedKey={selected}
        onSelect={(k) => setSelected(k as number | null)}
        onRowDoubleClick={(r) => navigate(`/partners/${r.id}`)}
        emptyHint="لا أطراف بهذا الاختيار"
        pagination={{ page, pageSize: PAGE_SIZE, total, onChange: setPage }}
      />

      {newChoice && (
        <PartnerEditorModal
          open={!!newChoice}
          fixedType={newChoice.type}
          fixedScope={newChoice.scope}
          onClose={() => setNewChoice(null)}
          onSaved={() => {
            setNewChoice(null);
            void load();
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
            void load();
          }}
        />
      )}
    </div>
  );
};
