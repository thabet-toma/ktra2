import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  LayoutGrid,
  List,
  RefreshCw,
  Search,
  Star,
  Users,
} from "lucide-react";

import {
  listPlatformApplicants,
  type PlatformJobApplicant,
  type PlatformJobPosting,
} from "../../services/platformHiringApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  APPLICANT_STATUS_OPTIONS,
  applicantStatusTone,
  filterPlatformApplicants,
} from "../../utils/platformHiring";
import {
  CcAvatar,
  CcCard,
  CcEmpty,
  CcPill,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "../platform/ui";
import { PlatformApplicantBroadcastDialog } from "./PlatformApplicantBroadcastDialog";
import { PlatformApplicantPanel } from "./PlatformApplicantPanel";

interface PlatformApplicantsTabProps {
  jobs: PlatformJobPosting[];
  initialJobFilter?: number | null;
  /** يُنادى بعد تطبيق فلتر الوظيفة، فيُفرِغه الأبُ ويصير الطلبُ الثاني مسموعاً. */
  onJobFilterHandled?: () => void;
  focusApplicantId?: number | null;
  /** يُنادى بعد تنفيذ طلب الفتح، فيُفرِغه الأبُ ويصير الضغطُ الثاني مسموعاً. */
  onFocusHandled?: () => void;
}

const STATUS_CHOICES = [
  { value: "", label: "كافة الحالات" },
  ...APPLICANT_STATUS_OPTIONS,
];

const PIPELINE_STAGES = [
  { key: "new", label: "تقديم", step: 1 },
  { key: "screening", label: "فرز أولي", step: 2 },
  { key: "interview", label: "مقابلة", step: 3 },
  { key: "offered", label: "عرض عمل", step: 4 },
  { key: "hired", label: "مقبول", step: 5 },
] as const;

const STAGE_ORDER: Record<string, number> = {
  new: 1,
  screening: 2,
  interview: 3,
  offered: 4,
  hired: 5,
};

export const PlatformApplicantsTab: React.FC<PlatformApplicantsTabProps> = ({
  jobs,
  initialJobFilter,
  onJobFilterHandled,
  focusApplicantId,
  onFocusHandled,
}: PlatformApplicantsTabProps) => {
  const [jobFilter, setJobFilter] = useState<string>(
    initialJobFilter ? String(initialJobFilter) : "",
  );
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");

  const [applicants, setApplicants] = useState<PlatformJobApplicant[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedApplicant, setSelectedApplicant] = useState<PlatformJobApplicant | null>(null);
  const [showBroadcastDialog, setShowBroadcastDialog] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [focusError, setFocusError] = useState<string | null>(null);
  /** الفلاتر التي **نتجت عنها** القائمةُ المحمَّلةُ الآن — لا التي في الحقول. */
  const [loadedFilters, setLoadedFilters] = useState({ job: "", status: "" });

  // **الطلبُ قائمٌ ما دام المعرّفُ قائماً**: الأبُ يُفرِغه فورَ تنفيذه
  // (`onFocusHandled`)، فلا يلزم تذكُّرُ ما نُفِّذ — وتذكُّرُه كان يمنع فتحَ
  // الشخص نفسِه مرّةً ثانيةً إلى الأبد.
  const isFocusPending = focusApplicantId != null;

  // **ويُستهلَك كما يُستهلَك طلبُ الفتح**: المعرَّفُ كان يبقى مخزَّناً عند الأب
  // إلى الأبد، والتبويبُ يُفصَل عند كلّ تبديل ثمّ يقرؤه من جديد — فمجرّدُ
  // العودة إلى «المتقدّمون» بزرّ التبويب كانت **تُعيد فرضَ فلتر وظيفةٍ قديم**
  // على من مسحه بيده. صار طلباً يُنفَّذ مرّةً ثمّ يُفرَغ.
  useEffect(() => {
    if (initialJobFilter == null) return;
    setJobFilter(String(initialJobFilter));
    onJobFilterHandled?.();
  }, [initialJobFilter, onJobFilterHandled]);

  useEffect(() => {
    if (focusApplicantId == null) return;
    setJobFilter("");
    setStatusFilter("");
    setSearchQuery("");
    setSelectedApplicant(null);
    setFocusError(null);
  }, [focusApplicantId]);

  // ‏`isFocusPending` **ليس** من تبعيّات الجلب: الأثرُ الذي قبله يُفرِغ الفلاتر،
  // وإفراغُها وحدَه يُعيد التحميلَ غيرَ مصفّى. إدخالُه كان يجلب القائمةَ ثلاثَ
  // مرّاتٍ للفتحة الواحدة — عند رفع الطلب، وعند إفراغ الفلاتر، وعند إنزاله.
  const loadApplicants = useCallback(async () => {
    setLoading(true);
    setHasLoaded(false);
    setLoadError(null);
    try {
      const data = await listPlatformApplicants({
        job: jobFilter ? parseInt(jobFilter, 10) : undefined,
        status: statusFilter || undefined,
      });
      setApplicants(data);
      setLoadedFilters({ job: jobFilter, status: statusFilter });
    } catch (err: any) {
      setApplicants([]);
      setLoadError(err?.message || "تعذر تحميل المتقدمين.");
    } finally {
      setLoading(false);
      setHasLoaded(true);
    }
  }, [jobFilter, statusFilter]);

  useEffect(() => {
    void loadApplicants();
  }, [loadApplicants]);

  // تصفية محلية بالبحث
  const filteredApplicants = useMemo(() => {
    return filterPlatformApplicants(applicants, searchQuery);
  }, [applicants, searchQuery]);

  const selectedBroadcastJob = useMemo(
    () => jobs.find((job) => job.id === parseInt(jobFilter, 10)) ?? null,
    [jobFilter, jobs],
  );

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = {
      new: 0,
      screening: 0,
      interview: 0,
      offered: 0,
      hired: 0,
      rejected: 0,
    };
    for (const applicant of applicants) {
      if (counts[applicant.status] !== undefined) {
        counts[applicant.status] += 1;
      }
    }
    return counts;
  }, [applicants]);

  const hiredCount = stageCounts.hired || 0;
  const offeredCount = stageCounts.offered || 0;
  const inProgressCount =
    (stageCounts.new || 0) + (stageCounts.screening || 0) + (stageCounts.interview || 0);

  useEffect(() => {
    if (!isFocusPending || loading || !hasLoaded || loadError || focusApplicantId == null) return;
    // **وقائمةُ البحث هي القائمةُ غيرُ المصفّاة** لا سابقتُها: الأثرُ الذي يُفرِغ
    // الفلاتر يُجدوِل حالةً لا تصل هذا الأثرَ في نفس اللقطة، فكان المطلوبُ
    // يُبحَث عنه في نتيجةِ فلترٍ قديمٍ ويُعلَن مفقوداً — ثمّ يُلغى الطلب.
    if (loadedFilters.job || loadedFilters.status) return;

    const applicant = applicants.find((item) => item.id === focusApplicantId);
    if (applicant) {
      setSelectedApplicant(applicant);
      setFocusError(null);
    } else {
      setFocusError("تعذّر العثور على المتقدّم المطلوب ضمن القائمة المحمّلة.");
    }
    onFocusHandled?.();
  }, [applicants, focusApplicantId, hasLoaded, isFocusPending, loadError, loadedFilters, loading, onFocusHandled]);

  return (
    <div className="space-y-6 text-right" dir="rtl">
      {/* 1. لوحة مراحل التوظيف كاللوحة 5 (Command Center Stepper Board) */}
      <CcCard className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 mb-4 border-b border-cc-border">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/20 border border-sky-500/40 text-sky-400 font-black text-sm">
              ATS
            </div>
            <div>
              <h2 className="text-base font-bold text-cc-text">
                مراحل المتقدمين وتدفق التوظيف
              </h2>
              <p className="text-xs text-cc-text-muted">
                تتبع مسار المرشحين من التقديم والفرز حتى القبول النهائي.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-cc-text-muted">تم القبول:</span>
              <span className="text-base font-black text-emerald-400">
                {formatNumber(hiredCount)}
              </span>
            </div>
            <div className="h-4 w-px bg-cc-border" />
            <div className="flex items-center gap-2">
              <span className="text-xs text-cc-text-muted">عروض عمل:</span>
              <span className="text-base font-black text-sky-400">
                {formatNumber(offeredCount)}
              </span>
            </div>
            <div className="h-4 w-px bg-cc-border" />
            <div className="flex items-center gap-2">
              <span className="text-xs text-cc-text-muted">قيد المتابعة:</span>
              <span className="text-base font-black text-amber-400">
                {formatNumber(inProgressCount)}
              </span>
            </div>
          </div>
        </div>

        {/* خط المراحل الأفقي التفاعلي كاللوحة 5 */}
        <div className="py-2 px-2 sm:px-6">
          <div className="flex items-center justify-between gap-1 w-full">
            {PIPELINE_STAGES.map((stage, idx) => {
              const isSelected = statusFilter === stage.key;
              const count = stageCounts[stage.key] || 0;
              const hasNext = idx < PIPELINE_STAGES.length - 1;

              return (
                <React.Fragment key={stage.key}>
                  <button
                    type="button"
                    onClick={() => setStatusFilter(isSelected ? "" : stage.key)}
                    className="flex flex-col items-center group focus:outline-none"
                    title={`تصفية حسب ${stage.label}`}
                  >
                    <div
                      className={`flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-full text-xs font-bold transition-all duration-150 ${
                        isSelected
                          ? "bg-emerald-400 text-slate-950 ring-4 ring-emerald-500/30 shadow-cc-glow"
                          : count > 0
                          ? "bg-sky-500/20 border border-sky-400/50 text-sky-300 group-hover:bg-sky-500/30"
                          : "bg-cc-surface-2 border border-cc-border text-cc-text-muted group-hover:border-cc-border-strong"
                      }`}
                    >
                      {formatNumber(stage.step)}
                    </div>
                    <span
                      className={`text-xs mt-1.5 whitespace-nowrap transition-colors ${
                        isSelected
                          ? "font-bold text-emerald-400"
                          : "text-cc-text-muted group-hover:text-cc-text"
                      }`}
                    >
                      {stage.label}
                    </span>
                    <span className="text-[11px] font-mono font-bold text-cc-text-muted">
                      {formatNumber(count)}
                    </span>
                  </button>
                  {hasNext && (
                    <div
                      className="flex-1 h-0.5 -mt-6 bg-cc-border transition-colors"
                      aria-hidden="true"
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </CcCard>

      {/* 2. شريط الفلاتر والبحث والتبديل */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-cc-surface p-3 rounded-xl border border-cc-border shadow-cc-card">
        <div className="flex flex-wrap items-center gap-2 flex-1">
          {/* مرشح الوظيفة */}
          <select
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            className="rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="">كافة الوظائف</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </select>

          {/* مرشح الحالة */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs text-cc-text focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            {STATUS_CHOICES.map((sc) => (
              <option key={sc.value} value={sc.value}>
                {sc.label}
              </option>
            ))}
          </select>

          {/* بحث نصي محلي */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-3.5 h-3.5 text-cc-text-muted absolute right-3 top-2.5" aria-hidden="true" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="ابحث بالاسم، الهاتف، البريد، أو رمز المرجع..."
              className="w-full rounded-lg border border-cc-border bg-cc-surface-2 pr-8 pl-3 py-1.5 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-cc-text-muted whitespace-nowrap">
            {formatNumber(filteredApplicants.length)} من {formatNumber(applicants.length)} متقدم
          </span>

          {/* زر تبديل العرض بين شبكة البطاقات والجدول */}
          <div className="flex items-center rounded-lg border border-cc-border bg-cc-surface-2 p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`p-1.5 rounded-md transition ${
                viewMode === "grid"
                  ? "bg-cc-surface text-sky-400 shadow-sm"
                  : "text-cc-text-muted hover:text-cc-text"
              }`}
              title="عرض البطاقات"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("table")}
              className={`p-1.5 rounded-md transition ${
                viewMode === "table"
                  ? "bg-cc-surface text-sky-400 shadow-sm"
                  : "text-cc-text-muted hover:text-cc-text"
              }`}
              title="عرض الجدول"
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            type="button"
            onClick={() => setShowBroadcastDialog(true)}
            disabled={!jobFilter}
            title={jobFilter ? "إرسال رسالة إلى متقدّمي الوظيفة المحددة" : "اختر وظيفة أولاً لإرسال رسالة جماعية"}
            className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Users className="h-3.5 w-3.5" aria-hidden="true" />
            <span>رسالة جماعية</span>
          </button>

          <button
            type="button"
            onClick={() => void loadApplicants()}
            disabled={loading}
            className="p-1.5 text-cc-text-muted hover:text-cc-text bg-cc-surface-2 hover:bg-cc-surface border border-cc-border rounded-lg transition"
            title="تحديث القائمة"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {focusError && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs font-semibold text-amber-300">
          {focusError}
        </div>
      )}

      {/* 3. العرض الرئيسي للمتقدمين: شبكة البطاقات بـ CcCard + CcAvatar + CcPill */}
      {viewMode === "grid" ? (
        filteredApplicants.length === 0 ? (
          <CcEmpty
            title={loading ? "جاري تحميل المتقدمين..." : "لا يوجد متقدمون يطابقون الفلاتر المحددة"}
            hint={loading ? undefined : "جرب تغيير معايير البحث أو اختيار وظيفة أو حالة أخرى."}
            action={
              loadError ? (
                <button
                  type="button"
                  onClick={() => void loadApplicants()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg shadow-sm transition"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  إعادة المحاولة
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredApplicants.map((applicant) => {
              const currentStep = STAGE_ORDER[applicant.status] ?? 0;
              const applicantTone = applicantStatusTone(applicant.status);

              return (
                <CcCard
                  key={applicant.id}
                  className="p-4 flex flex-col justify-between hover:border-cc-border-strong cursor-pointer group transition-all duration-200"
                  onClick={() => setSelectedApplicant(applicant)}
                >
                  <div>
                    {/* الرأس: الصورة، الاسم، التقييم، ورقاقات الحالة */}
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <CcAvatar name={applicant.name} size="md" />
                        <div className="min-w-0 flex-1">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedApplicant(applicant);
                            }}
                            className="text-sm font-bold text-cc-text hover:text-sky-400 truncate text-right block focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 rounded"
                          >
                            {applicant.name}
                          </button>
                          <div className="flex items-center gap-1.5 mt-0.5 text-xs text-cc-text-muted flex-wrap">
                            <span className="font-mono text-[10px]">({applicant.reference_code})</span>
                            <span>•</span>
                            <span className="truncate">{applicant.job_title}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <CcPill tone={applicantTone}>
                          {applicant.status_display}
                        </CcPill>
                        {applicant.unread_reply_count > 0 && (
                          <CcPill tone="warning" dot>
                            ردّ غير مقروء
                          </CcPill>
                        )}
                      </div>
                    </div>

                    {/* خط مراحل المتقدم كاللوحة 5 — دوائر مرقمة موصولة بخط، الممتلئة ما بلغه المتقدم */}
                    <div className="my-3 py-2.5 px-3 rounded-lg bg-cc-surface-2/60 border border-cc-border">
                      <div className="flex items-center justify-between text-[10px] text-cc-text-muted mb-2 font-medium">
                        <span>خط تقدم التوظيف</span>
                        {applicant.status === "rejected" ? (
                          <span className="text-rose-400 font-semibold">مرفوض</span>
                        ) : (
                          <span className="text-emerald-400 font-semibold">
                            المرحلة {formatNumber(Math.max(1, currentStep))} من {formatNumber(5)}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center justify-between gap-1 w-full">
                        {PIPELINE_STAGES.map((st, idx) => {
                          const isReached = currentStep >= st.step && applicant.status !== "rejected";
                          const isCurrent = currentStep === st.step && applicant.status !== "rejected";
                          const hasNext = idx < PIPELINE_STAGES.length - 1;
                          const isLineActive = currentStep > st.step && applicant.status !== "rejected";

                          return (
                            <React.Fragment key={st.key}>
                              <div className="flex flex-col items-center">
                                <div
                                  className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold transition-colors ${
                                    isCurrent
                                      ? "bg-emerald-500 text-slate-950 ring-2 ring-emerald-400/50"
                                      : isReached
                                      ? "bg-sky-500 text-slate-950"
                                      : "bg-cc-surface-2 border border-cc-border text-cc-text-muted"
                                  }`}
                                  title={`${st.label} (${st.step})`}
                                >
                                  {formatNumber(st.step)}
                                </div>
                                <span
                                  className={`text-[9px] mt-1 whitespace-nowrap ${
                                    isCurrent
                                      ? "font-bold text-emerald-400"
                                      : isReached
                                      ? "text-sky-300 font-medium"
                                      : "text-cc-text-muted"
                                  }`}
                                >
                                  {st.label}
                                </span>
                              </div>
                              {hasNext && (
                                <div
                                  className={`flex-1 h-0.5 -mt-3.5 transition-colors ${
                                    isLineActive ? "bg-emerald-500" : "bg-cc-border"
                                  }`}
                                  aria-hidden="true"
                                />
                              )}
                            </React.Fragment>
                          );
                        })}
                      </div>
                    </div>

                    {/* معلومات إضافية والتقييم */}
                    <div className="flex items-center justify-between text-xs text-cc-text-muted pt-2 border-t border-cc-border">
                      <div className="flex items-center gap-2">
                        {applicant.rating && applicant.rating > 0 ? (
                          <div className="flex items-center gap-1 text-amber-400 font-bold">
                            <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                            <span>{formatNumber(applicant.rating)}</span>
                          </div>
                        ) : (
                          <span className="text-[11px] text-cc-text-muted">بلا تقييم</span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {applicant.phone && (
                          <span dir="ltr" className="text-[11px] text-cc-text-muted font-mono">
                            {applicant.phone}
                          </span>
                        )}
                        <span className="text-[11px] text-cc-text-muted">
                          {formatDateValue(applicant.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>
                </CcCard>
              );
            })}
          </div>
        )
      ) : (
        /* عرض الجدول البديل بـ CcTable */
        <CcTable>
          <CcThead>
            <tr>
              <CcTh>الاسم ورمز المرجع</CcTh>
              <CcTh>الوظيفة</CcTh>
              <CcTh>الحالة</CcTh>
              <CcTh>التقييم</CcTh>
              <CcTh>تاريخ التقديم</CcTh>
            </tr>
          </CcThead>
          <tbody>
            {filteredApplicants.length === 0 ? (
              <tr>
                <CcTd colSpan={5} className="p-8 text-center">
                  <CcEmpty
                    title={loading ? "جاري تحميل المتقدمين..." : "لا يوجد متقدمون يطابقون الفلاتر المحددة"}
                  />
                </CcTd>
              </tr>
            ) : (
              filteredApplicants.map((applicant) => (
                <CcTr
                  key={applicant.id}
                  onClick={() => setSelectedApplicant(applicant)}
                  className="cursor-pointer"
                >
                  <CcTd className="font-semibold">
                    <div className="flex items-center gap-2">
                      <CcAvatar name={applicant.name} size="sm" />
                      <div>
                        <button
                          type="button"
                          onClick={() => setSelectedApplicant(applicant)}
                          className="rounded text-right text-cc-text hover:text-sky-400 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
                        >
                          {applicant.name}
                        </button>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className="font-mono text-[10px] text-cc-text-muted">
                            ({applicant.reference_code})
                          </span>
                          {applicant.unread_reply_count > 0 && (
                            <CcPill tone="warning" dot>
                              ردّ غير مقروء
                            </CcPill>
                          )}
                        </div>
                      </div>
                    </div>
                  </CcTd>
                  <CcTd className="text-cc-text-muted">{applicant.job_title}</CcTd>
                  <CcTd>
                    <CcPill tone={applicantStatusTone(applicant.status)}>
                      {applicant.status_display}
                    </CcPill>
                  </CcTd>
                  <CcTd>
                    {applicant.rating && applicant.rating > 0 ? (
                      <div className="flex items-center gap-1 text-amber-400 font-bold">
                        <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                        <span>{formatNumber(applicant.rating)}</span>
                      </div>
                    ) : (
                      <span className="text-cc-text-muted text-[11px]">بلا تقييم</span>
                    )}
                  </CcTd>
                  <CcTd className="text-cc-text-muted">
                    {formatDateValue(applicant.created_at)}
                  </CcTd>
                </CcTr>
              ))
            )}
          </tbody>
        </CcTable>
      )}

      {/* لوحة تفاصيل المتقدم */}
      <PlatformApplicantPanel
        applicant={selectedApplicant}
        onClose={() => setSelectedApplicant(null)}
        onUpdated={(updated) => {
          setApplicants((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
          setSelectedApplicant(updated);
        }}
      />

      {showBroadcastDialog && selectedBroadcastJob && (
        <PlatformApplicantBroadcastDialog
          job={selectedBroadcastJob}
          initialStatus={statusFilter}
          onClose={() => setShowBroadcastDialog(false)}
          onSent={() => {
            setShowBroadcastDialog(false);
            void loadApplicants();
          }}
        />
      )}
    </div>
  );
};
