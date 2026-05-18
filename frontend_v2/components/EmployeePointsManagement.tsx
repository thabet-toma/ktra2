// components/EmployeePointsManagement.tsx
import React, { useState, useEffect } from "react";
import { User, DailyPoints, ActivityStatus } from "../types";
import {
  pointsHistoryService,
  activityService,
} from "../services/firestoreService";
import { autoDisableScheduler } from "../services/autoDisableScheduler";

interface EmployeePointsManagementProps {
  users: User[];
}

// ... تعريف الواجهات UserStats و DailyUserPoints كما هي ...
interface UserStats {
  [userId: string]: {
    totalPoints: number;
    totalActivityPoints: number;
    totalTaskPoints: number;
  };
}

interface DailyUserPoints {
  userId: string;
  userName: string;
  dailyPoints: DailyPoints | null;
}

// تعريف واجهة لإعدادات التعطيل اليومي (عامة للنظام)
interface DailyDisableSettings {
  startTime: string; // مثال: "08:00"
  endTime: string; // مثال: "17:00"
  isEnabled: boolean; // لتمكين/تعطيل الخاصية ككل
}

export const EmployeePointsManagement: React.FC<
  EmployeePointsManagementProps
> = ({ users }) => {
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [userPoints, setUserPoints] = useState<DailyPoints[]>([]);
  const [userActivity, setUserActivity] = useState<ActivityStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedDate, setSelectedDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [manualPoints, setManualPoints] = useState({
    activityPoints: 0,
    taskPoints: 0,
  });
  const [showAdjustModal, setShowAdjustModal] = useState(false);
  const [userStats, setUserStats] = useState<UserStats>({});

  // الحقول الجديدة للفلترة والترتيب
  const [viewMode, setViewMode] = useState<"user" | "daily">("user");
  const [dailyUsersPoints, setDailyUsersPoints] = useState<DailyUserPoints[]>(
    []
  );
  const [sortBy, setSortBy] = useState<"points" | "name">("points");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  // ** 1. إضافة حالة جديدة لعرض مودال الإعدادات العامة **
  const [showGlobalSettingsModal, setShowGlobalSettingsModal] = useState(false);

  // ** 2. حالة لإعدادات التعطيل اليومي العامة **
  const [globalDailyDisableSettings, setGlobalDailyDisableSettings] =
    useState<DailyDisableSettings>({
      startTime: "00:00",
      endTime: "00:00",
      isEnabled: false,
    });

  const employees = users.filter((user) => user.role === "employee");


  

  useEffect(() => {
    loadAllUsersStats();
    // تحميل الإعدادات العامة عند تحميل المكون
    loadGlobalSettings();
  }, [users]);

  // تحميل بيانات الموظف المحدد عند التغيير
  useEffect(() => {
    if (selectedUser && viewMode === "user") {
      loadUserData();
    }
  }, [selectedUser, selectedDate, viewMode]);

  // تحميل بيانات جميع الموظفين ليوم محدد
  useEffect(() => {
    if (viewMode === "daily") {
      loadDailyUsersData();
    }
  }, [selectedDate, viewMode, employees]);

  // ** دالة جديدة: تحميل إعدادات التعطيل اليومي العامة **
  const loadGlobalSettings = async () => {
    try {
      // افتراض وجود دالة عامة لجلب الإعدادات
      const settings = await activityService.getGlobalDailyDisableSchedule();
      if (settings) {
        setGlobalDailyDisableSettings(settings);
      }
    } catch (error) {
      console.error("Error loading global disable settings:", error);
    }
  };

  const loadAllUsersStats = async () => {
    // ... (منطق تحميل الإحصائيات كما هو) ...
    const stats: UserStats = {};

    for (const user of employees) {
      try {
        const endDate = new Date().toISOString().split("T")[0];
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - 30);
        const startDateStr = startDate.toISOString().split("T")[0];

        const history = await pointsHistoryService.getPointsHistory(
          user.id,
          startDateStr,
          endDate
        );

        stats[user.id] = {
          totalPoints: history.reduce((sum, day) => sum + day.totalPoints, 0),
          totalActivityPoints: history.reduce(
            (sum, day) => sum + day.activityPoints,
            0
          ),
          totalTaskPoints: history.reduce(
            (sum, day) => sum + day.taskPoints,
            0
          ),
        };
      } catch (error) {
        console.error(`Error loading stats for user ${user.name}:`, error);
        stats[user.id] = {
          totalPoints: 0,
          totalActivityPoints: 0,
          totalTaskPoints: 0,
        };
      }
    }

    setUserStats(stats);
  };

  const loadUserData = async () => {
    if (!selectedUser) return;

    setLoading(true);
    try {
      // تحميل تاريخ النقاط للشهر الحالي (كما هو)
      const endDate = new Date().toISOString().split("T")[0];
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - 30);
      const startDateStr = startDate.toISOString().split("T")[0];

      const history = await pointsHistoryService.getPointsHistory(
        selectedUser.id,
        startDateStr,
        endDate
      );
      setUserPoints(history.sort((a, b) => b.date.localeCompare(a.date)));

      // تحميل حالة النشاط (كما هو)
      const activity = await activityService.getActivityStatus(selectedUser.id);
      setUserActivity(activity);

      // ** إزالة: لم نعد نحمل إعدادات التعطيل اليومي من النشاط الفردي **

      // تحميل نقاط اليوم المحدد (كما هو)
      const dailyPoints = await pointsHistoryService.getDailyPoints(
        selectedUser.id,
        selectedDate
      );
      setManualPoints({
        activityPoints: dailyPoints?.activityPoints || 0,
        taskPoints: dailyPoints?.taskPoints || 0,
      });
    } catch (error) {
      console.error("Error loading user data:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadDailyUsersData = async () => {
    // ... (منطق تحميل بيانات جميع المستخدمين كما هو) ...
    setLoading(true);
    try {
      const dailyData: DailyUserPoints[] = [];

      for (const user of employees) {
        try {
          const dailyPoints = await pointsHistoryService.getDailyPoints(
            user.id,
            selectedDate
          );
          dailyData.push({
            userId: user.id,
            userName: user.name,
            dailyPoints: dailyPoints,
          });
        } catch (error) {
          console.error(
            `Error loading daily points for user ${user.name}:`,
            error
          );
          dailyData.push({
            userId: user.id,
            userName: user.name,
            dailyPoints: null,
          });
        }
      }

      setDailyUsersPoints(dailyData);
    } catch (error) {
      console.error("Error loading daily users data:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleAdjustPoints = async () => {
    // ... (منطق تعديل النقاط كما هو) ...
    if (!selectedUser) return;

    try {
      // ... (منطق حفظ النقاط)
      await pointsHistoryService.updatePointsManually(
        selectedUser.id,
        selectedDate,
        manualPoints
      );
      setShowAdjustModal(false);
      loadUserData();
      if (viewMode === "daily") {
        loadDailyUsersData();
      }
    } catch (error) {
      console.error("Error adjusting points:", error);
      alert("حدث خطأ أثناء تعديل النقاط");
    }
  };

  const handleToggleCheckInButton = async (enabled: boolean) => {
    // ... (منطق تفعيل/تعطيل زر التأكيد كما هو) ...
    if (!selectedUser) return;

    try {
      await activityService.toggleCheckInButton(selectedUser.id, enabled);
      setUserActivity((prev) =>
        prev ? { ...prev, checkInButtonEnabled: enabled } : null
      );
      alert(`تم ${enabled ? "تفعيل" : "تعطيل"} زر التأكيد للموظف`);
    } catch (error) {
      console.error("Error toggling check-in button:", error);
      alert("حدث خطأ أثناء تعديل إعدادات الزر");
    }
  };

  // ** دالة جديدة: معالجة حفظ إعدادات التعطيل اليومي العامة **
  const handleSaveGlobalDailyDisableSettings = async () => {
    try {
      // ** افتراض وجود دالة `setGlobalDailyDisableSchedule` عامة في `activityService` **
      await activityService.setGlobalDailyDisableSchedule(
        globalDailyDisableSettings.startTime,
        globalDailyDisableSettings.endTime,
        globalDailyDisableSettings.isEnabled
      );
      setShowGlobalSettingsModal(false);
      // تحديث الإعدادات في الواجهة
      await loadGlobalSettings();
      alert("تم حفظ إعدادات التعطيل اليومي العامة بنجاح");
    } catch (error) {
      console.error("Error saving global daily disable settings:", error);
      alert("حدث خطأ أثناء حفظ الإعدادات");
    }
  };

  const getTotalStats = (userId: string) => {
    // ... (منطق الإحصائيات كما هو) ...
    return (
      userStats[userId] || {
        totalPoints: 0,
        totalActivityPoints: 0,
        totalTaskPoints: 0,
      }
    );
  };

  const formatDate = (dateStr: string) => {
    // ... (منطق تنسيق التاريخ كما هو) ...
    const date = new Date(dateStr);
    return date.toLocaleDateString("ar-SA", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      calendar: "gregory",
    });
  };

  // فرز بيانات الموظفين حسب اليوم
  const getSortedDailyUsers = () => {
    // ... (منطق الفرز كما هو) ...
    const sorted = [...dailyUsersPoints].sort((a, b) => {
      const pointsA = a.dailyPoints?.totalPoints || 0;
      const pointsB = b.dailyPoints?.totalPoints || 0;

      if (sortBy === "points") {
        return sortOrder === "desc" ? pointsB - pointsA : pointsA - pointsB;
      } else {
        return sortOrder === "desc"
          ? b.userName.localeCompare(a.userName)
          : a.userName.localeCompare(b.userName);
      }
    });

    return sorted;
  };

  const sortedDailyUsers = getSortedDailyUsers();

  return (
    <div className="animate-fade-in">
      <h1 className="text-3xl font-bold mb-6 text-gray-800 dark:text-gray-100">
        إدارة نقاط الموظفين
      </h1>

      {/* ** لوحة الإعدادات العامة الجديدة ** */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700 mb-6">
        <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-2">
              إعدادات النشاط العامة
            </h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              تعطيل زر النشاط اليومي:
              <span
                className={`font-semibold mr-1 ${
                  globalDailyDisableSettings.isEnabled
                    ? "text-red-600 dark:text-red-400"
                    : "text-green-600 dark:text-green-400"
                }`}
              >
                {globalDailyDisableSettings.isEnabled
                  ? `مفعل من ${globalDailyDisableSettings.startTime} إلى ${globalDailyDisableSettings.endTime}`
                  : "معطل"}
              </span>
            </p>
          </div>
          <button
            onClick={() => setShowGlobalSettingsModal(true)}
            className="bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white px-6 py-3 rounded-lg font-semibold transition-colors disabled:opacity-50"
          >
            تعديل الإعدادات العامة
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700 mb-6">
        <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-2">
              مراقبة نظام التعطيل التلقائي
            </h3>
            <p className="text-gray-600 dark:text-gray-400 text-sm">
              حالة المجدول:
              <span
                className={`font-semibold mr-1 ${
                  autoDisableScheduler.getStatus().isRunning
                    ? "text-green-600 dark:text-green-400"
                    : "text-red-600 dark:text-red-400"
                }`}
              >
                {autoDisableScheduler.getStatus().isRunning
                  ? "🟢 نشط"
                  : "🔴 متوقف"}
              </span>
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={async () => {
                await autoDisableScheduler.manualCheck();
                alert("تم التحقق يدوياً من الإعدادات العامة");
              }}
              className="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded-lg font-semibold transition-colors"
            >
              تحقق الآن
            </button>
            <button
              onClick={() => {
                if (autoDisableScheduler.getStatus().isRunning) {
                  autoDisableScheduler.stop();
                } else {
                  autoDisableScheduler.start();
                }
              }}
              className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                autoDisableScheduler.getStatus().isRunning
                  ? "bg-red-500 hover:bg-red-600 text-white"
                  : "bg-blue-500 hover:bg-blue-600 text-white"
              }`}
            >
              {autoDisableScheduler.getStatus().isRunning
                ? "إيقاف المجدول"
                : "تشغيل المجدول"}
            </button>
          </div>
        </div>
      </div>
      {/* ------------------------------------- */}

      {/* اختيار وضع العرض (كما هو) */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700 mb-6">
        <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
          <div className="flex gap-3">
            <button
              onClick={() => setViewMode("user")}
              className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                viewMode === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
              }`}
            >
              عرض موظف محدد
            </button>
            <button
              onClick={() => setViewMode("daily")}
              className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                viewMode === "daily"
                  ? "bg-blue-500 text-white"
                  : "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
              }`}
            >
              عرض جميع الموظفين ليوم محدد
            </button>
          </div>

          <div className="flex gap-3 items-center">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              التاريخ:
            </label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
            />
          </div>
        </div>
      </div>

      {viewMode === "user" ? (
        <>
          {/* اختيار الموظف (كما هو) */}
          <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700 mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              اختر الموظف:
            </label>
            <select
              value={selectedUser?.id || ""}
              onChange={(e) =>
                setSelectedUser(
                  users.find((u) => u.id === e.target.value) || null
                )
              }
              className="w-full max-w-md p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
            >
              <option value="">اختر موظف...</option>
              {employees.map((user) => {
                const stats = getTotalStats(user.id);
                return (
                  <option key={user.id} value={user.id}>
                    {user.name} - {stats.totalPoints} نقطة
                  </option>
                );
              })}
            </select>
          </div>

          {selectedUser && (
            <>
              {/* معلومات الموظف والإحصائيات (تحديث: إزالة حقل التعطيل اليومي الفردي) */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700">
                  <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-4">
                    معلومات الموظف
                  </h3>
                  <div className="space-y-2">
                    {/* ... (الاسم والبريد وحالة النشاط) ... */}
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-gray-400">
                        الاسم:
                      </span>
                      <span className="font-semibold">{selectedUser.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-gray-400">
                        البريد:
                      </span>
                      <span className="font-semibold">
                        {selectedUser.email}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-gray-400">
                        حالة النشاط:
                      </span>
                      <span
                        className={`font-semibold ${
                          userActivity?.isCurrentlyActive
                            ? "text-green-600"
                            : "text-red-600"
                        }`}
                      >
                        {userActivity?.isCurrentlyActive ? "نشط" : "غير نشط"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-600 dark:text-gray-400">
                        زر التأكيد:
                      </span>
                      <span
                        className={`font-semibold ${
                          userActivity?.checkInButtonEnabled !== false
                            ? "text-green-600"
                            : "text-red-600"
                        }`}
                      >
                        {userActivity?.checkInButtonEnabled !== false
                          ? "مفعل"
                          : "معطل"}
                      </span>
                    </div>
                    {/* ** إزالة: حقل عرض حالة التعطيل اليومي الفردي ** */}
                    {/* ------------------------------- */}
                  </div>
                </div>

                {/* الإحصائيات الإجمالية (كما هو) */}
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700">
                  {/* ... (محتوى الإحصائيات الإجمالية كما هو) ... */}
                  <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-4">
                    الإحصائيات الإجمالية (30 يوم)
                  </h3>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600 dark:text-gray-400">
                        إجمالي النقاط:
                      </span>
                      <span className="text-xl font-bold text-blue-600 dark:text-blue-400">
                        {getTotalStats(selectedUser.id).totalPoints}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600 dark:text-gray-400">
                        نقاط النشاط:
                      </span>
                      <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                        {getTotalStats(selectedUser.id).totalActivityPoints}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-600 dark:text-gray-400">
                        نقاط المهام:
                      </span>
                      <span className="text-lg font-semibold text-[var(--color-primary)] dark:text-[var(--color-primary)]">
                        {getTotalStats(selectedUser.id).totalTaskPoints}
                      </span>
                    </div>
                  </div>
                </div>

                {/* أدوات التحكم (تحديث: إزالة زر إعداد التعطيل اليومي) */}
                <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700">
                  <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-4">
                    أدوات التحكم
                  </h3>
                  <div className="space-y-3">
                    <button
                      onClick={() => setShowAdjustModal(true)}
                      className="w-full bg-blue-500 hover:bg-blue-600 text-white py-2 px-4 rounded-lg transition-colors font-semibold"
                    >
                      تعديل النقاط يدوياً
                    </button>

                    {/* ** إزالة زر إعداد التعطيل اليومي الفردي ** */}

                    {userActivity?.checkInButtonEnabled !== false ? (
                      <button
                        onClick={() => handleToggleCheckInButton(false)}
                        className="w-full bg-yellow-500 hover:bg-yellow-600 text-white py-2 px-4 rounded-lg transition-colors font-semibold"
                      >
                        تعطيل زر التأكيد
                      </button>
                    ) : (
                      <button
                        onClick={() => handleToggleCheckInButton(true)}
                        className="w-full bg-green-500 hover:bg-green-600 text-white py-2 px-4 rounded-lg transition-colors font-semibold"
                      >
                        تفعيل زر التأكيد
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* جدول النقاط اليومية (كما هو) */}
              <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
                {/* ... (محتوى جدول النقاط اليومية كما هو) ... */}
                <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                  <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100">
                    النقاط اليومية (آخر 30 يوم)
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-right">
                    <thead className="bg-gray-50 dark:bg-gray-700/50">
                      <tr>
                        <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                          التاريخ
                        </th>
                        <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                          نقاط النشاط
                        </th>
                        <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                          ضغطات النشاط
                        </th>
                        <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                          نقاط المهام
                        </th>
                        <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                          مهام مكتملة
                        </th>
                        <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                          الإجمالي
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {userPoints.length === 0 ? (
                        <tr>
                          <td
                            colSpan={6}
                            className="p-8 text-center text-gray-500 dark:text-gray-400"
                          >
                            لا توجد بيانات للنقاط
                          </td>
                        </tr>
                      ) : (
                        userPoints.map((day) => (
                          <tr
                            key={day.date}
                            className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                          >
                            <td className="p-4 font-medium text-gray-800 dark:text-gray-100">
                              {formatDate(day.date)}
                            </td>
                            <td className="p-4 text-green-600 dark:text-green-400 font-bold">
                              {day.activityPoints}
                            </td>
                            <td className="p-4 text-gray-600 dark:text-gray-300">
                              {day.checkinClicks}
                            </td>
                            <td className="p-4 text-[var(--color-primary)] dark:text-[var(--color-primary)] font-bold">
                              {day.taskPoints}
                            </td>
                            <td className="p-4 text-gray-600 dark:text-gray-300">
                              {day.completedTasks}
                            </td>
                            <td className="p-4 text-blue-600 dark:text-blue-400 font-bold text-lg">
                              {day.totalPoints}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </>
      ) : (
        /* عرض جميع الموظفين ليوم محدد (كما هو) */
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
          {/* ... (محتوى عرض جميع الموظفين كما هو) ... */}
          <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex flex-col md:flex-row gap-4 justify-between items-start md:items-center">
            <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100">
              نقاط الموظفين ليوم {formatDate(selectedDate)}
            </h3>

            <div className="flex gap-3 items-center">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "points" | "name")}
                className="p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
              >
                <option value="points">ترتيب حسب النقاط</option>
                <option value="name">ترتيب حسب الاسم</option>
              </select>

              <select
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value as "asc" | "desc")}
                className="p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
              >
                <option value="desc">تنازلي</option>
                <option value="asc">تصاعدي</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-gray-50 dark:bg-gray-700/50">
                <tr>
                  <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                    الموظف
                  </th>
                  <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                    نقاط النشاط
                  </th>
                  <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                    ضغطات النشاط
                  </th>
                  <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                    نقاط المهام
                  </th>
                  <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                    مهام مكتملة
                  </th>
                  <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                    الإجمالي
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {sortedDailyUsers.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="p-8 text-center text-gray-500 dark:text-gray-400"
                    >
                      {loading
                        ? "جاري تحميل البيانات..."
                        : "لا توجد بيانات لهذا اليوم"}
                    </td>
                  </tr>
                ) : (
                  sortedDailyUsers.map((userData) => (
                    <tr
                      key={userData.userId}
                      className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                    >
                      <td className="p-4 font-medium text-gray-800 dark:text-gray-100">
                        {userData.userName}
                      </td>
                      <td className="p-4 text-green-600 dark:text-green-400 font-bold">
                        {userData.dailyPoints?.activityPoints || 0}
                      </td>
                      <td className="p-4 text-gray-600 dark:text-gray-300">
                        {userData.dailyPoints?.checkinClicks || 0}
                      </td>
                      <td className="p-4 text-[var(--color-primary)] dark:text-[var(--color-primary)] font-bold">
                        {userData.dailyPoints?.taskPoints || 0}
                      </td>
                      <td className="p-4 text-gray-600 dark:text-gray-300">
                        {userData.dailyPoints?.completedTasks || 0}
                      </td>
                      <td className="p-4 text-blue-600 dark:text-blue-400 font-bold text-lg">
                        {userData.dailyPoints?.totalPoints || 0}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* مودال تعديل النقاط (كما هو) */}
      {showAdjustModal && (
        // ... (محتوى مودال تعديل النقاط كما هو) ...
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 w-full max-w-md">
            <h3 className="text-xl font-bold text-gray-800 dark:text-gray-100 mb-4">
              تعديل النقاط لـ {selectedUser?.name}
            </h3>

            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  تاريخ التعديل:
                </label>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  نقاط النشاط:
                </label>
                <input
                  type="number"
                  value={manualPoints.activityPoints}
                  onChange={(e) =>
                    setManualPoints((prev) => ({
                      ...prev,
                      activityPoints: parseInt(e.target.value) || 0,
                    }))
                  }
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  نقاط المهام:
                </label>
                <input
                  type="number"
                  value={manualPoints.taskPoints}
                  onChange={(e) =>
                    setManualPoints((prev) => ({
                      ...prev,
                      taskPoints: parseInt(e.target.value) || 0,
                    }))
                  }
                  className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
                />
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowAdjustModal(false)}
                className="flex-1 bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-300 py-2 px-4 rounded-lg font-semibold hover:bg-gray-400 dark:hover:bg-gray-600 transition-colors"
              >
                إلغاء
              </button>
              <button
                onClick={handleAdjustPoints}
                className="flex-1 bg-blue-500 hover:bg-blue-600 text-white py-2 px-4 rounded-lg font-semibold transition-colors"
              >
                حفظ التعديلات
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ** 3. مودال إعداد التعطيل اليومي العام الجديد ** */}
      {showGlobalSettingsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 w-full max-w-md">
            <h3 className="text-xl font-bold text-gray-800 dark:text-gray-100 mb-4">
              إعداد التعطيل اليومي العام لزر النشاط
            </h3>

            <div className="space-y-4 mb-6">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                سيتم تطبيق هذا الإعداد على زر النشاط (Check-in) **لجميع
                الموظفين** بشكل يومي.
              </p>

              {/* تفعيل/تعطيل الخاصية */}
              <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  تفعيل التعطيل اليومي التلقائي:
                </label>
                <input
                  type="checkbox"
                  checked={globalDailyDisableSettings.isEnabled}
                  onChange={(e) =>
                    setGlobalDailyDisableSettings((prev) => ({
                      ...prev,
                      isEnabled: e.target.checked,
                    }))
                  }
                  className="h-5 w-5 text-[var(--color-primary)] rounded border-gray-300 focus:ring-[var(--color-primary)] dark:bg-gray-600 dark:border-gray-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* ساعة البدء */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    وقت بدء التعطيل:
                  </label>
                  <input
                    type="time"
                    value={globalDailyDisableSettings.startTime}
                    onChange={(e) =>
                      setGlobalDailyDisableSettings((prev) => ({
                        ...prev,
                        startTime: e.target.value,
                      }))
                    }
                    disabled={!globalDailyDisableSettings.isEnabled}
                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white disabled:opacity-50"
                  />
                </div>

                {/* ساعة الانتهاء */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    وقت إنهاء التعطيل:
                  </label>
                  <input
                    type="time"
                    value={globalDailyDisableSettings.endTime}
                    onChange={(e) =>
                      setGlobalDailyDisableSettings((prev) => ({
                        ...prev,
                        endTime: e.target.value,
                      }))
                    }
                    disabled={!globalDailyDisableSettings.isEnabled}
                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white disabled:opacity-50"
                  />
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowGlobalSettingsModal(false)}
                className="flex-1 bg-gray-300 dark:bg-gray-700 text-gray-700 dark:text-gray-300 py-2 px-4 rounded-lg font-semibold hover:bg-gray-400 dark:hover:bg-gray-600 transition-colors"
              >
                إلغاء
              </button>
              <button
                onClick={handleSaveGlobalDailyDisableSettings}
                disabled={
                  loading ||
                  (!globalDailyDisableSettings.isEnabled &&
                    globalDailyDisableSettings.startTime === "00:00" &&
                    globalDailyDisableSettings.endTime === "00:00")
                }
                className="flex-1 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white py-2 px-4 rounded-lg font-semibold transition-colors disabled:opacity-50"
              >
                {loading ? "جاري الحفظ..." : "حفظ الإعدادات"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
