import React, { useState, useEffect } from "react";

export const EmployeePointsManagement = ({ users = [] }) => {
  const [selectedUser, setSelectedUser] = useState(null);
  const [userPoints, setUserPoints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split("T")[0]);
  const [viewMode, setViewMode] = useState("user");
  const [dailyUsersPoints, setDailyUsersPoints] = useState([]);
  const [sortBy, setSortBy] = useState("points");
  const [sortOrder, setSortOrder] = useState("desc");
  const [stats, setStats] = useState({});

  const employees = users.filter(user => user.role === 'employee' || !user.role);

  useEffect(() => {
    // In a real app, you would fetch the stats from the Django API (hr/points)
    const simulatedStats = {};
    employees.forEach(emp => {
      simulatedStats[emp.id] = { totalPoints: 0, totalActivityPoints: 0, totalTaskPoints: 0 };
    });
    setStats(simulatedStats);
  }, [users]);

  // For the port, we mock the rendering to match the original layout
  return (
    <div className="animate-fade-in p-6">
      <h1 className="text-3xl font-bold mb-6 text-gray-800 dark:text-gray-100">
        إدارة نقاط الموظفين
      </h1>

      <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-md border mb-6">
        <div className="flex flex-col md:flex-row gap-4 items-start justify-between">
          <div className="flex gap-3">
            <button
              onClick={() => setViewMode("user")}
              className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                viewMode === "user" ? "bg-blue-500 text-white" : "bg-gray-200 text-gray-700"
              }`}
            >
              عرض موظف محدد
            </button>
            <button
              onClick={() => setViewMode("daily")}
              className={`px-4 py-2 rounded-lg font-semibold transition-colors ${
                viewMode === "daily" ? "bg-blue-500 text-white" : "bg-gray-200 text-gray-700"
              }`}
            >
              عرض جميع الموظفين ليوم محدد
            </button>
          </div>

          <div className="flex gap-3 items-center">
            <label className="text-sm font-medium text-gray-700">التاريخ:</label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="p-2 border rounded-lg bg-gray-50"
            />
          </div>
        </div>
      </div>

      {viewMode === "user" ? (
        <>
          <div className="bg-white rounded-2xl p-6 shadow-md border mb-6">
            <label className="block text-sm font-medium mb-3">اختر الموظف:</label>
            <select
              value={selectedUser?.id || ""}
              onChange={(e) => setSelectedUser(employees.find((u) => u.id === parseInt(e.target.value)) || null)}
              className="w-full max-w-md p-3 border rounded-lg bg-gray-50"
            >
              <option value="">اختر موظف...</option>
              {employees.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username || user.first_name}
                </option>
              ))}
            </select>
          </div>

          {selectedUser && (
            <div className="bg-white rounded-2xl p-6 shadow-md border mb-6">
               <h3 className="text-lg font-bold mb-4">معلومات الموظف والإحصائيات</h3>
               <p className="text-gray-600">الاسم: <span className="font-semibold text-gray-900">{selectedUser.username}</span></p>
               <button className="mt-4 bg-blue-500 hover:bg-blue-600 text-white py-2 px-4 rounded-lg font-semibold">
                  تعديل النقاط يدوياً
               </button>
            </div>
          )}
        </>
      ) : (
        <div className="bg-white rounded-2xl shadow-md border overflow-hidden">
          <div className="p-4 border-b flex justify-between items-center">
            <h3 className="text-lg font-bold">نقاط الموظفين ليوم {selectedDate}</h3>
          </div>
          <div className="overflow-x-auto p-4 text-center text-gray-500">
             {loading ? 'جاري التحميل...' : 'اضغط لجلب بيانات النقاط للموظفين من API.'}
          </div>
        </div>
      )}
    </div>
  );
};
