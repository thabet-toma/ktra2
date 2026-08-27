import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { clientLogger } from '../services/logger';

/**
 * إظهار/إخفاء أسعار المنتجات (آخر/أقل سعر) في قوائم الاختيار **والربح الإجمالي** في محرّر
 * الفاتورة — تفضيل عام للخصوصية: حين يكون زبون أمام الشاشة لا يرى الأسعار ولا الأرباح.
 * مصدر حقيقة واحد يستهلكه KitAutocomplete وزر العين ومحرّر فاتورة المبيعات وصفحة الإعدادات.
 *
 * يُضبط من الإعدادات (إعدادات المنصة) بحقلين محليَّين لكل متصفح (localStorage):
 *  - showToggle: هل يظهر زر العين في الشريط العلوي أصلاً؟ (افتراضي: نعم)
 *  - defaultVisible: حين يكون الزر مخفياً، هل تُعرض الأسعار/الأرباح افتراضياً؟ (افتراضي: لا)
 * الظهور الفعّال = حالة الزر اليدوية حين يظهر الزر، وإلا القيمة الافتراضية المُعدّة.
 */
const STORAGE_KEY = 'ktra_prices_visible';
const SHOW_TOGGLE_KEY = 'ktra_prices_show_toggle';
const DEFAULT_VISIBLE_KEY = 'ktra_prices_default_visible';

interface PriceVisibilityValue {
  /** الظهور الفعّال (أسعار القوائم + الربح الإجمالي). */
  visible: boolean;
  /** يبدّل الحالة اليدوية (فعّال فقط حين يظهر زر العين). */
  toggle: () => void;
  /** هل يظهر زر العين في الشريط العلوي؟ */
  showToggle: boolean;
  setShowToggle: (v: boolean) => void;
  /** الظهور الافتراضي للأرباح/الأسعار حين يكون زر العين مخفياً. */
  defaultVisible: boolean;
  setDefaultVisible: (v: boolean) => void;
}

const PriceVisibilityContext = createContext<PriceVisibilityValue | null>(null);

const readBool = (key: string, fallback: boolean): boolean => {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : v === '1'; // غياب المفتاح ⇒ الافتراضي
  } catch {
    return fallback;
  }
};

const writeBool = (key: string, value: boolean): void => {
  try {
    localStorage.setItem(key, value ? '1' : '0');
  } catch {
    /* تجاهل — الحالة في الذاكرة تكفي لهذه الجلسة */
  }
};

export const PriceVisibilityProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [manualVisible, setManualVisible] = useState<boolean>(() => readBool(STORAGE_KEY, false));
  const [showToggle, setShowToggleState] = useState<boolean>(() => readBool(SHOW_TOGGLE_KEY, true));
  const [defaultVisible, setDefaultVisibleState] = useState<boolean>(() => readBool(DEFAULT_VISIBLE_KEY, false));

  const toggle = useCallback(() => {
    setManualVisible((prev) => {
      const next = !prev;
      writeBool(STORAGE_KEY, next);
      clientLogger.info('prices.visibility', { visible: next });
      return next;
    });
  }, []);

  const setShowToggle = useCallback((v: boolean) => {
    setShowToggleState(v);
    writeBool(SHOW_TOGGLE_KEY, v);
    clientLogger.info('prices.show_toggle', { showToggle: v });
  }, []);

  const setDefaultVisible = useCallback((v: boolean) => {
    setDefaultVisibleState(v);
    writeBool(DEFAULT_VISIBLE_KEY, v);
    clientLogger.info('prices.default_visible', { defaultVisible: v });
  }, []);

  // الظهور الفعّال: حين يظهر الزر نتبع حالته اليدوية، وإلا نتبع الافتراضي المُعدّ.
  const visible = showToggle ? manualVisible : defaultVisible;

  const value = useMemo<PriceVisibilityValue>(
    () => ({ visible, toggle, showToggle, setShowToggle, defaultVisible, setDefaultVisible }),
    [visible, toggle, showToggle, setShowToggle, defaultVisible, setDefaultVisible],
  );

  return (
    <PriceVisibilityContext.Provider value={value}>
      {children}
    </PriceVisibilityContext.Provider>
  );
};

export function usePriceVisibility(): PriceVisibilityValue {
  const ctx = useContext(PriceVisibilityContext);
  // افتراضياً مخفي عند غياب المزوّد (الأأمن للخصوصية) — لا نرمي استثناءً.
  return (
    ctx ?? {
      visible: false,
      toggle: () => {},
      showToggle: true,
      setShowToggle: () => {},
      defaultVisible: false,
      setDefaultVisible: () => {},
    }
  );
}
