// services/autoDisableScheduler.ts
// معطَّل — Firestore tail غير مَدعوم في backend الحالي. راجع P-G لإزالة كاملة.
class AutoDisableScheduler {
    start() { /* no-op */ }
    stop() { /* no-op */ }
    getStatus() { return { isRunning: false, nextCheck: 'متوقف' }; }
    async manualCheck() { /* no-op */ }
}

export const autoDisableScheduler = new AutoDisableScheduler();
