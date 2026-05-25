import { createPortal } from 'react-dom';

type Props = {
  message: string;
  type: 'info' | 'warn' | 'error';
};

export default function StatusMessage({ message, type }: Props) {
  const bg = type === 'error' ? 'bg-red-500' : type === 'warn' ? 'bg-yellow-500' : 'bg-blue-500';

  return createPortal(
    <div
      role="status"
      aria-live="polite"
      className={`fixed bottom-4 right-4 z-50 ${bg} text-white px-4 py-2 rounded-lg shadow-lg text-sm max-w-sm`}
    >
      {message}
    </div>,
    document.body,
  );
}
