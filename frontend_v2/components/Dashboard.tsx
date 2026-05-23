/**
 * N7-T1 — Dashboard — KPI Aseel-style summary blocks
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { Task, User, AppView } from '../types';
import { QuickActions } from './dashboard/QuickActions';
import { TasksDistributionChart } from './dashboard/TasksDistributionChart';

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
    const completionRate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

    return (
        <div dir="rtl" data-skin="aseel" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 10, padding: '8px 12px' }}>
            {/* شريط KPI */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 6, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>
                    مرحباً، {currentUser.name.split(' ')[0]}
                </strong>
                <span className="aseel-status-item">الإجمالي: <b>{totalTasks}</b></span>
                <span className="aseel-status-item">نشطة: <b style={{ color: 'var(--aseel-accent, #1857a4)' }}>{pendingTasks}</b></span>
                <span className="aseel-status-item">مكتملة: <b style={{ color: 'var(--aseel-ok, #267346)' }}>{completedTasks}</b></span>
                <span className="aseel-status-item">الإنجاز: <b>{completionRate}%</b></span>
                <span className="aseel-status-item">المستخدمون: <b>{totalUsers}</b></span>
            </div>

            {/* المحتوى الرئيسي */}
            <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
                {/* العمود الأيمن: الرسوم البيانية + الشركة */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, minWidth: 0 }}>
                    <TasksDistributionChart tasks={tasks} />

                    <div style={{ background: 'var(--aseel-accent, #1857a4)', borderRadius: 8, padding: '12px 16px', color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                        <div>
                            <div style={{ fontWeight: 700, fontSize: 'var(--aseel-fs-base, 13px)' }}>شركة النور للتجارة العالمية</div>
                            <div style={{ fontSize: 'var(--aseel-fs-sm, 11px)', opacity: 0.9, marginTop: 3 }}>
                                نظام إدارة عمليات الاستيراد والمشتريات المتكامل
                            </div>
                        </div>
                        <Link
                            to="/about-us"
                            style={{ padding: '4px 12px', background: '#fff', color: 'var(--aseel-accent, #1857a4)', borderRadius: 6, fontSize: 'var(--aseel-fs-sm, 11px)', fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap' }}
                        >
                            عرض التفاصيل
                        </Link>
                    </div>
                </div>

                {/* العمود الأيسر: الاختصارات + النشاطات */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: 220, flexShrink: 0 }}>
                    <QuickActions onNavigate={onNavigate} userRole={currentUser.role} />

                    <div style={{ border: '1px solid var(--aseel-border)', borderRadius: 6, overflow: 'hidden' }}>
                        <div style={{ padding: '5px 10px', borderBottom: '1px solid var(--aseel-border)', fontWeight: 600, fontSize: 'var(--aseel-fs-base, 13px)', color: 'var(--aseel-ink)' }}>
                            آخر النشاطات
                        </div>
                        {tasks.slice(0, 5).map(task => (
                            <div key={task.id} style={{ padding: '4px 10px', borderBottom: '1px solid var(--aseel-border)', fontSize: 'var(--aseel-fs-sm, 11px)' }}>
                                <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--aseel-ink)' }}>{task.title}</div>
                                <div style={{ color: 'var(--aseel-ink-soft)', fontSize: '10px' }}>{new Date(task.updatedAt).toLocaleDateString('ar-EG')}</div>
                            </div>
                        ))}
                        {tasks.length === 0 && (
                            <div style={{ padding: '8px 10px', color: 'var(--aseel-ink-soft)', fontSize: 'var(--aseel-fs-sm, 11px)', textAlign: 'center' }}>
                                لا توجد نشاطات حديثة
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
