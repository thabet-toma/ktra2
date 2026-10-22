/**
 * K2 — منطق ورقة الجرد الخالص: التجميع، التقدّم، الفلترة، فرق الحفظ، وإعادة
 * تطبيق التعديلات المحلية بعد 412، وملخّص النطاق وبناء جسم الإنشاء.
 *
 * القاعدة كلها هنا كي تُختبر بـ`node --test` (لا في مكوّنٍ يصعب اختباره)،
 * والمكوّن يرسم فقط. **مصدر الحقيقة للحفظ هو `baseline`**: قيمة الخادم وقت آخر
 * قراءة/حفظ — `undefined` تعني سطراً أُضيف محلياً لم يعرفه الخادم بعد.
 */
import { categoryPathLabel, type CategoryNodeLike } from './categoryTree.ts';
import { formatNumber } from './formatNumber.ts';
import { formatDateTimeValue } from './formatDate.ts';
import type {
  StocktakeLine, StocktakeScopeCounts, StocktakeScope,
} from '../types/inventory.ts';

/** نطاق الإنشاء في نافذة «جرد جديد» — ثلاث طرق لا رابعة. */
export type StocktakeScopeMode = 'all' | 'categories' | 'manual';

/** سطرٌ في الورقة: نسخة البند + القيمة المرجعية لحساب ما تغيّر فعلاً. */
export interface StocktakeSheetLine {
  product: number;
  product_name: string;
  product_sku: string;
  product_category: number | null;
  product_quantity_on_hand: string;
  product_is_active: boolean;
  /** الكمية الحالية كنصّ؛ `''` = غير معدود. */
  counted_quantity: string;
  counted_by_name: string;
  counted_at: string | null;
  system_quantity: string | null;
  variance: string | null;
  /** قيمة الخادم عند آخر قراءة/حفظ؛ `undefined` = سطر أُضيف محلياً. */
  baseline: string | null | undefined;
}

export interface StocktakeLineGroup {
  key: string;
  categoryId: number | null;
  label: string;
  lines: StocktakeSheetLine[];
}

export interface StocktakeSaveLine {
  product: number;
  counted_quantity: string | null;
}

export interface StocktakeLinesPayload {
  lines?: StocktakeSaveLine[];
  replace_lines?: true;
}

const UNCATEGORIZED_KEY = 'uncategorized';

/**
 * الكمية كما تُقارَن وتُرسَل وتُعرض في خانة العدّ: **تطبيعٌ رقميّ خام** —
 * «4.0000» ⇒ «4» و«2.5000» ⇒ «2.5»، بلا تجميعٍ ولا أرقامٍ محلّيةٍ ولا قصٍّ
 * يخسر رقماً؛ و`null`/الفراغ ⇒ ''. خانةُ إدخالٍ تعرض الكمية نفسها التي ستُرسَل،
 * لا صياغةً للعرض.
 */
export const normalizeQuantity = (value: string | null | undefined): string => {
  if (value == null) return '';
  const text = String(value).trim();
  if (text === '') return '';
  const number = Number(text);
  return Number.isFinite(number) ? String(number) : text;
};

/** هل القيمتان كميةً واحدة؟ (فراغ = غير معدود، و`0` كميةٌ حقيقية). */
export const quantityEquals = (
  a: string | null | undefined,
  b: string | null | undefined,
): boolean => normalizeQuantity(a) === normalizeQuantity(b);

/** شكلٌ رقميّ بلا إشارةٍ ولا فاصلةٍ عربية — يُفحص قبل `Number`. */
const QUANTITY_TEXT = /^(?:\d+(?:\.\d*)?|\.\d+)$/;

/**
 * كميةٌ معدودة صالحة؟ الفراغ «لم يُعدّ» وليس خطأً؛ وغيره رقمٌ منتهٍ غير سالب
 * بأربع منازل عشرية على الأكثر — نفس سقف `CountedQuantityField` في الخادم.
 */
export const validateCountedQuantity = (text: string | null | undefined): boolean => {
  const raw = String(text ?? '').trim();
  if (raw === '') return true;
  if (!QUANTITY_TEXT.test(raw)) return false;
  const decimals = raw.includes('.') ? raw.split('.')[1].length : 0;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 && decimals <= 4;
};

/**
 * صياغة عددٍ عربية: 1 «واحد»، 2 «اثنان»، 3–10 جمعُ قِلّة، و11+ تمييزٌ مفرد.
 * الصفر شأنُ المستدعي — يمرّر `zero` إن أراد صياغةً خاصة به.
 */
export const arabicCount = (
  count: number,
  forms: { one: string; two: string; few: string; many: string; zero?: string },
): string => {
  const n = Math.trunc(count);
  if (n === 1) return forms.one;
  if (n === 2) return forms.two;
  const label = n >= 3 && n <= 10 ? forms.few : forms.many;
  if (n === 0 && forms.zero) return forms.zero;
  return `${formatNumber(n)} ${label}`;
};

/** بندٌ من الخادم ← سطر ورقة بقيمة مرجعية. */
export const sheetLineFromStocktakeLine = (line: StocktakeLine): StocktakeSheetLine => ({
  product: line.product,
  product_name: line.product_name || line.product_sku || `منتج #${line.product}`,
  product_sku: line.product_sku || '',
  product_category: line.product_category ?? null,
  product_quantity_on_hand: line.product_quantity_on_hand ?? '0',
  product_is_active: line.product_is_active !== false,
  counted_quantity: normalizeQuantity(line.counted_quantity),
  counted_by_name: line.counted_by_name || '',
  counted_at: line.counted_at ?? null,
  system_quantity: line.system_quantity ?? null,
  variance: line.variance ?? null,
  baseline: normalizeQuantity(line.counted_quantity),
});

export const sheetLinesFromStocktake = (lines: StocktakeLine[]): StocktakeSheetLine[] =>
  (lines || []).map(sheetLineFromStocktakeLine);

/** بندٌ حقيقي (بلا منتج خدمي) قادمٌ من منتقي البحث ← سطر ورقة جديد. */
export interface ManualProductRow {
  id: number;
  sku?: string | null;
  name_ar?: string | null;
  name_en?: string | null;
  display_name?: string | null;
  brand?: string | null;
  quantity_on_hand?: string | number | null;
  category?: number | null;
  is_active?: boolean;
  is_service?: boolean;
}

/** اسم المنتج المعروض — مصدرٌ واحد لمنتقي الإضافة وسطر الورقة. */
export const productLabel = (
  product: Pick<ManualProductRow, 'id' | 'sku' | 'name_ar' | 'name_en' | 'display_name'>,
): string => product.display_name || product.name_ar || product.name_en || product.sku
  || `منتج #${product.id}`;

export const newSheetLineFromProduct = (product: ManualProductRow): StocktakeSheetLine => ({
  product: product.id,
  product_name: productLabel(product),
  product_sku: product.sku || '',
  product_category: product.category ?? null,
  product_quantity_on_hand: String(product.quantity_on_hand ?? '0'),
  product_is_active: product.is_active !== false,
  counted_quantity: '',
  counted_by_name: '',
  counted_at: null,
  system_quantity: null,
  variance: null,
  // سطرٌ أُضيف محلياً: لا قيمة خادمٍ مرجعية بعد.
  baseline: undefined,
});

/** هل عُدّ السطر؟ (`''` و`null` ليسا صفراً — الصفر كميةٌ معدودة). */
export const isCounted = (line: Pick<StocktakeSheetLine, 'counted_quantity'>): boolean =>
  String(line.counted_quantity ?? '').trim() !== '';

export interface StocktakeProgress {
  total: number;
  counted: number;
  uncounted: number;
  /** 0…1 — لأشرطة التقدّم. */
  ratio: number;
}

export const countStocktakeProgress = (
  lines: Array<Pick<StocktakeSheetLine, 'counted_quantity'>>,
): StocktakeProgress => {
  const total = lines.length;
  const counted = lines.filter(isCounted).length;
  return {
    total,
    counted,
    uncounted: total - counted,
    ratio: total === 0 ? 0 : counted / total,
  };
};

export interface StocktakeFilter {
  query?: string;
  /** وضع العرض: الكل/المعدود/غير المعدود/الفروقات. */
  mode?: 'all' | 'counted' | 'uncounted' | 'variance';
  /** الجرد المُرحَّل يقرأ الفرق المخزَّن؛ المسودّة تحسبه حياً. */
  posted?: boolean;
}

/**
 * فرق السطر المعروض: المخزَّن عند العرض المُرحَّل، وإلا المعدود − رصيد النظام.
 * `null` يعني «لم يُعدّ» أو لا لقطة — لا صفراً.
 */
export const stocktakeVariance = (
  line: Pick<StocktakeSheetLine, 'counted_quantity' | 'product_quantity_on_hand' | 'variance'>,
  posted = false,
): number | null => {
  if (posted) {
    if (line.variance == null || line.variance === '') return null;
    const saved = Number(line.variance);
    return Number.isFinite(saved) ? saved : null;
  }
  if (!isCounted(line)) return null;
  const counted = Number(line.counted_quantity);
  const system = Number(line.product_quantity_on_hand);
  if (!Number.isFinite(counted) || !Number.isFinite(system)) return null;
  return counted - system;
};

/** فلترة العرض: بحثٌ في الاسم والرمز + وضع العرض (غير المعدود/المعدود/الفروقات). */
export const filterStocktakeLines = (
  lines: StocktakeSheetLine[],
  filter: StocktakeFilter = {},
): StocktakeSheetLine[] => {
  const query = (filter.query ?? '').trim().toLocaleLowerCase('ar');
  const mode = filter.mode ?? 'all';
  return lines.filter((line) => {
    if (mode === 'uncounted' && isCounted(line)) return false;
    if (mode === 'counted' && !isCounted(line)) return false;
    if (mode === 'variance') {
      const variance = stocktakeVariance(line, !!filter.posted);
      if (variance === null || variance === 0) return false;
    }
    if (!query) return true;
    const haystack = `${line.product_name} ${line.product_sku}`.toLocaleLowerCase('ar');
    return haystack.includes(query);
  });
};

/**
 * تجميع الورقة: مجموعةٌ لكل **تصنيف مباشر** باسم مساره الكامل، و«بدون تصنيف»
 * أخيراً. التصنيفات بلا بنود لا تظهر (شاشة عدٍّ لا شجرةٌ كاملة).
 */
export const groupStocktakeLines = <T extends CategoryNodeLike>(
  lines: StocktakeSheetLine[],
  categories: T[],
): StocktakeLineGroup[] => {
  const groups = new Map<string, StocktakeLineGroup>();
  for (const line of lines) {
    const categoryId = line.product_category ?? null;
    const key = categoryId == null ? UNCATEGORIZED_KEY : `cat:${categoryId}`;
    let group = groups.get(key);
    if (!group) {
      // `categoryPathLabel` يعيد البديل نفسه حين لا مسار (لا ''): البديل
      // غير فارغ دائماً، فلا fallback ثانٍ.
      const label = categoryId == null
        ? 'بدون تصنيف'
        : categoryPathLabel(categories, categoryId, `تصنيف #${categoryId}`);
      group = { key, categoryId, label, lines: [] };
      groups.set(key, group);
    }
    group.lines.push(line);
  }
  const ordered = [...groups.values()].filter((group) => group.categoryId != null);
  ordered.sort((a, b) => a.label.localeCompare(b.label, 'ar'));
  // مجموعةٌ لا تُنشأ إلا عند دفع بندٍ إليها، فوجودها يعني أنها غير فارغة.
  const uncategorized = groups.get(UNCATEGORIZED_KEY);
  if (uncategorized) ordered.push(uncategorized);
  return ordered;
};

/**
 * جسم `lines` للحفظ: **فرقُ ما تغيّر وحده** — السطر المضاف (بلا `baseline`) أو
 * الذي اختلفت كميته عن آخر قراءة. لا سطرَ بلا تغيير يُرسَل.
 *
 * وإذا حذف المستخدم سطراً فالحذف لا يُعبَّر عنه بالغياب وحده (عقد K1 يحفظ
 * غير المُرسَل)، فيُرسَل كلُّ الحالي مع `replace_lines: true` — هي الدلالة
 * الصريحة الوحيدة للحذف.
 */
export const buildStocktakeLinesPayload = (
  lines: StocktakeSheetLine[],
  removedCount = 0,
): StocktakeLinesPayload => {
  const toPayload = (line: StocktakeSheetLine): StocktakeSaveLine => ({
    product: line.product,
    counted_quantity: isCounted(line) ? String(line.counted_quantity).trim() : null,
  });
  if (removedCount > 0) {
    return { replace_lines: true, lines: lines.map(toPayload) };
  }
  const changed = lines.filter(
    (line) => line.baseline === undefined || !quantityEquals(line.counted_quantity, line.baseline),
  );
  if (!changed.length) return {};
  return { lines: changed.map(toPayload) };
};

export interface ReapplyResult {
  lines: StocktakeSheetLine[];
  /** عدد البنود التي أُعيد تطبيق تعديلٍ محليٍّ عليها. */
  reapplied: number;
}

/**
 * بعد 412: نقرأ النسخة الجديدة ثم نضع تعديلات المستخدم فوقها — لا نطلب منه
 * إعادة كتابتها ولا نمحوها بصمت. السطر الذي لم يمسّه يبقى كما وصل من الخادم
 * (وربما تغيّر هناك)، والمعدَّل محلياً يعود بقيمته المحلية فوق `baseline`
 * الجديد، والمضاف محلياً يبقى مضافاً.
 *
 * **والخاتم لا يُنقل مع القيمة**: `counted_by_name`/`counted_at` يخصّان القيمة
 * التي وصلت من الخادم، وقيمة المستخدم لم يحفظها أحدٌ بعد — فتُمحى ويقول عمود
 * «عدّه» «تعديلك — غير محفوظ» حتى الحفظ التالي.
 */
export const reapplyLocalEdits = (
  freshLines: StocktakeSheetLine[],
  localLines: StocktakeSheetLine[],
): ReapplyResult => {
  const lines = freshLines.map((line) => ({ ...line }));
  const byProduct = new Map(lines.map((line) => [line.product, line]));
  let reapplied = 0;
  for (const local of localLines) {
    const target = byProduct.get(local.product);
    const addedLocally = local.baseline === undefined;
    const changedLocally = !addedLocally && !quantityEquals(local.counted_quantity, local.baseline);
    if (!addedLocally && !changedLocally) continue;
    // أُضيف محلياً ولم يُعدّ بعد، ثم وصل عدٌّ من عاملٍ آخر لنفس المنتج: القيمة
    // الواردة أحدث من «إضافةٍ بلا قيمة» — تبقى، ويبقى السطر في الورقة.
    if (addedLocally && !isCounted(local) && target) continue;
    // القيمة المحلية هي عين ما وصل من الخادم: لا تعديلَ فعليّاً — يبقى خاتم
    // الخادم (اسم مَن عدّ ووقته) ولا يُحتسب البند في «أُعيد تطبيق تعديلاتك».
    if (target && quantityEquals(local.counted_quantity, target.counted_quantity)) continue;
    reapplied += 1;
    if (target) {
      target.counted_quantity = local.counted_quantity;
      // الخاتم المعروض يخصّ القيمة الجديدة؛ الحفظ التالي هو من سيختم باسم المستخدم.
      target.counted_by_name = '';
      target.counted_at = null;
      continue;
    }
    // سطرٌ أضافه المستخدم (أو حُذف من الخادم بعد تعديله) — لا يضيع.
    lines.push({ ...local, counted_by_name: '', counted_at: null, baseline: undefined });
    byProduct.set(local.product, lines[lines.length - 1]);
  }
  return { lines, reapplied };
};

/**
 * استعادة مسودّةٍ محلية (تلقائية أو من شريط «استعرض مسودتي»): **تُعاد على بنود
 * الخادم المحمَّلة الآن** لا على بنود لحظة حفظ المسودّة. مرجعيات المسودّة قديمة،
 * ووضعُ قيمها فوق توكنٍ جديد يعني أن الحفظ التالي يرسل أرقاماً سبقها عدٌّ أحدث
 * — ويمحو عمل عاملٍ آخر بتوكنٍ صحيح.
 *
 * والحذف المحلي يُعاد فقط لمنتجٍ ما زال على الخادم؛ منتجٌ حُذف هناك لا حاجة
 * لحذفه (وطلبُ حذفه قد يرفضه الخادم).
 */
export const rebaseDraftRestore = (
  serverLines: StocktakeSheetLine[],
  draftLines: StocktakeSheetLine[],
  draftRemovedIds: number[] = [],
): { lines: StocktakeSheetLine[]; reapplied: number; removedIds: number[] } => {
  const { lines, reapplied } = reapplyLocalEdits(serverLines, draftLines);
  const serverIds = new Set(serverLines.map((line) => line.product));
  const removedIds = draftRemovedIds.filter((productId) => serverIds.has(productId));
  return {
    lines: lines.filter((line) => !removedIds.includes(line.product)),
    reapplied: reapplied + removedIds.length,
    removedIds,
  };
};

/** هل القيمة المعروضة تعديلٌ محليٌّ لم يُحفظ؟ (خاتمها ليس خاتمها). */
export const isLocallyEdited = (
  line: Pick<StocktakeSheetLine, 'counted_quantity' | 'baseline'>,
): boolean => (line.baseline === undefined
  ? isCounted(line)
  : !quantityEquals(line.counted_quantity, line.baseline));

/**
 * نصّ عمود «عدّه»: الخاتم المعروض **يخصّ القيمة المعروضة**. القيمة المحلية غير
 * المحفوظة لا يُلصق بها اسم من عدّ قيمةً أخرى، وغير المعدود بلا خاتم.
 */
export const stocktakeStampText = (
  line: Pick<
    StocktakeSheetLine,
    'counted_quantity' | 'baseline' | 'counted_by_name' | 'counted_at'
  >,
): string => {
  if (!isCounted(line)) return '';
  if (isLocallyEdited(line)) return 'تعديلك — غير محفوظ';
  return [line.counted_by_name, formatDateTimeValue(line.counted_at)]
    .filter(Boolean).join(' · ');
};

/**
 * رأس ورقة الجرد: تاريخٌ ومستودعٌ وملاحظات. «كل المخزون» (`null` في الخادم) هو
 * `''` في الشاشة — كل من ينتج رأساً (الخادم، الحالة، الحمولة المحفوظة) يطبّعه إليه.
 */
export interface StocktakeHeader {
  date: string;
  warehouse: number | '';
  notes: string;
}

/**
 * رأسٌ **مدخَلٌ** إلى `rebaseHeader` من حمولة مسودّةٍ مقروءةٍ من IndexedDB: النوع
 * يقول `number | ''` لكن JSON المخزَّن قد يحمل `null` لمستودعه، فيبقى مقبولاً
 * هنا وحده.
 */
export type StocktakeHeaderInput = Omit<StocktakeHeader, 'warehouse'> & {
  warehouse: StocktakeHeader['warehouse'] | null;
};

export interface StocktakeHeaderRebase {
  header: StocktakeHeader;
  /** عدد الحقول التي بقي فيها تعديل المستخدم (لم يأخذها الخادم). */
  kept: number;
}

/**
 * رأسُ «تحديث» يتبع قاعدة البنود نفسها: الحقل الذي يختلف عن مرجعيته (آخر رأسٍ
 * من الخادم بُني عليه ما في الشاشة) هو تعديلُ المستخدم فيبقى، والحقل غير
 * المعدَّل يأخذ قيمة الخادم الجديدة. المقارنة قيمةً: `''` و`null` في المستودع
 * سواء (والتطبيع إلى `''` هنا للمدخَلين المحلّيين وحدهما — حمولة المسودّة قد
 * تحمل `null`؛ ورأس الخادم يصل مطبَّعاً)، والأرقام بأرقامها.
 */
export const rebaseHeader = (
  serverHeader: StocktakeHeader,
  localHeader: StocktakeHeaderInput,
  localBaseline: StocktakeHeaderInput,
): StocktakeHeaderRebase => {
  const warehouseId = (value: StocktakeHeaderInput['warehouse']): number | '' =>
    (value == null || value === '' ? '' : Number(value));
  let kept = 0;
  const pick = (local: string, baseline: string, server: string): string => {
    if (local === baseline) return server;
    kept += 1;
    return local;
  };
  const localWarehouse = warehouseId(localHeader.warehouse);
  const warehouseEdited = localWarehouse !== warehouseId(localBaseline.warehouse);
  if (warehouseEdited) kept += 1;
  return {
    header: {
      date: pick(localHeader.date, localBaseline.date, serverHeader.date),
      warehouse: warehouseEdited ? localWarehouse : serverHeader.warehouse,
      notes: pick(localHeader.notes, localBaseline.notes, serverHeader.notes),
    },
    kept,
  };
};

/**
 * هويّة مسودّة الورقة: الإصدار الثالث يحمل رقم الجرد الذي كُتبت له ومرجعية
 * الرأس (`headerBaseline`). مسودّةٌ من إصدارٍ أقدم (بلا `baseline`، وربما
 * `product: ""`، وبلا مرجعية رأس) أو لجردٍ آخر لا تُطبَّق على جردٍ مفتوح —
 * وإلّا محت مسودّةُ A أرقامَ B.
 */
export interface StocktakeDraftIdentity {
  v?: number;
  docId?: number | null;
}

export const isApplicableStocktakeDraft = (
  payload: StocktakeDraftIdentity | null | undefined,
  openDocId: number | null | undefined,
): boolean => payload?.v === 3 && openDocId != null && payload.docId === openDocId;

export interface ScopeSelectionSummary {
  /** N — عدد المنتجات التي ستُجرد. */
  products: number;
  /** M — عدد التصنيفات (مع «بدون تصنيف» كواحدٍ عند اختياره). */
  categories: number;
}

/** ملخّص «سيُجرد N منتجاً في M تصنيفات» — من عدّادات الخادم وحدها. */
export const summarizeScopeSelection = (options: {
  mode: StocktakeScopeMode;
  checkedIds: number[];
  uncategorized: boolean;
  counts: StocktakeScopeCounts | null;
}): ScopeSelectionSummary => {
  const { mode, checkedIds, uncategorized, counts } = options;
  if (!counts || mode === 'manual') return { products: 0, categories: 0 };
  if (mode === 'all') {
    const populated = Object.values(counts.categories || {}).filter((count) => count > 0).length;
    return {
      products: counts.all,
      categories: populated + (counts.uncategorized > 0 ? 1 : 0),
    };
  }
  const unique = [...new Set(checkedIds)];
  let products = uncategorized ? counts.uncategorized : 0;
  for (const id of unique) products += counts.categories?.[String(id)] ?? 0;
  return { products, categories: unique.length + (uncategorized ? 1 : 0) };
};

export interface StocktakeCreateBody {
  stocktake_date: string;
  warehouse: number | null;
  notes: string;
  scope?: StocktakeScope;
}

/**
 * جسم `POST stocktakes/`: نطاقٌ بالكامل لـ«كل/تصنيفات»، وبلا `scope` إطلاقاً
 * لـ«يدوي» (الخادم يقرؤه جرداً يدوياً بلا بنود). لا `lines` في أيّ وضع.
 */
export const buildStocktakeCreateBody = (options: {
  mode: StocktakeScopeMode;
  stocktakeDate: string;
  warehouse: number | null;
  notes: string;
  checkedIds: number[];
  uncategorized: boolean;
  includeInactive: boolean;
}): StocktakeCreateBody => {
  const body: StocktakeCreateBody = {
    stocktake_date: options.stocktakeDate,
    warehouse: options.warehouse,
    notes: options.notes,
  };
  if (options.mode === 'manual') return body;
  if (options.mode === 'all') {
    body.scope = {
      all: true,
      categories: [],
      uncategorized: false,
      include_inactive: options.includeInactive,
    };
    return body;
  }
  body.scope = {
    all: false,
    categories: [...new Set(options.checkedIds)].sort((a, b) => a - b),
    uncategorized: options.uncategorized,
    include_inactive: options.includeInactive,
  };
  return body;
};

/** هل يسمح النطاق بالإنشاء؟ اليدوي دائماً، وغيره يحتاج منتجاً واحداً على الأقل. */
export const canCreateFromScope = (
  mode: StocktakeScopeMode,
  summary: ScopeSelectionSummary,
): boolean => mode === 'manual' || summary.products > 0;
