import React, { useEffect, useMemo, useState } from "react";
import {
  activateServiceUnitCatalog,
  cloneServiceUnitCatalog,
  createServiceUnitCatalogDraft,
  listServiceUnitCatalogs,
  SERVICE_DOCUMENT_TYPE_LABELS,
  SERVICE_DOCUMENT_TYPES,
  ServiceDocumentType,
  ServiceUnitCatalogRow,
  updateServiceUnitCatalogEntries,
} from "../../services/platformWorkOrdersApi";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

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

const EFFECTIVE_STATE_STYLES: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  scheduled: "bg-amber-100 text-amber-700",
  current: "bg-emerald-100 text-emerald-700",
  retired: "bg-rose-100 text-rose-600",
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
      if (!keepSelection || !sorted.some((c) => c.id === selectedId)) {
        setSelectedId(sorted[0]?.id ?? null);
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
      <div className="lg:col-span-1 bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-slate-800">نسخ الكتالوج</h2>
          <button
            type="button"
            onClick={handleCreateDraft}
            disabled={busyAction}
            className="px-3 py-1.5 text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
          >
            + مسودة جديدة
          </button>
        </div>
        {loading ? (
          <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>
        ) : catalogs.length === 0 ? (
          <div className="py-10 text-center text-xs text-slate-400">لا توجد نسخ كتالوج بعد</div>
        ) : (
          <ul className="space-y-2">
            {catalogs.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(c.id)}
                  className={`w-full text-right px-3 py-2 rounded-lg border transition ${
                    c.id === selectedId
                      ? "border-blue-400 bg-blue-50"
                      : "border-slate-200 bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-800">نسخة #{c.version}</span>
                    <span
                      className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                        EFFECTIVE_STATE_STYLES[c.effective_state] || "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {EFFECTIVE_STATE_LABELS[c.effective_state] || c.effective_state}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">{c.entries.length} بند</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm p-4">
        {error && (
          <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800">
            {error}
          </div>
        )}
        {!selected ? (
          <div className="py-16 text-center text-xs text-slate-400">اختر نسخةً من القائمة لعرض بنودها</div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-bold text-slate-800">
                  نسخة #{selected.version} —{" "}
                  <span
                    className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                      EFFECTIVE_STATE_STYLES[selected.effective_state] || "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {EFFECTIVE_STATE_LABELS[selected.effective_state] || selected.effective_state}
                  </span>
                </h2>
                {selected.activation_reason && (
                  <p className="text-[11px] text-slate-500 mt-1">سبب التفعيل: {selected.activation_reason}</p>
                )}
              </div>
              {selected.status !== "draft" && (
                <button
                  type="button"
                  onClick={handleClone}
                  disabled={busyAction}
                  className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg disabled:opacity-50"
                >
                  استنساخ إلى مسودة جديدة
                </button>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-200">
                    <th className="py-2 pr-2 text-right w-8"></th>
                    <th className="py-2 pr-2 text-right">نوع المستند</th>
                    <th className="py-2 px-2 text-right">وحدات أساس</th>
                    <th className="py-2 px-2 text-right">وزن لكلّ سطر</th>
                    <th className="py-2 px-2 text-right">تعقيد منخفض +</th>
                    <th className="py-2 px-2 text-right">تعقيد متوسط +</th>
                    <th className="py-2 px-2 text-right">تعقيد مرتفع +</th>
                  </tr>
                </thead>
                <tbody>
                  {SERVICE_DOCUMENT_TYPES.map((docType) => {
                    const row = form[docType];
                    return (
                      <tr key={docType} className="border-b border-slate-100">
                        <td className="py-1.5 pr-2">
                          <input
                            type="checkbox"
                            checked={row.included}
                            disabled={!isEditable}
                            onChange={(e) => handleFieldChange(docType, "included", e.target.checked)}
                          />
                        </td>
                        <td className="py-1.5 pr-2 font-medium text-slate-700">
                          {SERVICE_DOCUMENT_TYPE_LABELS[docType]}
                        </td>
                        {(
                          ["base_units", "per_line_weight", "complexity_low_add", "complexity_medium_add", "complexity_high_add"] as const
                        ).map((field) => (
                          <td key={field} className="py-1.5 px-2">
                            <input
                              type="number"
                              step="0.01"
                              value={row[field]}
                              disabled={!isEditable || !row.included}
                              onChange={(e) => handleFieldChange(docType, field, e.target.value)}
                              className="w-24 px-2 py-1 border border-slate-200 rounded-md disabled:bg-slate-50 disabled:text-slate-400"
                            />
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {isEditable && (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handleSaveEntries}
                  disabled={savingEntries}
                  className="px-3.5 py-2 text-xs font-bold text-white bg-slate-700 hover:bg-slate-800 rounded-lg disabled:opacity-50"
                >
                  {savingEntries ? "جارٍ الحفظ..." : "حفظ البنود"}
                </button>

                <div className="flex-1 min-w-[220px]">
                  <input
                    type="text"
                    value={activationReason}
                    onChange={(e) => setActivationReason(e.target.value)}
                    placeholder="سبب التفعيل (إلزامي عند التفعيل)"
                    className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg"
                  />
                </div>
                <div>
                  <input
                    type="datetime-local"
                    value={effectiveFrom}
                    onChange={(e) => setEffectiveFrom(e.target.value)}
                    className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleActivate}
                  disabled={activating || selected.entries.length === 0}
                  className="px-3.5 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg disabled:opacity-50"
                >
                  {activating ? "جارٍ التفعيل..." : "تفعيل هذه النسخة"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ServiceUnitCatalogPanel;
