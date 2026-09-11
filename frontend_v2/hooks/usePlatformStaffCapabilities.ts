import { useEffect, useState } from "react";

import {
  getPlatformStaffCapabilities,
  type PlatformStaffCapabilities,
} from "../services/platformHiringApi";

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

let pending: { userId: string; promise: Promise<PlatformStaffCapabilities> } | null = null;

export function usePlatformStaffCapabilities(
  userId: string | undefined,
  isSuperAdmin: boolean,
): PlatformStaffCapabilities {
  const [capabilities, setCapabilities] = useState<PlatformStaffCapabilities>(NONE);

  useEffect(() => {
    if (!userId || isSuperAdmin) {
      setCapabilities(isSuperAdmin ? { ...NONE, is_platform_admin: true } : NONE);
      return;
    }
    let alive = true;
    if (!pending || pending.userId !== userId) {
      const promise = getPlatformStaffCapabilities().catch(() => {
        pending = null;
        return NONE;
      });
      pending = { userId, promise };
    }
    void pending.promise.then((value) => {
      if (alive) setCapabilities(value);
    });
    return () => {
      alive = false;
    };
  }, [userId, isSuperAdmin]);

  return capabilities;
}
