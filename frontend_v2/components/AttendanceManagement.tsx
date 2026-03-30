// components/AttendanceManagement.tsx
import React, { useState, useEffect } from "react";
import { User, AttendanceSession, AttendanceRecord } from "../types";
import { attendanceService } from "../services/attendanceService";
import { format, isToday, parseISO } from "date-fns";
import { ar } from "date-fns/locale";

interface AttendanceManagementProps {
  users: User[];
  currentUser: User;
}

export const AttendanceManagement: React.FC<AttendanceManagementProps> = ({
  users,
  currentUser,
}) => {
  const [activeSession, setActiveSession] = useState<AttendanceSession | null>(
    null
  );
  const [selectedDate, setSelectedDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [attendanceRecords, setAttendanceRecords] = useState<
    AttendanceRecord[]
  >([]);
  const [loading, setLoading] = useState(false);
  const [timeLeft, setTimeLeft] = useState<number>(0);

  // 1. **إضافة حالتين جديدتين للبحث والفلترة**
  const [searchTerm, setSearchTerm] = useState("");
  const [attendanceFilter, setAttendanceFilter] = useState<
    "all" | "present" | "absent"
  >("all");

  const employees = users.filter((user) => (user.role === "employee" || user.role == "procurement"));

  useEffect(() => {
    loadActiveSession();
    loadAttendanceRecords();
  }, [selectedDate]);

  useEffect(() => {
    let interval: NodeJS.Timeout;

    if (activeSession) {
      const startTime = new Date(activeSession.startTime).getTime();
      const endTime = startTime + 5 * 60 * 1000; // 5 دقائق

      interval = setInterval(() => {
        const now = Date.now();
        const remaining = Math.max(0, endTime - now);
        setTimeLeft(Math.ceil(remaining / 1000));

        if (remaining === 0) {
          loadActiveSession();
        }
      }, 1000);
    }

    return () => clearInterval(interval);
  }, [activeSession]);

  const loadActiveSession = async () => {
    try {
      const session = await attendanceService.getActiveSession();
      setActiveSession(session);
    } catch (error) {
      console.error("Error loading active session:", error);
    }
  };

  const loadAttendanceRecords = async () => {
    setLoading(true);
    try {
      const records = await attendanceService.getAttendanceRecords(
        selectedDate
      );
      setAttendanceRecords(records);
    } catch (error) {
      console.error("Error loading attendance records:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleStartSession = async () => {
    try {
      setLoading(true);
      await attendanceService.startAttendanceSession(currentUser.id);
      await loadActiveSession();
    } catch (error) {
      console.error("Error starting session:", error);
      alert("حدث خطأ أثناء بدء جلسة الحضور");
    } finally {
      setLoading(false);
    }
  };

  const handleEndSession = async () => {
    if (!activeSession) return;

    try {
      setLoading(true);
      await attendanceService.endAttendanceSession(activeSession.id);
      setActiveSession(null);
      setTimeLeft(0);
    } catch (error) {
      console.error("Error ending session:", error);
      alert("حدث خطأ أثناء إنهاء جلسة الحضور");
    } finally {
      setLoading(false);
    }
  };

  const handleManualAttendance = async (userId: string, attended: boolean) => {
    try {
      setLoading(true);

      console.log("تعديل الحضور يدوياً:", { userId, selectedDate, attended });

      // استخدام الدالة المحدثة التي تتعامل مع النقاط تلقائياً
      await attendanceService.updateAttendanceManually(
        userId,
        selectedDate,
        attended
      );

      // إعادة تحميل البيانات
      await loadAttendanceRecords();

      const message = attended
        ? "تم تسجيل الحضور بنجاح! +10 نقاط ✅"
        : "تم إلغاء الحضور بنجاح! -10 نقاط ❌";

      alert(message);
    } catch (error) {
      console.error("Error updating attendance:", error);
      alert("حدث خطأ أثناء تعديل الحضور");
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
  };

  const getEmployeeAttendance = (userId: string) => {
    return attendanceRecords.find((record) => record.userId === userId);
  };

  const formatArabicDate = (dateStr: string) => {
    const date = parseISO(dateStr);
    return format(date, "EEEE، d MMMM yyyy", { locale: ar });
  };

  // 2. **تنفيذ منطق البحث والفلترة**
  const filteredEmployees = employees.filter((employee) => {
    // 1. البحث بالاسم (غير حساس لحالة الأحرف)
    const matchesSearch = employee.name
      .toLowerCase()
      .includes(searchTerm.toLowerCase());

    if (!matchesSearch) {
      return false;
    }

    // 2. الفلترة حسب حالة الحضور
    const attendance = getEmployeeAttendance(employee.id);
    const hasAttended = !!attendance;

    if (attendanceFilter === "present") {
      return hasAttended;
    }

    if (attendanceFilter === "absent") {
      return !hasAttended;
    }

    // "all" أو أي حالة أخرى
    return true;
  });

  return (
    <div className="animate-fade-in">
      <h1 className="text-3xl font-bold mb-6 text-gray-800 dark:text-gray-100">
        إدارة الحضور والغياب
      </h1>

      {/* جلسة الحضور النشطة */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700 mb-6">
        <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
          <div>
            <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-2">
              جلسة الحضور
            </h3>
            <p className="text-gray-600 dark:text-gray-400">
              {activeSession
                ? `جلسة نشطة - متبقي ${formatTime(timeLeft)}`
                : "لا توجد جلسة نشطة حالياً"}
            </p>
          </div>

          <div className="flex gap-3">
            {!activeSession ? (
              <button
                onClick={handleStartSession}
                disabled={loading}
                className="bg-green-500 hover:bg-green-600 text-white px-6 py-3 rounded-lg font-semibold transition-colors disabled:opacity-50"
              >
                بدء جلسة حضور جديدة
              </button>
            ) : (
              <button
                onClick={handleEndSession}
                disabled={loading}
                className="bg-red-500 hover:bg-red-600 text-white px-6 py-3 rounded-lg font-semibold transition-colors disabled:opacity-50"
              >
                إنهاء الجلسة
              </button>
            )}
          </div>
        </div>

        {activeSession && (
          <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900/50 rounded-lg border border-blue-200 dark:border-blue-700">
            <div className="flex flex-wrap gap-4 text-sm">
              <div>
                <span className="font-semibold text-blue-800 dark:text-blue-200">
                  بدأت في:
                </span>
                <span className="mr-2 text-blue-600 dark:text-blue-300">
                  {new Date(activeSession.startTime).toLocaleTimeString(
                    "ar-EG"
                  )}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 3. **تحديث قسم الفلترة ليشمل التاريخ والبحث والحالة** */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border border-gray-200 dark:border-gray-700 mb-6">
        <div className="flex flex-col gap-4">
          <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100">
            تقرير الحضور ليوم {formatArabicDate(selectedDate)}
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* فلترة التاريخ */}
            <div className="flex flex-col gap-1">
              <label
                htmlFor="date-input"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                اختر التاريخ:
              </label>
              <input
                id="date-input"
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
              />
            </div>

            {/* فلترة حسب الحالة */}
            <div className="flex flex-col gap-1">
              <label
                htmlFor="attendance-filter"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                فلترة حسب الحالة:
              </label>
              <select
                id="attendance-filter"
                value={attendanceFilter}
                onChange={(e) =>
                  setAttendanceFilter(
                    e.target.value as "all" | "present" | "absent"
                  )
                }
                className="p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white appearance-none"
              >
                <option value="all">الكل</option>
                <option value="present">حاضر</option>
                <option value="absent">غائب</option>
              </select>
            </div>

            {/* البحث باسم الموظف */}
            <div className="flex flex-col gap-1">
              <label
                htmlFor="search-term"
                className="text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                البحث باسم الموظف:
              </label>
              <input
                id="search-term"
                type="text"
                placeholder="ابحث بالاسم..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 dark:text-white"
              />
            </div>
          </div>
        </div>
      </div>

      {/* جدول الموظفين */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-right">
            <thead className="bg-gray-50 dark:bg-gray-700/50">
              <tr>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  الموظف
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  البريد الإلكتروني
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  حالة الحضور
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  وقت التسجيل
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  النقاط
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  الإجراءات
                </th>
              </tr>
            </thead>
            {/* 4. **استخدام قائمة الموظفين المفلترة** */}
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {filteredEmployees.map((employee) => {
                const attendance = getEmployeeAttendance(employee.id);
                const hasAttended = !!attendance;

                return (
                  <tr
                    key={employee.id}
                    className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                  >
                    <td className="p-4 font-medium text-gray-800 dark:text-gray-100">
                      {employee.name}
                    </td>
                    <td className="p-4 text-gray-600 dark:text-gray-300">
                      {employee.email}
                    </td>
                    <td className="p-4">
                      <span
                        className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${
                          hasAttended
                            ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300"
                            : "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300"
                        }`}
                      >
                        {hasAttended ? "حاضر" : "غائب"}
                      </span>
                    </td>
                    <td className="p-4 text-gray-600 dark:text-gray-300">
                      {attendance
                        ? new Date(attendance.attendedAt).toLocaleTimeString(
                            "ar-EG"
                          )
                        : "-"}
                    </td>
                    <td className="p-4">
                      <span
                        className={`font-bold ${
                          hasAttended
                            ? "text-green-600 dark:text-green-400"
                            : "text-gray-400"
                        }`}
                      >
                        {hasAttended ? "+10" : "0"}
                      </span>
                    </td>
                    <td className="p-4">
                      <div className="flex gap-2">
                        {!hasAttended ? (
                          <button
                            onClick={() =>
                              handleManualAttendance(employee.id, true)
                            }
                            disabled={loading}
                            className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-sm font-semibold transition-colors disabled:opacity-50"
                          >
                            {loading ? "جاري..." : "تسجيل حضور (+10)"}
                          </button>
                        ) : (
                          <button
                            onClick={() =>
                              handleManualAttendance(employee.id, false)
                            }
                            disabled={loading}
                            className="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded text-sm font-semibold transition-colors disabled:opacity-50"
                          >
                            {loading ? "جاري..." : "إلغاء حضور (-10)"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};