import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { getMyPermissions, setMyUiMode } from '../services/permissionsApi';
import { clientLogger } from '../services/logger';
import { useToast } from './ToastContext';
import { resolveTenantId } from '../utils/tenantContext';
import { DEFAULT_COMPANY_TEMPLATE } from '../utils/companyTemplates';
import {
  DEFAULT_UI_MODE,
  normalizeUiMode,
  readUiModeCache,
  writeUiModeCache,
  type UiMode,
} from '../utils/uiMode';

/**
 * T-PERM: صلاحيات المستخدم الحالي في الشركة النشطة — مصدر واحد تستهلكه الشاشات
 * لإخفاء ما لا يملكه (زر التراجع عن الترحيل، الحذف، الإعدادات…).
 *
 * الإخفاء **تجميل** لا حماية: كل إجراء محميّ مفروضٌ ثانيةً على الخادم
 * (core/access.py). إن تعذّر الجلب نُبقي `can()` مسموحة كي لا يتعطّل العمل —
 * الخادم سيرفض ما ليس مسموحاً على أي حال ويظهر خطؤه للمستخدم.
 *
 * THA-110: وضع العرض (`uiMode`) يركب هذه الحمولة نفسها **قصداً بلا سياق رابع**:
 * القيمة تصل مع `/permissions/me` المحمَّلة عند الإقلاع أصلاً، ومستهلكها الوحيد
 * هو الشريط الجانبي — سياقٌ مستقل كان سيكرّر طلب الإقلاع بلا مقابل.
 */
interface PermissionsValue {
  role: string;
  isManager: boolean;
  permissions: Set<string>;
  /** أعلام ترخيص الوحدات لهذه الشركة — تفشل مغلقة (غياب العَلَم = مطفأة). */
  modules: Record<string, boolean>;
  /** ISSUE #51: قالب الشركة النشطة — يحرس به `TEMPLATE_HIDDEN_VIEWS`. `general` افتراضياً. */
  template: string;
  /** هل يملك المستخدم هذه الصلاحية؟ */
  can: (key: string) => boolean;
  /** THA-110: وضع عرض الواجهة — تفضيل عرض لا صلاحية. */
  uiMode: UiMode;
  setUiMode: (mode: UiMode) => void;
  loading: boolean;
  reload: () => void;
}

const PermissionsContext = createContext<PermissionsValue | null>(null);

const hasToken = (): boolean => {
  try { return !!localStorage.getItem('token'); } catch { return false; }
};

export const PermissionsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [role, setRole] = useState('');
  const [isManager, setIsManager] = useState(false);
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [modules, setModules] = useState<Record<string, boolean>>({});
  const [template, setTemplate] = useState<string>(DEFAULT_COMPANY_TEMPLATE);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const toast = useToast();

  // الشركة النشطة تُثبَّت عند التركيب؛ تبديل الشركة يعيد تحميل الصفحة بالكامل
  // (CompanyContext.switchCompany) فيُعاد تركيب المزوّد بالشركة الجديدة.
  const tenantId = resolveTenantId();
  // cache الشركة أولاً كي تُطبَّق القائمة الصحيحة قبل رد الخادم بلا وميض.
  const [uiMode, setUiModeState] = useState<UiMode>(() => readUiModeCache(tenantId));

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
        setModules(res.modules || {});
        setTemplate(res.template || DEFAULT_COMPANY_TEMPLATE);
        // الخادم مصدر الحقيقة: قيمته تحسم الـcache (وحقلٌ غائب ⇒ «متقدم»).
        const serverMode = normalizeUiMode(res.ui_mode);
        setUiModeState(serverMode);
        writeUiModeCache(tenantId, serverMode);
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
  }, [tick, tenantId]);

  const can = useCallback(
    (key: string) => (loaded ? permissions.has(key) : true),
    [loaded, permissions],
  );

  /**
   * تبديل تفاؤلي: الحالة والـcache فوراً ثم الحفظ الخادمي في الخلفية. فشل
   * الحفظ **لا يرتدّ تحت يد المستخدم** — الوضع يعمل في هذا المتصفح ويُخبَر
   * بتحذير واحد أن الحفظ عبر الأجهزة لم يتم. هذا مسار الدور `viewer` المعروف:
   * ممنوعٌ من كل كتابة على المنصة، فيتصرّف كالزائر بلا أن ينكسر شيء.
   */
  const setUiMode = useCallback((mode: UiMode) => {
    setUiModeState(mode);
    writeUiModeCache(tenantId, mode);
    clientLogger.info('ui_mode.set', { uiMode: mode });
    if (!hasToken()) return; // بلا جلسة — cache محلي فقط، ولا طلب يُرسل
    void setMyUiMode(mode).catch((e) => {
      clientLogger.warn('ui_mode.persist_failed', { error: String(e) });
      // نبرة «معلومة» لا «خطأ»: لم ينكسر شيء — الوضع مطبَّق، والحفظ وحده تعذّر.
      toast('تم تطبيق الوضع في هذا المتصفح فقط — لم يُحفَظ عبر الأجهزة.', 'info');
    });
  }, [tenantId, toast]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  const value = useMemo<PermissionsValue>(
    () => ({ role, isManager, permissions, modules, template, can, uiMode, setUiMode, loading, reload }),
    [role, isManager, permissions, modules, template, can, uiMode, setUiMode, loading, reload],
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
      modules: {},
      template: DEFAULT_COMPANY_TEMPLATE,
      can: () => true,
      uiMode: DEFAULT_UI_MODE,
      setUiMode: () => {},
      loading: false,
      reload: () => {},
    }
  );
}
