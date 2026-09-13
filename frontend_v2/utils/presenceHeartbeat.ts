/**
 * قواعدُ نبضةِ الحضور — خالصةٌ كي يختبرَها `npm test` (‏`node --test` لا يصيّر مكوّناً).
 *
 * النبضةُ نفسُها أثرٌ جانبيٌّ في `hooks/usePlatformPresenceHeartbeat.ts`؛ وما هنا
 * هو **القرار**: هل ينبض هذا اللسانُ الآن، ولمن.
 */

/**
 * هل ينبض هذا المستخدمُ من داخل **نظام الشركة**؟ (212-N1)
 *
 * قبل هذه التذكرة كانت النبضةُ مكتوبةً في `StaffTopBar.tsx` وحدَه، أي داخل قشرة
 * `/staff` وحدَها. وموظّفُ كترا يقضي يومَه في نظام الشركة التي يخدمها — يفتح
 * `/staff` دقيقةً ثمّ يعمل ساعاتٍ في `/employee-ops` — فكان عدّادُ حضوره يقرأ
 * دقيقةً واحدةً، **والحضورُ يدخل في التقييم**. أي أنّ الموظّفَ يُحاسَب على وقتٍ
 * لم يُسجَّل لأنّ الشاشةَ التي تسجّله ليست الشاشةَ التي يعمل فيها.
 *
 * وشرطان لا ثالثَ لهما:
 *
 * * **`isPlatformEmployee` وحدَه** — لا `isPlatformAdmin`. الخادمُ يشتقّ الصفَّ
 *   من `PlatformEmployee` ومن لا صفَّ له يأخذ `recorded: false`؛ فتفعيلُها
 *   للمدير الذي لا ملفَّ موظّفٍ له طلبٌ كلَّ دقيقةٍ إلى الأبد بلا سطرٍ واحدٍ
 *   يُكتَب. (والسوبر أدمن لا يسأل الخادمَ عن قدراته أصلاً، فـ`isPlatformEmployee`
 *   يصله `false` دائماً — وهو الصواب هنا: وقتُه لا يدخل تقييماً.)
 * * **لا نبضةَ قبل الجواب** — `pending` يعني «لم يُحسم بعدُ مَن هذا»، وإطلاقُ
 *   النبضة عندها يجعل كلَّ مستخدمٍ في كلّ شركةٍ ينبض مرّةً على الأقلّ في كلّ
 *   تحميلٍ للصفحة.
 */
export function presenceHeartbeatEnabled(input: {
  pending: boolean;
  isPlatformEmployee: boolean;
}): boolean {
  if (input.pending) return false;
  return input.isPlatformEmployee;
}

/**
 * هل تُرسَل النبضةُ في هذه اللحظة؟
 *
 * لسانٌ مخفيٌّ لا ينبض: «قعد على المنصّة» حضورٌ لا لسانٌ منسيٌّ مفتوحٌ طوالَ
 * الليل. ولسانان ظاهران معاً لا يُضاعفان شيئاً — الخادمُ يجمع **الفجوات** لا
 * النبضات (`record_presence_heartbeat`).
 */
export function shouldSendHeartbeat(input: {
  enabled: boolean;
  documentHidden: boolean;
}): boolean {
  if (!input.enabled) return false;
  return !input.documentHidden;
}
