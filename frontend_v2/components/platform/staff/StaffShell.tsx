import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { ConfirmProvider } from '../../../contexts/ConfirmContext';
import { ToastProvider } from '../../../contexts/ToastContext';
import { useAuth } from '../../../contexts/AuthContext';
import { usePlatformStaffCapabilitiesState } from '../../../hooks/usePlatformStaffCapabilities';
import { getMyPlatformEmployeeProfile, type MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
import { staffNav, staffRouteForPath, type StaffNavKey } from '../../../utils/staffNav';
import { ChampionsPanel } from '../ChampionsPanel';
import { EmployeeCompaniesPanel } from '../EmployeeCompaniesPanel';
import { EmployeeSelfWalletCard } from '../EmployeeSelfWalletCard';
import { MyMeetingsPanel } from '../MyMeetingsPanel';
import { MyProfileCard } from '../MyProfileCard';
import { WorkOrdersPanel } from '../WorkOrdersPanel';
import { StaffHomeDashboard } from './StaffHomeDashboard';
import { StaffSidebar } from './StaffSidebar';
import { StaffTopBar } from './StaffTopBar';
import { CrmPanel } from './crm/CrmPanel';

/**
 * لوحةُ «لا شيء لتعرضه» — **مكوّنٌ واحدٌ لا أربعُ نسخ.**
 *
 * كانت هذه الأصنافُ العشرةُ مكتوبةً حرفيّاً أربعَ مرّاتٍ في سلسلة الشروط أدناه
 * (تحميلُ التقييم · لا ملفَّ للتقييم · تحميلُ الملفّ · لا ملفَّ أصلاً)، فتعديلُ
 * واحدةٍ منها كان يتركُ الثلاثَ الأخرى متباينةً بصمت — وهو أوّلُ ما يُفسد اتّساقَ
 * التصميم بين التبويبات.
 */
const StaffNotice: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="rounded-2xl border border-[var(--staff-line)] bg-[var(--staff-panel)] p-8 text-sm text-[var(--staff-muted)] shadow-lg shadow-black/30">
    {children}
  </p>
);

const StaffShellContent: React.FC = () => {
  const { currentUser, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { capabilities, loading: capabilitiesLoading } = usePlatformStaffCapabilitiesState(currentUser?.id ? String(currentUser.id) : undefined, Boolean(currentUser?.isSuperAdmin));
  const [profile, setProfile] = useState<MyPlatformEmployeeProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const searchTerm = useMemo(() => new URLSearchParams(location.search).get('search') || '', [location.search]);
  const allowed = capabilities.is_platform_employee || capabilities.is_platform_admin;
  const activePath = staffRouteForPath(location.pathname);
  const activeKey = staffNav.find((item) => item.path === activePath)?.key || 'home';

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);
    try { setProfile(await getMyPlatformEmployeeProfile(currentUser?.id)); } catch { setProfile(null); } finally { setProfileLoading(false); }
  }, [currentUser?.id]);

  useEffect(() => { if (!capabilitiesLoading && allowed) void loadProfile(); }, [allowed, capabilitiesLoading, loadProfile]);
  const go = (key: StaffNavKey) => { navigate(staffNav.find((item) => item.key === key)?.path || '/staff/home'); setDrawerOpen(false); };
  const search = (term: string) => navigate(term ? `/staff/home?search=${encodeURIComponent(term)}` : '/staff/home');

  if (authLoading || capabilitiesLoading) return <div className="staff-shell flex min-h-screen items-center justify-center gap-2 bg-[var(--staff-bg)] text-sm text-[var(--staff-muted)]" dir="rtl"><Loader2 className="h-5 w-5 animate-spin text-cyan-400" />جارٍ التحقق من الصلاحيات...</div>;
  if (!currentUser) return <Navigate to="/staff" replace />;
  if (!allowed) return <Navigate to="/" replace />;

  // خريطةُ مفتاحٍ ← لوحة، لا سلسلةَ شروطٍ بسِتّ طبقات: الربطُ صار مقروءاً سطراً
  // لكلّ تبويب، ويحرسه `test_every_navigation_entry_has_a_panel_behind_it`.
  // وبناءُ عنصرِ JSX لا يشغّل مكوّنَه، فالتبويباتُ غيرُ المعروضة لا تُصيَّر.
  const panels: Record<StaffNavKey, React.ReactNode> = {
    home: <StaffHomeDashboard profile={profile} searchTerm={searchTerm} onOpenTasks={() => go('tasks')} />,
    tasks: <WorkOrdersPanel />,
    companies: <EmployeeCompaniesPanel />,
    meetings: <MyMeetingsPanel />,
    // `space-y-6` لأنّ هذا التبويبَ وحدَه يحمل لوحتين: بلا الفاصلِ كانتا تتلاصقان
    // حدّاً بحدٍّ بينما كلُّ تبويبٍ آخرَ لوحةٌ واحدةٌ بهامشها.
    performance: (
      <div className="space-y-6">
        {profileLoading ? <StaffNotice>جارٍ تحميل تقييمك...</StaffNotice>
          : profile ? <EmployeeSelfWalletCard employeeId={profile.id} />
            : <StaffNotice>لا يوجد ملف موظف مرتبط بالحساب لعرض تقييمه.</StaffNotice>}
        <ChampionsPanel />
      </div>
    ),
    profile: profileLoading ? <StaffNotice>جارٍ تحميل ملفك...</StaffNotice>
      : profile ? <MyProfileCard profile={profile} onSaved={() => void loadProfile()} />
        : <StaffNotice>لا يوجد ملف موظف مرتبط بهذا الحساب.</StaffNotice>,
    crm: <CrmPanel isManager={capabilities.is_platform_admin} myEmployeeId={profile?.id ?? null} />,
  };
  const content = panels[activeKey];

  return <div className="staff-shell flex min-h-screen overflow-x-hidden bg-[var(--staff-bg)] text-[var(--staff-text)]" dir="rtl"><StaffSidebar activeKey={activeKey} collapsed={collapsed} drawerOpen={drawerOpen} profile={profile} onNavigate={go} onToggleCollapsed={() => setCollapsed((value) => !value)} onCloseDrawer={() => setDrawerOpen(false)} /><div className="flex min-w-0 flex-1 flex-col"><StaffTopBar profile={profile} searchTerm={searchTerm} onSearch={search} onOpenDrawer={() => setDrawerOpen(true)} /><main className="min-w-0 flex-1 p-4 sm:p-6">{content}</main></div></div>;
};

export const StaffShell: React.FC = () => <ToastProvider><ConfirmProvider><StaffShellContent /></ConfirmProvider></ToastProvider>;

export default StaffShell;
