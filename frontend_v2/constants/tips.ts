/**
 * THA-121 — نصوص «هل تعلم»: **ملفٌ واحد قابل للتحرير**، كما في `simpleHints.ts`.
 *
 * كل حرفٍ عربيّ يظهر في بطاقة التلميح يُكتب هنا ولا يُكتب في المكوّن
 * (`components/ui/DidYouKnow.tsx`) — فتحرير النصّ لاحقاً لا يمسّ شيفرةً ولا يفتح
 * باب انحدار.
 *
 * الشكل نفس شكل `SimpleHint` قصداً: عنوانٌ قصير + **سطران لا ثالث لهما**. سقفٌ
 * مقصود — التلميح جملةٌ تُقرأ في ثانيتين لا صفحةُ توثيق.
 *
 * **لا حقل صلاحية هنا.** أهلية التلميح ذي `targetView` تُشتقّ آلياً من
 * `utils/viewPermissions.ts` و`utils/uiMode.ts` (انظر `pickTip`) — نسخةٌ ثانية
 * يدوية من خريطة الصلاحيات كانت ستنحرف عن الأصل بصمت وتَعِد بشاشةٍ محجوبة.
 *
 * و`view`/`targetView` من نوع `AppView`: مفتاح شاشةٍ مخترَع **يكسر البناء** بدل
 * أن يمرّ تلميحاً يتيماً لا يظهر أبداً.
 */
import type { AppView } from '../types/common.ts';

export interface Tip {
  /** مفتاح ثابت — عليه يُحفظ الإخفاء وعدّاد الظهور. لا يُعاد استعماله بعد حذفه. */
  readonly key: string;
  /** الشاشة التي يظهر فيها التلميح — سياقُه، لا الرئيسية. */
  readonly view: AppView;
  /** عنوان البطاقة كما يقرأه المستخدم. */
  readonly title: string;
  /** سطران: ما هي الميزة · وماذا تكسب منها. */
  readonly lines: readonly [string, string];
  /** شاشةٌ يفتحها زرّ «افتحها» — وأهليةُ التلميح تُشتقّ من صلاحيتها ووحدتها. */
  readonly targetView?: AppView;
}

/**
 * عشرة تلميحات عن ميزات **قائمة فعلاً وقليلة الاستعمال** — كلٌّ منها مُثبَت من
 * الكود لا مخمَّن، والدليل مذكور فوقه. الترتيب هو ترتيب الترجيح عند التساوي.
 */
export const TIPS: readonly Tip[] = [
  // sales/services/flow.py (`collect_sales_invoice`) — الفائض غير الموزَّع يُقيَّد
  // «على الحساب»، واللوحة تقولها في SalesInvoiceEditor.tsx (لوحة التحصيل).
  {
    key: 'sales.collect-overflow',
    view: 'sales-invoices',
    title: 'حصّلت أكثر من قيمة الفاتورة؟ لا شيء يضيع',
    lines: [
      'الفائض عن المتبقّي يُقيَّد تلقائياً دفعةً على حساب الزبون.',
      'تخصمه من فاتورته التالية بدل أن تعيد إدخاله يدوياً.',
    ],
  },
  // components/accounting/InvoiceProfitsPage.tsx — يقرأ متوسط التكلفة الفعلي.
  {
    key: 'sales.invoice-profits',
    view: 'sales-invoices',
    title: 'اعرف ربح كل فاتورة لا مبيعاتها فقط',
    lines: [
      'تقرير «أرباح الفواتير» يطرح تكلفة ما بعته من قيمته.',
      'التكلفة من متوسط التكلفة الفعلي لا من سعر تكتبه بيدك.',
    ],
    targetView: 'invoice-profits',
  },
  // components/sales/ReservedStockReportPage.tsx
  {
    key: 'sales.reserved-stock',
    view: 'sales-orders',
    title: 'ما هو محجوز لطلبيّاتك ليس متاحاً للبيع',
    lines: [
      'تقرير «المخزون المحجوز» يُظهر كميات الطلبيات غير المسلَّمة.',
      'راجعه قبل أن تَعِد زبوناً آخر بصنفٍ محجوزٍ أصلاً.',
    ],
    targetView: 'reserved-stock',
  },
  // components/inventory/StocktakePage.tsx (صلاحية inventory.doc.post)
  {
    key: 'inventory.stocktake',
    view: 'stock-levels',
    title: 'الجرد الفعلي يوثّق الفرق بدل أن تُصلحه يدوياً',
    lines: [
      'أدخِل العدّ الفعلي فيقارنه النظام بالدفتري ويُظهر الفرق.',
      'التسوية تُسجَّل حركةَ مخزون موثَّقة — لا رقماً يُكتب فوق رقم.',
    ],
    targetView: 'stocktake',
  },
  // components/ui/FileDropZone.tsx (usePasteZone) داخل components/items/ItemForm.tsx
  {
    key: 'inventory.paste-image',
    view: 'items-management',
    title: 'صورة الصنف تُلصق بـ Ctrl+V',
    lines: [
      'انسخ الصورة من أي مكان وألصقها داخل بطاقة الصنف مباشرةً.',
      'تنزل في أول خانة صورةٍ فارغة بلا حفظ ملفٍ ولا تصفّح.',
    ],
  },
  // store/views.py (قراءة عامة بـ store_slug) · شاشة store-settings (store.manage)
  {
    key: 'store.public-link',
    view: 'items-management',
    title: 'لأصنافك متجرٌ عام برابطٍ واحد',
    lines: [
      'اختر رابط متجرك وحدّد ما يُنشر فيه من «متجري».',
      'الزبون يتصفّحه ويطلب منه بلا حسابٍ ولا تسجيل دخول.',
    ],
    targetView: 'store-settings',
  },
  // components/shared/DocumentPaymentPanel.tsx ← InvoiceForm.tsx
  {
    key: 'purchase.settle-on-account',
    view: 'purchase-invoices',
    title: 'سدّد للمورّد من دفعاته المقدّمة',
    lines: [
      'من لوحة الدفع داخل الفاتورة: «من رصيد المورّد (سلف)».',
      'الربط بلا قيدٍ جديد — الرصيد ينزل والفاتورة تُقفل.',
    ],
  },
  // accounting/services.py (`INCOMING_TRANSITIONS` / `OUTGOING_TRANSITIONS`)
  {
    key: 'accounting.cheque-lifecycle',
    view: 'accounting-cheques',
    title: 'الشيك دورةُ حياةٍ محروسة',
    lines: [
      'مسودّة ← تحت التحصيل ← محصَّل، والارتداد والإرجاع لهما مساراهما.',
      'النظام يمنع الانتقال غير المنطقي ويقول لك المسموح من هنا.',
    ],
  },
  // components/accounting/BankReconciliationPage.tsx
  {
    key: 'accounting.bank-reconciliation',
    view: 'accounting-journals',
    title: 'طابِق البنك قبل أن تتراكم الفروقات',
    lines: [
      'المطابقة البنكية تقابل كشف البنك بحركاتك وتكشف ما لم يُسجَّل.',
      'شهرٌ بلا مطابقة يعني فرقاً تبحث عنه في اثني عشر شهراً.',
    ],
    targetView: 'accounting-bank-reconciliation',
  },
  // components/SmartAssistantPage.tsx · مسار /assistant في App.tsx (VIEW_PATHS)
  {
    key: 'core.smart-assistant',
    view: 'dashboard',
    title: 'اسأل عن أرقام شركتك بالعربية',
    lines: [
      'المساعد الذكي يجيب عن مبيعاتك وأرصدتك ومتأخّراتك بسؤالٍ عادي.',
      'أسرع من فتح تقريرٍ حين تريد رقماً واحداً فقط.',
    ],
    targetView: 'smart-assistant',
  },
];
