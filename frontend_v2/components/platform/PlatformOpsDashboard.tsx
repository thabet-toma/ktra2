import React, { useEffect, useMemo, useState } from "react";
import {
  getPlatformOpsDashboard,
  PlatformOpsDashboardData,
  WorkOrderDrilldownFilter,
} from "../../services/platformOpsApi";
import {
  PlatformDashboardCompany,
  PlatformDashboardEmployee,
  sortCompaniesWorstFirst,
  sortEmployeesWorstFirst,
} from "../../utils/dashboardRanking";
import { PlatformAnomaly } from "../../utils/interventionAnomalies";
import { CompanyCard } from "./CompanyCard";
import { CrossTenantActivityTable } from "./CrossTenantActivityTable";
import { DrilldownModal } from "./DrilldownModal";
import { EmployeeCard } from "./EmployeeCard";
import { InterventionRail } from "./InterventionRail";
import { PlatformNotificationBell } from "./PlatformNotificationBell";

export const PlatformOpsDashboard: React.FC = () => {
  const [data, setData] = useState<PlatformOpsDashboardData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // مبدل العرض: الافتراضي بطاقة لكل موظف (م٦)
  const [viewUnit, setViewUnit] = useState<"employee" | "company">("employee");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [specialtyFilter, setSpecialtyFilter] = useState<string>("");

  // حالة التنقيب (Drilldown)
  const [drilldownModal, setDrilldownModal] = useState<{
    isOpen: boolean;
    title: string;
    filter: WorkOrderDrilldownFilter;
  }>({
    isOpen: false,
    title: "",
    filter: {},
  });

  // حالة سجل النشاط العابر
  const [activityModal, setActivityModal] = useState<{
    isOpen: boolean;
    employeeId?: number | null;
    employeeName?: string | null;
  }>({
    isOpen: false,
    employeeId: null,
    employeeName: null,
  });

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getPlatformOpsDashboard();
      setData(res);
    } catch (err: any) {
      setError(err?.message || "تعذر تحميل بيانات لوحة المنصة.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  // ترتيب الأسوأ أولاً للموظفين
  const sortedEmployees = useMemo(() => {
    if (!data?.employees) return [];
    return sortEmployeesWorstFirst(data.employees);
  }, [data?.employees]);

  // ترتيب الأسوأ أولاً للشركات
  const sortedCompanies = useMemo(() => {
    if (!data?.companies) return [];
    return sortCompaniesWorstFirst(data.companies);
  }, [data?.companies]);

  // التخصصات المتاحة للفلترة
  const specialties = useMemo(() => {
    if (!data?.employees) return [];
    const set = new Set<string>();
    data.employees.forEach((e) => {
      if (e.specialty) set.add(e.specialty);
    });
    return Array.from(set);
  }, [data?.employees]);

  // فلترة الموظفين المعروضين
  const filteredEmployees = useMemo(() => {
    return sortedEmployees.filter((emp) => {
      if (specialtyFilter && emp.specialty !== specialtyFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          emp.name.toLowerCase().includes(q) ||
          (emp.username && emp.username.toLowerCase().includes(q)) ||
          emp.specialty.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [sortedEmployees, specialtyFilter, searchQuery]);

  // فلترة الشركات المعروضة
  const filteredCompanies = useMemo(() => {
    return sortedCompanies.filter((comp) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          comp.name.toLowerCase().includes(q) ||
          (comp.subscription_plan && comp.subscription_plan.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [sortedCompanies, searchQuery]);

  // إجراءات التنقيب (Drilldown Handlers)
  const handleEmployeeDrilldown = (
    emp: PlatformDashboardEmployee,
    filter: { assignee: number; metric?: "active" | "overdue"; status?: string }
  ) => {
    const metricLabel =
      filter.metric === "overdue"
        ? "الأوامر المتأخرة"
        : filter.metric === "active"
        ? "الأوامر النشطة"
        : "أوامر العمل";
    setDrilldownModal({
      isOpen: true,
      title: `${metricLabel} للموظف: ${emp.name}`,
      filter,
    });
  };

  const handleCompanyDrilldown = (
    comp: PlatformDashboardCompany,
    filter: { metric?: "active" | "overdue"; status?: string }
  ) => {
    const metricLabel =
      filter.metric === "overdue"
        ? "الأوامر المتأخرة"
        : filter.metric === "active"
        ? "الأوامر النشطة"
        : "أوامر العمل";
    setDrilldownModal({
      isOpen: true,
      title: `${metricLabel} لشركة: ${comp.name}`,
      // **بهويّةِ الشركة**: بدونها كان الرقمُ ينقر إلى صفوفِ كلِّ الشركات لا صفوفِه.
      // و`company` تُضيّق داخل النطاق المشتقّ ولا تختار شركةً من خارجه.
      filter: { ...filter, company: comp.id },
    });
  };

  const handleAnomalySelect = (anomaly: PlatformAnomaly) => {
    if (anomaly.work_order_id) {
      setDrilldownModal({
        isOpen: true,
        title: `تنقيب الشذوذ: ${anomaly.message}`,
        // برقمِ الأمر لا بنصِّ عنوانِه: `search` مفتاحٌ لا يقرؤه الخادمُ أصلاً،
        // فكان النقرُ على شذوذِ أمرٍ واحدٍ يُرجع القائمةَ كاملة.
        filter: { work_order: anomaly.work_order_id },
      });
    } else if (anomaly.employee_id) {
      setDrilldownModal({
        isOpen: true,
        title: `أوامر العمل للموظف المعني بالشذوذ: ${anomaly.employee_name}`,
        filter: { assignee: anomaly.employee_id },
      });
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 p-4 sm:p-6 lg:p-8" dir="rtl">
      {/* 1. ترويسة الصفحة */}
      <header className="flex flex-wrap items-center justify-between gap-4 pb-6 mb-6 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-black text-slate-900 tracking-tight">
              مركز قيادة عمليات المنصة
            </h1>
            <span className="px-2.5 py-0.5 text-xs font-bold text-blue-700 bg-blue-100 rounded-full">
              المرحلة السادسة
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            اللوحة التفاعلية، شريط التدخل السريع، والتنقيب المعزول عابراً للشركات.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() =>
              setActivityModal({
                isOpen: true,
                employeeId: null,
                employeeName: null,
              })
            }
            className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-xl transition shadow-sm"
          >
            سجل النشاط العابر
          </button>

          <button
            type="button"
            onClick={loadDashboard}
            className="p-2 text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-100 rounded-full border border-slate-200 transition"
            title="تحديث البيانات"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          {/* جرس الإشعارات المنصية */}
          <PlatformNotificationBell />
        </div>
      </header>

      {/* خطأ التحميل إن وجد */}
      {error && (
        <div className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-800 flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={loadDashboard}
            className="px-3 py-1 bg-rose-100 hover:bg-rose-200 rounded-lg font-bold text-xs"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      {/* 2. شريط التدخل السريع (Intervention Rail) */}
      <section className="mb-6">
        <InterventionRail
          anomalies={data?.anomalies || []}
          onSelectAnomaly={handleAnomalySelect}
        />
      </section>

      {/* 3. شريط التحكم والفلترة ومبدل العرض (موظف / شركة) */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 mb-6 flex flex-wrap items-center justify-between gap-4 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-slate-500">وحدة العرض:</span>
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => setViewUnit("employee")}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition ${
                viewUnit === "employee"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              عرض حسب الموظف ({data?.employees?.length || 0})
            </button>
            <button
              type="button"
              onClick={() => setViewUnit("company")}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition ${
                viewUnit === "company"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              عرض حسب الشركة ({data?.companies?.length || 0})
            </button>
          </div>
        </div>

        {/* البحث والفلاتر */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-64">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={viewUnit === "employee" ? "البحث بالاسم أو التخصص..." : "البحث باسم الشركة..."}
              className="w-full px-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {viewUnit === "employee" && specialties.length > 0 && (
            <select
              value={specialtyFilter}
              onChange={(e) => setSpecialtyFilter(e.target.value)}
              className="px-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">كافة التخصصات</option>
              {specialties.map((spec) => (
                <option key={spec} value={spec}>
                  {spec}
                </option>
              ))}
            </select>
          )}

          <span className="text-xs text-slate-400 font-medium">
            الفرز: الأسوأ أولاً (تلقائي)
          </span>
        </div>
      </div>

      {/* 4. شبكة البطاقات */}
      <main>
        {loading ? (
          <div className="py-24 text-center text-sm text-slate-400">
            جاري تحميل لوحة العمليات...
          </div>
        ) : viewUnit === "employee" ? (
          filteredEmployees.length === 0 ? (
            <div className="py-24 text-center text-sm text-slate-400 bg-white rounded-xl border border-slate-200">
              لا يوجد موظفون مطابقون للشروط الحالية
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredEmployees.map((emp) => (
                <EmployeeCard
                  key={emp.id}
                  employee={emp}
                  onDrilldown={(f) => handleEmployeeDrilldown(emp, f)}
                  onViewActivity={(id, name) =>
                    setActivityModal({
                      isOpen: true,
                      employeeId: id,
                      employeeName: name,
                    })
                  }
                />
              ))}
            </div>
          )
        ) : filteredCompanies.length === 0 ? (
          <div className="py-24 text-center text-sm text-slate-400 bg-white rounded-xl border border-slate-200">
            لا توجد شركات مطابقة للشروط الحالية
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredCompanies.map((comp) => (
              <CompanyCard
                key={comp.id}
                company={comp}
                onDrilldown={(f) => handleCompanyDrilldown(comp, f)}
              />
            ))}
          </div>
        )}
      </main>

      {/* 5. نوافذ التنقيب وسجل النشاط */}
      <DrilldownModal
        isOpen={drilldownModal.isOpen}
        onClose={() =>
          setDrilldownModal((prev) => ({ ...prev, isOpen: false }))
        }
        title={drilldownModal.title}
        initialFilter={drilldownModal.filter}
      />

      <CrossTenantActivityTable
        isOpen={activityModal.isOpen}
        onClose={() =>
          setActivityModal((prev) => ({ ...prev, isOpen: false }))
        }
        employeeId={activityModal.employeeId}
        employeeName={activityModal.employeeName}
      />
    </div>
  );
};

export default PlatformOpsDashboard;
