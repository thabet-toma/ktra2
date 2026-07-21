/**
 * N7-T3 — AttendanceManagement (H3) — AseelDenseTable لإدارة الحضور
 */
import React, { useState, useEffect, useRef } from 'react';
import { User, AttendanceSession, AttendanceRecord } from '../types';
import { attendanceService } from '../services/attendanceService';
import { format, parseISO } from 'date-fns';
import { ar } from 'date-fns/locale';
import { RefreshCw } from 'lucide-react';
import { AseelDenseTable, type DenseColumn } from './aseel/AseelDenseTable';
import { useAseelIndexKeymap } from './aseel/useAseelIndexKeymap';

interface AttendanceManagementProps {
    users: User[];
    currentUser: User;
}

export const AttendanceManagement: React.FC<AttendanceManagementProps> = ({ users, currentUser }) => {
    const [activeSession, setActiveSession] = useState<AttendanceSession | null>(null);
    const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
    const [attendanceRecords, setAttendanceRecords] = useState<AttendanceRecord[]>([]);
    const [loading, setLoading] = useState(false);
    const [timeLeft, setTimeLeft] = useState<number>(0);
    const [searchTerm, setSearchTerm] = useState('');
    const [attendanceFilter, setAttendanceFilter] = useState<'all' | 'present' | 'absent'>('all');
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    const employees = users.filter(u => u.role === 'employee' || u.role === 'procurement');

    useEffect(() => { loadActiveSession(); loadAttendanceRecords(); }, [selectedDate]);

    useEffect(() => {
        let interval: NodeJS.Timeout;
        if (activeSession) {
            const endTime = new Date(activeSession.startTime).getTime() + 5 * 60 * 1000;
            interval = setInterval(() => {
                const remaining = Math.max(0, endTime - Date.now());
                setTimeLeft(Math.ceil(remaining / 1000));
                if (remaining === 0) loadActiveSession();
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [activeSession]);

    const loadActiveSession = async () => {
        try { setActiveSession(await attendanceService.getActiveSession()); } catch (e) { console.error(e); }
    };

    const loadAttendanceRecords = async () => {
        setLoading(true);
        try { setAttendanceRecords(await attendanceService.getAttendanceRecords(selectedDate)); } catch (e) { console.error(e); } finally { setLoading(false); }
    };

    const handleStartSession = async () => {
        try { setLoading(true); await attendanceService.startAttendanceSession(currentUser.id); await loadActiveSession(); } catch { alert('حدث خطأ أثناء بدء جلسة الحضور'); } finally { setLoading(false); }
    };

    const handleEndSession = async () => {
        if (!activeSession) return;
        try { setLoading(true); await attendanceService.endAttendanceSession(activeSession.id); setActiveSession(null); setTimeLeft(0); } catch { alert('حدث خطأ أثناء إنهاء جلسة الحضور'); } finally { setLoading(false); }
    };

    const handleManualAttendance = async (userId: string, attended: boolean) => {
        try {
            setLoading(true);
            await attendanceService.updateAttendanceManually(userId, selectedDate, attended);
            await loadAttendanceRecords();
            alert(attended ? 'تم تسجيل الحضور بنجاح! +10 نقاط ✅' : 'تم إلغاء الحضور بنجاح! -10 نقاط ❌');
        } catch { alert('حدث خطأ أثناء تعديل الحضور'); } finally { setLoading(false); }
    };

    const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    const getEmployeeAttendance = (uid: string) => attendanceRecords.find(r => r.userId === uid);
    const formatArabicDate = (d: string) => format(parseISO(d), 'EEEE، d MMMM yyyy', { locale: ar });

    const filteredEmployees = employees.filter(emp => {
        if (!emp.name.toLowerCase().includes(searchTerm.toLowerCase())) return false;
        const hasAttended = !!getEmployeeAttendance(emp.id);
        if (attendanceFilter === 'present') return hasAttended;
        if (attendanceFilter === 'absent') return !hasAttended;
        return true;
    });

    const presentCount = employees.filter(e => !!getEmployeeAttendance(e.id)).length;

    useAseelIndexKeymap(
        { F5: () => loadAttendanceRecords(), F6: () => searchInputRef.current?.focus(), Escape: () => { setSearchTerm(''); setAttendanceFilter('all'); } },
        { enabled: !loading },
    );

    const columns: DenseColumn<User>[] = [
        {
            key: 'name',
            header: 'الموظف',
            width: '150px',
            render: (emp) => <b style={{ color: 'var(--aseel-ink)' }}>{emp.name}</b>,
        },
        {
            key: 'email',
            header: 'البريد الإلكتروني',
            width: '180px',
            render: (emp) => <span style={{ color: 'var(--aseel-ink-soft)', fontSize: 'var(--aseel-fs-sm)' }}>{emp.email}</span>,
        },
        {
            key: 'status',
            header: 'الحضور',
            width: '80px',
            align: 'center',
            render: (emp) => {
                const hasAttended = !!getEmployeeAttendance(emp.id);
                return (
                    <span style={{ fontWeight: 600, color: hasAttended ? 'var(--aseel-ok, #267346)' : 'var(--aseel-danger, #c00)', fontSize: 'var(--aseel-fs-sm)' }}>
                        {hasAttended ? 'حاضر' : 'غائب'}
                    </span>
                );
            },
        },
        {
            key: 'time',
            header: 'وقت التسجيل',
            width: '100px',
            render: (emp) => {
                const rec = getEmployeeAttendance(emp.id);
                return <span style={{ color: 'var(--aseel-ink-soft)', fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{rec ? new Date(rec.attendedAt).toLocaleTimeString('ar-EG') : '—'}</span>;
            },
        },
        {
            key: 'points',
            header: 'النقاط',
            width: '60px',
            align: 'center',
            render: (emp) => {
                const hasAttended = !!getEmployeeAttendance(emp.id);
                return <span style={{ fontWeight: 700, color: hasAttended ? 'var(--aseel-ok, #267346)' : 'var(--aseel-ink-soft)' }}>{hasAttended ? '+10' : '0'}</span>;
            },
        },
        {
            key: 'actions',
            header: '',
            width: '140px',
            align: 'center',
            render: (emp) => {
                const hasAttended = !!getEmployeeAttendance(emp.id);
                return (
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 6px', fontSize: 'var(--aseel-fs-sm)', color: hasAttended ? 'var(--aseel-danger, #c00)' : 'var(--aseel-ok, #267346)' }}
                        onClick={() => handleManualAttendance(emp.id, !hasAttended)}
                        disabled={loading}
                    >
                        {hasAttended ? 'إلغاء حضور (-10)' : 'تسجيل حضور (+10)'}
                    </button>
                );
            },
        },
    ];

    return (
        <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 6, padding: '8px 12px' }}>
            {/* جلسة الحضور */}
            <div style={{ border: '1px solid var(--aseel-border)', borderRadius: 6, padding: '10px 14px', background: activeSession ? 'var(--aseel-surface-accent, #f0f5ff)' : undefined }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: 'var(--aseel-fs-base, 13px)', color: 'var(--aseel-ink)' }}>جلسة الحضور</strong>
                    <span style={{ color: 'var(--aseel-ink-soft)', fontSize: 'var(--aseel-fs-sm)' }}>
                        {activeSession ? `نشطة — متبقي ${formatTime(timeLeft)}` : 'لا توجد جلسة نشطة'}
                    </span>
                    {activeSession && (
                        <span style={{ color: 'var(--aseel-ink-soft)', fontSize: 'var(--aseel-fs-sm)' }}>
                            بدأت: {new Date(activeSession.startTime).toLocaleTimeString('ar-EG')}
                        </span>
                    )}
                    <div style={{ flex: 1 }} />
                    {!activeSession ? (
                        <button className="aseel-toolbtn" style={{ padding: '4px 10px', color: 'var(--aseel-ok, #267346)' }} onClick={handleStartSession} disabled={loading}>
                            بدء جلسة جديدة
                        </button>
                    ) : (
                        <button className="aseel-toolbtn" style={{ padding: '4px 10px', color: 'var(--aseel-danger, #c00)' }} onClick={handleEndSession} disabled={loading}>
                            إنهاء الجلسة
                        </button>
                    )}
                </div>
            </div>

            {/* شريط الفلاتر */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>
                    تقرير يوم {formatArabicDate(selectedDate)}
                </strong>
                <span className="aseel-status-item">الحضور: <b style={{ color: 'var(--aseel-ok, #267346)' }}>{presentCount}</b> / {employees.length}</span>
                <span className="aseel-status-item">الغياب: <b style={{ color: 'var(--aseel-danger, #c00)' }}>{employees.length - presentCount}</b></span>
                <div style={{ flex: 1 }} />
                <input
                    type="date"
                    className="aseel-input"
                    style={{ width: 140 }}
                    value={selectedDate}
                    onChange={e => setSelectedDate(e.target.value)}
                />
                <select className="aseel-input" style={{ width: 100 }} value={attendanceFilter} onChange={e => setAttendanceFilter(e.target.value as 'all' | 'present' | 'absent')}>
                    <option value="all">الكل</option>
                    <option value="present">حاضر</option>
                    <option value="absent">غائب</option>
                </select>
                <input
                    ref={searchInputRef}
                    className="aseel-input"
                    style={{ width: 150 }}
                    placeholder="بحث بالاسم… (F6)"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                />
                <button className="aseel-toolbtn" onClick={() => { setSearchTerm(''); setAttendanceFilter('all'); }} title="إعادة تعيين">
                    <RefreshCw style={{ width: 14, height: 14 }} />
                </button>
            </div>

            <AseelDenseTable<User>
                columns={columns}
                rows={filteredEmployees}
                getRowKey={emp => emp.id}
                loading={loading}
                emptyHint="لا يوجد موظفون"
            />
        </div>
    );
};
