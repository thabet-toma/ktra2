/**
 * اشتقاقُ حالةِ حضورِ الموظّف في غرفة مساحة العمل (#211 م٣).
 *
 * ثلاثةُ أضواءٍ في نموذج المالك البصريّ: أخضرُ متّصل · أصفرُ في اجتماع ·
 * أحمرُ غير متّصل. والمصدران مختلفان تماماً:
 *
 * - **الاتّصالُ** من `is_recently_active` الذي يحسبه الخادمُ بعتبة ١٥ دقيقة من
 *   `UserDevice.last_active_at` (لا نبضةَ جديدة: الطابعُ يُكتب على كلّ طلبٍ
 *   مصادق). ولا يُعاد حسابُه هنا بساعة المتصفّح — ساعةُ الجهاز قد تكون مغلوطةً
 *   بساعاتٍ فيُعرَض نصفُ الفريق «غير متّصل» بلا سبب.
 * - **الاجتماعُ** من دفتر حضور الاجتماعات، ولا علاقةَ له بالنشاط.
 *
 * **والاجتماعُ يغلب الاتّصال** حين يجتمعان: موظّفٌ داخلَ اجتماعٍ وهو نشطٌ على
 * المنصّة حالتُه «في اجتماع» — وإلاّ اختفى الضوءُ الأصفرُ كلَّما كان صاحبُه
 * يعمل، أي في الحالة التي وُجد لها.
 */

export type RoomPresence = 'online' | 'meeting' | 'offline';

export interface PresenceSource {
  /** محسوبٌ في الخادم بعتبة ١٥ دقيقة — لا يُعاد اشتقاقُه من ساعة المتصفّح. */
  is_recently_active?: boolean;
  last_active_at?: string | null;
}

export function derivePresence(
  employee: PresenceSource,
  employeeIdsInMeeting: ReadonlySet<number> | null | undefined,
  employeeId: number
): RoomPresence {
  if (employeeIdsInMeeting && employeeIdsInMeeting.has(employeeId)) {
    return 'meeting';
  }
  return employee.is_recently_active ? 'online' : 'offline';
}

/**
 * ترتيبُ الجلوس: الحاضرُ أوّلاً ثمّ المجتمعُ ثمّ الغائب، والاسمُ فاصلاً عند
 * التساوي — كي يبقى الترتيبُ ثابتاً بين تحديثَين فلا «تقفز» الوجوهُ حول
 * الطاولة عند كلّ استقصاء، وهي قفزةٌ تُفقِد الغرفةَ قيمتَها كلوحةِ مراقبة.
 */
const PRESENCE_RANK: Record<RoomPresence, number> = {
  online: 0,
  meeting: 1,
  offline: 2,
};

export function sortByPresence<T extends { presence: RoomPresence; name: string }>(
  occupants: readonly T[]
): T[] {
  return [...occupants].sort((a, b) => {
    const rank = PRESENCE_RANK[a.presence] - PRESENCE_RANK[b.presence];
    if (rank !== 0) return rank;
    return a.name.localeCompare(b.name, 'ar');
  });
}

/** عدُّ «المتّصلون الآن ١٨/٢٥»: المجتمعُ متّصلٌ أيضاً — هو في العمل لا خارجه. */
export function countPresent(occupants: readonly { presence: RoomPresence }[]): number {
  return occupants.filter((o) => o.presence !== 'offline').length;
}
