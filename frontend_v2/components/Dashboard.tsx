import React from 'react';
import { Link } from 'react-router-dom';
import { Task, User, AppView } from '../types';
import { StatCard } from './dashboard/StatCard';
import { QuickActions } from './dashboard/QuickActions';
import { TasksDistributionChart } from './dashboard/TasksDistributionChart';
import {
    CheckCircle,
    Clock,
    Users,
    ListTodo,
    TrendingUp,
    Activity
} from 'lucide-react';

interface DashboardProps {
    tasks: Task[];
    users: User[];
    onNavigate: (view: AppView, targetId?: string) => void;
    currentUser: User;
}

export const Dashboard: React.FC<DashboardProps> = ({ tasks, users, onNavigate, currentUser }) => {
    const totalTasks = tasks.length;
    const completedTasks = tasks.filter(t => t.status === 'COMPLETED').length;
    const pendingTasks = tasks.filter(t => ['NEW', 'IN_PROGRESS', 'WAITING_FOR_REVIEW'].includes(t.status)).length;
    const totalUsers = users.length;

    // Calculate completion rate
    const completionRate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

    return (
        <div className="space-y-6 animate-fade-in p-2">

            {/* Header Section with Greeting */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-2">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                        مرحباً، {currentUser.name.split(' ')[0]} 👋
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">
                        إليك نظرة عامة على أداء الشركة اليوم.
                    </p>
                </div>
                <div className="flex items-center gap-2 bg-blue-50 dark:bg-blue-900/20 px-3 py-1.5 rounded-full text-blue-700 dark:text-blue-300 text-sm font-medium">
                    <Activity className="w-4 h-4" />
                    <span>النظام يعمل بكفاءة 100%</span>
                </div>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    title="المهام النشطة"
                    value={pendingTasks}
                    icon={Clock}
                    color="orange"
                    description="مهام قيد التنفيذ أو المراجعة"
                />
                <StatCard
                    title="المهام المكتملة"
                    value={completedTasks}
                    icon={CheckCircle}
                    color="green"
                    trend={{ value: completionRate, isPositive: true }}
                    description="نسبة الإنجاز الكلية"
                />
                <StatCard
                    title="إجمالي المهام"
                    value={totalTasks}
                    icon={ListTodo}
                    color="blue"
                />
                <StatCard
                    title="المستخدمين"
                    value={totalUsers}
                    icon={Users}
                    color="indigo"
                    description="المستخدمين النشطين في النظام"
                />
            </div>

            {/* Main Content Info Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column: Charts */}
                <div className="lg:col-span-2 space-y-6">
                    <TasksDistributionChart tasks={tasks} />

                    {/* Company Info Box */}
                    <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-2xl p-6 text-white shadow-lg overflow-hidden relative">
                        <div className="relative z-10 flex justify-between items-center">
                            <div>
                                <h3 className="text-xl font-bold mb-2">شركة النور للتجارة العالمية</h3>
                                <p className="text-blue-100 max-w-lg text-sm leading-relaxed">
                                    نظام إدارة عمليات الاستيراد والمشتريات المتكامل. تتبع الطلبات، إدارة المهام، ومراقبة الشحنات في مكان واحد.
                                </p>
                            </div>
                            <Link to="/about-us" className="hidden sm:inline-block px-5 py-2.5 bg-white text-blue-700 rounded-xl font-bold shadow-md hover:bg-blue-50 transition-colors">
                                عرض التفاصيل
                            </Link>
                        </div>
                        {/* Abstract Background Shapes */}
                        <div className="absolute top-0 right-0 w-64 h-64 bg-white opacity-5 rounded-full -translate-y-1/2 translate-x-1/3"></div>
                        <div className="absolute bottom-0 left-0 w-48 h-48 bg-white opacity-10 rounded-full translate-y-1/3 -translate-x-1/4"></div>
                    </div>
                </div>

                {/* Right Column: Quick Actions & Activity */}
                <div className="space-y-6">
                    <QuickActions onNavigate={onNavigate} userRole={currentUser.role} />

                    {/* Placeholder for Recent Activity Listing */}
                    <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">آخر النشاطات</h3>
                            <button className="text-sm text-blue-600 hover:underline">عرض الكل</button>
                        </div>
                        <div className="space-y-4">
                            {tasks.slice(0, 5).map(task => (
                                <div key={task.id} className="flex gap-3 items-start pb-3 border-b border-gray-100 dark:border-gray-700 last:border-0 last:pb-0">
                                    <div className="mt-1 w-2 h-2 rounded-full bg-blue-500 flex-shrink-0"></div>
                                    <div>
                                        <p className="text-sm font-medium text-gray-800 dark:text-gray-200 line-clamp-1">{task.title}</p>
                                        <p className="text-xs text-gray-500">{new Date(task.updatedAt).toLocaleDateString('ar-EG')}</p>
                                    </div>
                                </div>
                            ))}
                            {tasks.length === 0 && <p className="text-sm text-gray-500 text-center py-4">لا توجد نشاطات حديثة</p>}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
