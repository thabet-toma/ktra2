import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Copy,
  Loader2,
  Search,
  UserPlus,
  X,
} from "lucide-react";
import {
  cancelInvitation,
  createEmployee,
  inviteEmployee,
  listEmployees,
  listPendingInvitations,
  resendInvitation,
  type CreateEmployeeResponse,
  type EmployeeDto,
  type EmployeeInvitationDto,
} from "../../services/employeeOpsApi";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { EmployeeCardModal } from "./EmployeeCardModal";

export const EmployeeOpsPeopleScreen: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();

  const [employees, setEmployees] = useState<EmployeeDto[]>([]);
  const [invitations, setInvitations] = useState<EmployeeInvitationDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  // نافذة كرت الموظف
  const [selectedCardEmployeeId, setSelectedCardEmployeeId] = useState<number | null>(null);

  // نافذة إضافة موظف
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newJobTitle, setNewJobTitle] = useState("");
  const [newManagerId, setNewManagerId] = useState<number | null>(null);
  const [savingEmployee, setSavingEmployee] = useState(false);

  // عرض رابط الدعوة لمرة واحدة فقط
  const [createdInviteData, setCreatedInviteData] = useState<{
    employeeName: string;
    invitationUrl: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // فشلُ الدعوات لا يُبتلع: قائمةٌ فارغةٌ بصمتٍ تعني أنّ كلّ مدعوٍّ يظهر
      // «بدون حساب» فيُدعى ثانيةً — وكلُّ دعوةٍ ناجحةٍ تستهلك مقعداً.
      const [emps, invs] = await Promise.all([
        listEmployees(),
        listPendingInvitations().catch((err: any) => {
          toast(err?.message || "تعذّر تحميل الدعوات المعلقة — قد تظهر حالاتٌ ناقصة", "error");
          return [] as EmployeeInvitationDto[];
        }),
      ]);
      setEmployees(emps);
      setInvitations(invs);
    } catch (err: any) {
      toast(err?.message || "فشل تحميل بيانات الموظفين", "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleCreateEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      toast("اسم الموظف مطلوب", "error");
      return;
    }

    setSavingEmployee(true);
    try {
      const res: CreateEmployeeResponse = await createEmployee({
        name: newName.trim(),
        phone: newPhone.trim(),
        job_title: newJobTitle.trim(),
        manager: newManagerId,
      });

      toast("تم إنشاء سجل الموظف وتوليد رابط الدعوة بنجاح", "success");
      setIsAddModalOpen(false);
      setNewName("");
      setNewPhone("");
      setNewJobTitle("");
      setNewManagerId(null);

      // عرض رابط الدعوة لمرة واحدة فقط!
      setCreatedInviteData({
        employeeName: res.employee.name,
        invitationUrl: res.invitation_url,
      });
      setCopied(false);

      void loadData();
    } catch (err: any) {
      toast(err?.message || "فشل إنشاء الموظف والدعوة", "error");
    } finally {
      setSavingEmployee(false);
    }
  };

  const handleCopyInviteUrl = async () => {
    if (!createdInviteData?.invitationUrl) return;
    try {
      await navigator.clipboard.writeText(createdInviteData.invitationUrl);
      setCopied(true);
      toast("تم نسخ رابط الدعوة إلى الحافظة", "success");
      setTimeout(() => setCopied(false), 3000);
    } catch {
      toast("تعذر نسخ الرابط تلقائياً، يرجى نسخه يدوياً", "info");
    }
  };

  const handleInviteAgain = async (employee: EmployeeDto) => {
    setActionLoadingId(employee.id);
    try {
      const res = await inviteEmployee(employee.id);
      toast("تم توليد رابط دعوة جديد للموظف", "success");
      setCreatedInviteData({
        employeeName: employee.name,
        invitationUrl: res.invitation_url,
      });
      setCopied(false);
      void loadData();
    } catch (err: any) {
      toast(err?.message || "فشل توليد رابط الدعوة", "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleResendPending = async (invitation: EmployeeInvitationDto) => {
    setActionLoadingId(invitation.employee);
    try {
      const res = await resendInvitation(invitation.id);
      toast("تم تجديد رابط الدعوة", "success");
      setCreatedInviteData({
        employeeName: invitation.employee_name,
        invitationUrl: res.invitation_url,
      });
      setCopied(false);
      void loadData();
    } catch (err: any) {
      toast(err?.message || "فشل تجديد الدعوة", "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleCancelPending = async (invitation: EmployeeInvitationDto) => {
    const ok = await confirm({
      title: "إلغاء دعوة الموظف",
      message: `هل تريد إلغاء دعوة الانضمام للموظف (${invitation.employee_name})؟ سيتم إبطال الرابط فوراً.`,
      confirmText: "إلغاء الدعوة",
      danger: true,
    });
    if (!ok) return;

    setActionLoadingId(invitation.employee);
    try {
      await cancelInvitation(invitation.id);
      toast("تم إلغاء الدعوة بنجاح", "success");
      void loadData();
    } catch (err: any) {
      toast(err?.message || "فشل إلغاء الدعوة", "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  const filteredEmployees = useMemo(() => {
    if (!searchQuery.trim()) return employees;
    const q = searchQuery.toLowerCase().trim();
    return employees.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        (e.code || "").toLowerCase().includes(q) ||
        (e.phone || "").toLowerCase().includes(q) ||
        (e.job_title || "").toLowerCase().includes(q),
    );
  }, [employees, searchQuery]);

  return (
    <div className="space-y-4 p-4 md:p-6 max-w-7xl mx-auto">
      {/* الترويسة وأزرار الإجراء */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
        <div>
          <h1 className="text-lg font-bold text-[var(--color-text)]">الموظفون</h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
            إدارة موظفي الشركة، دعوة الموظفين الجدد، وبطاقات المتابعة والملاحظات
          </p>
        </div>

        <button
          type="button"
          onClick={() => setIsAddModalOpen(true)}
          className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-bold text-white hover:opacity-90 shadow-sm"
        >
          <UserPlus className="h-4 w-4" /> أضف موظفاً
        </button>
      </div>

      {/* البحث */}
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
        <div className="relative">
          <Search className="absolute right-3 top-2.5 h-4 w-4 text-[var(--color-text-muted)]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="بحث بالاسم، رقم الهاتف، المسمى، أو الكود..."
            className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] pr-9 pl-3 text-xs text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
          />
        </div>
      </div>

      {/* جدول الموظفين */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--color-primary)]" />
        </div>
      ) : filteredEmployees.length === 0 ? (
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center text-xs text-[var(--color-text-muted)]">
          لا يوجد موظفون مسجلون يطابقون البحث.
        </div>
      ) : (
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead>
                <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-muted)]">
                  <th className="py-2.5 px-3 font-semibold">الموظف</th>
                  <th className="py-2.5 px-3 font-semibold">المسمى الوظيفي</th>
                  <th className="py-2.5 px-3 font-semibold">الهاتف</th>
                  <th className="py-2.5 px-3 font-semibold">المدير المباشر</th>
                  <th className="py-2.5 px-3 font-semibold text-center">حساب المنصة</th>
                  <th className="py-2.5 px-3 font-semibold text-center">الحالة</th>
                  <th className="py-2.5 px-3 font-semibold text-center">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {filteredEmployees.map((emp) => {
                  const pendingInv = invitations.find((inv) => inv.employee === emp.id);
                  const isActionLoading = actionLoadingId === emp.id;

                  return (
                    <tr key={emp.id} className="hover:bg-[var(--color-surface-2)] transition-colors">
                      <td className="py-3 px-3 font-bold text-[var(--color-text)]">
                        <button
                          type="button"
                          onClick={() => setSelectedCardEmployeeId(emp.id)}
                          className="hover:text-[var(--color-primary)] hover:underline text-right"
                        >
                          {emp.name}
                        </button>
                        {emp.code && (
                          <span className="text-[10px] text-[var(--color-text-muted)] block">
                            كود: {emp.code}
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-3 text-[var(--color-text-muted)]">
                        {emp.job_title || "—"}
                      </td>

                      <td className="py-3 px-3 text-[var(--color-text-muted)] font-mono">
                        {emp.phone || "—"}
                      </td>

                      <td className="py-3 px-3 text-[var(--color-text-muted)]">
                        {emp.manager_name || "—"}
                      </td>

                      <td className="py-3 px-3 text-center">
                        {/* العضويّةُ لا الحساب — كالزرِّ بجانبه سواءً: العائدُ إلى
                            العمل كان يُوصَف «مفعّل» وبجواره زرُّ «إرسال دعوة». */}
                        {emp.has_membership ? (
                          <span className="inline-block rounded px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                            مفعّل
                          </span>
                        ) : pendingInv ? (
                          <span className="inline-block rounded px-2 py-0.5 text-[10px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                            دعوة معلقة
                          </span>
                        ) : emp.has_account ? (
                          <span className="inline-block rounded px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            حساب بلا عضوية
                          </span>
                        ) : (
                          <span className="inline-block rounded px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            بدون حساب
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-3 text-center">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold ${
                            emp.is_active
                              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                              : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300"
                          }`}
                        >
                          {emp.is_active ? "نشط" : "معطل"}
                        </span>
                      </td>

                      <td className="py-3 px-3 text-center">
                        <div className="flex items-center justify-center gap-1.5 flex-wrap">
                          <button
                            type="button"
                            onClick={() => setSelectedCardEmployeeId(emp.id)}
                            className="rounded border border-[var(--color-border)] px-2 py-1 text-[11px] font-semibold text-[var(--color-primary)] hover:bg-[var(--color-surface-3)]"
                          >
                            كرت الموظف
                          </button>

                          {/* العضويّةُ لا الحساب: العائدُ إلى العمل يحتفظ بـuser
                              وتُحذف عضويّتُه، فيستحقّ دعوةً جديدةً يقبلها الخادم. */}
                          {!emp.has_membership && (
                            <>
                              {pendingInv ? (
                                <>
                                  <button
                                    type="button"
                                    disabled={isActionLoading}
                                    onClick={() => handleResendPending(pendingInv)}
                                    title="تجديد رابط الدعوة"
                                    className="rounded border border-amber-300 px-2 py-1 text-[11px] font-semibold text-amber-700 hover:bg-amber-50 dark:border-amber-900 dark:text-amber-300"
                                  >
                                    تجديد الدعوة
                                  </button>
                                  <button
                                    type="button"
                                    disabled={isActionLoading}
                                    onClick={() => handleCancelPending(pendingInv)}
                                    title="إلغاء الدعوة"
                                    className="text-rose-600 hover:text-rose-800 p-1"
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  disabled={isActionLoading}
                                  onClick={() => handleInviteAgain(emp)}
                                  className="rounded border border-[var(--color-primary)] px-2 py-1 text-[11px] font-semibold text-[var(--color-primary)] hover:bg-[var(--color-primary)]/10"
                                >
                                  إرسال دعوة
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* مودال إضافة موظف ودعوته */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="relative w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
              <h2 className="text-base font-bold text-[var(--color-text)]">إضافة موظف جديد ودعوته</h2>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreateEmployee} className="space-y-3.5 text-xs">
              <div>
                <label className="mb-1 block font-semibold text-[var(--color-text)]">
                  اسم الموظف <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="الاسم الكامل للموظف"
                  className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                />
              </div>

              <div>
                <label className="mb-1 block font-semibold text-[var(--color-text)]">رقم الهاتف</label>
                <input
                  type="tel"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  placeholder="059xxxxxxx"
                  className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                />
              </div>

              <div>
                <label className="mb-1 block font-semibold text-[var(--color-text)]">المسمى الوظيفي</label>
                <input
                  type="text"
                  value={newJobTitle}
                  onChange={(e) => setNewJobTitle(e.target.value)}
                  placeholder="مثال: مسؤول مبيعات، فني صيانة، مندوب مشتريات..."
                  className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                />
              </div>

              <div>
                <label className="mb-1 block font-semibold text-[var(--color-text)]">المدير المباشر (اختياري)</label>
                <select
                  value={newManagerId ?? ""}
                  onChange={(e) => setNewManagerId(e.target.value ? Number(e.target.value) : null)}
                  className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                >
                  <option value="">بدون مدير مباشر</option>
                  {employees
                    .filter((e) => e.is_active)
                    .map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.name} {e.job_title ? `(${e.job_title})` : ""}
                      </option>
                    ))}
                </select>
              </div>

              <div className="pt-3 border-t border-[var(--color-border)] flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={savingEmployee}
                  className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-5 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50"
                >
                  {savingEmployee && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  حفظ وتوليد رابط الدعوة
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* نافذة رابط الدعوة (مرّة واحدة مع زر نسخ وتنبيه) */}
      {createdInviteData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 overflow-y-auto">
          <div className="relative w-full max-w-lg rounded-2xl border border-amber-300 bg-[var(--color-surface)] p-6 shadow-2xl space-y-4">
            <div className="flex items-center gap-2 text-amber-600">
              <AlertCircle className="h-6 w-6 flex-shrink-0" />
              <h3 className="text-base font-bold text-[var(--color-text)]">
                رابط دعوة الموظف ({createdInviteData.employeeName})
              </h3>
            </div>

            <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20 p-3.5 text-xs text-amber-900 dark:text-amber-200 space-y-2">
              <p className="font-bold leading-relaxed">
                تنبيه أمني هام: هذا الرابط سيظهر لك{" "}
                <span className="underline decoration-2">لمرة واحدة فقط</span> ولن يتمكن النظام من
                إظهاره مجدداً للحفاظ على سرية الرمز. يرجى نسخه ومشاركته مع الموظف فوراً.
              </p>
              <p className="text-[11px] text-amber-800 dark:text-amber-300">
                يقوم الموظف بفتح هذا الرابط لإنشاء حسابه وكلمة مروره والانضمام لشركتكم.
              </p>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-semibold text-[var(--color-text)]">رابط الدعوة:</label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={createdInviteData.invitationUrl}
                  className="h-10 flex-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs font-mono text-[var(--color-text)] select-all"
                />
                <button
                  type="button"
                  onClick={handleCopyInviteUrl}
                  className={`flex items-center gap-1.5 h-10 px-4 rounded-lg text-xs font-bold text-white transition-all ${
                    copied ? "bg-emerald-600" : "bg-[var(--color-primary)] hover:opacity-90"
                  }`}
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {copied ? "تم النسخ" : "نسخ الرابط"}
                </button>
              </div>
            </div>

            <div className="pt-3 border-t border-[var(--color-border)] flex justify-end">
              <button
                type="button"
                onClick={() => setCreatedInviteData(null)}
                className="rounded-lg bg-[var(--color-surface-3)] px-5 py-2 text-xs font-bold text-[var(--color-text)] hover:bg-[var(--color-border)]"
              >
                تم النسخ والمتابعة
              </button>
            </div>
          </div>
        </div>
      )}

      {/* كرت الموظف */}
      {selectedCardEmployeeId && (
        <EmployeeCardModal
          employeeId={selectedCardEmployeeId}
          isOpen={Boolean(selectedCardEmployeeId)}
          onClose={() => setSelectedCardEmployeeId(null)}
          onEmployeeChanged={() => void loadData()}
        />
      )}
    </div>
  );
};
