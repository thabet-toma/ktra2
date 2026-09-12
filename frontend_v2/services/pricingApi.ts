/**
 * عميل نقطة الأسعار العامّة — `/api/pricing/plans/` بلا مصادقة وبلا شركة
 * (`core/public_pricing.py`). شكلُ الحمولة هنا حرفيّاً كما يصدره الخادم؛ لا حقل
 * يُضاف هنا لم يصدره — الصفحاتُ الثلاث التي تقرأ هذه الأنواع تعتمد عليها.
 */
import { apiGetObject } from './restApi';

export interface PublicPlanLimit {
  key: string;
  label: string;
  unit: string;
  period: string;
  period_label: string;
  /** عددٌ = الحدّ · `null` = بلا حدّ · `0` = غير متاح. */
  value: number | null;
}

export interface PublicPlanModule {
  key: string;
  label: string;
}

export interface PublicPlan {
  key: string;
  label: string;
  price: number;
  currency: string;
  currency_symbol: string;
  limits: PublicPlanLimit[];
  modules: PublicPlanModule[];
}

export interface DataEntryAddon {
  key: string;
  label: string;
  price: number;
  included_operations: number;
  /** لم يُحسم سعر العملية الزائدة بعد — `null` يعني إخفاء السطر لا طباعة صفر. */
  extra_operation_price: number | null;
}

export interface PublicPricingResponse {
  currency: string;
  plans: PublicPlan[];
  data_entry_addon: DataEntryAddon;
}

export async function fetchPublicPricing(): Promise<PublicPricingResponse> {
  return apiGetObject<PublicPricingResponse>('pricing/plans/');
}
