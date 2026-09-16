import React, { useCallback, useEffect, useState } from "react";
import { Copy, Info, Loader2, PlayCircle, Plus, Save } from "lucide-react";

import {
  activateEmployeeCompensationPolicy,
  activatePerformanceEvaluationPolicy,
  cloneEmployeeCompensationPolicy,
  clonePerformanceEvaluationPolicy,
  createEmployeeCompensationPolicyDraft,
  createPerformanceEvaluationPolicyDraft,
  listEmployeeCompensationPolicies,
  listPerformanceEvaluationPolicies,
  previewEmployeeCompensationPolicy,
  previewPerformanceEvaluationPolicy,
  updateEmployeeCompensationPolicyDraft,
  updatePerformanceEvaluationPolicyDraft,
  PILOT_AXES,
  PILOT_AXIS_LABELS,
  PILOT_POLICY_EFFECTIVE_STATE_LABEL,
  type EmployeeCompensationPolicyRow,
  type PerformanceEvaluationPolicyRow,
  type PilotAxisKey,
  type PilotPolicyEffectiveState,
  type PolicyPreview,
} from "../../services/platformPilotApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { formatDateValue, todayIso } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { type CcTone } from "../../utils/ccTone";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcSkeleton,
  CcTabs,
} from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لإدارة إعدادات الأداء والتعويض.", "تعذّر إتمام العملية.");

const rowBusyKey = (action: string, rowId: number) => `${action}:${rowId}`;

const EFFECTIVE_STATE_TONE: Record<PilotPolicyEffectiveState, CcTone> = {
  draft: "neutral",
  scheduled: "accent",
  current: "success",
  retired: "neutral",
};

type PerfDraft = {
  specialty: string;
  weights: Record<PilotAxisKey, string>;
  min_sample_size: string;
  review_grace_period_hours: string;
  presence_min_hours_per_day: string;
  presence_day_cap_percent: string;
};

function toPerfDraft(row: PerformanceEvaluationPolicyRow): PerfDraft {
  return {
    specialty: row.specialty,
    weights: PILOT_AXES.reduce((acc, axis) => {
      acc[axis] = String(row.weights[axis] ?? 0);
      return acc;
    }, {} as Record<PilotAxisKey, string>),
    min_sample_size: String(row.min_sample_size),
    review_grace_period_hours: String(row.review_grace_period_hours),
    presence_min_hours_per_day: String(row.presence_min_hours_per_day),
    presence_day_cap_percent: String(row.presence_day_cap_percent),
  };
}

const weightsSum = (weights: Record<PilotAxisKey, string>): number =>
  PILOT_AXES.reduce((sum, axis) => sum + (Number(weights[axis]) || 0), 0);

/** إعدادات محاور الأداء (40/30/20/10): نسخ مؤرَّخة بمسودة ومعاينة وتفعيل بسبب وتاريخ سريان (§٥، §٨). */
const PerformancePolicySection: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [rows, setRows] = useState<PerformanceEvaluationPolicyRow[]>([]);
  const [drafts, setDrafts] = useState<Record<number, PerfDraft>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [effectiveDates, setEffectiveDates] = useState<Record<number, string>>({});
  const [preview, setPreview] = useState<PolicyPreview<PerformanceEvaluationPolicyRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listPerformanceEvaluationPolicies();
      setRows(list);
      setDrafts(Object.fromEntries(list.map((row) => [row.id, toPerfDraft(row)])));
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
      if ((cause as { status?: number } | null)?.status === 409) await load();
      setError(message);
    } finally {
      setBusyKey(null);
    }
  };

  const updateDraft = (row: PerformanceEvaluationPolicyRow, patch: Partial<PerfDraft>) =>
    setDrafts((current) => ({ ...current, [row.id]: { ...(current[row.id] ?? toPerfDraft(row)), ...patch } }));

  const createDraft = () => run(
    "create",
    () => createPerformanceEvaluationPolicyDraft({}),
    "تم إنشاء مسودة سياسة تقييم جديدة — عدّل الأوزان ثم فعّلها.",
  );

  const saveDraft = (row: PerformanceEvaluationPolicyRow) => {
    const draft = drafts[row.id];
    if (!draft) return;
    if (weightsSum(draft.weights) !== 100) {
      setError("مجموع أوزان المحاور الأربعة يجب أن يساوي 100% بالضبط.");
      return;
    }
    void run(
      rowBusyKey("save", row.id),
      () => updatePerformanceEvaluationPolicyDraft(row.id, {
        specialty: draft.specialty.trim(),
        weights: draft.weights,
        min_sample_size: Number(draft.min_sample_size),
        review_grace_period_hours: Number(draft.review_grace_period_hours),
        presence_min_hours_per_day: draft.presence_min_hours_per_day.trim(),
        presence_day_cap_percent: Number(draft.presence_day_cap_percent),
      }),
      "تم حفظ المسودة.",
    );
  };

  const clone = (row: PerformanceEvaluationPolicyRow) =>
    run(rowBusyKey("clone", row.id), () => clonePerformanceEvaluationPolicy(row.id), "تم استنساخ مسودة جديدة من هذه النسخة.");

  const previewRow = async (row: PerformanceEvaluationPolicyRow) => {
    setBusyKey(rowBusyKey("preview", row.id));
    setError(null);
    try {
      setPreview(await previewPerformanceEvaluationPolicy(row.id));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setBusyKey(null);
    }
  };

  const activate = async (row: PerformanceEvaluationPolicyRow) => {
    const draft = drafts[row.id];
    if (draft && weightsSum(draft.weights) !== 100) {
      setError("مجموع أوزان المحاور الأربعة يجب أن يساوي 100% بالضبط قبل التفعيل.");
      return;
    }
    const reason = (reasons[row.id] ?? "").trim();
    if (!reason) { setError("سبب التفعيل مطلوب."); return; }
    const chosenDate = effectiveDates[row.id] ?? "";
    const effectiveFrom = chosenDate && chosenDate > todayIso() ? `${chosenDate}T00:00:00` : undefined;
    try {
      const impact = await previewPerformanceEvaluationPolicy(row.id);
      setPreview(impact);
      const confirmed = await confirm({
        title: `تفعيل سياسة التقييم v${row.version}`,
        message: effectiveFrom ? `تسري من ${formatDateValue(chosenDate)}. ${impact.note}` : `تسري فوراً. ${impact.note}`,
        confirmText: effectiveFrom ? "جدولة السياسة" : "تفعيل السياسة",
        danger: false,
      });
      if (!confirmed) return;
      await run(
        rowBusyKey("activate", row.id),
        () => activatePerformanceEvaluationPolicy(row.id, reason, effectiveFrom),
        effectiveFrom ? `جُدولت النسخة v${row.version}.` : `تم تفعيل النسخة v${row.version}.`,
      );
    } catch (cause) {
      setError(displayError(cause));
    }
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-400" role="alert">
          {error}
        </div>
      )}

      <CcSectionTitle
        title="سياسات تقييم الأداء"
        badge={rows.length > 0 ? rows.length : undefined}
        action={
          <button
            type="button"
            onClick={createDraft}
            disabled={busyKey === "create"}
            className="ktra-btn ktra-btn-primary"
          >
            <Plus className="h-3.5 w-3.5" /> مسودة سياسة تقييم جديدة
          </button>
        }
      />

      {preview && (
        <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-3 text-xs text-sky-300">
          <p className="font-semibold">معاينة v{preview.draft.version}</p>
          <p>{preview.note}</p>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 py-2 text-sm text-cc-text-muted">
            <Loader2 className="h-4 w-4 animate-spin text-sky-400" /> جارٍ التحميل…
          </div>
          <CcSkeleton variant="card" count={2} />
        </div>
      ) : rows.length === 0 ? (
        <CcEmpty
          title="لا توجد سياسة تقييم بعد"
          hint="أوزانُ المحاور الافتراضيّة المضبوطة في الخادم مطبَّقة ضمنيّاً."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((row) => {
            const draft = drafts[row.id] ?? toPerfDraft(row);
            const isDraft = row.status === "draft";
            const busy = Boolean(busyKey && busyKey.split(":")[1] === String(row.id));
            const sum = weightsSum(draft.weights);
            return (
              <CcCard key={row.id} className="p-5 space-y-4">
                <CcSectionTitle
                  title={`سياسة تقييم v${row.version} · ${row.specialty ? `تخصص «${row.specialty}»` : "عامة لكل التخصصات"}`}
                  action={
                    <CcPill tone={EFFECTIVE_STATE_TONE[row.effective_state]} dot>
                      {PILOT_POLICY_EFFECTIVE_STATE_LABEL[row.effective_state]}
                    </CcPill>
                  }
                />
                <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                  {PILOT_AXES.map((axis) => (
                    <label key={axis} className="space-y-1">
                      <span className="text-cc-text-muted">{PILOT_AXIS_LABELS[axis]} (%)</span>
                      <input
                        className="ktra-input h-8 w-full"
                        value={draft.weights[axis]}
                        disabled={!isDraft}
                        inputMode="decimal"
                        onChange={(event) => updateDraft(row, { weights: { ...draft.weights, [axis]: event.target.value } })}
                      />
                    </label>
                  ))}
                </div>
                <p className={`text-[11px] font-semibold ${sum === 100 ? "text-emerald-400" : "text-rose-400"}`}>
                  مجموع الأوزان: {formatNumber(sum)}% {sum !== 100 && "— يجب أن يساوي 100% لحفظ المسودة أو تفعيلها"}
                </p>
                <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                  <label className="space-y-1">
                    <span className="text-cc-text-muted">الحد الأدنى لحجم العينة</span>
                    <input
                      className="ktra-input h-8 w-full" value={draft.min_sample_size} disabled={!isDraft}
                      inputMode="numeric"
                      onChange={(event) => updateDraft(row, { min_sample_size: event.target.value })}
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="text-cc-text-muted">مهلة المراجعة قبل الإغلاق (ساعة)</span>
                    <input
                      className="ktra-input h-8 w-full" value={draft.review_grace_period_hours} disabled={!isDraft}
                      inputMode="numeric"
                      onChange={(event) => updateDraft(row, { review_grace_period_hours: event.target.value })}
                    />
                  </label>
                  {/* عتبةُ الحضورِ اليوميّةُ وسقفُها (#212 212-D): يُضبَطان من هنا
                      كي لا يكون حقلا السياسةِ حبيسَي افتراضِ قاعدةِ البيانات. */}
                  <label className="space-y-1">
                    <span className="text-cc-text-muted">الحد الأدنى لساعات الحضور اليومي</span>
                    <input
                      className="ktra-input h-8 w-full" value={draft.presence_min_hours_per_day} disabled={!isDraft}
                      inputMode="decimal"
                      onChange={(event) => updateDraft(row, { presence_min_hours_per_day: event.target.value })}
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="text-cc-text-muted">سقف درجة اليوم (%)</span>
                    <input
                      className="ktra-input h-8 w-full" value={draft.presence_day_cap_percent} disabled={!isDraft}
                      inputMode="numeric"
                      onChange={(event) => updateDraft(row, { presence_day_cap_percent: event.target.value })}
                    />
                  </label>
                </div>
                <p className="text-[11px] text-cc-text-muted">
                  حضورٌ دون العتبة يخصم من الدرجة المركَّبة، وما زاد عليها يرفعها حتى السقف؛
                  وعتبةُ صفرٍ تُطفئ أثرَ الحضور كلَّه.
                </p>
                <p className="text-[11px] text-cc-text-muted">
                  سريان: {row.effective_from ? formatDateValue(row.effective_from) : "—"}
                  {row.effective_to && ` حتى ${formatDateValue(row.effective_to)}`}
                  {row.activation_reason && ` · السبب: ${row.activation_reason}`}
                </p>
                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-cc-border">
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
                        className="ktra-input h-8 flex-1 min-w-[140px]" placeholder="سبب التفعيل"
                        value={reasons[row.id] ?? ""}
                        onChange={(event) => setReasons((current) => ({ ...current, [row.id]: event.target.value }))}
                      />
                      <label className="flex items-center gap-1.5 text-xs text-cc-text-muted">
                        يسري من
                        <input
                          type="date" className="ktra-input h-8" min={todayIso()}
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
        </div>
      )}
    </div>
  );
};

type CompDraft = {
  employee: string;
  base_salary: string;
  daily_hours: string;
  weekly_days: string;
  acquisition_commission_amount: string;
  acquisition_commission_months: string;
  accrual_day_of_month: string;
  pay_terms_note: string;
};

function toCompDraft(row: EmployeeCompensationPolicyRow): CompDraft {
  return {
    employee: row.employee ? String(row.employee) : "",
    base_salary: row.base_salary,
    daily_hours: row.daily_hours,
    weekly_days: String(row.weekly_days),
    acquisition_commission_amount: row.acquisition_commission_amount,
    acquisition_commission_months: String(row.acquisition_commission_months),
    accrual_day_of_month: String(row.accrual_day_of_month),
    pay_terms_note: row.pay_terms_note ?? "",
  };
}

const COMP_FIELD_LABELS: Record<string, string> = {
  base_salary: "الراتب الأساسي الشهري",
  daily_hours: "ساعات الدوام اليومية",
  weekly_days: "أيام الدوام الأسبوعية",
  acquisition_commission_amount: "عمولة اكتساب العميل الشهرية",
  acquisition_commission_months: "مدة عمولة الاكتساب (أشهر)",
  accrual_day_of_month: "يوم استحقاق إغلاق الشهر",
};

/** إعدادات تعويض الموظف: راتب أساسي وجدول دوام وعمولة اكتساب 100×3 قابلة للتغيير (§٧، §٨). */
const CompensationPolicySection: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [rows, setRows] = useState<EmployeeCompensationPolicyRow[]>([]);
  const [drafts, setDrafts] = useState<Record<number, CompDraft>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [effectiveDates, setEffectiveDates] = useState<Record<number, string>>({});
  const [preview, setPreview] = useState<PolicyPreview<EmployeeCompensationPolicyRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listEmployeeCompensationPolicies();
      setRows(list);
      setDrafts(Object.fromEntries(list.map((row) => [row.id, toCompDraft(row)])));
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
      if ((cause as { status?: number } | null)?.status === 409) await load();
      setError(message);
    } finally {
      setBusyKey(null);
    }
  };

  const updateDraft = (row: EmployeeCompensationPolicyRow, patch: Partial<CompDraft>) =>
    setDrafts((current) => ({ ...current, [row.id]: { ...(current[row.id] ?? toCompDraft(row)), ...patch } }));

  const createDraft = () => run(
    "create",
    () => createEmployeeCompensationPolicyDraft({}),
    "تم إنشاء مسودة سياسة تعويض عامة جديدة — عدّل قيمها ثم فعّلها.",
  );

  const saveDraft = (row: EmployeeCompensationPolicyRow) => {
    const draft = drafts[row.id];
    if (!draft) return;
    void run(
      rowBusyKey("save", row.id),
      () => updateEmployeeCompensationPolicyDraft(row.id, {
        employee: draft.employee ? Number(draft.employee) : null,
        base_salary: draft.base_salary,
        daily_hours: draft.daily_hours,
        weekly_days: Number(draft.weekly_days),
        acquisition_commission_amount: draft.acquisition_commission_amount,
        acquisition_commission_months: Number(draft.acquisition_commission_months),
        accrual_day_of_month: Number(draft.accrual_day_of_month),
        pay_terms_note: draft.pay_terms_note,
      }),
      "تم حفظ المسودة.",
    );
  };

  const clone = (row: EmployeeCompensationPolicyRow) =>
    run(rowBusyKey("clone", row.id), () => cloneEmployeeCompensationPolicy(row.id), "تم استنساخ مسودة جديدة من هذه النسخة.");

  const previewRow = async (row: EmployeeCompensationPolicyRow) => {
    setBusyKey(rowBusyKey("preview", row.id));
    setError(null);
    try {
      setPreview(await previewEmployeeCompensationPolicy(row.id));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setBusyKey(null);
    }
  };

  const activate = async (row: EmployeeCompensationPolicyRow) => {
    const reason = (reasons[row.id] ?? "").trim();
    if (!reason) { setError("سبب التفعيل مطلوب."); return; }
    const chosenDate = effectiveDates[row.id] ?? "";
    const effectiveFrom = chosenDate && chosenDate > todayIso() ? `${chosenDate}T00:00:00` : undefined;
    try {
      const impact = await previewEmployeeCompensationPolicy(row.id);
      setPreview(impact);
      const confirmed = await confirm({
        title: `تفعيل سياسة التعويض v${row.version}`,
        message: effectiveFrom ? `تسري من ${formatDateValue(chosenDate)}. ${impact.note}` : `تسري فوراً. ${impact.note}`,
        confirmText: effectiveFrom ? "جدولة السياسة" : "تفعيل السياسة",
        danger: false,
      });
      if (!confirmed) return;
      await run(
        rowBusyKey("activate", row.id),
        () => activateEmployeeCompensationPolicy(row.id, reason, effectiveFrom),
        effectiveFrom ? `جُدولت النسخة v${row.version}.` : `تم تفعيل النسخة v${row.version}.`,
      );
    } catch (cause) {
      setError(displayError(cause));
    }
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-400" role="alert">
          {error}
        </div>
      )}

      <CcSectionTitle
        title="سياسات تعويض الموظفين"
        badge={rows.length > 0 ? rows.length : undefined}
        action={
          <button
            type="button"
            onClick={createDraft}
            disabled={busyKey === "create"}
            className="ktra-btn ktra-btn-primary"
          >
            <Plus className="h-3.5 w-3.5" /> مسودة سياسة تعويض جديدة
          </button>
        }
      />

      {preview && (
        <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-3 text-xs text-sky-300">
          <p className="font-semibold">معاينة v{preview.draft.version}</p>
          <p>{preview.note}</p>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 py-2 text-sm text-cc-text-muted">
            <Loader2 className="h-4 w-4 animate-spin text-sky-400" /> جارٍ التحميل…
          </div>
          <CcSkeleton variant="card" count={2} />
        </div>
      ) : rows.length === 0 ? (
        <CcEmpty
          title="لا توجد سياسة تعويض بعد"
          hint="قيمُ التعويض الافتراضيّة المضبوطة في الخادم مطبَّقة ضمنيّاً."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((row) => {
            const draft = drafts[row.id] ?? toCompDraft(row);
            const isDraft = row.status === "draft";
            const busy = Boolean(busyKey && busyKey.split(":")[1] === String(row.id));
            return (
              <CcCard key={row.id} className="p-5 space-y-4">
                <CcSectionTitle
                  title={`سياسة تعويض v${row.version} · ${row.employee ? `موظف #${row.employee} (${row.employee_name ?? "—"})` : "عامة لكل الموظفين"}`}
                  action={
                    <CcPill tone={EFFECTIVE_STATE_TONE[row.effective_state]} dot>
                      {PILOT_POLICY_EFFECTIVE_STATE_LABEL[row.effective_state]}
                    </CcPill>
                  }
                />
                <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
                  <label className="space-y-1">
                    <span className="text-cc-text-muted">نطاق: معرّف موظف (فارغ = عامة)</span>
                    <input
                      className="ktra-input h-8 w-full" value={draft.employee} disabled={!isDraft} inputMode="numeric"
                      onChange={(event) => updateDraft(row, { employee: event.target.value })}
                    />
                  </label>
                  {(Object.keys(COMP_FIELD_LABELS) as (keyof CompDraft)[]).map((field) => (
                    <label key={field} className="space-y-1">
                      <span className="text-cc-text-muted">{COMP_FIELD_LABELS[field]}</span>
                      <input
                        className="ktra-input h-8 w-full" value={draft[field]} disabled={!isDraft} inputMode="decimal"
                        onChange={(event) => updateDraft(row, { [field]: event.target.value })}
                      />
                    </label>
                  ))}
                </div>
                <label className="block space-y-1 text-xs">
                  <span className="text-cc-text-muted">
                    شرح شروط الصرف — يقرؤه الموظّف في صفحته الشخصيّة
                  </span>
                  <textarea
                    className="ktra-input min-h-[68px] w-full py-1.5" rows={3} value={draft.pay_terms_note}
                    disabled={!isDraft}
                    placeholder="مثال: الأساسي 400 شيكل، وفوقه عمولة تسويق 5% على كل اشتراك تجلبه، وعمولة اكتساب 100 شيكل شهرياً لثلاثة أشهر عن كل شركة جديدة."
                    onChange={(event) => updateDraft(row, { pay_terms_note: event.target.value })}
                  />
                </label>
                <p className="text-[11px] text-cc-text-muted">
                  سريان: {row.effective_from ? formatDateValue(row.effective_from) : "—"}
                  {row.effective_to && ` حتى ${formatDateValue(row.effective_to)}`}
                  {row.activation_reason && ` · السبب: ${row.activation_reason}`}
                </p>
                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-cc-border">
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
                        className="ktra-input h-8 flex-1 min-w-[140px]" placeholder="سبب التفعيل"
                        value={reasons[row.id] ?? ""}
                        onChange={(event) => setReasons((current) => ({ ...current, [row.id]: event.target.value }))}
                      />
                      <label className="flex items-center gap-1.5 text-xs text-cc-text-muted">
                        يسري من
                        <input
                          type="date" className="ktra-input h-8" min={todayIso()}
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
        </div>
      )}
    </div>
  );
};

/** شاشة إعدادات الأداء (٤٠/٣٠/٢٠/١٠) وإعدادات تعويض الموظف — كلٌّ بنسخٍ مؤرَّخة (210-D، §٥، §٧، §٨). */
export const PilotSettingsPanel: React.FC = () => {
  const [section, setSection] = useState<string>("performance");
  const tabs = [
    { key: "performance", label: "سياسة تقييم الأداء" },
    { key: "compensation", label: "سياسة تعويض الموظف" },
  ];

  return (
    <section className="space-y-6">
      <CcTabs tabs={tabs} active={section} onChange={setSection} />
      {section === "performance" ? <PerformancePolicySection /> : <CompensationPolicySection />}
    </section>
  );
};

export default PilotSettingsPanel;
