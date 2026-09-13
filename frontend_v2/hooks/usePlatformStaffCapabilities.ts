import { useCallback, useEffect, useState } from "react";

import {
  getPlatformStaffCapabilities,
  type PlatformStaffCapabilities,
} from "../services/platformHiringApi";
import { capabilitiesPending } from "../utils/staffAccess";

/**
 * قدراتُ المستخدم الحاليّ على المنصّة — **نداءٌ واحدٌ لكلّ مستخدمٍ في الجلسة** (#207 م٨-ب).
 *
 * السوبر أدمن لا يسأل: عَلَمُه في حمولة المصادقة وأبوابُ المنصّة كلُّها مفتوحةٌ له.
 * وغيرُه يسأل مرّةً، لأنّ دورَ التوظيف لا يصل مع تلك الحمولة — تسكن `hr` التي يمنعها
 * حارسُ العزل من استيراد `platform_ops`. والوعدُ مخبَّأٌ على مستوى الوحدة كي لا يعيد
 * كلُّ رسمٍ للشريط الجانبيّ النداءَ، ويُنسى عند الفشل كي لا تحبس انقطاعةُ شبكةٍ عابرةٌ
 * مسؤولَ التوظيف خارج شاشته حتى تحديث الصفحة.
 */
const NONE: PlatformStaffCapabilities = {
  is_platform_admin: false,
  is_platform_recruiter: false,
  is_platform_employee: false,
};

let pending: { userId: string; promise: Promise<{ value: PlatformStaffCapabilities; ok: boolean }> } | null = null;

/**
 * النسخةُ الكاملة: تُميّز `loading` (لم يُحسم الجوابُ بعد) عن نتيجةٍ حاسمةٍ بالرفض.
 *
 * السوبر أدمن لا ينتظر (`loading` يبدأ `false` له فوراً). وغيرُه `loading: true`
 * حتى يعود النداء — فشاشةٌ كاملةٌ تعتمد `is_platform_employee` تعرض حالة تحميلٍ لا
 * «ممنوع» في أوّل رسمٍ لموظّفٍ حقيقيّ، بخلاف زرٍّ في الشريط الجانبيّ يتحمّل الوميض.
 */
export function usePlatformStaffCapabilitiesState(
  userId: string | undefined,
  isSuperAdmin: boolean,
): { capabilities: PlatformStaffCapabilities; loading: boolean; failed: boolean; reload: () => void } {
  const [capabilities, setCapabilities] = useState<PlatformStaffCapabilities>(NONE);
  const [fetching, setFetching] = useState<boolean>(!isSuperAdmin);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  /**
   * معرّفُ المستخدم الذي **يخصّه** الجوابُ المحفوظ — لا مجرّد «انتهى نداءٌ ما».
   *
   * بدونه لا يفرّق المستدعي بين «لم أسأل بعد» و«سألتُ فقيل لا»، وهما في بوّابة
   * `/staff` نقيضان: الأوّلُ انتظارٌ والثاني طرد. ولحظةَ انتهاءِ المصادقةِ يقع
   * رسمٌ فيه `fetching` كاذبٌ (ضبطَه فرعُ «لا مستخدمَ بعد») والجوابُ ما زال
   * `NONE` ولم يُسأل عن أحدٍ قطّ — فكان الموظّفُ يُطرَد قبل انطلاق النداء.
   */
  const [answeredFor, setAnsweredFor] = useState<string | null>(null);

  const reload = useCallback(() => {
    pending = null;
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!userId || isSuperAdmin) {
      setCapabilities(isSuperAdmin ? { ...NONE, is_platform_admin: true } : NONE);
      setFetching(false);
      setFailed(false);
      setAnsweredFor(userId ?? null);
      return;
    }
    let alive = true;
    setFetching(true);
    setFailed(false);
    if (!pending || pending.userId !== userId) {
      // **الفشلُ يُعلَن ولا يُترجَم إلى «لا»**: إعادةُ `NONE` وحدَها تجعل انقطاعةَ
      // شبكةٍ عابرةً تُخفي أزرارَ المدير بلا رسالةٍ ولا إعادةِ محاولة — وهو عينُ
      // ما يمنعه §٢ («فشلُ عنصرٍ واحدٍ لا يسقط اللوحة؛ يظهر retry»).
      const promise = getPlatformStaffCapabilities()
        .then((value) => ({ value, ok: true }))
        .catch(() => {
          pending = null;
          return { value: NONE, ok: false };
        });
      pending = { userId, promise };
    }
    void pending.promise.then((outcome) => {
      if (alive) {
        setCapabilities(outcome.value);
        setFailed(!outcome.ok);
        setAnsweredFor(userId);
        setFetching(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [userId, isSuperAdmin, attempt]);

  return {
    capabilities,
    // «معلَّقٌ» لا «جارٍ»: القاعدةُ خالصةٌ في `utils/staffAccess.ts` كي يختبرَها
    // `npm test` — فهو `node --test` على دوالَّ خالصةٍ ولا يصيّر مكوّناً.
    loading: capabilitiesPending({ isSuperAdmin, fetching, answeredFor, userId: userId ?? null }),
    failed,
    reload,
  };
}

export function usePlatformStaffCapabilities(
  userId: string | undefined,
  isSuperAdmin: boolean,
): PlatformStaffCapabilities {
  return usePlatformStaffCapabilitiesState(userId, isSuperAdmin).capabilities;
}
