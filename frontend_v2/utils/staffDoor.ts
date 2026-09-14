/**
 * بابُ `/staff` في شريط نظام الشركة — **لمن يُفتَح، وبأيّ اسم** (212-Q3).
 *
 * كان الشرطُ `!isSuperAdmin && is_platform_employee`، فمالكُ النظام لا يرى
 * باباً إلى مساحة موظّفيه إطلاقاً — ولا يستطيع أن يعاين ما يرونه إلّا بكتابة
 * `/staff/home` في شريط العنوان، وهو ما لا يخطر لأحدٍ ولم يخطر له: سأل عنها
 * مراراً وقيل له «موجودة» فلم يجدها.
 *
 * **والقشرةُ تقبله أصلاً**: `staffGate` يمرّر `is_platform_admin`، وحمولةُ
 * المصادقة ترفع هذه الرايةَ للسوبر أدمن. أي أنّ الممنوعَ كان البابَ لا الغرفة
 * — رابطٌ ناقصٌ فوق صلاحيّةٍ قائمة.
 *
 * والاسمُ يفرّق الحالتين لأنّ الشيئين مختلفان: الموظّفُ يذهب إلى **مساحته**،
 * والمالكُ يذهب **معايناً** مساحةَ غيره. ولو حمل البابان اسماً واحداً لقرأ
 * المالكُ لوحاتِه الشخصيّةَ الفارغةَ عطباً في حسابه — وقد فعل مرّةً.
 */

export interface StaffDoor {
  /** اسمُ الباب كما يُقرأ على الشريط. */
  label: string;
  /** معاينةٌ لمساحة غيره لا مساحتُه هو. */
  preview: boolean;
}

export function staffDoorFor(input: {
  isSuperAdmin: boolean;
  isPlatformEmployee: boolean;
}): StaffDoor | null {
  // موظّفُ المنصّة أوّلاً: مساحتُه مساحتُه ولو كان سوبر أدمن أيضاً.
  if (input.isPlatformEmployee) return { label: 'مساحتي — عمليات المنصة', preview: false };
  if (input.isSuperAdmin) return { label: 'معاينة مساحة الموظّف', preview: true };
  return null;
}

/**
 * هل ما يُعرَض الآن **معاينةٌ** لا مساحةُ صاحبها؟
 *
 * الجوابُ يلزمه ملفُّ الموظّف محسوماً: قبل عودة النداء لا يُقال «معاينة» ولا
 * «مساحتك»، وإلّا ومض الشريطُ على المالك وعلى الموظّف كليهما. وسوبر أدمن له
 * صفُّ `PlatformEmployee` حقيقيٌّ ليس معايناً — هي مساحتُه فعلاً.
 */
export function isStaffPreview(input: {
  isSuperAdmin: boolean;
  profileSettled: boolean;
  hasProfile: boolean;
}): boolean {
  if (!input.isSuperAdmin || !input.profileSettled) return false;
  return !input.hasProfile;
}
