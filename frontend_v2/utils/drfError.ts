/**
 * G2 — طبقة موحّدة لأخطاء الخادم.
 * تحوّل أخطاء DRF الخام ({"product":["..."]} أو المتداخلة many=True) إلى نص
 * عربي مقروء مربوط بالحقل، بدل عرض JSON خام أو اسم حقل تقني في التنبيهات.
 *
 * وحدة نقية (بلا اعتماد على المتصفح/dexie) كي تُختبر عبر node --test.
 * يستدعيها `services/restApi.handleResponseError` كنقطة اختناق وحيدة لكل الكتابات.
 */

/** خريطة أسماء حقول DRF التقنية → تسميات عربية بشرية. */
const FIELD_LABELS: Record<string, string> = {
  product: "الصنف",
  partner: "الطرف",
  customer: "العميل",
  supplier: "المورد",
  quantity: "الكمية",
  unit_price: "سعر الوحدة",
  price: "السعر",
  items: "البنود",
  lines: "البنود",
  ref_number: "الرقم المرجعي",
  order_date: "التاريخ",
  date: "التاريخ",
  warehouse: "المستودع",
  amount: "المبلغ",
  currency: "العملة",
  name_ar: "الاسم العربي",
  name_en: "الاسم الإنجليزي",
  name: "الاسم",
  sku: "رقم الصنف",
  account: "الحساب",
  shipment: "الشحنة",
  deal: "الصفقة",
  vat_percent: "نسبة الضريبة",
  discount_amount: "قيمة الخصم",
  discount_percent: "نسبة الخصم",
};

/** رسائل DRF الإنجليزية الافتراضية الشائعة → عربية (عند تشغيل الخادم بلغة إنجليزية). */
const COMMON_MESSAGES: Record<string, string> = {
  "This field is required.": "هذا الحقل مطلوب.",
  "This field may not be blank.": "هذا الحقل لا يمكن أن يكون فارغاً.",
  "This field may not be null.": "هذا الحقل مطلوب.",
  "A valid number is required.": "يجب إدخال رقم صحيح.",
  "A valid integer is required.": "يجب إدخال رقم صحيح.",
  "Not found.": "غير موجود.",
  "Invalid pk": "معرّف غير صالح.",
};

/** حقول لا تُلحق بها تسمية (رسائل عامة أو على مستوى السجل). */
const SKIP_LABEL = new Set(["non_field_errors", "detail", "error", "__all__"]);

function translate(msg: string): string {
  return COMMON_MESSAGES[msg.trim()] ?? msg;
}

export function humanizeDrfError(data: unknown): string {
  if (data == null) return "";
  if (typeof data === "string") return data;

  // DRF غالباً يضع الرسالة العامة في detail/error — تُعرض كما هي بلا تسمية حقل.
  if (typeof data === "object") {
    const top = data as Record<string, unknown>;
    if (typeof top.detail === "string") return translate(top.detail);
    if (typeof top.error === "string") return translate(top.error);
  }

  const seen = new Set<string>();
  const parts: string[] = [];

  const push = (fieldKey: string, raw: string): void => {
    const msg = translate(raw);
    const label = fieldKey && !SKIP_LABEL.has(fieldKey) ? FIELD_LABELS[fieldKey] : undefined;
    const line = label ? `${label}: ${msg}` : msg;
    if (!seen.has(line)) {
      seen.add(line);
      parts.push(line);
    }
  };

  const walk = (node: unknown, fieldKey: string): void => {
    if (node == null) return;
    if (typeof node === "string") { push(fieldKey, node); return; }
    if (typeof node === "number" || typeof node === "boolean") { push(fieldKey, String(node)); return; }
    if (Array.isArray(node)) { node.forEach((v) => walk(v, fieldKey)); return; }
    if (typeof node === "object") {
      for (const [k, v] of Object.entries(node as Record<string, unknown>)) walk(v, k);
    }
  };

  walk(data, "");
  return parts.join("؛ ");
}

/**
 * G6: يستخرج خريطة «حقل → رسالة عربية» من خطأ DRF لإبراز الحقل الناقص في النموذج.
 * المفتاح = اسم حقل DRF التقني (leaf، مثل shipment_date/product)؛ القيمة = الرسالة
 * المترجمة. يتجاهل detail/error/non_field_errors (رسائل عامة بلا حقل). أول رسالة
 * لكل حقل تُحفظ (تكفي للإبراز).
 */
export function extractDrfFieldErrors(data: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (data == null || typeof data !== "object") return out;

  const put = (fieldKey: string, raw: string): void => {
    if (!fieldKey || SKIP_LABEL.has(fieldKey)) return;
    if (out[fieldKey] == null) out[fieldKey] = translate(raw);
  };

  const walk = (node: unknown, fieldKey: string): void => {
    if (node == null) return;
    if (typeof node === "string") { put(fieldKey, node); return; }
    if (typeof node === "number" || typeof node === "boolean") { put(fieldKey, String(node)); return; }
    if (Array.isArray(node)) { node.forEach((v) => walk(v, fieldKey)); return; }
    if (typeof node === "object") {
      for (const [k, v] of Object.entries(node as Record<string, unknown>)) walk(v, k);
    }
  };

  walk(data, "");
  return out;
}

/**
 * رسالة خطأ مقروءة من أي شكل مرمي: `Error` (تُقرأ رسالته) أو جسم DRF أو نص.
 * `humanizeDrfError` وحده يعيد "" لكائن Error لأن رسالته ليست خاصية قابلة للتعداد.
 */
export function humanizeThrown(e: unknown, fallback = "حدث خطأ غير متوقع"): string {
  const raw = e instanceof Error ? e.message : e;
  let parsed: unknown = raw;
  if (typeof raw === "string") {
    const text = raw.trim();
    if (text.startsWith("{") || text.startsWith("[")) {
      try { parsed = JSON.parse(text); } catch { parsed = raw; }
    }
  }
  return humanizeDrfError(parsed) || fallback;
}
