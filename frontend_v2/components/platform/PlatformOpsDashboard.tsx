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
import { PromoteEmployeePanel } from "./PromoteEmployeePanel";
import { InterventionRail } from "./InterventionRail";
import { PlatformNotificationBell } from "./PlatformNotificationBell";
import { ServiceUnitCatalogPanel } from "./ServiceUnitCatalogPanel";
import { ServiceUsageLedgerPanel } from "./ServiceUsageLedgerPanel";
import { WorkOrdersPanel } from "./WorkOrdersPanel";
import { PilotSettingsPanel } from "./PilotSettingsPanel";
import { CompensationMonthClosePanel } from "./CompensationMonthClosePanel";
import { EmployeeWalletPanel } from "./EmployeeWalletPanel";
import { IntegrationKeysPanel } from "./IntegrationKeysPanel";
import { ChampionsPanel } from "./ChampionsPanel";
import { ProfitabilityPanel } from "./ProfitabilityPanel";
import { PerformanceReviewRequestsPanel } from "./PerformanceReviewRequestsPanel";
import { MeetingsPanel } from "./MeetingsPanel";
import { PlatformTasksAdminPanel } from "./PlatformTasksAdminPanel";
import { EmployeeTargetsModal } from "./EmployeeTargetsModal";
import { EmployeeProfileDrawer } from "./EmployeeProfileDrawer";
import { WorkspaceRoom, RoomOccupant } from "./WorkspaceRoom";
import { CrmPanel } from "./staff/crm/CrmPanel";
import { countPresent, derivePresence, sortByPresence } from "../../utils/roomPresence";
import { formatLastActive } from "../../utils/lastActiveFormat";
import { DashboardHeroStrip } from "./DashboardHeroStrip";
import { TeamTargetBars } from "./TeamTargetBars";
import {
  LayoutDashboard,
  ClipboardList,
  DoorOpen,
  CalendarClock,
  Search,
  RefreshCw,
  Users,
  CheckSquare,
  Layers,
  BookOpen,
  Sliders,
  Calendar,
  Wallet,
  KeyRound,
  Trophy,
  TrendingUp,
  FileText,
} from "lucide-react";
import { CcPill, CcTabs, type CcTabItem } from "./ui";

type DashboardTab =
  | "overview" | "work_orders" | "catalog" | "usage_ledger"
  | "pilot_settings" | "compensation_close" | "wallet" | "integration_keys" | "champions"
  | "profitability" | "review_requests" | "workspace_room" | "meetings" | "staff_tasks" | "crm";

const DASHBOARD_TABS: CcTabItem[] = [
  { key: "overview", label: "اللوحة", icon: <LayoutDashboard className="w-4 h-4" /> },
  { key: "crm", label: "العملاء", icon: <Users className="w-4 h-4" /> },
  { key: "workspace_room", label: "مساحة العمل", icon: <DoorOpen className="w-4 h-4" /> },
  { key: "work_orders", label: "أوامر العمل", icon: <ClipboardList className="w-4 h-4" /> },
  { key: "staff_tasks", label: "مهام الموظفين", icon: <CheckSquare className="w-4 h-4" /> },
  { key: "catalog", label: "كتالوج وحدات الخدمة", icon: <Layers className="w-4 h-4" /> },
  { key: "usage_ledger", label: "دفتر الاستخدام", icon: <BookOpen className="w-4 h-4" /> },
  { key: "pilot_settings", label: "سياسات الأداء والتعويض", icon: <Sliders className="w-4 h-4" /> },
  { key: "compensation_close", label: "إغلاق الشهر", icon: <Calendar className="w-4 h-4" /> },
  { key: "wallet", label: "محفظة الموظف", icon: <Wallet className="w-4 h-4" /> },
  { key: "integration_keys", label: "مفاتيح قنوات الإدخال", icon: <KeyRound className="w-4 h-4" /> },
  { key: "champions", label: "Champions", icon: <Trophy className="w-4 h-4" /> },
  { key: "profitability", label: "الربحيّة", icon: <TrendingUp className="w-4 h-4" /> },
  { key: "review_requests", label: "اعتراضات الأداء", icon: <FileText className="w-4 h-4" /> },
  { key: "meetings", label: "الاجتماعات", icon: <CalendarClock className="w-4 h-4" /> },
];

export const PlatformOpsDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<DashboardTab>("overview");
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

  // ضبطُ مستهدفَي موظّف — الحقلان اللذان كانا يُعرضان ولا يُضبطان (210-ز).
  const [targetsModal, setTargetsModal] = useState<{ employeeId: number; employeeName: string } | null>(null);

  // ملفُّ الموظّف الـ360 (211-J) — يُفتح من نقرةٍ على وجهِه في البطاقة أو على مقعده في الغرفة.
  const [profileDrawer, setProfileDrawer] = useState<{ employeeId: number; employeeName: string; tab?: "general" | "tasks" } | null>(null);

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
  // سكّانُ الغرفة: كلُّ الموظّفين لا المفلترين — الغرفةُ لوحةُ حضورٍ لا نتيجةَ
  // بحث، وإخفاءُ زميلٍ لأنّ كلمةَ بحثٍ لا تطابقه يجعل «من يعمل الآن» كذبة.
  // وحالةُ الاجتماع (الأصفر) من `is_in_meeting` الذي تحسبه اللوحةُ خادميّاً من
  // دفتر حضور الاجتماعات (حضورٌ فعليّ الآن، لا دعوة) — لا اشتقاقَ محلّيّاً.
  const roomOccupants = useMemo<RoomOccupant[]>(() => {
    const employees = data?.employees || [];
    const inMeeting = new Set<number>(
      employees.filter((employee) => employee.is_in_meeting).map((employee) => employee.id)
    );
    const rows = employees.map((employee) => ({
      id: employee.id,
      name: employee.name,
      // المسمّى قبل التخصّص: `specialty` مفتاحُ سياسةِ تقييمٍ لا عنوانُ عرض،
      // وقراءتُه على وجه الموظّف تُظهر مفتاحاً تقنيّاً مكان وظيفته.
      role: employee.job_title || employee.specialty || "",
      photoUrl: employee.photo_url || undefined,
      presence: derivePresence(employee, inMeeting, employee.id),
      lastActiveLabel: formatLastActive(employee.last_active_at),
      // مجموعُ اليوم على المقعد نفسِه (212-N2): الضوءُ يقول «الآن» وهذا يقول
      // «كم قعد اليوم» — والحمولةُ تحملهما معاً فلا نداءَ جديد.
      presenceSeconds: employee.presence_seconds_today,
      presenceTargetHours: employee.presence_target_hours,
    }));
    return sortByPresence(rows);
  }, [data?.employees]);

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
    <div
      className="platform-surface ops-shell min-h-screen bg-cc-bg text-cc-text p-4 sm:p-6 lg:p-8 pb-24 md:pb-6 lg:pb-8"
      dir="rtl"
    >
      {/* 1. ترويسة الصفحة كاللوحة 1 */}
      <header className="flex flex-wrap items-center justify-between gap-4 pb-6 mb-6 border-b border-cc-border">
        <div className="flex flex-col">
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl sm:text-2xl font-black text-cc-text tracking-tight">
              مركز قيادة شؤون الموظفين والمهام
            </h1>
            <CcPill tone="accent">المرحلة السادسة</CcPill>
          </div>
          <p className="text-xs text-cc-text-muted mt-1">
            اللوحة التفاعلية، شريط التدخل السريع، والتنقيب المعزول عابراً للشركات.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() =>
              setActivityModal({
                isOpen: true,
                employeeId: null,
                employeeName: null,
              })
            }
            className="px-3.5 py-2 text-xs font-semibold text-cc-text bg-cc-surface hover:bg-cc-surface-2 border border-cc-border rounded-xl transition shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            سجل النشاط العابر
          </button>

          <button
            type="button"
            onClick={loadDashboard}
            className="p-2 text-cc-text-muted hover:text-cc-text bg-cc-surface hover:bg-cc-surface-2 rounded-full border border-cc-border transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            title="تحديث البيانات"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          {/* جرس الإشعارات المنصية */}
          <PlatformNotificationBell />
        </div>
      </header>

      {/* تبويبات لوحة عمليات المنصة بـ CcTabs */}
      <div className="hidden md:block w-full mb-6">
        <CcTabs
          tabs={DASHBOARD_TABS}
          active={activeTab}
          onChange={(key) => setActiveTab(key as DashboardTab)}
        />
      </div>

      {/* شريطُ التنقّل السفليُّ العائم — بديلُ صفِّ التبويبات في العرض الضيّق وحدَه */}
      <nav
        dir="rtl"
        className="md:hidden fixed bottom-0 inset-x-0 z-30 flex items-stretch justify-around bg-cc-surface border-t border-cc-border shadow-cc-card"
      >
        <button
          type="button"
          onClick={() => setActiveTab("overview")}
          aria-label="نظرة عامّة"
          className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-[11px] font-bold transition ${
            activeTab === "overview" ? "text-sky-400" : "text-cc-text-muted"
          }`}
        >
          <LayoutDashboard className="w-5 h-5" />
          نظرة عامّة
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("work_orders")}
          aria-label="أوامر العمل"
          className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-[11px] font-bold transition ${
            activeTab === "work_orders" ? "text-sky-400" : "text-cc-text-muted"
          }`}
        >
          <ClipboardList className="w-5 h-5" />
          أوامر العمل
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("workspace_room")}
          aria-label="مساحة العمل"
          className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-[11px] font-bold transition ${
            activeTab === "workspace_room" ? "text-sky-400" : "text-cc-text-muted"
          }`}
        >
          <DoorOpen className="w-5 h-5" />
          مساحة العمل
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("meetings")}
          aria-label="الاجتماعات"
          className={`flex-1 flex flex-col items-center gap-0.5 py-2 text-[11px] font-bold transition ${
            activeTab === "meetings" ? "text-sky-400" : "text-cc-text-muted"
          }`}
        >
          <CalendarClock className="w-5 h-5" />
          الاجتماعات
        </button>
      </nav>

      {activeTab === "work_orders" && <WorkOrdersPanel />}
      {activeTab === "staff_tasks" && <PlatformTasksAdminPanel />}
      {activeTab === "catalog" && <ServiceUnitCatalogPanel />}
      {activeTab === "usage_ledger" && <ServiceUsageLedgerPanel />}
      {activeTab === "pilot_settings" && <PilotSettingsPanel />}
      {activeTab === "compensation_close" && <CompensationMonthClosePanel />}
      {activeTab === "wallet" && <EmployeeWalletPanel />}
      {activeTab === "integration_keys" && <IntegrationKeysPanel />}
      {activeTab === "champions" && <ChampionsPanel />}
      {activeTab === "profitability" && <ProfitabilityPanel />}
      {activeTab === "review_requests" && <PerformanceReviewRequestsPanel />}
      {activeTab === "meetings" && <MeetingsPanel />}
      {/* لا يصل إلى مركز القيادة إلا السوبر أدمن (`IsPlatformAdmin`)، لذلك `true` صحيح هنا.
          وليس لكل سوبر أدمن صفّ PlatformEmployee؛ `null` يمنع ادعاء ملكية عميل من دليل الزملاء. */}
      {activeTab === "crm" && <CrmPanel isManager={true} myEmployeeId={null} />}

      {activeTab === "workspace_room" && (
        <div className="bg-cc-surface rounded-xl border border-cc-border p-4 sm:p-6 shadow-sm">
          <WorkspaceRoom
            occupants={roomOccupants}
            screenTitle={`${countPresent(roomOccupants)} على المنصّة الآن`}
            screenSubtitle="مساحة عمل كترا"
            onSelectEmployee={(employeeId) => {
              const employee = roomOccupants.find((o) => o.id === employeeId);
              if (employee) {
                setProfileDrawer({ employeeId, employeeName: employee.name });
              }
            }}
          />
        </div>
      )}

      {activeTab === "overview" && (
        <>
          {/* شريطُ الأرقام العلويّ وملخّصُ أداء الفريق — كلُّ رقمٍ فيهما من
              حمولة اللوحة نفسِها (`data`)، لا رقمَ مخترَعاً ولا مالياً.

              **ولا يُرسَمان قبل وصول الحمولة**: صفرٌ بخطٍّ عريضٍ أثناء التحميل
              أو بعد فشلِه يُقرأ «لا أمرَ عملٍ متأخّراً» — وهو خبرٌ لم يقله أحد.
              الغيابُ أصدقُ من رقمٍ لم يُحسَب بعد. */}
          {data && (
            <>
              <DashboardHeroStrip
                employees={data.employees || []}
                presentCount={countPresent(roomOccupants)}
                totalCount={roomOccupants.length}
              />
              <TeamTargetBars employees={data.employees || []} />
            </>
          )}

      {/* خطأ التحميل إن وجد */}
      {error && (
        <div className="mb-6 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-sm text-rose-400 flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={loadDashboard}
            className="px-3 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 rounded-lg font-bold text-xs transition focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
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
      <div className="bg-cc-surface p-4 rounded-xl border border-cc-border mb-6 flex flex-wrap items-center justify-between gap-4 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-cc-text-muted">وحدة العرض:</span>
          <div className="inline-flex rounded-lg border border-cc-border bg-cc-surface-2 p-1">
            <button
              type="button"
              onClick={() => setViewUnit("employee")}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${
                viewUnit === "employee"
                  ? "bg-sky-500 text-white shadow-sm"
                  : "text-cc-text-muted hover:text-cc-text"
              }`}
            >
              عرض حسب الموظف ({data?.employees?.length || 0})
            </button>
            <button
              type="button"
              onClick={() => setViewUnit("company")}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 ${
                viewUnit === "company"
                  ? "bg-sky-500 text-white shadow-sm"
                  : "text-cc-text-muted hover:text-cc-text"
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
              className="w-full px-3 py-1.5 text-xs bg-cc-surface-2 border border-cc-border rounded-lg text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>

          {viewUnit === "employee" && specialties.length > 0 && (
            <select
              value={specialtyFilter}
              onChange={(e) => setSpecialtyFilter(e.target.value)}
              className="px-3 py-1.5 text-xs bg-cc-surface-2 text-cc-text border border-cc-border rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <option value="">كافة التخصصات</option>
              {specialties.map((spec) => (
                <option key={spec} value={spec}>
                  {spec}
                </option>
              ))}
            </select>
          )}

          <span className="text-xs text-cc-text-muted font-medium">
            الفرز: الأسوأ أولاً (تلقائي)
          </span>
        </div>
      </div>

      {/* 4. شبكة البطاقات */}
      <main>
        {loading ? (
          <div className="py-24 text-center text-sm text-cc-text-muted">
            جاري تحميل لوحة العمليات...
          </div>
        ) : viewUnit === "employee" ? (
          <>
          {/* 212-Q4: بابُ ضمِّ مستخدمٍ قائمٍ إلى الفريق — فوق الشبكة لا داخلَها،
              وقبل شرط «لا يوجد موظفون» عمداً: أوّلُ من يحتاجه فريقٌ فارغ. */}
          <PromoteEmployeePanel onPromoted={() => void loadDashboard()} />
          {filteredEmployees.length === 0 ? (
            <div className="py-24 text-center text-sm text-cc-text-muted bg-cc-surface rounded-xl border border-cc-border">
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
                  onEditTargets={(id, name) => setTargetsModal({ employeeId: id, employeeName: name })}
                  onOpenProfile={(id) => setProfileDrawer({ employeeId: id, employeeName: emp.name })}
                  onOpenTasks={(id) => setProfileDrawer({ employeeId: id, employeeName: emp.name, tab: "tasks" })}
                />
              ))}
            </div>
          )}
          </>
        ) : filteredCompanies.length === 0 ? (
          <div className="py-24 text-center text-sm text-cc-text-muted bg-cc-surface rounded-xl border border-cc-border">
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

      {targetsModal && (
        <EmployeeTargetsModal
          employeeId={targetsModal.employeeId}
          employeeName={targetsModal.employeeName}
          onClose={() => setTargetsModal(null)}
          onSaved={() => void loadDashboard()}
        />
      )}
        </>
      )}

      {profileDrawer && (
        <EmployeeProfileDrawer
          employeeId={profileDrawer.employeeId}
          employeeName={profileDrawer.employeeName}
          initialTab={profileDrawer.tab}
          onClose={() => setProfileDrawer(null)}
          onSaved={() => void loadDashboard()}
        />
      )}
    </div>
  );
};

export default PlatformOpsDashboard;
