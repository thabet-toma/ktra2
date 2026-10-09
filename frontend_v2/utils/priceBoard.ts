/**
 * جدول أسعار الاستيراد (PB-2): كل منطق المقارنة والإدخال خالصاً بلا React.
 *
 * القاعدة المحورية: المقارنة بين الموردين على `unit_price_base` (السعر بعملة
 * الأساس بعد التحويل) لا على `unit_price` — مورّد بالـCNY وآخر بالـUSD لا
 * يُقارَنان بأرقامهما الخام. الخادم هو من يحسب `unit_price_base`؛ هنا لا نحسبه
 * أبداً، وسعرٌ بلا قيمة أساس (لم يؤكّده الخادم بعد) يُستبعد من الترتيب بدل أن
 * يُرتَّب على تخمين.
 */

import { formatNumber } from "./formatNumber.ts";

/** فرق أقل من هذا يُعدّ تعادلاً (أخطاء الفاصلة العائمة بين نصّين عشريين). */
const EPSILON = 1e-9;

/** سعر وحدة للعرض: حتى 4 منازل (أسعار الأصناف تحتاج أكثر من منزلتين) مع فاصل الآلاف. */
export function formatBoardPrice(value: string | number | null | undefined): string {
  return formatNumber(value, { maxDecimals: 4, group: true, fallback: "—" });
}

export interface BoardPriceLike {
  item: number;
  board_supplier: number;
  unit_price: string;
  unit_price_base?: string | null;
  note?: string;
}

export interface RankedOffer<P extends BoardPriceLike = BoardPriceLike> {
  offer: P;
  base: number;
  /** ترتيب تنافسي: المتعادلان في الأرخص كلاهما 1 والتالي 3. */
  rank: number;
}

/** رقمٌ منتهٍ من نصّ عشري الخادم، وإلا `null`. */
export function parseAmount(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** عروض صنفٍ واحد التي لها قيمة أساس مؤكَّدة. */
export function offersForItem<P extends BoardPriceLike>(prices: P[], itemId: number): P[] {
  return prices.filter((p) => p.item === itemId && parseAmount(p.unit_price_base) !== null);
}

/** العروض من الأرخص (بعملة الأساس) إلى الأغلى، الترتيب الأصلي يحسم التعادل. */
export function rankOffers<P extends BoardPriceLike>(offers: P[]): RankedOffer<P>[] {
  const sorted = offers
    .map((offer, index) => ({ offer, base: parseAmount(offer.unit_price_base), index }))
    .filter((x): x is { offer: P; base: number; index: number } => x.base !== null)
    .sort((a, b) => a.base - b.base || a.index - b.index);
  return sorted.map((x) => ({
    offer: x.offer,
    base: x.base,
    rank: 1 + sorted.filter((y) => y.base < x.base - EPSILON).length,
  }));
}

/**
 * الموردون الأرخص في الصنف — كلّهم عند التعادل. فارغة حين يقلّ العدد عن
 * عرضين: «الأرخص» بين عرضٍ واحد لا معنى له ولا يُلوَّن.
 */
export function cheapestSupplierIds(offers: BoardPriceLike[]): Set<number> {
  const ranked = rankOffers(offers);
  if (ranked.length < 2) return new Set();
  return new Set(ranked.filter((r) => r.rank === 1).map((r) => r.offer.board_supplier));
}

/** أرخص عرض (أول المتعادلين) ولو كان وحيداً — لعمود الخلاصة. */
export function bestOffer<P extends BoardPriceLike>(offers: P[]): RankedOffer<P> | null {
  return rankOffers(offers)[0] ?? null;
}

/**
 * فرق الأغلى عن الأرخص بالنسبة المئوية (عدد صحيح). `null` حين لا مقارنة
 * (أقل من عرضين) أو حين الأرخص صفر فلا نسبة معرَّفة.
 */
export function spreadPercent(offers: BoardPriceLike[]): number | null {
  const ranked = rankOffers(offers);
  if (ranked.length < 2) return null;
  const low = ranked[0].base;
  const high = ranked[ranked.length - 1].base;
  if (low <= 0) return null;
  return Math.round(((high - low) / low) * 100);
}

/** ترتيب مورّدٍ في صنف: `rank` من `total` عروضٍ مؤكَّدة؛ `null` إن لم يعرض. */
export function supplierRankInItem(
  prices: BoardPriceLike[],
  itemId: number,
  boardSupplierId: number,
): { rank: number; total: number } | null {
  const ranked = rankOffers(offersForItem(prices, itemId));
  const mine = ranked.find((r) => r.offer.board_supplier === boardSupplierId);
  return mine ? { rank: mine.rank, total: ranked.length } : null;
}

/** كم صنفاً هو الأرخص فيه (بمقارنة حقيقية: عرضان فأكثر). مفتاح الخريطة: board_supplier. */
export function winsPerSupplier(
  itemIds: number[],
  prices: BoardPriceLike[],
): Map<number, number> {
  const wins = new Map<number, number>();
  for (const itemId of itemIds) {
    for (const supplierId of cheapestSupplierIds(offersForItem(prices, itemId))) {
      wins.set(supplierId, (wins.get(supplierId) ?? 0) + 1);
    }
  }
  return wins;
}

/** مفتاح مطابقة الأسماء: قصّ الأطراف وتجاهل حالة الأحرف. */
export function normalizeItemName(name: string): string {
  return name.trim().toLowerCase();
}

/**
 * لصق قائمة أصناف: سطر لكل صنف، وأول خليةٍ (قبل أول Tab) هي الاسم — فلصقُ
 * أعمدةٍ من Excel يأخذ العمود الأول. المكرَّر (في اللصقة نفسها أو ضد الموجود)
 * يُسقَط ويُعَدّ، فيُعرض للمستخدم «تم تجاهل N مكرّر».
 */
export function parsePastedItems(
  text: string,
  existingNames: string[],
): { names: string[]; duplicates: number } {
  const seen = new Set(existingNames.map(normalizeItemName));
  const names: string[] = [];
  let duplicates = 0;
  for (const line of text.split(/\r?\n/)) {
    const name = line.split("\t")[0].trim();
    if (!name) continue;
    const key = normalizeItemName(name);
    if (seen.has(key)) {
      duplicates += 1;
      continue;
    }
    seen.add(key);
    names.push(name);
  }
  return { names, duplicates };
}

export type CellInput =
  | { kind: "delete" }
  | { kind: "set"; price: string; note: string }
  | { kind: "invalid" };

const ARABIC_DIGITS: Record<string, string> = {
  "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
  "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
  "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
  "٫": ".",
};

/**
 * ما يكتبه المستخدم في الخلية: «السعر» أو «السعر, ملاحظة» (الفاصلة اللاتينية أو
 * العربية). فارغ = حذف السعر. الأرقام العربية تُقبل. السعر يبقى **نصّاً** كما
 * كُتب (بعد توحيد الأرقام) كي لا يُقصّ كسرٌ عشريٌّ في الذهاب والإياب.
 */
export function parseCellInput(raw: string): CellInput {
  const text = raw.trim();
  if (!text) return { kind: "delete" };
  // «1,180» فاصلة آلاف لا فاصل ملاحظة — وإلا حُفظ السعر 1 والملاحظة «180» بصمت.
  // وفاصلةٌ يليها رقمٌ مباشرة ولا تشكّل آلافاً سليمة («12,500 pcs») ملتبسة فتُرفض.
  const grouped = /^([0-9٠-٩۰-۹]{1,3}(?:,[0-9٠-٩۰-۹]{3})+(?:[.٫][0-9٠-٩۰-۹]*)?)(?:\s*[,،]\s*([\s\S]*))?$/.exec(text);
  if (!grouped && /^[0-9٠-٩۰-۹.٫]+[,،][0-9٠-٩۰-۹]/.test(text)) return { kind: "invalid" };
  const m = grouped ?? /^([0-9٠-٩۰-۹.٫]+)\s*(?:[,،]\s*([\s\S]*))?$/.exec(text);
  if (!m) return { kind: "invalid" };
  const price = m[1].replace(/,/g, "").replace(/[٠-٩۰-۹٫]/g, (c) => ARABIC_DIGITS[c]);
  if (!/^(?:\d+\.?\d*|\.\d+)$/.test(price)) return { kind: "invalid" };
  return { kind: "set", price: price.endsWith(".") ? price.slice(0, -1) : price, note: (m[2] ?? "").trim() };
}

/** روابط المرفقات تبدأ بـ http(s):// حصراً (لا javascript: ولا data:). */
export function isHttpUrl(value: string): boolean {
  return /^https?:\/\/\S+$/i.test(value.trim());
}

export interface SearchableItem { id: number; name: string }
export interface SearchableSupplier { id: number; supplier_name: string }

export interface BoardVisibility {
  visibleItemIds: Set<number>;
  /** موردون طابقهم البحث بالاسم. */
  supplierHits: Set<number>;
  /** أعمدة تُخفَّت: لا يطابقها البحث ولا فيها سعرٌ لصنفٍ مطابق. */
  dimSupplierIds: Set<number>;
  /** هل خلية (صنف، مورد) تُخفَّت؟ — مورّدٌ طابق البحث وهذه الخلية ليست منه ولا لصنفٍ مطابق. */
  isCellDim: (itemId: number, boardSupplierId: number) => boolean;
}

/**
 * البحث في الأصناف والموردين معاً + مرشّح «التي عليها عروض فقط».
 * صفّ يبقى إن طابق اسمُه، أو كان لمورّدٍ مطابقٍ سعرٌ فيه؛ والأعمدة غير ذات الصلة
 * تُخفَّت لا تُحذف (الجدول يحتفظ بشكله).
 */
export function searchBoard(
  items: SearchableItem[],
  suppliers: SearchableSupplier[],
  prices: BoardPriceLike[],
  query: string,
  onlyOffered: boolean,
): BoardVisibility {
  const q = query.trim().toLowerCase();
  const hasPrice = new Set(prices.map((p) => `${p.item}|${p.board_supplier}`));
  const offeredItems = new Set(prices.map((p) => p.item));
  const itemHits = new Set(
    q ? items.filter((i) => i.name.toLowerCase().includes(q)).map((i) => i.id) : [],
  );
  const supplierHits = new Set(
    q ? suppliers.filter((s) => s.supplier_name.toLowerCase().includes(q)).map((s) => s.id) : [],
  );
  const visibleItemIds = new Set<number>();
  for (const item of items) {
    const matchesQuery = !q
      || itemHits.has(item.id)
      || [...supplierHits].some((sid) => hasPrice.has(`${item.id}|${sid}`));
    if (matchesQuery && (!onlyOffered || offeredItems.has(item.id))) visibleItemIds.add(item.id);
  }
  const dimSupplierIds = new Set<number>();
  if (q) {
    for (const s of suppliers) {
      const relevant = supplierHits.has(s.id)
        || [...itemHits].some((iid) => hasPrice.has(`${iid}|${s.id}`));
      if (!relevant) dimSupplierIds.add(s.id);
    }
  }
  return {
    visibleItemIds,
    supplierHits,
    dimSupplierIds,
    isCellDim: (itemId, boardSupplierId) =>
      q !== "" && supplierHits.size > 0 && !supplierHits.has(boardSupplierId) && !itemHits.has(itemId),
  };
}
