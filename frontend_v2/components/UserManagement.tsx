import React, { useState, useEffect, useMemo } from "react";
import { User, ActivityStatus, UserRole } from "../types";
import { EditIcon } from "./icons/EditIcon";
import { DeleteIcon } from "./icons/DeleteIcon";
import { EditUserModal } from "./modals/EditUserModal";
import { EmployeeDetailsModal } from "./modals/EmployeeDetailsModal";
import {
  updateUserInDb,
  deleteUserFromDb,
  activityService,
} from "../services/firestoreService";
import { Filter, UserCheck, Briefcase, Activity } from 'lucide-react'; // استيراد أيقونات الفلاتر

// إضافة نوع لحالة التوظيف للاستخدام المحلي
type EmploymentStatus = "probation" | "permanent" | "intern";

interface UserManagementProps {
  users: User[];
  onUpdateUser: (user: User) => void;
  onDeleteUser: (userId: string) => void;
}

// دالة مساعدة لترجمة حالة التوظيف (لم تتغير)
const getEmploymentStatusText = (
  status: EmploymentStatus | undefined
): string => {
  switch (status) {
    case "permanent":
      return "موظف ثابت";
    case "probation":
      return "تحت الاختبار";
    case "intern":
      return "متدرب";
    default:
      return "غير محدد";
  }
};

// دالة مساعدة لجلب لون حالة التوظيف (لم تتغير)
const getEmploymentStatusColor = (
  status: EmploymentStatus | undefined
): string => {
  switch (status) {
    case "permanent":
      return "bg-green-100 text-green-800";
    case "probation":
      return "bg-yellow-100 text-yellow-800";
    case "intern":
      return "bg-blue-100 text-blue-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
};

// دالة مساعدة لحساب إذا كان المستخدم نشطاً حالياً (لم تتغير)
const calculateIsActive = (activityStatus?: ActivityStatus): boolean => {
  if (!activityStatus) {
    return false;
  }
  return activityStatus.isCurrentlyActive;
};

// دالة مساعدة للحصول على لون النقطة بناءً على الحالة (لم تتغير)
const getDotColor = (
  isActive: boolean,
  isApproved: boolean,
  activityStatus?: ActivityStatus
): string => {
  if (!isApproved) {
    return "bg-gray-500";
  }
  if (!activityStatus) {
    return "bg-yellow-500";
  }
  return isActive ? "bg-green-500" : "bg-red-500";
};

// دالة مساعدة للحصول على نص حالة النشاط للتلميح (تم تبسيطها قليلاً)
const getActivityTooltipText = (
  user: User,
  activityStatus?: ActivityStatus
): string => {
  if (!user.isApproved) return "غير مفعل";
  if (!activityStatus) return "مفعل - بيانات النشاط غير متاحة";
  if (!activityStatus.isCurrentlyActive) return "مفعل - غير نشط حالياً";

  const lastCheckIn = new Date(activityStatus.lastCheckIn);
  const minutesDiff = Math.floor((new Date().getTime() - lastCheckIn.getTime()) / (1000 * 60));

  if (minutesDiff < 1) return "نشط الآن";
  if (minutesDiff < 10) return `نشط (منذ ${minutesDiff} دقيقة)`;
  return "نشط (منذ أكثر من 10 دقائق)";
};


export const UserManagement: React.FC<UserManagementProps> = ({
  users,
  onUpdateUser,
  onDeleteUser,
}) => {
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [activityStatuses, setActivityStatuses] = useState<{
    [userId: string]: ActivityStatus;
  }>({});
  const [loading, setLoading] = useState(true);

  // حالة الفلاتر الجديدة
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [activityFilter, setActivityFilter] = useState<string>('all');


  // دالة لتحميل جميع بيانات النشاط للموظفين (لم تتغير)
  const loadAllActivityStatuses = async (): Promise<void> => {
    setLoading(true);
    const employees = users.filter(
      (user) => user.role === "employee" || user.role === "procurement"
    );
    const newStatuses: { [userId: string]: ActivityStatus } = {};

    const promises = employees.map(async (employee) => {
      try {
        const status = await activityService.getActivityStatus(employee.id);
        if (status) {
          newStatuses[employee.id] = status;
        }
      } catch (error) {
        // console suppressed
      }
    });

    await Promise.all(promises);
    setActivityStatuses(newStatuses);
    setLoading(false);
  };

  // الاشتراك في تحديثات حالة النشاط للموظفين (لم تتغير)
  useEffect(() => {
    const employees = users.filter((user) => user.role === "employee" || user.role === "procurement");
    const unsubscribes: (() => void)[] = [];

    employees.forEach((employee) => {
      const unsubscribe = activityService.subscribeToActivityStatus(
        employee.id,
        (status: ActivityStatus | null) => {
          if (status) {
            setActivityStatuses((prev) => ({
              ...prev,
              [employee.id]: status,
            }));
          }
        }
      );
      unsubscribes.push(unsubscribe);
    });

    return () => {
      unsubscribes.forEach((unsubscribe) => unsubscribe());
    };
  }, [users]);

  // تحميل بيانات النشاط عند التحميل الأولي (لم تتغير)
  useEffect(() => {
    if (users.length > 0) {
      loadAllActivityStatuses();
    }
  }, [users]);

  // دالة الفلترة الرئيسية
  const filteredUsers = useMemo(() => {
    return users.filter(user => {
      // فلتر الدور
      if (roleFilter !== 'all' && user.role !== roleFilter) {
        return false;
      }
      
      // فلتر الحالة الوظيفية
      if (statusFilter !== 'all') {
        const userStatus = (user.employmentStatus as EmploymentStatus) || 'غير محدد';
        if (userStatus !== statusFilter) {
          return false;
        }
      }
      
      // فلتر حالة النشاط
      if (activityFilter !== 'all') {
        const userActivityStatus = activityStatuses[user.id];
        const isActive = calculateIsActive(userActivityStatus);
        
        if (activityFilter === 'active' && !isActive) {
          return false;
        }
        if (activityFilter === 'inactive' && isActive) {
          return false;
        }
        if (activityFilter === 'unapproved' && user.isApproved) {
            return false;
        }
        if (activityFilter === 'no_data' && user.isApproved && userActivityStatus) {
            return false;
        }
      }

      return true;
    });
  }, [users, roleFilter, statusFilter, activityFilter, activityStatuses]);
  
  // دالة النقر على الصف
  const handleRowClick = (user: User, e: React.MouseEvent<HTMLTableRowElement>) => {
    // التحقق للتأكد من أن النقر لم يكن على أحد أزرار الإجراءات
    const target = e.target as HTMLElement;
    if (target.closest('button') || target.closest('a')) {
      return;
    }
    handleViewDetails(user);
  };


  const handleEditClick = (user: User) => {
    setSelectedUser(user);
    setIsEditModalOpen(true);
  };

  const handleViewDetails = (user: User) => {
    setSelectedUser(user);
    setIsDetailsModalOpen(true);
  };

  const handleUpdate = (updatedUser: User) => {
    onUpdateUser(updatedUser);
    setIsEditModalOpen(false);
    setSelectedUser(null);
  };

  const handleApproveUser = async (user: User) => {
    if (confirm(`هل أنت متأكد من تفعيل حساب ${user.name}؟`)) {
      const updatedUser = {
        ...user,
        isApproved: true,
        employmentStatus: user.employmentStatus || "probation",
      };
      await updateUserInDb(updatedUser);
      onUpdateUser(updatedUser as User);
      setIsDetailsModalOpen(false);
    }
  };

  const handleRejectUser = async (userId: string) => {
    if (
      confirm(
        "هل أنت متأكد من رفض وحذف هذا المستخدم نهائياً؟ سيتم حذف السيرة الذاتية أيضاً."
      )
    ) {
      await deleteUserFromDb(userId);
      onDeleteUser(userId);
      setIsDetailsModalOpen(false);
    }
  };

  const handleSaveNotes = async (userId: string, notes: string) => {
    onUpdateUser({ ...selectedUser, id: userId, notes: notes } as User);
    await updateUserInDb({ id: userId, notes: notes });
  };

  const handleRefreshActivityStatuses = async () => {
    await loadAllActivityStatuses();
  };

  if (loading) {
    return (
      <div className="animate-fade-in">
        <h1 className="text-3xl font-bold mb-6 text-gray-800 dark:text-gray-100">
          إدارة المستخدمين
        </h1>
        <div className="flex items-center justify-center h-64">
          <div className="text-lg text-gray-500">
            جاري تحميل بيانات النشاط...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-100">
          إدارة المستخدمين
        </h1>
        <button
          onClick={handleRefreshActivityStatuses}
          className="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors flex items-center gap-2"
          title="إعادة تحميل بيانات النشاط"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          تحديث النشاط
        </button>
      </div>

      {/* منطقة الفلاتر */}
      <div className="mb-6 p-4 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-3 flex items-center gap-2">
            <Filter className="w-5 h-5 text-blue-500" />
            تصفية المستخدمين
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* فلتر الدور */}
            <div>
                <label htmlFor="roleFilter" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1">
                    <Briefcase className="w-4 h-4" />
                    الدور
                </label>
                <select
                    id="roleFilter"
                    value={roleFilter}
                    onChange={(e) => setRoleFilter(e.target.value)}
                    className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                >
                    <option value="all">الكل</option>
                    <option value="manager">مدير</option>
                    <option value="procurement">مشتريات</option>
                    <option value="employee">موظف</option>
                </select>
            </div>
            
            {/* فلتر الحالة الوظيفية */}
            <div>
                <label htmlFor="statusFilter" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1">
                    <UserCheck className="w-4 h-4" />
                    الحالة الوظيفية
                </label>
                <select
                    id="statusFilter"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                >
                    <option value="all">الكل</option>
                    <option value="permanent">موظف ثابت</option>
                    <option value="probation">تحت الاختبار</option>
                    <option value="intern">متدرب</option>
                    <option value="غير محدد">غير محدد</option>
                </select>
            </div>
            
            {/* فلتر حالة النشاط */}
            <div>
                <label htmlFor="activityFilter" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1">
                    <Activity className="w-4 h-4" />
                    حالة النشاط
                </label>
                <select
                    id="activityFilter"
                    value={activityFilter}
                    onChange={(e) => setActivityFilter(e.target.value)}
                    className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                >
                    <option value="all">الكل</option>
                    <option value="active">نشط حالياً</option>
                    <option value="inactive">غير نشط حالياً</option>
                    <option value="no_data">بيانات غير متاحة (مفعل)</option>
                    <option value="unapproved">غير مفعل/بانتظار الموافقة</option>
                </select>
            </div>
        </div>
      </div>
      {/* نهاية منطقة الفلاتر */}


      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-right min-w-max">
            <thead className="bg-gray-50 dark:bg-gray-700/50">
              <tr>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  الاسم
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  الملاحظات الإدارية
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  العنوان
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  الدور
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  الحالة الوظيفية
                </th>
                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">
                  إجراءات
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {filteredUsers.map((user) => { // استخدام filteredUsers
                const userActivityStatus = activityStatuses[user.id];
                const isActive = calculateIsActive(userActivityStatus);
                const tooltipText = getActivityTooltipText(
                  user,
                  userActivityStatus
                );
                const dotColor = getDotColor(
                  isActive,
                  user.isApproved,
                  userActivityStatus
                );

                return (
                  <tr
                    key={user.id}
                    // إضافة النقر على الصف لفتح التفاصيل
                    onClick={(e) => handleRowClick(user, e)} 
                    className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors cursor-pointer"
                  >
                    <td className="p-4 font-medium text-gray-800 dark:text-gray-100">
                      {/* النقطة بجانب الاسم */}
                      <div className="flex items-center gap-2">
                        <span
                          className={`h-3 w-3 rounded-full ${dotColor} flex-shrink-0 ${
                            isActive ? "animate-pulse" : ""
                          }`}
                          title={tooltipText}
                        ></span>
                        <span>{user.name}</span>
                      </div>
                    </td>
                    
                    <td
                      className="p-4 text-gray-600 dark:text-gray-300 max-w-xs truncate"
                      title={user.notes}
                    >
                      {user.notes || "لا يوجد"}
                    </td>
                    <td className="p-4 text-gray-600 dark:text-gray-300">
                      {user.address || "غير متوفر"}
                    </td>
                    <td className="p-4 text-gray-600 dark:text-gray-300">
                      {user.role === "manager" ? (
                        <span className="bg-[var(--color-surface-2)] text-[var(--color-primary)] px-2 py-1 rounded text-xs">
                          مدير
                        </span>
                      ) : user.role === "procurement" ? (
                        <span className="bg-orange-100 text-orange-800 px-2 py-1 rounded text-xs">
                          مشتريات
                        </span>
                      ) : (
                        <span className="bg-gray-100 text-gray-800 px-2 py-1 rounded text-xs">
                          موظف
                        </span>
                      )}
                    </td>
                    <td className="p-4">
                      <span
                        className={`${getEmploymentStatusColor(
                          user.employmentStatus as EmploymentStatus
                        )} px-2 py-1 rounded text-xs font-bold`}
                      >
                        {getEmploymentStatusText(
                          user.employmentStatus as EmploymentStatus
                        )}
                      </span>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        {/* تم إزالة زر عرض التفاصيل */}

                        {!user.isApproved && (
                          <button
                            onClick={() => handleApproveUser(user)}
                            className="bg-green-500 text-white px-3 py-1 rounded text-xs hover:bg-green-600 transition"
                          >
                            قبول
                          </button>
                        )}

                        <button
                          onClick={() => handleEditClick(user)}
                          className="text-gray-500 hover:text-blue-700 p-1"
                          title="تعديل"
                        >
                          <EditIcon className="h-5 w-5" />
                        </button>

                        <button
                          onClick={() => handleRejectUser(user.id)}
                          className="text-red-500 hover:text-red-700 p-1"
                          title={user.isApproved ? "حذف" : "رفض وحذف"}
                        >
                          <DeleteIcon className="h-5 w-5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {selectedUser && (
        <>
          <EditUserModal
            isOpen={isEditModalOpen}
            onClose={() => setIsEditModalOpen(false)}
            user={selectedUser}
            onSave={handleUpdate}
          />
          <EmployeeDetailsModal
            isOpen={isDetailsModalOpen}
            onClose={() => setIsDetailsModalOpen(false)}
            user={selectedUser}
            onApprove={handleApproveUser}
            onReject={handleRejectUser}
            onSaveNotes={handleSaveNotes}
          />
        </>
      )}
    </div>
  );
};