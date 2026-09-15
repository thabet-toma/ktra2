import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { ConfirmProvider } from '../../../contexts/ConfirmContext';
import { ToastProvider } from '../../../contexts/ToastContext';
import { useAuth } from '../../../contexts/AuthContext';
import { usePlatformStaffCapabilitiesState } from '../../../hooks/usePlatformStaffCapabilities';
import { getMyPlatformEmployeeProfile, type MyPlatformEmployeeProfile } from '../../../services/platformEmployeeSpaceApi';
import { staffGate } from '../../../utils/staffAccess';
import { isStaffPreview } from '../../../utils/staffDoor';
import { staffNav, staffRouteForPath, type StaffNavKey } from '../../../utils/staffNav';
import { ChampionsPanel } from '../ChampionsPanel';
import { EmployeeCompaniesPanel } from '../EmployeeCompaniesPanel';
import { EmployeePayTermsCard } from '../EmployeePayTermsCard';
import { EmployeeSelfWalletCard } from '../EmployeeSelfWalletCard';
import { MyMeetingsPanel } from '../MyMeetingsPanel';
import { MyProfileCard } from '../MyProfileCard';
import { WorkOrdersPanel } from '../WorkOrdersPanel';
import { StaffHomeDashboard } from './StaffHomeDashboard';
import { StaffPresencePanel } from './StaffPresencePanel';
import { StaffSidebar } from './StaffSidebar';
import { StaffTopBar } from './StaffTopBar';
import { CrmPanel } from './crm/CrmPanel';
import { StaffTasksPanel } from './tasks/StaffTasksPanel';

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
  // 212-Q3: المالكُ يدخل بصلاحيّة `is_platform_admin` بلا صفِّ موظّف، فلوحاتُه
  // الشخصيّةُ فارغةٌ بحقّ. اللافتةُ تقول ذلك صراحةً كي لا يُقرأ الفراغُ عطباً —
  // وهو ما وقع فعلاً حين بحث عن أزرارٍ في مساحةٍ ليست مساحتَه.
  const preview = isStaffPreview({
    isSuperAdmin: Boolean(currentUser?.isSuperAdmin),
    profileSettled: !profileLoading,
    hasProfile: profile !== null,
  });

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);
    try { setProfile(await getMyPlatformEmployeeProfile(currentUser?.id)); } catch { setProfile(null); } finally { setProfileLoading(false); }
  }, [currentUser?.id]);

  useEffect(() => { if (!capabilitiesLoading && allowed) void loadProfile(); }, [allowed, capabilitiesLoading, loadProfile]);
  const go = (key: StaffNavKey) => { navigate(staffNav.find((item) => item.key === key)?.path || '/staff/home'); setDrawerOpen(false); };
  const search = (term: string) => navigate(term ? `/staff/home?search=${encodeURIComponent(term)}` : '/staff/home');

  // قرارُ البوّابة دالّةٌ خالصةٌ لا سلسلةُ شروطٍ هنا: الشرطُ المكتوبُ يدوياً كان
  // يقرأ جوابَ الصلاحيّات الفارغَ **قبل أن يُطلَب** على أنّه «ممنوع»، فيطرد
  // الموظّفَ إلى شاشة دوره بعد أن يرى `/staff/home` ثانيةً واحدة.
  const gate = staffGate({ authLoading, hasUser: Boolean(currentUser), pending: capabilitiesLoading, capabilities });
  if (gate === 'loading') return <div className="staff-shell flex min-h-screen items-center justify-center gap-2 bg-[var(--staff-bg)] text-sm text-[var(--staff-muted)]" dir="rtl"><Loader2 className="h-5 w-5 animate-spin text-cyan-400" />جارٍ التحقق من الصلاحيات...</div>;
  if (gate === 'login') return <Navigate to="/staff" replace />;
  if (gate === 'leave') return <Navigate to="/" replace />;

  // خريطةُ مفتاحٍ ← لوحة، لا سلسلةَ شروطٍ بسِتّ طبقات: الربطُ صار مقروءاً سطراً
  // لكلّ تبويب، ويحرسه `test_every_navigation_entry_has_a_panel_behind_it`.
  // وبناءُ عنصرِ JSX لا يشغّل مكوّنَه، فالتبويباتُ غيرُ المعروضة لا تُصيَّر.
  const panels: Record<StaffNavKey, React.ReactNode> = {
    home: <StaffHomeDashboard profile={profile} searchTerm={searchTerm} onOpenTasks={() => go('tasks')} />,
    tasks: <div className="space-y-6"><StaffTasksPanel /><section><h2 className="mb-3 text-lg font-bold text-[var(--staff-text)]">أوامر العمل</h2><WorkOrdersPanel /></section></div>,
    companies: <EmployeeCompaniesPanel />,
    meetings: <MyMeetingsPanel />,
    // `space-y-6` لأنّ هذا التبويبَ يحمل لوحتين: بلا الفاصلِ كانتا تتلاصقان
    // حدّاً بحدٍّ. و«تبويبُ الأداء وحدَه» لم يعد صحيحاً منذ #214-ج — تبويبُ
    // الملفّ صار لوحتين أيضاً (البطاقةُ الشخصيّةُ وشروطُ الصرف) فورث الفاصلَ نفسَه.
    performance: (
      <div className="space-y-6">
        {profileLoading ? <StaffNotice>جارٍ تحميل تقييمك...</StaffNotice>
          : profile ? <><StaffPresencePanel /><EmployeeSelfWalletCard employeeId={profile.id} /></>
            : <StaffNotice>لا يوجد ملف موظف مرتبط بالحساب لعرض تقييمه.</StaffNotice>}
        <ChampionsPanel />
      </div>
    ),
    profile: (
      <div className="space-y-6">
        {profileLoading ? <StaffNotice>جارٍ تحميل ملفك...</StaffNotice>
          : profile ? <><MyProfileCard profile={profile} onSaved={() => void loadProfile()} /><EmployeePayTermsCard employeeId={profile.id} /></>
            : <StaffNotice>لا يوجد ملف موظف مرتبط بهذا الحساب.</StaffNotice>}
      </div>
    ),
    crm: <CrmPanel isManager={capabilities.is_platform_admin} myEmployeeId={profile?.id ?? null} />,
  };
  const content = panels[activeKey];

  return <div className="staff-shell flex min-h-screen overflow-x-hidden bg-[var(--staff-bg)] text-[var(--staff-text)]" dir="rtl"><StaffSidebar activeKey={activeKey} collapsed={collapsed} drawerOpen={drawerOpen} profile={profile} onNavigate={go} onToggleCollapsed={() => setCollapsed((value) => !value)} onCloseDrawer={() => setDrawerOpen(false)} /><div className="flex min-w-0 flex-1 flex-col"><StaffTopBar profile={profile} searchTerm={searchTerm} onSearch={search} onOpenDrawer={() => setDrawerOpen(true)} /><main className="min-w-0 flex-1 p-4 sm:p-6">{preview && (
      <p className="mb-4 rounded-2xl border border-amber-400/40 bg-amber-400/10 p-4 text-sm text-amber-100" role="status">
        <span className="font-extrabold">معاينة.</span> هذه مساحةُ موظّف المنصّة كما يراها هو. حسابُك سوبر أدمن بلا ملفِّ
        موظّف، فاللوحاتُ الشخصيّة (تقييمك · محفظتك · مهامُّك · شركاتك) تظهر فارغةً — وهذا ليس عطباً.
      </p>
    )}{content}</main></div></div>;
};

export const StaffShell: React.FC = () => <ToastProvider><ConfirmProvider><StaffShellContent /></ConfirmProvider></ToastProvider>;

export default StaffShell;
