import React, { useCallback, useEffect, useState } from "react";
import { Loader2, RotateCcw } from "lucide-react";

import {
  approveHealthCheck,
  compareHealthBaseline,
  convertHealthCheckItemToWorkOrder,
  createHealthCheckDraft,
  listHealthChecks,
  refreshHealthCheckAutoItems,
  updateHealthCheck,
  updateHealthCheckItem,
  type CompanyHealthCheckItemRow,
  type CompanyHealthCheckRow,
  type HealthBaselineComparison,
  type HealthCheckComplexity,
} from "../../services/platformOpsApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatDateValue } from "../../utils/formatDate";
import {
  HEALTH_CHECK_COMPLEXITY_LABEL,
  HEALTH_CHECK_ITEM_STATUS_LABEL,
  canApproveHealthCheck,
  missingMandatoryEvidenceCodes,
} from "../../utils/platformHealthAssignment";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

interface Props {
  companyId: number;
}

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لإدارة فحوص صحة هذه الشركة.", "تعذّر إتمام العملية.");

/**
 * صحة الدفاتر والتشغيل — فحصٌ يُعتمَد ويبقى تاريخُه، منفصلٌ تماماً عن درجتي
 * «صحة الخدمة» و«تعاون الزبون» المشتقّتين حيّاً في القسم الآخر أعلى هذا. (210-B)
 */
export const CompanyHealthCheckSection: React.FC<Props> = ({ companyId }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [checks, setChecks] = useState<CompanyHealthCheckRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [noteDraft, setNoteDraft] = useState<Record<number, string>>({});
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [comparison, setComparison] = useState<HealthBaselineComparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setChecks(await listHealthChecks(companyId));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setLoading(false);
    }
  }, [companyId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setComparisonOpen(false); setComparison(null); }, [companyId]);

  const run = async (action: () => Promise<unknown>, okMsg: string): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast(okMsg, "success");
      await load();
      return true;
    } catch (cause) {
      const message = displayError(cause);
      if ((cause as { status?: number } | null)?.status === 409) await load();
      setError(message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const current = checks && checks.length > 0 ? checks[0] : null;

  const startDraft = () =>
    void run(() => createHealthCheckDraft(companyId), "بدأ فحص صحة تأسيسي جديد.");

  const setComplexity = (check: CompanyHealthCheckRow, complexity: HealthCheckComplexity) =>
    void run(() => updateHealthCheck(check.id, { complexity }), "تم تحديث تقدير التعقيد.");

  const setItemNote = (check: CompanyHealthCheckRow, item: CompanyHealthCheckItemRow) => {
    const note = (noteDraft[item.id] ?? "").trim();
    if (!note) { setError("اكتب ملاحظة الدليل قبل الحفظ."); return; }
    void run(
      () => updateHealthCheckItem(check.id, item.id, { evidence_note: note }),
      "تم حفظ ملاحظة الدليل.",
    );
  };

  const setItemStatus = (check: CompanyHealthCheckRow, item: CompanyHealthCheckItemRow, status: string) =>
    void run(
      () => updateHealthCheckItem(check.id, item.id, { status: status as CompanyHealthCheckItemRow["status"] }),
      "تم تحديث حالة البند.",
    );

  const convertItem = async (check: CompanyHealthCheckRow, item: CompanyHealthCheckItemRow) => {
    const confirmed = await confirm({
      title: "تحويل البند إلى أمر عمل",
      message: "سيُنشأ أمر عمل لمعالجة هذا البند ويرتبط به.",
      confirmText: "تحويل",
    });
    if (!confirmed) return;
    await run(() => convertHealthCheckItemToWorkOrder(check.id, item.id), "تم إنشاء أمر عمل لهذا البند.");
  };

  const approve = async (check: CompanyHealthCheckRow) => {
    const confirmed = await confirm({
      title: "اعتماد فحص الصحة",
      message: "بعد الاعتماد لا يمكن تعديل الفحص أو بنوده — يبقى أساساً ثابتاً للمقارنة والإسناد.",
      confirmText: "اعتماد",
    });
    if (!confirmed) return;
    await run(() => approveHealthCheck(check.id), "تم اعتماد الفحص.");
  };

  const loadComparison = useCallback(async () => {
    setComparisonLoading(true);
    setError(null);
    try {
      setComparison(await compareHealthBaseline(companyId));
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setComparisonLoading(false);
    }
  }, [companyId]);

  const toggleComparison = () => {
    const next = !comparisonOpen;
    setComparisonOpen(next);
    if (next && comparison === null) void loadComparison();
  };

  return (
    <section aria-label="صحة الدفاتر والتشغيل" className="mt-4 rounded-lg border border-[var(--color-border)] p-3">
      <h3 className="mb-3 text-sm font-bold text-[var(--color-text)]">صحة الدفاتر والتشغيل</h3>
      <p className="mb-3 text-[11px] ktra-text-soft">
        فحصٌ معتمَدٌ يبقى تاريخه — مستقلٌّ تماماً عن درجتي «صحة الخدمة» و«تعاون الزبون» أعلاه.
      </p>

      {error && (
        <div className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
          <button type="button" onClick={() => void load()} className="mr-2 underline">إعادة المحاولة</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm ktra-text-soft" role="status">
          <Loader2 className="h-4 w-4 animate-spin" /> جارٍ تحميل فحص الصحة…
        </div>
      ) : !current ? (
        <div className="py-3 text-sm">
          <p className="mb-2 ktra-text-soft">لا يوجد فحص صحة لهذه الشركة بعد.</p>
          <button type="button" onClick={startDraft} disabled={busy} className="ktra-btn ktra-btn-primary">
            بدء فحص تأسيسي
          </button>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold text-[var(--color-text)]">
              الحالة: {current.status_display} ({current.kind_display})
            </span>
            <span className="text-xs ktra-text-soft">فترة: {formatDateValue(current.period)}</span>
            {current.status === "approved" && current.approved_at && (
              <span className="text-xs ktra-text-soft">
                اعتُمد {formatDateValue(current.approved_at)} بواسطة {current.approved_by_name || "—"}
              </span>
            )}
          </div>

          {current.status === "draft" && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span className="font-bold ktra-text-soft">تقدير التعقيد:</span>
              {(["low", "medium", "high"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  disabled={busy}
                  onClick={() => setComplexity(current, value)}
                  className={`rounded-full border px-2 py-0.5 ${
                    current.complexity === value
                      ? "border-emerald-600 bg-emerald-50 font-bold text-emerald-700"
                      : "border-[var(--color-border)]"
                  }`}
                >
                  {HEALTH_CHECK_COMPLEXITY_LABEL[value]}
                </button>
              ))}
            </div>
          )}

          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-xs">
              <thead className="bg-[var(--color-surface-2)] ktra-text-soft">
                <tr>
                  <th className="px-2 py-1 text-right">البند</th>
                  <th className="px-2 py-1 text-right">الحالة</th>
                  <th className="px-2 py-1 text-right">الدليل</th>
                  {current.status === "draft" && <th className="px-2 py-1 text-right">إجراء</th>}
                </tr>
              </thead>
              <tbody>
                {current.items.map((item) => (
                  <tr key={item.id} className="border-t border-[var(--color-border)]">
                    <td className="px-2 py-1">
                      {item.code}
                      {item.mandatory && <span className="mr-1 text-red-600">*</span>}
                    </td>
                    <td className="px-2 py-1">
                      {current.status === "draft" ? (
                        <select
                          className="ktra-input h-7 w-full"
                          value={item.status}
                          disabled={busy}
                          onChange={(event) => setItemStatus(current, item, event.target.value)}
                          aria-label={`حالة بند ${item.code}`}
                        >
                          {Object.entries(HEALTH_CHECK_ITEM_STATUS_LABEL).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </select>
                      ) : HEALTH_CHECK_ITEM_STATUS_LABEL[item.status] ?? item.status}
                    </td>
                    <td className="px-2 py-1">
                      {item.evidence_value !== null && <span>{item.evidence_value}</span>}
                      {item.evidence_note && <span className="ktra-text-soft"> · {item.evidence_note}</span>}
                      {current.status === "draft" && !item.evidence_note && (
                        <input
                          className="ktra-input mt-1 h-7 w-full"
                          placeholder="ملاحظة الدليل"
                          value={noteDraft[item.id] ?? ""}
                          disabled={busy}
                          onChange={(event) => setNoteDraft((prev) => ({ ...prev, [item.id]: event.target.value }))}
                          onBlur={() => noteDraft[item.id]?.trim() && setItemNote(current, item)}
                        />
                      )}
                    </td>
                    {current.status === "draft" && (
                      <td className="px-2 py-1">
                        {item.work_order ? (
                          <span className="ktra-text-soft">مرتبطٌ بأمر عمل</span>
                        ) : (item.status === "follow_up" || item.status === "risk") ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void convertItem(current, item)}
                            className="ktra-iconbtn"
                          >
                            تحويل لأمر عمل
                          </button>
                        ) : null}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {current.status === "draft" && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void run(() => refreshHealthCheckAutoItems(current.id), "تم تحديث البنود الآلية.")}
                disabled={busy}
                className="ktra-btn"
              >
                <RotateCcw className="h-3.5 w-3.5" /> تحديث البنود الآلية
              </button>
              <button
                type="button"
                onClick={() => void approve(current)}
                disabled={busy || !canApproveHealthCheck(current, current.items)}
                title={
                  canApproveHealthCheck(current, current.items)
                    ? undefined
                    : `ينقص الاعتماد: ${missingMandatoryEvidenceCodes(current.items).join("، ") || "قدّر التعقيد أولاً"}`
                }
                className="ktra-btn ktra-btn-primary disabled:opacity-50"
              >
                اعتماد الفحص
              </button>
            </div>
          )}

          <div className="mt-4">
            <button
              type="button"
              onClick={toggleComparison}
              aria-expanded={comparisonOpen}
              className="text-xs font-bold ktra-text-soft underline"
            >
              مقارنة بآخر فحص تأسيسي معتمد
            </button>
            {comparisonOpen && (
              comparisonLoading ? (
                <div className="flex items-center gap-2 py-2 text-xs ktra-text-soft">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> جارٍ التحميل…
                </div>
              ) : !comparison || !comparison.baseline ? (
                <p className="py-2 text-xs ktra-text-soft">لا يوجد فحصان تأسيسيان معتمدان بعد للمقارنة.</p>
              ) : comparison.changes.length === 0 ? (
                <p className="py-2 text-xs ktra-text-soft">لا تغييرات بين الفحصين التأسيسيين المعتمدين.</p>
              ) : (
                <ul className="mt-2 space-y-1 text-xs">
                  {comparison.changes.map((change) => (
                    <li key={change.code}>
                      {change.code}: {change.from_status ? HEALTH_CHECK_ITEM_STATUS_LABEL[change.from_status] : "—"}
                      {" ← "}
                      {HEALTH_CHECK_ITEM_STATUS_LABEL[change.to_status]}
                    </li>
                  ))}
                </ul>
              )
            )}
          </div>
        </>
      )}
    </section>
  );
};
