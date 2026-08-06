/**
 * N7-T5 — PointsHistoryPage (H5) — AseelDenseTable لسجل النقاط
 */
import React, { useState, useEffect, useMemo } from 'react';
import { User, DailyPoints } from '../types';
import { pointsHistoryService } from '../services/firestoreService';
import { AseelDenseTable, type DenseColumn } from './aseel/AseelDenseTable';
import { formatDateValue, formatWeekdayName } from '../utils/formatDate';

interface PointsHistoryPageProps {
    user: User;
}

export const PointsHistoryPage: React.FC<PointsHistoryPageProps> = ({ user }) => {
    const [pointsHistory, setPointsHistory] = useState<DailyPoints[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedPeriod, setSelectedPeriod] = useState<'week' | 'month' | 'all'>('week');
    const [todayPoints, setTodayPoints] = useState<DailyPoints | null>(null);

    useEffect(() => { loadPointsHistory(); }, [selectedPeriod]);
    useEffect(() => { pointsHistoryService.subscribeToDailyPoints(user.id, setTodayPoints); }, [user.id]);

    const loadPointsHistory = async () => {
        setLoading(true);
        try {
            const endDate = new Date().toISOString().split('T')[0];
            const startDate = new Date();
            if (selectedPeriod === 'week') startDate.setDate(startDate.getDate() - 7);
            else if (selectedPeriod === 'month') startDate.setDate(startDate.getDate() - 30);
            else startDate.setFullYear(2024, 0, 1);
            const history = await pointsHistoryService.getPointsHistory(user.id, startDate.toISOString().split('T')[0], endDate);
            setPointsHistory(history.sort((a, b) => b.date.localeCompare(a.date)));
        } catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const formatDate = (dateStr: string) => `${formatWeekdayName(dateStr)} ${formatDateValue(dateStr)}`.trim();

    const totalStats = useMemo(() => ({
        totalPoints: pointsHistory.reduce((s, d) => s + d.totalPoints, 0),
        totalActivityPoints: pointsHistory.reduce((s, d) => s + d.activityPoints, 0),
        totalTaskPoints: pointsHistory.reduce((s, d) => s + d.taskPoints, 0),
        totalAttendancePoints: pointsHistory.reduce((s, d) => s + (d.attendancePoints || 0), 0),
        totalCheckins: pointsHistory.reduce((s, d) => s + d.checkinClicks, 0),
        totalTasks: pointsHistory.reduce((s, d) => s + d.completedTasks, 0),
        attendanceDays: pointsHistory.filter(d => d.attended).length,
    }), [pointsHistory]);

    const columns: DenseColumn<DailyPoints>[] = [
        { key: 'date', header: 'التاريخ', width: '200px', sortable: true, render: (d) => <span>{formatDate(d.date)}</span> },
        { key: 'activityPoints', header: 'نقاط النشاط', width: '100px', align: 'center', numeric: true, sortable: true, render: (d) => <b style={{ color: 'var(--aseel-ok, #267346)' }}>{d.activityPoints}</b> },
        { key: 'checkinClicks', header: 'ضغطات النشاط', width: '110px', align: 'center', render: (d) => <>{d.checkinClicks} ضغطة</> },
        { key: 'taskPoints', header: 'نقاط المهام', width: '100px', align: 'center', numeric: true, render: (d) => <b style={{ color: 'var(--aseel-accent, #1857a4)' }}>{d.taskPoints}</b> },
        {
            key: 'attendancePoints',
            header: 'نقاط الحضور',
            width: '100px',
            align: 'center',
            render: (d) => (
                <span style={{ color: (d.attendancePoints || 0) > 0 ? 'var(--aseel-warn, #b8800a)' : 'var(--aseel-ink-soft)' }}>
                    {d.attendancePoints || 0}
                    {d.attended && <span style={{ marginRight: 3 }}>✅</span>}
                </span>
            ),
        },
        { key: 'completedTasks', header: 'مهام مكتملة', width: '100px', align: 'center', render: (d) => <>{d.completedTasks} مهمة</> },
        { key: 'totalPoints', header: 'الإجمالي', width: '90px', align: 'center', numeric: true, sortable: true, render: (d) => <b style={{ color: 'var(--aseel-accent, #1857a4)', fontSize: 'var(--aseel-fs-base)' }}>{d.totalPoints}</b> },
    ];

    return (
        <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8, padding: '8px 12px' }}>
            {/* شريط العنوان */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>سجل نقاطي</strong>
                <span className="aseel-status-item">الإجمالي: <b>{totalStats.totalPoints}</b></span>
                <span className="aseel-status-item">نشاط: <b style={{ color: 'var(--aseel-ok, #267346)' }}>{totalStats.totalActivityPoints}</b></span>
                <span className="aseel-status-item">مهام: <b style={{ color: 'var(--aseel-accent, #1857a4)' }}>{totalStats.totalTaskPoints}</b></span>
                <span className="aseel-status-item">حضور: <b style={{ color: 'var(--aseel-warn, #b8800a)' }}>{totalStats.attendanceDays} يوم</b></span>
                <div style={{ flex: 1 }} />
                {todayPoints && (
                    <span className="aseel-status-item">اليوم: <b>{todayPoints.totalPoints} نقطة</b></span>
                )}
                {(['week', 'month', 'all'] as const).map(p => (
                    <button
                        key={p}
                        className="aseel-toolbtn"
                        style={{ fontWeight: selectedPeriod === p ? 700 : undefined, background: selectedPeriod === p ? 'var(--aseel-accent, #1857a4)' : undefined, color: selectedPeriod === p ? '#fff' : undefined }}
                        onClick={() => setSelectedPeriod(p)}
                    >
                        {p === 'week' ? 'أسبوع' : p === 'month' ? 'شهر' : 'الكامل'}
                    </button>
                ))}
            </div>

            <AseelDenseTable<DailyPoints>
                columns={columns}
                rows={pointsHistory}
                getRowKey={d => d.date}
                loading={loading}
                emptyHint="لا توجد بيانات للنقاط في الفترة المحددة"
                footer={
                    pointsHistory.length > 0 ? (
                        <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                            مجموع: <b>{totalStats.totalPoints}</b> نقطة | ضغطات: <b>{totalStats.totalCheckins}</b> | مهام: <b>{totalStats.totalTasks}</b>
                        </span>
                    ) : undefined
                }
            />

            {/* معلومات إضافية */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 4 }}>
                <div style={{ border: '1px solid var(--aseel-accent, #1857a4)', borderRadius: 6, padding: '8px 12px', background: 'rgba(24,87,164,0.04)', fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>
                    <b style={{ display: 'block', marginBottom: 6, color: 'var(--aseel-accent, #1857a4)' }}>كيفية كسب النقاط؟</b>
                    <ul style={{ margin: 0, padding: 0, listStyle: 'none', lineHeight: 1.8 }}>
                        <li>• كل ضغطة على «تأكيد الاستمرار» = 1 نقطة</li>
                        <li>• إكمال المهمة أقل 30 دقيقة = 10 نقاط</li>
                        <li>• إكمال المهمة أكثر 30 دقيقة = 5 نقاط</li>
                        <li>• الحضور اليومي = 10 نقاط</li>
                        <li>• الحد الأقصى اليومي = 50 نقطة</li>
                    </ul>
                </div>
                <div style={{ border: '1px solid var(--aseel-ok, #267346)', borderRadius: 6, padding: '8px 12px', background: 'rgba(38,115,70,0.04)', fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>
                    <b style={{ display: 'block', marginBottom: 6, color: 'var(--aseel-ok, #267346)' }}>نصائح لزيادة النقاط</b>
                    <ul style={{ margin: 0, padding: 0, listStyle: 'none', lineHeight: 1.8 }}>
                        <li>• احرص على الحضور اليومي لتحصل على 10 نقاط</li>
                        <li>• اضغط زر التأكيد كل 10 دقائق</li>
                        <li>• ركز على إكمال المهام بسرعة وجودة</li>
                        <li>• خطط لمهامك مسبقاً</li>
                    </ul>
                </div>
            </div>
        </div>
    );
};
