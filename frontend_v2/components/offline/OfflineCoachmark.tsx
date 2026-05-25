import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

const LS_KEY = 'offline-coachmark-dismissed';

export default function OfflineCoachmark() {
  const [show, setShow] = useState(false);
  // Track «don't show again» preference in local UI state until dismiss.
  const [dontShowAgain, setDontShowAgain] = useState(true);

  useEffect(() => {
    if (localStorage.getItem(LS_KEY)) return;
    const handler = () => {
      if (!navigator.onLine) setShow(true);
    };
    window.addEventListener('offline', handler);
    return () => window.removeEventListener('offline', handler);
  }, []);

  // Only persist the «dismissed» flag at close time, honoring the user's
  // checkbox choice. Earlier version set LS unconditionally on first offline
  // event, then offered a checkbox whose semantics were inverted — by the
  // time the user could uncheck it, the flag was already saved.
  const dismiss = () => {
    if (dontShowAgain) localStorage.setItem(LS_KEY, '1');
    setShow(false);
  };

  if (!show) return null;

  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-black/40 flex items-center justify-center p-4">
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 relative"
        role="dialog"
        aria-modal="true"
        aria-labelledby="coachmark-title"
      >
        <h2 id="coachmark-title" className="text-lg font-bold text-gray-800 mb-3">
          أنت الآن بدون اتصال
        </h2>
        <p className="text-sm font-semibold text-gray-600 mb-3">ماذا يعمل / لا يعمل؟</p>
        <div className="space-y-2 text-sm mb-4">
          <div className="flex items-center gap-2 text-green-700">
            <span>✅</span>
            <span>تصفح القوائم والفواتير القديمة</span>
          </div>
          <div className="flex items-center gap-2 text-green-700">
            <span>✅</span>
            <span>إنشاء مسوّدات (تُرسَل عند العودة)</span>
          </div>
          <div className="flex items-center gap-2 text-red-600">
            <span>❌</span>
            <span>ترحيل القيود/الفواتير</span>
          </div>
          <div className="flex items-center gap-2 text-red-600">
            <span>❌</span>
            <span>توليد التقارير الضريبية</span>
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-500 mb-4">
          <input
            type="checkbox"
            checked={dontShowAgain}
            onChange={(e) => setDontShowAgain(e.target.checked)}
          />
          لا تعرض هذا مرة أخرى
        </label>
        <button
          type="button"
          onClick={dismiss}
          className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm hover:bg-blue-700"
        >
          فهمت
        </button>
      </div>
    </div>,
    document.body,
  );
}
