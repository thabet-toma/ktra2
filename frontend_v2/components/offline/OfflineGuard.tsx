import type { ReactNode } from 'react';
import { useOnlineStatus } from '../../hooks/useOnlineStatus';

type Props = {
  /** Short label used as the aria-label of the disabled button (e.g. "ترحيل القيد"). */
  action: string;
  /** Set true if this action is OK to perform offline (rare — defaults to false). */
  allowedOffline?: boolean;
  /** Tooltip text shown on the disabled button. Falls back to a generic Arabic message. */
  warningMessage?: string;
  /** The button (or any node) to render. When offline, the wrapped node is hidden
   *  and replaced with a disabled stand-in showing the warning tooltip. */
  children: ReactNode;
};

/**
 * OfflineGuard — wraps a posting/critical action element. When offline, the
 * child is replaced with a disabled clone showing a red tooltip explaining
 * why. When online (or allowedOffline=true), the child is rendered as-is.
 *
 * Usage:
 *   <OfflineGuard action="ترحيل الفاتورة">
 *     <button onClick={post}>ترحيل</button>
 *   </OfflineGuard>
 *
 * Design note: the previous version wrapped children in an extra <button>,
 * which produces invalid HTML when the child is already a button. This
 * version uses an inline-block disabled stand-in with `pointer-events: none`
 * on the wrapped child and an absolute overlay carrying the tooltip.
 */
export default function OfflineGuard({
  action, allowedOffline, warningMessage, children,
}: Props) {
  const { online } = useOnlineStatus();

  if (online || allowedOffline) {
    return <>{children}</>;
  }

  return (
    <span
      className="relative group inline-block"
      role="group"
      aria-label={action}
    >
      <span
        aria-hidden="true"
        className="opacity-50 pointer-events-none select-none"
      >
        {children}
      </span>
      <span
        role="tooltip"
        className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2
                   bg-red-600 text-white text-xs rounded-lg px-3 py-1.5
                   whitespace-nowrap opacity-0 group-hover:opacity-100 group-focus-within:opacity-100
                   transition-opacity pointer-events-none z-50 shadow-lg"
      >
        {warningMessage || 'هذا الإجراء يتطلب اتصالاً بالإنترنت'}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-red-600" />
      </span>
    </span>
  );
}
