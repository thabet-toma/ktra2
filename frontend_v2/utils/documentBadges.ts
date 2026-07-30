/**
 * T-DOCBADGE — تسميات صادقة لمستندات ما قبل الفاتورة (بيعاً وشراءً).
 *
 * شاشة الشراء تعرض **نوعين** في قائمة واحدة: عرض سعر مورد وطلبية شراء. كانا
 * يُسقطان على قاموس حالات العرض القديم وحده، فـ«طلبية مؤكَّدة» و«طلبية محوَّلة
 * لفاتورة» تظهران بنفس النص («معتمد للشحن») ولا شيء يقول أيّهما عرضٌ وأيّهما
 * طلبية — فيبدو التحويل كأنه لم يحدث. هذه الطبقة نقيّة (بلا React) فتُختبر.
 */
export type ProcurementDocKind = "quotation" | "import_quotation" | "order";

/** نوع المستند من معرّف الواجهة الموحّد (`quote-12` / `order-7`). */
export const procurementDocKind = (
  id: string,
  scope: "purchase" | "import" = "purchase",
): ProcurementDocKind => {
  if (String(id).startsWith("order-")) return "order";
  return scope === "import" ? "import_quotation" : "quotation";
};

export const PROCUREMENT_KIND_LABELS: Record<ProcurementDocKind, string> = {
  quotation: "عرض سعر",
  import_quotation: "عرض استيراد",
  order: "طلبية شراء",
};

const QUOTATION_STATUS_LABELS: Record<string, string> = {
  draft: "مسودة",
  sent: "مُرسَل للمورد",
  accepted: "مقبول",
  rejected: "مرفوض",
  expired: "منتهي الصلاحية",
  cancelled: "ملغى",
  converted: "محوَّل إلى طلبية",
};

const ORDER_STATUS_LABELS: Record<string, string> = {
  draft: "مسودة",
  confirmed: "مؤكَّدة",
  converted: "محوَّلة إلى فاتورة",
  cancelled: "ملغاة",
};

/**
 * T-IMPOFFER — عرض الاستيراد يُقرأ كقرار ملاءمة لا كخطوة إرسال.
 *
 * المالك: «بدي عرض السعر في الاستيراد يكون إله حالات ومبيّن بالواجهة وداخل
 * العرض: ملائم / غير ملائم.» فـ`accepted`/`rejected` تُقرأان هنا بهذه اللغة،
 * و`converted` تعني «صار صفقة» لا «صار طلبية شراء».
 */
const IMPORT_QUOTATION_STATUS_LABELS: Record<string, string> = {
  draft: "مسودة",
  sent: "مُرسَل للمورد",
  accepted: "ملائم",
  rejected: "غير ملائم",
  expired: "منتهي الصلاحية",
  cancelled: "ملغى",
  converted: "محوَّل إلى صفقة",
};

const STATUS_TABLES: Record<ProcurementDocKind, Record<string, string>> = {
  quotation: QUOTATION_STATUS_LABELS,
  import_quotation: IMPORT_QUOTATION_STATUS_LABELS,
  order: ORDER_STATUS_LABELS,
};

/**
 * تسمية الحالة بحسب النوع — نفس المفتاح (`converted`) يعني ثلاثة أشياء مختلفة:
 * عرضٌ صار طلبية شراء، أو عرض استيراد صار صفقة، أو طلبيةٌ صارت فاتورة.
 */
export const procurementStatusLabel = (
  kind: ProcurementDocKind,
  backendStatus: string | undefined,
  fallback = "",
): string => {
  const key = String(backendStatus || "");
  return STATUS_TABLES[kind][key] || fallback || key || "—";
};

/** T-IMPOFFER — قرار الملاءمة على عرض السعر. */
export type OfferSuitability = "undecided" | "suitable" | "unsuitable";

export const offerSuitability = (
  backendStatus: string | undefined,
): OfferSuitability => {
  const key = String(backendStatus || "");
  if (key === "accepted" || key === "converted") return "suitable";
  if (key === "rejected" || key === "expired" || key === "cancelled") {
    return "unsuitable";
  }
  return "undecided";
};

/**
 * «وإذا غير ملائم يكون معلَّم على أنه مشطوب» — الشطب علامة قرار، لا علامة
 * انتهاء دورة: المحوَّل إلى صفقة **ليس** مشطوباً وإن أُغلقت دورته.
 */
export const isOfferStruckThrough = (backendStatus: string | undefined): boolean =>
  offerSuitability(backendStatus) === "unsuitable";

/**
 * عرض الاستيراد يُحوَّل إلى صفقة عند اعتباره ملائماً فقط — والمحوَّل مرة لا
 * يُحوَّل ثانية (الخادم يحرس ذلك بعلاقة OneToOne على المصدر).
 */
export const canConvertImportOffer = (backendStatus: string | undefined): boolean =>
  String(backendStatus || "") === "accepted";

/** المستند المنتهي دورته لا يقبل إجراءات — يُعرض للقراءة فقط. */
export const isProcurementDocClosed = (backendStatus: string | undefined): boolean =>
  ["converted", "cancelled", "rejected", "expired", "invoiced", "closed"].includes(
    String(backendStatus || ""),
  );

/**
 * T-RESERVE — هل حجز الطلبية **سارٍ الآن**؟
 *
 * تاريخ «الحجز حتى» وحده يكذب: يبقى معروضاً على طلبية ملغاة أو محوَّلة أو انتهت
 * مدّتها، فيقرأ المستخدم «محجوز» وهو غير محجوز. نفس قاعدة الخادم
 * (`sales.services.reserved_quantity_map`): مؤكَّدة **و**لم ينتهِ تاريخ الحجز.
 */
export const isReservationActive = (
  status: string | undefined,
  reservedUntil: string | null | undefined,
  today: string,
): boolean => {
  if (String(status || "") !== "confirmed") return false;
  if (!reservedUntil) return false;
  return String(reservedUntil) >= today;
};
