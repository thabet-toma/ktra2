/**
 * T-ITEMS M2 — شجرة التصنيفات: مصدرٌ واحد للترتيب والعمق والأحفاد والمسار.
 *
 * كانت الخوارزمية نفسها مكتوبةً أربع مرّات — في منتقي التصنيف، وشجرة الفاتورة،
 * وجدول إدارة التصنيفات، وجدول المنتجات المجمّع — بأربعة أسماء وأربعة سلوكيات
 * عند الحالات الحدّية: واحدة تعامل التصنيف اليتيم (أبوه خارج القائمة) جذراً
 * وأخرى تُسقطه من الشجرة فلا يعود قابلاً للاختيار أبداً.
 *
 * القاعدة هنا مرّةً واحدة على نسق `utils/accountTree.ts`.
 *
 * **المصطلح (T-PRODUCT)**: ثلاث طبقات لا اثنتان — «تصنيف» = فئةٌ في الشجرة
 * (`Category`) · «صنف» = العائلة/الموديل (`variant_group`) · «منتج» = السجلّ
 * القابل للبيع (`Product`). هذه الوحدة تخصّ الطبقة الأولى وحدها.
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
export const categoryKey = (id: CategoryId): string => String(id);

/** الاسم الداخلي القصير للمفتاح نفسه — لا نسخة ثانية من القاعدة. */
const keyOf = categoryKey;

/** فاصل المسار «أ ‹ ب» — يُبنى به النصّ في كل موضع، فلا يفترق فاصلٌ عن آخر. */
export const PATH_SEPARATOR = ' ‹ ';

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

/**
 * العُقد من عقدةٍ صعوداً إلى الجذر (العقدة نفسها أولاً) — المشي الصعودي الوحيد
 * في الوحدة، وعليه تُبنى المسارات والأسلاف معاً. محروسٌ من الحلقات، ويتوقّف
 * عند الأب الغائب عن القائمة (تصنيفٌ يتيم).
 */
const walkUpToRoot = <T extends CategoryNodeLike>(
  byId: Map<string, T>, start: T | undefined,
): T[] => {
  const out: T[] = [];
  const seen = new Set<string>();
  let node = start;
  while (node && !seen.has(keyOf(node.id))) {
    seen.add(keyOf(node.id));
    out.push(node);
    const parent = parentKeyOf(node, byId);
    node = parent != null ? byId.get(parent) : undefined;
  }
  return out;
};

/** أسلاف العقدة (الأب حتى الجذر) من فهرسٍ جاهز. */
const ancestorsOf = <T extends CategoryNodeLike>(
  byId: Map<string, T>, idKey: string,
): T[] => walkUpToRoot(byId, byId.get(idKey)).slice(1);

/** أسماء المسار من الجذر إلى العقدة — الفاصل يضيفه المستدعي. محروسٌ من الحلقات. */
const pathNamesTo = <T extends CategoryNodeLike>(
  byId: Map<string, T>, start: T | undefined,
): string[] => walkUpToRoot(byId, start).map(nameOf).reverse();

/**
 * معرّفات الأسلاف من الأب حتى الجذر (بلا العقدة نفسها) — لفتح المسار إلى
 * تصنيفٍ محدَّد. تُعاد كما هي على العُقد، ويتوقّف المشي عند اليتيم والحلقة.
 */
export const ancestorIds = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId,
): Array<T['id']> => {
  const { byId } = buildCategoryIndex(categories);
  return ancestorsOf(byId, keyOf(categoryId)).map((node) => node.id);
};

/** أسماء المسار من الجذر إلى التصنيف — للـbreadcrumb «أ ‹ ب ‹ ج». */
export const categoryPath = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId,
): string[] => {
  const { byId } = buildCategoryIndex(categories);
  return pathNamesTo(byId, byId.get(keyOf(categoryId)));
};

/** المسار نصّاً — الفاصل «‹» يقرأ من اليمين لليسار طبيعياً في العربية. */
export const categoryPathLabel = <T extends CategoryNodeLike>(
  categories: T[], categoryId: CategoryId | null, fallback = '',
): string => {
  if (categoryId == null) return fallback;
  const path = categoryPath(categories, categoryId);
  return path.length ? path.join(PATH_SEPARATOR) : fallback;
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

// ─── C1 — الاختيار: مجموعةٌ صريحة من المعرّفات المؤشَّرة ─────────────────────

/**
 * دلالة الاختيار (قرار الخطة 3): كل عقدة مؤشَّرة تعني **منتجاتها المباشرة**،
 * لا أحفادها. الأب المؤشَّر يؤشّر أحفاده بصرياً كي يبقى «تحديد الكل» بضغطة،
 * لكن إلغاء ابنٍ يُبقي منتجات الأب المباشرة مشمولة ويجعل الأب «جزئياً» —
 * ولهذا لم تُعرَّف الحالة بأنها «الأب يعني كل أحفاده»: ذاك التعبير يمحو
 * «الجزئي» ولا يُكتب.
 */
export type CategoryCheckState = 'on' | 'off' | 'partial';

/**
 * حالة مربّع عقدة: مؤشَّرة وكل أحفادها · لا هي ولا أيّ حفيد · وإلا جزئية.
 *
 * عقدةٌ يتيمة (أبوها خارج القائمة) تُقرأ جذراً، وحلقة بياناتٍ لا تُعلّقها —
 * كلتاهما محروستان في `descendantIds`.
 */
export const checkState = <T extends CategoryNodeLike>(
  categories: T[], checked: ReadonlySet<T['id']>, categoryId: T['id'],
): CategoryCheckState => {
  const keys = new Set<string>();
  for (const id of checked) keys.add(keyOf(id));
  const selfKey = keyOf(categoryId);
  const descendants = descendantIds(categories, categoryId)
    .map(keyOf)
    .filter((key) => key !== selfKey);
  if (!keys.has(selfKey)) {
    return descendants.some((key) => keys.has(key)) ? 'partial' : 'off';
  }
  return descendants.every((key) => keys.has(key)) ? 'on' : 'partial';
};

/**
 * حالة **كل** العُقد في مرورٍ واحد (فهرسٌ واحد + مشيٌ بعديّ واحد) بدل
 * `checkState` لكل صفّ — فتُبنى الشجرة مرّةً لكل رسمٍ لا مرّةً لكل عقدة.
 *
 * الحساب على مكوّنات الاتصال القويّ (Tarjan): عُقد الحلقة الواحدة تتشارك
 * مجموعة أحفادها، فيُطوى كلُّ مكوّنٍ عقدةً واحدة في التكثيف ثم تُجمع أعداد
 * الأحفاد من الأسفل. النتيجة مطابقةٌ لـ`checkState` عقدةً بعقدة، حتى في حلقة
 * بياناتٍ قديمة — اختبار التكافؤ يحرس ذلك.
 *
 * القاعدة المختصرة: مؤشَّرٌ من كل الأحفاد ⇒ `on` · بعضهم ⇒ `partial` · لا شيء ⇒ `off`.
 */
export const checkStates = <T extends CategoryNodeLike>(
  categories: T[], checked: ReadonlySet<T['id']>,
): Map<string, CategoryCheckState> => {
  const { byId, childrenOf } = buildCategoryIndex(categories);
  const checkedKeys = new Set<string>();
  for (const id of checked) checkedKeys.add(keyOf(id));

  const visitedAt = new Map<string, number>();
  const low = new Map<string, number>();
  const compOf = new Map<string, number>();
  const stack: string[] = [];
  const onStack = new Set<string>();
  const compSize: number[] = [];
  const compReach: number[] = [];
  const compCheckedReach: number[] = [];
  let counter = 0;

  const connect = (key: string) => {
    visitedAt.set(key, counter);
    low.set(key, counter);
    counter += 1;
    stack.push(key);
    onStack.add(key);

    for (const child of childrenOf.get(key) ?? []) {
      const childKey = keyOf(child.id);
      if (!visitedAt.has(childKey)) {
        connect(childKey);
        low.set(key, Math.min(low.get(key) as number, low.get(childKey) as number));
      } else if (onStack.has(childKey)) {
        low.set(key, Math.min(low.get(key) as number, visitedAt.get(childKey) as number));
      }
    }

    if (low.get(key) !== visitedAt.get(key)) return;

    const comp = compSize.length;
    const members: string[] = [];
    let member: string;
    do {
      member = stack.pop() as string;
      onStack.delete(member);
      compOf.set(member, comp);
      members.push(member);
    } while (member !== key);

    let checkedCount = 0;
    for (const m of members) if (checkedKeys.has(m)) checkedCount += 1;
    compSize.push(members.length);

    // أحفاد المكوّن: مكوّنات أبنائه في التكثيف، بلا نفسه وبلا تكرار.
    const successors = new Set<number>();
    for (const m of members) {
      for (const child of childrenOf.get(m) ?? []) {
        const childComp = compOf.get(keyOf(child.id));
        if (childComp != null && childComp !== comp) successors.add(childComp);
      }
    }
    let reach = members.length;
    let reachChecked = checkedCount;
    for (const successor of successors) {
      reach += compReach[successor];
      reachChecked += compCheckedReach[successor];
    }
    compReach.push(reach);
    compCheckedReach.push(reachChecked);
  };

  // كل عقدة تُزار — بما فيها عُقدُ حلقةٍ لا يبلغها أيّ جذر.
  for (const key of byId.keys()) if (!visitedAt.has(key)) connect(key);

  const states = new Map<string, CategoryCheckState>();
  for (const key of byId.keys()) {
    const comp = compOf.get(key) as number;
    const reach = compReach[comp];
    const reachChecked = compCheckedReach[comp];
    states.set(
      key,
      reachChecked === 0 ? 'off' : reachChecked < reach ? 'partial' : 'on',
    );
  }
  return states;
};

/**
 * تبديل عقدةٍ وشجرتها: من «مؤشَّرة» يُزيلها مع أحفادها، ومن «مطفأة» أو
 * «جزئية» يُضيفها مع أحفادها. المجموعة المُدخلة لا تُمَسّ — تعود مجموعةٌ جديدة.
 *
 * التمثيل يُطبَّع: `3` و`"3"` لا يقبعان معاً في النتيجة، كما تتساوى العُرفان
 * في الفهرس.
 */
export const toggleSubtree = <T extends CategoryNodeLike>(
  categories: T[], checked: ReadonlySet<T['id']>, categoryId: T['id'],
): Set<T['id']> => {
  const descendants = descendantIds(categories, categoryId);
  // معرّفٌ خارج القائمة (تصنيفٌ حُذف بين رسمتين) لا يُضاف شبحاً إلى القيمة.
  if (!descendants.length) return new Set<T['id']>(checked);
  const targetKeys = new Set(descendants.map(keyOf));
  const next = new Set<T['id']>(checked);
  for (const id of checked) {
    if (targetKeys.has(keyOf(id))) next.delete(id);
  }
  if (checkState(categories, checked, categoryId) !== 'on') {
    for (const id of descendants) next.add(id);
  }
  return next;
};

/**
 * شجرة `restrictTo`: العُقد المسموحة وحدها، وكلُّ عقدةٍ يُعاد ربط أبٍ لها
 * بأقرب أبٍ **مسموح** (أو `null` إن لم يوجد) — لا بالمسار الكامل.
 *
 * لولا هذا الربط لكان تأشير الأب في نطاقٍ مقصور يُدخل في القيمة أحفاداً خارج
 * النطاق لم يرها المستخدم، فصار إلغاء تأشير الأب مستحيلاً: `checkState` ترى
 * أحفاداً لا يمكن الوصول إليها. بالربط الأقرب يصير التأشير والإلغاء دورةً
 * مغلقة داخل النطاق: أ ⟵ ب ⟵ ج والمسموح {أ, ج} ⇒ أ مؤشَّرة تعني {أ, ج}.
 */
export const restrictCategories = <T extends CategoryNodeLike>(
  categories: T[], allowedIds: ReadonlyArray<CategoryId>,
): T[] => {
  const { byId } = buildCategoryIndex(categories);
  const allowed = new Set<string>(allowedIds.map(keyOf));
  const out: T[] = [];
  for (const category of categories) {
    const selfKey = keyOf(category.id);
    if (!allowed.has(selfKey)) continue;
    const nearest = ancestorsOf(byId, selfKey)
      .find((node) => allowed.has(keyOf(node.id)));
    const copy = { ...category };
    copy.parent = nearest ? nearest.id : null;
    out.push(copy);
  }
  return out;
};

/**
 * مفاتيح صفوف المسار في نطاقٍ مقصور: أسلاف كل عقدةٍ مسموحة، بلا العُقد
 * المسموحة نفسها. تُزرَع بها `expanded` كي يُرى المسموح عند أوّل رسم — وإلا
 * بقي مخبوئاً تحت جذورٍ مطويّة يفتحها المستخدم واحدةً واحدة بيده.
 */
export const restrictPathKeys = <T extends CategoryNodeLike>(
  categories: T[], allowedIds: ReadonlyArray<CategoryId>,
): Set<string> => {
  const { byId } = buildCategoryIndex(categories);
  const keys = new Set<string>();
  for (const id of allowedIds) {
    for (const ancestor of ancestorsOf(byId, keyOf(id))) keys.add(keyOf(ancestor.id));
  }
  return keys;
};

export interface VisibleTreeRowOptions {
  /** مفاتيح العُقد المفتوحة — الاستعلام يُلغي أثرها ويفتح المسارات المطابقة. */
  expanded: ReadonlySet<string>;
  /** نطاقٌ مقصور: المسار إلى كل عقدةٍ مسموحة يُعرض غير قابلٍ للاختيار. */
  restrictTo?: ReadonlyArray<CategoryId> | null;
  query?: string;
}

export interface VisibleCategoryRow<T extends CategoryNodeLike> {
  category: T;
  id: T['id'];
  depth: number;
  hasChildren: boolean;
  /** خارج `restrictTo`: سطرُ مسارٍ للوصول وحده، لا اختيار. */
  selectable: boolean;
}

/**
 * صفوف العرض بترتيب العمق: تتقيّد بالطيّ و`restrictTo` واستعلام البحث، وتُبقي
 * `depth` و`hasChildren` للرسم ولوحة المفاتيح. المشي محروسٌ من الحلقات.
 */
export const visibleTreeRows = <T extends CategoryNodeLike>(
  categories: T[], options: VisibleTreeRowOptions,
): Array<VisibleCategoryRow<T>> => {
  const { byId, childrenOf } = buildCategoryIndex(categories);
  const allowed = options.restrictTo
    ? new Set<string>(options.restrictTo.map(keyOf))
    : null;
  const q = (options.query ?? '').trim();
  let visible: Set<string> | null = null;

  if (allowed) {
    visible = new Set<string>(allowed);
    for (const key of allowed) {
      for (const ancestor of ancestorsOf(byId, key)) visible.add(keyOf(ancestor.id));
    }
  }
  if (q) {
    // مع `restrictTo` البحثُ **تقاطعٌ لا اتحاد**: مطابقاتُ النطاق ومساراتها
    // وحدها. الاتّحاد كان يعرض المسموح كلَّه فوق نتائج البحث، فلا يُرشَّح شيء
    // ولا تبلغ الشاشةُ «لا تطابق» أبداً، وتظهر صفوفٌ لا علاقة لها بالاستعلام.
    const hits = searchCategories(categories, q).filter(
      (hit) => !allowed || allowed.has(keyOf(hit.id)),
    );
    visible = new Set<string>();
    for (const hit of hits) {
      const key = keyOf(hit.id);
      visible.add(key);
      for (const ancestor of ancestorsOf(byId, key)) visible.add(keyOf(ancestor.id));
    }
  }

  const rows: Array<VisibleCategoryRow<T>> = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    for (const category of childrenOf.get(parent) ?? []) {
      const key = keyOf(category.id);
      if (seen.has(key)) continue;
      if (visible && !visible.has(key)) continue;
      seen.add(key);
      const children = childrenOf.get(key) ?? [];
      const hasChildren = children.some((c) => !visible || visible.has(keyOf(c.id)));
      rows.push({
        category,
        id: category.id,
        depth,
        hasChildren,
        selectable: !allowed || allowed.has(key),
      });
      // استعلام البحث يفتح الفروع المطابقة تلقائياً، وإلا فحالة الطيّ هي الحكم.
      if (hasChildren && (q || options.expanded.has(key))) walk(key, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
};

/**
 * قصٌّ وتوحيدُ المسافات إلى مسافةٍ واحدة — **بلا مسّ الأحرف**، فيصلح لما يُرسَل
 * إلى الخادم ويُعرض («مكاتب  جديدة» ⇒ «مكاتب جديدة») قبل أيّ تطبيعٍ للمقارنة.
 */
export const normalizeSpaces = (text: string): string => text.trim().replace(/\s+/g, ' ');

/**
 * التطبيع العربي **للمقارنة وحدها**: أ/إ/آ/ٱ ← ا · ى ← ي · ة ← ه · وحذف
 * التشكيل (U+064B–U+0652 و U+0670) والتطويل (U+0640)، ثم حالة الأحرف، ومعه
 * `normalizeSpaces` فمسافتان مكرّرتان لا تمنعان مطابقةً.
 *
 * النصّ المعروض يبقى الأصل — مطابقةُ «اطارات» لـ«إطارات» لا تعني عرض المعرّف
 * مطبَّعاً في الشجرة ولا في المسار.
 */
export const normalizeArabic = (text: string): string => normalizeSpaces(text
  .replace(/[\u064B-\u0652\u0670]/g, '')
  .replace(/\u0640/g, '')
  .replace(/[\u0623\u0625\u0622\u0671]/g, '\u0627')
  .replace(/\u0649/g, '\u064A')
  .replace(/\u0629/g, '\u0647')
  .toLocaleLowerCase('ar'));

/** كلمات النصّ بعد التطبيع — تفصلها أيُّ مسافةٍ بيضاء. */
const wordsOf = (text: string): string[] => normalizeArabic(text).split(/\s+/).filter(Boolean);

/**
 * رتبة مقطعٍ واحد: 0 يبدأ المقطع بالاستعلام · 1 الاستعلام يبدأ **عند حدّ كلمةٍ**
 * لا هي الأولى · `null` لا مطابقة.
 *
 * المقارنة على حدّ كلمة لا في أيّ موضع، فـ«ش» تصيب «شواحن» و«قطع شاحنات» ولا
 * تصيب «مشاحن». والاستعلام يُقارن كاملاً (بما فيه مسافته) بكلّ لاحقةٍ من كلماته:
 * «قطع غيار» تبدأ بها «قطع غيار» (رتبة 0) وتَلي في «زيت قطع غيار» (رتبة 1)،
 * و«طع غيار» لا تصيب شيئاً — وفحصُ كلمةٍ مفردة وحدها كان يُسقط الأولى.
 */
const segmentRank = (segment: string, query: string): 0 | 1 | null => {
  const words = wordsOf(segment);
  if (!words.length) return null;
  if (words.join(' ').startsWith(query)) return 0;
  for (let i = 1; i < words.length; i += 1) {
    if (words.slice(i).join(' ').startsWith(query)) return 1;
  }
  return null;
};

/**
 * رتبة مطابقة الاستعلام المطبَّع على مسارٍ من الأسماء (الجذر أولاً):
 * 0 اسمُ التصنيف نفسه يبدأ بالاستعلام · 1 كلمةٌ غير الأولى في اسمه تبدأ به ·
 * 2 مقطعٌ أعلى في المسار وحده (الأب أو الجدّ) · `null` لا مطابقة.
 *
 * الرتبة هي التي تُقدّم ما يبدأ به المستخدمُ بحثَه على ما صادفه في أبٍ بعيد —
 * وترتيب المسار يحكم داخل كل رتبة وحدها.
 */
const searchRank = (path: string[], query: string): number | null => {
  const own = segmentRank(path[path.length - 1] ?? '', query);
  if (own != null) return own;
  return path.slice(0, -1).some((segment) => segmentRank(segment, query) != null) ? 2 : null;
};

/**
 * بحث التصنيفات: مطابقةٌ غير حسّاسة لحالة الأحرف على **بداية أيّ كلمةٍ في أيّ
 * مقطع** من المسار — لا «يحوي» في أيّ موضع (فـ«ش» تصيب «شواحن» و«قطع شاحنات»
 * ولا تصيب «مشاحن») — بتطبيعٍ عربي على الطرفين (`normalizeArabic`).
 *
 * والنتيجة تحمل المسار الكامل كي يتميّز تصنيفان بالاسم نفسه، مرتّبةً بـ`searchRank`
 * ثم بالمسار داخل الرتبة. والاستعلام الفارغ يعيد `[]` — فالشجرة وحدها شاشةُ الفراغ.
 */
export const searchCategories = <T extends CategoryNodeLike>(
  categories: T[], query: string,
): Array<{ id: T['id']; pathLabel: string }> => {
  // الاستعلام يمرّ بالتطبيع نفسه: قصٌّ وتوحيدُ مسافاتٍ وحذفُ تشكيل (…).
  const q = normalizeArabic(query);
  if (!q) return [];
  const { byId } = buildCategoryIndex(categories);
  const hits: Array<{ id: T['id']; pathLabel: string; rank: number }> = [];
  for (const category of categories) {
    const path = pathNamesTo(byId, byId.get(keyOf(category.id)));
    const rank = searchRank(path, q);
    if (rank == null) continue;
    hits.push({
      id: category.id,
      pathLabel: path.join(PATH_SEPARATOR) || nameOf(category),
      rank,
    });
  }
  hits.sort((a, b) => a.rank - b.rank || a.pathLabel.localeCompare(b.pathLabel, 'ar'));
  return hits.map(({ id, pathLabel }) => ({ id, pathLabel }));
};
