/**
 * T-ITEMS M2 — شجرة التصنيفات: مصدرٌ واحد للترتيب والعمق والأحفاد والمسار.
 *
 * كانت الخوارزمية نفسها مكتوبةً أربع مرّات — في منتقي التصنيف، وشجرة الفاتورة،
 * وجدول إدارة التصنيفات، وجدول الأصناف المجمّع — بأربعة أسماء وأربعة سلوكيات
 * عند الحالات الحدّية: واحدة تعامل التصنيف اليتيم (أبوه خارج القائمة) جذراً
 * وأخرى تُسقطه من الشجرة فلا يعود قابلاً للاختيار أبداً.
 *
 * القاعدة هنا مرّةً واحدة على نسق `utils/accountTree.ts`.
 *
 * **المصطلح**: «تصنيف» = فئةٌ في الشجرة، و«صنف» = منتج. شجرة الفاتورة كانت
 * تعكسهما فتقول «إضافة صنف فرعي» وهي تعني تصنيفاً.
 */

/**
 * المعرّف رقمٌ أو نصّ: شاشاتُ المستودع تحمل أرقاماً وشجرةُ الفاتورة تحمل نصوصاً
 * (ومعرّفُ الأب فيها رقمٌ بينما معرّف العقدة نصّ). المفاتيح تُطبَّع داخلياً إلى
 * نصّ فيتساوى العُرفان، وتعود العُقد كما جاءت.
 */
export type CategoryId = number | string;

/** الحدّ الأدنى الذي تحتاجه الشجرة — الحقول مرنة لأن كل شاشة تعرّف نوعها. */
export interface CategoryNodeLike {
  id: CategoryId;
  name?: string | null;
  parent?: CategoryId | null;
}

/** مفتاح الفهرسة — نصٌّ دائماً، فلا يفترق `3` عن `"3"`. */
const keyOf = (id: CategoryId): string => String(id);

export interface CategoryIndex<T extends CategoryNodeLike> {
  /** مفاتيحها نصّية — استعمل `String(id)` عند الاستعلام. */
  byId: Map<string, T>;
  /** أبناء كل تصنيف مرتّبين بالاسم؛ مفتاح `null` = الجذور. */
  childrenOf: Map<string | null, T[]>;
}

export interface CategoryRow<T extends CategoryNodeLike> {
  category: T;
  depth: number;
  hasChildren: boolean;
}

const nameOf = (c: CategoryNodeLike): string => String(c.name ?? '');

/**
 * جذرٌ هو من لا أب له — أو من غاب أبوه عن القائمة.
 *
 * `parent = 0` يعني جذراً أيضاً: بياناتٌ قديمة تحمل صفراً حيث يجب أن يكون
 * `null`، والخادم نفسه يعاملها كذلك في `root_only`.
 */
const parentKeyOf = <T extends CategoryNodeLike>(
  node: T, byId: Map<string, T>,
): string | null => {
  const parent = node.parent;
  if (parent == null || parent === 0 || parent === '0') return null;
  const key = keyOf(parent);
  return byId.has(key) ? key : null;
};

export const buildCategoryIndex = <T extends CategoryNodeLike>(
  categories: T[],
): CategoryIndex<T> => {
  const byId = new Map<string, T>();
  for (const c of categories) byId.set(keyOf(c.id), c);

  const childrenOf = new Map<string | null, T[]>();
  for (const c of categories) {
    const key = parentKeyOf(c, byId);
    const list = childrenOf.get(key);
    if (list) list.push(c);
    else childrenOf.set(key, [c]);
  }
  for (const list of childrenOf.values()) {
    list.sort((x, y) => nameOf(x).localeCompare(nameOf(y), 'ar'));
  }
  return { byId, childrenOf };
};

/**
 * صفوف الشجرة بترتيب العرض (عمق أوّلاً) مع عمق كل صفّ.
 *
 * محروسٌ من الحلقات: بياناتٌ سبقت حارسَ الخادم قد تحمل تصنيفاً أباً لأصله،
 * والمشي الساذج عليها لا ينتهي — الشاشة تتجمّد ولا رسالة.
 */
export const sortCategoryRows = <T extends CategoryNodeLike>(
  categories: T[],
): CategoryRow<T>[] => {
  const { childrenOf } = buildCategoryIndex(categories);
  const rows: CategoryRow<T>[] = [];
  const seen = new Set<string>();

  const walk = (parent: string | null, depth: number) => {
    for (const category of childrenOf.get(parent) ?? []) {
      const key = keyOf(category.id);
      if (seen.has(key)) continue;
      seen.add(key);
      const children = childrenOf.get(key) ?? [];
      rows.push({ category, depth, hasChildren: children.length > 0 });
      walk(key, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
};

/** عمق تصنيفٍ بعينه (الجذر = 0). */
export const categoryDepth = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId,
): number => {
  const { byId } = buildCategoryIndex(categories);
  let depth = 0;
  const seen = new Set<string>();
  let node = byId.get(keyOf(categoryId));
  while (node && !seen.has(keyOf(node.id))) {
    seen.add(keyOf(node.id));
    const parent = parentKeyOf(node, byId);
    if (parent == null) break;
    depth += 1;
    node = byId.get(parent);
  }
  return depth;
};

/**
 * التصنيف **وكل أحفاده** (يشمل نفسه) — نظير `category_descendant_ids` الخادمي.
 * تعود المعرّفات كما هي على العُقد (رقماً أو نصّاً حسب الشاشة).
 */
export const descendantIds = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId,
): Array<T['id']> => {
  const { byId, childrenOf } = buildCategoryIndex(categories);
  const root = byId.get(keyOf(categoryId));
  if (!root) return [];
  const out: Array<T['id']> = [];
  const seen = new Set<string>();
  const stack: T[] = [root];
  while (stack.length) {
    const node = stack.pop() as T;
    const key = keyOf(node.id);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(node.id);
    for (const child of childrenOf.get(key) ?? []) stack.push(child);
  }
  return out;
};

/** أسماء المسار من الجذر إلى التصنيف — للـbreadcrumb «أ ‹ ب ‹ ج». */
export const categoryPath = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId,
): string[] => {
  const { byId } = buildCategoryIndex(categories);
  const names: string[] = [];
  const seen = new Set<string>();
  let node = byId.get(keyOf(categoryId));
  while (node && !seen.has(keyOf(node.id))) {
    seen.add(keyOf(node.id));
    names.unshift(nameOf(node));
    const parent = parentKeyOf(node, byId);
    node = parent != null ? byId.get(parent) : undefined;
  }
  return names;
};

/** المسار نصّاً — الفاصل «‹» يقرأ من اليمين لليسار طبيعياً في العربية. */
export const categoryPathLabel = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId | null, fallback = '',
): string => {
  if (categoryId == null) return fallback;
  const path = categoryPath(categories, categoryId);
  return path.length ? path.join(' ‹ ') : fallback;
};

/**
 * التصنيفات الصالحة أباً لتصنيفٍ ما: كلُّها عداه وعدا أحفاده.
 *
 * حارس الخادم يرفض الحلقة برسالة — وهذا يمنع عرضَ الخيار أصلاً، فلا يصطدم
 * المستخدم برفضٍ كان بوسع القائمة ألا تعرضه.
 */
export const eligibleParents = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId | null,
): T[] => {
  if (categoryId == null) return categories;
  const banned = new Set(descendantIds(categories, categoryId).map(keyOf));
  return categories.filter((c) => !banned.has(keyOf(c.id)));
};
