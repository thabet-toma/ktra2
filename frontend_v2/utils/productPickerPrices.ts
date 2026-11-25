/**
 * PICKER-COMPACT: دالّتان نقيتان لاختيار الأسعار المعروضة في السطر الثاني من
 * قائمة بحث المنتج في فاتورتَي البيع والشراء — عرضٌ فقط دون تغيير تسعير البند.
 *
 * - البيع (`pickSalesPickerPrices`): يُبقي «أقل شراء (آخر ٥)» (عند فتح زرّ العين
 *   فقط) و«آخر» (آخر بيع لهذا العميل بعينه بفلترة `kind === 'last'`، وإلا «آخر —»).
 *   لا فلترة على النص العربي أو ترتيب القائمة.
 * - الشراء (`pickPurchasePickerPrices`): يُبقي «آخر شراء» من مورد الفاتورة فقط
 *   بفلترة `kind === 'last'`، وإلا «آخر —».
 */

import { formatMoney } from './formatNumber.ts';
import {
  buildPurchasePriceHintChip,
  type PurchasePriceListEntry,
} from './purchasePriceHint.ts';

// تعكس الاتحادَين في `services/salesApi.ts` (`CustomerPriceRow`) و`services/purchaseInvoiceApi.ts` (`priceList`) وتبقى محلّية كي لا تستورد أدوات `node --test` خدمات.
export type CustomerPriceKind = 'last' | 'lowest' | 'quote' | 'card';
export type PurchasePriceKind = 'last' | 'lowest' | 'avg_cost';

export interface CustomerPriceEntry {
  kind?: CustomerPriceKind;
  label?: string;
  unit_price: string | number;
  source_type?: string;
  document_id?: number | null;
  invoice_number?: string | null;
}

export type PurchasePickerEntry = PurchasePriceListEntry & {
  kind?: PurchasePriceKind;
};

export interface PickerPriceChip {
  label: string;
  value: string;
  link?: string;
  isEmpty?: boolean;
}

export interface SalesPickerPricesResult {
  lowestPurchase?: PickerPriceChip;
  last: PickerPriceChip;
}

const INDICATIVE_PURCHASE_LABEL = 'أقل شراء (آخر ٥)';

/**
 * يختار لائحة أسعار خيار المنتج في فاتورة المبيعات:
 * - يفلتر على `kind === 'last'` فقط (يُسقط `card`/`lowest`/`quote`).
 * - عند غياب فاتورة سابقة للعميل يعيد `{ label: 'آخر', value: '—', isEmpty: true }`.
 * - عندما يكون زرّ العين مغلقاً (`eyeOpen=false`) لا يُرجع `lowestPurchase` أصلاً.
 * - تسمية «أقل شراء» من الخادم (`indicative_purchase_price_source`، تحمل حجم النافذة)،
 *   والثابت المحلي احتياطٌ عند غيابها فقط.
 */
export function pickSalesPickerPrices(
  prices: CustomerPriceEntry[] | null | undefined,
  indicativePurchasePrice: string | number | null | undefined,
  eyeOpen: boolean,
  indicativePurchaseLabel?: string | null,
): SalesPickerPricesResult {
  const lastEntry = (prices || []).find((pr) => pr.kind === 'last');
  const hasValue =
    lastEntry != null &&
    lastEntry.unit_price !== null &&
    lastEntry.unit_price !== undefined &&
    lastEntry.unit_price !== '' &&
    Number.isFinite(Number(lastEntry.unit_price));

  const last: PickerPriceChip = hasValue
    ? {
        label: 'آخر',
        value: formatMoney(Number(lastEntry.unit_price)),
        ...(lastEntry.document_id ? { link: `/sales/invoices/${lastEntry.document_id}` } : {}),
        isEmpty: false,
      }
    : {
        label: 'آخر',
        value: '—',
        isEmpty: true,
      };

  const result: SalesPickerPricesResult = { last };
  if (eyeOpen) {
    const hasIndicative =
      indicativePurchasePrice != null &&
      indicativePurchasePrice !== '' &&
      Number.isFinite(Number(indicativePurchasePrice));
    result.lowestPurchase = {
      label: indicativePurchaseLabel || INDICATIVE_PURCHASE_LABEL,
      value: hasIndicative ? formatMoney(Number(indicativePurchasePrice)) : '—',
    };
  }
  return result;
}

/**
 * يختار شارة «آخر شراء» وحدها لخيار المنتج في فاتورة الشراء من مورد الفاتورة
 * عبر `kind === 'last'` فقط. يُسقط `lowest` و`avg_cost`، ويعيد «آخر —» عند
 * غياب المورد أو غياب شراء سابق من هذا المورد.
 */
export function pickPurchasePickerPrices(
  entries: PurchasePickerEntry[] | null | undefined,
  hasSupplier: boolean,
  options: { invoiceLink?: (documentId: number) => string } = {},
): PickerPriceChip {
  if (!hasSupplier) {
    return { label: 'آخر', value: '—', isEmpty: true };
  }
  const lastEntry = (entries || []).find((entry) => entry.kind === 'last');
  if (!lastEntry) {
    return { label: 'آخر', value: '—', isEmpty: true };
  }
  const chip = buildPurchasePriceHintChip(lastEntry, options);
  return {
    label: 'آخر شراء',
    value: chip.value,
    ...(chip.link ? { link: chip.link } : {}),
    isEmpty: false,
  };
}
