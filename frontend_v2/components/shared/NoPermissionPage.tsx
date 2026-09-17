/**
 * C2-5 — «لا تملك صلاحية عرض هذه الشاشة» بدل السقوط الصامت إلى لوحة التحكم.
 *
 * كان حارسُ الشاشة في `App.tsx` (`canView`/`canPerm`) يُصيِّر `Dashboard` حين
 * تنقص الصلاحية: الرابطُ يبقى في شريط العنوان ولا رسالة — فيبدو الرابطُ معطوباً
 * لا ممنوعاً. هذه الصفحةُ تقول السببَ واسمَ الشاشة وتعيد إلى الرئيسية.
 *
 * **لا ٤٠٣ أثناء التحميل**: `can()` تعيد `true` قبل وصول الصلاحيات، فالحارسُ لا
 * يبلغ هذا الفرعَ إلا بصلاحياتٍ محمَّلة؛ لكنّ إعادةَ التحميل (`reload()`) تُبقي
 * الصلاحياتِ القديمة ريثما تصل الجديدة — فالمؤشّرُ هنا لا الرفض. لا تغيير في
 * دلالة `can()` نفسها.
 */
import React from "react";
import { ShieldAlert } from "lucide-react";
import { LoadingSpinner } from "../LoadingSpinner";
import { VIEW_LABELS } from "../layout/Breadcrumb";
import { usePermissions } from "../../contexts/PermissionsContext";
import type { AppView } from "../../types";

export interface NoPermissionPageProps {
  /** الشاشة الممنوعة — يُقرأ اسمها من `VIEW_LABELS` (مصدر مسار التنقّل). */
  view: AppView;
  /** العودة إلى الرئيسية — `setViewAndSyncPath("dashboard")` كي يتبع الرابطُ الشاشة. */
  onBackToDashboard: () => void;
}

export const NoPermissionPage: React.FC<NoPermissionPageProps> = ({ view, onBackToDashboard }) => {
  const { loading } = usePermissions();
  if (loading) return <div className="flex justify-center py-16"><LoadingSpinner /></div>;
  const screenName = VIEW_LABELS[view];
  return (
    <div
      role="alert"
      data-testid="no-permission-page"
      className="mx-auto mt-8 flex max-w-xl flex-col items-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center text-red-800"
    >
      <ShieldAlert className="h-10 w-10" aria-hidden="true" />
      <h2 className="text-lg font-bold">لا تملك صلاحية عرض هذه الشاشة</h2>
      {screenName && <p className="text-sm font-medium">{screenName}</p>}
      <p className="text-sm">اطلب الصلاحية من مدير الشركة إن كنت تحتاجها في عملك.</p>
      <button
        type="button"
        onClick={onBackToDashboard}
        className="mt-2 rounded-xl bg-blue-600 px-5 py-2 text-sm font-bold text-white transition hover:bg-blue-700"
      >
        العودة إلى الرئيسية
      </button>
    </div>
  );
};

export default NoPermissionPage;
