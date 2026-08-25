import React, { createContext, useContext, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { clientLogger } from '../services/logger';
import { apiPatchObject } from '../services/restApi';
import { getTenantSettings, invalidateTenantSettings } from '../services/tenantSettingsApi';
import { resolveTenantId } from '../utils/tenantContext';

/**
 * تفضيل المظهر — حجم الخط ونوعه. مصدر الحقيقة هو الخادم (TenantSettings) لكل
 * شركة: يُحفَظ per-company فيثبت عبر الأجهزة ولا يرجع للافتراضي عند إعادة فتح
 * الموقع، ومعزول لكل شركة لا للمنصة كلها. يُبقى cache محلي مفتاحه رقم الشركة
 * للتطبيق الفوري قبل رد الخادم. يُطبَّق بضبط متغيّرات CSS على <html> فيسري على
 * الواجهة العامة (rem مرتكز على html) وسكِن «الأصيل» (--ktra-*) معاً.
 * يُضبط من صفحة الإعدادات (قسم «الخط»).
 */
const SCALE_KEY = 'ktra_font_scale';
const FAMILY_KEY = 'ktra_font_family';
/** مفاتيح cache خاصة بكل شركة (مع إبقاء المفتاح القديم كترحيل للتفضيل السابق). */
const scaleCacheKey = (tid: number) => `${SCALE_KEY}::${tid}`;
const familyCacheKey = (tid: number) => `${FAMILY_KEY}::${tid}`;

export type FontScale = 'small' | 'normal' | 'large' | 'xlarge';
export type FontFamilyId = 'default' | 'tahoma' | 'segoe' | 'arial';

const SCALE_IDS = ['small', 'normal', 'large', 'xlarge'] as const;
const FAMILY_IDS = ['default', 'tahoma', 'segoe', 'arial'] as const;

/** نسبة تكبير الخط لكل مستوى (تُطبَّق على مرتكز rem ومتغيّرات الأصيل). */
const SCALE_FACTOR: Record<FontScale, number> = {
  small: 0.9,
  normal: 1,
  large: 1.15,
  xlarge: 1.3,
};

/** خيارات نوع الخط — مكدّسات آمنة على النظام (لا خطوط ويب خارجية). */
const FONT_STACK: Record<FontFamilyId, string> = {
  default: "'IBM Plex Sans Arabic', 'Segoe UI', system-ui, sans-serif",
  tahoma: "'Tahoma', 'Segoe UI', 'IBM Plex Sans Arabic', system-ui, sans-serif",
  segoe: "'Segoe UI', 'IBM Plex Sans Arabic', system-ui, sans-serif",
  arial: "'Arial', 'IBM Plex Sans Arabic', system-ui, sans-serif",
};

export const FONT_SCALE_OPTIONS: { id: FontScale; label: string }[] = [
  { id: 'small', label: 'صغير' },
  { id: 'normal', label: 'متوسط (افتراضي)' },
  { id: 'large', label: 'كبير' },
  { id: 'xlarge', label: 'أكبر' },
];

export const FONT_FAMILY_OPTIONS: { id: FontFamilyId; label: string }[] = [
  { id: 'default', label: 'افتراضي (IBM Plex Arabic)' },
  { id: 'tahoma', label: 'Tahoma' },
  { id: 'segoe', label: 'Segoe UI' },
  { id: 'arial', label: 'Arial' },
];

interface AppearanceValue {
  fontScale: FontScale;
  setFontScale: (v: FontScale) => void;
  fontFamily: FontFamilyId;
  setFontFamily: (v: FontFamilyId) => void;
}

const AppearanceContext = createContext<AppearanceValue | null>(null);

/** يقرأ التفضيل من cache الشركة، ثم المفتاح القديم العام (ترحيل)، ثم الافتراضي. */
const readPref = <T extends string>(
  perKey: string, legacyKey: string, allowed: readonly T[], fallback: T,
): T => {
  try {
    const v = (localStorage.getItem(perKey) ?? localStorage.getItem(legacyKey)) as T | null;
    return v && allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
};

/** كتابة cache الشركة (لا تُفشل العملية إن امتلأت الذاكرة). */
const writeCache = (key: string, v: string): void => {
  try { localStorage.setItem(key, v); } catch { /* الذاكرة تكفي لهذه الجلسة */ }
};

const hasToken = (): boolean => {
  try { return !!localStorage.getItem('token'); } catch { return false; }
};

/** يطبّق التفضيل على <html> عبر متغيّرات CSS (المرتكز العام + متغيّرات الأصيل). */
const applyAppearance = (scale: FontScale, family: FontFamilyId): void => {
  const root = document.documentElement;
  const factor = SCALE_FACTOR[scale] ?? 1;
  const stack = FONT_STACK[family] ?? FONT_STACK.default;
  // نوع الخط: للواجهة العامة وسكِن الأصيل.
  root.style.setProperty('--font-family-base', stack);
  root.style.setProperty('--ktra-font', stack);
  // الحجم: مرتكز rem العام (html أصله 16px) يُكبّر كل الأحجام النسبية.
  root.style.fontSize = `${16 * factor}px`;
  // متغيّرات الأصيل بالبكسل (لا تتبع rem) تُكبَّر يدوياً بنفس النسبة.
  root.style.setProperty('--ktra-fs', `${12 * factor}px`);
  root.style.setProperty('--ktra-fs-sm', `${11 * factor}px`);
  root.style.setProperty('--ktra-fs-base', `${13 * factor}px`);
  root.style.setProperty('--ktra-fs-title', `${14 * factor}px`);
};

export const AppearanceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // الشركة النشطة تُثبَّت عند التركيب؛ تبديل الشركة يعيد تحميل الصفحة بالكامل
  // (CompanyContext.switchCompany) فيُعاد تركيب المزوّد بالشركة الجديدة.
  const tenantId = resolveTenantId();
  const [fontScale, setFontScaleState] = useState<FontScale>(() =>
    readPref(scaleCacheKey(tenantId), SCALE_KEY, SCALE_IDS, 'normal'),
  );
  const [fontFamily, setFontFamilyState] = useState<FontFamilyId>(() =>
    readPref(familyCacheKey(tenantId), FAMILY_KEY, FAMILY_IDS, 'default'),
  );

  // تطبيق فوري عند التركيب وعند أي تغيير.
  useEffect(() => {
    applyAppearance(fontScale, fontFamily);
  }, [fontScale, fontFamily]);

  /** حفظ التفضيل خادمياً (per-company). غير حظري — لا يُعطّل الواجهة. */
  const persist = useCallback((patch: { font_scale?: FontScale; font_family?: FontFamilyId }) => {
    if (!hasToken()) return; // زائر (صفحة الهبوط/الدخول) — cache محلي فقط
    // الإفراغ بعد نجاح الكتابة لا قبلها: إفراغٌ مبكر يترك نافذةً يهبط فيها
    // GET متزامن فيعيد تعبئة النافذة بالقيمة القديمة قبل أن يصل الـPATCH.
    void apiPatchObject('tenants/settings/current/', patch, { tenantId })
      .then(() => invalidateTenantSettings())
      .catch((e) => clientLogger.warn('appearance.persist_failed', { error: String(e) }));
  }, [tenantId]);

  // مزامنة أوّلية من الخادم (مصدر الحقيقة per-company). تعمل مرة لكل تركيب.
  const syncedRef = useRef(false);
  useEffect(() => {
    if (syncedRef.current || !hasToken()) return;
    syncedRef.current = true;
    void (async () => {
      try {
        const s = await getTenantSettings<{ font_scale?: string; font_family?: string }>(
          tenantId,
        );
        const srvScale = SCALE_IDS.includes(s?.font_scale as FontScale) ? (s!.font_scale as FontScale) : null;
        const srvFamily = FAMILY_IDS.includes(s?.font_family as FontFamilyId) ? (s!.font_family as FontFamilyId) : null;

        // ترحيل لطيف: تفضيل محلي غير افتراضي والخادم افتراضي ⇒ ادفع المحلي مرة
        // (حتى لا يفقد المستخدم تفضيله السابق المحفوظ محلياً بعد هذا التحديث).
        const localScale = readPref(scaleCacheKey(tenantId), SCALE_KEY, SCALE_IDS, 'normal');
        const localFamily = readPref(familyCacheKey(tenantId), FAMILY_KEY, FAMILY_IDS, 'default');
        const migrate: { font_scale?: FontScale; font_family?: FontFamilyId } = {};
        if (srvScale === 'normal' && localScale !== 'normal') migrate.font_scale = localScale;
        if (srvFamily === 'default' && localFamily !== 'default') migrate.font_family = localFamily;
        if (migrate.font_scale || migrate.font_family) {
          persist(migrate);
          return; // القيم المحلية مطبَّقة أصلاً — أبقها
        }

        if (srvScale) { setFontScaleState(srvScale); writeCache(scaleCacheKey(tenantId), srvScale); }
        if (srvFamily) { setFontFamilyState(srvFamily); writeCache(familyCacheKey(tenantId), srvFamily); }
      } catch (e) {
        clientLogger.warn('appearance.sync_failed', { error: String(e) });
      }
    })();
  }, [tenantId, persist]);

  const setFontScale = useCallback((v: FontScale) => {
    setFontScaleState(v);
    writeCache(scaleCacheKey(tenantId), v);
    persist({ font_scale: v });
    clientLogger.info('appearance.font_scale', { fontScale: v });
  }, [tenantId, persist]);

  const setFontFamily = useCallback((v: FontFamilyId) => {
    setFontFamilyState(v);
    writeCache(familyCacheKey(tenantId), v);
    persist({ font_family: v });
    clientLogger.info('appearance.font_family', { fontFamily: v });
  }, [tenantId, persist]);

  const value = useMemo<AppearanceValue>(
    () => ({ fontScale, setFontScale, fontFamily, setFontFamily }),
    [fontScale, setFontScale, fontFamily, setFontFamily],
  );

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
};

export function useAppearance(): AppearanceValue {
  const ctx = useContext(AppearanceContext);
  // افتراضات آمنة عند غياب المزوّد (لا نرمي استثناءً).
  return (
    ctx ?? {
      fontScale: 'normal',
      setFontScale: () => {},
      fontFamily: 'default',
      setFontFamily: () => {},
    }
  );
}
