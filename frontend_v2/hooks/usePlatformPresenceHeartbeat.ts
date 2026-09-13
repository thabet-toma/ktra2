import { useEffect, useState } from 'react';

import { sendPresenceHeartbeat } from '../services/platformPresenceApi';
import { shouldSendHeartbeat } from '../utils/presenceHeartbeat';

/**
 * نبضةُ حضورِ موظّف المنصّة — **من حيث يعمل فعلاً، لا من قشرة `/staff` وحدَها** (212-N1).
 *
 * كانت هذه الحلقةُ مكتوبةً داخل `StaffTopBar.tsx`، فلم تكن تدقّ إلّا والموظّفُ
 * واقفٌ في قشرة المنصّة. وهو يقضي يومَه في نظام الشركة التي يخدمها، فيقرأ عدّادُ
 * حضوره دقائقَ ويُحاسَب عليها في التقييم. فصارت حلقةً واحدةً يركّبها الجانبان:
 * شريطُ `/staff` (`enabled` دائماً) وقشرةُ الشركة (`enabled` لموظّف المنصّة وحدَه).
 *
 * والتركيبُ مرّتين لا يضاعف شيئاً: الخادمُ يجمع **الفجوات** بين النبضات لا
 * عددَها (`record_presence_heartbeat`)، فلسانان — أو قشرتان — يضيفان فجوةً واحدة.
 *
 * وتُعيد ثوانيَ اليوم **كما قالها الخادم**، و`null` قبل أوّل جوابٍ ناجح: صفرٌ
 * مُلفَّقٌ يقول «لم يحضر» عمّن لم نسأل عنه بعد.
 */
export function usePlatformPresenceHeartbeat(enabled: boolean): number | null {
  const [seconds, setSeconds] = useState<number | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    const beat = async () => {
      if (!shouldSendHeartbeat({ enabled, documentHidden: document.visibilityState === 'hidden' })) return;
      try {
        const result = await sendPresenceHeartbeat();
        if (alive && result.recorded && typeof result.active_seconds === 'number') {
          setSeconds(result.active_seconds);
        }
      } catch {
        /* فشلُ نبضةٍ لا يُفرغ العدّاد: آخرُ قيمةٍ معروفةٍ أصدقُ من صفرٍ مُلفَّق. */
      }
    };
    void beat();
    const interval = window.setInterval(() => void beat(), 60000);
    return () => { alive = false; window.clearInterval(interval); };
  }, [enabled]);

  return seconds;
}
