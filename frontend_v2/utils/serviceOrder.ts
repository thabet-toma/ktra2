/**
 * THA-24 م4 — قواعد أمر الصيانة الصرفة (بلا React وبلا شبكة).
 *
 * مرآة `after_sales/service_orders.py`: المسار الخطّي واحد، والحالتان النهائيتان
 * مجمَّدتان. ما هنا **عرضٌ** لقرار الخادم لا قرارٌ ثانٍ ينافسه — أسباب منع
 * التسليم والإلغاء تأتي محسوبةً منه (`delivery_blockers`) وتُعرض كما هي، فلا
 * تختلف رسالة الشاشة عن سبب الرفض الفعلي.
 */
// الامتداد صريح: `node --test` يشغّل هذا الملف مباشرةً ولا يحلّ الاستيراد بدونه.
import type {
  PartBilling,
  ServiceOrderOutcome,
  ServiceOrderStatus,
} from "../services/afterSalesApi.ts";

/** المسار الخطّي — التقدّم والرجوع داخله مسموحان، وطرفاه وحدهما محروسان. */
export const SERVICE_FLOW: ServiceOrderStatus[] = [
  "received",
  "in_diagnosis",
  "awaiting_approval",
  "in_repair",
  "ready",
];

export const SERVICE_STATUS_LABELS: Record<ServiceOrderStatus, string> = {
  received: "مُستلَم",
  in_diagnosis: "قيد التشخيص",
  awaiting_approval: "بانتظار الموافقة",
  in_repair: "قيد الإصلاح",
  ready: "جاهز للتسليم",
  delivered: "تم التسليم",
  cancelled: "ملغى",
};

export const SERVICE_OUTCOME_LABELS: Record<Exclude<ServiceOrderOutcome, "">, string> = {
  repaired: "تم الإصلاح",
  unrepaired: "تعذّر الإصلاح",
  rejected_estimate: "رفض الزبون التقدير",
  no_fault: "لا عطل",
};

export const PART_BILLING_LABELS: Record<PartBilling, string> = {
  billable: "مفوترة على الزبون",
  covered: "مغطاة بالكفالة",
};

/** الحالتان النهائيتان: لا تعديل ولا نقل ولا حذف قطع بعدهما. */
export const isTerminalStatus = (status: ServiceOrderStatus): boolean =>
  status === "delivered" || status === "cancelled";

/** الخطوة التالية على المسار، أو `null` عند طرفه. */
export const nextServiceStatus = (
  status: ServiceOrderStatus,
): ServiceOrderStatus | null => {
  const index = SERVICE_FLOW.indexOf(status);
  if (index < 0) return null;
  return index + 1 < SERVICE_FLOW.length ? SERVICE_FLOW[index + 1] : "delivered";
};

/** الخطوة السابقة — الرجوع خطوة حين يظهر عطل ثانٍ بعد «جاهز». */
export const previousServiceStatus = (
  status: ServiceOrderStatus,
): ServiceOrderStatus | null => {
  const index = SERVICE_FLOW.indexOf(status);
  return index > 0 ? SERVICE_FLOW[index - 1] : null;
};

/**
 * لون شارة الحالة. «جاهز للتسليم» أخضر لأنه مكسب، و«ملغى» رمادي لا أحمر:
 * الإلغاء قرار مشروع لا عطل.
 */
export const serviceStatusPillClass = (status: ServiceOrderStatus): string => {
  const tone =
    status === "delivered"
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
      : status === "cancelled"
        ? "bg-[var(--color-surface-2)] text-[var(--color-text-muted)]"
        : status === "ready"
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
          : status === "awaiting_approval"
            ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
            : "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300";
  return `inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${tone}`;
};

/** شارة القطعة: المغطاة بالكفالة تُقرأ فوراً كمصروفٍ علينا لا إيرادٍ لنا. */
export const partBillingPillClass = (billing: PartBilling): string => {
  const tone =
    billing === "covered"
      ? "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300"
      : "bg-[var(--color-surface-2)] text-[var(--color-text)]";
  return `inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${tone}`;
};

/**
 * مجموع القطع لكل مسار — للعرض وحده. الأرقام التي تدخل الدفاتر يحسبها الخادم:
 * المغطاة بتكلفة WAC التاريخية (لا بسعر البيع)، والمفوترة عبر الفاتورة.
 */
export function sumParts(
  parts: { quantity: string; unit_price: string; billing: PartBilling }[],
  billing: PartBilling,
): number {
  return parts
    .filter((p) => p.billing === billing)
    .reduce(
      (total, p) => total + (Number(p.quantity) || 0) * (Number(p.unit_price) || 0),
      0,
    );
}
