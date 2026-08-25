/**
 * N7-T1 — Dashboard — KPI Kit-style summary blocks
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { Task, User, AppView } from '../types';
import { QuickActions } from './dashboard/QuickActions';
import { TasksDistributionChart } from './dashboard/TasksDistributionChart';
import { useTenantSettings } from '../hooks/useTenantSettings';
import { useCompany } from '../contexts/CompanyContext';
import { formatDateValue } from "../utils/formatDate";

interface DashboardProps {
    tasks: Task[];
    users: User[];
    onNavigate: (view: AppView, targetId?: string) => void;
    currentUser: User;
}

export const Dashboard: React.FC<DashboardProps> = ({ tasks, users, onNavigate, currentUser }) => {
    // M2: هوية الشركة النشطة — لا أسماء ثابتة
    const { identity } = useTenantSettings();
    const { currentCompany } = useCompany();
    const companyName =
        identity?.company_name_primary || currentCompany?.CompanyName || 'الشركة النشطة';
    const companySub = identity?.company_name_sub || 'نظام إدارة عمليات الاستيراد والمشتريات المتكامل';

    const totalTasks = tasks.length;
    const completedTasks = tasks.filter(t => t.status === 'COMPLETED').length;
    const pendingTasks = tasks.filter(t => ['NEW', 'IN_PROGRESS', 'WAITING_FOR_REVIEW'].includes(t.status)).length;
    const totalUsers = users.length;
    const completionRate = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

    return (
        <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 10, padding: '8px 12px' }}>
            {/* شريط KPI */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 6, borderBottom: '1px solid var(--ktra-border)' }}>
                <strong style={{ fontSize: 'var(--ktra-fs-title, 14px)', color: 'var(--ktra-ink)' }}>
                    مرحباً، {currentUser.name.split(' ')[0]}
                </strong>
                <span className="ktra-status-item">الإجمالي: <b>{totalTasks}</b></span>
                <span className="ktra-status-item">نشطة: <b style={{ color: 'var(--ktra-accent, #1857a4)' }}>{pendingTasks}</b></span>
                <span className="ktra-status-item">مكتملة: <b style={{ color: 'var(--ktra-ok, #267346)' }}>{completedTasks}</b></span>
                <span className="ktra-status-item">الإنجاز: <b>{completionRate}%</b></span>
                <span className="ktra-status-item">المستخدمون: <b>{totalUsers}</b></span>
            </div>

            {/* المحتوى الرئيسي */}
            <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0 }}>
                {/* العمود الأيمن: الرسوم البيانية + الشركة */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, minWidth: 0 }}>
                    <TasksDistributionChart tasks={tasks} />

                    <div style={{ background: 'var(--ktra-accent, #1857a4)', borderRadius: 8, padding: '12px 16px', color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            {identity?.logo_url && (
                                <img
                                    src={identity.logo_url}
                                    alt={`شعار ${companyName}`}
                                    style={{ width: 36, height: 36, borderRadius: 6, objectFit: 'cover', background: '#fff' }}
                                />
                            )}
                            <div>
                                <div style={{ fontWeight: 700, fontSize: 'var(--ktra-fs-base, 13px)' }}>{companyName}</div>
                                <div style={{ fontSize: 'var(--ktra-fs-sm, 11px)', opacity: 0.9, marginTop: 3 }}>
                                    {companySub}
                                </div>
                            </div>
                        </div>
                        <Link
                            to="/about-us"
                            style={{ padding: '4px 12px', background: '#fff', color: 'var(--ktra-accent, #1857a4)', borderRadius: 6, fontSize: 'var(--ktra-fs-sm, 11px)', fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap' }}
                        >
                            عرض التفاصيل
                        </Link>
                    </div>
                </div>

                {/* العمود الأيسر: الاختصارات + النشاطات */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: 220, flexShrink: 0 }}>
                    <QuickActions onNavigate={onNavigate} userRole={currentUser.role} />

                    <div style={{ border: '1px solid var(--ktra-border)', borderRadius: 6, overflow: 'hidden' }}>
                        <div style={{ padding: '5px 10px', borderBottom: '1px solid var(--ktra-border)', fontWeight: 600, fontSize: 'var(--ktra-fs-base, 13px)', color: 'var(--ktra-ink)' }}>
                            آخر النشاطات
                        </div>
                        {tasks.slice(0, 5).map(task => (
                            <div key={task.id} style={{ padding: '4px 10px', borderBottom: '1px solid var(--ktra-border)', fontSize: 'var(--ktra-fs-sm, 11px)' }}>
                                <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--ktra-ink)' }}>{task.title}</div>
                                <div style={{ color: 'var(--ktra-ink-soft)', fontSize: '10px' }}>{formatDateValue(task.updatedAt)}</div>
                            </div>
                        ))}
                        {tasks.length === 0 && (
                            <div style={{ padding: '8px 10px', color: 'var(--ktra-ink-soft)', fontSize: 'var(--ktra-fs-sm, 11px)', textAlign: 'center' }}>
                                لا توجد نشاطات حديثة
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
