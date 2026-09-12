import React, { useCallback, useEffect, useState } from "react";
import { Camera, Loader2, Pencil, Phone, X } from "lucide-react";

import {
  EMPLOYEE_STATUS_LABEL,
  PERFORMANCE_AXES,
  PERFORMANCE_AXIS_LABELS,
  getEmployeePerformance,
  getPlatformEmployee,
  setEmployeeProfileCard,
  uploadEmployeePhoto,
  type EmployeePerformance,
  type PlatformEmployeeRow,
} from "../../services/platformEmployeeProfileApi";
import { getEmployeeTargets, type EmployeeTargets } from "../../services/platformEmployeeTargetsApi";
import {
  getEmployeePilotPerformance,
  getEmployeeWallet,
  WALLET_LINE_STATUS_LABEL,
  type AcquisitionCommissionLineRow,
  type EmployeePilotPerformance,
  type EmployeeSalaryLineRow,
  type EmployeeWalletSummary,
  type WalletLineStatus,
} from "../../services/platformPilotApi";
import { getEmployeeActivity, type PlatformActivityLog } from "../../services/platformOpsApi";
import { PilotAxesTable } from "./PilotAxesTable";
import { useAuth } from "../../contexts/AuthContext";
import { usePlatformStaffCapabilitiesState } from "../../hooks/usePlatformStaffCapabilities";
import { useToast } from "../../contexts/ToastContext";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";

type ProfileTab = "general" | "performance" | "wallet" | "activity";

const TABS: { key: ProfileTab; label: string }[] = [
  { key: "general", label: "عام" },
  { key: "performance", label: "الأداء" },
  { key: "wallet", label: "المحفظة" },
  { key: "activity", label: "النشاط" },
];

type WalletLine = EmployeeSalaryLineRow | AcquisitionCommissionLineRow;
const isCommissionLine = (line: WalletLine): line is AcquisitionCommissionLineRow => "acquisition" in line;

/**
 * لونُ سطر المحفظة بحسب حالته — **ستُّ حالاتٍ لا اثنتان**. كان اللونُ
 * `pending ? أصفر : أخضر`، فيظهر السطرُ **المعكوس** (المُلغى) بأخضر المصروف:
 * مبلغٌ سُحب من الموظّف يُقرأ مالاً في يده.
 */
const WALLET_STATUS_CLASS: Record<WalletLineStatus, string> = {
  pending: "bg-amber-100 text-amber-700",
  eligible: "bg-amber-100 text-amber-700",
  approved: "bg-blue-100 text-blue-700",
  payable: "bg-blue-100 text-blue-700",
  paid: "bg-emerald-100 text-emerald-700",
  reversed: "bg-rose-100 text-rose-700 line-through",
};

const now = new Date();

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "؟";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[1][0]}`;
}

interface EmployeeProfileDrawerProps {
  employeeId: number;
  employeeName: string;
  onClose: () => void;
  /** يُستدعى بعد تعديل ناجحٍ للبطاقة — يتيح لمن يستضيف الدرج تحديثَ قوائمه هو. */
  onSaved?: () => void;
}

/**
 * ملفُّ الموظّف الـ360 (التذكرة 211-J): درجٌ يُفتح بمعرّف موظّف، رأسُه بطاقتُه
 * الشخصيّة (211-Q)، وتبويباتُه الأربعة تحمّل بياناتِها عند فتحها لا قبله — نداءٌ
 * واحدٌ لكلّ تبويبٍ لا خمسةٌ عند أوّل نقرة.
 *
 * **لا رقمَ يُشتقّ هنا**: كلُّ ما يُعرَض يأتي حرفيّاً من حمولة النقطة المقابلة؛
 * ما لا تُرجعه نقطةٌ لا يُعرَض ولا يُخترَع بديلٌ عنه.
 */
export const EmployeeProfileDrawer: React.FC<EmployeeProfileDrawerProps> = ({
  employeeId,
  employeeName,
  onClose,
  onSaved,
}) => {
  const toast = useToast();
  const { currentUser } = useAuth();
  const { capabilities } = usePlatformStaffCapabilitiesState(
    currentUser?.id ? String(currentUser.id) : undefined,
    !!currentUser?.isSuperAdmin,
  );
  const canManage = capabilities.is_platform_admin;

  const [employee, setEmployee] = useState<PlatformEmployeeRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<ProfileTab>("general");

  const [editing, setEditing] = useState(false);
  const [jobTitle, setJobTitle] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const loadEmployee = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const row = await getPlatformEmployee(employeeId);
      setEmployee(row);
      setJobTitle(row.job_title);
      setPhone(row.phone);
    } catch (cause) {
      setError(describePlatformOpsError(cause, "لا تصريح لك بعرض بطاقة هذا الموظّف.", "تعذّر تحميل بيانات الموظّف."));
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => { void loadEmployee(); }, [loadEmployee]);

  // تبويب «عام» — المستهدفان ومقاديرُهما المقترحة.
  const [targets, setTargets] = useState<EmployeeTargets | null>(null);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [targetsError, setTargetsError] = useState<string | null>(null);

  // تبويب «الأداء» — المحاور الخمسة الرسميّة ومحاور الـpilot الأربعة معاً.
  const [performance, setPerformance] = useState<EmployeePerformance | null>(null);
  const [pilotPerformance, setPilotPerformance] = useState<EmployeePilotPerformance | null>(null);
  const [performanceLoading, setPerformanceLoading] = useState(false);
  const [performanceError, setPerformanceError] = useState<string | null>(null);

  // تبويب «المحفظة».
  const [wallet, setWallet] = useState<EmployeeWalletSummary | null>(null);
  const [walletLoading, setWalletLoading] = useState(false);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [walletYear, setWalletYear] = useState(now.getFullYear());
  const [walletMonth, setWalletMonth] = useState(now.getMonth() + 1);

  // تبويب «النشاط».
  const [activity, setActivity] = useState<PlatformActivityLog[] | null>(null);
  const [activityLoading, setActivityLoading] = useState(false);
  const [activityError, setActivityError] = useState<string | null>(null);

  useEffect(() => {
    if (tab !== "general" || targets || targetsLoading) return;
    setTargetsLoading(true);
    setTargetsError(null);
    getEmployeeTargets(employeeId)
      .then(setTargets)
      .catch((cause) => setTargetsError(describePlatformOpsError(cause, "لا تصريح لك بعرض مستهدفات هذا الموظّف.", "تعذّر تحميل المستهدفات.")))
      .finally(() => setTargetsLoading(false));
  }, [tab, employeeId, targets, targetsLoading]);

  useEffect(() => {
    if (tab !== "performance" || performance || performanceLoading) return;
    setPerformanceLoading(true);
    setPerformanceError(null);
    Promise.all([getEmployeePerformance(employeeId), getEmployeePilotPerformance(employeeId)])
      .then(([perf, pilot]) => {
        setPerformance(perf);
        setPilotPerformance(pilot);
      })
      .catch((cause) => setPerformanceError(describePlatformOpsError(cause, "لا تصريح لك بعرض أداء هذا الموظّف.", "تعذّر تحميل الأداء.")))
      .finally(() => setPerformanceLoading(false));
  }, [tab, employeeId, performance, performanceLoading]);

  const loadWallet = useCallback(() => {
    setWalletLoading(true);
    setWalletError(null);
    getEmployeeWallet(employeeId, walletYear, walletMonth)
      .then(setWallet)
      .catch((cause) => setWalletError(describePlatformOpsError(cause, "لا تصريح لك بعرض محفظة هذا الموظّف.", "تعذّر تحميل المحفظة.")))
      .finally(() => setWalletLoading(false));
  }, [employeeId, walletYear, walletMonth]);

  useEffect(() => {
    if (tab !== "wallet" || wallet || walletLoading) return;
    loadWallet();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  useEffect(() => {
    if (tab !== "activity" || activity || activityLoading) return;
    setActivityLoading(true);
    setActivityError(null);
    getEmployeeActivity(employeeId)
      .then(setActivity)
      .catch((cause) => setActivityError(describePlatformOpsError(cause, "لا تصريح لك بعرض نشاط هذا الموظّف.", "تعذّر تحميل سجلّ النشاط.")))
      .finally(() => setActivityLoading(false));
  }, [tab, employeeId, activity, activityLoading]);

  const saveProfileCard = async () => {
    if (!employee) return;
    const payload: { phone?: string; job_title?: string } = {};
    if (phone.trim() !== employee.phone) payload.phone = phone.trim();
    if (jobTitle.trim() !== employee.job_title) payload.job_title = jobTitle.trim();
    if (Object.keys(payload).length === 0) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const updated = await setEmployeeProfileCard(employeeId, payload);
      setEmployee(updated);
      toast("حُفظت بطاقة الموظّف.", "success");
      setEditing(false);
      onSaved?.();
    } catch (cause) {
      toast(describePlatformOpsError(cause, "المسمّى الوظيفي لمدير العمليات وحده.", "تعذّر حفظ البطاقة."), "error");
    } finally {
      setSaving(false);
    }
  };

  const onPickPhoto = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const { photo_url } = await uploadEmployeePhoto(employeeId, file);
      setEmployee((prev) => (prev ? { ...prev, photo_url } : prev));
      toast("حُفظت الصورة.", "success");
      onSaved?.();
    } catch (cause) {
      toast(describePlatformOpsError(cause, "لا تصريح لك برفع صورة هذا الموظّف.", "تعذّر رفع الصورة."), "error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" dir="rtl">
      <div className="flex h-full w-full max-w-xl flex-col bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="text-sm font-bold text-slate-800">ملفّ الموظّف</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="إغلاق"
            className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="py-14 text-center text-xs text-slate-400">جاري التحميل...</div>
          ) : error || !employee ? (
            <div className="m-5 flex items-center justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => void loadEmployee()}
                className="rounded-lg bg-rose-100 px-3 py-1 text-[11px] font-bold hover:bg-rose-200"
              >
                إعادة المحاولة
              </button>
            </div>
          ) : (
            <>
              {/* الرأس: الصورة أو الأحرف الأولى، الاسم، المسمّى الوظيفي، التخصّص، الحالة والهاتف. */}
              <div className="border-b border-slate-100 p-5">
                <div className="flex items-start gap-3">
                  <div className="relative">
                    {employee.photo_url ? (
                      <img
                        src={employee.photo_url}
                        alt={employeeName}
                        className="h-16 w-16 rounded-full object-cover ring-2 ring-slate-100"
                      />
                    ) : (
                      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-100 text-lg font-bold text-blue-700 ring-2 ring-slate-100">
                        {initialsOf(employeeName)}
                      </span>
                    )}
                    {canManage && (
                      <label
                        className="absolute -bottom-1 -left-1 flex h-6 w-6 cursor-pointer items-center justify-center rounded-full bg-slate-800 text-white shadow ring-2 ring-white hover:bg-slate-900"
                        title="رفع صورة"
                      >
                        {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Camera className="h-3 w-3" />}
                        <input type="file" accept="image/*" className="hidden" onChange={onPickPhoto} disabled={uploading} />
                      </label>
                    )}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <h2 className="truncate text-base font-bold text-slate-900">{employeeName}</h2>
                      {canManage && !editing && (
                        <button
                          type="button"
                          onClick={() => setEditing(true)}
                          className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[11px] font-bold text-slate-600 transition hover:bg-slate-50"
                        >
                          <Pencil className="h-3 w-3" /> تعديل
                        </button>
                      )}
                    </div>

                    {!editing ? (
                      <div className="mt-1 space-y-1">
                        {employee.job_title && (
                          <p className="text-xs font-semibold text-slate-700">{employee.job_title}</p>
                        )}
                        <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                          {employee.specialty && (
                            <span className="rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
                              {employee.specialty}
                            </span>
                          )}
                          <span
                            className={`rounded-full px-2 py-0.5 font-bold ${
                              employee.status === "active"
                                ? "bg-emerald-100 text-emerald-700"
                                : employee.status === "on_leave"
                                ? "bg-amber-100 text-amber-700"
                                : "bg-slate-200 text-slate-600"
                            }`}
                          >
                            {EMPLOYEE_STATUS_LABEL[employee.status]}
                          </span>
                          {employee.phone && (
                            <span className="flex items-center gap-1">
                              <Phone className="h-3 w-3" /> {employee.phone}
                            </span>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="mt-2 space-y-2">
                        <label className="block">
                          <span className="mb-1 block text-[11px] font-bold text-slate-600">المسمّى الوظيفي</span>
                          <input
                            type="text"
                            value={jobTitle}
                            onChange={(event) => setJobTitle(event.target.value)}
                            className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                          />
                        </label>
                        <label className="block">
                          <span className="mb-1 block text-[11px] font-bold text-slate-600">الهاتف</span>
                          <input
                            type="text"
                            value={phone}
                            onChange={(event) => setPhone(event.target.value)}
                            className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                          />
                        </label>
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setEditing(false);
                              setJobTitle(employee.job_title);
                              setPhone(employee.phone);
                            }}
                            className="rounded-lg bg-slate-100 px-3 py-1 text-[11px] font-bold text-slate-600 hover:bg-slate-200"
                          >
                            إلغاء
                          </button>
                          <button
                            type="button"
                            disabled={saving}
                            onClick={() => void saveProfileCard()}
                            className="rounded-lg bg-blue-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-blue-700 disabled:opacity-50"
                          >
                            حفظ
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* التبويبات */}
              <div className="flex border-b border-slate-100 px-5">
                {TABS.map(({ key, label }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTab(key)}
                    className={`-mb-px border-b-2 px-3 py-2.5 text-xs font-bold transition ${
                      tab === key
                        ? "border-blue-600 text-blue-700"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="p-5">
                {tab === "general" && (
                  <section className="space-y-3">
                    {targetsLoading ? (
                      <div className="py-8 text-center text-xs text-slate-400">جاري التحميل...</div>
                    ) : targetsError ? (
                      <p className="text-xs text-rose-700">{targetsError}</p>
                    ) : targets ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="rounded-xl border border-slate-200 p-3">
                            <p className="text-[11px] text-slate-500">طاقة الإسناد</p>
                            <p className="text-lg font-bold text-slate-900">{formatNumber(targets.capacity_target)}</p>
                          </div>
                          <div className="rounded-xl border border-slate-200 p-3">
                            <p className="text-[11px] text-slate-500">مقام الإنجاز الشهري (وحدات)</p>
                            <p className="text-lg font-bold text-slate-900">{formatNumber(targets.monthly_units_target)}</p>
                          </div>
                        </div>
                        {targets.monthly_units_suggestion?.targets && (
                          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                            <p className="mb-1.5 text-[11px] font-bold text-slate-600">مقاديرُ مقترحة لمقام الإنجاز</p>
                            <div className="flex gap-3 text-xs text-slate-700">
                              <span>الأدنى: {formatNumber(targets.monthly_units_suggestion.targets.low)}</span>
                              <span>المتوسط: {formatNumber(targets.monthly_units_suggestion.targets.medium)}</span>
                              <span>الأعلى: {formatNumber(targets.monthly_units_suggestion.targets.high)}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : null}
                  </section>
                )}

                {tab === "performance" && (
                  <section className="space-y-4">
                    {performanceLoading ? (
                      <div className="py-8 text-center text-xs text-slate-400">جاري التحميل...</div>
                    ) : performanceError ? (
                      <p className="text-xs text-rose-700">{performanceError}</p>
                    ) : (
                      <>
                        {performance && (
                          <div className="space-y-2">
                            <h4 className="text-xs font-bold text-slate-800">المحاور الخمسة الرسميّة</h4>
                            <p className="text-[11px] text-slate-500">
                              {performance.status_message} · حجم العينة: {formatNumber(performance.sample_size)} (الحد الأدنى{" "}
                              {formatNumber(performance.min_sample_size)})
                            </p>
                            {performance.composite_score !== null && (
                              <p className="text-sm font-bold text-slate-900">
                                النتيجة المركّبة: {formatNumber(performance.composite_score)}%
                              </p>
                            )}
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="border-b border-slate-200 text-slate-500">
                                    <th className="py-1.5 pr-2 text-right">المحور</th>
                                    <th className="py-1.5 px-2 text-right">منطبق</th>
                                    <th className="py-1.5 px-2 text-right">الوزن</th>
                                    <th className="py-1.5 px-2 text-right">النتيجة</th>
                                    <th className="py-1.5 px-2 text-right">المساهمة</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {PERFORMANCE_AXES.map((axis) => {
                                    const detail = performance.axes[axis];
                                    if (!detail) return null;
                                    return (
                                      <tr key={axis} className="border-b border-slate-100">
                                        <td className="py-1.5 pr-2 font-medium">{PERFORMANCE_AXIS_LABELS[axis]}</td>
                                        <td className="py-1.5 px-2">{detail.applicable ? "نعم" : "لا"}</td>
                                        <td className="py-1.5 px-2">{formatNumber(detail.weight_pct)}%</td>
                                        <td className="py-1.5 px-2">{formatNumber(detail.score_pct)}%</td>
                                        <td className="py-1.5 px-2">{formatNumber(detail.weighted_contribution)}</td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {pilotPerformance && (
                          <div className="space-y-2 border-t border-slate-100 pt-4">
                            <h4 className="text-xs font-bold text-slate-800">محاور الـpilot الأربعة</h4>
                            <p className="text-[11px] text-slate-500">
                              {pilotPerformance.status_message} · حجم العينة: {formatNumber(pilotPerformance.sample_size)} (الحد
                              الأدنى {formatNumber(pilotPerformance.min_sample_size)})
                            </p>
                            {pilotPerformance.composite_score !== null && (
                              <p className="text-sm font-bold text-slate-900">
                                النتيجة المركّبة: {formatNumber(pilotPerformance.composite_score)}%
                              </p>
                            )}
                            <PilotAxesTable performance={pilotPerformance} />
                          </div>
                        )}
                      </>
                    )}
                  </section>
                )}

                {tab === "wallet" && (
                  <section className="space-y-3">
                    <div className="flex flex-wrap items-end gap-2">
                      <label className="space-y-1 text-[11px]">
                        <span className="block text-slate-500">السنة</span>
                        <input
                          type="number"
                          value={walletYear}
                          onChange={(event) => setWalletYear(Number(event.target.value))}
                          className="w-20 rounded-lg border border-slate-200 px-2 py-1 text-xs"
                        />
                      </label>
                      <label className="space-y-1 text-[11px]">
                        <span className="block text-slate-500">الشهر</span>
                        <input
                          type="number"
                          min={1}
                          max={12}
                          value={walletMonth}
                          onChange={(event) => setWalletMonth(Number(event.target.value))}
                          className="w-16 rounded-lg border border-slate-200 px-2 py-1 text-xs"
                        />
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setWallet(null);
                          loadWallet();
                        }}
                        className="rounded-lg bg-slate-100 px-3 py-1.5 text-[11px] font-bold text-slate-700 hover:bg-slate-200"
                      >
                        عرض
                      </button>
                    </div>

                    {walletLoading ? (
                      <div className="py-8 text-center text-xs text-slate-400">جاري التحميل...</div>
                    ) : walletError ? (
                      <p className="text-xs text-rose-700">{walletError}</p>
                    ) : wallet ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="rounded-xl border border-slate-200 p-3">
                            <p className="text-[11px] text-slate-500">مؤكَّد</p>
                            <p className="text-lg font-bold text-emerald-700">{formatNumber(wallet.totals.confirmed)}</p>
                          </div>
                          <div className="rounded-xl border border-slate-200 p-3">
                            <p className="text-[11px] text-slate-500">معلَّق</p>
                            <p className="text-lg font-bold text-amber-700">{formatNumber(wallet.totals.pending)}</p>
                          </div>
                        </div>
                        {(() => {
                          const lines: WalletLine[] = [...wallet.salary_lines, ...wallet.commission_lines];
                          return lines.length === 0 ? (
                            <p className="text-xs text-slate-500">لا سطور لهذا الشهر.</p>
                          ) : (
                            <div className="overflow-x-auto">
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="border-b border-slate-200 text-slate-500">
                                    <th className="py-1.5 pr-2 text-right">النوع</th>
                                    <th className="py-1.5 px-2 text-right">المبلغ</th>
                                    <th className="py-1.5 px-2 text-right">الحالة</th>
                                    <th className="py-1.5 px-2 text-right">آخر تحديث</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {lines.map((line) => (
                                    <tr
                                      key={`${isCommissionLine(line) ? "commission" : "salary"}:${line.id}`}
                                      className="border-b border-slate-100"
                                    >
                                      <td className="py-1.5 pr-2">{isCommissionLine(line) ? "عمولة اكتساب" : "راتب"}</td>
                                      <td className="py-1.5 px-2 font-semibold">{formatNumber(line.amount)}</td>
                                      <td className="py-1.5 px-2">
                                        <span
                                          className={`rounded-full px-2 py-0.5 ${WALLET_STATUS_CLASS[line.status]}`}
                                        >
                                          {line.status_display || WALLET_LINE_STATUS_LABEL[line.status]}
                                        </span>
                                      </td>
                                      <td className="py-1.5 px-2">{formatDateTimeValue(line.updated_at) || "—"}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          );
                        })()}
                      </div>
                    ) : null}
                  </section>
                )}

                {tab === "activity" && (
                  <section>
                    {activityLoading ? (
                      <div className="py-8 text-center text-xs text-slate-400">جاري التحميل...</div>
                    ) : activityError ? (
                      <p className="text-xs text-rose-700">{activityError}</p>
                    ) : activity && activity.length > 0 ? (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-slate-200 text-slate-500">
                              <th className="py-1.5 pr-2 text-right">التوقيت</th>
                              <th className="py-1.5 px-2 text-right">الحدث</th>
                              <th className="py-1.5 px-2 text-right">الوصف</th>
                              <th className="py-1.5 px-2 text-right">الشركة</th>
                            </tr>
                          </thead>
                          <tbody>
                            {activity.map((log) => (
                              <tr key={log.id} className="border-b border-slate-100">
                                <td className="whitespace-nowrap py-1.5 pr-2 text-slate-500">
                                  {formatDateTimeValue(log.created_at)}
                                </td>
                                <td className="py-1.5 px-2 font-mono text-slate-500">{log.action_display || log.action}</td>
                                <td className="py-1.5 px-2 text-slate-700">{log.description}</td>
                                <td className="py-1.5 px-2 text-slate-400">{log.company_name || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="py-8 text-center text-xs text-slate-400">لا يوجد نشاطٌ مسجَّل حتى الآن.</p>
                    )}
                  </section>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default EmployeeProfileDrawer;
