import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getMyPermissions } from '../services/permissionsApi';
import { clientLogger } from '../services/logger';

/**
 * T-PERM: صلاحيات المستخدم الحالي في الشركة النشطة — مصدر واحد تستهلكه الشاشات
 * لإخفاء ما لا يملكه (زر التراجع عن الترحيل، الحذف، الإعدادات…).
 *
 * الإخفاء **تجميل** لا حماية: كل إجراء محميّ مفروضٌ ثانيةً على الخادم
 * (core/access.py). إن تعذّر الجلب نُبقي `can()` مسموحة كي لا يتعطّل العمل —
 * الخادم سيرفض ما ليس مسموحاً على أي حال ويظهر خطؤه للمستخدم.
 */
interface PermissionsValue {
  role: string;
  isManager: boolean;
  permissions: Set<string>;
  /** هل يملك المستخدم هذه الصلاحية؟ */
  can: (key: string) => boolean;
  loading: boolean;
  reload: () => void;
}

const PermissionsContext = createContext<PermissionsValue | null>(null);

export const PermissionsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [role, setRole] = useState('');
  const [isManager, setIsManager] = useState(false);
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!localStorage.getItem('token')) return;
    setLoading(true);
    getMyPermissions()
      .then((res) => {
        if (cancelled) return;
        setRole(res.role);
        setIsManager(res.is_manager);
        setPermissions(new Set(res.permissions));
        setLoaded(true);
        clientLogger.info('permissions.loaded', { role: res.role, count: res.permissions.length });
      })
      .catch(() => {
        /* بلا صلاحيات محمّلة — لا نحجب شيئاً بالواجهة، الخادم يفرض */
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [tick]);

  const can = useCallback(
    (key: string) => (loaded ? permissions.has(key) : true),
    [loaded, permissions],
  );

  const reload = useCallback(() => setTick((t) => t + 1), []);

  const value = useMemo<PermissionsValue>(
    () => ({ role, isManager, permissions, can, loading, reload }),
    [role, isManager, permissions, can, loading, reload],
  );

  return <PermissionsContext.Provider value={value}>{children}</PermissionsContext.Provider>;
};

export function usePermissions(): PermissionsValue {
  const ctx = useContext(PermissionsContext);
  // غياب المزوّد (اختبارات/شاشات معزولة) ⇒ لا حجب بالواجهة.
  return (
    ctx ?? {
      role: '',
      isManager: false,
      permissions: new Set<string>(),
      can: () => true,
      loading: false,
      reload: () => {},
    }
  );
}
