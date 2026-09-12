import React, { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { useAuth } from "../../contexts/AuthContext";
import { usePlatformStaffCapabilitiesState } from "../../hooks/usePlatformStaffCapabilities";
import { getMyPlatformEmployeeProfile, type MyPlatformEmployeeProfile } from "../../services/platformEmployeeSpaceApi";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { PlatformNotificationBell } from "./PlatformNotificationBell";
import { WorkOrdersPanel } from "./WorkOrdersPanel";
import { EmployeeSelfWalletCard } from "./EmployeeSelfWalletCard";

type EmployeeTab = "queue" | "wallet";

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
      <div className="py-20 flex items-center justify-center gap-2 text-slate-500" dir="rtl">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">جارٍ التحقّق من صلاحيّاتك...</span>
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="py-20 text-center bg-white rounded-xl border border-slate-200" dir="rtl">
        <p className="text-sm font-bold text-slate-700">هذه المساحة مخصّصةٌ لموظّفي عمليات المنصة.</p>
        <p className="text-xs text-slate-500 mt-1">إن كنت تظنّ هذا خطأً فراجع مدير عمليات المنصة.</p>
      </div>
    );
  }

  return (
    <div className="p-6" dir="rtl">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-bold text-slate-900">مساحتي — عمليات المنصة</h1>
          <p className="text-xs text-slate-500">طابورُ أعمالك عبر شركات ارتباطاتك، وتقييمُك ومحفظتُك.</p>
        </div>
        <PlatformNotificationBell />
      </header>

      {profileError && (
        <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800 flex items-center justify-between">
          <span>{profileError}</span>
          <button
            type="button"
            onClick={() => void loadProfile()}
            className="px-3 py-1 bg-rose-100 hover:bg-rose-200 rounded-lg font-bold text-[11px]"
          >
            إعادة المحاولة
          </button>
        </div>
      )}

      <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1 mb-6">
        <button
          type="button"
          onClick={() => setTab("queue")}
          className={`px-3.5 py-1.5 text-xs font-bold rounded-md transition ${
            tab === "queue" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          طابوري
        </button>
        <button
          type="button"
          onClick={() => setTab("wallet")}
          className={`px-3.5 py-1.5 text-xs font-bold rounded-md transition ${
            tab === "wallet" ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          محفظتي وتقييمي
        </button>
      </div>

      {tab === "queue" && <WorkOrdersPanel />}
      {tab === "wallet" && (
        profileLoading ? (
          <div className="py-10 text-center text-xs text-slate-400">جاري التحميل...</div>
        ) : !profile ? (
          <div className="py-10 text-center text-xs text-slate-400 bg-white rounded-xl border border-slate-200">
            لا يوجد ملفُّ موظّف منصّةٍ مرتبطٌ بحسابك بعد.
          </div>
        ) : (
          <EmployeeSelfWalletCard employeeId={profile.id} />
        )
      )}
    </div>
  );
};

export default PlatformEmployeeWorkspace;
