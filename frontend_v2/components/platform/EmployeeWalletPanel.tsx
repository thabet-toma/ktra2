import React, { useCallback, useEffect, useState } from "react";
import { Loader2, RotateCcw, Search, Wallet } from "lucide-react";

import { getPlatformOpsDashboard } from "../../services/platformOpsApi";
import {
  WALLET_LINE_NEXT_STATUS,
  WALLET_LINE_STATUS_LABEL,
  adjustCommissionLine,
  adjustSalaryLine,
  getEmployeePilotPerformance,
  getEmployeeWallet,
  reverseCommissionLine,
  reverseSalaryLine,
  transitionCommissionLine,
  transitionSalaryLine,
  type AcquisitionCommissionLineRow,
  type EmployeePilotPerformance,
  type EmployeeSalaryLineRow,
  type EmployeeWalletSummary,
  type WalletLineStatus,
} from "../../services/platformPilotApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { ccScoreTone, type CcTone } from "../../utils/ccTone";
import { PilotAxesTable } from "./PilotAxesTable";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcSectionTitle,
  CcStatTile,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "./ui";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لاستعراض محفظة موظف آخر.", "تعذّر تحميل البيانات.");

const now = new Date();

type WalletLine = EmployeeSalaryLineRow | AcquisitionCommissionLineRow;

const isCommissionLine = (line: WalletLine): line is AcquisitionCommissionLineRow => "acquisition" in line;

const WALLET_STATUS_TONE: Record<WalletLineStatus, CcTone> = {
  pending: "warning",
  eligible: "warning",
  approved: "accent",
  payable: "accent",
  paid: "success",
  reversed: "danger",
};

/** محفظة الموظّف الشهرية وتفصيل محاور تقييمه — «افتح مصدر كلّ سطر» (210-D، §٢، §٥، §٧، §٣٤). */
export const EmployeeWalletPanel: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const [employees, setEmployees] = useState<{ id: number; name: string }[]>([]);
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [wallet, setWallet] = useState<EmployeeWalletSummary | null>(null);
  const [performance, setPerformance] = useState<EmployeePilotPerformance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyLine, setBusyLine] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const dashboard = await getPlatformOpsDashboard();
        setEmployees(dashboard.employees.map((emp) => ({ id: emp.id, name: emp.name })));
      } catch {
        // قائمة الاختيار كماليّة — فشلها لا يمنع إدخال معرّف الموظف يدويّاً لاحقاً.
      }
    })();
  }, []);

  const load = useCallback(async () => {
    if (!employeeId) return;
    setLoading(true);
    setError(null);
    try {
      const [walletData, perfData] = await Promise.all([
        getEmployeeWallet(employeeId, year, month),
        getEmployeePilotPerformance(employeeId, year, month),
      ]);
      setWallet(walletData);
      setPerformance(perfData);
    } catch (cause) {
      setError(displayError(cause));
      setWallet(null);
      setPerformance(null);
    } finally {
      setLoading(false);
    }
  }, [employeeId, year, month]);

  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [adjustAmounts, setAdjustAmounts] = useState<Record<string, string>>({});

  const lineKey = (line: WalletLine) => `${isCommissionLine(line) ? "commission" : "salary"}:${line.id}`;

  const doReverse = async (line: WalletLine) => {
    const key = lineKey(line);
    const reason = (reasons[key] ?? "").trim();
    if (!reason) { setError("سبب العكس مطلوب — اكتبه في حقل السبب بجانب السطر قبل العكس."); return; }
    const confirmed = await confirm({
      title: "عكس سطر مالي",
      message: `سيُعكس مبلغ ${formatNumber(line.amount)} — لن يُحذف السطر الأصلي، بل يُضاف سطرُ عكسٍ ظاهر. هل تريد المتابعة؟`,
      confirmText: "عكس السطر",
      danger: true,
    });
    if (!confirmed) return;
    setBusyLine(`reverse:${key}`);
    setError(null);
    try {
      if (isCommissionLine(line)) {
        await reverseCommissionLine(line.id, reason);
      } else {
        await reverseSalaryLine(line.id, reason);
      }
      toast("تم عكس السطر.", "success");
      await load();
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setBusyLine(null);
    }
  };

  const doTransition = async (line: WalletLine) => {
    const next = WALLET_LINE_NEXT_STATUS[line.status];
    if (!next) return;
    const key = lineKey(line);
    const confirmed = await confirm({
      title: "نقل حالة سطر مالي",
      message: `نقل السطر من «${WALLET_LINE_STATUS_LABEL[line.status]}» إلى «${WALLET_LINE_STATUS_LABEL[next]}».`,
      confirmText: "نقل الحالة",
      danger: false,
    });
    if (!confirmed) return;
    setBusyLine(`transition:${key}`);
    setError(null);
    try {
      if (isCommissionLine(line)) {
        await transitionCommissionLine(line.id, next);
      } else {
        await transitionSalaryLine(line.id, next);
      }
      toast("تم نقل حالة السطر.", "success");
      await load();
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setBusyLine(null);
    }
  };

  const doAdjust = async (line: WalletLine) => {
    const key = lineKey(line);
    const reason = (reasons[key] ?? "").trim();
    const amount = adjustAmounts[key] ?? "";
    if (!reason || !amount) { setError("مبلغ التسوية وسببها مطلوبان."); return; }
    const confirmed = await confirm({
      title: "إضافة سطر تسوية",
      message: `سيُضاف سطرُ تسويةٍ ظاهرٌ بمبلغ ${formatNumber(amount)} إلى جانب السطر الأصلي — لا تعديل ولا حذف عليه.`,
      confirmText: "إضافة التسوية",
      danger: false,
    });
    if (!confirmed) return;
    setBusyLine(`adjust:${key}`);
    setError(null);
    try {
      if (isCommissionLine(line)) {
        await adjustCommissionLine(line.id, amount, reason);
      } else {
        await adjustSalaryLine(line.id, amount, reason);
      }
      toast("تمت إضافة سطر التسوية.", "success");
      await load();
    } catch (cause) {
      setError(displayError(cause));
    } finally {
      setBusyLine(null);
    }
  };

  return (
    <section className="space-y-6">
      <CcSectionTitle title="محفظة الموظّف" />

      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs font-semibold text-rose-400" role="alert">
          {error}
        </div>
      )}

      <CcCard className="p-5">
        <div className="flex flex-wrap items-end gap-4">
          <label className="space-y-1 text-xs">
            <span className="text-cc-text-muted">الموظّف</span>
            <select
              className="ktra-input h-9 min-w-[220px]"
              value={employeeId ?? ""}
              onChange={(event) => setEmployeeId(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">اختر موظّفاً…</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>{emp.name} (#{emp.id})</option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-cc-text-muted">السنة</span>
            <input type="number" className="ktra-input h-9 w-28" value={year} onChange={(event) => setYear(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-cc-text-muted">الشهر</span>
            <input type="number" min={1} max={12} className="ktra-input h-9 w-24" value={month} onChange={(event) => setMonth(Number(event.target.value))} />
          </label>
          <button
            type="button"
            onClick={() => void load()}
            disabled={!employeeId || loading}
            className="ktra-btn ktra-btn-primary"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />} عرض
          </button>
        </div>
      </CcCard>

      {wallet && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <CcCard className="p-4">
              <CcStatTile
                label="مؤكَّد"
                value={wallet.totals.confirmed}
                tone="success"
                icon={<Wallet className="h-5 w-5 text-emerald-400" />}
              />
            </CcCard>
            <CcCard className="p-4">
              <CcStatTile
                label="معلَّق (بانتظار تسجيل الدفع أو الاعتماد)"
                value={wallet.totals.pending}
                tone="warning"
                icon={<Wallet className="h-5 w-5 text-amber-400" />}
              />
            </CcCard>
          </div>

          <WalletLinesTable
            title="سطور الراتب"
            lines={wallet.salary_lines}
            busyLine={busyLine}
            reasons={reasons}
            setReasons={setReasons}
            adjustAmounts={adjustAmounts}
            setAdjustAmounts={setAdjustAmounts}
            onReverse={doReverse}
            onAdjust={doAdjust}
            onTransition={doTransition}
          />

          <WalletLinesTable
            title="سطور عمولة الاكتساب"
            lines={wallet.commission_lines}
            busyLine={busyLine}
            reasons={reasons}
            setReasons={setReasons}
            adjustAmounts={adjustAmounts}
            setAdjustAmounts={setAdjustAmounts}
            onReverse={doReverse}
            onAdjust={doAdjust}
            onTransition={doTransition}
          />
        </div>
      )}

      {performance && (
        <CcCard className="p-5 space-y-4">
          <CcSectionTitle
            title="كيف يُحسب تقييمي؟ — المحاور الأربعة وأوزانُها في السياسة السارية"
            subtitle={`${performance.status_message} · حجم العينة: ${formatNumber(performance.sample_size)} (الحد الأدنى ${formatNumber(performance.min_sample_size)})`}
          />
          {performance.composite_score !== null && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <CcCard className="p-4">
                <CcStatTile
                  label="النتيجة المركّبة"
                  value={`${formatNumber(performance.composite_score)}%`}
                  tone={ccScoreTone(performance.composite_score)}
                />
              </CcCard>
            </div>
          )}
          <PilotAxesTable performance={performance} />
        </CcCard>
      )}
    </section>
  );
};

const WalletLinesTable: React.FC<{
  title: string;
  lines: WalletLine[];
  busyLine: string | null;
  reasons: Record<string, string>;
  setReasons: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  adjustAmounts: Record<string, string>;
  setAdjustAmounts: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  onReverse: (line: WalletLine) => void;
  onAdjust: (line: WalletLine) => void;
  onTransition: (line: WalletLine) => void;
}> = ({ title, lines, busyLine, reasons, setReasons, adjustAmounts, setAdjustAmounts, onReverse, onAdjust, onTransition }) => (
  <CcCard className="p-5 space-y-4">
    <CcSectionTitle title={title} badge={lines.length > 0 ? lines.length : undefined} />
    {lines.length === 0 ? (
      <CcEmpty title="لا سطور لهذا الشهر." />
    ) : (
      <CcTable>
        <CcThead>
          <tr>
            <CcTh>المبلغ</CcTh>
            <CcTh>الحالة</CcTh>
            <CcTh>السبب/المصدر</CcTh>
            <CcTh>تسلسل</CcTh>
            <CcTh>آخر تحديث</CcTh>
            <CcTh>سبب الإجراء</CcTh>
            <CcTh>مبلغ التسوية</CcTh>
            <CcTh></CcTh>
          </tr>
        </CcThead>
        <tbody>
          {lines.map((line) => {
            const key = `${isCommissionLine(line) ? "commission" : "salary"}:${line.id}`;
            return (
              <CcTr key={key}>
                <CcTd className="font-semibold tabular-nums">{formatNumber(line.amount)}</CcTd>
                <CcTd>
                  <CcPill
                    tone={WALLET_STATUS_TONE[line.status] || "neutral"}
                    className={line.status === "reversed" ? "line-through" : ""}
                  >
                    {line.status_display || WALLET_LINE_STATUS_LABEL[line.status]}
                  </CcPill>
                </CcTd>
                <CcTd className="text-xs">
                  {line.status === "pending" && line.pending_reason ? line.pending_reason : (line.reason || "—")}
                  {isCommissionLine(line) && ` · ${line.company_name} · شهر ${formatNumber(line.commission_month_index)}`}
                </CcTd>
                <CcTd className="tabular-nums text-xs">{formatNumber(line.sequence)}</CcTd>
                <CcTd className="text-xs text-cc-text-muted">{formatDateTimeValue(line.updated_at)}</CcTd>
                <CcTd>
                  <input
                    className="ktra-input h-7 w-32 text-xs"
                    placeholder="سبب العكس/التسوية"
                    value={reasons[key] ?? ""}
                    onChange={(event) => setReasons((current) => ({ ...current, [key]: event.target.value }))}
                  />
                </CcTd>
                <CcTd>
                  <input
                    className="ktra-input h-7 w-24 text-xs"
                    placeholder="مبلغ"
                    inputMode="decimal"
                    value={adjustAmounts[key] ?? ""}
                    onChange={(event) => setAdjustAmounts((current) => ({ ...current, [key]: event.target.value }))}
                  />
                </CcTd>
                <CcTd className="whitespace-nowrap">
                  <div className="flex items-center gap-1.5">
                    {WALLET_LINE_NEXT_STATUS[line.status] && (
                      <button
                        type="button"
                        disabled={busyLine === `transition:${key}`}
                        onClick={() => onTransition(line)}
                        className="ktra-btn h-7 px-2 text-[11px]"
                      >
                        → {WALLET_LINE_STATUS_LABEL[WALLET_LINE_NEXT_STATUS[line.status]!]}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busyLine === `adjust:${key}`}
                      onClick={() => onAdjust(line)}
                      className="ktra-btn h-7 px-2 text-[11px]"
                    >
                      + تسوية
                    </button>
                    {line.status !== "reversed" && (
                      <button
                        type="button"
                        disabled={busyLine === `reverse:${key}`}
                        onClick={() => onReverse(line)}
                        className="inline-flex items-center gap-1 rounded-md bg-rose-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-rose-700 disabled:opacity-50 transition"
                      >
                        <RotateCcw className="h-3 w-3" /> عكس
                      </button>
                    )}
                  </div>
                </CcTd>
              </CcTr>
            );
          })}
        </tbody>
      </CcTable>
    )}
  </CcCard>
);

export default EmployeeWalletPanel;
