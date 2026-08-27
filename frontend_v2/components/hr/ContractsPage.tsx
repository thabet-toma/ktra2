import React, { useCallback, useEffect, useState } from "react";
import {
  FileSignature, Plus, Loader2, X, Check, AlertTriangle, Trash2, Play, Square,
  PlayCircle, Calculator,
} from "lucide-react";
import {
  activateContract, computePayrollRun, createContract, createPayrollRun,
  deleteContract, deletePayrollRun, fetchContractAlerts, listContracts,
  listPayrollRuns, postPayrollRun, terminateContract, unpostPayrollRun,
  type ContractAlerts, type ContractComponentRow, type ContractRow,
  type PayrollRunRow,
} from "../../services/hrRequestsApi";
import { listEmployees, type Employee } from "../../services/payrollApi";
import { currentMonth } from "../../utils/attendance";
import { formatNumber } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";

/**
 * T-HR M6/M7 — «العقود ومسير الرواتب».
 *
 * **العقد يتحرّك بأفعالٍ مسمّاة** (تفعيل/إنهاء) لا بتحرير حالته: الحارس الذي
 * يمنع عقدين نشطين لموظفٍ واحد يسكن في `activate` الخادمي، وتحريرُ الحالة
 * مباشرةً كان يتخطّاه.
 *
 * **وتنبيه انتهاء العقود محسوبٌ عند الفتح** لا مُرسَلٌ ليلاً: لا مجدول في
 * هذه المنصة، فالتنبيه سؤالٌ يُطرح — ومن لا يفتح الشاشة لا يُنبَّه.
 */

const cardClass =
  "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 md:p-4";
const inputClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]";
const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";
const btnPrimary =
  "inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-3 h-9 text-sm " +
  "font-semibold text-white disabled:opacity-50";
const btnGhost =
  "inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 h-9 " +
  "text-sm text-[var(--color-text)] disabled:opacity-50";

type Tab = "contracts" | "runs";

const statusClass = (status: string) => {
  const base = "inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold";
  if (status === "active" || status === "posted") return `${base} bg-emerald-100 text-emerald-800`;
  if (status === "draft") return `${base} bg-sky-100 text-sky-800`;
  if (status === "computed") return `${base} bg-amber-100 text-amber-900`;
  return `${base} bg-slate-100 text-slate-600`;
};

interface ContractDraft {
  id?: number;
  employee: number | "";
  start_date: string;
  end_date: string;
  pay_type: "monthly" | "hourly";
  monthly_salary: string;
  hourly_rate: string;
  overtime_multiplier: string;
  job_title: string;
  notes: string;
  components: ContractComponentRow[];
}

const EMPTY_CONTRACT: ContractDraft = {
  employee: "", start_date: "", end_date: "", pay_type: "monthly",
  monthly_salary: "", hourly_rate: "", overtime_multiplier: "",
  job_title: "", notes: "", components: [],
};

export const ContractsPage: React.FC = () => {
  const permissions = usePermissions();
  const toast = useToast();
  const confirm = useConfirm();
  const canManage = permissions.can("hr.contracts.manage");
  const canRun = permissions.can("hr.payroll.manage");
  const canPost = permissions.can("hr.payroll.post");

  const [tab, setTab] = useState<Tab>("contracts");
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [alerts, setAlerts] = useState<ContractAlerts | null>(null);
  const [runs, setRuns] = useState<PayrollRunRow[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<ContractDraft | null>(null);
  const [runDraft, setRunDraft] = useState<{ name: string; month: string } | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [contractRows, alertRows, staff] = await Promise.all([
        listContracts(),
        fetchContractAlerts(30),
        listEmployees(),
      ]);
      setContracts(contractRows);
      setAlerts(alertRows);
      setEmployees(staff);
      if (canRun) setRuns(await listPayrollRuns());
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر تحميل العقود."), "error");
    } finally {
      setLoading(false);
    }
  }, [canRun, toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const act = async (fn: () => Promise<unknown>, success: string) => {
    setBusy(true);
    try {
      await fn();
      toast(success, "success");
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر تنفيذ الإجراء."), "error");
    } finally {
      setBusy(false);
    }
  };

  const saveContract = async () => {
    if (!draft || !draft.employee || !draft.start_date) {
      toast("اختر الموظف وتاريخ بداية العقد.", "error");
      return;
    }
    const payload: Record<string, unknown> = {
      employee: Number(draft.employee),
      start_date: draft.start_date,
      end_date: draft.end_date || null,
      pay_type: draft.pay_type,
      monthly_salary: draft.monthly_salary || "0",
      hourly_rate: draft.hourly_rate || "0",
      overtime_multiplier: draft.overtime_multiplier || null,
      job_title: draft.job_title,
      notes: draft.notes,
      components: draft.components.filter((c) => c.name.trim()),
    };
    setBusy(true);
    try {
      await createContract(payload);
      toast("أُنشئ العقد مسودّةً — فعّله ليصير مصدر أرقام الراتب.", "success");
      setDraft(null);
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر حفظ العقد."), "error");
    } finally {
      setBusy(false);
    }
  };

  const activate = async (row: ContractRow) => {
    const ok = await confirm({
      title: "تفعيل العقد",
      message: `سيصير هذا العقد مصدر أرقام راتب «${row.employee_name}». وأي عقدٍ نشطٍ سابق له سيُنهى تلقائياً.`,
      confirmText: "تفعيل",
      danger: false,
    });
    if (!ok) return;
    await act(() => activateContract(row.id), "فُعّل العقد.");
  };

  const terminate = async (row: ContractRow) => {
    const ok = await confirm({
      title: "إنهاء العقد",
      message: `سينتهي عقد «${row.employee_name}» اليوم، ويعود احتساب راتبه إلى بطاقته.`,
      confirmText: "إنهاء",
      danger: true,
    });
    if (!ok) return;
    await act(() => terminateContract(row.id, {}), "أُنهي العقد.");
  };

  const createRun = async () => {
    if (!runDraft?.month) {
      toast("اختر شهر المسير.", "error");
      return;
    }
    const [year, month] = runDraft.month.split("-").map(Number);
    const start = `${runDraft.month}-01`;
    const end = new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
    await act(
      () => createPayrollRun({ name: runDraft.name || `مسير ${runDraft.month}`,
        period_start: start, period_end: end }),
      "أُنشئ المسير — احتسبه ثم رحّله.");
    setRunDraft(null);
  };

  const runCompute = async (row: PayrollRunRow) => {
    setBusy(true);
    try {
      const result = await computePayrollRun(row.id);
      const skipped = result.skipped.length
        ? ` وتُخطّي ${formatNumber(result.skipped.length, { maxDecimals: 0 })}: ${result.skipped.map((s) => `${s.name} (${s.reason})`).join("، ")}`
        : "";
      toast(
        `احتُسب ${formatNumber(result.created + result.updated, { maxDecimals: 0 })} كشفاً.${skipped}`,
        result.skipped.length ? "info" : "success");
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر احتساب المسير."), "error");
    } finally {
      setBusy(false);
    }
  };

  const runPost = async (row: PayrollRunRow, posting: boolean) => {
    const ok = await confirm({
      title: posting ? "ترحيل المسير" : "إلغاء ترحيل المسير",
      message: posting
        ? "ستدخل كشوف هذا المسير الدفاتر — مدين «الرواتب والأجور» ودائن حساب كل موظف."
        : "سيُلغى ترحيل كشوف هذا المسير، ويعود ما خُصم من السلف إلى أرصدتها.",
      confirmText: posting ? "ترحيل" : "إلغاء الترحيل",
      danger: !posting,
    });
    if (!ok) return;
    setBusy(true);
    try {
      const result = posting ? await postPayrollRun(row.id) : await unpostPayrollRun(row.id);
      const done = posting ? result.posted : result.reverted;
      const failed = result.failed.length
        ? ` وتعذّر ${formatNumber(result.failed.length, { maxDecimals: 0 })}: ${result.failed.map((f) => `${f.employee_name} (${f.reason})`).join("، ")}`
        : "";
      toast(
        `${posting ? "رُحّل" : "أُلغي ترحيل"} ${formatNumber(done || 0, { maxDecimals: 0 })} كشفاً.${failed}`,
        result.failed.length ? "info" : "success");
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر تنفيذ الإجراء."), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        <FileSignature size={20} className="text-[var(--color-primary)]" />
        <h1 className="text-lg font-bold">العقود ومسير الرواتب</h1>
        <div className="ms-auto flex gap-2">
          {tab === "contracts" && canManage && (
            <button type="button" className={btnPrimary} onClick={() => setDraft({ ...EMPTY_CONTRACT })}>
              <Plus size={14} /> عقد جديد
            </button>
          )}
          {tab === "runs" && canRun && (
            <button
              type="button"
              className={btnPrimary}
              onClick={() => setRunDraft({ name: "", month: currentMonth() })}
            >
              <Plus size={14} /> مسير جديد
            </button>
          )}
        </div>
      </header>

      {alerts && alerts.count > 0 && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 rounded-2xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
        >
          <AlertTriangle size={16} />
          <span className="font-semibold">
            {formatNumber(alerts.count, { maxDecimals: 0 })} عقداً ينتهي خلال {alerts.within_days} يوماً:
          </span>
          <span>
            {alerts.contracts.map((c) =>
              `${c.employee_name} (${formatDateLocalized(c.end_date)})`).join("، ")}
          </span>
        </div>
      )}

      <nav className="flex gap-1 border-b border-[var(--color-border)]">
        {([["contracts", "العقود"], ...(canRun ? [["runs", "مسير الرواتب"]] : [])] as [Tab, string][])
          .map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`px-3 py-2 text-sm ${
                tab === key
                  ? "border-b-2 border-[var(--color-primary)] font-semibold text-[var(--color-primary)]"
                  : "text-[var(--color-text-muted)]"
              }`}
            >
              {label}
            </button>
          ))}
      </nav>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin" /></div>
      ) : tab === "contracts" ? (
        <div className={`${cardClass} overflow-x-auto`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-muted)]">
                <th className="p-2 text-start">الموظف</th>
                <th className="p-2 text-start">المدة</th>
                <th className="p-2 text-start">الأجر</th>
                <th className="p-2 text-start">البنود</th>
                <th className="p-2 text-start">الحالة</th>
                {canManage && <th className="p-2" />}
              </tr>
            </thead>
            <tbody>
              {contracts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-[var(--color-text-muted)]">
                    لا عقود — الرواتب تُحسب من بطاقة كل موظف حتى يُفعَّل له عقد.
                  </td>
                </tr>
              ) : (
                contracts.map((row) => (
                  <tr key={row.id} className="border-t border-[var(--color-border)]">
                    <td className="p-2">
                      <div className="font-semibold">{row.employee_name}</div>
                      {row.job_title && (
                        <div className="text-[11px] text-[var(--color-text-muted)]">{row.job_title}</div>
                      )}
                    </td>
                    <td className="p-2">
                      {formatDateLocalized(row.start_date)}
                      {row.end_date ? ` — ${formatDateLocalized(row.end_date)}` : " — غير محدّدة"}
                      {row.days_to_expiry != null && row.days_to_expiry <= 30 && (
                        <span className="ms-1 text-[11px] text-amber-800">
                          ({formatNumber(row.days_to_expiry, { maxDecimals: 0 })} يوماً)
                        </span>
                      )}
                    </td>
                    <td className="p-2">
                      {row.pay_type === "monthly"
                        ? `${formatNumber(row.monthly_salary)} شهرياً`
                        : `${formatNumber(row.hourly_rate)} للساعة`}
                      {row.overtime_multiplier && (
                        <span className="text-[11px] text-[var(--color-text-muted)]">
                          {" "}· إضافي ×{formatNumber(row.overtime_multiplier)}
                        </span>
                      )}
                    </td>
                    <td className="p-2 text-xs">
                      {row.components.length === 0 ? "—" : row.components.map((c) =>
                        `${c.name}: ${c.kind === "earning" ? "+" : "−"}${formatNumber(c.amount)}`).join("، ")}
                    </td>
                    <td className="p-2">
                      <span className={statusClass(row.status)}>{row.status_label}</span>
                    </td>
                    {canManage && (
                      <td className="p-2">
                        <div className="flex justify-end gap-1">
                          {row.status === "draft" && (
                            <button type="button" className={btnGhost} disabled={busy}
                              onClick={() => void activate(row)}>
                              <Play size={14} /> تفعيل
                            </button>
                          )}
                          {row.status === "active" && (
                            <button type="button" className={btnGhost} disabled={busy}
                              onClick={() => void terminate(row)}>
                              <Square size={14} /> إنهاء
                            </button>
                          )}
                          {row.status !== "active" && (
                            <button type="button" className={btnGhost} disabled={busy}
                              onClick={() => void act(() => deleteContract(row.id), "حُذف العقد.")}>
                              <Trash2 size={14} /> حذف
                            </button>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={`${cardClass} overflow-x-auto`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[var(--color-text-muted)]">
                <th className="p-2 text-start">المسير</th>
                <th className="p-2 text-start">الفترة</th>
                <th className="p-2 text-start">الكشوف</th>
                <th className="p-2 text-start">إجمالي الصافي</th>
                <th className="p-2 text-start">الحالة</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-[var(--color-text-muted)]">
                    لا مسيرات بعد.
                  </td>
                </tr>
              ) : (
                runs.map((row) => (
                  <tr key={row.id} className="border-t border-[var(--color-border)]">
                    <td className="p-2 font-semibold">{row.name || `مسير #${row.id}`}</td>
                    <td className="p-2">
                      {formatDateLocalized(row.period_start)} — {formatDateLocalized(row.period_end)}
                      {row.department_name && ` · ${row.department_name}`}
                      {row.branch_name && ` · ${row.branch_name}`}
                    </td>
                    <td className="p-2">{formatNumber(row.payslip_count, { maxDecimals: 0 })}</td>
                    <td className="p-2">{row.total_net ? formatNumber(row.total_net) : "—"}</td>
                    <td className="p-2">
                      <span className={statusClass(row.status)}>{row.status_label}</span>
                    </td>
                    <td className="p-2">
                      <div className="flex flex-wrap justify-end gap-1">
                        {row.status !== "posted" && (
                          <button type="button" className={btnGhost} disabled={busy}
                            onClick={() => void runCompute(row)}>
                            <Calculator size={14} /> احتساب
                          </button>
                        )}
                        {canPost && row.status === "computed" && (
                          <button type="button" className={btnPrimary} disabled={busy}
                            onClick={() => void runPost(row, true)}>
                            <PlayCircle size={14} /> ترحيل
                          </button>
                        )}
                        {canPost && row.status === "posted" && (
                          <button type="button" className={btnGhost} disabled={busy}
                            onClick={() => void runPost(row, false)}>
                            <Square size={14} /> إلغاء الترحيل
                          </button>
                        )}
                        {row.status !== "posted" && (
                          <button type="button" className={btnGhost} disabled={busy}
                            onClick={() => void act(() => deletePayrollRun(row.id), "حُذف المسير.")}>
                            <Trash2 size={14} /> حذف
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {runDraft && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-3">
          <div className={`${cardClass} w-full max-w-sm`}>
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-bold">مسير رواتب جديد</h2>
              <button type="button" className="ms-auto" onClick={() => setRunDraft(null)} aria-label="إغلاق">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className={labelClass} htmlFor="run-month">الشهر</label>
                <input
                  id="run-month"
                  type="month"
                  className={inputClass}
                  value={runDraft.month}
                  onChange={(event) => setRunDraft({ ...runDraft, month: event.target.value })}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="run-name">اسم المسير</label>
                <input
                  id="run-name"
                  className={inputClass}
                  value={runDraft.name}
                  placeholder={`مسير ${runDraft.month}`}
                  onChange={(event) => setRunDraft({ ...runDraft, name: event.target.value })}
                />
              </div>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={() => setRunDraft(null)}>إلغاء</button>
              <button type="button" className={btnPrimary} disabled={busy} onClick={() => void createRun()}>
                <Check size={14} /> إنشاء
              </button>
            </div>
          </div>
        </div>
      )}

      {draft && (
        <div className="fixed inset-0 z-40 grid place-items-center overflow-y-auto bg-black/40 p-3">
          <div className={`${cardClass} w-full max-w-lg`}>
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-bold">عقد جديد</h2>
              <button type="button" className="ms-auto" onClick={() => setDraft(null)} aria-label="إغلاق">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className={labelClass} htmlFor="ct-employee">الموظف</label>
                <select
                  id="ct-employee"
                  className={inputClass}
                  value={draft.employee}
                  onChange={(event) => setDraft({
                    ...draft, employee: event.target.value ? Number(event.target.value) : "",
                  })}
                >
                  <option value="">— اختر —</option>
                  {employees.map((employee) => (
                    <option key={employee.id} value={employee.id}>{employee.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={labelClass} htmlFor="ct-start">بداية العقد</label>
                  <input id="ct-start" type="date" className={inputClass} value={draft.start_date}
                    onChange={(event) => setDraft({ ...draft, start_date: event.target.value })} />
                </div>
                <div>
                  <label className={labelClass} htmlFor="ct-end">نهايته (اختياري)</label>
                  <input id="ct-end" type="date" className={inputClass} value={draft.end_date}
                    onChange={(event) => setDraft({ ...draft, end_date: event.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={labelClass} htmlFor="ct-paytype">دورة الأجر</label>
                  <select id="ct-paytype" className={inputClass} value={draft.pay_type}
                    onChange={(event) => setDraft({
                      ...draft, pay_type: event.target.value as "monthly" | "hourly",
                    })}>
                    <option value="monthly">شهري</option>
                    <option value="hourly">بالساعة</option>
                  </select>
                </div>
                <div>
                  <label className={labelClass} htmlFor="ct-amount">
                    {draft.pay_type === "monthly" ? "الراتب الشهري" : "أجر الساعة"}
                  </label>
                  <input
                    id="ct-amount"
                    type="number"
                    min={0}
                    step="0.01"
                    className={inputClass}
                    value={draft.pay_type === "monthly" ? draft.monthly_salary : draft.hourly_rate}
                    onChange={(event) => setDraft(
                      draft.pay_type === "monthly"
                        ? { ...draft, monthly_salary: event.target.value }
                        : { ...draft, hourly_rate: event.target.value })}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={labelClass} htmlFor="ct-ot">مضاعف الساعة الإضافية</label>
                  <input id="ct-ot" type="number" min={1} max={5} step="0.25" className={inputClass}
                    placeholder="يتبع الوردية"
                    value={draft.overtime_multiplier}
                    onChange={(event) => setDraft({ ...draft, overtime_multiplier: event.target.value })} />
                </div>
                <div>
                  <label className={labelClass} htmlFor="ct-title">المسمّى في العقد</label>
                  <input id="ct-title" className={inputClass} value={draft.job_title}
                    onChange={(event) => setDraft({ ...draft, job_title: event.target.value })} />
                </div>
              </div>

              <div>
                <div className="mb-1 flex items-center gap-2">
                  <span className={labelClass}>بنود التعويض</span>
                  <button
                    type="button"
                    className="text-xs underline"
                    onClick={() => setDraft({
                      ...draft,
                      components: [...draft.components,
                        { kind: "earning", name: "", amount: "0" }],
                    })}
                  >
                    + إضافة بند
                  </button>
                </div>
                {draft.components.map((component, index) => (
                  <div key={index} className="mb-1 flex gap-1">
                    <select
                      className={`${inputClass} w-28`}
                      value={component.kind}
                      onChange={(event) => {
                        const next = [...draft.components];
                        next[index] = { ...component, kind: event.target.value as "earning" | "deduction" };
                        setDraft({ ...draft, components: next });
                      }}
                    >
                      <option value="earning">استحقاق</option>
                      <option value="deduction">خصم</option>
                    </select>
                    <input
                      className={inputClass}
                      placeholder="اسم البند"
                      value={component.name}
                      onChange={(event) => {
                        const next = [...draft.components];
                        next[index] = { ...component, name: event.target.value };
                        setDraft({ ...draft, components: next });
                      }}
                    />
                    <input
                      className={`${inputClass} w-32`}
                      type="number"
                      step="0.01"
                      value={component.amount}
                      onChange={(event) => {
                        const next = [...draft.components];
                        next[index] = { ...component, amount: event.target.value };
                        setDraft({ ...draft, components: next });
                      }}
                    />
                    <button
                      type="button"
                      className={btnGhost}
                      onClick={() => setDraft({
                        ...draft,
                        components: draft.components.filter((_, i) => i !== index),
                      })}
                      aria-label="حذف البند"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
                <p className="text-[11px] text-[var(--color-text-muted)]">
                  البنود مبالغُ ثابتة تُضاف إلى بدلات القسيمة أو خصوماتها. العمولة تُدخَل
                  بندَ استحقاقٍ بمبلغها المحسوب.
                </p>
              </div>

              <div>
                <label className={labelClass} htmlFor="ct-notes">ملاحظات</label>
                <textarea id="ct-notes" className={`${inputClass} h-16 py-2`} value={draft.notes}
                  onChange={(event) => setDraft({ ...draft, notes: event.target.value })} />
              </div>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={() => setDraft(null)}>إلغاء</button>
              <button type="button" className={btnPrimary} disabled={busy} onClick={() => void saveContract()}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} حفظ مسودّة
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ContractsPage;
