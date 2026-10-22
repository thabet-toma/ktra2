/**
 * K2 — هيكل نوافذ الجرد الثلاث (`NewStocktakeModal`، `PostStocktakeModal`،
 * `StaleStocktakeModal`) في مكوّنٍ واحد: الطبقة، اللوحة، الرأس (أيقونة + عنوان +
 * إغلاقٌ اختياري)، ومكان التذييل. الحبس والتركيز الأوّل وعودة التركيز وEsc
 * كلّها في `useDialogFocusTrap` وحده — لا نسخةَ رابعة من القواعد.
 *
 * الفئات الافتراضية هي فئات نافذة التقادم؛ نافذة الترحيل تمرّر جسمها
 * (`bodyClassName`) ونافذة «جرد جديد» لوحتها وجسمها وطبقتها، فتبقى كلٌّ كما كانت.
 */
import React from 'react';
import { X } from 'lucide-react';
import { useDialogFocusTrap } from '../../hooks/useDialogFocusTrap';

export interface StocktakeDialogProps {
  title: string;
  titleId: string;
  /** يُستدعى بـEsc وبالنقر على الطبقة — لا يظهر زرّ إغلاق إلا إن طُلب. */
  onClose: () => void;
  busy?: boolean;
  /** «لاحقاً» في التذييل يكفي في نافذة التقادم — فلا زرَّ X في رأسها اليوم. */
  showCloseButton?: boolean;
  closeLabel?: string;
  closeTitle?: string;
  icon?: React.ReactNode;
  headerExtra?: React.ReactNode;
  /** الطبقة الافتراضية `z-[95]`؛ «جرد جديد» تمرّر `z-[90]` فتقع تحتها. */
  overlayClassName?: string;
  panelClassName?: string;
  bodyClassName?: string;
  footer: React.ReactNode;
  children: React.ReactNode;
}

export const StocktakeDialog: React.FC<StocktakeDialogProps> = ({
  title,
  titleId,
  onClose,
  busy = false,
  showCloseButton = true,
  closeLabel = 'إغلاق النافذة',
  closeTitle,
  icon,
  headerExtra,
  overlayClassName = '',
  panelClassName = 'max-w-md',
  bodyClassName = 'space-y-2 p-4 text-sm text-[var(--ktra-ink)]',
  footer,
  children,
}) => {
  const { ref: dialogRef, onKeyDown } = useDialogFocusTrap({
    onEscape: onClose,
    busy,
  });

  return (
    <div
      className={`ktra-overlay-mask fixed inset-0 ${overlayClassName || 'z-[95]'} flex items-center justify-center p-4`}
      dir="rtl"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className={`w-full overflow-hidden rounded-lg border border-[var(--ktra-border)] bg-[var(--ktra-panel)] shadow-xl ${panelClassName}`}
      >
        <div className="flex items-center gap-2 border-b border-[var(--ktra-border-soft)] px-4 py-3">
          {icon}
          <h2 id={titleId} className="min-w-0 flex-1 truncate font-bold text-[var(--ktra-ink)]">
            {title}
          </h2>
          {headerExtra}
          {showCloseButton && (
            <button
              type="button"
              className="ktra-iconbtn"
              onClick={onClose}
              disabled={busy}
              aria-label={closeLabel}
              title={closeTitle}
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className={bodyClassName}>{children}</div>

        <div className="flex justify-end gap-2 border-t border-[var(--ktra-border-soft)] bg-[var(--ktra-surface-2)] px-4 py-3">
          {footer}
        </div>
      </div>
    </div>
  );
};

export default StocktakeDialog;
