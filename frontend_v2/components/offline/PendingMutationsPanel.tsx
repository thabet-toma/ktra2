import { useState, useEffect, useCallback } from 'react';
import { AseelSidePanel } from '../aseel/AseelSidePanel';
import db, { type MutationEntry } from '../../services/offline/db';

export default function PendingMutationsPanel() {
  const [open, setOpen] = useState(false);
  const [mutations, setMutations] = useState<MutationEntry[]>([]);

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

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors"
        aria-label={`العملية المعلقة: ${pendingCount + failedCount}`}
      >
        <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        {(pendingCount + failedCount) > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center font-bold">
            {pendingCount + failedCount}
          </span>
        )}
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
