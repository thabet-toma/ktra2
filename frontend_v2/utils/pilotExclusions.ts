/**
 * أسماءُ استبعادات محاور الـpilot بالعربيّة — **مصدرٌ واحد** لجدول المحاور
 * (`PilotAxesTable`) ولقائمة تصنيف الردّ (`WorkOrdersPanel`).
 *
 * يُرجع الخادمُ في `axes[محور].exclusions` رموزاً ثابتة
 * (`platform_ops/services.py`، `calculate_employee_pilot_performance`)، وكان
 * الجدولُ يطبعها كما هي: «onboarding، waiting_customer، transferred_before_due».
 * والرموزُ من ثلاث مفرداتٍ خادميّة لا واحدة، فالأسماءُ منقولةٌ من تسمياتها هناك:
 *
 * * `onboarding` ⟵ `Engagement.Kind.ONBOARDING`.
 * * `waiting_customer` ⟵ `WorkOrder.Status.WAITING_CUSTOMER`.
 * * `customer_new_info` و`other` ⟵ `WorkOrderDeliverable.RejectionCategory`.
 * * `transferred_before_due` بلا choices خادميّة — اسمُه من شرح الدالّة نفسِها
 *   («العمل الذي نُقل قبل الاستحقاق»).
 *
 * `platform_ops/tests/test_pilot_exclusion_labels.py` يسقط إن أرسل الخادمُ رمزاً
 * بلا اسمٍ هنا، أو افترق اسمٌ عن تسمية choices خادمه.
 */
export const REJECTION_CATEGORY_LABELS = {
  employee_error: 'خطأ الموظف',
  customer_new_info: 'معلومات جديدة من العميل',
  other: 'أخرى',
} as const;

export const PILOT_EXCLUSION_LABELS: Record<string, string> = {
  onboarding: 'تهيئة مؤقتة',
  waiting_customer: 'بانتظار العميل',
  transferred_before_due: 'نُقل قبل الاستحقاق',
  customer_new_info: REJECTION_CATEGORY_LABELS.customer_new_info,
  other: REJECTION_CATEGORY_LABELS.other,
};

/**
 * اسمُ الاستبعاد؛ والرمزُ المجهولُ يُعرَض كما هو — لا خانةَ فارغة. والفحصُ بالمفاتيح
 * الخاصّة لا بالقراءة: `toString` وأخواتُها موروثةٌ فتُرجع دالّةً بدل الرمز.
 */
export const pilotExclusionLabel = (code: string): string =>
  Object.prototype.hasOwnProperty.call(PILOT_EXCLUSION_LABELS, code) ? PILOT_EXCLUSION_LABELS[code] : code;
