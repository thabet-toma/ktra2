/**
 * T-SCAN — «ما الذي في يدي؟»: نداءٌ واحد لكل ما يُمسح أو يُكتب.
 *
 * العقد كلّه في `core/scan.py` (`resolve_scan`): نصٌّ واحد يدخل، وقائمةٌ واحدة
 * موسومةٌ بالنوع تخرج مرتّبةً من الأخصّ إلى الأعمّ. الواجهة **لا تستنتج** نوع
 * الرقم ولا تختار المصدر — الخادم فعل ذلك، وتكرارُ القاعدة هنا كان سيعني
 * نسختين من Luhn وخانةِ تحقّق EAN تتباعدان مع أول تعديل.
 *
 * ولا تُصفّي الواجهة بالصلاحيات كذلك: `scope` يصل محسوباً من الخادم فتُرسم به
 * الأزرار، فلا زرٌّ يقود إلى 403.
 */
import { apiGetObject } from "./restApi";

/** ما استنتجه الخادم من **شكل** النصّ — لافتةٌ للعرض لا مصفاةٌ للبحث. */
export type ScanKind = "imei" | "barcode" | "text";

export interface ScanWarrantyCard {
  id: number;
  serial: string;
  device_name: string;
  start_date: string | null;
  end_date: string | null;
  duration_months: number | null;
  status: "active" | "expired" | string;
  days_remaining: number | null;
  customer_name: string;
  supplier_warranty_end_date: string | null;
  supplier_warranty_active: boolean;
}

export interface ScanServiceOrder {
  id: number;
  order_number: string;
  order_date: string | null;
  status: string;
  status_display: string;
  complaint: string;
}

/** بطاقة القطعة — رحلتها كاملة: من أين جاءت، بكم، لمن ذهبت، وما يغطّيها. */
export interface ScanUnitMatch {
  type: "unit";
  id: number;
  serial: string;
  status: "in_stock" | "sold" | string;
  status_display: string;
  product: number | null;
  product_name: string;
  product_sku: string;
  purchase_invoice: number | null;
  purchase_invoice_number: string | null;
  supplier_name: string | null;
  purchase_unit_price: string | null;
  purchase_date: string | null;
  sales_invoice: number | null;
  sales_invoice_number: string | null;
  customer: number | null;
  customer_name: string | null;
  customer_phone: string | null;
  sold_at: string | null;
  created_at: string | null;
  /** `null` حين لا تكون وحدة «ما بعد البيع» مرخَّصةً أو مصرّحاً بها. */
  warranty: {
    covered: boolean;
    supplier_covered: boolean;
    cards: ScanWarrantyCard[];
  } | null;
  service_orders: ScanServiceOrder[];
}

export interface ScanDeviceMatch {
  type: "device";
  id: number;
  model_name: string;
  serial_number: string;
  imei: string;
  status: string;
  status_display: string;
  customer_name: string;
  customer_phone: string;
  registered_at: string | null;
}

export interface ScanProductMatch {
  type: "product";
  id: number;
  sku: string;
  barcode: string;
  name: string;
  brand: string;
  quantity_on_hand: string;
  sale_price: string;
  is_serialized: boolean;
  /** لماذا طابق: `barcode` · `sku` يقين، و`partial` ترجيح. */
  matched_on: "barcode" | "sku" | "partial";
}

export type ScanMatch = ScanUnitMatch | ScanDeviceMatch | ScanProductMatch;

export interface ScanScope {
  units: boolean;
  products: boolean;
  devices: boolean;
  warranty: boolean;
  orders: boolean;
}

export interface ScanResult {
  term: string;
  kind: ScanKind;
  matches: ScanMatch[];
  /** بحثنا في كل ما يحقّ لك وما وجدنا. النصّ الفارغ ليس رقماً مجهولاً. */
  unregistered: boolean;
  scope: ScanScope;
}

export const scanApi = {
  lookup(term: string, opts?: { tenantId?: number }): Promise<ScanResult> {
    return apiGetObject<ScanResult>("scan/", {
      tenantId: opts?.tenantId,
      query: { q: term },
    });
  },
};

export default scanApi;
