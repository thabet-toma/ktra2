import { useState, useCallback, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

type ResolveValue = 'confirm' | 'cancel';

type Props = {
  productName: string;
  cachedQuantity: string;
  lastUpdated: string;
  onResolve: (value: ResolveValue) => void;
};

function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return 'منذ لحظات';
  if (diff < 3600) return `منذ ${Math.floor(diff / 60)} دقيقة`;
  if (diff < 86400) return `منذ ${Math.floor(diff / 3600)} ساعة`;
  return `منذ ${Math.floor(diff / 86400)} يوم`;
}

export default function StaleDataConfirm({
  productName, cachedQuantity, lastUpdated, onResolve,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onResolve('cancel');
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
      onClick={(e) => { if (e.target === e.currentTarget) onResolve('cancel'); }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="stale-confirm-title"
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6"
      >
        <div className="flex items-center gap-3 mb-4">
          <span className="text-2xl">⚠️</span>
          <h2 id="stale-confirm-title" className="text-lg font-bold text-gray-800">تحذير</h2>
        </div>
        <div className="text-sm text-gray-600 space-y-2 mb-6">
          <p>
            كمية المنتج «<strong>{productName}</strong>» المعروضة (<strong>{cachedQuantity}</strong>)
            من cache آخر تحديث: <strong>{relativeTime(lastUpdated)}</strong>.
          </p>
          <p className="font-medium text-amber-700">
            قد لا تكون الكمية الفعلية الآن متاحة. تأكد فعلياً (أو تأخر حتى يعود الاتصال) قبل المتابعة.
          </p>
        </div>
        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={() => onResolve('cancel')}
            className="px-4 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50"
          >
            إلغاء
          </button>
          <button
            type="button"
            onClick={() => onResolve('confirm')}
            className="px-4 py-2 rounded-lg bg-amber-600 text-white text-sm hover:bg-amber-700"
          >
            أفهم وأستمر
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function useStaleConfirm() {
  const [pending, setPending] = useState<{
    productName: string;
    cachedQuantity: string;
    lastUpdated: string;
  } | null>(null);
  const resolveRef = useRef<((value: ResolveValue) => void) | null>(null);

  const confirm = useCallback(async (
    productName: string,
    cachedQuantity: string,
    lastUpdated: string,
  ): Promise<'confirm' | 'cancel'> => {
    return new Promise((resolve) => {
      setPending({ productName, cachedQuantity, lastUpdated });
      resolveRef.current = resolve;
    });
  }, []);

  const handleResolve = useCallback((value: ResolveValue) => {
    resolveRef.current?.(value);
    resolveRef.current = null;
    setPending(null);
  }, []);

  const modal = pending ? (
    <StaleDataConfirm
      productName={pending.productName}
      cachedQuantity={pending.cachedQuantity}
      lastUpdated={pending.lastUpdated}
      onResolve={handleResolve}
    />
  ) : null;

  return { confirm, modal };
}
