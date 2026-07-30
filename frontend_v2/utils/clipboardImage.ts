/**
 * لصق صورة من الحافظة (Ctrl+V) في حقول رفع الصور — بديل عن رفع الملف يدوياً فقط.
 */
import { useEffect } from "react";

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

/**
 * يلتقط لصق صورة من الحافظة طوال فترة تركيب المكوّن (أو حين `enabled`) ويمرّرها
 * إلى `onFiles` — نفس مسار معالجة الملفات المُختارة يدوياً عبر `<input type="file">`.
 */
export function usePasteImageUpload(onFiles: (files: File[]) => void, enabled: boolean = true): void {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: ClipboardEvent) => {
      const files = extractImageFilesFromClipboard(e);
      if (files.length > 0) {
        e.preventDefault();
        onFiles(files);
      }
    };
    document.addEventListener("paste", handler);
    return () => document.removeEventListener("paste", handler);
  }, [enabled, onFiles]);
}
