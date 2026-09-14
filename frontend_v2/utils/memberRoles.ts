/**
 * أدوارُ أعضاء الشركة — مصدرٌ واحدٌ للتسمية والتصنيف والتحويل.
 *
 * شاشةُ «إدارة المستخدمين» تقرأ أعضاءَ الشركة النشطة من
 * `tenants/companies/{id}/members/` للجميع بمن فيهم السوبر أدمن؛ مرآةُ
 * `users` في bridge عالميةٌ عمداً (كلُّ حسابات المنصة بلا شركة) فعرضُها
 * «قائمةَ مستخدمي الشركة» كذبٌ على المستخدم — والرؤيةُ العابرةُ للشركات
 * مكانُها لوحةُ المنصة (`superadmin/PlatformCompanyPanel`).
 *
 * ومفرداتُ الأدوار هنا مفرداتُ الخادم نفسِها (`tenants.models`
 * `UserCompanyMembership.ROLE_CHOICES`) لا مفرداتُ التطبيق القديم: لا وجود
 * لدور `employee` في العضوية، فسحقُ كلِّ غير المدير إليه كان يُخفي
 * `procurement` و`accountant` و`sales` عن الفلاتر والشاشات.
 *
 * دوالُّ خالصةٌ بلا متصفّح كي تُختبر بـ`node --test` (انظر `memberRoles.test.ts`).
 */
import { userRoleLabel } from "./userRoleLabel.ts";

/** صفٌّ من `tenants.services.member_payload` كما يصل الواجهة. */
export interface CompanyMemberRow {
  membership_id?: number;
  user_id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  is_default?: boolean;
  can_access_import?: boolean;
  /** `auth_user.is_active` — مصدرُ «الحساب مفعَّل» الوحيد (لا قيمةَ مخترعة). */
  is_active?: boolean;
  created_at?: string;
}

/** المستخدَمُ كما تعرضه الشاشات القديمة — الحقولُ التي للعضوية مصدرٌ لها فقط. */
export interface CompanyMemberUser {
  id: string;
  name: string;
  email: string;
  role: string;
  isApproved: boolean;
}

/**
 * كلُّ دورٍ قد يعيده الخادم في صفِّ عضويّة — **قائمةُ مفاتيحَ لا خريطةُ تسميات**.
 *
 * التسميةُ مصدرُها `utils/userRoleLabel.ts` وحدَه (212-P1)، ويحرسه
 * `core/tests/test_header_role_label.py`. وخريطةٌ ثانيةٌ هنا كانت تفترق عنه
 * صامتةً — وقد افترقت في أوّلِ سطرٍ كُتِب: `viewer` «مستعرض» هناك
 * و«مستعرض (قراءة فقط)» هنا، والحارسُ لا يرى نسخةً لا يعرف مكانَها.
 */
export const MEMBER_ROLES = [
  "manager", "accountant", "legal_accountant",
  // T-PERM: دورا الموظف المتخصّص — صلاحياتهما تُضبط من شاشة «الصلاحيات والأدوار».
  "sales", "procurement", "staff", "ess", "field_staff", "viewer",
] as const;

/** الدورُ ⇐ اسمُه العربيّ — مشتقّاً من مصدر التسمية الواحد لا منسوخاً عنه. */
export const MEMBER_ROLE_LABELS: Record<string, string> = Object.fromEntries(
  MEMBER_ROLES.map((role) => [role, userRoleLabel(role)]),
);

/**
 * ما يجوز لمديرِ شركةٍ إسنادُه من قوائم «إضافة عضو» و«تغيير الدور».
 *
 * `legal_accountant` خارجها عمداً — الخادم يرفض إسنادَه من هنا
 * (`tenants/views.py`: «يُنشأ دور المحاسب القانوني من دورة الارتباط
 * المحمية فقط»)، و`ess`/`field_staff` يُمنحان من وحدتيهما لا من هنا.
 * فالعرضُ أوسعُ من الإسناد قصداً: تُقرأ أدوارٌ لا تُكتَب من هذه الشاشة.
 */
export const ASSIGNABLE_MEMBER_ROLES = [
  "manager", "accountant", "sales", "procurement", "staff", "viewer",
] as const;

/**
 * تسميةُ الدور — المصدرُ نفسُه الذي تقرؤه الترويسةُ وبطاقةُ الحساب.
 *
 * والمجهولُ يُعرَض «مستخدم» لا رمزَه الإنجليزيَّ: القاعدةُ الأولى في 212-P1
 * أنّ مفتاحاً إنجليزيّاً لا يصل الشاشةَ أبداً — قرأه المالكُ مرّةً فاستنتج
 * عطباً لا وجودَ له. ودورٌ جديدٌ لا يختفي بصمتٍ رغم ذلك: `ROLE_CHOICES`
 * يقرؤه الحارسُ فيسقط على أوّلِ دورٍ بلا اسمٍ عربيّ.
 */
export const memberRoleLabel = userRoleLabel;

/**
 * «موظف» بالمعنى الذي تقصده شاشاتُ التقارير والملاحظات والنقاط والحضور:
 * كلُّ عضوٍ ليس مديرَ الشركة.
 *
 * وهو **نفسُ سلوكِ اليوم** حرفياً: السحقُ القديم كان يجعل كلَّ غير المدير
 * `employee`، فكان `role === 'employee'` يساوي «ليس مديراً». تمريرُ الدور
 * الحقيقيّ بلا هذه الدالّة كان سيُفرغ تلك الشاشاتِ الأربع، إذ لا عضوَ
 * دورُه `employee` أصلاً.
 */
export const isEmployeeMember = (role: string | undefined | null): boolean =>
  role !== "manager";

/**
 * صفُّ عضويةٍ ⇐ مستخدَمُ الواجهة. ما لا تحمله العضويةُ لا يُختلق:
 * لا `employmentStatus` (لا وجودَ له في الخادم أصلاً) ولا `isEmailVerified`
 * ولا `notes` — والشاشةُ لا تعرض عموداً بلا بيانات بدل تعبئته بقيمةٍ كاذبة.
 */
export const mapMemberToUser = (row: CompanyMemberRow): CompanyMemberUser => ({
  id: String(row.user_id),
  name: row.full_name || row.username,
  email: row.email || "",
  role: row.role,
  isApproved: Boolean(row.is_active),
});
