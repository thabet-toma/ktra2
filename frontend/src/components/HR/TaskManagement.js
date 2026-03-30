import React, { useState, useMemo } from 'react';
import { List, Eye, Users, FileText, CheckCircle, XCircle, Clock } from 'lucide-react';

const StatusBadge = ({ status }) => {
    const style = {
        'NEW': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
        'IN_PROGRESS': 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
        'WAITING_FOR_REVIEW': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300',
        'COMPLETED': 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
        'REJECTED': 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
    }[status] || 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    
    const text = {
        'NEW': 'لم تبدأ',
        'IN_PROGRESS': 'قيد التنفيذ',
        'WAITING_FOR_REVIEW': 'مسلمة',
        'COMPLETED': 'مكتملة',
        'REJECTED': 'مرفوضة',
    }[status] || status;
    
    return <span className={`px-3 py-1 text-sm font-semibold rounded-full ${style}`}>{text}</span>;
}

const PriorityIndicator = ({ priority }) => {
    const getPriorityInfo = (p) => {
        switch (p) {
            case 'LOW':
                return { text: 'منخفضة', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-100 dark:bg-green-900/30' };
            case 'MEDIUM':
                return { text: 'متوسطة', color: 'text-yellow-600 dark:text-yellow-400', bg: 'bg-yellow-100 dark:bg-yellow-900/30' };
            case 'HIGH':
                return { text: 'عالية', color: 'text-orange-600 dark:text-orange-400', bg: 'bg-orange-100 dark:bg-orange-900/30' };
            case 'URGENT':
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

const EmployeeStatusSummary = ({ assignedTo, usersMap, status }) => {
    // simplified for Django backend
    if (!assignedTo) return <span className="text-gray-500 text-sm">غير معين</span>;
    return (
        <div className="flex items-center gap-3">
            <span className="text-gray-900 dark:text-gray-100 font-medium">{usersMap[assignedTo] || 'مجهول'}</span>
            <StatusBadge status={status} />
        </div>
    );
};

export const TaskManagement = ({ 
    allTasks = [], 
    users = [], 
    onCreateTask, 
    onSelectTask,
    onUpdateSubmissionStatus 
}) => {
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [statusFilter, setStatusFilter] = useState('All');
    const [employeeFilter, setEmployeeFilter] = useState('All');
    const [priorityFilter, setPriorityFilter] = useState('All');
    const [viewMode, setViewMode] = useState('list');
    const [selectedTaskForSubmissions, setSelectedTaskForSubmissions] = useState(null);

    const usersMap = useMemo(() => {
        return users.reduce((acc, user) => {
            acc[user.id] = user.username || user.first_name;
            return acc;
        }, {});
    }, [users]);

    const filteredTasks = useMemo(() => {
        return allTasks.filter(task => {
            const employeeMatch = employeeFilter === 'All' || task.assigned_to === parseInt(employeeFilter);
            if (!employeeMatch) return false;
            
            const priorityMatch = priorityFilter === 'All' || task.priority === priorityFilter;
            if (!priorityMatch) return false;
            
            if (statusFilter === 'All') return true;
            return task.status === statusFilter;
        });
    }, [allTasks, statusFilter, employeeFilter, priorityFilter]);

    const overallStats = useMemo(() => {
        return {
            totalTasks: allTasks.length,
            activeTasks: allTasks.filter(task => task.status === 'IN_PROGRESS' || task.status === 'WAITING_FOR_REVIEW').length,
            completedTasks: allTasks.filter(task => task.status === 'COMPLETED').length,
            urgentTasks: allTasks.filter(task => task.priority === 'URGENT').length,
        };
    }, [allTasks]);

    return (
        <div className="animate-fade-in p-6">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div>
                    <h1 className="text-2xl md:text-3xl font-bold text-gray-800 dark:text-gray-100">إدارة المهام</h1>
                    <p className="text-gray-600 dark:text-gray-400 mt-2">
                        إجمالي المهام: <span className="font-bold">{overallStats.totalTasks}</span> | 
                        نشطة: <span className="font-bold text-blue-600 dark:text-blue-400">{overallStats.activeTasks}</span> | 
                        مكتملة: <span className="font-bold text-green-600 dark:text-green-400">{overallStats.completedTasks}</span>
                        {overallStats.urgentTasks > 0 && (
                            <span className="ml-4">عاجلة: <span className="font-bold text-red-600 dark:text-red-400">{overallStats.urgentTasks}</span></span>
                        )}
                    </p>
                </div>
                <button
                    onClick={() => {if(onCreateTask) setIsCreateModalOpen(true)}}
                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 md:px-6 rounded-lg transition"
                >
                    <span className="text-lg">+</span> مهمة جديدة
                </button>
            </div>

            <div className="mb-6 bg-white dark:bg-gray-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label className="block text-sm font-medium mb-1">حالة المهمة</label>
                        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="w-full p-2 border rounded-lg bg-white">
                            <option value="All">جميع الحالات</option>
                            <option value="NEW">لم تبدأ</option>
                            <option value="IN_PROGRESS">قيد التنفيذ</option>
                            <option value="WAITING_FOR_REVIEW">مسلمة</option>
                            <option value="COMPLETED">مكتملة</option>
                            <option value="REJECTED">مرفوضة</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium mb-1">الموظف</label>
                        <select value={employeeFilter} onChange={e => setEmployeeFilter(e.target.value)} className="w-full p-2 border rounded-lg bg-white">
                            <option value="All">كل الموظفين</option>
                            {users.map(u => <option key={u.id} value={u.id}>{u.username || u.first_name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium mb-1">الأولوية</label>
                        <select value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)} className="w-full p-2 border rounded-lg bg-white">
                            <option value="All">جميع الأولويات</option>
                            <option value="LOW">منخفضة</option>
                            <option value="MEDIUM">متوسطة</option>
                            <option value="HIGH">عالية</option>
                            <option value="URGENT">عاجلة</option>
                        </select>
                    </div>
                </div>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border overflow-hidden">
                <table className="w-full text-right">
                    <thead className="bg-gray-50 border-b">
                        <tr>
                            <th className="p-4 font-semibold text-gray-600">المهمة</th>
                            <th className="p-4 font-semibold text-gray-600">الموظف</th>
                            <th className="p-4 font-semibold text-gray-600">الأولوية</th>
                            <th className="p-4 font-semibold text-gray-600">الإجراءات</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y">
                        {filteredTasks.map(task => (
                            <tr key={task.id} onClick={() => onSelectTask && onSelectTask(task)} className="hover:bg-gray-50 cursor-pointer transition-colors">
                                <td className="p-4">
                                    <h3 className="font-bold text-gray-900">{task.title}</h3>
                                    <p className="text-xs text-gray-500 line-clamp-2">{task.description}</p>
                                </td>
                                <td className="p-4"><EmployeeStatusSummary assignedTo={task.assigned_to} usersMap={usersMap} status={task.status} /></td>
                                <td className="p-4"><PriorityIndicator priority={task.priority} /></td>
                                <td className="p-4">
                                    <button onClick={(e) => { e.stopPropagation(); onSelectTask && onSelectTask(task); }} className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg">
                                        <Eye className="w-4 h-4" />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

        </div>
    );
};
