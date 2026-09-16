import React, { useCallback, useEffect, useState } from "react";
import { Copy, Info, Loader2, PlayCircle, Plus, Save } from "lucide-react";

import {
  activateSubscriptionPolicy,
  cloneSubscriptionPolicy,
  createSubscriptionPolicyDraft,
  listSubscriptionPolicies,
  previewSubscriptionPolicy,
  updateSubscriptionPolicyDraft,
  type BillingProductOption,
  type SubscriptionPolicyDiffValue,
  type SubscriptionPolicyEffectiveState,
  type SubscriptionPolicyInput,
  type SubscriptionPolicyPreview,
  type SubscriptionPolicyRow,
} from "../../services/platformOpsApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  POLICY_EFFECTIVE_STATE_LABEL,
  describePlatformOpsError,
  validateCommercialNumbers,
} from "../../utils/platformSubscriptionManagement";
import { type CcTone } from "../../utils/ccTone";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "./ui";
import { BillingProductPicker } from "./BillingProductPicker";
import { CompanyPicker } from "./CompanyPicker";

type ProductChoice = Pick<BillingProductOption, "id" | "name"> | null;

type DraftFields = {
  plan: string;
  monthly_fee: string;
  included_quota: string;
  trial_days: string;
  overage_unit_price: string;
  fixed_fee_product: ProductChoice;
  overage_product: ProductChoice;
};

function toDraft(row: SubscriptionPolicyRow): DraftFields {
  return {
    plan: row.plan,
    monthly_fee: row.monthly_fee,
    included_quota: String(row.included_quota),
    trial_days: String(row.trial_days),
    overage_unit_price: row.overage_unit_price,
    fixed_fee_product: row.fixed_fee_product
      ? { id: row.fixed_fee_product, name: row.fixed_fee_product_name ?? `#${row.fixed_fee_product}` }
      : null,
    overage_product: row.overage_product
      ? { id: row.overage_product, name: row.overage_product_name ?? `#${row.overage_product}` }
      : null,
  };
}

function toPolicyInput(draft: DraftFields): Partial<SubscriptionPolicyInput> {
  return {
    plan: draft.plan.trim(),
    monthly_fee: draft.monthly_fee,
    included_quota: Number(draft.included_quota),
    trial_days: Number(draft.trial_days),
    overage_unit_price: draft.overage_unit_price,
    fixed_fee_product: draft.fixed_fee_product?.id ?? null,
    overage_product: draft.overage_product?.id ?? null,
  };
}

const NUMBER_FIELDS = ["monthly_fee", "included_quota", "trial_days", "overage_unit_price"] as const;

const FIELD_LABELS: Record<string, string> = {
  plan: "نطاق الخطة",
  monthly_fee: "الرسم الشهري",
  included_quota: "الحصة المشمولة",
  trial_days: "أيام التجربة",
  overage_unit_price: "سعر التجاوز",
  billing_tenant_id: "شركة فوترة المنصة",
  fixed_fee_product_id: "صنف الرسم الشهري",
  overage_product_id: "صنف العمليات الزائدة",
};

/** نفس حارس الأرقام الذي تستعمله شروط اشتراك بعينه — دالّة واحدة مغطّاة بـ`node --test`. */
const validateDraft = (draft: DraftFields): string | null =>
  validateCommercialNumbers({
    monthly_fee: draft.monthly_fee,
    included_quota: draft.included_quota,
    overage_unit_price: draft.overage_unit_price,
    trial_days: draft.trial_days,
  });

/** تاريخ اليوم المحلي بصيغة YYYY-MM-DD — لا `toLocale*` (بالعربية يُخرج تقويماً هجرياً). */
function localIsoDate(date: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لإدارة سياسات الاشتراك.", "تعذّر إتمام العملية.");

/** مفتاح الانشغال لكل صف — مقارنة تامة كي لا يُعطَّل صف 11 حين ينشغل صف 1. */
const rowBusyKey = (action: string, rowId: number) => `${action}:${rowId}`;

const policyEffectiveStateTone = (state: SubscriptionPolicyEffectiveState): CcTone => {
  switch (state) {
    case "current":
      return "success";
    case "scheduled":
      return "accent";
    case "draft":
      return "warning";
    case "retired":
      return "neutral";
    default:
      return "neutral";
  }
};

/** إعدادات سياسة اشتراك خدمة الإدخال: إصدارات بنطاق خطة، مسودة، معاينة أثر، وتفعيل بسبب وتاريخ سريان. */
export const SubscriptionPolicyPanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [policies, setPolicies] = useState<SubscriptionPolicyRow[]>([]);
  const [drafts, setDrafts] = useState<Record<number, DraftFields>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [effectiveDates, setEffectiveDates] = useState<Record<number, string>>({});
  const [preview, setPreview] = useState<SubscriptionPolicyPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newBillingTenant, setNewBillingTenant] = useState<{ id: number; name: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listSubscriptionPolicies();
      setPolicies(rows);
      setDrafts(Object.fromEntries(rows.map((row) => [row.id, toDraft(row)])));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const run = async (key: string, action: () => Promise<unknown>, okMsg: string) => {
    setBusyKey(key);
    setError(null);
    try {
      await action();
      toast(okMsg, "success");
      await load();
    } catch (cause) {
      const message = displayError(cause);
      // تعارض: أعد تحميل النسخ ثم أبقِ سبب التعارض ظاهراً (`load` يمسح الخطأ أولاً).
      if ((cause as { status?: number } | null)?.status === 409) await load();
      setError(message);
    } finally {
      setBusyKey(null);
    }
  };

  const updateDraft = (row: SubscriptionPolicyRow, patch: Partial<DraftFields>) =>
    setDrafts((current) => ({ ...current, [row.id]: { ...(current[row.id] ?? toDraft(row)), ...patch } }));

  const createDraft = () => {
    if (!newBillingTenant) {
      setError("اختر شركة فوترة المنصة أولاً.");
      return;
    }
    // لا أرقام pilot في الواجهة: الخادم يملأ قيم البداية، ثم تُعدَّل المسودة في مكانها كأي مسودة.
    void run(
      "create",
      () => createSubscriptionPolicyDraft({ billing_tenant: newBillingTenant.id }),
      "تم إنشاء مسودة سياسة جديدة — عدّل قيمها وصنفَي الفوترة ثم فعّلها.",
    );
  };

  const saveDraft = (row: SubscriptionPolicyRow) => {
    const draft = drafts[row.id];
    if (!draft) return;
    const validationError = validateDraft(draft);
    if (validationError) { setError(validationError); return; }
    void run(rowBusyKey("save", row.id), () => updateSubscriptionPolicyDraft(row.id, toPolicyInput(draft)), "تم حفظ المسودة.");
  };

  const clone = (row: SubscriptionPolicyRow) =>
    run(rowBusyKey("clone", row.id), () => cloneSubscriptionPolicy(row.id), "تم استنساخ مسودة جديدة من هذه النسخة.");

  const previewRow = async (row: SubscriptionPolicyRow) => {
    setBusyKey(rowBusyKey("preview", row.id));
    setError(null);
    try {
      setPreview(await previewSubscriptionPolicy(row.id));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setBusyKey(null);
    }
  };

  const activate = async (row: SubscriptionPolicyRow) => {
    const reason = (reasons[row.id] ?? "").trim();
    if (!reason) {
      setError("سبب التفعيل مطلوب.");
      return;
    }
    // يوم لاحق ⇒ نسخة مجدولة تسري من بداية ذلك اليوم؛ اليوم أو فارغ ⇒ سريان فوري.
    const chosenDate = effectiveDates[row.id] ?? "";
    const effectiveFrom = chosenDate && chosenDate > localIsoDate() ? `${chosenDate}T00:00:00` : undefined;
    try {
      const impact = await previewSubscriptionPolicy(row.id);
      setPreview(impact);
      const confirmed = await confirm({
        title: `تفعيل سياسة v${row.version}`,
        message: (
          <div>
            <p>{effectiveFrom ? `تسري من ${formatDateValue(chosenDate)}.` : "تسري فوراً."}</p>
            <PolicyImpact impact={impact} plain />
          </div>
        ),
        confirmText: effectiveFrom ? "جدولة السياسة" : "تفعيل السياسة",
        danger: false,
      });
      if (!confirmed) return;
      await run(
        rowBusyKey("activate", row.id),
        () => activateSubscriptionPolicy(row.id, reason, effectiveFrom),
        effectiveFrom ? `جُدولت النسخة v${row.version}.` : `تم تفعيل النسخة v${row.version}.`,
      );
    } catch (cause) {
      setError(displayError(cause));
    }
  };

  return (
    <section className="space-y-4">
      <CcSectionTitle
        title="سياسة اشتراك خدمة الإدخال"
        subtitle="إصدارات بنطاق خطة، مسودة، معاينة أثر، وتفعيل بسبب وتاريخ سريان."
        badge={policies.length}
      />

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-300 flex items-center justify-between" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="mr-2 underline text-rose-200 hover:text-rose-100">إعادة المحاولة</button>
        </div>
      )}

      <CcCard className="space-y-3 p-4">
        <p className="flex items-center gap-2 text-sm font-bold text-cc-text">
          <Plus className="h-4 w-4 text-sky-400" />
          <span>مسودة جديدة</span>
        </p>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="flex-1">
            <CompanyPicker
              value={newBillingTenant?.id ?? null}
              onChange={(id, name) => setNewBillingTenant({ id, name })}
              placeholder="شركة فوترة المنصة..."
            />
          </div>
          <button
            type="button"
            onClick={createDraft}
            disabled={busyKey === "create"}
            className="ktra-btn ktra-btn-primary shrink-0"
          >
            {busyKey === "create" ? "جارٍ الإنشاء…" : "إنشاء مسودة"}
          </button>
        </div>
      </CcCard>

      {preview && (
        <CcCard tone="accent" className="p-4 space-y-2 text-xs">
          <p className="font-bold text-sky-400">معاينة v{preview.draft.version}</p>
          <p className="text-cc-text-muted">{preview.note}</p>
          <PolicyImpact impact={preview} />
        </CcCard>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-cc-text-muted" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-sky-400" />
          <span>جارٍ التحميل…</span>
        </div>
      ) : (
        <div className="space-y-4">
          {policies.map((row) => {
            const draft = drafts[row.id] ?? toDraft(row);
            const isDraft = row.status === "draft";
            const busy = Boolean(busyKey && busyKey.split(":")[1] === String(row.id));
            return (
              <CcCard
                key={row.id}
                tone={row.effective_state === "current" ? "accent" : "default"}
                className="space-y-3 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-bold text-cc-text">
                    سياسة v{row.version} · {row.plan ? `خطة «${row.plan}»` : "عامة لكل الخطط"} · {row.billing_tenant_name}
                  </p>
                  <CcPill tone={policyEffectiveStateTone(row.effective_state)} dot>
                    {POLICY_EFFECTIVE_STATE_LABEL[row.effective_state]}
                  </CcPill>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
                  <label className="space-y-1">
                    <span className="text-cc-text-muted">{FIELD_LABELS.plan}</span>
                    <input
                      className="ktra-input h-8 w-full"
                      value={draft.plan}
                      disabled={!isDraft}
                      maxLength={50}
                      placeholder="فارغ = عامة"
                      onChange={(event) => updateDraft(row, { plan: event.target.value })}
                    />
                  </label>
                  {NUMBER_FIELDS.map((field) => (
                    <label key={field} className="space-y-1">
                      <span className="text-cc-text-muted">{FIELD_LABELS[field]}</span>
                      <input
                        className="ktra-input h-8 w-full"
                        value={draft[field]}
                        disabled={!isDraft}
                        inputMode="decimal"
                        onChange={(event) => updateDraft(row, { [field]: event.target.value })}
                      />
                    </label>
                  ))}
                </div>
                <div className="grid gap-2 text-xs sm:grid-cols-2">
                  {(["fixed_fee_product", "overage_product"] as const).map((field) => (
                    <div key={field} className="space-y-1">
                      <span className="text-cc-text-muted">{FIELD_LABELS[`${field}_id`]}</span>
                      {isDraft ? (
                        <BillingProductPicker
                          policyId={row.id}
                          value={draft[field]?.id ?? null}
                          valueLabel={draft[field]?.name ?? null}
                          onChange={(product) => updateDraft(row, {
                            [field]: product ? { id: product.id, name: product.name } : null,
                          })}
                          placeholder="ابحث عن صنف خدمي في شركة الفوترة..."
                          disabled={busy}
                        />
                      ) : (
                        <p className="py-1.5 text-cc-text">{draft[field]?.name ?? "—"}</p>
                      )}
                    </div>
                  ))}
                </div>
                <p className="text-[11px] text-cc-text-muted">
                  سريان: {row.effective_from ? formatDateValue(row.effective_from) : "—"}
                  {row.effective_to && ` حتى ${formatDateValue(row.effective_to)}`}
                  {row.activated_at && ` · فُعّلت ${formatDateValue(row.activated_at)}`}
                  {row.activation_reason && ` · السبب: ${row.activation_reason}`}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  {isDraft && (
                    <button type="button" disabled={busy} onClick={() => saveDraft(row)} className="ktra-btn">
                      <Save className="h-3.5 w-3.5" /> حفظ
                    </button>
                  )}
                  <button type="button" disabled={busy} onClick={() => void previewRow(row)} className="ktra-btn">
                    <Info className="h-3.5 w-3.5" /> معاينة الأثر
                  </button>
                  {!isDraft && (
                    <button type="button" disabled={busy} onClick={() => clone(row)} className="ktra-btn">
                      <Copy className="h-3.5 w-3.5" /> استنساخ إلى مسودة
                    </button>
                  )}
                  {isDraft && (
                    <>
                      <input
                        className="ktra-input h-8 flex-1"
                        placeholder="سبب التفعيل"
                        value={reasons[row.id] ?? ""}
                        onChange={(event) => setReasons((current) => ({ ...current, [row.id]: event.target.value }))}
                      />
                      <label className="flex items-center gap-1 text-xs text-cc-text-muted">
                        يسري من
                        <input
                          type="date"
                          className="ktra-input h-8"
                          min={localIsoDate()}
                          value={effectiveDates[row.id] ?? ""}
                          onChange={(event) => setEffectiveDates((current) => ({ ...current, [row.id]: event.target.value }))}
                        />
                      </label>
                      <button type="button" disabled={busy} onClick={() => void activate(row)} className="ktra-btn ktra-btn-primary">
                        <PlayCircle className="h-3.5 w-3.5" /> تفعيل
                      </button>
                    </>
                  )}
                </div>
              </CcCard>
            );
          })}
          {policies.length === 0 && <CcEmpty title="لا توجد سياسة بعد." />}
        </div>
      )}
    </section>
  );
};

// `plain`: حوارُ التأكيد يُرسَم من `ConfirmContext` في جذر التطبيق **خارجَ** `.ops-shell`،
// فجدولُ `Cc*` الكحليُّ هناك نصٌّ فاتحٌ فوق حوارٍ فاتح. الحوارُ يبقى على الأسطر المجرّدة.
const PolicyImpact: React.FC<{ impact: SubscriptionPolicyPreview; plain?: boolean }> = ({
  impact,
  plain = false,
}: {
  impact: SubscriptionPolicyPreview;
  plain?: boolean;
}) => {
  const describe = (field: string, value: SubscriptionPolicyDiffValue["active"], side: "active" | "draft"): string => {
    const policy = side === "active" ? impact.active : impact.draft;
    if (side === "active" && !policy) return "لا توجد نسخة سارية";
    if (field === "plan") return value ? `«${value}»` : "عامة";
    if (field === "billing_tenant_id") return policy?.billing_tenant_name ?? "—";
    if (field === "fixed_fee_product_id") return policy?.fixed_fee_product_name ?? "—";
    if (field === "overage_product_id") return policy?.overage_product_name ?? "—";
    return formatNumber(value, { fallback: "—" });
  };

  const diffEntries = Object.entries(impact.diff) as [string, SubscriptionPolicyDiffValue][];

  if (plain) {
    return (
      <div className="mt-2 space-y-1">
        {diffEntries.length === 0 && <p>لا فروق عن النسخة السارية.</p>}
        {diffEntries.map(([field, values]) => (
          <p key={field}>
            {FIELD_LABELS[field] ?? field}: {describe(field, values.active, "active")} ← {describe(field, values.draft, "draft")}
          </p>
        ))}
      </div>
    );
  }

  if (diffEntries.length === 0) {
    return <p className="mt-2 text-xs text-cc-text-muted">لا فروق عن النسخة السارية.</p>;
  }

  return (
    <div className="mt-2">
      <CcTable>
        <CcThead>
          <tr>
            <CcTh>الحقل</CcTh>
            <CcTh>النسخة السارية</CcTh>
            <CcTh>النسخة المسودة</CcTh>
          </tr>
        </CcThead>
        <tbody>
          {diffEntries.map(([field, values]) => (
            <CcTr key={field}>
              <CcTd className="font-semibold text-cc-text">{FIELD_LABELS[field] ?? field}</CcTd>
              <CcTd className="font-mono text-cc-text-muted">{describe(field, values.active, "active")}</CcTd>
              <CcTd className="font-mono font-bold text-sky-400">{describe(field, values.draft, "draft")}</CcTd>
            </CcTr>
          ))}
        </tbody>
      </CcTable>
    </div>
  );
};
