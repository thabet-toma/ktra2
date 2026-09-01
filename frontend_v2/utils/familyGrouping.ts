/**
 * #23: شاشة الأصناف — الشجرة تنتهي عند المنتج. صفوف البراندات (`SqlProduct`)
 * بنفس `family_id` تتجمّع في صفٍّ واحد يعرض مجموع أرصدتها؛ منتجٌ بلا أبٍ
 * (بياناتٌ قديمة) يبقى فرداً كما اليوم. كل مجموعٍ هنا **مشتقٌّ عند القراءة**
 * — لا شيء يُخزَّن (`ProductFamily` ممنوعةٌ من حمل أي رقم، #17).
 */
import type { SqlProduct } from "../types/inventory";

export interface ProductGroup {
  key: string;
  familyId: number | null;
  members: SqlProduct[];
}

const SUM_FIELDS = [
  "quantity_on_hand", "reserved_quantity", "available_quantity",
  "purchased_qty", "avg_monthly_sales",
] as const;
type SumField = typeof SUM_FIELDS[number];

/**
 * يُجمّع صفوف المنتجات حسب `family_id` — ترتيب الظهور محفوظ (أوّل ظهورٍ
 * لعائلةٍ يحجز مكانها)، وأعضاء كل عائلة مرتَّبون بمعرّفهم (الأقدم أوّلاً، وهو
 * غالباً البراند الضمنيّ الذي سُمّي أوّلاً — #21).
 */
export function groupProductsByFamily(products: SqlProduct[]): ProductGroup[] {
  const order: ProductGroup[] = [];
  const byFamily = new Map<number, ProductGroup>();
  for (const p of products) {
    const fid = p.family_id ?? null;
    if (fid == null) {
      order.push({ key: `p-${p.id}`, familyId: null, members: [p] });
      continue;
    }
    let g = byFamily.get(fid);
    if (!g) {
      g = { key: `f-${fid}`, familyId: fid, members: [] };
      byFamily.set(fid, g);
      order.push(g);
    }
    g.members.push(p);
  }
  for (const g of order) g.members.sort((a, b) => a.id - b.id);
  return order;
}

const sumNumeric = (members: SqlProduct[], field: SumField): number | null => {
  let sum = 0;
  let any = false;
  for (const m of members) {
    const raw = m[field];
    if (raw == null || raw === "") continue;
    const n = Number(raw);
    if (!Number.isFinite(n)) continue;
    sum += n;
    any = true;
  }
  return any ? sum : null;
};

/** متوسط تكلفةٍ مرجَّحٌ بالكمية — لا متوسطٌ بسيط، وإلا شوّهه براندٌ بقطعتين
 *  وسعرٍ شاذّ (قرار #14 — نفس القاعدة هنا لعرض الصفّ المجمَّع). */
const weightedAvgCost = (members: SqlProduct[]): number => {
  let qtySum = 0;
  let costQtySum = 0;
  for (const m of members) {
    const qty = Number(m.quantity_on_hand) || 0;
    const cost = Number(m.avg_cost) || 0;
    qtySum += qty;
    costQtySum += qty * cost;
  }
  return qtySum > 0 ? costQtySum / qtySum : 0;
};

/**
 * صفٌّ واحدٌ يمثّل المنتج (الأب): مجموع أرصدة برانداته، بلا أي رقمٍ يُخزَّن —
 * يُشتقّ من صفوف الأعضاء في كل رسم. البراند المرجعي (`anchor`، أصغر معرّف)
 * يمثّل الحقول التي لا تُجمَع (السعر، رقم المنتج…) لأنها فيزيائياً على صفّ
 * البراند خلال المرحلة الانتقالية (#20)، ومتطابقةٌ عملياً بين الإخوة عند
 * الإنشاء (`add_brand_to_family` تنسخها من الأب). `stock_status` ليس
 * استثناءً فعلياً: الخادم يحسبها أصلاً على مجموع الإخوة مقابل حدّ الأب (#25)،
 * فهي متطابقةٌ بين كل الإخوة أصلاً — لا حاجة لإعادة اشتقاقها هنا.
 * الحدّان (`min`/`max_stock_level`) ليسا متطابقين بالضرورة بعد ضمٍّ لا يُسوّي
 * إخوته (#24) — فيُفضَّلان من `effective_*` (حدّ الأب الحاكم من الخادم، نفس
 * ما حُوكِمت به `stock_status`) لا من قيمة المرجعي الخام (#35).
 */
export function buildFamilyRow(members: SqlProduct[]): SqlProduct {
  const anchor = members[0];
  const purchased = sumNumeric(members, "purchased_qty");
  const monthly = sumNumeric(members, "avg_monthly_sales");
  const name = anchor.family_name || anchor.name_ar || anchor.name_en || null;
  return {
    ...anchor,
    display_name: name,
    name_ar: name,
    quantity_on_hand: sumNumeric(members, "quantity_on_hand") ?? 0,
    reserved_quantity: sumNumeric(members, "reserved_quantity") ?? 0,
    available_quantity: sumNumeric(members, "available_quantity") ?? 0,
    purchased_qty: purchased != null ? String(purchased) : null,
    avg_monthly_sales: monthly != null ? String(monthly) : null,
    avg_cost: weightedAvgCost(members),
    // #35: الحدّان يُفضّلان قيمة الأب **الحاكمة** (`effective_*`، من الخادم)
    // على حدّ البراند المرجعي الخام — وإلا عرض الصفّ رقماً غير الذي حَكَم على
    // شارته، وهو تحديداً العيب الذي أصلحته هذه التذكرة.
    min_stock_level: anchor.effective_min_stock_level ?? anchor.min_stock_level,
    max_stock_level: anchor.effective_max_stock_level ?? anchor.max_stock_level,
  };
}
