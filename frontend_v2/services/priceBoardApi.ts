/**
 * جداول أسعار الاستيراد (PB-2) — `/api/logistics/price-boards/`.
 *
 * ملفٌّ مستقلّ عن `procurementDocumentsApi.ts` عمداً: الجدول مورد قائم بذاته
 * (أصناف × موردون × أسعار) لا علاقة له بعروض المورد ولا الطلبيات، وملف المستندات
 * فوق السبعمئة سطر من DTOs مستندات أخرى. النمط نفسه: `BASE` + `tenantId()`.
 *
 * الأعداد العشرية تصل نصوصاً — لا تُحوَّل إلى رقم هنا؛ التحويل للعرض والمقارنة
 * عند `utils/priceBoard` و`utils/formatNumber`.
 */
import {
  apiDelete,
  apiGetList,
  apiGetObject,
  apiPatchObject,
  apiPostObject,
} from "./restApi";
import { resolveTenantId } from "../utils/tenantContext";

const BASE = "logistics";
const tenantId = () => resolveTenantId();

export interface PriceBoardAttachment {
  name: string;
  url: string;
  type?: string;
  size?: number;
}

export interface PriceBoardSummaryDto {
  id: number;
  title: string;
  notes: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  items_count: number;
  suppliers_count: number;
  prices_count: number;
}

export interface PriceBoardItemDto {
  id: number;
  seq: number;
  name: string;
  /** null = نصٌّ حرٌّ لا منتج في النظام. */
  product: number | null;
  product_name?: string | null;
  unit_of_measure: string;
  quantity: string | null;
  note: string;
}

export interface PriceBoardSupplierDto {
  id: number;
  seq: number;
  supplier_name: string;
  /** null = اسمٌ حرٌّ لمورّد غير مسجَّل. */
  supplier: number | null;
  currency: number;
  currency_code: string;
  exchange_rate: string;
  offer_date: string | null;
  terms: string;
  attachments: PriceBoardAttachment[];
}

export interface PriceBoardPriceDto {
  id: number;
  item: number;
  board_supplier: number;
  unit_price: string;
  /** السعر بعملة الأساس بعد التحويل — عليه وحده تقوم المقارنة. */
  unit_price_base: string;
  note: string;
}

export interface PriceBoardDetailDto extends Omit<PriceBoardSummaryDto, "items_count" | "suppliers_count" | "prices_count"> {
  base_currency_code: string;
  items: PriceBoardItemDto[];
  suppliers: PriceBoardSupplierDto[];
  prices: PriceBoardPriceDto[];
}

export interface PriceBoardItemWrite {
  name: string;
  product?: number | null;
  unit_of_measure?: string;
  quantity?: string | null;
  note?: string;
}

export interface PriceBoardSupplierWrite {
  supplier_name: string;
  supplier?: number | null;
  currency: number;
  exchange_rate?: string;
  offer_date?: string | null;
  terms?: string;
  attachments?: PriceBoardAttachment[];
}

export type PriceBoardCellResult = PriceBoardPriceDto | { deleted: true };

export interface BoardCurrency {
  CurrencyID: number;
  Code: string;
  Name?: string | null;
}

const boardPath = (boardId: number, tail = "") => `${BASE}/price-boards/${boardId}/${tail}`;

export function listPriceBoards(archived: boolean): Promise<PriceBoardSummaryDto[]> {
  return apiGetList(`${BASE}/price-boards/`, {
    tenantId: tenantId(),
    query: { archived: archived ? 1 : 0 },
  });
}

export function createPriceBoard(body: { title: string; notes: string }): Promise<PriceBoardSummaryDto> {
  return apiPostObject(`${BASE}/price-boards/`, body, { tenantId: tenantId() });
}

export function updatePriceBoard(
  id: number,
  body: Partial<{ title: string; notes: string; is_archived: boolean }>,
): Promise<PriceBoardSummaryDto> {
  return apiPatchObject(boardPath(id), body, { tenantId: tenantId() });
}

export function getPriceBoard(id: number): Promise<PriceBoardDetailDto> {
  return apiGetObject(boardPath(id), { tenantId: tenantId() });
}

export function addPriceBoardItems(
  boardId: number,
  items: PriceBoardItemWrite[],
): Promise<{ created: PriceBoardItemDto[]; skipped_duplicates: number }> {
  return apiPostObject(boardPath(boardId, "items/"), { items }, { tenantId: tenantId() });
}

export function updatePriceBoardItem(
  boardId: number,
  itemId: number,
  body: Partial<PriceBoardItemWrite>,
): Promise<PriceBoardItemDto> {
  return apiPatchObject(boardPath(boardId, `items/${itemId}/`), body, { tenantId: tenantId() });
}

export function deletePriceBoardItem(boardId: number, itemId: number): Promise<void> {
  return apiDelete(boardPath(boardId, `items/${itemId}/`), { tenantId: tenantId() });
}

/**
 * 400 بلا سعر صرف للعملة يصل خطأً على الحقل: `err.fieldErrors.exchange_rate` —
 * الشاشة تعرضه وتكشف خانة السعر اليدوي ثم تعيد الإرسال.
 */
export function addPriceBoardSupplier(
  boardId: number,
  body: PriceBoardSupplierWrite,
): Promise<PriceBoardSupplierDto> {
  return apiPostObject(boardPath(boardId, "suppliers/"), body, { tenantId: tenantId() });
}

export function updatePriceBoardSupplier(
  boardId: number,
  supplierId: number,
  body: Partial<PriceBoardSupplierWrite>,
): Promise<PriceBoardSupplierDto> {
  return apiPatchObject(boardPath(boardId, `suppliers/${supplierId}/`), body, { tenantId: tenantId() });
}

/** قد يردّ الخادم `{deleted_prices}`، لكنّ `apiDelete` لا يقرأ الجسم — الشاشة تعدّ الأسعار محلياً قبل الحذف. */
export function deletePriceBoardSupplier(boardId: number, supplierId: number): Promise<void> {
  return apiDelete(boardPath(boardId, `suppliers/${supplierId}/`), { tenantId: tenantId() });
}

/** `unit_price: null` يحذف السعر. */
export function setPriceBoardCell(
  boardId: number,
  body: { item: number; board_supplier: number; unit_price: string | null; note?: string },
): Promise<PriceBoardCellResult> {
  return apiPostObject(boardPath(boardId, "set-cell/"), body, { tenantId: tenantId() });
}

let currencyCache: Promise<BoardCurrency[]> | null = null;

/**
 * العملات المعرَّفة في الشركة — المصدر نفسه الذي يحوّل به `PriceOfferForm` رمز
 * العملة إلى معرّفها (`tenants/currencies/`). تُخزَّن الوعدة لا النتيجة فلا يُطلب
 * مرتين معاً، وتُترك عند الفشل كي لا يُثبَّت الخطأ.
 */
export function listBoardCurrencies(): Promise<BoardCurrency[]> {
  if (!currencyCache) {
    currencyCache = apiGetList<BoardCurrency>("tenants/currencies/", { tenantId: tenantId() })
      .catch((cause) => {
        currencyCache = null;
        throw cause;
      });
  }
  return currencyCache;
}
