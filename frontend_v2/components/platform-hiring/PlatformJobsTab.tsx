import React, { useState } from "react";
import {
  Copy,
  Edit2,
  Link2,
  Lock,
  Plus,
  RefreshCw,
  Unlock,
  Users,
} from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  closePlatformJob,
  regeneratePlatformJobLink,
  reopenPlatformJob,
  type PlatformJobPosting,
} from "../../services/platformHiringApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  CcCard,
  CcEmpty,
  CcPill,
  CcStatTile,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "../platform/ui";
import { PlatformJobFormModal } from "./PlatformJobFormModal";

interface PlatformJobsTabProps {
  jobs: PlatformJobPosting[];
  loading: boolean;
  loadError?: string | null;
  canListPolicyProfiles: boolean;
  onRefresh: () => void;
  onJobUpdated: (job: PlatformJobPosting) => void;
  onJobCreated: (job: PlatformJobPosting) => void;
  onSelectJobForApplicants: (jobId: number) => void;
}

export const PlatformJobsTab: React.FC<PlatformJobsTabProps> = ({
  jobs,
  loading,
  loadError,
  canListPolicyProfiles,
  onRefresh,
  onJobUpdated,
  onJobCreated,
  onSelectJobForApplicants,
}: PlatformJobsTabProps) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<PlatformJobPosting | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

  const totalJobs = jobs.length;
  const liveJobs = jobs.filter((j) => j.is_live).length;
  const closedJobs = jobs.filter((j) => !j.is_open).length;

  const handleCopyLink = async (job: PlatformJobPosting) => {
    try {
      await navigator.clipboard.writeText(job.public_url);
      toast("تم نسخ الرابط العام للوظيفة بنجاح.", "success");
    } catch {
      toast("تعذر نسخ الرابط إلى الحافظة.", "error");
    }
  };

  const handleToggleOpen = async (job: PlatformJobPosting) => {
    const isClosing = job.is_open;
    const ok = await confirm({
      title: isClosing ? "إغلاق إعلان الوظيفة" : "إعادة فتح إعلان الوظيفة",
      message: isClosing
        ? `هل أنت متأكد من إغلاق «${job.title}»؟ لن يتمكن أحد من التقديم عليها حتى يُعاد فتحها.`
        : `هل تريد إعادة فتح «${job.title}» للتقديم العام؟`,
      confirmText: isClosing ? "إغلاق الإعلان" : "إعادة فتح",
      danger: isClosing,
    });
    if (!ok) return;

    setActionLoadingId(job.id);
    try {
      const updated = isClosing ? await closePlatformJob(job.id) : await reopenPlatformJob(job.id);
      onJobUpdated(updated);
      toast(isClosing ? "تم إغلاق إعلان الوظيفة." : "تمت إعادة فتح إعلان الوظيفة.", "success");
    } catch (err: any) {
      toast(err?.message || "فشل تغيير حالة الوظيفة.", "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRegenerateLink = async (job: PlatformJobPosting) => {
    const ok = await confirm({
      title: "توليد رابط عام جديد",
      message: "سيتوقف الرابط القديم فوراً عن العمل لكل من يحمله أو فُتحت له الصفحة. هل تريد المتابعة وتوليد رابط جديد؟",
      confirmText: "إعادة التوليد فوراً",
      danger: true,
    });
    if (!ok) return;

    setActionLoadingId(job.id);
    try {
      const updated = await regeneratePlatformJobLink(job.id);
      onJobUpdated(updated);
      toast("تم إبطال الرابط القديم وتوليد رابط جديد بنجاح.", "success");
    } catch (err: any) {
      toast(err?.message || "تعذر توليد رابط جديد.", "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="space-y-4 text-right" dir="rtl">
      {/* صف الأرقام العلوي بـ CcStatTile (إجمالي/منشور/مغلق) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <CcCard className="p-4">
          <CcStatTile
            label="إجمالي الوظائف"
            value={totalJobs}
            tone="neutral"
          />
        </CcCard>
        <CcCard className="p-4">
          <CcStatTile
            label="وظائف منشورة"
            value={liveJobs}
            tone="success"
          />
        </CcCard>
        <CcCard className="p-4">
          <CcStatTile
            label="وظائف مغلقة"
            value={closedJobs}
            tone="warning"
          />
        </CcCard>
      </div>

      {/* شريط الإجراءات */}
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-cc-text-muted hover:text-cc-text bg-cc-surface hover:bg-cc-surface-2 border border-cc-border rounded-lg transition disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          title="تحديث القائمة"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>تحديث</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setEditingJob(null);
            setModalOpen(true);
          }}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        >
          <Plus className="w-4 h-4" />
          وظيفة جديدة
        </button>
      </div>

      {/* جدول الوظائف بـ CcTable */}
      <CcTable>
        <CcThead>
          <tr>
            <CcTh>العنوان</CcTh>
            <CcTh>التخصص</CcTh>
            <CcTh>الحالة</CcTh>
            <CcTh className="text-center">المتقدمون</CcTh>
            <CcTh>تاريخ الانتهاء</CcTh>
            <CcTh className="text-center">الإجراءات</CcTh>
          </tr>
        </CcThead>
        <tbody>
          {jobs.length === 0 ? (
            <tr>
              <CcTd colSpan={6} className="p-8 text-center">
                {loading ? (
                  <div className="flex items-center justify-center gap-2 text-xs text-cc-text-muted">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>جاري تحميل الوظائف...</span>
                  </div>
                ) : loadError ? (
                  <div className="flex flex-col items-center justify-center gap-2">
                    <p className="text-xs font-semibold text-rose-400">{loadError}</p>
                    <button
                      type="button"
                      onClick={onRefresh}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg shadow-sm transition"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      إعادة المحاولة
                    </button>
                  </div>
                ) : (
                  <CcEmpty
                    title="لا توجد إعلانات وظائف حالياً"
                    hint="يمكنك إنشاء أول إعلان وظيفي للبدء في استقبال طلبات التوظيف."
                  />
                )}
              </CcTd>
            </tr>
          ) : (
            jobs.map((job) => {
              const statusPill = job.is_live ? (
                <CcPill tone="success" dot>منشور</CcPill>
              ) : job.is_open ? (
                <CcPill tone="warning" dot>منتهي الصلاحية</CcPill>
              ) : (
                <CcPill tone="neutral">مغلق</CcPill>
              );

              return (
                <CcTr key={job.id}>
                  <CcTd className="font-semibold">
                    <div className="text-cc-text">{job.title}</div>
                    {job.location && (
                      <div className="text-[11px] text-cc-text-muted font-normal mt-0.5">
                        {job.location} · {job.employment_type_display}
                      </div>
                    )}
                  </CcTd>
                  <CcTd>
                    {job.specialty ? (
                      <CcPill tone="accent">{job.specialty}</CcPill>
                    ) : (
                      <CcPill tone="warning" title="الموظّفُ المقبولُ يرث التخصّصَ؛ بلا تخصّصٍ لا يُطابَق بملفّ سياسة">
                        بلا تخصّص
                      </CcPill>
                    )}
                  </CcTd>
                  <CcTd>{statusPill}</CcTd>
                  <CcTd className="text-center font-bold text-cc-text">
                    {formatNumber(job.applicants_count)}
                  </CcTd>
                  <CcTd className="text-cc-text-muted">
                    {job.expires_at ? formatDateValue(job.expires_at) : "دائم"}
                  </CcTd>
                  <CcTd>
                    <div className="flex items-center justify-center gap-1">
                      <button
                        type="button"
                        onClick={() => handleCopyLink(job)}
                        className="p-1.5 text-cc-text-muted hover:text-sky-400 rounded-lg hover:bg-cc-surface-2 transition"
                        title="نسخ الرابط العام"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setEditingJob(job);
                          setModalOpen(true);
                        }}
                        className="p-1.5 text-cc-text-muted hover:text-emerald-400 rounded-lg hover:bg-cc-surface-2 transition"
                        title="تعديل الإعلان"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleOpen(job)}
                        disabled={actionLoadingId === job.id}
                        className={`p-1.5 rounded-lg hover:bg-cc-surface-2 transition ${
                          job.is_open
                            ? "text-cc-text-muted hover:text-rose-400"
                            : "text-cc-text-muted hover:text-emerald-400"
                        }`}
                        title={job.is_open ? "إغلاق الإعلان" : "إعادة فتح الإعلان"}
                      >
                        {job.is_open ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRegenerateLink(job)}
                        disabled={actionLoadingId === job.id}
                        className="p-1.5 text-cc-text-muted hover:text-amber-400 rounded-lg hover:bg-cc-surface-2 transition"
                        title="رابط جديد (إبطال القديم)"
                      >
                        <Link2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => onSelectJobForApplicants(job.id)}
                        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-sky-400 bg-sky-500/15 hover:bg-sky-500/25 rounded-md border border-sky-500/30 transition mr-1"
                        title="عرض المتقدمين لهذه الوظيفة"
                      >
                        <Users className="w-3 h-3" />
                        عرض المتقدمين
                      </button>
                    </div>
                  </CcTd>
                </CcTr>
              );
            })
          )}
        </tbody>
      </CcTable>

      <PlatformJobFormModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        jobToEdit={editingJob}
        canListPolicyProfiles={canListPolicyProfiles}
        onSaved={(saved) => {
          if (editingJob) {
            onJobUpdated(saved);
          } else {
            onJobCreated(saved);
          }
        }}
      />
    </div>
  );
};
