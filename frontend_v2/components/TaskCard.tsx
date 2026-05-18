import React from 'react';
import { Task, User } from '../types';

interface TaskCardProps {
    task: Task;
    user: User;
    userTaskStatus: {
        hasSubmission: boolean;
        status: string;
        submissionCount: number;
        latestSubmission: any;
    };
    onSelectTask: (task: Task) => void;
    categoryName?: string; // إضافة prop جديد
}

// مكون بادج الفئة - محدث
const CategoryBadge: React.FC<{ 
  category: string; 
  categoryName?: string 
}> = ({ category, categoryName }) => {
    const style = {
        electronics: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
        electrical: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
        clothing: 'bg-pink-100 text-pink-800 dark:bg-pink-900/50 dark:text-pink-300',
    }[category] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';

    // استخدام categoryName إذا كان متاحاً، وإلا استخدام القيمة الافتراضية
    const text = categoryName || {
        electronics: 'إلكترونيات',
        electrical: 'كهربائيات',
        clothing: 'ملابس',
    }[category] || category;

    return (
        <span className={`px-3 py-1 text-xs font-medium rounded-full ${style}`}>
            {text}
        </span>
    );
};

// مكون بادج الحالة - محسن
export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
     const style = {
        NEW: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
        ACCEPTED: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
        IN_PROGRESS: 'bg-[var(--color-surface-2)] text-[var(--color-primary)] dark:bg-[var(--color-surface-2)]/50 dark:text-[var(--color-primary)]',
        WAITING_FOR_REVIEW: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
        COMPLETED: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
        REJECTED: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    }[status] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';

    const text = {
        NEW: 'جديدة',
        ACCEPTED: 'مقبولة',
        IN_PROGRESS: 'قيد التنفيذ',
        WAITING_FOR_REVIEW: 'بانتظار المراجعة',
        COMPLETED: 'مكتملة',
        REJECTED: 'مرفوضة',
    }[status] || status;

    return (
        <span className={`px-3 py-1 text-xs font-semibold rounded-full ${style}`}>
            {text}
        </span>
    );
}

// مؤشر الأولوية - محسن
const PriorityIndicator: React.FC<{ priority: string }> = ({ priority }) => {
    const style = {
        low: 'bg-green-500',
        medium: 'bg-yellow-500',
        high: 'bg-orange-500',
        urgent: 'bg-red-500',
    }[priority] || 'bg-gray-500';
    
    const text = {
        low: 'منخفضة',
        medium: 'متوسطة',
        high: 'عالية',
        urgent: 'عاجلة',
    }[priority] || priority;
    
    return (
        <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${style}`}></span>
            <span className="text-xs">{text}</span>
        </div>
    );
}

// مكون معلومات الإسناد - محسن
const AssignmentInfo: React.FC<{ 
  assignedTo: string | string[];
  isMultiAssigned: boolean;
}> = ({ assignedTo, isMultiAssigned }) => {
    const assignedCount = Array.isArray(assignedTo) ? assignedTo.length : 1;
    
    return (
        <div className="flex items-center justify-between">
            <span className="font-semibold text-gray-800 dark:text-gray-100">المعينون:</span>
            <div className="flex items-center gap-2">
                <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs font-medium">
                    {assignedCount} موظف
                </span>
                {isMultiAssigned && (
                    <span className="text-xs text-blue-600 dark:text-blue-400" title="مهمة مشتركة">
                        🔗
                    </span>
                )}
            </div>
        </div>
    );
};

// مكون حالة الموظف في المهمة - محسن
const UserTaskStatus: React.FC<{ 
  status: any;
  submissionCount: number;
}> = ({ status, submissionCount }) => {
    const getStatusInfo = () => {
        switch (status) {
            case 'not_started':
                return { 
                    text: 'لم تبدأ', 
                    color: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300', 
                    icon: '⚪' 
                };
            case 'in_progress':
                return { 
                    text: 'قيد التنفيذ', 
                    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300', 
                    icon: '🔵' 
                };
            case 'submitted':
                return { 
                    text: `مسلمة ${submissionCount > 0 ? `(${submissionCount})` : ''}`, 
                    color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300', 
                    icon: '🟡' 
                };
            case 'completed':
                return { 
                    text: `مكتملة ${submissionCount > 0 ? `(${submissionCount})` : ''}`, 
                    color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300', 
                    icon: '✅' 
                };
            case 'rejected':
                return { 
                    text: `مرفوضة ${submissionCount > 0 ? `(${submissionCount})` : ''}`, 
                    color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300', 
                    icon: '❌' 
                };
            default:
                return { 
                    text: 'غير معروفة', 
                    color: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300', 
                    icon: '⚪' 
                };
        }
    };

    const statusInfo = getStatusInfo();

    return (
        <span className={`px-3 py-1 text-xs font-medium rounded-full ${statusInfo.color} flex items-center gap-2`}>
            <span>{statusInfo.icon}</span>
            {statusInfo.text}
        </span>
    );
};

// مكون الوقت المتبقي
const TimeRemaining: React.FC<{ dueDate: string }> = ({ dueDate }) => {
    const now = new Date();
    const due = new Date(dueDate);
    const diffTime = due.getTime() - now.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    let text = '';
    let color = '';
    
    if (diffDays < 0) {
        text = 'متأخرة';
        color = 'text-red-600 dark:text-red-400';
    } else if (diffDays === 0) {
        text = 'تنتهي اليوم';
        color = 'text-orange-600 dark:text-orange-400';
    } else if (diffDays === 1) {
        text = 'غداً';
        color = 'text-yellow-600 dark:text-yellow-400';
    } else if (diffDays <= 3) {
        text = `${diffDays} أيام`;
        color = 'text-yellow-600 dark:text-yellow-400';
    } else {
        text = `${diffDays} يوم`;
        color = 'text-green-600 dark:text-green-400';
    }
    
    return (
        <div className="flex items-center justify-between">
            <span className="font-semibold text-gray-800 dark:text-gray-100">الوقت المتبقي:</span>
            <span className={`text-xs font-medium ${color}`}>
                {text}
            </span>
        </div>
    );
};

export const TaskCard: React.FC<TaskCardProps> = ({ 
    task, 
    user, 
    userTaskStatus, 
    onSelectTask,
    categoryName 
}) => {
    const isMultiAssigned = Array.isArray(task.assignedTo) && task.assignedTo.length > 1;

    const getButtonText = () => {
        switch (userTaskStatus.status) {
            case 'not_started':
                return 'بدء العمل';
            case 'in_progress':
                return task.workStartTime ? 'مستمر في العمل' : 'استئناف العمل';
            case 'submitted':
                return 'عرض التسليم';
            case 'completed':
                return 'عرض النتائج';
            case 'rejected':
                return 'إعادة التسليم';
            default:
                return 'عرض التفاصيل';
        }
    };

    const getButtonStyle = () => {
        switch (userTaskStatus.status) {
            case 'not_started':
                return 'bg-blue-600 hover:bg-blue-700';
            case 'in_progress':
                return 'bg-green-600 hover:bg-green-700';
            case 'submitted':
                return 'bg-yellow-600 hover:bg-yellow-700';
            case 'completed':
                return 'bg-green-600 hover:bg-green-700';
            case 'rejected':
                return 'bg-red-600 hover:bg-red-700';
            default:
                return 'bg-blue-600 hover:bg-blue-700';
        }
    };

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200/80 dark:border-gray-700 shadow-sm overflow-hidden flex flex-col transition-all duration-300 hover:shadow-lg hover:-translate-y-1 p-5 space-y-4">
            {/* العنوان والحالة */}
            <div className="flex justify-between items-start">
                <h3 className="text-xl font-bold text-gray-800 dark:text-gray-100 truncate" title={task.title}>
                    {task.title}
                </h3>
            </div>
          
            {/* معلومات المهمة */}
            <div className="space-y-3 text-gray-600 dark:text-gray-300 text-sm">
                {/* حالة الموظف في هذه المهمة */}
                <div className="flex items-center justify-between">
                    <span className="font-semibold text-gray-800 dark:text-gray-100">حالتك:</span>
                    <UserTaskStatus 
                        status={userTaskStatus.status} 
                        submissionCount={userTaskStatus.submissionCount} 
                    />
                </div>

                {/* معلومات الإسناد */}
                <AssignmentInfo 
                    assignedTo={task.assignedTo} 
                    isMultiAssigned={isMultiAssigned}
                />
                
                {/* الفئة */}
                <div className="flex items-center justify-between">
                    <span className="font-semibold text-gray-800 dark:text-gray-100">الفئة:</span>
                    <CategoryBadge 
                        category={task.category} 
                        categoryName={categoryName}
                    />
                </div>
                
                {/* الأولوية */}
                <div className="flex items-center justify-between">
                    <span className="font-semibold text-gray-800 dark:text-gray-100">الأولوية:</span>
                    <PriorityIndicator priority={task.priority} />
                </div>
                
                {/* الوقت المتبقي */}
                <TimeRemaining dueDate={task.dueDate} />
                
                {/* تاريخ التسليم */}
                <div className="flex items-center justify-between">
                    <span className="font-semibold text-gray-800 dark:text-gray-100">تاريخ التسليم:</span>
                    <span className="text-xs">{task.dueDate}</span>
                </div>
                
                {/* السعر المستهدف */}
                {task.targetPrice && (
                    <div className="flex items-center justify-between">
                        <span className="font-semibold text-gray-800 dark:text-gray-100">السعر المستهدف:</span>
                        <span className="text-green-600 dark:text-green-400 font-bold">
                            ${task.targetPrice}
                        </span>
                    </div>
                )}
            </div>

            {/* الحالات الخاصة */}
            {task.status === 'REJECTED' && task.rejectReason && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                    <p className="text-red-700 dark:text-red-300 text-sm">
                        <span className="font-semibold">سبب الرفض:</span> {task.rejectReason}
                    </p>
                </div>
            )}

            {task.status === 'IN_PROGRESS' && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                    <p className="text-blue-700 dark:text-blue-300 text-sm font-semibold flex items-center gap-2">
                        <span>⚡</span>
                        قيد التنفيذ
                        {task.workStartTime && (
                            <span className="text-xs font-normal">
                                (بدأت في {new Date(task.workStartTime).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})})
                            </span>
                        )}
                    </p>
                </div>
            )}

            {/* زر العمل */}
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                    onClick={() => onSelectTask(task)}
                    className={`w-full text-white font-semibold py-3 px-5 rounded-lg transition-colors duration-300 ${getButtonStyle()}`}
                >
                    {getButtonText()}
                </button>
                
                {/* معلومات إضافية */}
                <div className="flex items-center justify-between mt-3 text-xs text-gray-500 dark:text-gray-400">
                    <span>
                        أنشئت في: {new Date(task.createdAt).toLocaleDateString()}
                    </span>
                    {userTaskStatus.submissionCount > 0 && (
                        <span>
                            {userTaskStatus.submissionCount} تسليم
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
};