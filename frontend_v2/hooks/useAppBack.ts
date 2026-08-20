import { useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { historyCanGoBack, resolveBackTarget, type BackTarget } from '../utils/backTarget';
import { uiLog } from '../utils/uiLog';

export interface AppBack extends BackTarget {
  /** يُنفّذ الرجوع: سابقةٌ داخل التطبيق، أو انتقالٌ إلى `path`. */
  go: () => void;
}

/**
 * زرّ رجوعٍ لا يكذب: يرجع حين توجد سابقة، وينتقل إلى وجهةٍ مسمّاة حين لا توجد
 * (تبويبٌ فُتح على المستند مباشرةً). القاعدة في `utils/backTarget.ts`.
 *
 * @param listPath  مسار قائمة الشاشة الحالية (`VIEW_PATHS[activeView]`).
 * @param listLabel اسم الشاشة الحالية (`VIEW_LABELS[activeView]`).
 */
export function useAppBack(listPath?: string | null, listLabel?: string | null): AppBack {
  const navigate = useNavigate();
  const location = useLocation();

  const target = useMemo(() => {
    // `history.state` يُقرأ عند كل تغيّر مسار — `idx` يتقدّم مع كل دفعة.
    const canGoBack =
      typeof window !== 'undefined' && historyCanGoBack(window.history.state);
    return resolveBackTarget({
      canGoBack,
      currentPath: location.pathname,
      listPath,
      listLabel,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key, location.pathname, listPath, listLabel]);

  const go = useCallback(() => {
    if (target.kind === 'history') {
      uiLog.info('[Routing] back: history');
      navigate(-1);
      return;
    }
    uiLog.info('[Routing] back: fallback', target.path);
    navigate(target.path);
  }, [navigate, target]);

  return { ...target, go };
}
