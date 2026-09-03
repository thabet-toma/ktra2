/**
 * ISSUE #113 — حكمٌ يلزمه انتباه: `core/pricing.py` (`purchase_price_list`)
 * يُرجع «آخر شراء» **بعملة الفاتورة المصدر كما سُجّلت** و«أقل شراء» (ISSUE #111)
 * **بالعملة الأساسية دائماً**، مُحوَّلاً بسعر صرف فاتورته هو. عرضُ الرقمين
 * جنباً إلى جنب بلا تمييز يجعل مستخدماً يشتري بالدولار يرى «آخر شراء ١٢» بجانب
 * «أقل شراء ٤٣٫٢٠» ويحكم أن الأقل معطوب — وهذا بالضبط صنف العطب الذي خرجت
 * هذه المواصفة لقتله (#108 §٣). الحلّ هنا: تسمية صريحة لرقاقة «أقل شراء»
 * تقول إنها بالعملة الأساسية، لا رقماً عارياً بجانب رقمٍ بعملة أخرى.
 *
 * دالّة نقيّة تُستهلَك من منتقي فاتورة الشراء (`InvoiceForm.tsx`) ومن منتقي
 * بند الطلبية الجديد (`PurchaseRFQForm.tsx`) — مصدرٌ واحد لبناء الرقاقة بدل
 * نسخةٍ في كل شاشة.
 */

import { formatMoney } from './formatNumber.ts';

/** شكل عنصر واحد من `prices[]` في ردّ `purchase_price_list` (`purchaseInvoiceApi.priceList`). */
export interface PurchasePriceListEntry {
  label?: string;
  source_label?: string;
  unit_price: string | number;
  source_type?: string;
  document_id?: number | null;
  document_number?: string | null;
  document_date?: string | null;
  supplier_id?: number | null;
  supplier_name?: string | null;
}

export interface PurchasePriceHintChip {
  /** التسمية كاملة — تحمل علامة العملة الأساسية صراحةً حين يلزم (لا رقماً غامضاً). */
  label: string;
  /** القيمة مهيّأةً بـ`formatMoney` — لا `toFixed` أبداً. */
  value: string;
  /** المورد الذي بيعت به هذه القيمة (يظهر فقط لِـ«أقل شراء» — الحقل موجود له وحده). */
  supplierName: string | null;
  /** تاريخ المستند المصدر. */
  documentDate: string | null;
  documentNumber: string | null;
  documentId: number | null;
  link: string | null;
  /** بالعملة الأساسية لا بعملة السطر — العلامة التي تمنع الالتباس. */
  isBaseCurrency: boolean;
}

/** «أقل شراء» — النوع الوحيد الذي يُحوَّل دائماً إلى العملة الأساسية (core/pricing.py). */
const LOWEST_PURCHASE_PREFIX = 'أقل شراء';

const isLowestPurchaseEntry = (entry: PurchasePriceListEntry): boolean => {
  const label = entry.source_label || entry.label || '';
  return label.startsWith(LOWEST_PURCHASE_PREFIX);
};

/**
 * يبني رقاقة عرضٍ واحدة من عنصر خام — يضيف «(بالعملة الأساسية)» على تسمية
 * «أقل شراء» تحديداً كي لا يُقرأ رقمها كأنه بعملة السطر نفسها. لا يفترض عملة
 * بعينها (الدولار/الشيكل) لأنها تختلف بين الشركات — تسميةٌ لا رمز.
 */
export function buildPurchasePriceHintChip(
  entry: PurchasePriceListEntry,
  options: { invoiceLink?: (documentId: number) => string } = {},
): PurchasePriceHintChip {
  const rawLabel = entry.source_label || entry.label || '';
  const baseCurrency = isLowestPurchaseEntry(entry);
  const label = baseCurrency && !rawLabel.includes('بالعملة الأساسية')
    ? `${rawLabel} (بالعملة الأساسية)`
    : rawLabel;
  const documentId = entry.document_id ?? null;
  return {
    label,
    value: formatMoney(Number(entry.unit_price)),
    supplierName: baseCurrency ? (entry.supplier_name ?? null) : null,
    documentDate: entry.document_date ?? null,
    documentNumber: entry.document_number ?? null,
    documentId,
    link: documentId && options.invoiceLink ? options.invoiceLink(documentId) : null,
    isBaseCurrency: baseCurrency,
  };
}

/** يبني كل الرقاقات (آخر شراء + أقل شراء) لمنتج واحد دفعة واحدة. */
export function buildPurchasePriceHintChips(
  entries: PurchasePriceListEntry[] | undefined | null,
  options: { invoiceLink?: (documentId: number) => string } = {},
): PurchasePriceHintChip[] {
  return (entries || []).map((entry) => buildPurchasePriceHintChip(entry, options));
}

/**
 * الفارق المئوي بين سعر المورد (في العرض) وأقلّ سعرٍ مسجَّل — موجبٌ يعني
 * المورد أغلى من الأقلّ، سالبٌ أو صفر يعني هو الأقلّ فعلاً أو أرخص منه.
 * `null` بلا أساس مقارنة (أقلّ سعر غائب أو صفر أو سعر المورد غير صالح) —
 * مقارنةٌ مُختلَقة أسوأ من لا مقارنة (مواصفة #108 §٨: «بندٌ بلا تقديري ←
 * يُعرَض سعر المورد عارياً: لا نسبة ولا لون»؛ القاعدة نفسها تسري هنا على
 * غياب «أقل سعر»).
 */
export function computeDeltaPercent(
  unitPrice: number,
  lowestValue: number | null | undefined,
): number | null {
  if (lowestValue == null || !Number.isFinite(lowestValue) || lowestValue <= 0) return null;
  if (!Number.isFinite(unitPrice)) return null;
  return ((unitPrice - lowestValue) / lowestValue) * 100;
}

/**
 * نصّ إشارة مختصر لعرضها بجانب بند الطلبية أو في منتقي الأصناف — «أقل شراء
 * ٤٣٫٢٠ (بالعملة الأساسية) — شركة الأمل، ٢٠٢٦-٠٨-٠١» (issue #113 §الشاشة:
 * «أقل سعر... مع المورد والتاريخ»). يعيد `null` حين لا «أقل شراء» في الردّ
 * أصلاً — لا نصّ فارغ يُرسم بلا معنى.
 */
export function formatLowestPurchaseHint(
  entries: PurchasePriceListEntry[] | undefined | null,
): string | null {
  const lowest = (entries || []).find(isLowestPurchaseEntry);
  if (!lowest) return null;
  const chip = buildPurchasePriceHintChip(lowest);
  const parts = [`${chip.label}: ${chip.value}`];
  if (chip.supplierName) parts.push(chip.supplierName);
  if (chip.documentDate) parts.push(chip.documentDate);
  return parts.join(' — ');
}
