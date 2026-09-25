/**
 * task16 (A4-A6): روابط موحّدة بين الكيانات.
 *
 * أي مرجع لفاتورة (في حركات المخزن، قيود اليومية، …) يجب أن يفتح الفاتورة
 * نفسها. هذه الدالة تترجم (reference_type, reference_id) إلى مسار الفاتورة.
 * مصدر حقيقة واحد كي لا يتكرر منطق المطابقة في كل شاشة (DRY).
 */
// ‏`.ts` صريحةً: هذا الملفّ يُستورَد من `entityLinks.test.ts` عبر `node --test`،
// وهو محرّكُ ESM لا حزمةُ Vite — لا يحلّ امتداداً محذوفاً فيسقط الاختبارُ بـ
// `ERR_MODULE_NOT_FOUND` لا بتأكيدٍ فاشل، فيبدو العطبُ في الاختبار لا في الاستيراد.
import { invoiceKindLabel } from "./documentTypeLabels.ts";

export function invoicePathForReference(
  referenceType?: string | null,
  referenceId?: number | null
): string | null {
  if (referenceId == null) return null;
  const t = (referenceType || "").toUpperCase();
  // مراجع فاتورة الشراء (الاستلام/الترحيل)
  if (t.includes("PURCHASE_INVOICE")) return `/purchase-invoices/${referenceId}`;
  // مراجع فاتورة المبيعات: الفاتورة نفسها + حركات المخزون/التكلفة الناتجة عنها
  if (
    t.includes("SALES_INVOICE") ||
    t.includes("SALES_DELIVERY") ||
    t === "SALE" ||
    t === "STOCK_ISSUE"
  ) {
    return `/sales/invoices/${referenceId}`;
  }
  return null;
}

/** مسار مستند/حركة من سجل النشاط أو كشف الحساب — مصدر تنقّل واحد. */
export function entityPathForReference(
  referenceType?: string | null,
  referenceId?: number | null
): string | null {
  const invoicePath = invoicePathForReference(referenceType, referenceId);
  if (invoicePath) return invoicePath;
  if (referenceId == null) return null;
  const t = (referenceType || "").toUpperCase();
  if (t === "DEAL" || t === "LOGISTICS_DEAL") return `/deals/${referenceId}`;
  if (t === "SHIPMENT" || t === "LOGISTICS_SHIPMENT") return `/import-flow/${referenceId}`;
  if (t === "CUSTOMER_PAYMENT") return `/sales/customer-payments?payment_id=${referenceId}`;
  if (t === "SUPPLIER_PAYMENT") return `/supplier-payments?payment_id=${referenceId}`;
  // مستند قيد العكس هو القيد الأصلي نفسه — `reference_id` رقمه (accounting/views.py `reverse`).
  if (t === "JOURNAL_REVERSAL") return `/accounting/journals/${referenceId}`;
  // LOGISTICS_PAYMENT عمداً بلا مسار هنا: `reference_id` رقم الدفعة لا رقم الصفقة
  // (logistics/views/deals.py) — فـ`/deals/<id>` سيفتح صفقة خاطئة. الصفقة تُفتح من
  // شريط «مرتبط بصفقة» في شاشة القيد، وهو يستعمل `deal_ref_number` من الخادم.
  return null;
}

export interface PlatformNoteTarget {
  target_type: string;
  target_id: string;
  target_label: string;
  target_path: string;
}

/** رابط داخلي آمن للتنقّل من إشعار؛ يُعاد فحصه أمامياً حتى لو عُدّلت بيانات الإشعار. */
export function isSafeInternalPath(path: string): boolean {
  return path.startsWith('/')
    && !path.startsWith('//')
    && !path.includes('\\')
    && !Array.from(path).some((char) => char.charCodeAt(0) < 32);
}

/** هدف افتراضي لملاحظة عامة: الصفحة الحالية كاملةً، بما فيها معرّف السجل في query. */
export function platformNoteTarget(
  pathname: string,
  search: string,
  label: string,
): PlatformNoteTarget {
  const candidate = `${pathname || '/'}${search || ''}`;
  const targetPath = isSafeInternalPath(candidate) ? candidate : '/dashboard';
  return {
    target_type: 'page',
    target_id: targetPath,
    target_label: label.trim() || 'الصفحة الحالية',
    target_path: targetPath,
  };
}

/**
 * كشف الحساب: تسمية عربية واضحة لنوع الحركة بدل رمز `reference_type` الإنجليزي الخام
 * (SALES_INVOICE / CUSTOMER_PAYMENT …). مصدر حقيقة واحد يخدم كشف الحساب ونافذة التفاصيل.
 */
export function referenceTypeLabel(
  referenceType?: string | null,
  /**
   * ‏#214-ب: نوعُ المستند حين يكون معلوماً (`reference_kind` في كشف الحساب).
   *
   * **بلاغُ المالك: «لما اضغط عليه بتبين كلمة فاتورة مبيعات بالعنوان».** وهو
   * صحيح: قيدُ مرتجع البيع يُكتب بـ`reference_type="SALES_INVOICE"` **كالبيعة
   * حرفاً** — لأنّه فعلاً صفُّ `SalesInvoice` بنوعٍ آخر — فكانت هذه الدالّةُ
   * تسمّيه فاتورةَ مبيعات في كشف الحساب وفي عنوان نافذة التفاصيل.
   *
   * ولم يكن فرعُ `SALES_RETURN` أدناه يحرس شيئاً: **لا مستدعيَ يُنتج تلك
   * القيمة أصلاً** — فرعٌ ميّتٌ بدا حارساً.
   *
   * والوسيطُ اختياريٌّ عمداً: للدالّة مستدعون لا يملكون النوع (كشفُ حسابٍ قديم،
   * دفترُ اليومية)، وإلزامُهم به يكسرهم بلا فائدة — يبقى سلوكُهم كما كان.
   */
  invoiceKind?: string | null,
): string {
  const t = (referenceType || "").toUpperCase();
  if (!t) return "حركة";
  const kindLabel = invoiceKindLabel(invoiceKind);
  if (kindLabel) return kindLabel;
  if (t.includes("SALES_RETURN")) return "مرتجع بيع";
  if (t.includes("PURCHASE_RETURN")) return "مرتجع شراء";
  if (
    t.includes("SALES_INVOICE") ||
    t.includes("SALES_DELIVERY") ||
    t === "SALE" ||
    t === "STOCK_ISSUE"
  )
    return "فاتورة مبيعات";
  if (t.includes("PURCHASE_INVOICE") || t === "PURCHASE_RECEIPT") return "فاتورة مشتريات";
  if (t === "CUSTOMER_PAYMENT") return "سند قبض";
  if (t === "SUPPLIER_PAYMENT") return "سند صرف";
  if (t === "LOGISTICS_CLEARANCE") return "مستحق تخليص";
  if (t === "CLEARANCE_PAYMENT") return "دفع تخليص جمركي";
  if (t === "LOCAL_SHIPMENT") return "ارسالية";
  if (t === "LOCAL_SHIPMENT_PAYMENT") return "دفع للناقل";
  if (t === "LOGISTICS_PAYMENT" || t === "PAYMENT") return "سند دفع";
  if (t === "CREDIT_DEBIT_NOTE") return "إشعار مدين/دائن";
  if (t === "PARTNER_OPENING") return "رصيد افتتاحي";
  if (t === "JOURNAL_REVERSAL") return "عكس قيد";
  // A3: قيد يدوي وسمه المحاسب «تسوية» — يُميَّز عن القيد اليدوي العادي.
  if (t === "ADJUSTMENT") return "قيد تسوية";
  return "قيد يومية";
}

/**
 * كشف الحساب: نبرة الحركة للتمييز اللوني. ما يُنشئ ذمّة على الطرف (فاتورة/مستحق)
 * أحمر، وما يسدّدها (سند قبض/صرف) أخضر، وما عداه محايد. مصدر حقيقة واحد كي لا
 * تختلف الألوان بين بطاقة العميل والمورد.
 */
export type StatementTone = "invoice" | "payment" | "neutral";

export function statementMovementTone(referenceType?: string | null): StatementTone {
  const t = (referenceType || "").toUpperCase();
  if (!t) return "neutral";
  if (t.includes("PAYMENT")) return "payment";
  if (
    t.includes("SALES_INVOICE") ||
    t.includes("PURCHASE_INVOICE") ||
    t.includes("SALES_DELIVERY") ||
    t === "SALE" ||
    t === "STOCK_ISSUE" ||
    t === "PURCHASE_RECEIPT" ||
    t === "LOGISTICS_CLEARANCE" ||
    t === "LOCAL_SHIPMENT" ||
    t === "SHIPMENT_FREIGHT_ACCRUAL"
  ) {
    return "invoice";
  }
  return "neutral";
}

/** صنف خلفية الصف حسب نبرة الحركة — يخدم كشف الحساب في كل البطاقات. */
export function statementToneRowClass(referenceType?: string | null): string {
  const tone = statementMovementTone(referenceType);
  if (tone === "payment") return "bg-emerald-50 dark:bg-emerald-900/20";
  if (tone === "invoice") return "bg-red-50 dark:bg-red-900/20";
  return "";
}

/**
 * كشف الحساب: «بيان» مقروء بدل مصطلح الحساب الخام («ذمم» / «تسديد ذمم») الذي يربك
 * المستخدم. يستبدل الجزء الأول (اسم الحساب) بتسمية الحركة العربية ويُبقي رقم المستند
 * في الذيل — يعمل على البيانات القديمة (تحويل وقت العرض، بلا مساس بسجلّ القيد).
 * الفاصل em-dash «—» (رقم الفاتورة مثل SI-1-6 يستخدم شرطة ASCII، فالفصل آمن).
 */
export function clarifyStatementDescription(
  referenceType?: string | null,
  description?: string | null
): string {
  const label = referenceTypeLabel(referenceType);
  const desc = (description || "").trim();
  if (!desc) return label;
  const sep = desc.indexOf("—");
  const tail = sep >= 0 ? desc.slice(sep + 1).trim() : "";
  return tail ? `${label} — ${tail}` : desc;
}

/**
 * task16 A4 / ربط المنتجات: رابط بطاقة المنتج. أي «ذكر لمنتج» في الموقع يجب أن
 * يكون قابلاً للنقر ويفتح بطاقة المنتج على تبويب «حركة المخزون» (لا النظرة العامة)
 * — مصدر حقيقة واحد كي لا يتكرر بناء المسار في كل شاشة (DRY). التبويب يُمرَّر
 * عبر `?tab=` ويُقرأ في `ProductProfilePage` كـ `initialTab`.
 */
export function productProfilePath(
  productId: number | string,
  tab: "kpis" | "invoices" | "ledger" = "ledger"
): string {
  return `/products/${productId}?tab=${tab}`;
}

/**
 * مسار الكرت المجمّع — مصدر واحد لكل من يفتحه (شجرة المنتجات، جدولها، الجرد).
 * التصنيف يسمو على تعداد المعرّفات: رابطٌ فيه ~1500 معرّف يبلغ ~7.5KB في سطر
 * الطلب فيردّه nginx بـ414 قبل أن تُقلع الواجهة أصلاً. `?ids=` يبقى مفهوماً —
 * للروابط القديمة، ولمجموعةٍ لا تصنيفَ لها.
 */
export function productGroupPath(opts: {
  name: string;
  categoryId?: number | string | null;
  ids?: Array<number | string>;
}): string {
  const name = encodeURIComponent(opts.name || "");
  const cat = opts.categoryId == null ? "" : String(opts.categoryId);
  if (cat) return `/product-group?category=${encodeURIComponent(cat)}&name=${name}`;
  return `/product-group?ids=${(opts.ids || []).join(",")}&name=${name}`;
}

export function supplierPath(): string {
  return "/suppliers";
}

export function customerPath(): string {
  return "/sales/customers";
}

/** مستندٌ وُزِّع عليه سندٌ واحدٌ مع غيره — من `link_targets` في كشف الحساب. */
export interface StatementLinkTarget {
  key: string;
  label: string;
  /** المبلغ الموزَّع على هذا المستند بالعملة الأساسية. */
  amount: string;
}

interface StatementLinkRow {
  id: number | string;
  link_key?: string | null;
  link_targets?: StatementLinkTarget[];
}

/**
 * سندٌ موزَّع على أكثر من مستند يبقى صفّاً واحداً في مكانه (الرصيد الجاري لا يتكرّر)،
 * ويُلحق داخل مجموعة كل مستندٍ ظاهرٍ في الصفحة سطراً معلوماتياً بلا مدين/دائن ولا
 * رصيد (`info_amount` = ما وُزِّع عليه). مستندٌ خارج الصفحة لا سطر له — مجموعةٌ من
 * سطرٍ فرعيٍّ وحده بلا مستندها تضلّل.
 */
export function withStatementLinkSublines<T extends StatementLinkRow>(
  rows: T[],
): Array<T & { info_amount?: string }> {
  const anchors = new Set(rows.map((r) => r.link_key).filter(Boolean));
  const sublines: Array<T & { info_amount?: string }> = [];
  for (const row of rows) {
    for (const target of row.link_targets ?? []) {
      if (!anchors.has(target.key)) continue;
      sublines.push({
        ...row,
        id: `info-${row.id}-${target.key}`,
        debit: "",
        credit: "",
        balance_before: "",
        running_balance: "",
        link_key: target.key,
        link_targets: [],
        info_amount: target.amount,
      });
    }
  }
  return [...rows, ...sublines];
}

/** قيدٌ وعكسه على كشف الطرف — `reversal_pair` في ردّ الخادم (`statement_reversal_pairs`). */
export interface StatementReversalPair {
  original_journal_id: number;
  reversal_journal_id: number;
  role?: "original" | "reversal";
}

interface ReversalFoldRow extends StatementLinkRow {
  debit: string;
  credit: string;
  running_balance: string;
  balance_before?: string;
  /** الرصيد نفسه محسوباً بلا الأزواج — من حلقة الخادم لا من الصفحة. */
  running_balance_folded?: string;
  balance_before_folded?: string;
  reversal_pair_id?: number | null;
  reversal_pair?: StatementReversalPair | null;
}

export type FoldedStatementRow<T> = T & {
  /** السطر الرمادي وطرفاه المفتوحان مجموعةٌ واحدة (`reversal:<الأصل>`). */
  link_key?: string | null;
  /** سطر «قيد صُحّح» الرمادي مكان الزوج. */
  reversal_summary?: StatementReversalPair;
  /** طرفٌ من زوجٍ مفتوح تحت سطره — بلا رصيدٍ جارٍ، فالرصيد المطويّ لا يمرّ به. */
  reversal_member?: boolean;
};

/**
 * يطوي «القيد + عكسه» (صافيهما على الطرف صفر) في سطرٍ رماديٍّ واحد مكان أوّل
 * طرفَيه في الصفحة، ويعرض بقية الأسطر بالرصيد المطويّ — فلا يمرّ الرصيد الجاري
 * بالقيمة المضلّلة بين القيد وعكسه. الزوج المفتوح (`expanded`) يُظهر طرفيه تحت
 * سطره بلا رصيد. لا يُسقط سطراً ماليّاً: الزوج صافيه صفر، والختامي واحد.
 * طرفٌ خارج الصفحة لا يمنع الطيّ — السطر الرمادي يدلّ عليه برقمه.
 */
export function foldStatementReversals<T extends ReversalFoldRow>(
  rows: T[],
  expanded: ReadonlySet<number>,
): Array<FoldedStatementRow<T>> {
  const members = new Map<number, T[]>();
  for (const row of rows) {
    if (row.reversal_pair_id == null || !row.reversal_pair) continue;
    members.set(row.reversal_pair_id, [...(members.get(row.reversal_pair_id) ?? []), row]);
  }
  const out: Array<FoldedStatementRow<T>> = [];
  for (const row of rows) {
    const pairId = row.reversal_pair_id;
    if (pairId == null || !row.reversal_pair) {
      out.push({
        ...row,
        balance_before: row.balance_before_folded ?? row.balance_before,
        running_balance: row.running_balance_folded ?? row.running_balance,
      });
      continue;
    }
    const group = members.get(pairId);
    if (!group || group[0] !== row) continue;
    const key = `reversal:${pairId}`;
    out.push({
      ...row,
      id: `reversal-${pairId}`,
      debit: "",
      credit: "",
      balance_before: row.balance_before_folded ?? "",
      running_balance: row.running_balance_folded ?? "",
      link_key: key,
      link_targets: [],
      reversal_summary: {
        original_journal_id: row.reversal_pair.original_journal_id,
        reversal_journal_id: row.reversal_pair.reversal_journal_id,
      },
    });
    if (!expanded.has(pairId)) continue;
    for (const member of group) {
      out.push({
        ...member,
        balance_before: "",
        running_balance: "",
        link_key: key,
        link_targets: [],
        reversal_member: true,
      });
    }
  }
  return out;
}
