import { useState, useEffect, useCallback } from 'react';
import { AseelSidePanel } from '../aseel/AseelSidePanel';
import db, { type MutationEntry } from '../../services/offline/db';
import { useOnlineStatus } from '../../hooks/useOnlineStatus';

export default function PendingMutationsPanel() {
  const [open, setOpen] = useState(false);
  const [mutations, setMutations] = useState<MutationEntry[]>([]);
  const { online } = useOnlineStatus();

  const refresh = useCallback(async () => {
    const items = await db.mutation_queue
      .where('status')
      .anyOf(['pending', 'syncing', 'failed'])
      .toArray();
    setMutations(items);
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const pendingCount = mutations.filter((m) => m.status === 'pending').length;
  const failedCount = mutations.filter((m) => m.status === 'failed').length;
  const syncingCount = mutations.filter((m) => m.status === 'syncing').length;

  const retryMutation = async (id: number) => {
    await db.mutation_queue.update(id, { status: 'pending', error: undefined });
    refresh();
    if ('serviceWorker' in navigator && 'sync' in (navigator.serviceWorker as any)) {
      (navigator.serviceWorker as any).ready.then((reg: any) => {
        reg.sync?.register('ktra-mutations').catch(() => {});
      });
    }
  };

  const deleteMutation = async (id: number) => {
    await db.mutation_queue.delete(id);
    refresh();
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case 'pending': return 'bg-yellow-100 text-yellow-700';
      case 'syncing': return 'bg-blue-100 text-blue-700';
      case 'failed': return 'bg-red-100 text-red-700';
      default: return 'bg-gray-100 text-gray-700';
    }
  };

  let chipBg = "bg-green-100 text-green-800 dark:bg-green-950/20 dark:text-green-400";
  let chipText = "مزامنة نشطة / متصل";
  let chipDot = "bg-green-500";

  if (!online && pendingCount === 0 && failedCount === 0 && syncingCount === 0) {
    chipBg = "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400";
    chipText = "منقطع / أوفلاين";
    chipDot = "bg-gray-400";
  } else if (failedCount > 0) {
    chipBg = "bg-red-100 text-red-800 dark:bg-red-950/20 dark:text-red-400";
    chipText = `فشل: ${failedCount}`;
    chipDot = "bg-red-500";
  } else if (syncingCount > 0) {
    chipBg = "bg-blue-100 text-blue-800 dark:bg-blue-950/20 dark:text-blue-400";
    chipText = "جاري المزامنة...";
    chipDot = "bg-blue-500 animate-pulse";
  } else if (pendingCount > 0) {
    chipBg = "bg-yellow-100 text-yellow-800 dark:bg-yellow-950/20 dark:text-yellow-400";
    chipText = `معلق: ${pendingCount}`;
    chipDot = "bg-yellow-500";
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold transition-all border border-transparent hover:border-gray-200 dark:hover:border-gray-700 ${chipBg}`}
        aria-label={`حالة المزامنة: ${chipText}`}
      >
        <span className={`w-2 h-2 rounded-full ${chipDot}`} />
        <span>{chipText}</span>
      </button>

      <AseelSidePanel open={open} onClose={() => setOpen(false)} title="العمليات المعلقة" width={420}>
        {mutations.length === 0 ? (
          <div className="text-center text-gray-400 py-12 text-sm">لا توجد عمليات معلقة</div>
        ) : (
          <div className="space-y-2">
            {mutations.map((m) => (
              <div key={m.id} className="border rounded-lg p-3 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className={`px-2 py-0.5 rounded-full font-medium ${statusBadge(m.status)}`}>
                    {m.status === 'pending' ? 'معلق' : m.status === 'syncing' ? 'قيد المزامنة' : 'فشل'}
                  </span>
                  <span className="text-gray-400">{new Date(m.created_at).toLocaleString('ar-SA')}</span>
                </div>
                <div className="text-gray-600">
                  <span className="font-medium">{m.method}</span>
                  <span className="mr-1">{m.endpoint}</span>
                </div>
                {m.status === 'failed' && (
                  <div className="flex gap-2 mt-2">
                    <button
                      type="button"
                      onClick={() => retryMutation(m.id!)}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      إعادة المحاولة
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteMutation(m.id!)}
                      className="text-red-600 hover:underline text-xs"
                    >
                      حذف
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </AseelSidePanel>
    </>
  );
}
