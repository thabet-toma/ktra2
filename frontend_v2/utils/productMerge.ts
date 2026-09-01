/**
 * #24: منطق معاينة/تحديد الضمّ — منطقٌ خالص بلا React كي يُختبَر بـ`node --test`
 * (منطق المكوّن وحده لا يُختبَر هنا). **لا اقتراح آلي هنا إطلاقاً**: المستخدم
 * يحدّد الأعضاء والهدف يدوياً، والدالة تصنّف ما يمكن ضمّه وما يُرفَض فقط —
 * لا تقترح تجميعاً بتشابه الاسم ولا غيره (قرارٌ ملغى من المالك بعد تدقيق
 * أظهر أن أسماء المنتجات لا تتبع نمطاً — #13).
 *
 * دلتا ٢: الاسم يُطبَّع فيصير موحَّداً بين كل الأعضاء — فالبراند وحده يبقى
 * مميِّزاً بينهم في المنتقي («اسم المنتج (البراند)»، `product_display_name`).
 * `findBrandCollisions` تكشف صفوفاً ستنتهي بلا تمييز (براندٌ مكرَّر، أو
 * فراغان معاً) **قبل** أي طلبٍ للخادم — لا تمنع، فالبراند الفارغ مسموحٌ عمداً
 * (يُسمَّى لاحقاً من كرت المنتج)، لكنها تُظهر الأثر صراحةً.
 */

export interface MergeCandidate {
  id: number;
  name: string;
  /** البراند الحالي — يُعبّئ به حقل الإدخال في نافذة الضمّ، فارغٌ إن لم يكن مُسمّى. */
  brand: string;
  uomId: number | null;
  isSerialized: boolean;
}

export interface MergeMovable {
  id: number;
  name: string;
}

export interface MergeBlocked {
  id: number;
  name: string;
  reason: string;
}

export interface MergePreview {
  target: MergeCandidate;
  /** كل عضوٍ منقول سيُعاد تسميته لهذا الاسم — القرار المسجَّل على #24. */
  renamedTo: string;
  movable: MergeMovable[];
  blocked: MergeBlocked[];
}

/**
 * يصنّف المُحدَّدين (عدا الهدف) إلى قابلٍ للضمّ أو مرفوض — **الوحدة والتتبّع
 * التسلسلي فقط** (مرآة `inventory.services.MERGE_GUARD_FIELDS`)، بلا مانعٍ
 * مخترَع. `null` إن كان `targetId` خارج المُحدَّدين (حالةٌ لا يجب أن تصل الواجهة).
 */
export function buildMergePreview(
  selected: readonly MergeCandidate[],
  targetId: number,
): MergePreview | null {
  const target = selected.find((c) => c.id === targetId);
  if (!target) return null;

  const movable: MergeMovable[] = [];
  const blocked: MergeBlocked[] = [];
  for (const candidate of selected) {
    if (candidate.id === target.id) continue;
    if (candidate.uomId !== target.uomId) {
      blocked.push({ id: candidate.id, name: candidate.name, reason: "وحدة القياس تختلف عن الهدف" });
    } else if (candidate.isSerialized !== target.isSerialized) {
      blocked.push({ id: candidate.id, name: candidate.name, reason: "التتبّع التسلسلي يختلف عن الهدف" });
    } else {
      movable.push({ id: candidate.id, name: candidate.name });
    }
  }
  return { target, renamedTo: target.name, movable, blocked };
}

export interface BrandMember {
  id: number;
  /** القيمة النهائية التي سترسل للخادم (مسودّة الإدخال، لا الحالة القديمة). */
  brand: string;
}

export interface BrandCollision {
  /** فارغٌ يعني «بلا براند» — تصادمُ فراغين حالةٌ حقيقية يجب أن تُرى أيضاً. */
  brand: string;
  ids: number[];
}

/**
 * يكشف أعضاءً (الهدف + من سينضمّ فعلياً) سينتهون ببراندٍ واحد لا يميّزهم —
 * الفشل الذي يمنعه هذا الحقل بالضبط: صفوفٌ متطابقة الاسم في المنتقي بعد أن
 * يُطبَّع الاسم على اسم الهدف. **تحذيرٌ لا منع**: البراند الفارغ مسموحٌ عمداً
 * (قرار #24)، فتصادم فراغين لا يُبطل الضمّ — يُعرَض فقط.
 *
 * القصّ (`trim`) يطابق ما يفعله الخادم فعلياً على `brands` (`services.merge_products`)
 * — لا تطبيعٌ إضافي (بلا توحيد أحرف)، فالتصادم هنا هو نفسه ما سيُخزَّن حرفياً.
 */
export function findBrandCollisions(members: readonly BrandMember[]): BrandCollision[] {
  const groups = new Map<string, number[]>();
  for (const member of members) {
    const key = member.brand.trim();
    const ids = groups.get(key);
    if (ids) ids.push(member.id); else groups.set(key, [member.id]);
  }
  const collisions: BrandCollision[] = [];
  for (const [brand, ids] of groups) {
    if (ids.length > 1) collisions.push({ brand, ids });
  }
  return collisions;
}
