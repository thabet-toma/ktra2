import React, { useEffect, useMemo, useState } from "react";
import {
  activateServiceUnitCatalog,
  cloneServiceUnitCatalog,
  createServiceUnitCatalogDraft,
  getActiveServiceUnitCatalog,
  listServiceUnitCatalogs,
  SERVICE_DOCUMENT_TYPE_LABELS,
  SERVICE_DOCUMENT_TYPES,
  ServiceDocumentType,
  ServiceUnitCatalogRow,
  updateServiceUnitCatalogEntries,
} from "../../services/platformWorkOrdersApi";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcTable,
  CcThead,
  CcTh,
  CcTr,
  CcTd,
} from "./ui";

/** رسالةٌ موحَّدةٌ تميّز 403 عن غيره بدل نصّ الخادم الخام. */
const describeError = (cause: unknown, fallback: string): string =>
  describePlatformOpsError(cause, "ليس لديك تصريحٌ لإدارة كتالوج وحدات الخدمة.", fallback);

type EntryFormRow = {
  included: boolean;
  base_units: string;
  per_line_weight: string;
  complexity_low_add: string;
  complexity_medium_add: string;
  complexity_high_add: string;
};

const EMPTY_ROW: EntryFormRow = {
  included: false,
  base_units: "0.00",
  per_line_weight: "0.00",
  complexity_low_add: "0.00",
  complexity_medium_add: "0.00",
  complexity_high_add: "0.00",
};

const EFFECTIVE_STATE_LABELS: Record<string, string> = {
  draft: "مسودة",
  scheduled: "مجدولة",
  current: "سارية الآن",
  retired: "منتهية",
};

const catalogStateTone = (state: string): "neutral" | "accent" | "success" | "warning" | "danger" => {
  switch (state) {
    case "current":
      return "success";
    case "scheduled":
      return "warning";
    case "retired":
      return "danger";
    case "draft":
    default:
      return "neutral";
  }
};

function buildFormFromCatalog(catalog: ServiceUnitCatalogRow | null): Record<ServiceDocumentType, EntryFormRow> {
  const form = {} as Record<ServiceDocumentType, EntryFormRow>;
  SERVICE_DOCUMENT_TYPES.forEach((docType) => {
    const existing = catalog?.entries.find((e) => e.document_type === docType);
    form[docType] = existing
      ? {
          included: true,
          base_units: existing.base_units,
          per_line_weight: existing.per_line_weight,
          complexity_low_add: existing.complexity_low_add,
          complexity_medium_add: existing.complexity_medium_add,
          complexity_high_add: existing.complexity_high_add,
        }
      : { ...EMPTY_ROW };
  });
  return form;
}

export const ServiceUnitCatalogPanel: React.FC = () => {
  const [catalogs, setCatalogs] = useState<ServiceUnitCatalogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [activeCatalogId, setActiveCatalogId] = useState<number | null>(null);
  const [form, setForm] = useState<Record<ServiceDocumentType, EntryFormRow>>(buildFormFromCatalog(null));
  const [savingEntries, setSavingEntries] = useState(false);
  const [activationReason, setActivationReason] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [activating, setActivating] = useState(false);
  const [busyAction, setBusyAction] = useState(false);

  const selected = useMemo(
    () => catalogs.find((c) => c.id === selectedId) || null,
    [catalogs, selectedId],
  );

  const load = async (keepSelection = true) => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listServiceUnitCatalogs();
      const sorted = [...rows].sort((a, b) => b.version - a.version);
      setCatalogs(sorted);
      // النسخةُ السارية الآن — لا أحدث نسخةٍ بالإصدار، فقد تكون مسودةً غيرَ مفعَّلة بعد.
      const active = await getActiveServiceUnitCatalog().catch(() => null);
      setActiveCatalogId(active?.id ?? null);
      if (!keepSelection || !sorted.some((c) => c.id === selectedId)) {
        setSelectedId(active?.id ?? sorted[0]?.id ?? null);
      }
    } catch (err: unknown) {
      setError(describeError(err, "تعذّر تحميل كتالوج وحدات الخدمة."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setForm(buildFormFromCatalog(selected));
    setActivationReason(selected?.activation_reason || "");
    setEffectiveFrom("");
  }, [selected]);

  const isEditable = selected?.status === "draft";

  const handleFieldChange = (docType: ServiceDocumentType, field: keyof EntryFormRow, value: string | boolean) => {
    setForm((prev) => ({ ...prev, [docType]: { ...prev[docType], [field]: value } }));
  };

  const handleCreateDraft = async () => {
    setBusyAction(true);
    setError(null);
    try {
      const draft = await createServiceUnitCatalogDraft();
      await load(false);
      setSelectedId(draft.id);
    } catch (err: unknown) {
      setError(describeError(err, "تعذّر إنشاء مسودة جديدة."));
    } finally {
      setBusyAction(false);
    }
  };

  const handleClone = async () => {
    if (!selected) return;
    setBusyAction(true);
    setError(null);
    try {
      const cloned = await cloneServiceUnitCatalog(selected.id);
      await load(false);
      setSelectedId(cloned.id);
    } catch (err: unknown) {
      setError(describeError(err, "تعذّر استنساخ الكتالوج."));
    } finally {
      setBusyAction(false);
    }
  };

  const handleSaveEntries = async () => {
    if (!selected) return;
    setSavingEntries(true);
    setError(null);
    try {
      const entries = SERVICE_DOCUMENT_TYPES.filter((docType) => form[docType].included).map((docType) => ({
        document_type: docType,
        base_units: form[docType].base_units,
        per_line_weight: form[docType].per_line_weight,
        complexity_low_add: form[docType].complexity_low_add,
        complexity_medium_add: form[docType].complexity_medium_add,
        complexity_high_add: form[docType].complexity_high_add,
      }));
      await updateServiceUnitCatalogEntries(selected.id, entries);
      await load(true);
    } catch (err: unknown) {
      setError(describeError(err, "تعذّر حفظ بنود الكتالوج."));
    } finally {
      setSavingEntries(false);
    }
  };

  const handleActivate = async () => {
    if (!selected) return;
    setActivating(true);
    setError(null);
    try {
      await activateServiceUnitCatalog(selected.id, activationReason, effectiveFrom || undefined);
      await load(true);
    } catch (err: unknown) {
      setError(describeError(err, "تعذّر تفعيل الكتالوج."));
    } finally {
      setActivating(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" dir="rtl">
      <CcCard className="lg:col-span-1 p-4">
        <CcSectionTitle
          title="نسخ الكتالوج"
          badge={catalogs.length}
          action={
            <button
              type="button"
              onClick={handleCreateDraft}
              disabled={busyAction}
              className="rounded-lg bg-sky-600 hover:bg-sky-500 px-3 py-1.5 text-xs font-bold text-white transition disabled:opacity-50"
            >
              + مسودة جديدة
            </button>
          }
          className="mb-4"
        />
        {loading ? (
          <div className="py-10 text-center text-xs text-cc-text-muted">جاري التحميل...</div>
        ) : catalogs.length === 0 ? (
          <CcEmpty title="لا توجد نسخ كتالوج بعد" />
        ) : (
          <ul className="space-y-2">
            {catalogs.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(c.id)}
                  className={`w-full text-right px-3 py-2.5 rounded-xl border transition ${
                    c.id === selectedId
                      ? "border-sky-500 bg-sky-500/15 text-cc-text shadow-cc-card"
                      : "border-cc-border bg-cc-surface-2/50 text-cc-text-muted hover:bg-cc-surface-2 hover:text-cc-text"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-cc-text">
                      نسخة #{c.version} {c.id === activeCatalogId && "★"}
                    </span>
                    <CcPill tone={catalogStateTone(c.effective_state)}>
                      {EFFECTIVE_STATE_LABELS[c.effective_state] || c.effective_state}
                    </CcPill>
                  </div>
                  <div className="text-[10px] text-cc-text-muted mt-1">
                    {c.entries.length} بند{c.id === activeCatalogId ? " — الساريةُ حالياً على الاحتساب" : ""}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CcCard>

      <CcCard className="lg:col-span-2 p-4 sm:p-6">
        {error && (
          <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300">
            {error}
          </div>
        )}
        {!selected ? (
          <CcEmpty title="اختر نسخةً من القائمة لعرض بنودها" />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-cc-text tracking-tight">
                    نسخة #{selected.version}
                  </h2>
                  <CcPill tone={catalogStateTone(selected.effective_state)}>
                    {EFFECTIVE_STATE_LABELS[selected.effective_state] || selected.effective_state}
                  </CcPill>
                </div>
                {selected.activation_reason && (
                  <p className="text-xs text-cc-text-muted mt-1">سبب التفعيل: {selected.activation_reason}</p>
                )}
              </div>
              {selected.status !== "draft" && (
                <button
                  type="button"
                  onClick={handleClone}
                  disabled={busyAction}
                  className="rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs font-semibold text-cc-text hover:bg-cc-surface transition disabled:opacity-50"
                >
                  استنساخ إلى مسودة جديدة
                </button>
              )}
            </div>

            <CcTable>
              <CcThead>
                <tr>
                  <CcTh className="w-8"></CcTh>
                  <CcTh>نوع المستند</CcTh>
                  <CcTh>وحدات أساس</CcTh>
                  <CcTh>وزن لكلّ سطر</CcTh>
                  <CcTh>تعقيد منخفض +</CcTh>
                  <CcTh>تعقيد متوسط +</CcTh>
                  <CcTh>تعقيد مرتفع +</CcTh>
                </tr>
              </CcThead>
              <tbody>
                {SERVICE_DOCUMENT_TYPES.map((docType) => {
                  const row = form[docType];
                  return (
                    <CcTr key={docType}>
                      <CcTd>
                        <input
                          type="checkbox"
                          checked={row.included}
                          disabled={!isEditable}
                          onChange={(e) => handleFieldChange(docType, "included", e.target.checked)}
                          className="rounded border-cc-border"
                        />
                      </CcTd>
                      <CcTd className="font-medium text-cc-text">
                        {SERVICE_DOCUMENT_TYPE_LABELS[docType]}
                      </CcTd>
                      {(
                        ["base_units", "per_line_weight", "complexity_low_add", "complexity_medium_add", "complexity_high_add"] as const
                      ).map((field) => (
                        <CcTd key={field}>
                          <input
                            type="number"
                            step="0.01"
                            value={row[field]}
                            disabled={!isEditable || !row.included}
                            onChange={(e) => handleFieldChange(docType, field, e.target.value)}
                            className="w-24 px-2 py-1 rounded-md border border-cc-border bg-cc-surface-2 text-cc-text disabled:opacity-40 disabled:bg-cc-surface/30"
                          />
                        </CcTd>
                      ))}
                    </CcTr>
                  );
                })}
              </tbody>
            </CcTable>

            {isEditable && (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handleSaveEntries}
                  disabled={savingEntries}
                  className="rounded-lg bg-cc-surface-2 border border-cc-border px-3.5 py-2 text-xs font-bold text-cc-text hover:bg-cc-surface transition disabled:opacity-50"
                >
                  {savingEntries ? "جارٍ الحفظ..." : "حفظ البنود"}
                </button>

                <div className="flex-1 min-w-[220px]">
                  <input
                    type="text"
                    value={activationReason}
                    onChange={(e) => setActivationReason(e.target.value)}
                    placeholder="سبب التفعيل (إلزامي عند التفعيل)"
                    className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <input
                    type="datetime-local"
                    value={effectiveFrom}
                    onChange={(e) => setEffectiveFrom(e.target.value)}
                    className="rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleActivate}
                  disabled={activating || selected.entries.length === 0}
                  className="rounded-lg bg-emerald-600 hover:bg-emerald-500 px-3.5 py-2 text-xs font-bold text-white transition disabled:opacity-50"
                >
                  {activating ? "جارٍ التفعيل..." : "تفعيل هذه النسخة"}
                </button>
              </div>
            )}
          </>
        )}
      </CcCard>
    </div>
  );
};

export default ServiceUnitCatalogPanel;
