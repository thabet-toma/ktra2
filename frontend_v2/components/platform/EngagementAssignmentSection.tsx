import React, { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import {
  assignPlatformEmployee,
  getCustomerAcquisition,
  listAssignmentCandidates,
  listEngagements,
  resumeEngagement,
  revokeEngagement,
  setCustomerAcquisition,
  suspendEngagement,
  transferEngagement,
  type AssignmentCandidateRow,
  type CustomerAcquisitionRow,
  type EngagementKind,
  type EngagementRow,
} from "../../services/platformOpsApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatDateValue } from "../../utils/formatDate";
import {
  ENGAGEMENT_KIND_LABEL,
  ENGAGEMENT_STATUS_LABEL,
  formatCapacityLabel,
  formatOnboardingRemainingLabel,
  getAllowedEngagementActions,
  type EngagementAction,
} from "../../utils/platformHealthAssignment";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

interface Props {
  companyId: number;
}

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لإدارة إسناد هذه الشركة.", "تعذّر إتمام العملية.");

const ACTION_LABEL: Record<EngagementAction, string> = {
  transfer: "نقل",
  suspend: "تعليق",
  resume: "استئناف",
  revoke: "إلغاء",
};

/** الإسناد والطاقة — من يخدم هذه الشركة الآن، ومن جلبها كعميل. منفصلان لا يتبادلان (210-B). */
export const EngagementAssignmentSection: React.FC<Props> = ({ companyId }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [engagements, setEngagements] = useState<EngagementRow[] | null>(null);
  const [candidates, setCandidates] = useState<AssignmentCandidateRow[] | null>(null);
  const [acquisition, setAcquisition] = useState<CustomerAcquisitionRow | null | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<number | "">("");
  const [kind, setKind] = useState<EngagementKind>("standard");
  const [overrideReason, setOverrideReason] = useState("");
  const [showOverride, setShowOverride] = useState(false);
  const [reason, setReason] = useState("");
  const [acquisitionEmployee, setAcquisitionEmployee] = useState<number | "">("");
  const [acquisitionNote, setAcquisitionNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [engagementRows, candidateRows, acquisitionRow] = await Promise.all([
        listEngagements(companyId),
        listAssignmentCandidates(companyId),
        getCustomerAcquisition(companyId),
      ]);
      setEngagements(engagementRows);
      setCandidates(candidateRows);
      setAcquisition(acquisitionRow);
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    setSelectedEmployee(""); setKind("standard"); setOverrideReason(""); setShowOverride(false);
    setReason(""); setAcquisitionEmployee(""); setAcquisitionNote("");
  }, [companyId]);

  const run = async (action: () => Promise<unknown>, okMsg: string): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast(okMsg, "success");
      setReason("");
      setOverrideReason("");
      setShowOverride(false);
      await load();
      return true;
    } catch (cause) {
      const message = displayError(cause);
      if ((cause as { status?: number } | null)?.status === 409) {
        setShowOverride(true);
        await load();
      }
      setError(message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  // المعلَّق ارتباطٌ قائمٌ لا تاريخ: حَسْبُه ضمن السجلّ كان يُخفي أزراره فيتعذّر
  // استئنافه من الشاشة أصلاً، ويعرض نموذج الإسناد فوقه فيُنشئ ارتباطاً ثانياً للشركة.
  const current = engagements?.find((row) => row.status === "active" || row.status === "suspended") ?? null;
  const history = engagements?.filter((row) => row.id !== current?.id) ?? [];

  const assign = () => {
    if (!selectedEmployee) { setError("اختر موظفاً للإسناد."); return; }
    void run(
      () => assignPlatformEmployee(companyId, Number(selectedEmployee), kind, overrideReason || undefined),
      "تم إسناد الموظف لهذه الشركة.",
    );
  };

  const doAction = async (engagement: EngagementRow, action: EngagementAction) => {
    if (action === "resume") {
      await run(() => resumeEngagement(engagement.id), "تم استئناف الارتباط.");
      return;
    }
    const trimmedReason = reason.trim();
    if (!trimmedReason) { setError("السبب مطلوب لهذا الإجراء."); return; }
    if (action === "suspend") {
      await run(() => suspendEngagement(engagement.id, trimmedReason), "تم تعليق الارتباط.");
    } else if (action === "revoke") {
      const confirmed = await confirm({
        title: "إلغاء الارتباط",
        message: "سينتهي إسناد هذا الموظف لهذه الشركة نهائياً — التاريخ يبقى محفوظاً.",
        confirmText: "إلغاء الارتباط",
        danger: true,
      });
      if (!confirmed) return;
      await run(() => revokeEngagement(engagement.id, trimmedReason), "تم إلغاء الارتباط.");
    } else if (action === "transfer") {
      if (!selectedEmployee) { setError("اختر الموظف الجديد قبل النقل."); return; }
      await run(
        () => transferEngagement(engagement.id, Number(selectedEmployee), trimmedReason, overrideReason || undefined),
        "تم نقل الارتباط إلى الموظف الجديد.",
      );
    }
  };

  const saveAcquisition = () => {
    if (!acquisitionEmployee) { setError("اختر موظفاً لتسجيل جالب العميل."); return; }
    void run(
      () => setCustomerAcquisition(companyId, Number(acquisitionEmployee), undefined, acquisitionNote || undefined),
      "تم تسجيل اكتساب العميل.",
    );
  };

  return (
    <section aria-label="الإسناد والطاقة" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
      <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">الإسناد والطاقة</h3>
      <p className="mb-3 text-[11px] ktra-text-soft">
        من يخدم هذه الشركة الآن ومن جلبها كعميل — سجلّان مستقلّان، النقل لا يمسّ الثاني.
      </p>

      {error && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
          <button type="button" onClick={() => void load()} className="mr-2 underline">إعادة المحاولة</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm ktra-text-soft" role="status">
          <Loader2 className="h-4 w-4 animate-spin" /> جارٍ تحميل بيانات الإسناد…
        </div>
      ) : (
        <>
          <div className="text-sm">
            {current ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-[var(--color-text)]">
                  الموظف الحالي: {current.employee_name} ({ENGAGEMENT_KIND_LABEL[current.kind]})
                </span>
                <span
                  className={
                    current.status === "suspended"
                      ? "text-xs font-bold text-amber-700"
                      : "text-xs ktra-text-soft"
                  }
                >
                  {ENGAGEMENT_STATUS_LABEL[current.status]}
                </span>
                {current.kind === "onboarding" && (
                  <span className="text-xs font-semibold text-amber-600">
                    {formatOnboardingRemainingLabel(current.onboarding_expires_at)}
                  </span>
                )}
              </div>
            ) : (
              <p className="ktra-text-soft">لا موظف مُسنَد لهذه الشركة حالياً.</p>
            )}
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <label className="space-y-1 text-xs">
              <span className="font-bold ktra-text-soft">{current ? "الموظف الجديد (للنقل)" : "الموظف"}</span>
              <select
                className="ktra-input h-8 w-full"
                value={selectedEmployee}
                disabled={busy}
                onChange={(event) => setSelectedEmployee(event.target.value ? Number(event.target.value) : "")}
              >
                <option value="">اختر موظفاً…</option>
                {candidates?.map((row) => (
                  <option key={row.employee} value={row.employee}>
                    {row.employee_name} — {formatCapacityLabel(row.load, row.capacity_target)}
                    {row.would_exceed_capacity ? " (يتجاوز الطاقة)" : ""}
                  </option>
                ))}
              </select>
            </label>
            {!current && (
              <label className="space-y-1 text-xs">
                <span className="font-bold ktra-text-soft">نوع الإسناد</span>
                <select
                  className="ktra-input h-8 w-full"
                  value={kind}
                  disabled={busy}
                  onChange={(event) => setKind(event.target.value as EngagementKind)}
                >
                  <option value="standard">عادي (يلزمه فحص تأسيسي معتمد)</option>
                  <option value="onboarding">تهيئة مؤقتة (بلا فحص، لمدة محدودة)</option>
                </select>
              </label>
            )}
          </div>

          {showOverride && (
            <input
              className="ktra-input mt-2 h-8 w-full"
              placeholder="سبب تجاوز الطاقة المستهدفة (إلزامي للمتابعة رغم التجاوز)"
              value={overrideReason}
              disabled={busy}
              onChange={(event) => setOverrideReason(event.target.value)}
            />
          )}

          {(current ? getAllowedEngagementActions(current.status).some((a) => a !== "resume") : true) && (
            <input
              className="ktra-input mt-2 h-8 w-full"
              placeholder="سبب الإجراء (تعليق / إلغاء / نقل)"
              value={reason}
              disabled={busy}
              onChange={(event) => setReason(event.target.value)}
            />
          )}

          <div className="mt-3 flex flex-wrap gap-2">
            {!current ? (
              <button type="button" onClick={assign} disabled={busy || !selectedEmployee} className="ktra-btn ktra-btn-primary">
                إسناد
              </button>
            ) : (
              getAllowedEngagementActions(current.status).map((action) => (
                <button
                  key={action}
                  type="button"
                  disabled={busy}
                  onClick={() => void doAction(current, action)}
                  className={
                    action === "revoke"
                      ? "rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-50"
                      : "ktra-btn disabled:opacity-50"
                  }
                >
                  {ACTION_LABEL[action]}
                </button>
              ))
            )}
          </div>

          {history.length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-xs font-bold ktra-text-soft">سجلّ الارتباطات السابقة</p>
              <ul className="space-y-1 text-xs">
                {history.map((row) => (
                  <li key={row.id} className="border-t border-[var(--color-border)] pt-1">
                    {row.employee_name} — {row.status_display}
                    {row.ended_at && <span className="ktra-text-soft"> · انتهى {formatDateValue(row.ended_at)}</span>}
                    {row.end_reason && <span className="ktra-text-soft"> · {row.end_reason}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 rounded border border-[var(--color-border)] p-2">
            <p className="mb-2 text-xs font-bold ktra-text-soft">اكتساب العميل — مستقلّ عمّن يخدمها الآن</p>
            {acquisition ? (
              <p className="text-xs">
                جلبها: <span className="font-semibold">{acquisition.acquired_by_name}</span>
                {" · "}{formatDateValue(acquisition.acquired_at)}
                {acquisition.note && <span className="ktra-text-soft"> · {acquisition.note}</span>}
              </p>
            ) : (
              <p className="text-xs ktra-text-soft">لم يُسجَّل بعد من جلب هذه الشركة كعميل.</p>
            )}
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <select
                className="ktra-input h-8 w-full"
                value={acquisitionEmployee}
                disabled={busy}
                onChange={(event) => setAcquisitionEmployee(event.target.value ? Number(event.target.value) : "")}
              >
                <option value="">اختر موظفاً…</option>
                {candidates?.map((row) => (
                  <option key={row.employee} value={row.employee}>{row.employee_name}</option>
                ))}
              </select>
              <input
                className="ktra-input h-8 w-full"
                placeholder="ملاحظة (اختياري)"
                value={acquisitionNote}
                disabled={busy}
                onChange={(event) => setAcquisitionNote(event.target.value)}
              />
            </div>
            <button
              type="button"
              onClick={saveAcquisition}
              disabled={busy || !acquisitionEmployee}
              className="ktra-btn mt-2"
            >
              {acquisition ? "تعديل جالب العميل" : "تسجيل جالب العميل"}
            </button>
          </div>
        </>
      )}
    </section>
  );
};
