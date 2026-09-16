import React, { useCallback, useEffect, useState } from "react";
import { Briefcase, CalendarDays, ShieldAlert, UserCheck, Users } from "lucide-react";

import {
  listPlatformJobs,
  type PlatformJobPosting,
} from "../../services/platformHiringApi";
import { CcCard, CcEmpty, CcPill, CcTabs, type CcTabItem } from "../platform/ui";
import { PlatformApplicantsTab } from "./PlatformApplicantsTab";
import { PlatformJobsTab } from "./PlatformJobsTab";
import { PlatformMeetingsTab } from "./PlatformMeetingsTab";
import { PlatformRecruitersTab } from "./PlatformRecruitersTab";

interface PlatformHiringScreenProps {
  canManageRecruiters: boolean;
}

const HIRING_TABS: CcTabItem[] = [
  { key: "jobs", label: "الوظائف", icon: <Briefcase className="w-4 h-4" /> },
  { key: "applicants", label: "المتقدّمون", icon: <Users className="w-4 h-4" /> },
  { key: "meetings", label: "اجتماعات", icon: <CalendarDays className="w-4 h-4" /> },
  { key: "recruiters", label: "مسؤولو التوظيف", icon: <UserCheck className="w-4 h-4" /> },
];

export const PlatformHiringScreen: React.FC<PlatformHiringScreenProps> = ({
  canManageRecruiters,
}: PlatformHiringScreenProps) => {
  const [activeTab, setActiveTab] = useState<"jobs" | "applicants" | "meetings" | "recruiters">("jobs");
  const [jobs, setJobs] = useState<PlatformJobPosting[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [isForbidden, setIsForbidden] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // الفلتر الممرر لتبويب المتقدمين عند الضغط على «عرض المتقدمين» من صف وظيفة
  const [applicantJobFilter, setApplicantJobFilter] = useState<number | null>(null);
  const [applicantFocus, setApplicantFocus] = useState<number | null>(null);

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

  // **والطلبُ يُستهلَك بعد تنفيذه**: لو بقي المعرّفُ مخزَّناً بعد فتح البطاقة،
  // لَما فُتحت في المرّة الثانية — يعود المستخدمُ إلى الشبكة ويضغط الاسمَ نفسَه
  // فينتقل التبويبُ ولا يحدث شيء، وهو طريقٌ مسدودٌ بلا رسالة.
  // ثابتُ الهويّة كي لا يُعاد تشغيلُ أثرِ الفتح في كلّ رسم.
  const handleApplicantFocusHandled = useCallback(() => setApplicantFocus(null), []);
  const handleApplicantJobFilterHandled = useCallback(() => setApplicantJobFilter(null), []);

  const handleOpenApplicantFromMeetings = (id: number) => {
    setApplicantFocus(id);
    setActiveTab("applicants");
  };

  const visibleTabs = canManageRecruiters
    ? HIRING_TABS
    : HIRING_TABS.filter((t) => t.key !== "recruiters");

  if (isForbidden) {
    return (
      <div
        className="platform-surface ops-shell min-h-screen bg-cc-bg text-cc-text p-4 sm:p-6 lg:p-8 flex items-center justify-center"
        dir="rtl"
      >
        <CcCard tone="warning" className="max-w-md w-full p-6 text-center">
          <CcEmpty
            icon={<ShieldAlert className="w-10 h-10 text-amber-400" />}
            title="صلاحية غير متوفرة"
            hint="يتطلب الدخول لهذه الصفحة إسناد دور «مسؤول توظيف المنصة» لحسابك من قبل مدير النظام."
          />
        </CcCard>
      </div>
    );
  }

  return (
    <div
      className="platform-surface ops-shell min-h-screen bg-cc-bg text-cc-text p-4 sm:p-6 lg:p-8 pb-24 md:pb-6 lg:pb-8"
      dir="rtl"
    >
      {/* الترويسة الرئيسية كترويسة PlatformOpsDashboard */}
      <header className="flex flex-wrap items-center gap-4 pb-6 mb-6 border-b border-cc-border">
        <div className="flex flex-col">
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl sm:text-2xl font-black text-cc-text tracking-tight flex items-center gap-2">
              <Briefcase className="w-6 h-6 text-sky-400" />
              التوظيف المنصّي
            </h1>
            <CcPill tone="accent">المرحلة الثامنة</CcPill>
          </div>
          <p className="text-xs text-cc-text-muted mt-1">
            إدارة إعلانات التوظيف المنصية، متابعة طلبات المرشحين، وإصدار روابط الدعوات والقبول.
          </p>
        </div>

      </header>

      {/* شريط التبويبات بـ CcTabs */}
      <div className="w-full mb-6">
        <CcTabs
          tabs={visibleTabs}
          active={activeTab}
          onChange={(key) => setActiveTab(key as "jobs" | "applicants" | "meetings" | "recruiters")}
        />
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
          onJobFilterHandled={handleApplicantJobFilterHandled}
          focusApplicantId={applicantFocus}
          onFocusHandled={handleApplicantFocusHandled}
        />
      )}

      {activeTab === "meetings" && <PlatformMeetingsTab onOpenApplicant={handleOpenApplicantFromMeetings} />}

      {activeTab === "recruiters" && canManageRecruiters && (
        <PlatformRecruitersTab />
      )}
    </div>
  );
};
