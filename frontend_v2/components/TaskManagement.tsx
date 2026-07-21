/**
 * N7-T2 — TaskManagement (H2) — AseelDenseTable لإدارة المهام
 */
import React, { useState, useMemo, useRef } from 'react';
import { Task, User, TaskPriority } from '../types';
import { CreateTaskModal } from './CreateTaskModal';
import { List, Eye, CheckCircle, XCircle, Clock, FileText, RefreshCw, Plus } from 'lucide-react';
import { AllSubmissionsView } from './tasks/AllSubmissionsView';
import { AseelDenseTable, type DenseColumn } from './aseel/AseelDenseTable';
import { useAseelIndexKeymap } from './aseel/useAseelIndexKeymap';

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

const PRIORITY_LABELS: Record<string, string> = { low: 'منخفضة', medium: 'متوسطة', high: 'عالية', urgent: 'عاجلة' };
const PRIORITY_COLORS: Record<string, string> = {
    low:    'var(--aseel-ok, #267346)',
    medium: 'var(--aseel-warn, #b8800a)',
    high:   'var(--aseel-warn, #b8800a)',
    urgent: 'var(--aseel-danger, #c00)',
};
const STATUS_LABELS: Record<string, string> = {
    not_started: 'لم تبدأ',
    in_progress: 'قيد التنفيذ',
    submitted:   'مسلمة',
    completed:   'مكتملة',
    rejected:    'مرفوضة',
};

const getTaskCompletionRate = (task: Task): number => {
    const assignedCount = Array.isArray(task.assignedTo) ? task.assignedTo.length : 1;
    const completedCount = Object.values(task.userStatuses || {}).filter((s: any) => s.status === 'completed').length;
    return assignedCount > 0 ? Math.round((completedCount / assignedCount) * 100) : 0;
};

export const TaskManagement: React.FC<TaskManagementProps> = ({
    allTasks,
    users,
    onCreateTask,
    onSelectTask,
    onUpdateSubmissionStatus,
}) => {
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [statusFilter, setStatusFilter] = useState('All');
    const [employeeFilter, setEmployeeFilter] = useState('All');
    const [priorityFilter, setPriorityFilter] = useState('All');
    const [viewMode, setViewMode] = useState<'list' | 'submissions'>('list');
    const [selectedTaskForSubmissions, setSelectedTaskForSubmissions] = useState<Task | null>(null);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    const usersMap = useMemo(() => users.reduce((acc, u) => { acc[u.id] = u.name; return acc; }, {} as Record<string, string>), [users]);
    const employees = useMemo(() => users.filter(u => u.role === 'employee' || u.role === 'procurement'), [users]);

    const filteredTasks = useMemo(() => {
        return allTasks.filter(task => {
            const employeeMatch = employeeFilter === 'All' || task.assignedTo.includes(employeeFilter);
            if (!employeeMatch) return false;
            const priorityMatch = priorityFilter === 'All' || task.priority === priorityFilter;
            if (!priorityMatch) return false;
            if (statusFilter === 'All') return true;
            const statusMap: Record<string, string[]> = {
                'Not Started': ['not_started'], 'In Progress': ['in_progress'],
                'Submitted': ['submitted'], 'Completed': ['completed'], 'Rejected': ['rejected'],
            };
            if (employeeFilter !== 'All') {
                const userStatus = task.userStatuses?.[employeeFilter]?.status || 'not_started';
                return statusMap[statusFilter]?.includes(userStatus) || false;
            }
            const targets = statusMap[statusFilter];
            if (!targets) return false;
            return task.assignedTo.some(uid => targets.includes(task.userStatuses?.[uid]?.status || 'not_started'));
        });
    }, [allTasks, statusFilter, employeeFilter, priorityFilter]);

    const stats = useMemo(() => ({
        total: allTasks.length,
        active: allTasks.filter(t => t.assignedTo.some(uid => ['in_progress', 'submitted'].includes(t.userStatuses?.[uid]?.status || 'not_started'))).length,
        completed: allTasks.filter(t => t.assignedTo.some(uid => (t.userStatuses?.[uid]?.status || '') === 'completed')).length,
        urgent: allTasks.filter(t => t.priority === 'urgent').length,
    }), [allTasks]);

    useAseelIndexKeymap(
        { CtrlIns: () => setIsCreateModalOpen(true), Escape: () => { setStatusFilter('All'); setEmployeeFilter('All'); setPriorityFilter('All'); } },
        { enabled: viewMode === 'list' && !isCreateModalOpen },
    );

    if (viewMode === 'submissions' && selectedTaskForSubmissions && onUpdateSubmissionStatus) {
        return (
            <div dir="rtl" style={{ padding: '8px 12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <button className="aseel-toolbtn" onClick={() => { setViewMode('list'); setSelectedTaskForSubmissions(null); }}>← رجوع</button>
                    <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>
                        تسليمات: {selectedTaskForSubmissions.title}
                    </strong>
                </div>
                <AllSubmissionsView
                    task={selectedTaskForSubmissions}
                    users={employees}
                    onUpdateSubmissionStatus={onUpdateSubmissionStatus}
                    onOpenSubmissionDetail={(s) => console.log('submission detail', s)}
                    onSendReminder={(uid) => alert(`تم إرسال تذكير للموظف ${usersMap[uid] || uid}`)}
                />
            </div>
        );
    }

    const columns: DenseColumn<Task>[] = [
        {
            key: 'title',
            header: 'المهمة',
            width: '240px',
            render: (t) => {
                const rate = getTaskCompletionRate(t);
                const isOverdue = new Date(t.dueDate) < new Date();
                return (
                    <span>
                        <b style={{ color: 'var(--aseel-ink)' }}>{t.title}</b>
                        {isOverdue && <span style={{ marginRight: 4, fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-danger, #c00)' }}>متأخرة</span>}
                        {rate > 0 && <span style={{ marginRight: 4, fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>{rate}%</span>}
                    </span>
                );
            },
        },
        {
            key: 'assignedTo',
            header: 'الموظفون',
            width: '160px',
            render: (t) => {
                const assigned = Array.isArray(t.assignedTo) ? t.assignedTo : [t.assignedTo];
                const completed = Object.values(t.userStatuses || {}).filter((s: any) => s.status === 'completed').length;
                const inProgress = Object.values(t.userStatuses || {}).filter((s: any) => s.status === 'in_progress' || s.status === 'submitted').length;
                const rejected = Object.values(t.userStatuses || {}).filter((s: any) => s.status === 'rejected').length;
                return (
                    <span style={{ fontSize: 'var(--aseel-fs-sm)', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                        <span style={{ color: 'var(--aseel-ink-soft)' }}>{assigned.length} موظف</span>
                        {completed > 0 && <span style={{ color: 'var(--aseel-ok, #267346)' }}><CheckCircle style={{ width: 11, height: 11, display: 'inline' }} />{completed}</span>}
                        {inProgress > 0 && <span style={{ color: 'var(--aseel-accent, #1857a4)' }}><Clock style={{ width: 11, height: 11, display: 'inline' }} />{inProgress}</span>}
                        {rejected > 0 && <span style={{ color: 'var(--aseel-danger, #c00)' }}><XCircle style={{ width: 11, height: 11, display: 'inline' }} />{rejected}</span>}
                    </span>
                );
            },
        },
        {
            key: 'priority',
            header: 'الأولوية',
            width: '80px',
            align: 'center',
            render: (t) => (
                <span style={{ color: PRIORITY_COLORS[t.priority] || 'inherit', fontWeight: 500, fontSize: 'var(--aseel-fs-sm)' }}>
                    {PRIORITY_LABELS[t.priority] || t.priority}
                </span>
            ),
        },
        {
            key: 'dueDate',
            header: 'تاريخ التسليم',
            width: '100px',
            render: (t) => {
                const isOverdue = new Date(t.dueDate) < new Date();
                return <span style={{ color: isOverdue ? 'var(--aseel-danger, #c00)' : 'inherit' }}>{t.dueDate}</span>;
            },
        },
        {
            key: 'actions',
            header: '',
            width: '80px',
            align: 'center',
            render: (t) => (
                <span style={{ display: 'inline-flex', gap: 2 }}>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px' }}
                        onClick={(e) => { e.stopPropagation(); onSelectTask(t); }}
                        title="عرض التفاصيل"
                    >
                        <Eye style={{ width: 13, height: 13 }} />
                    </button>
                    {onUpdateSubmissionStatus && (
                        <button
                            className="aseel-toolbtn"
                            style={{ padding: '2px 4px' }}
                            onClick={(e) => { e.stopPropagation(); setSelectedTaskForSubmissions(t); setViewMode('submissions'); }}
                            title="التسليمات"
                        >
                            <List style={{ width: 13, height: 13 }} />
                        </button>
                    )}
                </span>
            ),
        },
    ];

    return (
        <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 6, padding: '8px 12px' }}>
            {/* شريط العنوان */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>إدارة المهام</strong>
                <span className="aseel-status-item">الإجمالي: <b>{stats.total}</b></span>
                <span className="aseel-status-item">نشطة: <b style={{ color: 'var(--aseel-accent, #1857a4)' }}>{stats.active}</b></span>
                <span className="aseel-status-item">مكتملة: <b style={{ color: 'var(--aseel-ok, #267346)' }}>{stats.completed}</b></span>
                {stats.urgent > 0 && <span className="aseel-status-item">عاجلة: <b style={{ color: 'var(--aseel-danger, #c00)' }}>{stats.urgent}</b></span>}
                <div style={{ flex: 1 }} />
                <select className="aseel-input" style={{ width: 130 }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                    <option value="All">جميع الحالات</option>
                    {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k === 'not_started' ? 'Not Started' : k === 'in_progress' ? 'In Progress' : k === 'submitted' ? 'Submitted' : k === 'completed' ? 'Completed' : 'Rejected'}>{v}</option>)}
                </select>
                <select className="aseel-input" style={{ width: 130 }} value={employeeFilter} onChange={e => setEmployeeFilter(e.target.value)}>
                    <option value="All">كل الموظفين</option>
                    {employees.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
                <select className="aseel-input" style={{ width: 110 }} value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}>
                    <option value="All">جميع الأولويات</option>
                    {Object.entries(PRIORITY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <button className="aseel-toolbtn" onClick={() => { setStatusFilter('All'); setEmployeeFilter('All'); setPriorityFilter('All'); }} title="إعادة تعيين"><RefreshCw style={{ width: 14, height: 14 }} /></button>
                <button className="aseel-toolbtn" onClick={() => setIsCreateModalOpen(true)} title="مهمة جديدة (Ctrl+Ins)">
                    <Plus style={{ width: 14, height: 14 }} /> مهمة جديدة
                </button>
            </div>

            <AseelDenseTable<Task>
                columns={columns}
                rows={filteredTasks}
                getRowKey={t => t.id}
                onRowDoubleClick={onSelectTask}
                emptyHint="لا توجد مهام — اضغط «مهمة جديدة»"
                footer={
                    filteredTasks.length > 0 ? (
                        <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                            المُعيَّنون: <b>{filteredTasks.reduce((s, t) => s + (Array.isArray(t.assignedTo) ? t.assignedTo.length : 1), 0)}</b>
                        </span>
                    ) : undefined
                }
            />

            <CreateTaskModal
                isOpen={isCreateModalOpen}
                onClose={() => setIsCreateModalOpen(false)}
                onSubmit={onCreateTask}
                employees={employees}
            />
        </div>
    );
};
