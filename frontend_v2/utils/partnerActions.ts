/**
 * T-COAMENU — إجراءات الطرف: **مصدر واحد** تستهلكه كل قائمة يمين في الموقع.
 *
 * كانت إجراءات الشريك مكتوبةً داخل `layout/GlobalContextMenu` وحده، فشجرة
 * الحسابات (حيث كل حساب ذمم هو طرف) لم يكن لها منها شيء — كبسة اليمين عليها
 * تعرض إجراءات الحساب فقط. هذه الطبقة نقيّة (بلا React ولا DOM) فتُختبر بـNode
 * وتُعرض في أي قائمة: الشجرة، القائمة العامّة، وأي شاشة لاحقة.
 *
 * الإجراء إمّا **رابط** (`href`) يُفتح كما هو، أو **جسر** (`bridge`) يفتح مودالاً
 * في كرت الطرف عبر `sessionStorage` (نمط `ktra_partner_action` القائم).
 */

export type PartnerKind = "customer" | "supplier";

export interface PartnerActionTarget {
  id: string;
  name: string;
  kind: PartnerKind;
}

export type PartnerActionIcon =
  | "card"
  | "statement"
  | "ledger"
  | "invoice"
  | "quotation"
  | "order"
  | "receipt"
  | "payment"
  | "list"
  | "repeat";

export interface PartnerAction {
  key: string;
  label: string;
  icon: PartnerActionIcon;
  /** وجهة الإجراء — رابط داخلي مُعبَّأ بمعرّف الطرف. */
  href?: string;
  /** إجراء يفتح مودالاً في كرت الطرف بدل رابط مستقل. */
  bridge?: "receipt" | "payment";
}

export interface PartnerActionGroup {
  title: string;
  actions: PartnerAction[];
}

/**
 * نوع الطرف في الخادم ← جانب المستندات. أطراف الشحن (وكيل/مخلّص/ناقل) تُعامَل
 * معاملة المورد: تُشترى منها خدمات وتُصرف لها سندات — لا فواتير بيع.
 */
export function partnerKindFromType(
  partnerType: string | null | undefined,
): PartnerKind | null {
  switch (String(partnerType || "")) {
    case "Customer":
      return "customer";
    case "Supplier":
    case "FreightForwarder":
    case "CustomsBroker":
    case "LocalTransporter":
    case "Carrier":
      return "supplier";
    default:
      return null;
  }
}

/** تسمية نوع الطرف كما تظهر في الكرت والجداول والفلاتر. */
const PARTNER_TYPE_LABELS: Record<string, string> = {
  Customer: "عميل",
  Supplier: "مورد",
  FreightForwarder: "وكيل شحن",
  CustomsBroker: "مخلّص جمركي",
  LocalTransporter: "ناقل محلي",
  Carrier: "ناقل",
};

export function partnerTypeLabel(partnerType: string | null | undefined): string {
  const t = String(partnerType || "");
  return PARTNER_TYPE_LABELS[t] || t;
}

export type VoucherDirection = "receipt" | "payment";

/**
 * اتجاه السند لكل نوع طرف — **قاعدة واحدة** يقرؤها كرت الطرف وقائمة زر اليمين.
 * كان الكرت يقرّر بـ`partner_type === 'supplier'` فيُعامَل المخلّص ووكيل الشحن
 * والناقل عملاءً («سند قبض» زرّاً افتراضياً). الدائن يُصرف له أولاً، ويبقى
 * «سند قبض» خياراً ثانياً صريحاً لاسترداد زيادةٍ دُفعت له.
 */
export function partnerVoucherDirections(
  partnerType: string | null | undefined,
): { primary: VoucherDirection; secondary: VoucherDirection | null } | null {
  const kind = partnerKindFromType(partnerType);
  if (kind === "customer") return { primary: "receipt", secondary: null };
  if (kind === "supplier") return { primary: "payment", secondary: "receipt" };
  return null;
}

/** إجراءات الطرف مجمَّعة بعناوين — قائمة مسطّحة طويلة لا تُقرأ. */
export function partnerActionGroups(
  target: PartnerActionTarget,
): PartnerActionGroup[] {
  const id = encodeURIComponent(target.id);
  const named = (base: string) => (target.name ? `${base}: ${target.name}` : base);

  if (target.kind === "customer") {
    return [
      {
        title: "الطرف",
        actions: [
          { key: "card", label: named("بطاقة العميل"), icon: "card", href: `/partners/${id}` },
          { key: "statement", label: "كشف حساب", icon: "statement", href: `/partners/${id}?tab=statement` },
          { key: "ledger", label: "حركات الحساب", icon: "ledger", href: `/partners/${id}?tab=ledger` },
        ],
      },
      {
        title: "إنشاء مستند",
        actions: [
          { key: "sales-invoice", label: "فاتورة مبيعات", icon: "invoice", href: `/sales/invoices/new?customer_id=${id}` },
          // ISSUE #53 (قرار 11): فاتورة الأتعاب فاتورة بيعٍ عادية — عميل مملوء
          // سلفاً وبندها الأول خدمي افتراضاً (`?service=1`، `SalesInvoiceEditor`).
          { key: "fee-invoice", label: "فاتورة أتعاب", icon: "invoice", href: `/sales/invoices/new?customer_id=${id}&service=1` },
          { key: "sales-quotation", label: "عرض سعر", icon: "quotation", href: `/sales/quotations?action=new&customer_id=${id}` },
          { key: "sales-order", label: "طلبية زبون", icon: "order", href: `/sales/orders?action=new&customer_id=${id}` },
          { key: "receipt", label: "سند قبض", icon: "receipt", bridge: "receipt" },
          // ISSUE #53 (قرار 22): نسخ آخر فاتورة للشهر الماضي بنقرة واحدة —
          // `SalesInvoicesPage` تلتقط العلمين وتطلب النسخ فور الوصول.
          { key: "repeat-last-invoice", label: "كرّر فاتورة الشهر الماضي", icon: "repeat", href: `/sales/invoices?repeat_last_month=1&customer=${id}` },
        ],
      },
      {
        title: "مستنداته",
        actions: [
          { key: "sales-invoices", label: "فواتيره", icon: "list", href: `/sales/invoices?customer=${id}` },
          { key: "sales-payments", label: "سندات قبضه", icon: "list", href: `/sales/customer-payments?partner=${id}` },
        ],
      },
    ];
  }

  return [
    {
      title: "الطرف",
      actions: [
        { key: "card", label: named("بطاقة المورد"), icon: "card", href: `/partners/${id}` },
        { key: "statement", label: "كشف حساب", icon: "statement", href: `/partners/${id}?tab=statement` },
        { key: "ledger", label: "حركات الحساب", icon: "ledger", href: `/partners/${id}?tab=ledger` },
      ],
    },
    {
      title: "إنشاء مستند",
      actions: [
        { key: "purchase-invoice", label: "فاتورة شراء", icon: "invoice", href: "/purchase-invoices/new" },
        { key: "purchase-offer", label: "عرض سعر شراء", icon: "quotation", href: "/price-offers" },
        { key: "payment", label: "سند صرف", icon: "payment", bridge: "payment" },
        { key: "refund-receipt", label: "سند قبض (استرداد)", icon: "receipt", bridge: "receipt" },
      ],
    },
    {
      title: "مستنداته",
      actions: [
        { key: "purchase-invoices", label: "فواتيره", icon: "list", href: `/purchase-invoices?partner=${id}` },
        { key: "supplier-payments", label: "سندات صرفه", icon: "list", href: `/supplier-payments?partner=${id}` },
      ],
    },
  ];
}
