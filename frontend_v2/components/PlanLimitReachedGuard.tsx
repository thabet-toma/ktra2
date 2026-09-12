import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';

import { PLAN_LIMIT_REACHED_EVENT, type PlanLimitReachedDetail } from '../utils/sessionEvents';

/**
 * 211-P — بلغتَ حدَّ خطّتك: تنبيهٌ يحمل رسالة الخادم حرفياً (لا إعادة صياغة)
 * مع طريقٍ فعليٍّ إلى «خطّتي»، بدل toast يقول «رقِّ الخطة» بلا وجهة.
 * على نمط `EngagementRevokedGuard` بالضبط — نفس الحوار المانع عبر `createPortal`.
 */
export const PlanLimitReachedGuard: React.FC = () => {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<PlanLimitReachedDetail | null>(null);

  useEffect(() => {
    const show = (event: Event) => setDetail((event as CustomEvent<PlanLimitReachedDetail>).detail);
    window.addEventListener(PLAN_LIMIT_REACHED_EVENT, show);
    return () => window.removeEventListener(PLAN_LIMIT_REACHED_EVENT, show);
  }, []);

  if (!detail) return null;

  return createPortal(
    <div
      dir="rtl"
      role="alertdialog"
      aria-modal="true"
      aria-label="بلغتَ حدَّ خطّتك"
      className="fixed inset-0 z-[100000] flex items-center justify-center bg-slate-950/60 p-4"
    >
      <div className="w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-2xl dark:bg-slate-900">
        <h2 className="text-xl font-black text-slate-900 dark:text-white">بلغتَ حدَّ خطّتك</h2>
        <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{detail.message}</p>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={() => { setDetail(null); navigate('/settings#my-plan'); }}
            className="flex-1 rounded-xl bg-blue-600 px-5 py-3 font-black text-white transition hover:bg-blue-700"
          >
            عرض خطّتي
          </button>
          <button
            type="button"
            onClick={() => setDetail(null)}
            className="flex-1 rounded-xl border border-slate-300 px-5 py-3 font-black text-slate-700 transition hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            إغلاق
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
};

export default PlanLimitReachedGuard;
