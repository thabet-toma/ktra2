import React, { useEffect, useRef } from 'react';
import { AlertTriangle, X } from 'lucide-react';

export interface ConfirmDialogProps {
  title?: string;
  message: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  /** نمط الخطر (أحمر) — للحذف والإجراءات غير القابلة للتراجع. */
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** حوار تأكيد موحّد (RTL) — بديل window.confirm لكل أزرار الحذف/الإجراءات الحساسة. */
export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  title, message, confirmText, cancelText, danger = true, onConfirm, onCancel,
}) => {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
      else if (e.key === 'Enter') onConfirm();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onConfirm, onCancel]);

  return (
    <div
      dir="rtl"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-[1000] p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white dark:bg-gray-800 shadow-2xl border border-gray-200 dark:border-gray-700 p-6"
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
      >
        <div className="flex items-start gap-3 mb-3">
          <div className={`p-2 rounded-lg ${danger ? 'bg-red-100 dark:bg-red-900/30' : 'bg-blue-100 dark:bg-blue-900/30'}`}>
            <AlertTriangle className={`w-5 h-5 ${danger ? 'text-red-600 dark:text-red-400' : 'text-blue-600 dark:text-blue-400'}`} />
          </div>
          <h3 className="text-lg font-bold flex-1 dark:text-white">{title || 'تأكيد'}</h3>
          <button onClick={onCancel} className="p-1 rounded-lg text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700" aria-label="إغلاق">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="text-sm text-gray-600 dark:text-gray-300 mb-6 whitespace-pre-line leading-relaxed pr-1">
          {message}
        </div>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-sm font-semibold rounded-lg border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            {cancelText || 'إلغاء'}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`px-4 py-2 text-sm font-bold text-white rounded-lg ${danger ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'}`}
          >
            {confirmText || (danger ? 'حذف' : 'تأكيد')}
          </button>
        </div>
      </div>
    </div>
  );
};
