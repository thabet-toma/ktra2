import React, { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { useAuth } from "../../contexts/AuthContext";
import { usePlatformStaffCapabilitiesState } from "../../hooks/usePlatformStaffCapabilities";
import { getMyPlatformEmployeeProfile, type MyPlatformEmployeeProfile } from "../../services/platformEmployeeSpaceApi";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { PlatformNotificationBell } from "./PlatformNotificationBell";
import { WorkOrdersPanel } from "./WorkOrdersPanel";
import { EmployeeSelfWalletCard } from "./EmployeeSelfWalletCard";
import { EmployeeCompaniesPanel } from "./EmployeeCompaniesPanel";
import { ChampionsPanel } from "./ChampionsPanel";
import { MyMeetingsPanel } from "./MyMeetingsPanel";
import { MyProfileCard } from "./MyProfileCard";
import { CcCard, CcEmpty, CcSkeleton, CcTabs } from "./ui";

type EmployeeTab = "queue" | "companies" | "wallet" | "champions" | "meetings";

const TABS = [
  { key: "queue", label: "طابوري" },
  { key: "companies", label: "شركاتي" },
  { key: "wallet", label: "محفظتي وتقييمي" },
  { key: "champions", label: "Champions" },
  { key: "meetings", label: "اجتماعاتي" },
];

const displayError = (cause: unknown): string =>
  describePlatformOpsError(cause, "هذه المساحة لموظفي عمليات المنصة فقط.", "تعذّر تحميل مساحتك.");

/**
 * مساحةُ موظّف الإدخال — التذكرة 210-E، §١. أكبرُ بابٍ ميّتٍ في المواصفة: طبقةُ
 * الصلاحيّات (`IsPlatformOperationsStaff`، `is_platform_employee`) جاهزةٌ منذ
 * #207 ولا شاشة لها. تُبنى الآن هنا، وتُركَّب في `App.tsx` بالـpatch المرفق في
 * التقرير — التسجيلُ في تلك الملفّة محظورٌ عليّ (مهمّةٌ أخرى تملكها الآن).
 *
 * **حالةُ التحميل منفصلةٌ عن حالة الرفض عمداً**: `usePlatformStaffCapabilitiesState`
 * يبدأ بأعلامٍ كلّها كاذبة قبل أن يحسم الخادمُ الجواب — فوميضُ «هذه المساحة ليست
 * لك» على موظّفٍ حقيقيّ في أوّل رسمٍ عيبٌ يرفضه §١ من التذكرة صراحةً.
 *
 * **ولم يعد هذا بابَ الموظّف** (212-I): البابُ `/staff`، وزرُّ الشريط الجانبيّ
 * ينتقل إليه. ويبقى هذا الملفُّ لأنّ `App.tsx` تستورده وهي محجوزةٌ لمهمّةٍ أخرى،
 * فحذفُه يكسر البناءَ فوراً — سطحُ توافقٍ لا سطحُ استعمال. وحين يُفرَج عن
 * `App.tsx` يُحذف هو ومساره `/platform/employee-space` معاً.
 */
export const PlatformEmployeeWorkspace: React.FC = () => {
  const { currentUser } = useAuth();
  const { capabilities, loading: capabilitiesLoading } = usePlatformStaffCapabilitiesState(
    currentUser?.id ? String(currentUser.id) : undefined,
    !!currentUser?.isSuperAdmin,
  );
  const [profile, setProfile] = useState<MyPlatformEmployeeProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [tab, setTab] = useState<EmployeeTab>("queue");

  const allowed = capabilities.is_platform_employee || capabilities.is_platform_admin;

  /** مُحمِّلٌ واحد: التأثيرُ الأوّل وزرُّ إعادة المحاولة يستدعيانه معاً بدل نسختين تتباعدان. */
  const loadProfile = useCallback(async () => {
    setProfileLoading(true);
    setProfileError(null);
    try {
      setProfile(await getMyPlatformEmployeeProfile(currentUser?.id));
    } catch (cause) {
      setProfileError(displayError(cause));
    } finally {
      setProfileLoading(false);
    }
  }, [currentUser?.id]);

  useEffect(() => {
    if (capabilitiesLoading || !allowed) return;
    void loadProfile();
  }, [capabilitiesLoading, allowed, loadProfile]);

  if (capabilitiesLoading) {
    return (
      <div className="platform-surface ops-shell min-h-screen bg-cc-bg text-cc-text p-4 sm:p-6 lg:p-8 flex items-center justify-center gap-2" dir="rtl">
        <Loader2 className="h-5 w-5 animate-spin text-sky-400" />
        <span className="text-sm text-cc-text-muted">جارٍ التحقّق من صلاحيّاتك...</span>
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="platform-surface ops-shell min-h-screen bg-cc-bg text-cc-text p-4 sm:p-6 lg:p-8 flex items-center justify-center" dir="rtl">
        <CcEmpty
          title="هذه المساحة مخصّصةٌ لموظّفي عمليات المنصة."
          hint="إن كنت تظنّ هذا خطأً فراجع مدير عمليات المنصة."
          className="max-w-md w-full"
        />
      </div>
    );
  }

  return (
    <div className="platform-surface ops-shell min-h-screen bg-cc-bg text-cc-text p-4 sm:p-6 lg:p-8 space-y-6" dir="rtl">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg sm:text-xl font-bold text-cc-text">مساحتي — عمليات المنصة</h1>
          <p className="text-xs text-cc-text-muted mt-0.5">طابورُ أعمالك، وشركاتُ ارتباطاتك بحصصها وبنودِ صحّتها، وتقييمُك ومحفظتُك.</p>
        </div>
        <PlatformNotificationBell />
      </header>

      {profileError && (
        <CcCard tone="danger" className="p-4 flex items-center justify-between gap-4">
          <span className="text-xs text-rose-400 font-medium">{profileError}</span>
          <button
            type="button"
            onClick={() => void loadProfile()}
            className="px-3 py-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 rounded-lg font-bold text-[11px] transition-colors shrink-0"
          >
            إعادة المحاولة
          </button>
        </CcCard>
      )}

      {profile && <MyProfileCard profile={profile} onSaved={() => void loadProfile()} />}

      <CcTabs
        tabs={TABS}
        active={tab}
        onChange={(k) => setTab(k as EmployeeTab)}
        className="mb-6"
      />

      {tab === "queue" && <WorkOrdersPanel />}
      {tab === "companies" && <EmployeeCompaniesPanel />}
      {tab === "champions" && <ChampionsPanel />}
      {tab === "meetings" && <MyMeetingsPanel />}
      {tab === "wallet" && (
        profileLoading ? (
          <CcSkeleton variant="card" count={2} className="mt-4" />
        ) : !profile ? (
          <CcEmpty
            title="لا يوجد ملفُّ موظّف منصّةٍ مرتبطٌ بحسابك بعد."
            className="mt-4"
          />
        ) : (
          <EmployeeSelfWalletCard employeeId={profile.id} />
        )
      )}
    </div>
  );
};

export default PlatformEmployeeWorkspace;
