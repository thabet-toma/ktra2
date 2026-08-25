/**
 * M0-T5 + N0-T6 — useKitKeymap
 * Kit keyboard model. NON-BLOCKING by design:
 *  - Function keys (F2..F6, F12), Enter-as-save (F12), Escape and Alt+F4
 *    always fire (these never conflict with text entry).
 *  - `+` / `*` / `-` (index lookup / next / prev) only fire when the user is
 *    NOT typing into a free-text field, OR when the focused field explicitly
 *    opts in via `data-ktra-key="1"` (numeric/index fields). This prevents
 *    hijacking normal typing — exactly the Kit behaviour.
 *  - The whole map is suppressed when `enabled === false` (pass false while a
 *    modal/picker is open so it owns the keyboard).
 *  - N0-T6 additions: Ctrl+Home/End/PageUp/PageDown (nav), Ctrl+Ins (add),
 *    Ctrl+Del (delete), Alt+F4 (exit).
 * Reference: docs/aseel_reference/invoices.txt 193–200; shipments.txt 114–121;
 *            invoices.txt 207–229.
 */
import { useEffect, useRef } from 'react';

export type KitKey =
  | 'F1' | 'F2' | 'F3' | 'F4' | 'F5' | 'F6' | 'F12'
  | 'Escape' | 'AltF4' | 'plus' | 'star' | 'minus'
  | 'CtrlHome' | 'CtrlEnd' | 'CtrlPageUp' | 'CtrlPageDown'
  | 'CtrlIns' | 'CtrlDel';

export type KitKeymapHandlers = Partial<Record<KitKey, () => void>>;

interface Options {
  enabled?: boolean;
}

function isEditableTextTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  if (el.isContentEditable) return true;
  if (el instanceof HTMLTextAreaElement) return true;
  if (el instanceof HTMLInputElement) {
    const t = (el.type || 'text').toLowerCase();
    // 'number' is included so '-' inside a numeric input lets the user type a
    // negative value instead of being captured as a "prev record" shortcut.
    // Numeric fields that DO want Kit +/- semantics opt in with data-ktra-key="1".
    return ['text', 'search', 'email', 'url', 'tel', 'password', 'number'].includes(t);
  }
  return false;
}

export function useKitKeymap(
  handlers: KitKeymapHandlers,
  { enabled = true }: Options = {},
): void {
  const ref = useRef<KitKeymapHandlers>(handlers);
  ref.current = handlers;

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (e: KeyboardEvent) => {
      const h = ref.current;
      const fire = (key: KitKey) => {
        const fn = h[key];
        if (fn) {
          e.preventDefault();
          fn();
        }
      };

      // Alt+F4 — exit
      if (e.altKey && e.key === 'F4') return fire('AltF4');

      // Ctrl+nav keys
      if (e.ctrlKey) {
        switch (e.key) {
          case 'Home': return fire('CtrlHome');
          case 'End': return fire('CtrlEnd');
          case 'PageUp': return fire('CtrlPageUp');
          case 'PageDown': return fire('CtrlPageDown');
          case 'Insert': return fire('CtrlIns');
          case 'Delete': return fire('CtrlDel');
        }
      }

      /* المفاتيح الوظيفية هنا **مجرّدة**: `F2` لا `Ctrl+F2`. بلا هذا الحارس كان
         الوتر يُفهم مفتاحاً مفرداً — فـ`Ctrl+F1` (طيّ شريط الوصول السريع) يفتح
         بحث المستند معه، و`Ctrl+F5` يُطلق إجراء `F5` مع إعادة تحميل المتصفّح. */
      if (e.ctrlKey || e.metaKey) return;

      switch (e.key) {
        case 'F1': return fire('F1');
        case 'F2': return fire('F2');
        case 'F3': return fire('F3');
        case 'F4': return fire('F4');
        case 'F5': return fire('F5');
        case 'F6': return fire('F6');
        case 'F12': return fire('F12');
        case 'Escape': return fire('Escape');
      }

      // +/*/- — index lookup & record stepping
      const target = e.target as HTMLElement | null;
      const optedIn = target?.getAttribute?.('data-ktra-key') === '1';
      const typing = isEditableTextTarget(target);
      if (typing && !optedIn) return;

      if (e.key === '+') return fire('plus');
      if (e.key === '*') return fire('star');
      if (e.key === '-') return fire('minus');
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enabled]);
}
