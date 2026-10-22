/**
 * حصر التركيز في نافذةٍ حوارية — القواعد الثلاث نفسها في كل نافذة في النظام:
 * التركيز الأوّل عند الفتح، وإعادته إلى ما كان عليه عند الإغلاق، وTab/Shift+Tab
 * يدوران داخل النافذة. Esc يُغلق عبر `onEscape` ما لم يمنعه عنصرٌ داخلي
 * (`defaultPrevented` — منتقي التصنيف يستهلكه ليغلق لوحته وحده) أو تكن النافذة
 * مشغولةً بعمليةٍ لا يجوز قطعها.
 */
import React, { useEffect, useRef } from 'react';

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export interface UseDialogFocusTrapOptions {
  /** يُستدعى عند Esc بعد التأكد أن لا عنصراً داخلياً استهلكه وأن النافذة ليست مشغولة. */
  onEscape?: () => void;
  /** عمليةٌ جارية (حفظ/إنشاء/ترحيل): Esc لا يغلق والنافذة في منتصفها. */
  busy?: boolean;
}

export function useDialogFocusTrap<T extends HTMLElement = HTMLDivElement>({
  onEscape,
  busy = false,
}: UseDialogFocusTrapOptions = {}) {
  const ref = useRef<T>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    restoreFocusRef.current = document.activeElement as HTMLElement | null;
    const frame = requestAnimationFrame(() => {
      const first = ref.current?.querySelector(FOCUSABLE) as HTMLElement | null;
      (first ?? ref.current)?.focus();
    });
    return () => {
      cancelAnimationFrame(frame);
      restoreFocusRef.current?.focus?.();
    };
  }, []);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      if (event.defaultPrevented || busy) return;
      event.preventDefault();
      onEscape?.();
      return;
    }
    if (event.key !== 'Tab') return;
    const nodes = (Array.from(
      ref.current?.querySelectorAll(FOCUSABLE) ?? [],
    ) as HTMLElement[]).filter((node) => node.offsetParent !== null);
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return { ref, onKeyDown };
}
