import React, { useCallback, useEffect, useState } from "react";
import { Briefcase, ShieldAlert, UserCheck, Users } from "lucide-react";

import {
  listPlatformJobs,
  type PlatformJobPosting,
} from "../../services/platformHiringApi";
import { PlatformApplicantsTab } from "./PlatformApplicantsTab";
import { PlatformJobsTab } from "./PlatformJobsTab";
import { PlatformRecruitersTab } from "./PlatformRecruitersTab";

interface PlatformHiringScreenProps {
  canManageRecruiters: boolean;
}

export const PlatformHiringScreen: React.FC<PlatformHiringScreenProps> = ({
  canManageRecruiters,
}) => {
  const [activeTab, setActiveTab] = useState<"jobs" | "applicants" | "recruiters">("jobs");
  const [jobs, setJobs] = useState<PlatformJobPosting[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [isForbidden, setIsForbidden] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // الفلتر الممرر لتبويب المتقدمين عند الضغط على «عرض المتقدمين» من صف وظيفة
  const [applicantJobFilter, setApplicantJobFilter] = useState<number | null>(null);

  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    setIsForbidden(false);
    setLoadError(null);
    try {
      const data = await listPlatformJobs();
      setJobs(data);
    } catch (err: any) {
      if (err?.status === 403) {
        setIsForbidden(true);
      } else {
        setLoadError(err?.message || "تعذر تحميل إعلانات الوظائف.");
      }
    } finally {
      setLoadingJobs(false);
    }
  }, []);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const handleSelectJobForApplicants = (jobId: number) => {
    setApplicantJobFilter(jobId);
    setActiveTab("applicants");
  };

  if (isForbidden) {
    return (
      <div className="p-8 max-w-4xl mx-auto text-right" dir="rtl">
        <div className="p-8 rounded-2xl bg-amber-50/70 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-center space-y-4 shadow-sm">
          <ShieldAlert className="w-12 h-12 text-amber-600 dark:text-amber-400 mx-auto" />
          <div className="space-y-1">
            <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              صلاحية غير متوفرة
            </h2>
            <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
              هذه الشاشة لمسؤولي التوظيف في المنصة.
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto">
              يتطلب الدخول لهذه الصفحة إسناد دور «مسؤول توظيف المنصة» لحسابك من قبل مدير النظام.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6 text-right" dir="rtl">
      {/* الترويسة الرئيسية */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-4">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Briefcase className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            التوظيف المنصّي
          </h1>
          <p className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mt-1">
            إدارة إعلانات التوظيف المنصية، متابعة طلبات المرشحين، وإصدار روابط الدعوات والقبول.
          </p>
        </div>

        {/* أزرار التبويبات */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/60 p-1 rounded-xl border border-slate-200 dark:border-slate-700">
          <button
            type="button"
            onClick={() => setActiveTab("jobs")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === "jobs"
                ? "bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm"
                : "text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100"
            }`}
          >
            <Briefcase className="w-3.5 h-3.5" />
            الوظائف
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("applicants")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeTab === "applicants"
                ? "bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm"
                : "text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100"
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            المتقدّمون
          </button>
          {canManageRecruiters && (
            <button
              type="button"
              onClick={() => setActiveTab("recruiters")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeTab === "recruiters"
                  ? "bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm"
                  : "text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100"
              }`}
            >
              <UserCheck className="w-3.5 h-3.5" />
              مسؤولو التوظيف
            </button>
          )}
        </div>
      </div>

      {/* محتوى التبويب النشط */}
      {activeTab === "jobs" && (
        <PlatformJobsTab
          jobs={jobs}
          loading={loadingJobs}
          loadError={loadError}
          canListPolicyProfiles={canManageRecruiters}
          onRefresh={() => void loadJobs()}
          onJobCreated={(job) => setJobs((prev) => [job, ...prev])}
          onJobUpdated={(job) => setJobs((prev) => prev.map((j) => (j.id === job.id ? job : j)))}
          onSelectJobForApplicants={handleSelectJobForApplicants}
        />
      )}

      {activeTab === "applicants" && (
        <PlatformApplicantsTab
          jobs={jobs}
          initialJobFilter={applicantJobFilter}
        />
      )}

      {activeTab === "recruiters" && canManageRecruiters && (
        <PlatformRecruitersTab />
      )}
    </div>
  );
};
