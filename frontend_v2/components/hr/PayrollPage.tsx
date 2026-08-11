/**
 * PayrollPage — «الرواتب».
 *
 * ثلاثة تبويبات تعكس دورة الراتب كما هي، لا كما تُخزَّن:
 *   الموظفون  →  السجل اليومي (ساعات للجزئي، غيابات/تأخيرات للدائم)  →  الكشوف والصرف
 *
 * الموظف المختار يقود الشاشة كلها: التبويب الأوسط يبدّل شكله بنوعه — سجلُّ
 * ساعاتٍ لمن يُدفع له بالساعة، وسجلُّ غياباتٍ لمن يُخصم من راتبه الثابت. عرض
 * الحقلين معاً يدعو لإدخال لا معنى له.
 *
 * كل رقم مالي من الخادم: المعاينة (`preview`) والكشف المحفوظ يمرّان بدالة
 * الاحتساب نفسها، فما يراه المستخدم قبل الحفظ هو ما يُرحَّل بعده.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Banknote, Plus, Trash2, RefreshCw, ChevronRight, ChevronLeft, Loader2,
  Users, Clock, CalendarX, FileText, CheckCircle2, RotateCcw, Wallet, X,
} from "lucide-react";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized, todayIso } from "../../utils/formatDate";
import { monthKeyLabel, monthKeyOf, monthKeyRange, shiftMonthKey } from "../../utils/monthKey";
import {
  formatHours, formatLateMinutes, validateAdjustmentDraft, validateEmployeeDraft,
  validateWorkLogDraft,
} from "../../utils/payroll";
import {
  listEmployees, createEmployee, updateEmployee, deleteEmployee,
  listWorkLogs, createWorkLog, deleteWorkLog,
  listAdjustments, createAdjustment, deleteAdjustment,
  listPayslips, createPayslip, deletePayslip, postPayslip, unpostPayslip, previewPayslip,
  listPayrollPayments, createPayrollPayment, deletePayrollPayment,
  type AttendanceAdjustment, type Employee, type EmployeeDraft, type PayslipPreview,
  type Payslip, type PayrollPayment, type PayType, type WorkLog,
} from "../../services/payrollApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { usePermissions } from "../../contexts/PermissionsContext";

type Tab = "employees" | "daily" | "payslips";

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

const EMPTY_EMPLOYEE = {
  name: "",
  pay_type: "monthly" as PayType,
  monthly_salary: "",
  hourly_rate: "",
  standard_hours_per_day: "8",
  working_days_per_month: "26",
  job_title: "",
  phone: "",
  hire_date: "",
  notes: "",
};

const inputClass =
  "h-10 px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:ring-1 focus:ring-emerald-500 outline-none";
const cellClass = "px-3 py-2 text-sm text-[var(--color-text)]";
const headClass =
  "px-3 py-2 text-xs font-bold text-[var(--color-text-muted)] whitespace-nowrap";

export const PayrollPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const canManage = can("hr.payroll.manage");
  const canPost = can("hr.payroll.post");

  const [tab, setTab] = useState<Tab>("employees");
  const [month, setMonth] = useState(() => monthKeyOf(todayIso()));
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [workLogs, setWorkLogs] = useState<WorkLog[]>([]);
  const [adjustments, setAdjustments] = useState<AttendanceAdjustment[]>([]);
  const [payslips, setPayslips] = useState<Payslip[]>([]);
  const [payments, setPayments] = useState<PayrollPayment[]>([]);
  const [preview, setPreview] = useState<PayslipPreview | null>(null);

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [employeeDraft, setEmployeeDraft] = useState({ ...EMPTY_EMPLOYEE });
  const [editingEmployeeId, setEditingEmployeeId] = useState<number | null>(null);
  const [showEmployeeForm, setShowEmployeeForm] = useState(false);

  const [hoursDraft, setHoursDraft] = useState({ date: todayIso(), hours: "", notes: "" });
  const [adjustmentDraft, setAdjustmentDraft] = useState({
    date: todayIso(), kind: "absence" as "absence" | "late",
    days: "1", minutes: "30", is_deductible: true, notes: "",
  });
  const [slipDraft, setSlipDraft] = useState({ allowances: "", other_deductions: "", notes: "" });
  const [paymentDraft, setPaymentDraft] = useState({ date: todayIso(), amount: "", notes: "" });

  const selected = useMemo(
    () => employees.find((e) => e.id === selectedId) || null,
    [employees, selectedId],
  );
  const period = useMemo(() => monthKeyRange(month), [month]);

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const rows = await listEmployees();
      setEmployees(rows);
      setSelectedId((current) =>
        current && rows.some((r) => r.id === current) ? current : rows[0]?.id ?? null);
    } catch (e) {
      setErr(messageOf(e, "تعذر تحميل الموظفين"));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDaily = useCallback(async () => {
    if (!selected) {
      setWorkLogs([]);
      setAdjustments([]);
      return;
    }
    setLoading(true);
    try {
      if (selected.pay_type === "hourly") {
        setWorkLogs(await listWorkLogs({ employee: selected.id, month }));
        setAdjustments([]);
      } else {
        setAdjustments(await listAdjustments({ employee: selected.id, month }));
        setWorkLogs([]);
      }
    } catch (e) {
      setErr(messageOf(e, "تعذر تحميل السجل اليومي"));
    } finally {
      setLoading(false);
    }
  }, [selected, month]);

  const loadPayslips = useCallback(async () => {
    if (!selected) {
      setPayslips([]);
      setPayments([]);
      return;
    }
    setLoading(true);
    try {
      const [slips, paid] = await Promise.all([
        listPayslips({ employee: selected.id }),
        listPayrollPayments({ employee: selected.id }),
      ]);
      setPayslips(slips);
      setPayments(paid);
    } catch (e) {
      setErr(messageOf(e, "تعذر تحميل كشوف الرواتب"));
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => { void loadEmployees(); }, [loadEmployees]);
  useEffect(() => { if (tab === "daily") void loadDaily(); }, [tab, loadDaily]);
  useEffect(() => { if (tab === "payslips") void loadPayslips(); }, [tab, loadPayslips]);

  // معاينة الفترة — الأرقام من الخادم دائماً، فلا تختلف عمّا يُحفظ.
  useEffect(() => {
    if (tab !== "payslips" || !selected) {
      setPreview(null);
      return;
    }
    let alive = true;
    void (async () => {
      try {
        const numbers = await previewPayslip({
          employee: selected.id,
          period_start: period.start,
          period_end: period.end,
          allowances: slipDraft.allowances || "0",
          other_deductions: slipDraft.other_deductions || "0",
        });
        if (alive) setPreview(numbers);
      } catch {
        if (alive) setPreview(null);
      }
    })();
    return () => { alive = false; };
  }, [tab, selected, period.start, period.end, slipDraft.allowances, slipDraft.other_deductions]);

  /* — الموظفون — */

  const openNewEmployee = () => {
    setEditingEmployeeId(null);
    setEmployeeDraft({ ...EMPTY_EMPLOYEE });
    setShowEmployeeForm(true);
  };

  const openEditEmployee = (row: Employee) => {
    setEditingEmployeeId(row.id);
    setEmployeeDraft({
      name: row.name,
      pay_type: row.pay_type,
      monthly_salary: row.monthly_salary,
      hourly_rate: row.hourly_rate,
      standard_hours_per_day: row.standard_hours_per_day,
      working_days_per_month: row.working_days_per_month,
      job_title: row.job_title,
      phone: row.phone,
      hire_date: row.hire_date || "",
      notes: row.notes,
    });
    setShowEmployeeForm(true);
  };

  const saveEmployee = async () => {
    const problem = validateEmployeeDraft(employeeDraft);
    if (problem) {
      setErr(problem);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      // حقول النوع وحده تُرسَل: النموذج لا يعرض الأجر الآخر أصلاً، وإرساله
      // فارغاً يُقرأ في الخادم «رقم غير صالح» على حقلٍ لم يلمسه المستخدم.
      // وميزة ثانية: تبديل النوع لا يدهس أجر النوع السابق المحفوظ.
      const payload: EmployeeDraft = {
        name: employeeDraft.name.trim(),
        pay_type: employeeDraft.pay_type,
        job_title: employeeDraft.job_title,
        phone: employeeDraft.phone,
        notes: employeeDraft.notes,
        hire_date: employeeDraft.hire_date || null,
        ...(employeeDraft.pay_type === "hourly"
          ? { hourly_rate: employeeDraft.hourly_rate }
          : {
              monthly_salary: employeeDraft.monthly_salary,
              working_days_per_month: employeeDraft.working_days_per_month,
              standard_hours_per_day: employeeDraft.standard_hours_per_day,
            }),
      };
      if (editingEmployeeId) await updateEmployee(editingEmployeeId, payload);
      else await createEmployee(payload);
      setShowEmployeeForm(false);
      toast(editingEmployeeId ? "تم حفظ بيانات الموظف" : "تمت إضافة الموظف وفُتح حسابه في الشجرة", "success");
      await loadEmployees();
    } catch (e) {
      setErr(messageOf(e, "تعذر حفظ بيانات الموظف"));
    } finally {
      setBusy(false);
    }
  };

  const removeEmployee = async (row: Employee) => {
    const ok = await confirm({
      title: "حذف موظف",
      message: `سيُحذف «${row.name}». الموظف الذي دخل الدفاتر يُعطَّل ولا يُحذف.`,
      confirmText: "حذف",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteEmployee(row.id);
      toast("تم حذف الموظف", "success");
      await loadEmployees();
    } catch (e) {
      setErr(messageOf(e, "تعذر حذف الموظف"));
    }
  };

  /* — السجل اليومي — */

  const addHours = async () => {
    if (!selected) return;
    const problem = validateWorkLogDraft(hoursDraft);
    if (problem) {
      setErr(problem);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await createWorkLog({
        employee: selected.id, date: hoursDraft.date,
        hours: hoursDraft.hours, notes: hoursDraft.notes,
      });
      setHoursDraft({ date: hoursDraft.date, hours: "", notes: "" });
      await loadDaily();
    } catch (e) {
      setErr(messageOf(e, "تعذر تسجيل الساعات"));
    } finally {
      setBusy(false);
    }
  };

  const addAdjustment = async () => {
    if (!selected) return;
    const problem = validateAdjustmentDraft(adjustmentDraft);
    if (problem) {
      setErr(problem);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await createAdjustment({
        employee: selected.id,
        date: adjustmentDraft.date,
        kind: adjustmentDraft.kind,
        days: adjustmentDraft.days,
        minutes: Number(adjustmentDraft.minutes) || 0,
        is_deductible: adjustmentDraft.is_deductible,
        notes: adjustmentDraft.notes,
      });
      setAdjustmentDraft({ ...adjustmentDraft, notes: "" });
      await loadDaily();
    } catch (e) {
      setErr(messageOf(e, "تعذر تسجيل الغياب/التأخير"));
    } finally {
      setBusy(false);
    }
  };

  /* — الكشوف والصرف — */

  const generateSlip = async () => {
    if (!selected) return;
    setBusy(true);
    setErr(null);
    try {
      await createPayslip({
        employee: selected.id,
        period_start: period.start,
        period_end: period.end,
        allowances: slipDraft.allowances || "0",
        other_deductions: slipDraft.other_deductions || "0",
        notes: slipDraft.notes,
      });
      setSlipDraft({ allowances: "", other_deductions: "", notes: "" });
      toast("تم إنشاء كشف الراتب كمسودّة", "success");
      await loadPayslips();
    } catch (e) {
      setErr(messageOf(e, "تعذر إنشاء الكشف"));
    } finally {
      setBusy(false);
    }
  };

  const runOnSlip = async (
    action: () => Promise<unknown>, done: string, fallback: string,
  ) => {
    setBusy(true);
    setErr(null);
    try {
      await action();
      toast(done, "success");
      await Promise.all([loadPayslips(), loadEmployees()]);
    } catch (e) {
      setErr(messageOf(e, fallback));
    } finally {
      setBusy(false);
    }
  };

  const payEmployee = async () => {
    if (!selected) return;
    const amount = Number(paymentDraft.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setErr("مبلغ الصرف يجب أن يكون أكبر من صفر.");
      return;
    }
    const latestPosted = payslips.find((s) => s.status === "posted");
    await runOnSlip(
      () => createPayrollPayment({
        employee: selected.id,
        payslip: latestPosted?.id ?? null,
        date: paymentDraft.date,
        amount: paymentDraft.amount,
        notes: paymentDraft.notes,
      }),
      "تم صرف الراتب وترحيل قيده",
      "تعذر صرف الراتب",
    );
    setPaymentDraft({ date: paymentDraft.date, amount: "", notes: "" });
  };

  /* — العرض — */

  const totalOwed = employees.reduce((sum, e) => sum + (Number(e.balance) || 0), 0);

  const tabButton = (key: Tab, label: string, icon: React.ReactNode) => (
    <button
      key={key}
      onClick={() => setTab(key)}
      className={`flex items-center gap-2 px-4 py-2 text-sm rounded-t-lg border border-b-0 ${
        tab === key
          ? "border-[var(--color-border)] bg-[var(--color-surface)] font-bold text-[var(--color-primary-emphasis)]"
          : "border-transparent bg-[var(--color-surface-2)] text-[var(--color-text-muted)]"
      }`}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <div dir="rtl" className="space-y-4 p-3 md:p-4">
      {/* الترويسة */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-lg font-bold text-[var(--color-text)]">
          <Banknote className="w-5 h-5 text-[var(--color-primary)]" />
          الرواتب
          <span className="text-[11px] font-normal text-[var(--color-text-muted)]">
            كل موظف له حسابه تحت بند «رواتب مستحقة للموظفين» في شجرة الحسابات
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-lg bg-[var(--color-surface-2)] px-3 py-1.5 text-sm text-[var(--color-text)]">
            مستحق للموظفين: <b>{formatMoney(totalOwed)}</b>
          </span>
          <button
            onClick={() => void loadEmployees()}
            className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="تحديث"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {err && (
        <div role="alert" className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm font-bold text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">
          <button onClick={() => setErr(null)} className="float-left p-0.5" title="إغلاق">
            <X className="w-4 h-4" />
          </button>
          {err}
        </div>
      )}

      {/* الموظف المختار — يقود التبويبين التاليين */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-[var(--color-text-muted)]">الموظف:</span>
        <select
          value={selectedId ?? ""}
          onChange={(e) => setSelectedId(Number(e.target.value) || null)}
          className={inputClass}
        >
          {employees.length === 0 && <option value="">لا يوجد موظفون بعد</option>}
          {employees.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name} — {row.pay_type_label}
            </option>
          ))}
        </select>
        {selected && (
          <span className="rounded-lg bg-[var(--color-surface-2)] px-3 py-1.5 text-sm">
            رصيده: <b>{formatMoney(selected.balance)}</b>
            {selected.account_code && (
              <span className="mr-2 text-[11px] text-[var(--color-text-muted)]">
                ({selected.account_code})
              </span>
            )}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1 overflow-x-auto border-b border-[var(--color-border)]">
        {tabButton("employees", "الموظفون", <Users className="w-4 h-4" />)}
        {tabButton("daily", "السجل اليومي", <Clock className="w-4 h-4" />)}
        {tabButton("payslips", "كشوف الرواتب", <FileText className="w-4 h-4" />)}
      </div>

      {/* ═══ الموظفون ═══ */}
      {tab === "employees" && (
        <div className="space-y-3">
          {canManage && (
            <button
              onClick={openNewEmployee}
              className="flex items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white"
            >
              <Plus className="w-4 h-4" /> موظف جديد
            </button>
          )}

          {showEmployeeForm && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 space-y-3">
              <div className="grid gap-2 md:grid-cols-3">
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  اسم الموظف
                  <input
                    value={employeeDraft.name}
                    onChange={(e) => setEmployeeDraft({ ...employeeDraft, name: e.target.value })}
                    className={inputClass}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  نوع التعاقد
                  <select
                    value={employeeDraft.pay_type}
                    onChange={(e) =>
                      setEmployeeDraft({ ...employeeDraft, pay_type: e.target.value as PayType })}
                    className={inputClass}
                  >
                    <option value="monthly">دائم — راتب شهري</option>
                    <option value="hourly">جزئي — أجر بالساعة</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  المسمّى الوظيفي
                  <input
                    value={employeeDraft.job_title}
                    onChange={(e) => setEmployeeDraft({ ...employeeDraft, job_title: e.target.value })}
                    className={inputClass}
                  />
                </label>
              </div>

              {/* حقول النوع وحده — الحقل الذي لا يخصّ النوع لا يُعرض أصلاً */}
              {employeeDraft.pay_type === "hourly" ? (
                <label className="flex max-w-xs flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  الأجر المتفق عليه للساعة
                  <input
                    type="number" min="0" step="0.01"
                    value={employeeDraft.hourly_rate}
                    onChange={(e) => setEmployeeDraft({ ...employeeDraft, hourly_rate: e.target.value })}
                    className={inputClass}
                  />
                </label>
              ) : (
                <div className="grid gap-2 md:grid-cols-3">
                  <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    الراتب الشهري
                    <input
                      type="number" min="0" step="0.01"
                      value={employeeDraft.monthly_salary}
                      onChange={(e) => setEmployeeDraft({ ...employeeDraft, monthly_salary: e.target.value })}
                      className={inputClass}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    أيام الدوام في الشهر <span className="opacity-70">(أساس خصم الغياب)</span>
                    <input
                      type="number" min="1" step="0.5"
                      value={employeeDraft.working_days_per_month}
                      onChange={(e) => setEmployeeDraft({ ...employeeDraft, working_days_per_month: e.target.value })}
                      className={inputClass}
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    ساعات الدوام اليومية <span className="opacity-70">(أساس خصم التأخير)</span>
                    <input
                      type="number" min="1" step="0.5"
                      value={employeeDraft.standard_hours_per_day}
                      onChange={(e) => setEmployeeDraft({ ...employeeDraft, standard_hours_per_day: e.target.value })}
                      className={inputClass}
                    />
                  </label>
                </div>
              )}

              <div className="grid gap-2 md:grid-cols-3">
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  الهاتف
                  <input
                    value={employeeDraft.phone}
                    onChange={(e) => setEmployeeDraft({ ...employeeDraft, phone: e.target.value })}
                    className={inputClass}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  تاريخ المباشرة
                  <input
                    type="date"
                    value={employeeDraft.hire_date}
                    onChange={(e) => setEmployeeDraft({ ...employeeDraft, hire_date: e.target.value })}
                    className={inputClass}
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  ملاحظات
                  <input
                    value={employeeDraft.notes}
                    onChange={(e) => setEmployeeDraft({ ...employeeDraft, notes: e.target.value })}
                    className={inputClass}
                  />
                </label>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => void saveEmployee()}
                  disabled={busy}
                  className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
                >
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  حفظ
                </button>
                <button
                  onClick={() => setShowEmployeeForm(false)}
                  className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm"
                >
                  إلغاء
                </button>
              </div>
            </div>
          )}

          <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
            <table className="w-full min-w-[46rem]">
              <thead className="bg-[var(--color-surface-2)]">
                <tr>
                  <th className={headClass}>الرقم</th>
                  <th className={headClass}>الاسم</th>
                  <th className={headClass}>النوع</th>
                  <th className={headClass}>الأجر</th>
                  <th className={headClass}>حسابه في الشجرة</th>
                  <th className={headClass}>رصيده</th>
                  <th className={headClass}>الحالة</th>
                  <th className={headClass}></th>
                </tr>
              </thead>
              <tbody>
                {employees.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => setSelectedId(row.id)}
                    className={`cursor-pointer border-t border-[var(--color-border)] ${
                      row.id === selectedId ? "bg-[var(--color-surface-3)]" : ""}`}
                  >
                    <td className={cellClass}>{row.code}</td>
                    <td className={`${cellClass} font-bold`}>{row.name}</td>
                    <td className={cellClass}>{row.pay_type_label}</td>
                    <td className={cellClass}>
                      {row.pay_type === "hourly"
                        ? `${formatMoney(row.hourly_rate)} / ساعة`
                        : `${formatMoney(row.monthly_salary)} / شهر`}
                    </td>
                    <td className={`${cellClass} text-[var(--color-text-muted)]`}>
                      {row.account_code || "—"}
                    </td>
                    <td className={`${cellClass} font-bold`}>{formatMoney(row.balance)}</td>
                    <td className={cellClass}>{row.is_active ? "على رأس العمل" : "موقوف"}</td>
                    <td className={cellClass}>
                      {canManage && (
                        <div className="flex gap-1">
                          <button
                            onClick={(e) => { e.stopPropagation(); openEditEmployee(row); }}
                            className="rounded-md px-2 py-1 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
                          >
                            تعديل
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); void removeEmployee(row); }}
                            className="rounded-md p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                            title="حذف"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {employees.length === 0 && !loading && (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-sm text-[var(--color-text-muted)]">
                      لا يوجد موظفون بعد — ابدأ بـ«موظف جديد».
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ═══ السجل اليومي ═══ */}
      {tab === "daily" && (
        <div className="space-y-3">
          <div className="flex items-center gap-1">
            <button onClick={() => setMonth(shiftMonthKey(month, -1))}
              className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]" title="الشهر السابق">
              <ChevronRight className="w-4 h-4" />
            </button>
            <span className="min-w-[9rem] text-center font-semibold">{monthKeyLabel(month)}</span>
            <button onClick={() => setMonth(shiftMonthKey(month, 1))}
              className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]" title="الشهر التالي">
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>

          {!selected && (
            <p className="text-sm text-[var(--color-text-muted)]">اختر موظفاً أولاً.</p>
          )}

          {/* الجزئي: ساعات يومية */}
          {selected?.pay_type === "hourly" && (
            <>
              {canManage && (
                <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
                  <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    التاريخ
                    <input type="date" value={hoursDraft.date}
                      onChange={(e) => setHoursDraft({ ...hoursDraft, date: e.target.value })}
                      className={inputClass} />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    الساعات
                    <input type="number" min="0" step="0.25" value={hoursDraft.hours}
                      onChange={(e) => setHoursDraft({ ...hoursDraft, hours: e.target.value })}
                      className={`${inputClass} w-28`} />
                  </label>
                  <label className="flex flex-1 flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    ملاحظة
                    <input value={hoursDraft.notes}
                      onChange={(e) => setHoursDraft({ ...hoursDraft, notes: e.target.value })}
                      className={inputClass} />
                  </label>
                  <button onClick={() => void addHours()} disabled={busy}
                    className="flex h-10 items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 text-sm font-bold text-white disabled:opacity-60">
                    <Plus className="w-4 h-4" /> تسجيل الساعات
                  </button>
                </div>
              )}

              <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
                <table className="w-full min-w-[32rem]">
                  <thead className="bg-[var(--color-surface-2)]">
                    <tr>
                      <th className={headClass}>التاريخ</th>
                      <th className={headClass}>الساعات</th>
                      <th className={headClass}>ملاحظة</th>
                      <th className={headClass}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {workLogs.map((row) => (
                      <tr key={row.id} className="border-t border-[var(--color-border)]">
                        <td className={cellClass}>{formatDateLocalized(row.date)}</td>
                        <td className={`${cellClass} font-bold`}>{formatHours(row.hours)}</td>
                        <td className={cellClass}>{row.notes}</td>
                        <td className={cellClass}>
                          {canManage && (
                            <button
                              onClick={() => void deleteWorkLog(row.id).then(loadDaily)}
                              className="rounded-md p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                              title="حذف"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {workLogs.length === 0 && !loading && (
                      <tr>
                        <td colSpan={4} className="px-3 py-8 text-center text-sm text-[var(--color-text-muted)]">
                          لا ساعات مسجّلة في {monthKeyLabel(month)}.
                        </td>
                      </tr>
                    )}
                  </tbody>
                  {workLogs.length > 0 && (
                    <tfoot className="bg-[var(--color-surface-2)]">
                      <tr>
                        <td className={`${cellClass} font-bold`}>الإجمالي</td>
                        <td className={`${cellClass} font-bold`}>
                          {formatHours(workLogs.reduce((s, r) => s + Number(r.hours), 0))}
                        </td>
                        <td colSpan={2} />
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </>
          )}

          {/* الدائم: غيابات وتأخيرات */}
          {selected?.pay_type === "monthly" && (
            <>
              {canManage && (
                <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
                  <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    التاريخ
                    <input type="date" value={adjustmentDraft.date}
                      onChange={(e) => setAdjustmentDraft({ ...adjustmentDraft, date: e.target.value })}
                      className={inputClass} />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    النوع
                    <select value={adjustmentDraft.kind}
                      onChange={(e) => setAdjustmentDraft({
                        ...adjustmentDraft, kind: e.target.value as "absence" | "late" })}
                      className={inputClass}>
                      <option value="absence">غياب</option>
                      <option value="late">تأخير</option>
                    </select>
                  </label>
                  {adjustmentDraft.kind === "absence" ? (
                    <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                      عدد الأيام
                      <input type="number" min="0" step="0.5" value={adjustmentDraft.days}
                        onChange={(e) => setAdjustmentDraft({ ...adjustmentDraft, days: e.target.value })}
                        className={`${inputClass} w-24`} />
                    </label>
                  ) : (
                    <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                      دقائق التأخير
                      <input type="number" min="0" step="5" value={adjustmentDraft.minutes}
                        onChange={(e) => setAdjustmentDraft({ ...adjustmentDraft, minutes: e.target.value })}
                        className={`${inputClass} w-28`} />
                    </label>
                  )}
                  <label className="flex items-center gap-2 pb-2 text-xs text-[var(--color-text)]">
                    <input type="checkbox" checked={adjustmentDraft.is_deductible}
                      onChange={(e) => setAdjustmentDraft({ ...adjustmentDraft, is_deductible: e.target.checked })} />
                    يُخصم من الراتب
                  </label>
                  <label className="flex flex-1 flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                    السبب
                    <input value={adjustmentDraft.notes}
                      onChange={(e) => setAdjustmentDraft({ ...adjustmentDraft, notes: e.target.value })}
                      className={inputClass} />
                  </label>
                  <button onClick={() => void addAdjustment()} disabled={busy}
                    className="flex h-10 items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 text-sm font-bold text-white disabled:opacity-60">
                    <CalendarX className="w-4 h-4" /> تسجيل
                  </button>
                </div>
              )}

              <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
                <table className="w-full min-w-[38rem]">
                  <thead className="bg-[var(--color-surface-2)]">
                    <tr>
                      <th className={headClass}>التاريخ</th>
                      <th className={headClass}>النوع</th>
                      <th className={headClass}>المقدار</th>
                      <th className={headClass}>يُخصم؟</th>
                      <th className={headClass}>السبب</th>
                      <th className={headClass}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {adjustments.map((row) => (
                      <tr key={row.id} className="border-t border-[var(--color-border)]">
                        <td className={cellClass}>{formatDateLocalized(row.date)}</td>
                        <td className={cellClass}>{row.kind_label}</td>
                        <td className={`${cellClass} font-bold`}>
                          {row.kind === "absence"
                            ? `${formatHours(row.days)} يوم`
                            : formatLateMinutes(row.minutes)}
                        </td>
                        <td className={cellClass}>{row.is_deductible ? "نعم" : "لا (معذور)"}</td>
                        <td className={cellClass}>{row.notes}</td>
                        <td className={cellClass}>
                          {canManage && (
                            <button
                              onClick={() => void deleteAdjustment(row.id).then(loadDaily)}
                              className="rounded-md p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                              title="حذف"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {adjustments.length === 0 && !loading && (
                      <tr>
                        <td colSpan={6} className="px-3 py-8 text-center text-sm text-[var(--color-text-muted)]">
                          لا غيابات ولا تأخيرات في {monthKeyLabel(month)} — الراتب كامل.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {/* ═══ كشوف الرواتب ═══ */}
      {tab === "payslips" && selected && (
        <div className="space-y-3">
          <div className="flex items-center gap-1">
            <button onClick={() => setMonth(shiftMonthKey(month, -1))}
              className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]" title="الشهر السابق">
              <ChevronRight className="w-4 h-4" />
            </button>
            <span className="min-w-[9rem] text-center font-semibold">{monthKeyLabel(month)}</span>
            <button onClick={() => setMonth(shiftMonthKey(month, 1))}
              className="p-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]" title="الشهر التالي">
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>

          {/* معاينة الفترة — من الخادم، فما يُعرض هنا هو ما يُحفظ */}
          {canManage && (
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 space-y-3">
              <div className="grid gap-2 md:grid-cols-3">
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  بدلات / مكافأة
                  <input type="number" min="0" step="0.01" value={slipDraft.allowances}
                    onChange={(e) => setSlipDraft({ ...slipDraft, allowances: e.target.value })}
                    className={inputClass} />
                </label>
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  خصومات أخرى
                  <input type="number" min="0" step="0.01" value={slipDraft.other_deductions}
                    onChange={(e) => setSlipDraft({ ...slipDraft, other_deductions: e.target.value })}
                    className={inputClass} />
                </label>
                <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                  ملاحظات
                  <input value={slipDraft.notes}
                    onChange={(e) => setSlipDraft({ ...slipDraft, notes: e.target.value })}
                    className={inputClass} />
                </label>
              </div>

              {preview && (
                <div className="flex flex-wrap gap-3 rounded-lg bg-[var(--color-surface-2)] p-3 text-sm">
                  {selected.pay_type === "hourly" ? (
                    <span>الساعات: <b>{formatHours(preview.worked_hours)}</b></span>
                  ) : (
                    <>
                      <span>غياب: <b>{formatHours(preview.absence_days)} يوم</b></span>
                      <span>تأخير: <b>{formatLateMinutes(preview.late_minutes)}</b></span>
                    </>
                  )}
                  <span>الاستحقاق: <b>{formatMoney(preview.gross)}</b></span>
                  <span>خصم الغياب: <b>{formatMoney(preview.absence_deduction)}</b></span>
                  <span>خصم التأخير: <b>{formatMoney(preview.late_deduction)}</b></span>
                  <span className="text-[var(--color-primary-emphasis)]">
                    الصافي: <b>{formatMoney(preview.net)}</b>
                  </span>
                </div>
              )}

              <button onClick={() => void generateSlip()} disabled={busy}
                className="flex items-center gap-2 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white disabled:opacity-60">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                إنشاء كشف {monthKeyLabel(month)}
              </button>
            </div>
          )}

          <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
            <table className="w-full min-w-[52rem]">
              <thead className="bg-[var(--color-surface-2)]">
                <tr>
                  <th className={headClass}>الفترة</th>
                  <th className={headClass}>الاستحقاق</th>
                  <th className={headClass}>البدلات</th>
                  <th className={headClass}>الخصومات</th>
                  <th className={headClass}>الصافي</th>
                  <th className={headClass}>المصروف</th>
                  <th className={headClass}>الحالة</th>
                  <th className={headClass}></th>
                </tr>
              </thead>
              <tbody>
                {payslips.map((row) => {
                  const deductions =
                    Number(row.absence_deduction) + Number(row.late_deduction) + Number(row.other_deductions);
                  return (
                    <tr key={row.id} className="border-t border-[var(--color-border)]">
                      <td className={cellClass}>
                        {formatDateLocalized(row.period_start)} — {formatDateLocalized(row.period_end)}
                      </td>
                      <td className={cellClass}>{formatMoney(row.gross)}</td>
                      <td className={cellClass}>{formatMoney(row.allowances)}</td>
                      <td className={cellClass}>{formatMoney(deductions)}</td>
                      <td className={`${cellClass} font-bold`}>{formatMoney(row.net)}</td>
                      <td className={cellClass}>{formatMoney(row.paid_total)}</td>
                      <td className={cellClass}>
                        <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                          row.status === "posted"
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                            : "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"}`}>
                          {row.status_label}
                        </span>
                      </td>
                      <td className={cellClass}>
                        <div className="flex gap-1">
                          {row.status === "draft" && canPost && (
                            <button
                              onClick={() => void runOnSlip(
                                () => postPayslip(row.id), "تم اعتماد الكشف وترحيل قيده", "تعذر ترحيل الكشف")}
                              className="flex items-center gap-1 rounded-md bg-emerald-600 px-2 py-1 text-xs font-bold text-white"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5" /> اعتماد وترحيل
                            </button>
                          )}
                          {row.status === "posted" && canPost && (
                            <button
                              onClick={() => void runOnSlip(
                                () => unpostPayslip(row.id), "تم إلغاء ترحيل الكشف", "تعذر إلغاء الترحيل")}
                              className="flex items-center gap-1 rounded-md border border-[var(--color-border)] px-2 py-1 text-xs"
                            >
                              <RotateCcw className="w-3.5 h-3.5" /> إلغاء الترحيل
                            </button>
                          )}
                          {row.status === "draft" && canManage && (
                            <button
                              onClick={() => void runOnSlip(
                                () => deletePayslip(row.id), "تم حذف الكشف", "تعذر حذف الكشف")}
                              className="rounded-md p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                              title="حذف"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {payslips.length === 0 && !loading && (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-sm text-[var(--color-text-muted)]">
                      لا كشوف لهذا الموظف بعد.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* الصرف */}
          {canPost && (
            <div className="flex flex-wrap items-end gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
              <span className="flex items-center gap-2 pb-2 text-sm font-bold">
                <Wallet className="w-4 h-4 text-[var(--color-primary)]" /> صرف راتب
              </span>
              <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                التاريخ
                <input type="date" value={paymentDraft.date}
                  onChange={(e) => setPaymentDraft({ ...paymentDraft, date: e.target.value })}
                  className={inputClass} />
              </label>
              <label className="flex flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                المبلغ
                <input type="number" min="0" step="0.01" value={paymentDraft.amount}
                  onChange={(e) => setPaymentDraft({ ...paymentDraft, amount: e.target.value })}
                  className={`${inputClass} w-32`} />
              </label>
              <label className="flex flex-1 flex-col gap-1 text-xs text-[var(--color-text-muted)]">
                ملاحظة
                <input value={paymentDraft.notes}
                  onChange={(e) => setPaymentDraft({ ...paymentDraft, notes: e.target.value })}
                  className={inputClass} />
              </label>
              <button onClick={() => void payEmployee()} disabled={busy}
                className="flex h-10 items-center gap-2 rounded-lg bg-emerald-600 px-4 text-sm font-bold text-white disabled:opacity-60">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Banknote className="w-4 h-4" />}
                صرف من الصندوق
              </button>
            </div>
          )}

          {payments.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
              <table className="w-full min-w-[34rem]">
                <thead className="bg-[var(--color-surface-2)]">
                  <tr>
                    <th className={headClass}>تاريخ الصرف</th>
                    <th className={headClass}>المبلغ</th>
                    <th className={headClass}>من حساب</th>
                    <th className={headClass}>ملاحظة</th>
                    <th className={headClass}></th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((row) => (
                    <tr key={row.id} className="border-t border-[var(--color-border)]">
                      <td className={cellClass}>{formatDateLocalized(row.date)}</td>
                      <td className={`${cellClass} font-bold`}>{formatMoney(row.amount)}</td>
                      <td className={cellClass}>{row.cash_account_name || "—"}</td>
                      <td className={cellClass}>{row.notes}</td>
                      <td className={cellClass}>
                        {canPost && (
                          <button
                            onClick={() => void runOnSlip(
                              () => deletePayrollPayment(row.id),
                              "تم حذف سند الصرف وقيده", "تعذر حذف سند الصرف")}
                            className="rounded-md p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                            title="حذف السند وقيده"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PayrollPage;
