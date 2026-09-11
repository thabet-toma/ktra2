import React, { useState } from "react";
import {
  Copy,
  Edit2,
  ExternalLink,
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
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingJob, setEditingJob] = useState<PlatformJobPosting | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);

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
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">
            إجمالي الوظائف: {formatNumber(jobs.length)}
          </span>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="p-1.5 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            title="تحديث القائمة"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        <button
          type="button"
          onClick={() => {
            setEditingJob(null);
            setModalOpen(true);
          }}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition"
        >
          <Plus className="w-4 h-4" />
          وظيفة جديدة
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <table className="w-full text-right text-xs">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300 font-semibold border-b border-slate-200 dark:border-slate-800">
            <tr>
              <th className="p-3">العنوان</th>
              <th className="p-3">التخصص</th>
              <th className="p-3">الحالة</th>
              <th className="p-3 text-center">المتقدمون</th>
              <th className="p-3">تاريخ الانتهاء</th>
              <th className="p-3 text-center">الإجراءات</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-slate-800 dark:text-slate-200">
            {jobs.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-slate-400 dark:text-slate-500">
                  {loading ? (
                    "جاري تحميل الوظائف..."
                  ) : loadError ? (
                    <div className="flex flex-col items-center justify-center gap-2">
                      <p className="text-xs font-semibold text-rose-600 dark:text-rose-400">
                        {loadError}
                      </p>
                      <button
                        type="button"
                        onClick={onRefresh}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        إعادة المحاولة
                      </button>
                    </div>
                  ) : (
                    "لا توجد إعلانات وظائف حالياً."
                  )}
                </td>
              </tr>
            ) : (
              jobs.map((job) => {
                const statusBadge = job.is_live ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                    منشور
                  </span>
                ) : job.is_open ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800">
                    منتهي الصلاحية
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700">
                    مغلق
                  </span>
                );

                const specialtyBadge = job.specialty ? (
                  <span className="font-mono text-slate-700 dark:text-slate-300">
                    {job.specialty}
                  </span>
                ) : (
                  <span
                    className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
                    title="الموظّفُ المقبولُ يرث التخصّصَ؛ بلا تخصّصٍ لا يُطابَق بملفّ سياسة"
                  >
                    بلا تخصّص
                  </span>
                );

                return (
                  <tr
                    key={job.id}
                    className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition"
                  >
                    <td className="p-3 font-semibold text-slate-900 dark:text-slate-100">
                      <div>{job.title}</div>
                      {job.location && (
                        <div className="text-[11px] text-slate-500 dark:text-slate-400 font-normal">
                          {job.location} · {job.employment_type_display}
                        </div>
                      )}
                    </td>
                    <td className="p-3">{specialtyBadge}</td>
                    <td className="p-3">{statusBadge}</td>
                    <td className="p-3 text-center font-bold">
                      {formatNumber(job.applicants_count)}
                    </td>
                    <td className="p-3 text-slate-600 dark:text-slate-400">
                      {job.expires_at ? formatDateValue(job.expires_at) : "دائم"}
                    </td>
                    <td className="p-3">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleCopyLink(job)}
                          className="p-1.5 text-slate-500 hover:text-blue-600 dark:text-slate-400 dark:hover:text-blue-400 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition"
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
                          className="p-1.5 text-slate-500 hover:text-emerald-600 dark:text-slate-400 dark:hover:text-emerald-400 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                          title="تعديل الإعلان"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleToggleOpen(job)}
                          disabled={actionLoadingId === job.id}
                          className={`p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition ${
                            job.is_open
                              ? "text-slate-500 hover:text-rose-600 dark:text-slate-400 dark:hover:text-rose-400"
                              : "text-slate-500 hover:text-emerald-600 dark:text-slate-400 dark:hover:text-emerald-400"
                          }`}
                          title={job.is_open ? "إغلاق الإعلان" : "إعادة فتح الإعلان"}
                        >
                          {job.is_open ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleRegenerateLink(job)}
                          disabled={actionLoadingId === job.id}
                          className="p-1.5 text-slate-500 hover:text-amber-600 dark:text-slate-400 dark:hover:text-amber-400 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                          title="رابط جديد (إبطال القديم)"
                        >
                          <Link2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onSelectJobForApplicants(job.id)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/40 dark:text-blue-300 dark:hover:bg-blue-900/60 rounded border border-blue-200 dark:border-blue-800 transition mr-1"
                          title="عرض المتقدمين لهذه الوظيفة"
                        >
                          <Users className="w-3 h-3" />
                          عرض المتقدمين
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

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
