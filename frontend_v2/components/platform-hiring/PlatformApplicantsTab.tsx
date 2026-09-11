import React, { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Search, Star, Users } from "lucide-react";

import {
  listPlatformApplicants,
  type PlatformJobApplicant,
  type PlatformJobPosting,
} from "../../services/platformHiringApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import {
  APPLICANT_STATUS_OPTIONS,
  applicantStatusBadgeClass,
  filterPlatformApplicants,
} from "../../utils/platformHiring";
import { PlatformApplicantPanel } from "./PlatformApplicantPanel";

interface PlatformApplicantsTabProps {
  jobs: PlatformJobPosting[];
  initialJobFilter?: number | null;
}

const STATUS_CHOICES = [
  { value: "", label: "كافة الحالات" },
  ...APPLICANT_STATUS_OPTIONS,
];

export const PlatformApplicantsTab: React.FC<PlatformApplicantsTabProps> = ({
  jobs,
  initialJobFilter,
}) => {
  const [jobFilter, setJobFilter] = useState<string>(
    initialJobFilter ? String(initialJobFilter) : "",
  );
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const [applicants, setApplicants] = useState<PlatformJobApplicant[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedApplicant, setSelectedApplicant] = useState<PlatformJobApplicant | null>(null);

  useEffect(() => {
    if (initialJobFilter) {
      setJobFilter(String(initialJobFilter));
    }
  }, [initialJobFilter]);

  const loadApplicants = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await listPlatformApplicants({
        job: jobFilter ? parseInt(jobFilter, 10) : undefined,
        status: statusFilter || undefined,
      });
      setApplicants(data);
    } catch (err: any) {
      setApplicants([]);
      setLoadError(err?.message || "تعذر تحميل المتقدمين.");
    } finally {
      setLoading(false);
    }
  }, [jobFilter, statusFilter]);

  useEffect(() => {
    void loadApplicants();
  }, [loadApplicants]);

  // تصفية محلية بالبحث
  const filteredApplicants = useMemo(() => {
    return filterPlatformApplicants(applicants, searchQuery);
  }, [applicants, searchQuery]);

  return (
    <div className="space-y-4 text-right" dir="rtl">
      {/* شريط الفلاتر والبحث */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-white dark:bg-slate-900 p-3 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="flex flex-wrap items-center gap-2 flex-1">
          {/* مرشح الوظيفة */}
          <select
            value={jobFilter}
            onChange={(e) => setJobFilter(e.target.value)}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {STATUS_CHOICES.map((sc) => (
              <option key={sc.value} value={sc.value}>
                {sc.label}
              </option>
            ))}
          </select>

          {/* بحث نصي محلي */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute right-3 top-2.5" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="ابحث بالاسم، الهاتف، البريد، أو رمز المرجع..."
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 pr-8 pl-3 py-1.5 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {formatNumber(filteredApplicants.length)} من {formatNumber(applicants.length)} متقدم
          </span>
          <button
            type="button"
            onClick={() => void loadApplicants()}
            disabled={loading}
            className="p-1.5 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            title="تحديث القائمة"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* جدول المتقدمين */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
        <table className="w-full text-right text-xs">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300 font-semibold border-b border-slate-200 dark:border-slate-800">
            <tr>
              <th className="p-3">الاسم ورمز المرجع</th>
              <th className="p-3">الوظيفة</th>
              <th className="p-3">الحالة</th>
              <th className="p-3">التقييم</th>
              <th className="p-3">تاريخ التقديم</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-slate-800 dark:text-slate-200">
            {filteredApplicants.length === 0 ? (
              <tr>
                <td colSpan={5} className="p-8 text-center text-slate-400 dark:text-slate-500">
                  {loading ? (
                    "جاري تحميل المتقدمين..."
                  ) : loadError ? (
                    <div className="flex flex-col items-center justify-center gap-2">
                      <p className="text-xs font-semibold text-rose-600 dark:text-rose-400">
                        {loadError}
                      </p>
                      <button
                        type="button"
                        onClick={() => void loadApplicants()}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        إعادة المحاولة
                      </button>
                    </div>
                  ) : (
                    "لا يوجد متقدمون يطابقون الفلاتر المحددة."
                  )}
                </td>
              </tr>
            ) : (
              filteredApplicants.map((applicant) => (
                <tr
                  key={applicant.id}
                  onClick={() => setSelectedApplicant(applicant)}
                  className="hover:bg-blue-50/40 dark:hover:bg-blue-950/20 cursor-pointer transition"
                >
                  <td className="p-3 font-semibold text-slate-900 dark:text-slate-100">
                    <div className="flex items-center gap-2">
                      <span>{applicant.name}</span>
                      <span className="font-mono text-[10px] text-slate-400 font-normal">
                        ({applicant.reference_code})
                      </span>
                    </div>
                    {applicant.phone && (
                      <div dir="ltr" className="text-[11px] text-slate-500 dark:text-slate-400 font-normal inline-block">
                        {applicant.phone}
                      </div>
                    )}
                  </td>
                  <td className="p-3 text-slate-700 dark:text-slate-300">
                    {applicant.job_title}
                  </td>
                  <td className="p-3">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${applicantStatusBadgeClass(
                        applicant.status,
                      )}`}
                    >
                      {applicant.status_display}
                    </span>
                  </td>
                  <td className="p-3">
                    {applicant.rating && applicant.rating > 0 ? (
                      <div className="flex items-center gap-1 text-amber-500">
                        <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                        <span className="font-bold text-xs">{formatNumber(applicant.rating)}</span>
                      </div>
                    ) : (
                      <span className="text-slate-400 text-[11px]">بلا تقييم</span>
                    )}
                  </td>
                  <td className="p-3 text-slate-500 dark:text-slate-400">
                    {formatDateValue(applicant.created_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* لوحة تفاصيل المتقدم */}
      <PlatformApplicantPanel
        applicant={selectedApplicant}
        onClose={() => setSelectedApplicant(null)}
        onUpdated={(updated) => {
          setApplicants((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
          setSelectedApplicant(updated);
        }}
      />
    </div>
  );
};
