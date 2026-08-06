/**
 * N7-T4 — EmployeePointsManagement (H4) — AseelDenseTable لإدارة نقاط الموظفين
 */
import React, { useState, useEffect, useMemo } from 'react';
import { User, DailyPoints, ActivityStatus } from '../types';
import { pointsHistoryService, activityService } from '../services/firestoreService';
import { autoDisableScheduler } from '../services/autoDisableScheduler';
import { AseelDenseTable, type DenseColumn } from './aseel/AseelDenseTable';
import { formatDateValue, formatWeekdayName } from '../utils/formatDate';

interface EmployeePointsManagementProps {
    users: User[];
}

interface UserStats { [userId: string]: { totalPoints: number; totalActivityPoints: number; totalTaskPoints: number } }
interface DailyUserPoints { userId: string; userName: string; dailyPoints: DailyPoints | null }
interface DailyDisableSettings { startTime: string; endTime: string; isEnabled: boolean }

export const EmployeePointsManagement: React.FC<EmployeePointsManagementProps> = ({ users }) => {
    const [selectedUser, setSelectedUser] = useState<User | null>(null);
    const [userPoints, setUserPoints] = useState<DailyPoints[]>([]);
    const [userActivity, setUserActivity] = useState<ActivityStatus | null>(null);
    const [loading, setLoading] = useState(false);
    const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
    const [manualPoints, setManualPoints] = useState({ activityPoints: 0, taskPoints: 0 });
    const [showAdjustModal, setShowAdjustModal] = useState(false);
    const [userStats, setUserStats] = useState<UserStats>({});
    const [viewMode, setViewMode] = useState<'user' | 'daily'>('user');
    const [dailyUsersPoints, setDailyUsersPoints] = useState<DailyUserPoints[]>([]);
    const [sortBy, setSortBy] = useState<'points' | 'name'>('points');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
    const [showGlobalSettingsModal, setShowGlobalSettingsModal] = useState(false);
    const [globalDailyDisableSettings, setGlobalDailyDisableSettings] = useState<DailyDisableSettings>({ startTime: '00:00', endTime: '00:00', isEnabled: false });

    const employees = users.filter(u => u.role === 'employee');

    useEffect(() => { loadAllUsersStats(); loadGlobalSettings(); }, [users]);
    useEffect(() => { if (selectedUser && viewMode === 'user') loadUserData(); }, [selectedUser, selectedDate, viewMode]);
    useEffect(() => { if (viewMode === 'daily') loadDailyUsersData(); }, [selectedDate, viewMode, employees.length]);

    const loadGlobalSettings = async () => {
        try {
            const settings = await activityService.getGlobalDailyDisableSchedule();
            if (settings) setGlobalDailyDisableSettings(settings);
        } catch (e) { console.error(e); }
    };

    const loadAllUsersStats = async () => {
        const stats: UserStats = {};
        for (const user of employees) {
            try {
                const endDate = new Date().toISOString().split('T')[0];
                const startDate = new Date(); startDate.setDate(startDate.getDate() - 30);
                const history = await pointsHistoryService.getPointsHistory(user.id, startDate.toISOString().split('T')[0], endDate);
                stats[user.id] = {
                    totalPoints: history.reduce((s, d) => s + d.totalPoints, 0),
                    totalActivityPoints: history.reduce((s, d) => s + d.activityPoints, 0),
                    totalTaskPoints: history.reduce((s, d) => s + d.taskPoints, 0),
                };
            } catch { stats[user.id] = { totalPoints: 0, totalActivityPoints: 0, totalTaskPoints: 0 }; }
        }
        setUserStats(stats);
    };

    const loadUserData = async () => {
        if (!selectedUser) return;
        setLoading(true);
        try {
            const endDate = new Date().toISOString().split('T')[0];
            const startDate = new Date(); startDate.setDate(startDate.getDate() - 30);
            const history = await pointsHistoryService.getPointsHistory(selectedUser.id, startDate.toISOString().split('T')[0], endDate);
            setUserPoints(history.sort((a, b) => b.date.localeCompare(a.date)));
            setUserActivity(await activityService.getActivityStatus(selectedUser.id));
            const daily = await pointsHistoryService.getDailyPoints(selectedUser.id, selectedDate);
            setManualPoints({ activityPoints: daily?.activityPoints || 0, taskPoints: daily?.taskPoints || 0 });
        } catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const loadDailyUsersData = async () => {
        setLoading(true);
        try {
            const data: DailyUserPoints[] = [];
            for (const user of employees) {
                try {
                    data.push({ userId: user.id, userName: user.name, dailyPoints: await pointsHistoryService.getDailyPoints(user.id, selectedDate) });
                } catch { data.push({ userId: user.id, userName: user.name, dailyPoints: null }); }
            }
            setDailyUsersPoints(data);
        } catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const handleAdjustPoints = async () => {
        if (!selectedUser) return;
        try {
            await pointsHistoryService.updatePointsManually(selectedUser.id, selectedDate, manualPoints);
            setShowAdjustModal(false);
            loadUserData();
        } catch { alert('حدث خطأ أثناء تعديل النقاط'); }
    };

    const handleToggleCheckInButton = async (enabled: boolean) => {
        if (!selectedUser) return;
        try {
            await activityService.toggleCheckInButton(selectedUser.id, enabled);
            setUserActivity(prev => prev ? { ...prev, checkInButtonEnabled: enabled } : null);
            alert(`تم ${enabled ? 'تفعيل' : 'تعطيل'} زر التأكيد للموظف`);
        } catch { alert('حدث خطأ أثناء تعديل إعدادات الزر'); }
    };

    const handleSaveGlobalDailyDisableSettings = async () => {
        try {
            await activityService.setGlobalDailyDisableSchedule(globalDailyDisableSettings.startTime, globalDailyDisableSettings.endTime, globalDailyDisableSettings.isEnabled);
            setShowGlobalSettingsModal(false);
            await loadGlobalSettings();
            alert('تم حفظ إعدادات التعطيل اليومي العامة بنجاح');
        } catch { alert('حدث خطأ أثناء حفظ الإعدادات'); }
    };

    const getTotalStats = (userId: string) => userStats[userId] || { totalPoints: 0, totalActivityPoints: 0, totalTaskPoints: 0 };

    const formatDate = (dateStr: string) => `${formatWeekdayName(dateStr)} ${formatDateValue(dateStr)}`.trim();

    const sortedDailyUsers = useMemo(() => {
        return [...dailyUsersPoints].sort((a, b) => {
            const pa = a.dailyPoints?.totalPoints || 0, pb = b.dailyPoints?.totalPoints || 0;
            if (sortBy === 'points') return sortOrder === 'desc' ? pb - pa : pa - pb;
            return sortOrder === 'desc' ? b.userName.localeCompare(a.userName) : a.userName.localeCompare(b.userName);
        });
    }, [dailyUsersPoints, sortBy, sortOrder]);

    // columns for userPoints table (user mode)
    const userPointsCols: DenseColumn<DailyPoints>[] = [
        { key: 'date', header: 'التاريخ', width: '180px', render: (d) => <span>{formatDate(d.date)}</span> },
        { key: 'activityPoints', header: 'نقاط النشاط', width: '100px', align: 'center', render: (d) => <b style={{ color: 'var(--aseel-ok, #267346)' }}>{d.activityPoints}</b> },
        { key: 'checkinClicks', header: 'ضغطات النشاط', width: '100px', align: 'center', render: (d) => <>{d.checkinClicks}</> },
        { key: 'taskPoints', header: 'نقاط المهام', width: '100px', align: 'center', render: (d) => <b style={{ color: 'var(--aseel-accent, #1857a4)' }}>{d.taskPoints}</b> },
        { key: 'completedTasks', header: 'مهام مكتملة', width: '100px', align: 'center', render: (d) => <>{d.completedTasks}</> },
        { key: 'totalPoints', header: 'الإجمالي', width: '100px', align: 'center', numeric: true, render: (d) => <b style={{ color: 'var(--aseel-accent, #1857a4)', fontSize: 'var(--aseel-fs-base)' }}>{d.totalPoints}</b> },
    ];

    // columns for daily users table (daily mode)
    const dailyUsersCols: DenseColumn<DailyUserPoints>[] = [
        { key: 'userName', header: 'الموظف', width: '140px', render: (d) => <b>{d.userName}</b> },
        { key: 'activityPoints', header: 'نقاط النشاط', width: '100px', align: 'center', render: (d) => <b style={{ color: 'var(--aseel-ok, #267346)' }}>{d.dailyPoints?.activityPoints || 0}</b> },
        { key: 'checkinClicks', header: 'ضغطات النشاط', width: '100px', align: 'center', render: (d) => <>{d.dailyPoints?.checkinClicks || 0}</> },
        { key: 'taskPoints', header: 'نقاط المهام', width: '100px', align: 'center', render: (d) => <b style={{ color: 'var(--aseel-accent, #1857a4)' }}>{d.dailyPoints?.taskPoints || 0}</b> },
        { key: 'completedTasks', header: 'مهام مكتملة', width: '100px', align: 'center', render: (d) => <>{d.dailyPoints?.completedTasks || 0}</> },
        { key: 'totalPoints', header: 'الإجمالي', width: '100px', align: 'center', numeric: true, render: (d) => <b style={{ color: 'var(--aseel-accent, #1857a4)' }}>{d.dailyPoints?.totalPoints || 0}</b> },
    ];

    return (
        <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 12px', height: '100%' }}>
            {/* العنوان */}
            <div style={{ paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>إدارة نقاط الموظفين</strong>
            </div>

            {/* إعدادات النشاط العامة */}
            <div style={{ border: '1px solid var(--aseel-border)', borderRadius: 6, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>
                    تعطيل زر النشاط:
                    <b style={{ marginRight: 4, color: globalDailyDisableSettings.isEnabled ? 'var(--aseel-danger, #c00)' : 'var(--aseel-ok, #267346)' }}>
                        {globalDailyDisableSettings.isEnabled ? `من ${globalDailyDisableSettings.startTime} إلى ${globalDailyDisableSettings.endTime}` : 'معطل'}
                    </b>
                </span>
                <span style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>
                    المجدول:
                    <b style={{ marginRight: 4, color: autoDisableScheduler.getStatus().isRunning ? 'var(--aseel-ok, #267346)' : 'var(--aseel-danger, #c00)' }}>
                        {autoDisableScheduler.getStatus().isRunning ? '🟢 نشط' : '🔴 متوقف'}
                    </b>
                </span>
                <div style={{ flex: 1 }} />
                <button className="aseel-toolbtn" onClick={() => setShowGlobalSettingsModal(true)}>تعديل الإعدادات</button>
                <button className="aseel-toolbtn" onClick={() => autoDisableScheduler.manualCheck().then(() => alert('تم التحقق يدوياً'))}>تحقق الآن</button>
                <button
                    className="aseel-toolbtn"
                    style={{ color: autoDisableScheduler.getStatus().isRunning ? 'var(--aseel-danger, #c00)' : 'var(--aseel-ok, #267346)' }}
                    onClick={() => autoDisableScheduler.getStatus().isRunning ? autoDisableScheduler.stop() : autoDisableScheduler.start()}
                >
                    {autoDisableScheduler.getStatus().isRunning ? 'إيقاف المجدول' : 'تشغيل المجدول'}
                </button>
            </div>

            {/* وضع العرض + التاريخ */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <button className="aseel-toolbtn" style={{ fontWeight: viewMode === 'user' ? 700 : undefined, background: viewMode === 'user' ? 'var(--aseel-accent, #1857a4)' : undefined, color: viewMode === 'user' ? '#fff' : undefined }} onClick={() => setViewMode('user')}>
                    موظف محدد
                </button>
                <button className="aseel-toolbtn" style={{ fontWeight: viewMode === 'daily' ? 700 : undefined, background: viewMode === 'daily' ? 'var(--aseel-accent, #1857a4)' : undefined, color: viewMode === 'daily' ? '#fff' : undefined }} onClick={() => setViewMode('daily')}>
                    جميع الموظفين ليوم محدد
                </button>
                <div style={{ flex: 1 }} />
                <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>التاريخ:</label>
                <input type="date" className="aseel-input" style={{ width: 140 }} value={selectedDate} onChange={e => setSelectedDate(e.target.value)} />
            </div>

            {viewMode === 'user' ? (
                <>
                    {/* اختيار الموظف */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>الموظف:</label>
                        <select
                            className="aseel-input"
                            style={{ width: 260 }}
                            value={selectedUser?.id || ''}
                            onChange={e => setSelectedUser(users.find(u => u.id === e.target.value) || null)}
                        >
                            <option value="">اختر موظف...</option>
                            {employees.map(u => (
                                <option key={u.id} value={u.id}>{u.name} — {getTotalStats(u.id).totalPoints} نقطة</option>
                            ))}
                        </select>
                        {selectedUser && (
                            <>
                                <span className="aseel-status-item">النشاط: <b style={{ color: userActivity?.isCurrentlyActive ? 'var(--aseel-ok, #267346)' : 'var(--aseel-danger, #c00)' }}>{userActivity?.isCurrentlyActive ? 'نشط' : 'غير نشط'}</b></span>
                                <span className="aseel-status-item">زر التأكيد: <b style={{ color: userActivity?.checkInButtonEnabled !== false ? 'var(--aseel-ok, #267346)' : 'var(--aseel-danger, #c00)' }}>{userActivity?.checkInButtonEnabled !== false ? 'مفعل' : 'معطل'}</b></span>
                                <span className="aseel-status-item">إجمالي النقاط (30 يوم): <b>{getTotalStats(selectedUser.id).totalPoints}</b></span>
                                <div style={{ flex: 1 }} />
                                <button className="aseel-toolbtn" onClick={() => setShowAdjustModal(true)}>تعديل النقاط</button>
                                <button
                                    className="aseel-toolbtn"
                                    style={{ color: userActivity?.checkInButtonEnabled !== false ? 'var(--aseel-warn, #b8800a)' : 'var(--aseel-ok, #267346)' }}
                                    onClick={() => handleToggleCheckInButton(userActivity?.checkInButtonEnabled === false)}
                                >
                                    {userActivity?.checkInButtonEnabled !== false ? 'تعطيل زر التأكيد' : 'تفعيل زر التأكيد'}
                                </button>
                            </>
                        )}
                    </div>

                    {selectedUser && (
                        <AseelDenseTable<DailyPoints>
                            columns={userPointsCols}
                            rows={userPoints}
                            getRowKey={d => d.date}
                            loading={loading}
                            emptyHint="لا توجد بيانات للنقاط"
                            footer={
                                userPoints.length > 0 ? (
                                    <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                                        الإجمالي: <b>{userPoints.reduce((s, d) => s + d.totalPoints, 0)}</b> نقطة
                                    </span>
                                ) : undefined
                            }
                        />
                    )}
                </>
            ) : (
                <>
                    {/* فرز عرض اليوم */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>الترتيب:</span>
                        <select className="aseel-input" style={{ width: 160 }} value={sortBy} onChange={e => setSortBy(e.target.value as 'points' | 'name')}>
                            <option value="points">حسب النقاط</option>
                            <option value="name">حسب الاسم</option>
                        </select>
                        <select className="aseel-input" style={{ width: 100 }} value={sortOrder} onChange={e => setSortOrder(e.target.value as 'asc' | 'desc')}>
                            <option value="desc">تنازلي</option>
                            <option value="asc">تصاعدي</option>
                        </select>
                    </div>

                    <AseelDenseTable<DailyUserPoints>
                        columns={dailyUsersCols}
                        rows={sortedDailyUsers}
                        getRowKey={d => d.userId}
                        loading={loading}
                        emptyHint="لا توجد بيانات لهذا اليوم"
                        footer={
                            sortedDailyUsers.length > 0 ? (
                                <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                                    إجمالي النقاط: <b>{sortedDailyUsers.reduce((s, d) => s + (d.dailyPoints?.totalPoints || 0), 0)}</b>
                                </span>
                            ) : undefined
                        }
                    />
                </>
            )}

            {/* مودال تعديل النقاط */}
            {showAdjustModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 12 }}>
                    <div dir="rtl" style={{ background: 'var(--aseel-surface, #fff)', borderRadius: 8, padding: 20, width: '100%', maxWidth: 400 }}>
                        <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>تعديل النقاط لـ {selectedUser?.name}</strong>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
                            <div>
                                <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>التاريخ</label>
                                <input type="date" className="aseel-input" style={{ width: '100%', marginTop: 4 }} value={selectedDate} onChange={e => setSelectedDate(e.target.value)} />
                            </div>
                            <div>
                                <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>نقاط النشاط</label>
                                <input type="number" className="aseel-input" style={{ width: '100%', marginTop: 4 }} value={manualPoints.activityPoints} onChange={e => setManualPoints(p => ({ ...p, activityPoints: parseInt(e.target.value) || 0 }))} />
                            </div>
                            <div>
                                <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>نقاط المهام</label>
                                <input type="number" className="aseel-input" style={{ width: '100%', marginTop: 4 }} value={manualPoints.taskPoints} onChange={e => setManualPoints(p => ({ ...p, taskPoints: parseInt(e.target.value) || 0 }))} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                            <button className="aseel-toolbtn" onClick={() => setShowAdjustModal(false)}>إلغاء</button>
                            <button className="aseel-toolbtn" style={{ color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }} onClick={handleAdjustPoints}>حفظ التعديلات</button>
                        </div>
                    </div>
                </div>
            )}

            {/* مودال الإعدادات العامة */}
            {showGlobalSettingsModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 12 }}>
                    <div dir="rtl" style={{ background: 'var(--aseel-surface, #fff)', borderRadius: 8, padding: 20, width: '100%', maxWidth: 400 }}>
                        <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>إعداد التعطيل اليومي العام</strong>
                        <p style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)', marginTop: 8 }}>سيُطبَّق على زر النشاط لجميع الموظفين يومياً.</p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>
                                <input type="checkbox" checked={globalDailyDisableSettings.isEnabled} onChange={e => setGlobalDailyDisableSettings(p => ({ ...p, isEnabled: e.target.checked }))} />
                                تفعيل التعطيل اليومي التلقائي
                            </label>
                            <div style={{ display: 'flex', gap: 10 }}>
                                <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>وقت البدء</label>
                                    <input type="time" className="aseel-input" style={{ width: '100%', marginTop: 4 }} value={globalDailyDisableSettings.startTime} disabled={!globalDailyDisableSettings.isEnabled} onChange={e => setGlobalDailyDisableSettings(p => ({ ...p, startTime: e.target.value }))} />
                                </div>
                                <div style={{ flex: 1 }}>
                                    <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>وقت الانتهاء</label>
                                    <input type="time" className="aseel-input" style={{ width: '100%', marginTop: 4 }} value={globalDailyDisableSettings.endTime} disabled={!globalDailyDisableSettings.isEnabled} onChange={e => setGlobalDailyDisableSettings(p => ({ ...p, endTime: e.target.value }))} />
                                </div>
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
                            <button className="aseel-toolbtn" onClick={() => setShowGlobalSettingsModal(false)}>إلغاء</button>
                            <button className="aseel-toolbtn" style={{ color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }} onClick={handleSaveGlobalDailyDisableSettings}>حفظ الإعدادات</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
