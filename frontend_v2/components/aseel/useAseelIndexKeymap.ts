/**
 * N0-T7 — useAseelIndexKeymap
 * Aseel keyboard model for LIST/INDEX pages (not forms).
 * Different callbacks than form keymap:
 *   - F2: drillToLedger — حركات المحاسبة للسجل المحدَّد
 *   - F3: drillToStock — حركات المخازن
 *   - F4: showNotes — ملاحظات السجل
 *   - F5: sortBy, F6: search
 *   - Enter: openRecord — يفتح الـrecord في form mode
 *   - Ctrl+Home/End/PageUp/PageDown/Ins/Del: navigation
 * Reference: docs/aseel_reference/accounting.txt 48–69.
 */
import { useEffect, useRef } from 'react';
import { AseelKey, AseelKeymapHandlers, useAseelKeymap } from './useAseelKeymap';

export type AseelIndexKey =
  | 'F2' | 'F3' | 'F4' | 'F5' | 'F6'
  | 'Enter' | 'Escape' | 'AltF4'
  | 'CtrlHome' | 'CtrlEnd' | 'CtrlPageUp' | 'CtrlPageDown'
  | 'CtrlIns' | 'CtrlDel';

export type AseelIndexKeymapHandlers = Partial<Record<AseelIndexKey, () => void>>;

interface Options {
  enabled?: boolean;
}

export function useAseelIndexKeymap(
  handlers: AseelIndexKeymapHandlers,
  { enabled = true }: Options = {},
): void {
  const ref = useRef<AseelIndexKeymapHandlers>(handlers);
  ref.current = handlers;

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (e: KeyboardEvent) => {
      const h = ref.current;
      const fire = (key: AseelIndexKey) => {
        const fn = h[key];
        if (fn) {
          e.preventDefault();
          fn();
        }
      };

      // Alt+F4
      if (e.altKey && e.key === 'F4') return fire('AltF4');

      // Ctrl+nav
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

      // F-keys
      switch (e.key) {
        case 'F2': return fire('F2');
        case 'F3': return fire('F3');
        case 'F4': return fire('F4');
        case 'F5': return fire('F5');
        case 'F6': return fire('F6');
        case 'Enter': return fire('Enter');
        case 'Escape': return fire('Escape');
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enabled]);
}
