import React, { useState, useEffect } from 'react';
import { User, DailyPoints } from '../types';
import { pointsHistoryService } from '../services/firestoreService';

interface PointsHistoryPageProps {
    user: User;
}

export const PointsHistoryPage: React.FC<PointsHistoryPageProps> = ({ user }) => {
    const [pointsHistory, setPointsHistory] = useState<DailyPoints[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedPeriod, setSelectedPeriod] = useState<'week' | 'month' | 'all'>('week');
    const [todayPoints, setTodayPoints] = useState<DailyPoints | null>(null);

    useEffect(() => {
        loadPointsHistory();
        loadTodayPoints();
    }, [selectedPeriod]);

    const loadPointsHistory = async () => {
        setLoading(true);
        try {
            const endDate = new Date().toISOString().split('T')[0];
            let startDate = new Date();
            
            switch (selectedPeriod) {
                case 'week':
                    startDate.setDate(startDate.getDate() - 7);
                    break;
                case 'month':
                    startDate.setDate(startDate.getDate() - 30);
                    break;
                case 'all':
                    startDate = new Date('2024-01-01');
                    break;
            }
            
            const startDateStr = startDate.toISOString().split('T')[0];
            const history = await pointsHistoryService.getPointsHistory(user.id, startDateStr, endDate);
            
            setPointsHistory(history.sort((a, b) => b.date.localeCompare(a.date)));
        } catch (error) {
            console.error('Error loading points history:', error);
        } finally {
            setLoading(false);
        }
    };

    const loadTodayPoints = () => {
        pointsHistoryService.subscribeToDailyPoints(user.id, setTodayPoints);
    };

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString('ar-SA', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            calendar: 'gregory'
        });
    };

    const getTotalStats = () => {
        const totalPoints = pointsHistory.reduce((sum, day) => sum + day.totalPoints, 0);
        const totalActivityPoints = pointsHistory.reduce((sum, day) => sum + day.activityPoints, 0);
        const totalTaskPoints = pointsHistory.reduce((sum, day) => sum + day.taskPoints, 0);
        const totalAttendancePoints = pointsHistory.reduce((sum, day) => sum + (day.attendancePoints || 0), 0); // جديد
        const totalCheckins = pointsHistory.reduce((sum, day) => sum + day.checkinClicks, 0);
        const totalTasks = pointsHistory.reduce((sum, day) => sum + day.completedTasks, 0);
        const attendanceDays = pointsHistory.filter(day => day.attended).length; // جديد

        return { 
            totalPoints, 
            totalActivityPoints, 
            totalTaskPoints, 
            totalAttendancePoints, // جديد
            totalCheckins, 
            totalTasks,
            attendanceDays // جديد
        };
    };

    const totalStats = getTotalStats();

    if (loading) {
        return (
            <div className="animate-fade-in">
                <div className="flex items-center justify-center h-64">
                    <div className="text-lg text-gray-500">جاري تحميل سجل النقاط...</div>
                </div>
            </div>
        );
    }

    return (
        <div className="animate-fade-in">
            <div className="flex flex-col lg:flex-row gap-6 mb-6">
                {/* العنوان والتحكم */}
                <div className="flex-1">
                    <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-100 mb-2">
                        سجل نقاطي
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 mb-4">
                        تتبع أدائك ونقاطك اليومية
                    </p>
                    
                    <div className="flex gap-2">
                        {['week', 'month', 'all'].map((period) => (
                            <button
                                key={period}
                                onClick={() => setSelectedPeriod(period as any)}
                                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                                    selectedPeriod === period
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                                }`}
                            >
                                {period === 'week' && 'أسبوع'}
                                {period === 'month' && 'شهر'}
                                {period === 'all' && 'الكامل'}
                            </button>
                        ))}
                    </div>
                </div>

                {/* إحصائيات اليوم */}
                {todayPoints && (
                    <div className="bg-gradient-to-r from-green-500 to-emerald-600 rounded-2xl p-6 text-white shadow-lg">
                        <h3 className="text-lg font-bold mb-4">نقاط اليوم</h3>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="text-center">
                                <div className="text-2xl font-bold">{todayPoints.totalPoints}</div>
                                <div className="text-sm opacity-90">إجمالي النقاط</div>
                            </div>
                            <div className="text-center">
                                <div className="text-2xl font-bold">{todayPoints.checkinClicks}</div>
                                <div className="text-sm opacity-90">ضغطات النشاط</div>
                            </div>
                            <div className="text-center">
                                <div className="text-2xl font-bold">{todayPoints.activityPoints}</div>
                                <div className="text-sm opacity-90">نقاط النشاط</div>
                            </div>
                            <div className="text-center">
                                <div className="text-2xl font-bold">{todayPoints.taskPoints}</div>
                                <div className="text-sm opacity-90">نقاط المهام</div>
                            </div>
                            {/* جديد: نقاط الحضور */}
                            <div className="text-center">
                                <div className="text-2xl font-bold">{todayPoints.attendancePoints || 0}</div>
                                <div className="text-sm opacity-90">نقاط الحضور</div>
                            </div>
                            <div className="text-center">
                                <div className="text-2xl font-bold">{todayPoints.attended ? '✅' : '❌'}</div>
                                <div className="text-sm opacity-90">الحضور</div>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* الإحصائيات الإجمالية */}
            <div className="grid grid-cols-2 md:grid-cols-5 lg:grid-cols-7 gap-4 mb-6">
                <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-md border border-gray-200 dark:border-gray-700 text-center">
                    <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{totalStats.totalPoints}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">إجمالي النقاط</div>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-md border border-gray-200 dark:border-gray-700 text-center">
                    <div className="text-2xl font-bold text-green-600 dark:text-green-400">{totalStats.totalActivityPoints}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">نقاط النشاط</div>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-md border border-gray-200 dark:border-gray-700 text-center">
                    <div className="text-2xl font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)]">{totalStats.totalTaskPoints}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">نقاط المهام</div>
                </div>
                {/* جديد: نقاط الحضور */}
                <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-md border border-gray-200 dark:border-gray-700 text-center">
                    <div className="text-2xl font-bold text-orange-600 dark:text-orange-400">{totalStats.totalAttendancePoints}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">نقاط الحضور</div>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-md border border-gray-200 dark:border-gray-700 text-center">
                    <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">{totalStats.totalCheckins}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">ضغطات النشاط</div>
                </div>
                <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-md border border-gray-200 dark:border-gray-700 text-center">
                    <div className="text-2xl font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)]">{totalStats.totalTasks}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">مهام مكتملة</div>
                </div>
                {/* جديد: أيام الحضور */}
                <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-md border border-gray-200 dark:border-gray-700 text-center">
                    <div className="text-2xl font-bold text-[var(--color-primary)] dark:text-[var(--color-primary)]">{totalStats.attendanceDays}</div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">أيام حضور</div>
                </div>
            </div>

            {/* جدول النقاط اليومية */}
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-right">
                        <thead className="bg-gray-50 dark:bg-gray-700/50">
                            <tr>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">التاريخ</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">نقاط النشاط</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">ضغطات النشاط</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">نقاط المهام</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">نقاط الحضور</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">مهام مكتملة</th>
                                <th className="p-4 font-semibold text-gray-600 dark:text-gray-300">الإجمالي</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                            {pointsHistory.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="p-8 text-center text-gray-500 dark:text-gray-400">
                                        لا توجد بيانات للنقاط في الفترة المحددة
                                    </td>
                                </tr>
                            ) : (
                                pointsHistory.map((day) => (
                                    <tr key={day.date} className="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                                        <td className="p-4 font-medium text-gray-800 dark:text-gray-100">
                                            {formatDate(day.date)}
                                        </td>
                                        <td className="p-4">
                                            <div className="flex items-center gap-2">
                                                <span className="text-green-600 dark:text-green-400 font-bold">
                                                    {day.activityPoints}
                                                </span>
                                                <span className="text-xs text-gray-500">نقطة</span>
                                            </div>
                                        </td>
                                        <td className="p-4 text-gray-600 dark:text-gray-300">
                                            {day.checkinClicks} ضغطة
                                        </td>
                                        <td className="p-4">
                                            <div className="flex items-center gap-2">
                                                <span className="text-[var(--color-primary)] dark:text-[var(--color-primary)] font-bold">
                                                    {day.taskPoints}
                                                </span>
                                                <span className="text-xs text-gray-500">نقطة</span>
                                            </div>
                                        </td>
                                        {/* جديد: نقاط الحضور */}
                                        <td className="p-4">
                                            <div className="flex items-center gap-2">
                                                <span className={`font-bold ${
                                                    (day.attendancePoints || 0) > 0 
                                                        ? 'text-orange-600 dark:text-orange-400' 
                                                        : 'text-gray-400'
                                                }`}>
                                                    {day.attendancePoints || 0}
                                                </span>
                                                <span className="text-xs text-gray-500">نقطة</span>
                                                {day.attended && (
                                                    <span className="text-xs text-green-600">✅</span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="p-4 text-gray-600 dark:text-gray-300">
                                            {day.completedTasks} مهمة
                                        </td>
                                        <td className="p-4">
                                            <div className="flex items-center gap-2 justify-end">
                                                <span className="text-lg font-bold text-blue-600 dark:text-blue-400">
                                                    {day.totalPoints}
                                                </span>
                                                <span className="text-xs text-gray-500">نقطة</span>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* معلومات إضافية */}
            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-xl border border-blue-200 dark:border-blue-800">
                    <h4 className="font-bold text-blue-800 dark:text-blue-200 mb-2">كيفية كسب النقاط؟</h4>
                    <ul className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                        <li>• كل ضغطة على زر "تأكيد الاستمرار" = 1 نقطة</li>
                        <li>• إكمال المهمة في أقل من 30 دقيقة = 10 نقاط</li>
                        <li>• إكمال المهمة في أكثر من 30 دقيقة = 5 نقاط</li>
                        <li>• <strong>الحضور اليومي = 10 نقاط كاملة ✅</strong></li>
                        <li>• الحد الأقصى للنقاط اليومية = 50 نقطة</li>
                    </ul>
                </div>
                
                <div className="bg-green-50 dark:bg-green-900/20 p-4 rounded-xl border border-green-200 dark:border-green-800">
                    <h4 className="font-bold text-green-800 dark:text-green-200 mb-2">نصائح لزيادة النقاط</h4>
                    <ul className="text-sm text-green-700 dark:text-green-300 space-y-1">
                        <li>• <strong>احرص على الحضور اليومي لتحصل على 10 نقاط مجانية</strong></li>
                        <li>• اضغط زر التأكيد كل 10 دقائق للحفاظ على النشاط</li>
                        <li>• ركز على إكمال المهام بسرعة وجودة عالية</li>
                        <li>• خطط لمهامك مسبقاً لتقليل الوقت المستغرق</li>
                        <li>• حافظ على استمرارية العمل لتجميع نقاط النشاط</li>
                    </ul>
                </div>
            </div>
        </div>
    );
};