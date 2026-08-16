/**
 * لصق صورة من الحافظة (Ctrl+V) في حقول رفع الصور — بديل عن رفع الملف يدوياً فقط.
 *
 * سجلّ مناطق اللصق: مهما بلغ عدد المناطق المسجّلة، هناك مستمع `paste` واحد على
 * المستند، وكل لصقة تذهب إلى **منطقة واحدة على الأكثر** يحدّدها `resolvePasteZone`
 * (دالة صرفة، مُختبَرة في `clipboardImage.test.ts`). قبل هذا السجلّ كان كل مستهلك
 * يركّب مستمعاً خاصاً به، فتُرفع الصورة مرتين حين تُركَّب شاشتان معاً.
 */
import { useEffect, useRef } from "react";
import type { RefObject } from "react";

export function extractImageFilesFromClipboard(e: ClipboardEvent): File[] {
  const items = e.clipboardData?.items;
  if (!items) return [];
  const files: File[] = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) files.push(file);
    }
  }
  return files;
}

// ── التوجيه: الجزء الصرف ──────────────────────────────────────────

/** حالة منطقة لصق مسجّلة كما يراها المُوجِّه — بلا DOM كي تبقى قابلة للاختبار. */
export type PasteZoneState = {
  id: number;
  enabled: boolean;
  /** لا تفوز أبداً بترتيب التركيب — فقط بالاحتواء أو بعد تفاعل صريح (صفوف متكرّرة). */
  interactionRequired: boolean;
  /** عدّاد نشاط تصاعدي: يُمنح عند التركيب ويُجدَّد عند كل تفاعل. صفر = لم تنشط بعد. */
  activity: number;
};

/** وصف هدف اللصق: هل هو حقل نصّي، وأي المناطق تحتويه (من الأعمق إلى الأسطح). */
export type PasteTarget = {
  editable: boolean;
  containerIds: number[];
};

/**
 * يحدّد المنطقة الفائزة بلصقة واحدة، بالترتيب:
 * 1. هدف اللصق داخل عنصر منطقة مفعّلة ← تلك المنطقة (الأعمق أولاً).
 * 2. الهدف حقل نصّي (`input`/`textarea`/`contenteditable`) ← لا منطقة.
 * 3. وإلا ← صاحبة آخر نشاط (تفاعل، أو تركيب لمن لا تشترط تفاعلاً).
 * 4. لا منطقة مؤهّلة ← لا شيء.
 */
export function resolvePasteZone(
  zones: readonly PasteZoneState[],
  target: PasteTarget,
): number | null {
  const enabled = zones.filter((z) => z.enabled);

  for (const id of target.containerIds) {
    const inside = enabled.find((z) => z.id === id);
    if (inside) return inside.id;
  }

  if (target.editable) return null;

  let winner: PasteZoneState | null = null;
  for (const zone of enabled) {
    if (zone.activity <= 0) continue; // مسجّلة بلا نشاط: تشترط تفاعلاً ولم تحظَ به
    if (!winner || zone.activity > winner.activity) winner = zone;
  }
  return winner ? winner.id : null;
}

// ── التوجيه: السجلّ الحيّ ─────────────────────────────────────────

type RegisteredZone = PasteZoneState & {
  /** `null` = منطقة بلا عنصر تغطّي الشاشة كلها (سلوك `usePasteImageUpload` القديم). */
  element: () => HTMLElement | null;
  onFiles: (files: File[]) => void;
};

const registry = new Map<number, RegisteredZone>();
let zoneSeq = 0;
let activitySeq = 0;
let listening = false;
let lastDragTarget: EventTarget | null = null;

/** أنواع `input` التي لا تحمل نصّاً — لصق الصورة فيها ليس لصق نصّ. */
const NON_TEXT_INPUT_TYPES = new Set([
  "file", "checkbox", "radio", "button", "submit", "reset", "image", "range", "color",
]);

function isEditableElement(el: Element): boolean {
  if (el.tagName === "TEXTAREA") return true;
  if (el.tagName === "INPUT") {
    const type = ((el as HTMLInputElement).type || "text").toLowerCase();
    return !NON_TEXT_INPUT_TYPES.has(type);
  }
  return (el as HTMLElement).isContentEditable === true;
}

function describeTarget(node: EventTarget | null): PasteTarget {
  const containerIds: number[] = [];
  let editable = false;
  let el = node instanceof Element ? node : null;
  while (el) {
    if (!editable && isEditableElement(el)) editable = true;
    for (const zone of registry.values()) {
      if (zone.element() === el) containerIds.push(zone.id);
    }
    el = el.parentElement;
  }
  return { editable, containerIds };
}

function handleDocumentPaste(e: ClipboardEvent): void {
  if (registry.size === 0) return;
  const files = extractImageFilesFromClipboard(e);
  if (files.length === 0) return; // لصق نصّ عادي: لا نلمسه
  const winnerId = resolvePasteZone([...registry.values()], describeTarget(e.target));
  if (winnerId === null) return;
  e.preventDefault();
  registry.get(winnerId)?.onFiles(files);
}

/** نقرة/تركيز/سحب داخل منطقة يجعلها صاحبة آخر نشاط، فتفوز باللصقة التالية. */
function markInteraction(e: Event): void {
  if (registry.size === 0) return;
  if (e.type === "dragover") {
    if (e.target === lastDragTarget) return; // السحب يطلق عشرات الأحداث فوق العنصر ذاته
    lastDragTarget = e.target;
  }
  const { containerIds } = describeTarget(e.target);
  for (const id of containerIds) {
    const zone = registry.get(id);
    if (zone?.enabled) {
      zone.activity = ++activitySeq;
      return;
    }
  }
}

function attachListeners(): void {
  if (listening || typeof document === "undefined") return;
  document.addEventListener("paste", handleDocumentPaste);
  document.addEventListener("pointerdown", markInteraction, true);
  document.addEventListener("focusin", markInteraction, true);
  document.addEventListener("dragover", markInteraction, true);
  listening = true;
}

function detachListeners(): void {
  if (!listening) return;
  document.removeEventListener("paste", handleDocumentPaste);
  document.removeEventListener("pointerdown", markInteraction, true);
  document.removeEventListener("focusin", markInteraction, true);
  document.removeEventListener("dragover", markInteraction, true);
  listening = false;
  lastDragTarget = null;
}

export type PasteZoneOptions = {
  enabled?: boolean;
  /** لصفوف متكرّرة: لا تستقبل لصقاً إلا بعد نقر/سحب داخلها، فلا تخطف لصقة الصفّ المجاور. */
  interactionRequired?: boolean;
};

/**
 * يسجّل منطقة لصق طوال فترة تركيب المكوّن. `ref` هو عنصر المنطقة، و`null` يعني
 * منطقة تغطّي الشاشة كلها (لا تفوز بالاحتواء، بل بترتيب التركيب/التفاعل).
 */
export function usePasteZone(
  ref: RefObject<HTMLElement | null> | null,
  onFiles: (files: File[]) => void,
  options: PasteZoneOptions = {},
): void {
  const { enabled = true, interactionRequired = false } = options;
  // المعالج يُقرأ من `ref` وقت اللصق، فلا يُعاد تسجيل المنطقة عند كل رسم —
  // وإلا قفزت إلى رأس ترتيب النشاط مع كل إعادة رسم وسرقت اللصقة من نافذة فوقها.
  const onFilesRef = useRef(onFiles);
  useEffect(() => {
    onFilesRef.current = onFiles;
  });

  useEffect(() => {
    if (!enabled) return;
    const id = ++zoneSeq;
    registry.set(id, {
      id,
      enabled: true,
      interactionRequired,
      activity: interactionRequired ? 0 : ++activitySeq,
      element: () => ref?.current ?? null,
      onFiles: (files) => onFilesRef.current(files),
    });
    attachListeners();
    return () => {
      registry.delete(id);
      if (registry.size === 0) detachListeners();
    };
  }, [enabled, interactionRequired, ref]);
}

/**
 * يلتقط لصق صورة من الحافظة طوال فترة تركيب المكوّن (أو حين `enabled`) ويمرّرها
 * إلى `onFiles` — نفس مسار معالجة الملفات المُختارة يدوياً عبر `<input type="file">`.
 * غلافٌ رفيع فوق `usePasteZone` بمنطقة تغطّي الشاشة كلها: الشاشات القائمة تحتفظ
 * بسلوك «Ctrl+V في أي مكان»، وتدخل تلقائياً في قاعدة الفائز الواحد.
 */
export function usePasteImageUpload(onFiles: (files: File[]) => void, enabled: boolean = true): void {
  usePasteZone(null, onFiles, { enabled });
}
