import React, { useCallback, useEffect, useState } from "react";
import { Loader2, RotateCcw, Search, Wallet } from "lucide-react";

import { getPlatformOpsDashboard } from "../../services/platformOpsApi";
import {
  PILOT_AXES,
  PILOT_AXIS_LABELS,
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
} from "../../services/platformPilotApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "ليس لديك تصريح لاستعراض محفظة موظف آخر.", "تعذّر تحميل البيانات.");

const now = new Date();

type WalletLine = EmployeeSalaryLineRow | AcquisitionCommissionLineRow;

const isCommissionLine = (line: WalletLine): line is AcquisitionCommissionLineRow => "acquisition" in line;

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
    <section className="space-y-4">
      <h2 className="text-lg font-bold text-slate-900">محفظة الموظّف</h2>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700" role="alert">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">الموظّف</span>
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
          <span className="text-slate-500">السنة</span>
          <input type="number" className="ktra-input h-9 w-24" value={year} onChange={(event) => setYear(Number(event.target.value))} />
        </label>
        <label className="space-y-1 text-xs">
          <span className="text-slate-500">الشهر</span>
          <input type="number" min={1} max={12} className="ktra-input h-9 w-20" value={month} onChange={(event) => setMonth(Number(event.target.value))} />
        </label>
        <button type="button" onClick={() => void load()} disabled={!employeeId || loading} className="ktra-btn ktra-btn-primary">
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />} عرض
        </button>
      </div>

      {wallet && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2">
            <div className="flex items-center gap-2">
              <Wallet className="h-5 w-5 text-emerald-600" />
              <div>
                <p className="text-xs text-slate-500">مؤكَّد</p>
                <p className="text-lg font-bold text-emerald-700">{formatNumber(wallet.totals.confirmed)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Wallet className="h-5 w-5 text-amber-600" />
              <div>
                <p className="text-xs text-slate-500">معلَّق (بانتظار تسجيل الدفع أو الاعتماد)</p>
                <p className="text-lg font-bold text-amber-700">{formatNumber(wallet.totals.pending)}</p>
              </div>
            </div>
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
        <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-bold text-slate-800">كيف يُحسب تقييمي؟ — المحاور الأربعة وأوزانُها في السياسة السارية</h3>
          <p className="text-xs text-slate-500">{performance.status_message} · حجم العينة: {formatNumber(performance.sample_size)} (الحد الأدنى {formatNumber(performance.min_sample_size)})</p>
          {performance.composite_score !== null && (
            <p className="text-sm font-bold">النتيجة المركّبة: {formatNumber(performance.composite_score)}%</p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-1.5 pr-2 text-right">المحور</th>
                  <th className="py-1.5 px-2 text-right">منطبق</th>
                  <th className="py-1.5 px-2 text-right">البسط</th>
                  <th className="py-1.5 px-2 text-right">المقام</th>
                  <th className="py-1.5 px-2 text-right">النتيجة</th>
                  <th className="py-1.5 px-2 text-right">الوزن</th>
                  <th className="py-1.5 px-2 text-right">المساهمة</th>
                  <th className="py-1.5 px-2 text-right">الاستبعادات</th>
                </tr>
              </thead>
              <tbody>
                {PILOT_AXES.map((axis) => {
                  const detail = performance.axes[axis];
                  if (!detail) return null;
                  return (
                    <tr key={axis} className="border-b border-slate-100">
                      <td className="py-1.5 pr-2 font-medium">{PILOT_AXIS_LABELS[axis]}</td>
                      <td className="py-1.5 px-2">{detail.applicable ? "نعم" : "لا"}</td>
                      <td className="py-1.5 px-2">{formatNumber(detail.numerator)}</td>
                      <td className="py-1.5 px-2">{formatNumber(detail.denominator)}</td>
                      <td className="py-1.5 px-2">{formatNumber(detail.score_pct)}%</td>
                      <td className="py-1.5 px-2">{formatNumber(detail.weight_pct)}%</td>
                      <td className="py-1.5 px-2">{formatNumber(detail.weighted_contribution)}</td>
                      <td className="py-1.5 px-2">{detail.exclusions.length ? detail.exclusions.join("، ") : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
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
  <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <h3 className="text-sm font-bold text-slate-800">{title}</h3>
    {lines.length === 0 ? (
      <p className="text-xs text-slate-500">لا سطور لهذا الشهر.</p>
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500">
              <th className="py-1.5 pr-2 text-right">المبلغ</th>
              <th className="py-1.5 px-2 text-right">الحالة</th>
              <th className="py-1.5 px-2 text-right">السبب/المصدر</th>
              <th className="py-1.5 px-2 text-right">تسلسل</th>
              <th className="py-1.5 px-2 text-right">آخر تحديث</th>
              <th className="py-1.5 px-2 text-right">سبب الإجراء</th>
              <th className="py-1.5 px-2 text-right">مبلغ التسوية</th>
              <th className="py-1.5 px-2 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const key = `${isCommissionLine(line) ? "commission" : "salary"}:${line.id}`;
              return (
                <tr key={key} className="border-b border-slate-100">
                  <td className="py-1.5 pr-2 font-semibold">{formatNumber(line.amount)}</td>
                  <td className="py-1.5 px-2">
                    <span className={`rounded-full px-2 py-0.5 ${line.status === "pending" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                      {line.status_display || WALLET_LINE_STATUS_LABEL[line.status]}
                    </span>
                  </td>
                  <td className="py-1.5 px-2">
                    {line.status === "pending" && line.pending_reason ? line.pending_reason : (line.reason || "—")}
                    {isCommissionLine(line) && ` · ${line.company_name} · شهر ${formatNumber(line.commission_month_index)}`}
                  </td>
                  <td className="py-1.5 px-2">{formatNumber(line.sequence)}</td>
                  <td className="py-1.5 px-2">{formatDateTimeValue(line.updated_at)}</td>
                  <td className="py-1.5 px-2">
                    <input
                      className="ktra-input h-7 w-32"
                      placeholder="سبب العكس/التسوية"
                      value={reasons[key] ?? ""}
                      onChange={(event) => setReasons((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  </td>
                  <td className="py-1.5 px-2">
                    <input
                      className="ktra-input h-7 w-24"
                      placeholder="مبلغ"
                      inputMode="decimal"
                      value={adjustAmounts[key] ?? ""}
                      onChange={(event) => setAdjustAmounts((current) => ({ ...current, [key]: event.target.value }))}
                    />
                  </td>
                  <td className="py-1.5 px-2 whitespace-nowrap">
                    <div className="flex gap-1">
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
                          className="inline-flex items-center gap-1 rounded-md bg-red-600 px-2 py-1 text-[11px] font-bold text-white hover:bg-red-700 disabled:opacity-50"
                        >
                          <RotateCcw className="h-3 w-3" /> عكس
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

export default EmployeeWalletPanel;
