import React, { useState, useMemo } from 'react';
import { Task, User, TaskPriority } from '../types';
import { CreateTaskModal } from './CreateTaskModal';
import { List, Eye, Users, FileText, CheckCircle, XCircle, Clock } from 'lucide-react';
import { AllSubmissionsView } from './tasks/AllSubmissionsView';

interface TaskManagementProps {
    allTasks: Task[];
    users: User[];
    onCreateTask: (newTask: Omit<Task, 'id' | 'status' | 'totalWorkTime' | 'logs' | 'createdAt' | 'updatedAt' | 'submissions'> & { assignedTo: string[] }) => void;
    onSelectTask: (task: Task) => void;
    onUpdateSubmissionStatus?: (
        taskId: string,
        submissionId: string,
        status: 'approved' | 'rejected',
        reviewerNotes?: string
    ) => void;
}

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
     const style = {
        'not_started': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
        'in_progress': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
        'submitted': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
        'completed': 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
        'rejected': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    }[status] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    
    const text = {
        'not_started': 'لم تبدأ',
        'in_progress': 'قيد التنفيذ',
        'submitted': 'مسلمة',
        'completed': 'مكتملة',
        'rejected': 'مرفوضة',
    }[status] || status;
    
    return <span className={`px-3 py-1 text-sm font-semibold rounded-full ${style}`}>{text}</span>;
}

const PriorityIndicator: React.FC<{ priority: TaskPriority }> = ({ priority }) => {
    const getPriorityInfo = (p: TaskPriority) => {
        switch (p) {
            case 'low':
                return { text: 'منخفضة', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-100 dark:bg-green-900/30' };
            case 'medium':
                return { text: 'متوسطة', color: 'text-yellow-600 dark:text-yellow-400', bg: 'bg-yellow-100 dark:bg-yellow-900/30' };
            case 'high':
                return { text: 'عالية', color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-100 dark:bg-orange-900/30' };
            case 'urgent':
                return { text: 'عاجلة', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-100 dark:bg-red-900/30' };
            default:
                return { text: p, color: 'text-gray-600 dark:text-gray-400', bg: 'bg-gray-100 dark:bg-gray-700' };
        }
    };
    
    const info = getPriorityInfo(priority);
    return (
        <span className={`px-3 py-1 rounded-full text-xs font-medium ${info.bg} ${info.color}`}>
            {info.text}
        </span>
    );
}

// مكون لعرض حالة الموظفين بشكل مختصر مع أيقونات
const EmployeeStatusSummary: React.FC<{ 
    assignedTo: string[]; 
    usersMap: Record<string, string>;
    userStatuses?: { [userId: string]: { status: string } };
}> = ({ assignedTo, usersMap, userStatuses }) => {
    const statusCounts = useMemo(() => {
        const counts = {
            'not_started': 0,
            'in_progress': 0,
            'submitted': 0,
            'completed': 0,
            'rejected': 0
        };
        
        assignedTo.forEach(userId => {
            const status = userStatuses?.[userId]?.status || 'not_started';
            counts[status as keyof typeof counts]++;
        });
        
        return counts;
    }, [assignedTo, userStatuses]);

    if (assignedTo.length === 0) {
        return <span className="text-gray-500 text-sm">غير معين</span>;
    }

    const total = assignedTo.length;
    const completed = statusCounts.completed;
    const submitted = statusCounts.submitted;
    const inProgress = statusCounts.in_progress;

    return (
        <div className="flex items-center gap-3">
            <div className="flex -space-x-2">
                {assignedTo.slice(0, 3).map(userId => {
                    const status = userStatuses?.[userId]?.status || 'not_started';
                    let color = 'bg-gray-300 dark:bg-gray-600';
                    if (status === 'completed') color = 'bg-green-500';
                    else if (status === 'submitted') color = 'bg-yellow-500';
                    else if (status === 'in_progress') color = 'bg-blue-500';
                    else if (status === 'rejected') color = 'bg-red-500';
                    
                    return (
                        <div 
                            key={userId}
                            className={`w-8 h-8 rounded-full border-2 border-white dark:border-gray-800 ${color} flex items-center justify-center text-white text-xs`}
                            title={`${usersMap[userId] || 'غير معروف'}: ${status}`}
                        >
                            {usersMap[userId]?.charAt(0) || '?'}
                        </div>
                    );
                })}
                {assignedTo.length > 3 && (
                    <div className="w-8 h-8 rounded-full border-2 border-white dark:border-gray-800 bg-gray-200 dark:bg-gray-700 flex items-center justify-center text-gray-700 dark:text-gray-300 text-xs">
                        +{assignedTo.length - 3}
                    </div>
                )}
            </div>
            
            <div className="flex items-center gap-4">
                {completed > 0 && (
                    <div className="flex items-center gap-1" title={`${completed} مكتمل`}>
                        <CheckCircle className="w-4 h-4 text-green-500" />
                        <span className="text-xs font-medium text-green-700 dark:text-green-400">{completed}</span>
                    </div>
                )}
                {submitted > 0 && (
                    <div className="flex items-center gap-1" title={`${submitted} مسلم`}>
                        <FileText className="w-4 h-4 text-yellow-500" />
                        <span className="text-xs font-medium text-yellow-700 dark:text-yellow-400">{submitted}</span>
                    </div>
                )}
                {inProgress > 0 && (
                    <div className="flex items-center gap-1" title={`${inProgress} قيد التنفيذ`}>
                        <Clock className="w-4 h-4 text-blue-500" />
                        <span className="text-xs font-medium text-blue-700 dark:text-blue-400">{inProgress}</span>
                    </div>
                )}
                {statusCounts.rejected > 0 && (
                    <div className="flex items-center gap-1" title={`${statusCounts.rejected} مرفوض`}>
                        <XCircle className="w-4 h-4 text-red-500" />
                        <span className="text-xs font-medium text-red-700 dark:text-red-400">{statusCounts.rejected}</span>
                    </div>
                )}
            </div>
        </div>
    );
};

export const TaskManagement: React.FC<TaskManagementProps> = ({ 
    allTasks, 
    users, 
    onCreateTask, 
    onSelectTask,
    onUpdateSubmissionStatus 
}) => {
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [statusFilter, setStatusFilter] = useState('All');
    const [employeeFilter, setEmployeeFilter] = useState('All');
    const [priorityFilter, setPriorityFilter] = useState('All');
    const [viewMode, setViewMode] = useState<'list' | 'submissions'>('list');
    const [selectedTaskForSubmissions, setSelectedTaskForSubmissions] = useState<Task | null>(null);

    const usersMap = useMemo(() => {
        return users.reduce((acc, user) => {
            acc[user.id] = user.name;
            return acc;
        }, {} as Record<string, string>);
    }, [users]);

    const employees = useMemo(() => users.filter(u => (u.role === 'employee' || u.role === 'procurement')), [users]);

    const filteredTasks = useMemo(() => {
        return allTasks.filter(task => {
            // فلتر الموظفين
            const employeeMatch = employeeFilter === 'All' || task.assignedTo.includes(employeeFilter);
            if (!employeeMatch) return false;
            
            // فلتر الأولوية
            const priorityMatch = priorityFilter === 'All' || task.priority === priorityFilter;
            if (!priorityMatch) return false;
            
            // فلتر الحالة
            if (statusFilter === 'All') return true;
            
            if (employeeFilter !== 'All') {
                // إذا كان هناك موظف محدد، نفحص حالته فقط
                const userStatus = task.userStatuses?.[employeeFilter];
                const status = userStatus?.status || 'not_started';
                
                const statusMap: Record<string, string[]> = {
                    'Not Started': ['not_started'],
                    'In Progress': ['in_progress'],
                    'Submitted': ['submitted'],
                    'Completed': ['completed'],
                    'Rejected': ['rejected'],
                };
                
                return statusMap[statusFilter]?.includes(status) || false;
            } else {
                // إذا لم يكن هناك موظف محدد، نفحص إذا كانت هناك أي حالة مطابقة
                const statusMap: Record<string, string[]> = {
                    'Not Started': ['not_started'],
                    'In Progress': ['in_progress'],
                    'Submitted': ['submitted'],
                    'Completed': ['completed'],
                    'Rejected': ['rejected'],
                };
                
                const targetStatuses = statusMap[statusFilter];
                if (!targetStatuses) return false;
                
                // نتحقق إذا كان أي موظف لديه الحالة المطلوبة
                return task.assignedTo.some(userId => {
                    const userStatus = task.userStatuses?.[userId];
                    const status = userStatus?.status || 'not_started';
                    return targetStatuses.includes(status);
                });
            }
        });
    }, [allTasks, statusFilter, employeeFilter, priorityFilter]);

    // إحصائيات عامة
    const overallStats = useMemo(() => {
        const stats = {
            totalTasks: allTasks.length,
            activeTasks: allTasks.filter(task => 
                task.assignedTo.some(userId => {
                    const status = task.userStatuses?.[userId]?.status || 'not_started';
                    return status === 'in_progress' || status === 'submitted';
                })
            ).length,
            completedTasks: allTasks.filter(task => 
                task.assignedTo.some(userId => {
                    const status = task.userStatuses?.[userId]?.status || 'not_started';
                    return status === 'completed';
                })
            ).length,
            urgentTasks: allTasks.filter(task => task.priority === 'urgent').length,
            overdueTasks: allTasks.filter(task => new Date(task.dueDate) < new Date()).length,
        };
        
        return stats;
    }, [allTasks]);

    // حساب نسبة الإنجاز للمهمة
    const getTaskCompletionRate = (task: Task): number => {
        const assignedCount = Array.isArray(task.assignedTo) ? task.assignedTo.length : 1;
        const completedCount = Object.values(task.userStatuses || {}).filter(
            (status: any) => status.status === 'completed'
        ).length;
        
        return assignedCount > 0 ? Math.round((completedCount / assignedCount) * 100) : 0;
    };

    // التحقق إذا كانت المهمة متأخرة
    const isTaskOverdue = (task: Task): boolean => {
        return new Date(task.dueDate) < new Date();
    };

    const handleOpenSubmissionsView = (task: Task, e?: React.MouseEvent) => {
        if (e) e.stopPropagation();
        setSelectedTaskForSubmissions(task);
        setViewMode('submissions');
    };

    const handleCloseSubmissionsView = () => {
        setViewMode('list');
        setSelectedTaskForSubmissions(null);
    };

    // عرض جميع التسليمات
    if (viewMode === 'submissions' && selectedTaskForSubmissions && onUpdateSubmissionStatus) {
        return (
            <div className="animate-fade-in">
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={handleCloseSubmissionsView}
                            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                        >
                            <span className="text-xl">←</span>
                        </button>
                        <div>
                            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                                تسليمات المهمة: {selectedTaskForSubmissions.title}
                            </h1>
                            <p className="text-gray-600 dark:text-gray-400">
                                عرض جميع تسليمات الموظفين في صفحة واحدة
                            </p>
                        </div>
                    </div>
                </div>

                <AllSubmissionsView
                    task={selectedTaskForSubmissions}
                    users={employees}
                    onUpdateSubmissionStatus={onUpdateSubmissionStatus}
                    onOpenSubmissionDetail={(submission) => {
                        // يمكنك فتح عرض تفصيلي للتسليم
                        console.log('Open submission detail:', submission);
                    }}
                    onSendReminder={(userId) => {
                        alert(`تم إرسال تذكير للموظف ${usersMap[userId] || userId}`);
                    }}
                />
            </div>
        );
    }

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-2xl md:text-3xl font-bold text-gray-800 dark:text-gray-100">إدارة المهام</h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-2">
                        إجمالي المهام: <span className="font-bold">{overallStats.totalTasks}</span> | 
                        نشطة: <span className="font-bold text-blue-600 dark:text-blue-400">{overallStats.activeTasks}</span> | 
                        مكتملة: <span className="font-bold text-green-600 dark:text-green-400">{overallStats.completedTasks}</span>
                        {overallStats.urgentTasks > 0 && (
                            <span className="ml-4">
                                عاجلة: <span className="font-bold text-red-600 dark:text-red-400">{overallStats.urgentTasks}</span>
                            </span>
                        )}
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button
                        onClick={() => setIsCreateModalOpen(true)}
                        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 md:px-6 rounded-lg text-sm md:text-base transition"
                    >
                        <span className="text-lg">+</span>
                        مهمة جديدة
                    </button>
                </div>
            </div>

            {/* Filters */}
            <div className="mb-6 bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label htmlFor="statusFilter" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            حالة الموظفين
                        </label>
                        <select
                            id="statusFilter"
                            value={statusFilter}
                            onChange={e => setStatusFilter(e.target.value)}
                            className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        >
                            <option value="All">جميع الحالات</option>
                            <option value="Not Started">لم تبدأ</option>
                            <option value="In Progress">قيد التنفيذ</option>
                            <option value="Submitted">مسلمة</option>
                            <option value="Completed">مكتملة</option>
                            <option value="Rejected">مرفوضة</option>
                        </select>
                    </div>
                    <div>
                        <label htmlFor="employeeFilter" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            الموظف
                        </label>
                        <select
                            id="employeeFilter"
                            value={employeeFilter}
                            onChange={e => setEmployeeFilter(e.target.value)}
                            className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        >
                            <option value="All">كل الموظفين</option>
                            {employees.map(emp => (
                                <option key={emp.id} value={emp.id}>{emp.name}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label htmlFor="priorityFilter" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            الأولوية
                        </label>
                        <select
                            id="priorityFilter"
                            value={priorityFilter}
                            onChange={e => setPriorityFilter(e.target.value)}
                            className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        >
                            <option value="All">جميع الأولويات</option>
                            <option value="low">منخفضة</option>
                            <option value="medium">متوسطة</option>
                            <option value="high">عالية</option>
                            <option value="urgent">عاجلة</option>
                        </select>
                    </div>
                </div>
            </div>

            {/* Tasks List */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-right">
                        <thead className="bg-gray-50 dark:bg-gray-700/50">
                            <tr>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300 min-w-[250px]">المهمة</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300 min-w-[200px]">حالة الموظفين</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">الأولوية</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">تاريخ التسليم</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">الإجراءات</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {filteredTasks.map(task => {
                                const completionRate = getTaskCompletionRate(task);
                                const isOverdue = isTaskOverdue(task);
                                
                                return (
                                    <tr 
                                        key={task.id}
                                        onClick={() => onSelectTask(task)}
                                        className={`hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors ${
                                            isOverdue ? 'border-l-4 border-l-red-500' : ''
                                        }`}
                                    >
                                        <td className="p-4">
                                            <div className="flex flex-col gap-1">
                                                <div className="flex items-start justify-between">
                                                    <h3 className="font-bold text-gray-900 dark:text-white text-sm md:text-base">
                                                        {task.title}
                                                    </h3>
                                                    {isOverdue && (
                                                        <span className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-2 py-1 rounded">
                                                            متأخرة
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                                                    {task.description}
                                                </p>
                                                {completionRate > 0 && (
                                                    <div className="mt-2">
                                                        <div className="flex justify-between text-xs mb-1">
                                                            <span className="text-gray-600 dark:text-gray-400">نسبة الإنجاز</span>
                                                            <span className="font-medium">{completionRate}%</span>
                                                        </div>
                                                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                                            <div 
                                                                className={`h-2 rounded-full ${
                                                                    completionRate >= 100 ? 'bg-green-500' :
                                                                    completionRate >= 70 ? 'bg-blue-500' :
                                                                    completionRate >= 30 ? 'bg-yellow-500' :
                                                                    'bg-gray-400'
                                                                }`}
                                                                style={{ width: `${completionRate}%` }}
                                                            />
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </td>
                                        <td className="p-4">
                                            <EmployeeStatusSummary 
                                                assignedTo={Array.isArray(task.assignedTo) ? task.assignedTo : [task.assignedTo]}
                                                usersMap={usersMap}
                                                userStatuses={task.userStatuses}
                                            />
                                        </td>
                                        <td className="p-4">
                                            <div className="flex justify-center">
                                                <PriorityIndicator priority={task.priority} />
                                            </div>
                                        </td>
                                        <td className="p-4">
                                            <div className="flex flex-col items-center">
                                                <span className="text-gray-900 dark:text-white text-sm">
                                                    {task.dueDate}
                                                </span>
                                                {isOverdue && (
                                                    <span className="text-xs text-red-600 dark:text-red-400 mt-1">
                                                        منذ {Math.floor((new Date().getTime() - new Date(task.dueDate).getTime()) / (1000 * 60 * 60 * 24))} يوم
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="p-4">
                                            <div className="flex gap-2 justify-center">
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onSelectTask(task);
                                                    }}
                                                    className="p-2 text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                                                    title="عرض التفاصيل"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </button>
                                                
                                                {onUpdateSubmissionStatus && (
                                                    <button
                                                        onClick={(e) => handleOpenSubmissionsView(task, e)}
                                                        className="flex items-center gap-1 px-3 py-1.5 bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 rounded-lg hover:bg-purple-200 dark:hover:bg-purple-900/50 transition-colors text-sm"
                                                        title="عرض جميع التسليمات"
                                                    >
                                                        <List className="w-3 h-3" />
                                                        <span className="hidden md:inline">التسليمات</span>
                                                        <span className="bg-white dark:bg-purple-800 text-purple-700 dark:text-purple-300 text-xs px-1.5 py-0.5 rounded-full">
                                                            {Array.isArray(task.assignedTo) ? task.assignedTo.length : 1}
                                                        </span>
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                    
                    {filteredTasks.length === 0 && (
                        <div className="text-center py-12">
                            <div className="w-16 h-16 mx-auto mb-4 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center">
                                <FileText className="w-8 h-8 text-gray-400" />
                            </div>
                            <p className="text-gray-500 dark:text-gray-400 text-lg">لا توجد مهام مطابقة للبحث</p>
                            <p className="text-gray-400 dark:text-gray-500 text-sm mt-2">حاول تغيير الفلاتر المحددة</p>
                        </div>
                    )}
                </div>
            </div>

            {/* إحصائيات سريعة في الأسفل */}
            {filteredTasks.length > 0 && (
                <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center">
                                <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                            </div>
                            <div>
                                <p className="text-sm text-gray-500 dark:text-gray-400">إجمالي المعينين</p>
                                <p className="text-lg font-bold text-gray-900 dark:text-white">
                                    {filteredTasks.reduce((sum, task) => sum + (Array.isArray(task.assignedTo) ? task.assignedTo.length : 1), 0)}
                                </p>
                            </div>
                        </div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center">
                                <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                            </div>
                            <div>
                                <p className="text-sm text-gray-500 dark:text-gray-400">مكتملة</p>
                                <p className="text-lg font-bold text-gray-900 dark:text-white">
                                    {filteredTasks.reduce((sum, task) => {
                                        const completedCount = Object.values(task.userStatuses || {}).filter(
                                            (status: any) => status.status === 'completed'
                                        ).length;
                                        return sum + completedCount;
                                    }, 0)}
                                </p>
                            </div>
                        </div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-yellow-100 dark:bg-yellow-900/30 rounded-lg flex items-center justify-center">
                                <Clock className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                            </div>
                            <div>
                                <p className="text-sm text-gray-500 dark:text-gray-400">قيد التنفيذ</p>
                                <p className="text-lg font-bold text-gray-900 dark:text-white">
                                    {filteredTasks.reduce((sum, task) => {
                                        const inProgressCount = Object.values(task.userStatuses || {}).filter(
                                            (status: any) => status.status === 'in_progress' || status.status === 'submitted'
                                        ).length;
                                        return sum + inProgressCount;
                                    }, 0)}
                                </p>
                            </div>
                        </div>
                    </div>
                    <div className="bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-red-100 dark:bg-red-900/30 rounded-lg flex items-center justify-center">
                                <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
                            </div>
                            <div>
                                <p className="text-sm text-gray-500 dark:text-gray-400">مرفوضة</p>
                                <p className="text-lg font-bold text-gray-900 dark:text-white">
                                    {filteredTasks.reduce((sum, task) => {
                                        const rejectedCount = Object.values(task.userStatuses || {}).filter(
                                            (status: any) => status.status === 'rejected'
                                        ).length;
                                        return sum + rejectedCount;
                                    }, 0)}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Modals */}
            <CreateTaskModal 
                isOpen={isCreateModalOpen} 
                onClose={() => setIsCreateModalOpen(false)} 
                onSubmit={onCreateTask}
                employees={employees}
            />
        </div>
    );
};