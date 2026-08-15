/**
 * MyAccountPage — «حسابي»: صفحة المستخدم نفسه، خارج قوائم الشركة.
 *
 * سبب وجودها: دفتر المصاريف الشخصي كان بنداً في الشريط الجانبي بين شاشات
 * الشركة، فبدا كأنه مصروفُ شركةٍ لا مصروفَ صاحبه. الحدّ الذي يفصل المالَ
 * الشخصي عن مال الشركة حدٌّ محاسبيّ قبل أن يكون حدَّ تنقّل — ووضعُه في
 * القائمة نفسها التي فيها «فواتير الشراء» و«صناديق الكاش» يمحوه بصرياً.
 * فصارت لما يخصّ المستخدم صفحةٌ واحدة يدخلها من بطاقة اسمه أسفل القائمة،
 * وهو نفس ما تفعله المنتجات المحترفة: Odoo تضع «My Profile / Preferences»
 * خلف صورة المستخدم أعلى اليمين لا داخل قوائم التطبيقات، وZoho Books تفصل
 * إعدادات المنظّمة عن حساب المستخدم فصلاً كاملاً.
 *
 * ما فيها **يتبع المستخدم لا الشركة النشطة**: بلا `tenant`، بلا قيد محاسبي،
 * ولا يظهر لمدير الشركة (العزل خادميّ في `hr.PersonalExpenseOwnedViewSet`
 * بـ`user=request.user`، ويردّ 404 لغير المالك — لا 403 — فلا يُفشي وجود
 * السجل أصلاً).
 *
 * «الإعدادات» تبقى شاشتها كما هي ولها بندها المعتاد — هنا رابطٌ إليها فقط،
 * لا نسخة ثانية منها.
 */
import React from "react";
import { UserCircle2, Mail, ShieldOff, Settings2 } from "lucide-react";
import { User, AppView } from "../../types";
import PersonalExpensesPage from "./PersonalExpensesPage";

interface MyAccountPageProps {
  user: User;
  onNavigate: (view: AppView) => void;
}

const roleLabel = (user: User): string => {
  if (user.isSuperAdmin) return "سوبر أدمن المنصة";
  if (user.role === "manager") return "مدير";
  if (user.role === "procurement") return "مشتريات";
  return "موظف";
};

export const MyAccountPage: React.FC<MyAccountPageProps> = ({ user, onNavigate }) => (
  <div dir="rtl" className="space-y-4 p-3 md:p-4">
    {/* بطاقة الهوية — من أنت، لا في أي شركة أنت */}
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-12 h-12 rounded-full bg-[var(--color-primary)] flex items-center justify-center text-xl font-bold text-[var(--color-primary-foreground)] flex-shrink-0">
          {user.name?.charAt(0)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-lg font-bold text-[var(--color-text)]">
            <UserCircle2 className="w-5 h-5 text-[var(--color-primary)]" />
            <span className="truncate">{user.name}</span>
            <span className="rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-0.5 text-[11px] font-normal text-[var(--color-text-muted)]">
              {roleLabel(user)}
            </span>
          </div>
          {user.email && (
            <div className="mt-1 flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
              <Mail className="w-3.5 h-3.5" />
              <span className="truncate">{user.email}</span>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => onNavigate("settings")}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
          title="ملفي الشخصي، كلمة المرور، والتفضيلات"
        >
          <Settings2 className="w-4 h-4" />
          إعداداتي وتفضيلاتي
        </button>
      </div>

      {/* التنبيه الذي طلبه المالك — الحدّ مكتوبٌ لا مفهومٌ ضمناً */}
      <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        <ShieldOff className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <span>
          هذه صفحتك أنت: ما فيها يتبع حسابك لا الشركة، ولا يراه مدير الشركة، ولا
          يدخل حسابات أي شركة ولا قيودها ولا تقاريرها. تبديل الشركة لا يغيّر ما هنا.
        </span>
      </div>
    </div>

    {/* دفتر الجيب — الشاشة نفسها بلا تغيير، في موضعها الصحيح */}
    <PersonalExpensesPage />
  </div>
);

export default MyAccountPage;
