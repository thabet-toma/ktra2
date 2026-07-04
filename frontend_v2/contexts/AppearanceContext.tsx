import React, { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';
import { clientLogger } from '../services/logger';

/**
 * تفضيل المظهر — حجم الخط ونوعه. تفضيل عام محلي لكل متصفح (localStorage) على نمط
 * ThemeContext. يُطبَّق بضبط متغيّرات CSS على <html> فيسري على الواجهة العامة
 * (rem مرتكز على html) وعلى سكِن «الأصيل» (متغيّرات --aseel-*) معاً — مصدر تحكّم واحد.
 * يُضبط من صفحة الإعدادات (قسم «الخط»).
 */
const SCALE_KEY = 'ktra_font_scale';
const FAMILY_KEY = 'ktra_font_family';

export type FontScale = 'small' | 'normal' | 'large' | 'xlarge';
export type FontFamilyId = 'default' | 'tahoma' | 'segoe' | 'arial';

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

const read = <T extends string>(key: string, allowed: readonly T[], fallback: T): T => {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
};

/** يطبّق التفضيل على <html> عبر متغيّرات CSS (المرتكز العام + متغيّرات الأصيل). */
const applyAppearance = (scale: FontScale, family: FontFamilyId): void => {
  const root = document.documentElement;
  const factor = SCALE_FACTOR[scale] ?? 1;
  const stack = FONT_STACK[family] ?? FONT_STACK.default;
  // نوع الخط: للواجهة العامة وسكِن الأصيل.
  root.style.setProperty('--font-family-base', stack);
  root.style.setProperty('--aseel-font', stack);
  // الحجم: مرتكز rem العام (html أصله 16px) يُكبّر كل الأحجام النسبية.
  root.style.fontSize = `${16 * factor}px`;
  // متغيّرات الأصيل بالبكسل (لا تتبع rem) تُكبَّر يدوياً بنفس النسبة.
  root.style.setProperty('--aseel-fs', `${12 * factor}px`);
  root.style.setProperty('--aseel-fs-sm', `${11 * factor}px`);
  root.style.setProperty('--aseel-fs-base', `${13 * factor}px`);
  root.style.setProperty('--aseel-fs-title', `${14 * factor}px`);
};

export const AppearanceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [fontScale, setFontScaleState] = useState<FontScale>(() =>
    read(SCALE_KEY, ['small', 'normal', 'large', 'xlarge'] as const, 'normal'),
  );
  const [fontFamily, setFontFamilyState] = useState<FontFamilyId>(() =>
    read(FAMILY_KEY, ['default', 'tahoma', 'segoe', 'arial'] as const, 'default'),
  );

  // تطبيق فوري عند التركيب وعند أي تغيير.
  useEffect(() => {
    applyAppearance(fontScale, fontFamily);
  }, [fontScale, fontFamily]);

  const setFontScale = useCallback((v: FontScale) => {
    setFontScaleState(v);
    try { localStorage.setItem(SCALE_KEY, v); } catch { /* الذاكرة تكفي لهذه الجلسة */ }
    clientLogger.info('appearance.font_scale', { fontScale: v });
  }, []);

  const setFontFamily = useCallback((v: FontFamilyId) => {
    setFontFamilyState(v);
    try { localStorage.setItem(FAMILY_KEY, v); } catch { /* الذاكرة تكفي لهذه الجلسة */ }
    clientLogger.info('appearance.font_family', { fontFamily: v });
  }, []);

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
