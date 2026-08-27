import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Inbox, Plus, Loader2, X, Check, Send, Ban, ThumbsUp, ThumbsDown,
  Wallet, CalendarDays, FileText, CircleDollarSign,
} from "lucide-react";
import {
  REQUEST_KIND_LABELS, REQUEST_STATUS_LABELS,
  approveRequest, cancelAdvance, cancelRequest, createRequest, disburseAdvance,
  listAdvances, listLeaveBalances, listLeaveTypes, listRequests, rejectRequest,
  submitRequest,
  type AdvanceRow, type EmployeeRequestRow, type LeaveBalanceRow, type LeaveTypeRow,
  type RequestKind,
} from "../../services/hrRequestsApi";
import { listEmployees, type Employee } from "../../services/payrollApi";
import { formatNumber } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { usePermissions } from "../../contexts/PermissionsContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";

/**
 * T-HR M5/M7 — «الطلبات والسلف»: طلباتي، وصندوق الموافقات، والسلف.
 *
 * **آلة الحالات خادمية بالكامل** (`hr/requests.py`) — الشاشة تعرض ما وصل
 * إليه الطلب وتُطلق أفعالاً مسمّاة، ولا تقرّر متى يصير موافقاً.
 *
 * وسلسلةُ المستويات تُعرض كاملةً لا الخطوة الحالية وحدها: صاحبُ الطلب يحتاج
 * أن يعرف **أين وصل ومن بقي**، لا أن ينتظر بلا خبر.
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

type Tab = "mine" | "inbox" | "all" | "advances" | "balances";

const statusClass = (status: string) => {
  const base = "inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold";
  if (status === "approved") return `${base} bg-emerald-100 text-emerald-800`;
  if (status === "rejected") return `${base} bg-red-100 text-red-800`;
  if (status === "pending") return `${base} bg-amber-100 text-amber-900`;
  if (status === "cancelled") return `${base} bg-slate-100 text-slate-600`;
  return `${base} bg-sky-100 text-sky-800`;
};

interface Draft {
  kind: RequestKind;
  employee: number | "";
  leave_type: number | "";
  date_from: string;
  date_to: string;
  amount: string;
  installments: string;
  description: string;
}

const EMPTY_DRAFT: Draft = {
  kind: "leave", employee: "", leave_type: "", date_from: "", date_to: "",
  amount: "", installments: "1", description: "",
};

export const RequestsPage: React.FC = () => {
  const permissions = usePermissions();
  const toast = useToast();
  const confirm = useConfirm();
  const canApprove = permissions.can("hr.requests.approve");
  const canViewAll = permissions.can("hr.requests.view") || canApprove;
  const canDisburse = permissions.can("hr.payroll.post");

  const [tab, setTab] = useState<Tab>(canApprove ? "inbox" : "mine");
  const [rows, setRows] = useState<EmployeeRequestRow[]>([]);
  const [advances, setAdvances] = useState<AdvanceRow[]>([]);
  const [balances, setBalances] = useState<LeaveBalanceRow[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<LeaveTypeRow[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const scope = tab === "mine" ? "mine" : tab === "inbox" ? "inbox" : undefined;
      const [requestRows, types] = await Promise.all([
        listRequests(scope ? { scope } : undefined),
        listLeaveTypes(),
      ]);
      setRows(requestRows);
      setLeaveTypes(types);
      if (canViewAll) {
        const staff = await listEmployees();
        setEmployees(staff);
      }
      if (tab === "advances" && canDisburse) setAdvances(await listAdvances());
      if (tab === "balances" && canViewAll) setBalances(await listLeaveBalances());
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر تحميل الطلبات."), "error");
    } finally {
      setLoading(false);
    }
  }, [tab, canViewAll, canDisburse, toast]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const activeLeaveTypes = useMemo(
    () => leaveTypes.filter((t) => t.is_active), [leaveTypes]);

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

  const decide = async (row: EmployeeRequestRow, approving: boolean) => {
    const ok = await confirm({
      title: approving ? "الموافقة على الطلب" : "رفض الطلب",
      message: approving
        ? `ستوافق على ${row.kind_label} لـ«${row.employee_name}».`
        : `سترفض ${row.kind_label} لـ«${row.employee_name}». الرفض يقطع سلسلة الاعتماد.`,
      confirmText: approving ? "موافقة" : "رفض",
      danger: !approving,
    });
    if (!ok) return;
    await act(
      () => (approving ? approveRequest(row.id) : rejectRequest(row.id)),
      approving ? "تمت الموافقة." : "تم الرفض.");
  };

  const saveDraft = async () => {
    if (!draft) return;
    const payload: Record<string, unknown> = {
      kind: draft.kind,
      description: draft.description,
    };
    if (draft.employee) payload.employee = Number(draft.employee);
    if (draft.kind === "leave") {
      payload.leave_type = draft.leave_type ? Number(draft.leave_type) : null;
      payload.date_from = draft.date_from;
      payload.date_to = draft.date_to;
    } else if (draft.kind === "advance" || draft.kind === "expense") {
      payload.amount = draft.amount;
      if (draft.kind === "advance") payload.installments = Number(draft.installments) || 1;
    }
    setBusy(true);
    try {
      const created = await createRequest(payload);
      await submitRequest(created.id);
      toast("قُدّم الطلب للاعتماد.", "success");
      setDraft(null);
      await reload();
    } catch (cause) {
      toast(humanizeThrown(cause, "تعذّر تقديم الطلب."), "error");
    } finally {
      setBusy(false);
    }
  };

  const tabs: [Tab, string, React.ReactNode][] = [
    ["mine", "طلباتي", <FileText size={14} key="m" />],
    ...(canApprove
      ? [["inbox", "بانتظار موافقتي", <Inbox size={14} key="i" />] as [Tab, string, React.ReactNode]]
      : []),
    ...(canViewAll
      ? [["all", "كل الطلبات", <CalendarDays size={14} key="a" />] as [Tab, string, React.ReactNode]]
      : []),
    ...(canDisburse
      ? [["advances", "السلف", <Wallet size={14} key="w" />] as [Tab, string, React.ReactNode]]
      : []),
    ...(canViewAll
      ? [["balances", "أرصدة الإجازات", <CircleDollarSign size={14} key="b" />] as [Tab, string, React.ReactNode]]
      : []),
  ];

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        <Inbox size={20} className="text-[var(--color-primary)]" />
        <h1 className="text-lg font-bold">الطلبات والسلف</h1>
        <button
          type="button"
          className={`${btnPrimary} ms-auto`}
          onClick={() => setDraft({ ...EMPTY_DRAFT })}
        >
          <Plus size={14} /> طلب جديد
        </button>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-[var(--color-border)]">
        {tabs.map(([key, label, icon]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm ${
              tab === key
                ? "border-b-2 border-[var(--color-primary)] font-semibold text-[var(--color-primary)]"
                : "text-[var(--color-text-muted)]"
            }`}
          >
            {icon}
            {label}
          </button>
        ))}
      </nav>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin" /></div>
      ) : tab === "advances" ? (
        <AdvancesTable
          rows={advances}
          busy={busy}
          onDisburse={(row) => void act(
            () => disburseAdvance(row.id, {}), "صُرفت السلفة وسُجّل سندها.")}
          onCancel={(row) => void act(() => cancelAdvance(row.id), "أُلغيت السلفة.")}
        />
      ) : tab === "balances" ? (
        <BalancesTable rows={balances} />
      ) : (
        <div className={`${cardClass} space-y-2`}>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-[var(--color-text-muted)]">
              {tab === "inbox" ? "لا طلبات بانتظار موافقتك." : "لا طلبات بعد."}
            </p>
          ) : (
            rows.map((row) => (
              <article
                key={row.id}
                className="rounded-xl border border-[var(--color-border)] p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{row.employee_name}</span>
                  <span className="text-sm">{row.kind_label}</span>
                  <span className={statusClass(row.status)}>{row.status_label}</span>
                  {row.kind === "leave" && row.date_from && (
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {formatDateLocalized(row.date_from)} — {formatDateLocalized(row.date_to || "")}
                      {" · "}{formatNumber(Number(row.days), { maxDecimals: 0 })} يوم
                      {row.leave_type_name ? ` · ${row.leave_type_name}` : ""}
                    </span>
                  )}
                  {row.amount && (
                    <span className="text-xs text-[var(--color-text-muted)]">
                      {formatNumber(row.amount)}
                      {row.installments ? ` · ${row.installments} أقساط` : ""}
                    </span>
                  )}
                  <span className="ms-auto flex flex-wrap items-center gap-1">
                    {row.status === "draft" && (
                      <button
                        type="button"
                        className={btnGhost}
                        disabled={busy}
                        onClick={() => void act(() => submitRequest(row.id), "قُدّم الطلب.")}
                      >
                        <Send size={14} /> تقديم
                      </button>
                    )}
                    {row.status === "pending" && canApprove && (
                      <>
                        <button
                          type="button"
                          className={btnGhost}
                          disabled={busy}
                          onClick={() => void decide(row, true)}
                        >
                          <ThumbsUp size={14} /> موافقة
                        </button>
                        <button
                          type="button"
                          className={btnGhost}
                          disabled={busy}
                          onClick={() => void decide(row, false)}
                        >
                          <ThumbsDown size={14} /> رفض
                        </button>
                      </>
                    )}
                    {(row.status === "draft" || row.status === "pending") && (
                      <button
                        type="button"
                        className={btnGhost}
                        disabled={busy}
                        onClick={() => void act(() => cancelRequest(row.id), "أُلغي الطلب.")}
                      >
                        <Ban size={14} /> إلغاء
                      </button>
                    )}
                  </span>
                </div>

                {row.description && (
                  <p className="mt-1 text-sm text-[var(--color-text-muted)]">{row.description}</p>
                )}

                {row.steps.length > 0 && (
                  <ol className="mt-2 flex flex-wrap gap-2 text-[11px]">
                    {row.steps.map((step) => (
                      <li key={step.id} className="flex items-center gap-1">
                        <span className={statusClass(step.status)}>
                          مستوى {formatNumber(step.level, { maxDecimals: 0 })}: {step.status_label}
                        </span>
                        {step.approver_name && (
                          <span className="text-[var(--color-text-muted)]">
                            ({step.approver_name})
                          </span>
                        )}
                        {step.acted_by_name && (
                          <span className="text-[var(--color-text-muted)]">
                            — {step.acted_by_name}
                          </span>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
                {row.decision_note && (
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                    ملاحظة القرار: {row.decision_note}
                  </p>
                )}
              </article>
            ))
          )}
        </div>
      )}

      {draft && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-3">
          <div className={`${cardClass} w-full max-w-md`}>
            <div className="mb-3 flex items-center gap-2">
              <h2 className="font-bold">طلب جديد</h2>
              <button type="button" className="ms-auto" onClick={() => setDraft(null)} aria-label="إغلاق">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              <div>
                <label className={labelClass} htmlFor="req-kind">نوع الطلب</label>
                <select
                  id="req-kind"
                  className={inputClass}
                  value={draft.kind}
                  onChange={(event) => setDraft({ ...draft, kind: event.target.value as RequestKind })}
                >
                  {(Object.keys(REQUEST_KIND_LABELS) as RequestKind[]).map((key) => (
                    <option key={key} value={key}>{REQUEST_KIND_LABELS[key]}</option>
                  ))}
                </select>
              </div>

              {canViewAll && (
                <div>
                  <label className={labelClass} htmlFor="req-employee">الموظف</label>
                  <select
                    id="req-employee"
                    className={inputClass}
                    value={draft.employee}
                    onChange={(event) => setDraft({
                      ...draft,
                      employee: event.target.value ? Number(event.target.value) : "",
                    })}
                  >
                    <option value="">— أنا —</option>
                    {employees.map((employee) => (
                      <option key={employee.id} value={employee.id}>{employee.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {draft.kind === "leave" && (
                <>
                  <div>
                    <label className={labelClass} htmlFor="req-type">نوع الإجازة</label>
                    <select
                      id="req-type"
                      className={inputClass}
                      value={draft.leave_type}
                      onChange={(event) => setDraft({
                        ...draft,
                        leave_type: event.target.value ? Number(event.target.value) : "",
                      })}
                    >
                      <option value="">— اختر —</option>
                      {activeLeaveTypes.map((type) => (
                        <option key={type.id} value={type.id}>
                          {type.name}{type.is_paid ? "" : " (بلا أجر)"}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className={labelClass} htmlFor="req-from">من</label>
                      <input
                        id="req-from"
                        type="date"
                        className={inputClass}
                        value={draft.date_from}
                        onChange={(event) => setDraft({ ...draft, date_from: event.target.value })}
                      />
                    </div>
                    <div>
                      <label className={labelClass} htmlFor="req-to">إلى</label>
                      <input
                        id="req-to"
                        type="date"
                        className={inputClass}
                        value={draft.date_to}
                        onChange={(event) => setDraft({ ...draft, date_to: event.target.value })}
                      />
                    </div>
                  </div>
                </>
              )}

              {(draft.kind === "advance" || draft.kind === "expense") && (
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={labelClass} htmlFor="req-amount">المبلغ</label>
                    <input
                      id="req-amount"
                      type="number"
                      min={0}
                      step="0.01"
                      className={inputClass}
                      value={draft.amount}
                      onChange={(event) => setDraft({ ...draft, amount: event.target.value })}
                    />
                  </div>
                  {draft.kind === "advance" && (
                    <div>
                      <label className={labelClass} htmlFor="req-installments">عدد الأقساط</label>
                      <input
                        id="req-installments"
                        type="number"
                        min={1}
                        className={inputClass}
                        value={draft.installments}
                        onChange={(event) => setDraft({ ...draft, installments: event.target.value })}
                      />
                    </div>
                  )}
                </div>
              )}

              <div>
                <label className={labelClass} htmlFor="req-desc">السبب / الملاحظات</label>
                <textarea
                  id="req-desc"
                  className={`${inputClass} h-20 py-2`}
                  value={draft.description}
                  onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                />
              </div>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={() => setDraft(null)}>إلغاء</button>
              <button type="button" className={btnPrimary} disabled={busy} onClick={() => void saveDraft()}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                تقديم الطلب
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/** السلف — الصرف سندٌ يُنتج قيده المعتاد، والقسط يُخصم في القسيمة بلا قيدٍ ثانٍ. */
const AdvancesTable: React.FC<{
  rows: AdvanceRow[];
  busy: boolean;
  onDisburse: (row: AdvanceRow) => void;
  onCancel: (row: AdvanceRow) => void;
}> = ({ rows, busy, onDisburse, onCancel }) => (
  <div className={`${cardClass} overflow-x-auto`}>
    <table className="w-full text-sm">
      <thead>
        <tr className="text-[var(--color-text-muted)]">
          <th className="p-2 text-start">الموظف</th>
          <th className="p-2 text-start">التاريخ</th>
          <th className="p-2 text-start">الإجمالي</th>
          <th className="p-2 text-start">القسط الشهري</th>
          <th className="p-2 text-start">المتبقّي</th>
          <th className="p-2 text-start">الحالة</th>
          <th className="p-2" />
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={7} className="py-8 text-center text-[var(--color-text-muted)]">
              لا سلف — تُنشأ باعتماد طلب سلفة.
            </td>
          </tr>
        ) : (
          rows.map((row) => (
            <tr key={row.id} className="border-t border-[var(--color-border)]">
              <td className="p-2 font-semibold">{row.employee_name}</td>
              <td className="p-2">{formatDateLocalized(row.date)}</td>
              <td className="p-2">{formatNumber(row.total)}</td>
              <td className="p-2">{formatNumber(row.monthly_installment)}</td>
              <td className="p-2 font-semibold">{formatNumber(row.remaining)}</td>
              <td className="p-2">
                <span className={statusClass(row.status === "open" ? "pending" : "approved")}>
                  {row.status_label}
                </span>
                {!row.is_disbursed && row.status === "open" && (
                  <span className="ms-1 text-[11px] text-amber-800">لم تُصرَف بعد</span>
                )}
              </td>
              <td className="p-2">
                <div className="flex justify-end gap-1">
                  {row.status === "open" && !row.is_disbursed && (
                    <>
                      <button
                        type="button"
                        className={btnGhost}
                        disabled={busy}
                        onClick={() => onDisburse(row)}
                      >
                        <Wallet size={14} /> صرف
                      </button>
                      <button
                        type="button"
                        className={btnGhost}
                        disabled={busy}
                        onClick={() => onCancel(row)}
                      >
                        <Ban size={14} /> إلغاء
                      </button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  </div>
);

/** أرصدة الإجازات — مفكَّكةً كي يُقرأ سببُ الرقم لا الرقم وحده. */
const BalancesTable: React.FC<{ rows: LeaveBalanceRow[] }> = ({ rows }) => (
  <div className={`${cardClass} overflow-x-auto`}>
    <table className="w-full text-sm">
      <thead>
        <tr className="text-[var(--color-text-muted)]">
          <th className="p-2 text-start">الموظف</th>
          <th className="p-2 text-start">نوع الإجازة</th>
          <th className="p-2 text-start">المستحقّ</th>
          <th className="p-2 text-start">تسويات</th>
          <th className="p-2 text-start">المستهلَك</th>
          <th className="p-2 text-start">المتبقّي</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={6} className="py-8 text-center text-[var(--color-text-muted)]">
              لا أرصدة — عرّف أنواع الإجازات أولاً.
            </td>
          </tr>
        ) : (
          rows.flatMap((row) =>
            row.balances.map((balance) => (
              <tr key={`${row.employee}:${balance.leave_type}`} className="border-t border-[var(--color-border)]">
                <td className="p-2">{row.employee_name}</td>
                <td className="p-2">
                  {balance.leave_type_name}
                  {balance.is_paid ? "" : " (بلا أجر)"}
                </td>
                <td className="p-2">{formatNumber(balance.accrued)}</td>
                <td className="p-2">{formatNumber(balance.adjusted)}</td>
                <td className="p-2">{formatNumber(balance.taken)}</td>
                <td className="p-2 font-semibold">{formatNumber(balance.remaining)}</td>
              </tr>
            )))
        )}
      </tbody>
    </table>
  </div>
);

export default RequestsPage;
