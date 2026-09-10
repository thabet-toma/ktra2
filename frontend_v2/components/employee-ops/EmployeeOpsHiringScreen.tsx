import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Briefcase,
  Copy,
  ExternalLink,
  FileText,
  Link2,
  Loader2,
  Lock,
  MessageCircle,
  Plus,
  RefreshCw,
  Search,
  Star,
  UserPlus,
  Trash2,
  Unlock,
  X,
} from "lucide-react";

import {
  closeJob,
  createEmployee,
  createJob,
  deleteJob,
  getApplicantCv,
  listApplicants,
  listJobs,
  markApplicantHired,
  publicJobUrl,
  regenerateJobToken,
  reopenJob,
  updateApplicant,
  type ApplicantStatus,
  type JobApplicantDto,
  type JobPostingDto,
} from "../../services/employeeOpsApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";

/** أربعُ حالاتٍ تصف **المتقدّم** لا عملَ المالك. */
const STATUS_LABELS: Record<ApplicantStatus, string> = {
  new: "جديد",
  interview: "للمقابلة",
  hired: "موظَّف",
  rejected: "مرفوض",
};

const STATUS_BADGE: Record<ApplicantStatus, string> = {
  new: "bg-blue-100 text-blue-800 dark:bg-blue-950/40 dark:text-blue-300",
  interview: "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
  hired: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
  rejected: "bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300",
};

/** «موظَّف» لا تُضبط باليد — تُبلَغ بإنشاء سجلّ الموظف من المتقدّم. */
const MANUAL_STATUSES: ApplicantStatus[] = ["new", "interview", "rejected"];

const EMPLOYMENT_TYPES = [
  { value: "", label: "غير محدد" },
  { value: "full_time", label: "دوام كامل" },
  { value: "part_time", label: "دوام جزئي" },
  { value: "contract", label: "عقد" },
  { value: "temporary", label: "مؤقت" },
];

/** رقمٌ فلسطينيٌّ محلّيّ إلى صيغة `wa.me` — رابطٌ فقط، لا تكامل API. */
function whatsappHref(phone: string): string {
  const digits = (phone || "").replace(/\D/g, "");
  if (!digits) return "";
  const international = digits.startsWith("0") ? `970${digits.slice(1)}` : digits;
  return `https://wa.me/${international}`;
}

export const EmployeeOpsHiringScreen: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();

  const [activeTab, setActiveTab] = useState<"jobs" | "applicants">("jobs");

  const [jobs, setJobs] = useState<JobPostingDto[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);

  const [applicants, setApplicants] = useState<JobApplicantDto[]>([]);
  const [loadingApplicants, setLoadingApplicants] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"" | ApplicantStatus>("");
  const [jobFilter, setJobFilter] = useState<string>("");
  const [search, setSearch] = useState("");
  /** المكتوبُ في الحقل يُهدَّأ قبل أن يصير طلباً — لا طلبٌ لكلّ ضغطةِ مفتاح. */
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const applicantsRequestRef = useRef(0);

  const [isJobModalOpen, setIsJobModalOpen] = useState(false);
  const [savingJob, setSavingJob] = useState(false);
  const [draft, setDraft] = useState({
    title: "",
    description: "",
    requirements: "",
    location: "",
    employment_type: "",
    salary_range: "",
    expires_at: "",
  });

  const [openApplicant, setOpenApplicant] = useState<JobApplicantDto | null>(null);
  const [openingCvId, setOpeningCvId] = useState<number | null>(null);

  // «من متقدّمٍ إلى موظف» — **إنشاءٌ يدويٌّ مملوءٌ مسبقاً لا تحويلٌ آليّ**:
  // الإنشاء يستهلك مقعداً ويطلق دعوة، وكلاهما أثقلُ من أن يقع بضغطةٍ بلا مراجعة.
  const [hireDraft, setHireDraft] = useState<{
    name: string;
    phone: string;
    job_title: string;
  } | null>(null);
  const [hiring, setHiring] = useState(false);
  const [inviteLink, setInviteLink] = useState("");

  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      setJobs(await listJobs());
    } catch (err: any) {
      toast(err?.message || "فشل تحميل الوظائف", "error");
    } finally {
      setLoadingJobs(false);
    }
  }, [toast]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const loadApplicants = useCallback(async () => {
    // حارسُ سباق: «محمد» أربعُ ضغطاتٍ = أربعةُ طلبات، وسبقُ الأبطأِ يترك
    // الشاشةَ تعرض نتيجةَ بحثٍ أقدم.
    const token = ++applicantsRequestRef.current;
    setLoadingApplicants(true);
    try {
      const rows = await listApplicants({
        status: statusFilter || undefined,
        job: jobFilter ? Number(jobFilter) : undefined,
        search: debouncedSearch.trim() || undefined,
      });
      if (token !== applicantsRequestRef.current) return;
      setApplicants(rows);
    } catch (err: any) {
      if (token === applicantsRequestRef.current) {
        toast(err?.message || "فشل تحميل المتقدمين", "error");
      }
    } finally {
      if (token === applicantsRequestRef.current) setLoadingApplicants(false);
    }
  }, [statusFilter, jobFilter, debouncedSearch, toast]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (activeTab === "applicants") void loadApplicants();
  }, [activeTab, loadApplicants]);

  const openJobsCount = useMemo(() => jobs.filter((j) => j.is_live).length, [jobs]);

  const handleCopyLink = async (job: JobPostingDto) => {
    const url = publicJobUrl(job.token);
    try {
      await navigator.clipboard.writeText(url);
      toast("تم نسخ رابط الوظيفة", "success");
    } catch {
      // الحافظةُ محجوبةٌ بلا HTTPS — الرابطُ يبقى مقروءاً في الحقل بجانبه.
      toast("تعذّر النسخ تلقائياً — انسخ الرابط يدوياً", "error");
    }
  };

  /**
   * دمجُ ردٍّ غيرِ مُعلَّمٍ في الحالة.
   * `applicant_count` يُحسب في `list` وحدها؛ وبقيّةُ النقاط تُعيد صفّاً بلا
   * تعليم، فكان الردُّ يصفّر العدّاد: بطاقةٌ تقول «١٢ متقدم» تصير «٠» لحظةَ
   * إغلاق الوظيفة. نحتفظ بالعدّاد المعروف حتى يعود من قائمةٍ حقيقيّة.
   */
  const mergeJob = (updated: JobPostingDto) =>
    setJobs((prev) =>
      prev.map((j) =>
        j.id === updated.id
          ? { ...updated, applicant_count: j.applicant_count }
          : j,
      ),
    );

  const handleRegenerate = async (job: JobPostingDto) => {
    const ok = await confirm({
      title: "إعادة توليد رابط الوظيفة",
      message:
        "سيتوقف الرابط الحالي عن العمل فوراً لكل من يملكه. هل تريد المتابعة؟",
      confirmText: "إعادة التوليد",
      danger: true,
    });
    if (!ok) return;
    try {
      mergeJob(await regenerateJobToken(job.id));
      toast("تم توليد رابط جديد", "success");
    } catch (err: any) {
      toast(err?.message || "فشل توليد الرابط", "error");
    }
  };

  const handleToggleOpen = async (job: JobPostingDto) => {
    try {
      mergeJob(job.is_open ? await closeJob(job.id) : await reopenJob(job.id));
      toast(job.is_open ? "أُغلقت الوظيفة" : "أُعيد فتح الوظيفة", "success");
    } catch (err: any) {
      toast(err?.message || "فشل تعديل حالة الوظيفة", "error");
    }
  };

  const handleDelete = async (job: JobPostingDto) => {
    const ok = await confirm({
      title: "حذف الوظيفة",
      message: `حذف «${job.title}»؟ الوظيفة التي تقدّم عليها أحد لا تُحذف — أغلقها بدل ذلك.`,
      confirmText: "حذف",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteJob(job.id);
      setJobs((prev) => prev.filter((j) => j.id !== job.id));
      toast("تم حذف الوظيفة", "success");
    } catch (err: any) {
      toast(err?.message || "فشل حذف الوظيفة", "error");
    }
  };

  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft.title.trim() || !draft.description.trim()) {
      toast("العنوان والوصف مطلوبان", "error");
      return;
    }
    setSavingJob(true);
    try {
      const created = await createJob({
        ...draft,
        // فارغٌ = بلا انتهاء، وهو الوضعُ الطبيعيُّ لإعلانٍ يُنشر مرّةً ويُنسى.
        expires_at: draft.expires_at ? new Date(draft.expires_at).toISOString() : null,
      });
      setJobs((prev) => [created, ...prev]);
      setIsJobModalOpen(false);
      setDraft({
        title: "", description: "", requirements: "",
        location: "", employment_type: "", salary_range: "", expires_at: "",
      });
      // «إنشاء ونسخ الرابط» كان يَعِد بنسخٍ لا يقع — والوعدُ يُنفَّذ أو يُحذف.
      await handleCopyLink(created);
    } catch (err: any) {
      toast(err?.message || "فشل إنشاء الوظيفة", "error");
    } finally {
      setSavingJob(false);
    }
  };

  const handleHire = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!openApplicant || !hireDraft) return;
    if (!hireDraft.name.trim()) {
      toast("اسم الموظف مطلوب", "error");
      return;
    }
    setHiring(true);
    try {
      // خطوتان بترتيبٍ مقصود: يُنشأ الموظفُ أوّلاً (وهو ما يستهلك المقعدَ وقد
      // يُردّ بحدّ الخطة)، ثمّ يُربط المتقدّمُ به. العكسُ كان يترك متقدّماً
      // موسوماً «موظَّف» بلا سجلٍّ حين ينفد المقعد.
      const created = await createEmployee({
        name: hireDraft.name.trim(),
        phone: hireDraft.phone.trim(),
        job_title: hireDraft.job_title.trim(),
      });
      const updated = await markApplicantHired(openApplicant.id, created.employee.id);
      setApplicants((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      setOpenApplicant(updated);
      setHireDraft(null);
      setInviteLink(created.invitation_url || "");
      toast("تم إنشاء الموظف وربطه بالمتقدم", "success");
    } catch (err: any) {
      toast(err?.message || "فشل تحويل المتقدم إلى موظف", "error");
    } finally {
      setHiring(false);
    }
  };

  const patchApplicant = async (
    applicant: JobApplicantDto,
    data: { status?: ApplicantStatus; rating?: number; notes?: string },
  ) => {
    try {
      const updated = await updateApplicant(applicant.id, data);
      setApplicants((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      setOpenApplicant((prev) => (prev && prev.id === updated.id ? updated : prev));
    } catch (err: any) {
      toast(err?.message || "فشل تحديث المتقدم", "error");
    }
  };

  const handleOpenCv = async (applicant: JobApplicantDto) => {
    // افتح التبويب داخل حدث النقرة نفسه كي لا يحجبه مانع النوافذ المنبثقة أثناء
    // انتظار طلب الشبكة. ثم انزع علاقة opener قبل تحميل أي محتوى فيه.
    const popup = window.open("about:blank", "_blank");
    if (!popup) {
      toast("تعذّر فتح تبويب السيرة — اسمح بالنوافذ المنبثقة ثم حاول مجدداً", "error");
      return;
    }
    setOpeningCvId(applicant.id);
    try {
      const cv = await getApplicantCv(applicant.id);
      const objectUrl = URL.createObjectURL(cv);
      popup.document.title = applicant.cv_name || "السيرة الذاتية";
      const viewer = popup.document.createElement("iframe");
      viewer.src = objectUrl;
      viewer.title = applicant.cv_name || "السيرة الذاتية";
      viewer.width = "100%";
      viewer.height = String(Math.max(popup.innerHeight - 24, 480));
      viewer.setAttribute("frameborder", "0");
      popup.document.body.replaceChildren(viewer);
      popup.opener = null;
      // الرابط محليّ لذا يُحرَّر بعد أن يحصل التبويب على وقتٍ كافٍ لقراءة البايتات.
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (err: any) {
      popup.close();
      toast(err?.message || "تعذّر فتح السيرة الذاتية", "error");
    } finally {
      setOpeningCvId(null);
    }
  };

  return (
    <div className="space-y-4 p-4 md:p-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] pb-4">
        <div>
          <h1 className="text-lg font-bold text-[var(--color-text)]">التوظيف</h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
            وظيفةٌ برابطٍ عامّ يُنشر، وقائمةُ من تقدّم عليها
          </p>
        </div>
        <button
          type="button"
          onClick={() => setIsJobModalOpen(true)}
          className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-bold text-white hover:opacity-90 shadow-sm"
        >
          <Plus className="h-4 w-4" /> وظيفة جديدة
        </button>
      </div>

      <div className="flex items-center gap-1 border-b border-[var(--color-border)]">
        <button
          type="button"
          onClick={() => setActiveTab("jobs")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold border-b-2 transition-all ${
            activeTab === "jobs"
              ? "border-[var(--color-primary)] text-[var(--color-primary)]"
              : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          }`}
        >
          <Briefcase className="h-4 w-4" /> الوظائف ({formatNumber(openJobsCount)} مفتوحة)
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("applicants")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold border-b-2 transition-all ${
            activeTab === "applicants"
              ? "border-[var(--color-primary)] text-[var(--color-primary)]"
              : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          }`}
        >
          <FileText className="h-4 w-4" /> المتقدمون
        </button>
      </div>

      {activeTab === "jobs" && (
        <div className="space-y-3">
          {loadingJobs ? (
            <div className="flex justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--color-primary)]" />
            </div>
          ) : jobs.length === 0 ? (
            <p className="text-center py-10 text-xs text-[var(--color-text-muted)]">
              لا توجد وظائف بعد. أنشئ وظيفة وانشر رابطها.
            </p>
          ) : (
            jobs.map((job) => (
              <div
                key={job.id}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-bold text-[var(--color-text)]">
                        {job.title}
                      </h2>
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                          job.is_live
                            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                            : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                        }`}
                      >
                        {job.is_live ? "مفتوحة" : "مغلقة"}
                      </span>
                    </div>
                    <p className="text-[11px] text-[var(--color-text-muted)] mt-1">
                      {formatNumber(job.applicant_count)} متقدم •{" "}
                      {formatDateTimeValue(job.created_at)}
                    </p>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => handleToggleOpen(job)}
                      title={job.is_open ? "إغلاق الوظيفة" : "إعادة فتحها"}
                      className="rounded-md border border-[var(--color-border)] px-2 py-1 text-[11px] font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                    >
                      {job.is_open ? (
                        <Lock className="h-3.5 w-3.5" />
                      ) : (
                        <Unlock className="h-3.5 w-3.5" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRegenerate(job)}
                      title="إبطال الرابط وتوليد بديل"
                      className="rounded-md border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(job)}
                      title="حذف الوظيفة"
                      className="rounded-md px-2 py-1 text-red-500 hover:text-red-700"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2 rounded-lg bg-[var(--color-surface-2)] p-2">
                  <Link2 className="h-3.5 w-3.5 text-[var(--color-text-muted)] flex-shrink-0" />
                  <input
                    type="text"
                    readOnly
                    value={publicJobUrl(job.token)}
                    onFocus={(e) => e.currentTarget.select()}
                    className="flex-1 min-w-0 bg-transparent text-[11px] text-[var(--color-text-muted)] outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => handleCopyLink(job)}
                    className="flex items-center gap-1 rounded border border-[var(--color-border)] px-2 py-1 text-[11px] font-semibold text-[var(--color-primary)] hover:bg-[var(--color-surface-3)] flex-shrink-0"
                  >
                    <Copy className="h-3 w-3" /> نسخ
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === "applicants" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute right-3 top-2.5 h-4 w-4 text-[var(--color-text-muted)]" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="بحث بالاسم أو الرقم..."
                className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] pr-9 pl-3 text-xs text-[var(--color-text)] outline-none"
              />
            </div>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as "" | ApplicantStatus)}
              className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)] outline-none"
            >
              <option value="">كل الحالات</option>
              {(Object.keys(STATUS_LABELS) as ApplicantStatus[]).map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABELS[value]}
                </option>
              ))}
            </select>

            <select
              value={jobFilter}
              onChange={(e) => setJobFilter(e.target.value)}
              className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)] outline-none"
            >
              <option value="">كل الوظائف</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title}
                </option>
              ))}
            </select>
          </div>

          {loadingApplicants ? (
            <div className="flex justify-center py-10">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--color-primary)]" />
            </div>
          ) : applicants.length === 0 ? (
            <p className="text-center py-10 text-xs text-[var(--color-text-muted)]">
              لا يوجد متقدمون مطابقون.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <table className="w-full text-right text-xs">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-[var(--color-text-muted)]">
                    <th className="py-2.5 px-3 font-semibold">المتقدم</th>
                    <th className="py-2.5 px-3 font-semibold">الوظيفة</th>
                    <th className="py-2.5 px-3 font-semibold">التواصل</th>
                    <th className="py-2.5 px-3 font-semibold text-center">الحالة</th>
                    <th className="py-2.5 px-3 font-semibold text-center">التقييم</th>
                    <th className="py-2.5 px-3 font-semibold text-center">تاريخ التقديم</th>
                    <th className="py-2.5 px-3 font-semibold text-center">الإجراء</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {applicants.map((applicant) => (
                    <tr key={applicant.id} className="hover:bg-[var(--color-surface-2)]">
                      <td className="py-2.5 px-3">
                        <span className="font-bold text-[var(--color-text)]">
                          {applicant.name}
                        </span>
                        <span className="block text-[10px] text-[var(--color-text-muted)]">
                          {applicant.reference_code}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-[var(--color-text-muted)]">
                        {applicant.job_title}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className="text-[var(--color-text)]">{applicant.phone}</span>
                        {whatsappHref(applicant.phone) && (
                          <a
                            href={whatsappHref(applicant.phone)}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="مراسلة عبر واتساب"
                            className="inline-flex items-center mr-1.5 text-emerald-600 hover:text-emerald-700"
                          >
                            <MessageCircle className="h-3.5 w-3.5" />
                          </a>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <span
                          className={`inline-block rounded px-2 py-0.5 text-[10px] font-bold ${STATUS_BADGE[applicant.status]}`}
                        >
                          {STATUS_LABELS[applicant.status]}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-center text-amber-500">
                        {applicant.rating > 0
                          ? "★".repeat(applicant.rating)
                          : "—"}
                      </td>
                      <td className="py-2.5 px-3 text-center text-[var(--color-text-muted)]">
                        {formatDateTimeValue(applicant.created_at)}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <button
                          type="button"
                          onClick={() => setOpenApplicant(applicant)}
                          className="rounded-md border border-[var(--color-border)] px-2 py-1 text-[11px] font-semibold text-[var(--color-primary)] hover:bg-[var(--color-surface-3)]"
                        >
                          فتح
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* نافذة الوظيفة الجديدة */}
      {isJobModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <form
            onSubmit={handleCreateJob}
            className="relative w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] overflow-y-auto space-y-3"
          >
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
              <h2 className="text-base font-bold text-[var(--color-text)]">وظيفة جديدة</h2>
              <button
                type="button"
                onClick={() => setIsJobModalOpen(false)}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                عنوان الوظيفة <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                الوصف <span className="text-red-500">*</span>
              </label>
              <textarea
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                rows={4}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                المتطلبات
              </label>
              <textarea
                value={draft.requirements}
                onChange={(e) => setDraft({ ...draft, requirements: e.target.value })}
                rows={3}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                  المكان
                </label>
                <input
                  type="text"
                  value={draft.location}
                  onChange={(e) => setDraft({ ...draft, location: e.target.value })}
                  className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                  نوع الدوام
                </label>
                <select
                  value={draft.employment_type}
                  onChange={(e) => setDraft({ ...draft, employment_type: e.target.value })}
                  className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 text-xs text-[var(--color-text)] outline-none"
                >
                  {EMPLOYMENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                  نطاق الراتب
                </label>
                <input
                  type="text"
                  value={draft.salary_range}
                  onChange={(e) => setDraft({ ...draft, salary_range: e.target.value })}
                  className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                تاريخ انتهاء الرابط (اختياري)
              </label>
              <input
                type="date"
                value={draft.expires_at}
                onChange={(e) => setDraft({ ...draft, expires_at: e.target.value })}
                className="h-9 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 text-xs text-[var(--color-text)] outline-none"
              />
              <p className="mt-1 text-[10px] text-[var(--color-text-muted)]">
                اتركه فارغاً ليبقى الرابط صالحاً حتى تُغلق الوظيفة يدوياً.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-[var(--color-border)] pt-4">
              <button
                type="button"
                onClick={() => setIsJobModalOpen(false)}
                className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-semibold text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
              >
                إلغاء
              </button>
              <button
                type="submit"
                disabled={savingJob}
                className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-60"
              >
                {savingJob && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                إنشاء ونسخ الرابط
              </button>
            </div>
          </form>
        </div>
      )}

      {/* نافذة المتقدم */}
      {openApplicant && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
          <div className="relative w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
              <div>
                <h2 className="text-base font-bold text-[var(--color-text)]">
                  {openApplicant.name}
                </h2>
                <p className="text-[11px] text-[var(--color-text-muted)]">
                  {openApplicant.job_title} • {openApplicant.reference_code}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setOpenApplicant(null);
                  setHireDraft(null);
                  setInviteLink("");
                }}
                className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div>
                <span className="block text-[var(--color-text-muted)] mb-0.5">الهاتف</span>
                <span className="font-semibold text-[var(--color-text)]">
                  {openApplicant.phone}
                </span>
              </div>
              <div>
                <span className="block text-[var(--color-text-muted)] mb-0.5">البريد</span>
                <span className="font-semibold text-[var(--color-text)]">
                  {openApplicant.email || "—"}
                </span>
              </div>
            </div>

            {openApplicant.about && (
              <div className="rounded-lg bg-[var(--color-surface-2)] p-3">
                <span className="block text-[11px] font-bold text-[var(--color-text-muted)] mb-1">
                  نبذة المتقدم
                </span>
                <p className="text-xs text-[var(--color-text)] whitespace-pre-wrap leading-relaxed">
                  {openApplicant.about}
                </p>
              </div>
            )}

            {/* السيرةُ تُجلب بطلبٍ مصادَق عليه، ثم تُفتح من Blob محلي. رابطُ
                التخزين الحقيقي لا يصل المتصفح بأيّ حال. */}
            {openApplicant.has_cv && (
              <button
                type="button"
                onClick={() => void handleOpenCv(openApplicant)}
                disabled={openingCvId === openApplicant.id}
                className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs font-semibold text-[var(--color-primary)] hover:bg-[var(--color-surface-2)] w-fit"
              >
                {openingCvId === openApplicant.id
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <ExternalLink className="h-3.5 w-3.5" />}
                فتح السيرة الذاتية {openApplicant.cv_name && `(${openApplicant.cv_name})`}
              </button>
            )}

            <div>
              <span className="block text-xs font-semibold text-[var(--color-text)] mb-1.5">
                الحالة
              </span>
              <div className="flex flex-wrap items-center gap-1.5">
                {MANUAL_STATUSES.map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => patchApplicant(openApplicant, { status: value })}
                    className={`rounded-lg px-3 py-1.5 text-[11px] font-bold border transition-all ${
                      openApplicant.status === value
                        ? "border-[var(--color-primary)] text-[var(--color-primary)] bg-[var(--color-primary)]/10"
                        : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                    }`}
                  >
                    {STATUS_LABELS[value]}
                  </button>
                ))}
              </div>
              {openApplicant.status === "hired" ? (
                <p className="mt-1.5 text-[11px] text-emerald-600 font-semibold">
                  موظَّف — مرتبط بسجل موظف في الشركة.
                </p>
              ) : hireDraft ? (
                <form
                  onSubmit={handleHire}
                  className="mt-2 space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3"
                >
                  <p className="text-[11px] text-[var(--color-text-muted)]">
                    مراجعةٌ قبل الحفظ: الإنشاء يستهلك مقعداً ويطلق دعوة.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <input
                      type="text"
                      value={hireDraft.name}
                      onChange={(e) => setHireDraft({ ...hireDraft, name: e.target.value })}
                      placeholder="الاسم"
                      className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-xs text-[var(--color-text)] outline-none"
                    />
                    <input
                      type="text"
                      value={hireDraft.phone}
                      onChange={(e) => setHireDraft({ ...hireDraft, phone: e.target.value })}
                      placeholder="الهاتف"
                      className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-xs text-[var(--color-text)] outline-none"
                    />
                    <input
                      type="text"
                      value={hireDraft.job_title}
                      onChange={(e) =>
                        setHireDraft({ ...hireDraft, job_title: e.target.value })
                      }
                      placeholder="المسمى الوظيفي"
                      className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-xs text-[var(--color-text)] outline-none"
                    />
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setHireDraft(null)}
                      className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-[11px] font-semibold text-[var(--color-text-muted)]"
                    >
                      إلغاء
                    </button>
                    <button
                      type="submit"
                      disabled={hiring}
                      className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-[11px] font-bold text-white hover:bg-emerald-700 disabled:opacity-60"
                    >
                      {hiring && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      حفظ الموظف
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    setHireDraft({
                      name: openApplicant.name,
                      phone: openApplicant.phone,
                      job_title: openApplicant.job_title,
                    })
                  }
                  className="mt-2 flex items-center gap-1.5 rounded-lg border border-emerald-300 px-3 py-1.5 text-[11px] font-bold text-emerald-700 hover:bg-emerald-50 dark:border-emerald-900 dark:text-emerald-400 dark:hover:bg-emerald-950/30"
                >
                  <UserPlus className="h-3.5 w-3.5" /> حوّله إلى موظف
                </button>
              )}

              {inviteLink && (
                <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 dark:border-amber-900/50 dark:bg-amber-950/20">
                  <p className="text-[11px] font-bold text-amber-900 dark:text-amber-200">
                    رابط الدعوة يظهر{" "}
                    <span className="underline decoration-2">لمرة واحدة فقط</span> — انسخه
                    وأرسله للموظف الآن.
                  </p>
                  <div className="mt-1.5 flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={inviteLink}
                      onFocus={(e) => e.currentTarget.select()}
                      className="flex-1 min-w-0 bg-transparent text-[11px] text-amber-900 dark:text-amber-200 outline-none"
                    />
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(inviteLink);
                          toast("تم نسخ رابط الدعوة", "success");
                        } catch {
                          toast("تعذّر النسخ — انسخ الرابط يدوياً", "error");
                        }
                      }}
                      className="rounded border border-amber-300 px-2 py-1 text-[11px] font-semibold text-amber-800 dark:border-amber-800 dark:text-amber-300"
                    >
                      نسخ
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div>
              <span className="block text-xs font-semibold text-[var(--color-text)] mb-1.5">
                التقييم
              </span>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() =>
                      patchApplicant(openApplicant, {
                        rating: openApplicant.rating === star ? 0 : star,
                      })
                    }
                    title={`${star} من ٥`}
                    className={
                      star <= openApplicant.rating
                        ? "text-amber-500"
                        : "text-[var(--color-text-muted)] hover:text-amber-400"
                    }
                  >
                    <Star
                      className="h-5 w-5"
                      fill={star <= openApplicant.rating ? "currentColor" : "none"}
                    />
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
                ملاحظات
              </label>
              <textarea
                value={openApplicant.notes}
                onChange={(e) =>
                  setOpenApplicant({ ...openApplicant, notes: e.target.value })
                }
                onBlur={() =>
                  patchApplicant(openApplicant, { notes: openApplicant.notes })
                }
                rows={3}
                placeholder="انطباعك بعد المقابلة..."
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
