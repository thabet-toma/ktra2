import React, { createContext, useContext, useState, useCallback } from 'react';
import type { Theme } from '../types';
import { uiLog } from '../utils/uiLog';

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const THEME_KEY = 'ktra.theme';

/** التفضيل المحفوظ، وإلا تفضيل نظام التشغيل، وإلا الوضع الفاتح. */
export const getStoredTheme = (): Theme => {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === 'dark' || saved === 'light') return saved;
  } catch (error) {
    uiLog.warn('تعذّرت قراءة سمة الواجهة من التخزين المحلي.', error);
  }
  try {
    if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark';
  } catch {
    /* بيئات بلا matchMedia */
  }
  return 'light';
};

const applyThemeClass = (theme: Theme): void => {
  document.documentElement.classList.toggle('dark', theme === 'dark');
};

/** تُستدعى مرة من index.tsx قبل الرندر — تمنع وميض الفاتح قبل تطبيق الداكن. */
export const applyThemeOnBoot = (): Theme => {
  const theme = getStoredTheme();
  applyThemeClass(theme);
  uiLog.info('تم تطبيق سمة الواجهة عند الإقلاع.', { theme });
  return theme;
};

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // القراءة من التخزين لا من قيمة ثابتة: كان يبدأ 'light' دائماً فيضيع
  // اختيار المستخدم مع كل تحديث للصفحة.
  const [theme, setTheme] = useState<Theme>(getStoredTheme);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'light' ? 'dark' : 'light';
      applyThemeClass(next);
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (error) {
        uiLog.warn('تعذّر حفظ سمة الواجهة في التخزين المحلي.', error);
      }
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider');
  return ctx;
}
