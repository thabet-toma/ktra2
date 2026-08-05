import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { ENGAGEMENT_REVOKED_EVENT } from '../../utils/sessionEvents';

/**
 * الشاشة 6 — إلغاء الارتباط أثناء العمل: حوار مانع ثم عودة للوحة الشركات.
 * لا يمسّ التوكن ولا يُخرج المحاسب من شركاته الأخرى (T7) — يوقف هذه الشركة فقط.
 */
export const EngagementRevokedGuard: React.FC<{ onReturn: () => void }> = ({ onReturn }) => {
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    const show = () => setBlocked(true);
    window.addEventListener(ENGAGEMENT_REVOKED_EVENT, show);
    return () => window.removeEventListener(ENGAGEMENT_REVOKED_EVENT, show);
  }, []);

  if (!blocked) return null;

  return createPortal(
    <div
      dir="rtl"
      role="alertdialog"
      aria-modal="true"
      aria-label="انتهى ارتباطك بهذه الشركة"
      className="fixed inset-0 z-[100000] flex items-center justify-center bg-slate-950/60 p-4"
    >
      <div className="w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-2xl dark:bg-slate-900">
        <h2 className="text-xl font-black text-slate-900 dark:text-white">انتهى ارتباطك بهذه الشركة</h2>
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          أُلغي أو عُلِّق ارتباطك، فسقط وصولك لبياناتها فوراً. بقية شركاتك لم تتأثر.
        </p>
        <button
          type="button"
          onClick={() => { setBlocked(false); onReturn(); }}
          className="mt-6 w-full rounded-xl bg-blue-600 px-5 py-3 font-black text-white"
        >
          العودة للوحة الشركات
        </button>
      </div>
    </div>,
    document.body,
  );
};

export default EngagementRevokedGuard;
