/**
 * SAVE-3 — حوار إدخال قيمة واحدة، بديل `window.prompt`.
 *
 * `prompt` المتصفح لا يُنسَّق، ولا يحترم RTL، ولا يفرّق بين نصّ ورقم، ويوقف
 * الصفحة كلها — وكانت تُستعمل في مسارات مالية (ربط قيد يومية، عدد شيكات).
 * هذا الحوار يقابله بالسلوك نفسه: قيمة واحدة، تأكيد أو إلغاء.
 *
 * `useConfirm` لا يصلح هنا لأنه يعيد boolean بلا قيمة مُدخَلة، وبناء موفّر
 * (Provider) ثانٍ لأجل ثلاثة مواضع مبالغة — فالمكوّن مضبوط بحالة محلّية عند
 * مستدعيه، تماماً كنمط `RejectReasonModal` المتّبع في هذا المستودع.
 */
import React, { useEffect, useState } from 'react';

interface PromptDialogProps {
  isOpen: boolean;
  title: string;
  /** نصّ يشرح المطلوب فوق الحقل. */
  message: string;
  /** القيمة الابتدائية في الحقل عند كل فتح. */
  initialValue?: string;
  type?: 'text' | 'number';
  confirmText?: string;
  onCancel: () => void;
  onSubmit: (value: string) => void;
}

export const PromptDialog: React.FC<PromptDialogProps> = ({
  isOpen,
  title,
  message,
  initialValue = '',
  type = 'text',
  confirmText = 'تأكيد',
  onCancel,
  onSubmit,
}) => {
  const [value, setValue] = useState(initialValue);

  // كل فتحة تبدأ من القيمة الابتدائية، لا من بقايا الفتحة السابقة.
  useEffect(() => {
    if (isOpen) setValue(initialValue);
  }, [isOpen, initialValue]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(value);
  };

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg bg-[var(--color-surface)] p-5 shadow-xl">
        <h2 className="mb-2 text-lg font-bold text-[var(--color-text)]">{title}</h2>
        <p className="mb-3 whitespace-pre-line text-sm text-[var(--color-text-muted)]">{message}</p>
        <form onSubmit={submit} className="space-y-4">
          <input
            type={type}
            value={value}
            autoFocus
            onChange={(e) => setValue(e.target.value)}
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-[var(--color-text)]"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="rounded-md bg-[var(--color-surface-3)] px-4 py-2 text-[var(--color-text)]"
            >
              إلغاء
            </button>
            <button
              type="submit"
              className="rounded-md bg-[var(--color-primary)] px-4 py-2 text-white"
            >
              {confirmText}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default PromptDialog;
