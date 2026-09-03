/**
 * ISSUE #113 (مواصفة #108 §٤) — مصفوفة أعمدة «العروض والطلبيات»: الوصلة
 * الجديدة الوحيدة في هذه المواصفة. دالّةٌ نقيّة تأخذ نوع المستند (طلبية/عرض)
 * وتُعيد أعمدته — **تقرأ منها الشاشة والطباعة وExcel معاً**، لا ثلاث قوائم
 * تتباعد بمرور الوقت.
 *
 * **ثلاث مجموعات لا مجموعتان**: ما يُعرَض (`screen`) · وما يُطبَع (`print`) ·
 * وما يخرج إلى المورد (`supplier`) — والثالثة فرعيّة من الثانية. كلتاهما
 * **قائمة سماح لا قائمة منع** (`PRINT_ALLOWED_KEYS`/`SUPPLIER_ALLOWED_KEYS`):
 * عمودٌ جديد يُضاف غداً إلى `SCREEN_COLUMN_KEYS` لا يخرج تلقائياً — يلزمه
 * إدراجٌ صريح في القائمتين. هذا يحمي «السعر التقديري» (داخليٌّ بحت، صار حقلاً
 * مخزَّناً على `PurchaseRFQLine.estimated_price` بقرار المالك 2026-09-03،
 * فالحماية استبعادٌ نشط لا غياباً بنيوياً) و«أقل سعر» — لا يدخلان بانيَ
 * حمولة المورد أو الطباعة أصلاً.
 *
 * **كود HS غائبٌ عن المصفوفة كلّها** (قرار المالك 2026-09-03) — لا يُسأل عنه
 * مورّدٌ يُسعّر، محلّياً واستيراداً على السواء. وبخروجه **يسقط بُعد النطاق من
 * المصفوفة كلّها**: كان العمود الوحيد الذي يتغيّر بالنطاق. `scope` يبقى
 * بارامتراً اختيارياً في التوقيع (توافقاً مع مواصفة #108 §«الوصلات»: «دالّة
 * تأخذ نوعاً ونطاقاً») لكنه **لا يغيّر الأعمدة بتاتاً** — النطاق حقيقةٌ خامّة
 * تخصّ الصفقة والتخليص، لا الشاشة. ولا حذف بيانات: حقل HS يبقى على النماذج
 * التي تحمله (`SupplierQuotationLine`)، العرض وحده يتغيّر. ولا إعداد لكل
 * شركة يتحكّم بالأعمدة — رفضٌ صريح (تعقيدٌ بلا مشترٍ).
 */

export type ProcurementDocType = 'rfq' | 'offer';

/**
 * لا تؤثّر في أيّ دالّة هنا — أُبقيت بارامتراً لأن مواصفة #108 تنصّ على توقيع
 * (نوع، نطاق)، ولتوافق مستدعٍ قد يمرّرها اليوم. اختبار `procurementColumns.test.ts`
 * يُثبت أنّ تمرير نطاقين مختلفين يُنتج المصفوفة نفسها حرفياً.
 */
export type ProcurementScope = 'local' | 'import';

export type ProcurementColumnKey =
  | 'seq'
  | 'product'
  | 'specs'
  | 'quantity'
  | 'unitOfMeasure'
  | 'estimatedPrice'
  | 'unitPrice'
  | 'lineTotal'
  | 'lowestPrice';

export interface ProcurementColumnDef {
  key: ProcurementColumnKey;
  header: string;
}

const HEADERS: Record<ProcurementColumnKey, string> = {
  seq: 'تسلسل',
  product: 'الصنف',
  specs: 'المواصفات',
  quantity: 'الكمية',
  unitOfMeasure: 'وحدة القياس',
  estimatedPrice: 'السعر التقديري',
  unitPrice: 'سعر الوحدة',
  lineTotal: 'الإجمالي',
  lowestPrice: 'أقل سعر',
};

/**
 * أعمدة الشاشة لكل نوع مستند — المصدر الوحيد للمصفوفة الواردة في مواصفة #108 §٤:
 *
 * |                     | طلبية | عرض |
 * |---------------------|:-----:|:---:|
 * | تسلسل/الصنف/المواصفات/الكمية | ✓ | ✓ |
 * | وحدة القياس          |   ✓   |  ✓  |
 * | السعر التقديري (داخلي) |   ✓   |  ✗  |
 * | سعر الوحدة/الإجمالي  |   ✗   |  ✓  |
 * | أقل سعر              | مصدر تعبئة فقط (لا عمود) | ✓ عمود |
 *
 * «أقل سعر» في الطلبية ليس عمود شاشة — هو مصدر تعبئة السعر التقديري ويُعرض
 * إشارةً بجانب البند وفي منتقي الأصناف (`purchasePriceHint.ts`)، لا عموداً في
 * الجدول. لذلك غائبٌ عمداً عن `rfq` هنا رغم وجوده في العرض.
 */
const SCREEN_COLUMN_KEYS: Record<ProcurementDocType, ProcurementColumnKey[]> = {
  rfq: ['seq', 'product', 'specs', 'quantity', 'unitOfMeasure', 'estimatedPrice'],
  offer: ['seq', 'product', 'specs', 'quantity', 'unitOfMeasure', 'unitPrice', 'lineTotal', 'lowestPrice'],
};

/**
 * قائمة سماح: وحدها هذه المفاتيح تخرج إلى مستندٍ يُطبَع أو يُصدَّر — عمودٌ لا
 * يُذكَر هنا لا يخرج مهما أُضيف إلى `SCREEN_COLUMN_KEYS` مستقبلاً.
 * `estimatedPrice` و`lowestPrice` غائبان عمداً — لا يخرجان أبداً (مواصفة #108
 * §١١: «أقل سعر غائبٌ — لا يدخل بانيَ الحمولة أصلاً»). أمّا `unitPrice`
 * و`lineTotal` **فيُطبَعان في العرض**: عرضٌ يُطبَع بلا أسعارٍ ورقةٌ فارغةُ
 * المعنى. وهذا بعينه ما يجعل المجموعات **ثلاثاً لا اثنتين**: الطباعةُ أوسعُ
 * ممّا يخرج إلى المورد، لا مساويةً له.
 */
const PRINT_ALLOWED_KEYS: ProcurementColumnKey[] = [
  'seq', 'product', 'specs', 'quantity', 'unitOfMeasure', 'unitPrice', 'lineTotal',
];

/**
 * قائمة سماح المورد — فرعية من `PRINT_ALLOWED_KEYS` (الثالثة فرعية من
 * الثانية دوماً، مهما تغيّرت الأولى). والورقةُ التي تصل المورد فيها **خانةُ
 * سعرٍ فارغةٌ يملؤها هو** — فلا سعرَ وحدةٍ ولا إجماليَّ يخرجان إليه، ولا رقمٌ
 * يوحي إليه بجوابنا. وهذا هو الحدُّ الذي تفترق عنده الطباعةُ عمّا يخرج إليه.
 */
const SUPPLIER_ALLOWED_KEYS: ProcurementColumnKey[] = [
  'seq', 'product', 'specs', 'quantity', 'unitOfMeasure',
];

const buildColumns = (keys: ProcurementColumnKey[]): ProcurementColumnDef[] =>
  keys.map((key) => ({ key, header: HEADERS[key] }));

/** أعمدة الشاشة — الجدول الكامل الذي يراه المستخدم داخل النظام. */
export function getScreenColumns(
  docType: ProcurementDocType,
  _scope?: ProcurementScope,
): ProcurementColumnDef[] {
  return buildColumns(SCREEN_COLUMN_KEYS[docType]);
}

/** أعمدة الطباعة — فرعٌ مبنيٌّ بقائمة سماح من أعمدة الشاشة نفسها. */
export function getPrintColumns(
  docType: ProcurementDocType,
  scope?: ProcurementScope,
): ProcurementColumnDef[] {
  return getScreenColumns(docType, scope).filter((col) => PRINT_ALLOWED_KEYS.includes(col.key));
}

/** أعمدة ما يخرج إلى المورد — فرعٌ من أعمدة الطباعة، بقائمة سماح أضيق. */
export function getSupplierColumns(
  docType: ProcurementDocType,
  scope?: ProcurementScope,
): ProcurementColumnDef[] {
  return getPrintColumns(docType, scope).filter((col) => SUPPLIER_ALLOWED_KEYS.includes(col.key));
}

/** الثلاث مجموعات معاً — للمستهلك الذي يحتاجها دفعة واحدة (شاشة + طباعة + Excel). */
export function getProcurementColumns(
  docType: ProcurementDocType,
  scope?: ProcurementScope,
): { screen: ProcurementColumnDef[]; print: ProcurementColumnDef[]; supplier: ProcurementColumnDef[] } {
  return {
    screen: getScreenColumns(docType, scope),
    print: getPrintColumns(docType, scope),
    supplier: getSupplierColumns(docType, scope),
  };
}

/**
 * تقصّ صفّ بيانات فعلياً على مفاتيح مجموعة أعمدة — بانيَ الحمولة الحقيقي
 * الذي يستهلكه رابط المورد والطباعة وExcel، لا مجرّد وصفٍ للأعمدة. حقلٌ
 * موجود على الصفّ (مثل `estimatedPrice`) ولا يظهر في `columns` **لا يُنسخ** —
 * هذا ما يمنع تسرّبه، لا شرطٌ يُكتب عند كل استهلاك.
 */
export function pickProcurementRowFields<T extends Record<string, unknown>>(
  row: T,
  columns: ProcurementColumnDef[],
): Partial<T> {
  const out: Partial<T> = {};
  for (const col of columns) {
    const key = col.key as keyof T;
    if (Object.prototype.hasOwnProperty.call(row, key)) {
      out[key] = row[key];
    }
  }
  return out;
}
