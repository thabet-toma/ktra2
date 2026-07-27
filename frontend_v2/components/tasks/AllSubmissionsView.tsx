// components/tasks/AllSubmissionsView.tsx
import React, { useState, useMemo } from 'react';
import { Task, User, Submission } from '../../types';
import { Check, X, Download, Eye, Clock, AlertCircle, Filter, Search, ExternalLink, Mail, Phone } from 'lucide-react';
import { formatDateValue } from "../../utils/formatDate";

interface AllSubmissionsViewProps {
  task: Task;
  users: User[];
  onUpdateSubmissionStatus: (
    taskId: string,
    submissionId: string,
    status: 'approved' | 'rejected',
    reviewerNotes?: string
  ) => void;
  onOpenSubmissionDetail: (submission: Submission) => void;
  onSendReminder?: (userId: string) => void;
}

export const AllSubmissionsView: React.FC<AllSubmissionsViewProps> = ({
  task,
  users,
  onUpdateSubmissionStatus,
  onOpenSubmissionDetail,
  onSendReminder
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedUser, setSelectedUser] = useState<string | null>(null);

  // تجميع بيانات جميع الموظفين مع تسليماتهم
  const userSubmissionsData = useMemo(() => {
    const assignedUserIds = Array.isArray(task.assignedTo) ? task.assignedTo : [task.assignedTo];
    
    return assignedUserIds.map(userId => {
      const user = users.find(u => u.id === userId);
      const submissions = (task.submissions || []).filter(sub => sub.userId === userId);
      const latestSubmission = submissions.length > 0 
        ? submissions.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())[0]
        : null;
      
      const userStatus = task.userStatuses?.[userId] || {};
      const isSubmitted = userStatus.status === 'submitted' || userStatus.status === 'completed';
      const isOverdue = new Date(task.dueDate) < new Date() && !isSubmitted;

      return {
        user,
        userId,
        submissions,
        latestSubmission,
        userStatus,
        isSubmitted,
        isOverdue,
        submissionCount: submissions.length,
        lastActivity: latestSubmission?.createdAt || userStatus.startedAt || userStatus.submittedAt,
        hasNewItems: latestSubmission?.newItemsCount && latestSubmission.newItemsCount > 0
      };
    }).filter(data => data.user); // إزالة المستخدمين غير الموجودين
  }, [task, users]);

  // تصفية البيانات حسب البحث والفلتر
  const filteredData = useMemo(() => {
    return userSubmissionsData.filter(data => {
      const user = data.user!;
      const matchesSearch = 
        user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        user.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (data.latestSubmission?.status && data.latestSubmission.status.toLowerCase().includes(searchTerm.toLowerCase()));
      
      const matchesFilter = 
        statusFilter === 'all' ||
        (statusFilter === 'pending' && data.latestSubmission?.status === 'pending') ||
        (statusFilter === 'approved' && data.latestSubmission?.status === 'approved') ||
        (statusFilter === 'rejected' && data.latestSubmission?.status === 'rejected') ||
        (statusFilter === 'not_submitted' && !data.isSubmitted) ||
        (statusFilter === 'with_new_items' && data.hasNewItems);
      
      return matchesSearch && matchesFilter;
    });
  }, [userSubmissionsData, searchTerm, statusFilter]);

  // إحصائيات
  const stats = useMemo(() => {
    const total = userSubmissionsData.length;
    const submitted = userSubmissionsData.filter(d => d.isSubmitted).length;
    const pending = userSubmissionsData.filter(d => d.latestSubmission?.status === 'pending').length;
    const approved = userSubmissionsData.filter(d => d.latestSubmission?.status === 'approved').length;
    const rejected = userSubmissionsData.filter(d => d.latestSubmission?.status === 'rejected').length;
    const overdue = userSubmissionsData.filter(d => d.isOverdue).length;
    const withNewItems = userSubmissionsData.filter(d => d.hasNewItems).length;

    return { total, submitted, pending, approved, rejected, overdue, withNewItems };
  }, [userSubmissionsData]);

  // دالة للموافقة/الرفض السريع
  const handleQuickApprove = (submissionId: string, userId: string) => {
    if (confirm('هل تريد الموافقة على هذا التسليم؟')) {
      onUpdateSubmissionStatus(task.id, submissionId, 'approved', 'تمت الموافقة من العرض الكلي');
    }
  };

  const handleQuickReject = (submissionId: string, userId: string) => {
    const reason = prompt('يرجى كتابة سبب الرفض:');
    if (reason) {
      onUpdateSubmissionStatus(task.id, submissionId, 'rejected', reason);
    }
  };

  // دالة لإرسال تذكير
  const handleSendReminder = (userId: string) => {
    if (onSendReminder && confirm('هل تريد إرسال تذكير لهذا الموظف؟')) {
      onSendReminder(userId);
    }
  };

  // دالة لتحميل جميع التسليمات
  const handleDownloadAllSubmissions = () => {
    // يمكن تنفيذ منطق تحميل جميع التسليمات هنا
    alert('سيتم تحميل جميع التسليمات');
  };

  return (
    <div className="bg-[var(--color-surface)] rounded-xl shadow-sm border border-[var(--color-border)] p-4 md:p-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-[var(--color-text)]">
            تسليمات المهمة: {task.title}
          </h2>
          <p className="text-[var(--color-text-muted)] mt-1">
            عرض جميع تسليمات الموظفين في صفحة واحدة
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleDownloadAllSubmissions}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--color-surface-3)] text-[var(--color-text)] rounded-lg hover:bg-[var(--color-surface-3)] transition-colors"
          >
            <Download className="w-4 h-4" />
            تحميل الكل
          </button>
        </div>
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
        <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg border border-blue-100 dark:border-blue-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-100 dark:bg-blue-800 rounded-full flex items-center justify-center">
              <span className="text-blue-600 dark:text-blue-400 font-bold">{stats.total}</span>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">المعينين</p>
              <p className="font-bold text-[var(--color-text)]">الكل</p>
            </div>
          </div>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-lg border border-green-100 dark:border-green-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-green-100 dark:bg-green-800 rounded-full flex items-center justify-center">
              <span className="text-green-600 dark:text-green-400 font-bold">{stats.approved}</span>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">مقبول</p>
              <p className="font-bold text-[var(--color-text)]">مقبول</p>
            </div>
          </div>
        </div>
        <div className="bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-lg border border-yellow-100 dark:border-yellow-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-yellow-100 dark:bg-yellow-800 rounded-full flex items-center justify-center">
              <span className="text-yellow-600 dark:text-yellow-400 font-bold">{stats.pending}</span>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">قيد المراجعة</p>
              <p className="font-bold text-[var(--color-text)]">قيد المراجعة</p>
            </div>
          </div>
        </div>
        <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded-lg border border-red-100 dark:border-red-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-red-100 dark:bg-red-800 rounded-full flex items-center justify-center">
              <span className="text-red-600 dark:text-red-400 font-bold">{stats.rejected}</span>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">مرفوض</p>
              <p className="font-bold text-[var(--color-text)]">مرفوض</p>
            </div>
          </div>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 p-3 rounded-lg border border-purple-100 dark:border-purple-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-purple-100 dark:bg-purple-800 rounded-full flex items-center justify-center">
              <span className="text-purple-600 dark:text-purple-400 font-bold">{stats.submitted}</span>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">مسلمة</p>
              <p className="font-bold text-[var(--color-text)]">مسلمة</p>
            </div>
          </div>
        </div>
        <div className="bg-orange-50 dark:bg-orange-900/20 p-3 rounded-lg border border-orange-100 dark:border-orange-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-orange-100 dark:bg-orange-800 rounded-full flex items-center justify-center">
              <span className="text-orange-600 dark:text-orange-400 font-bold">{stats.overdue}</span>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">متأخر</p>
              <p className="font-bold text-[var(--color-text)]">متأخر</p>
            </div>
          </div>
        </div>
        <div className="bg-indigo-50 dark:bg-indigo-900/20 p-3 rounded-lg border border-indigo-100 dark:border-indigo-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-100 dark:bg-indigo-800 rounded-full flex items-center justify-center">
              <span className="text-indigo-600 dark:text-indigo-400 font-bold">{stats.withNewItems}</span>
            </div>
            <div>
              <p className="text-xs text-[var(--color-text-muted)]">جديد</p>
              <p className="font-bold text-[var(--color-text)]">بنود جديدة</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-4 mb-6">
        <div className="flex-1 relative">
          <Search className="absolute right-3 top-1/2 transform -translate-y-1/2 text-[var(--color-text-muted)] w-5 h-5" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="ابحث عن موظف أو حالة..."
            className="w-full pr-10 pl-4 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="w-full md:w-64">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-[var(--color-text-muted)]" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full px-4 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]"
            >
              <option value="all">جميع الحالات</option>
              <option value="pending">قيد المراجعة</option>
              <option value="approved">مقبول</option>
              <option value="rejected">مرفوض</option>
              <option value="not_submitted">لم يسلم</option>
              <option value="with_new_items">بنود جديدة</option>
            </select>
          </div>
        </div>
      </div>

      {/* Users Table */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-max">
          <thead className="bg-[var(--color-surface-2)] border-b border-[var(--color-border)]">
            <tr>
              <th className="py-3 px-4 text-right font-semibold text-[var(--color-text)]">
                الموظف
              </th>
              <th className="py-3 px-4 text-right font-semibold text-[var(--color-text)]">
                حالة التسليم
              </th>
              <th className="py-3 px-4 text-right font-semibold text-[var(--color-text)]">
                آخر تسليم
              </th>
              <th className="py-3 px-4 text-right font-semibold text-[var(--color-text)]">
                عدد البنود
              </th>
              <th className="py-3 px-4 text-right font-semibold text-[var(--color-text)]">
                الإجراءات
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {filteredData.map((data) => (
              <tr 
                key={data.userId} 
                className={`hover:bg-[var(--color-surface-2)] transition-colors ${
                  selectedUser === data.userId ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                }`}
                onClick={() => setSelectedUser(data.userId === selectedUser ? null : data.userId)}
              >
                <td className="py-4 px-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-[var(--color-surface-3)] rounded-full flex items-center justify-center">
                      <span className="font-bold text-[var(--color-text)]">
                        {data.user?.name?.charAt(0) || '?'}
                      </span>
                    </div>
                    <div>
                      <h4 className="font-bold text-[var(--color-text)]">
                        {data.user?.name}
                      </h4>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {data.user?.email && (
                          <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
                            <Mail className="w-3 h-3" />
                            {data.user.email}
                          </span>
                        )}
                        {data.user?.phone && (
                          <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
                            <Phone className="w-3 h-3" />
                            {data.user.phone}
                          </span>
                        )}
                      </div>
                      {data.isOverdue && (
                        <span className="inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400 mt-1">
                          <AlertCircle className="w-3 h-3" />
                          متأخر عن التسليم
                        </span>
                      )}
                    </div>
                  </div>
                </td>
                <td className="py-4 px-4">
                  {data.latestSubmission ? (
                    <div className="flex items-center gap-2">
                      <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                        data.latestSubmission.status === 'approved' 
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                          : data.latestSubmission.status === 'rejected'
                          ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                          : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                      }`}>
                        {data.latestSubmission.status === 'approved' ? 'مقبول' :
                         data.latestSubmission.status === 'rejected' ? 'مرفوض' : 'قيد المراجعة'}
                      </span>
                      {data.hasNewItems && (
                        <span className="px-2 py-0.5 bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded-full text-xs">
                          {data.latestSubmission.newItemsCount} جديد
                        </span>
                      )}
                    </div>
                  ) : data.isSubmitted ? (
                    <span className="px-3 py-1 bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded-full text-xs font-medium">
                      مسلمة
                    </span>
                  ) : (
                    <span className="px-3 py-1 bg-[var(--color-surface-3)] text-[var(--color-text)] rounded-full text-xs font-medium">
                      لم يسلم
                    </span>
                  )}
                </td>
                <td className="py-4 px-4">
                  {data.latestSubmission ? (
                    <div className="space-y-1">
                      <span className="text-sm text-[var(--color-text)] block">
                        {formatDateValue(data.latestSubmission.createdAt)}
                      </span>
                      <span className="text-xs text-[var(--color-text-muted)] block">
                        {new Date(data.latestSubmission.createdAt).toLocaleTimeString('ar-EG')}
                      </span>
                      {data.latestSubmission.reviewedAt && (
                        <span className="text-xs text-[var(--color-text-muted)] block">
                          مراجعة: {formatDateValue(data.latestSubmission.reviewedAt)}
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="text-[var(--color-text-muted)]">لا يوجد</span>
                  )}
                </td>
                <td className="py-4 px-4">
                  {data.latestSubmission ? (
                    <div className="space-y-1">
                      <span className="font-medium text-[var(--color-text)] block">
                        {data.submissionCount} تسليم
                      </span>
                      <span className="text-sm text-[var(--color-text-muted)] block">
                        {data.latestSubmission.items?.length || 0} بند
                      </span>
                    </div>
                  ) : (
                    <span className="text-[var(--color-text-muted)]">0</span>
                  )}
                </td>
                <td className="py-4 px-4">
                  <div className="flex gap-2">
                    {data.latestSubmission ? (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenSubmissionDetail(data.latestSubmission!);
                          }}
                          className="p-2 text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                          title="عرض التفاصيل"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        
                        {data.latestSubmission.status === 'pending' && (
                          <>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleQuickApprove(data.latestSubmission!.id, data.userId);
                              }}
                              className="p-2 text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-colors"
                              title="موافقة"
                            >
                              <Check className="w-4 h-4" />
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleQuickReject(data.latestSubmission!.id, data.userId);
                              }}
                              className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                              title="رفض"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </>
                        )}
                        
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            window.open(`/tasks/${task.id}/submissions/${data.latestSubmission!.id}`, '_blank');
                          }}
                          className="p-2 text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface-2)] rounded-lg transition-colors"
                          title="فتح في نافذة جديدة"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSendReminder(data.userId);
                        }}
                        className="flex items-center gap-1 px-3 py-1.5 bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 rounded-lg hover:bg-yellow-200 dark:hover:bg-yellow-900/50 transition-colors text-sm"
                        title="إرسال تذكير"
                      >
                        <Clock className="w-3 h-3" />
                        تذكير
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredData.length === 0 && (
        <div className="text-center py-12 text-[var(--color-text-muted)]">
          <div className="w-16 h-16 mx-auto mb-4 bg-[var(--color-surface-3)] rounded-full flex items-center justify-center">
            <Search className="w-8 h-8" />
          </div>
          <p className="text-lg">لا توجد نتائج مطابقة</p>
          <p className="text-sm mt-2">حاول تغيير كلمات البحث أو الفلاتر</p>
        </div>
      )}
    </div>
  );
};