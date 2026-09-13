/**
 * بوّابةُ `/staff` — قرارُها دالّتان خالصتان لا شرطٌ داخل مكوّن.
 *
 * **سببُ الاستخراج عطبٌ حقيقيٌّ لا ترتيب.** كان `StaffShell` يسأل «هل هو
 * مسموح؟» ويقرأ جوابَ `NONE` الابتدائيَّ على أنّه «لا»، فيطرد الموظّفَ **قبل أن
 * يُطرَح السؤالُ أصلاً**: حلقةُ الصلاحيّات تضبط `loading = false` حين لا مستخدمَ
 * بعد، فحين تنتهي المصادقةُ يقع رسمٌ واحدٌ فيه `authLoading` و`fetching` كلاهما
 * `false` والجوابُ ما زال `NONE` — فيُطلَق `<Navigate to="/" />` قبل انطلاق
 * النداء. والموظّفُ يرى `/staff/home` ثانيةً ثمّ يُقذَف إلى شاشةِ دوره.
 *
 * ولا يمسك العطبَ اختبارٌ يصيّر المكوّن: `npm test` هنا `node --test` على
 * `utils/*.test.ts` — دوالَّ خالصةً لا JSX. فالقرارُ نفسُه هو ما يجب أن يكون
 * قابلاً للاختبار، لا الشاشةُ التي تعرضه.
 */

export interface StaffCapabilitiesAnswer {
  is_platform_employee: boolean;
  is_platform_admin: boolean;
}

export type StaffGate = 'loading' | 'login' | 'leave' | 'render';

/**
 * هل ما زلنا ننتظر جوابَ الصلاحيّات عن **هذا المستخدم بعينه**؟
 *
 * `answeredFor` هو معرّفُ المستخدم الذي يخصّه الجوابُ المحفوظ — لا مجرّد «هل
 * انتهى نداءٌ ما». وبدونه لا يفرّق الشرطُ بين «لم أسأل بعد» و«سألتُ فقيل لا»،
 * وهما في هذه البوّابة نقيضان: الأوّلُ انتظارٌ والثاني طرد.
 */
export function capabilitiesPending(input: {
  isSuperAdmin: boolean;
  fetching: boolean;
  answeredFor: string | null;
  userId: string | null;
}): boolean {
  // السوبر أدمن لا يسأل أصلاً: عَلَمُه في حمولة المصادقة.
  if (input.isSuperAdmin) return false;
  // لا مستخدمَ ⇒ لا سؤالَ معلّقاً؛ وإلّا علّقت البوّابةُ زائراً غيرَ مسجَّل أبداً.
  if (input.userId === null) return false;
  return input.fetching || input.answeredFor !== input.userId;
}

/** قرارُ الرسم: انتظارٌ · صفحةُ دخول · مغادرةٌ إلى نظام الشركة · عرضُ القشرة. */
export function staffGate(input: {
  authLoading: boolean;
  hasUser: boolean;
  pending: boolean;
  capabilities: StaffCapabilitiesAnswer;
}): StaffGate {
  if (input.authLoading || input.pending) return 'loading';
  if (!input.hasUser) return 'login';
  const allowed = input.capabilities.is_platform_employee || input.capabilities.is_platform_admin;
  return allowed ? 'render' : 'leave';
}
