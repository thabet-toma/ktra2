/**
 * منطق سياق قائمة زر الفأرة اليمنى — مصدر واحد مشترك يستهلكه
 * {@link ../components/layout/GlobalContextMenu}. الجزء النقيّ (بذر الحاسبة،
 * تنسيق الناتج، قراءة سياق الشريك) قابل لاختبار Node؛ وأغلفة DOM رفيعة تفصل
 * الوصول للـ DOM عن المنطق. لا وصول DOM على مستوى الوحدة (يبقى الاستيراد آمناً في Node).
 */

export type PartnerKind = "customer" | "supplier";
export interface PartnerContext {
  id: string;
  name: string;
  kind: PartnerKind;
}

export interface ItemContext {
  id: string;
  name: string;
}

/**
 * يحوّل قيمة حقل خام (قد تحوي فواصل آلاف/رمز عملة) إلى بذرة رقمية للحاسبة،
 * أو "" إن لم توجد قيمة رقمية صالحة.
 */
export function calcSeedFromRawValue(raw: string | null | undefined): string {
  if (!raw) return "";
  // أبقِ الأرقام والنقطة والإشارة السالبة فقط (احذف فواصل الآلاف بأنواعها والرموز والمسافات).
  const cleaned = raw
    .replace(/[٫٬]/g, (m) => (m === "٫" ? "." : ""))
    .replace(/[^\d.\-]/g, "");
  if (cleaned === "" || cleaned === "-") return "";
  const n = Number(cleaned);
  return Number.isFinite(n) ? String(n) : "";
}

/** ينسّق ناتج الحاسبة كنص (حتى 4 منازل، بلا أصفار زائدة) — يطابق سلوك الحاسبة الحالي. */
export function formatCalcResult(value: number): string {
  return String(Number(value.toFixed(4)));
}

/**
 * يقرأ سياق الشريك من مُلتقِط سمات (يفصل قراءة DOM عن المنطق ليُختبَر نقيّاً).
 * يتطلّب معرّفاً ونوعاً معروفاً؛ الاسم اختياري.
 */
export function readPartnerContext(
  getAttr: (name: string) => string | null,
): PartnerContext | null {
  const id = getAttr("data-ctx-partner-id");
  const kind = getAttr("data-ctx-partner-kind");
  if (!id || (kind !== "customer" && kind !== "supplier")) return null;
  return { id, name: getAttr("data-ctx-partner-name") || "", kind };
}

/** يقرأ سياق الصنف من مُلتقِط سمات — معرّف مطلوب، الاسم اختياري. */
export function readItemContext(
  getAttr: (name: string) => string | null,
): ItemContext | null {
  const id = getAttr("data-ctx-item-id");
  if (!id) return null;
  return { id, name: getAttr("data-ctx-item-name") || "" };
}

// ————————————————————————— أغلفة DOM رفيعة —————————————————————————

const EDITABLE_SELECTOR =
  'input, textarea, [contenteditable=""], [contenteditable="true"]';

// أنواع input غير النصية لا تُفتح لها حاسبة/حافظة.
const NON_TEXT_INPUT_TYPES = new Set([
  "checkbox",
  "radio",
  "button",
  "submit",
  "reset",
  "file",
  "range",
  "color",
  "image",
  "hidden",
]);

/** يعيد أقرب حقل نصّي قابل للتحرير من هدف الحدث، أو null إن لم يكن حقل نصّ. */
export function resolveEditableTarget(
  target: EventTarget | null,
): HTMLElement | null {
  const el = target as HTMLElement | null;
  if (!el || typeof el.closest !== "function") return null;
  const editable = el.closest(EDITABLE_SELECTOR) as HTMLElement | null;
  if (!editable) return null;
  if (
    editable instanceof HTMLInputElement &&
    NON_TEXT_INPUT_TYPES.has(editable.type)
  ) {
    return null;
  }
  return editable;
}

/** يقرأ القيمة النصية الحالية لحقل قابل للتحرير. */
export function readEditableValue(el: HTMLElement): string {
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    return el.value;
  }
  return el.textContent ?? "";
}

/**
 * يكتب قيمة إلى حقل ويطلق حدث `input` (و`change` للحقول الأصيلة) كي تلتقطه
 * حقول React المتحكَّم بها. يستخدم setter الأصيل حتى لا يتجاهل React التغيير.
 */
export function writeEditableValue(el: HTMLElement, value: string): void {
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    const proto =
      el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  } else {
    el.textContent = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

/** يعيد سياق الشريك من أقرب عنصر يحمل `data-ctx-partner-id`، أو null. */
export function resolvePartnerContextFromTarget(
  target: EventTarget | null,
): PartnerContext | null {
  const el = target as HTMLElement | null;
  if (!el || typeof el.closest !== "function") return null;
  const node = el.closest("[data-ctx-partner-id]") as HTMLElement | null;
  if (!node) return null;
  return readPartnerContext((name) => node.getAttribute(name));
}

/** يعيد سياق الصنف من أقرب عنصر يحمل `data-ctx-item-id`، أو null. */
export function resolveItemContextFromTarget(
  target: EventTarget | null,
): ItemContext | null {
  const el = target as HTMLElement | null;
  if (!el || typeof el.closest !== "function") return null;
  const node = el.closest("[data-ctx-item-id]") as HTMLElement | null;
  if (!node) return null;
  return readItemContext((name) => node.getAttribute(name));
}
