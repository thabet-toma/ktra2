import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

export type ConflictResolution = 'overwrite' | 'take_server' | 'manual_merge';

type Props = {
  localData: string;
  serverData: string;
  modelName: string;
  onResolve: (resolution: ConflictResolution) => void;
};

export default function SyncConflictModal({
  localData, serverData, modelName, onResolve,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onResolve('take_server');
    };
    document.addEventListener('keydown', handler);
    document.body.style.overflow = 'hidden';
    dialogRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [onResolve]);

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] bg-black/50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onResolve('take_server'); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="conflict-title"
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="bg-white rounded-xl shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col"
      >
        <div className="p-4 border-b">
          <h2 id="conflict-title" className="text-lg font-bold text-gray-800">
            تعارض في المزامنة — {modelName}
          </h2>
          <p className="text-sm text-gray-500 mt-1">هناك نسختان مختلفتان. اختر الإجراء المناسب.</p>
        </div>

        <div className="flex-1 overflow-auto grid grid-cols-2 gap-0">
          <div className="p-4 border-l border-gray-200 bg-gray-50">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">تعديلك المحلي</h3>
            <pre className="text-xs text-gray-600 whitespace-pre-wrap break-words max-h-60 overflow-auto">
              {localData}
            </pre>
          </div>
          <div className="p-4">
            <h3 className="text-sm font-semibold text-gray-700 mb-2">الـ Server الحالي</h3>
            <pre className="text-xs text-gray-600 whitespace-pre-wrap break-words max-h-60 overflow-auto">
              {serverData}
            </pre>
          </div>
        </div>

        <div className="p-4 border-t flex gap-3 justify-end flex-wrap">
          <button
            type="button"
            onClick={() => onResolve('take_server')}
            className="px-4 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50"
          >
            خذ نسخة الـ Server (تجاهل تعديلي)
          </button>
          <button
            type="button"
            onClick={() => onResolve('overwrite')}
            className="px-4 py-2 rounded-lg bg-amber-600 text-white text-sm hover:bg-amber-700"
          >
            احفظ نسختي (Overwrite)
          </button>
          <button
            type="button"
            onClick={() => onResolve('manual_merge')}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700"
          >
            دمج يدوي
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
