/**
 * N0-T8 — useKitFieldShortcuts
 * Field-level keyboard helpers يُستدعى داخل input handlers أو عبر
 * data-ktra-field attribute:
 *   - data-ktra-field="date" + * ⇒ +1 day; - ⇒ −1 day
 *   - data-ktra-field="remaining-amount" + Space ⇒ autofill with computed remaining
 *   - data-ktra-field="voucher-link" + * ⇒ open attached voucher
 *   - data-ktra-field="account-number" + * ⇒ next account; - ⇒ prev
 *   - data-ktra-field="item-number" + + (alone) ⇒ next available number; +<num> ⇒ next after num
 * Reference: docs/aseel_reference/invoices.txt 38–43, 62; inventory.txt 30–32.
 */
import { useEffect, useRef } from 'react';

export type FieldShortcutAction =
  | 'date-next'      // * on date field
  | 'date-prev'      // - on date field
  | 'remaining-fill' // Space on remaining-amount
  | 'voucher-open'   // * on voucher-link
  | 'account-next'   // * on account-number
  | 'account-prev'   // - on account-number
  | 'item-next'      // + on item-number
  | 'item-next-after'; // +<num> on item-number

export type FieldShortcutHandlers = Partial<Record<FieldShortcutAction, () => void>>;

interface Options {
  enabled?: boolean;
}

export function useKitFieldShortcuts(
  handlers: FieldShortcutHandlers,
  { enabled = true }: Options = {},
): void {
  const ref = useRef<FieldShortcutHandlers>(handlers);
  ref.current = handlers;

  useEffect(() => {
    if (!enabled) return;

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;

      const field = target.getAttribute?.('data-ktra-field');
      if (!field) return;

      const h = ref.current;
      const fire = (action: FieldShortcutAction) => {
        const fn = h[action];
        if (fn) {
          e.preventDefault();
          fn();
        }
      };

      // Date field: * = +1 day, - = -1 day
      if (field === 'date') {
        if (e.key === '*') return fire('date-next');
        if (e.key === '-') return fire('date-prev');
      }

      // Remaining amount: Space = autofill
      if (field === 'remaining-amount' && e.key === ' ') return fire('remaining-fill');

      // Voucher link: * = open attached voucher
      if (field === 'voucher-link' && e.key === '*') return fire('voucher-open');

      // Account number: * = next, - = prev
      if (field === 'account-number') {
        if (e.key === '*') return fire('account-next');
        if (e.key === '-') return fire('account-prev');
      }

      // Item number: + = next available
      if (field === 'item-number' && e.key === '+') return fire('item-next');
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enabled]);
}
