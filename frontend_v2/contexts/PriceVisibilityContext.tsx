import React, { createContext, useContext, useState, useCallback } from 'react';
import { clientLogger } from '../services/logger';

/**
 * إظهار/إخفاء أسعار الأصناف (آخر/أقل سعر) في قوائم الاختيار — تفضيل عام للخصوصية:
 * حين يكون زبون أمام الشاشة لا يرى الأسعار. **الافتراضي مخفي** (الأأمن)، ويُخزَّن
 * في localStorage فيثبت بين الجلسات. مصدر حقيقة واحد يستهلكه AseelAutocomplete والزر.
 */
const STORAGE_KEY = 'ktra_prices_visible';

interface PriceVisibilityValue {
  visible: boolean;
  toggle: () => void;
}

const PriceVisibilityContext = createContext<PriceVisibilityValue | null>(null);

const readInitial = (): boolean => {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'; // غياب المفتاح ⇒ مخفي
  } catch {
    return false;
  }
};

export const PriceVisibilityProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [visible, setVisible] = useState<boolean>(readInitial);

  const toggle = useCallback(() => {
    setVisible((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
      } catch {
        /* تجاهل — الحالة في الذاكرة تكفي لهذه الجلسة */
      }
      clientLogger.info('prices.visibility', { visible: next });
      return next;
    });
  }, []);

  return (
    <PriceVisibilityContext.Provider value={{ visible, toggle }}>
      {children}
    </PriceVisibilityContext.Provider>
  );
};

export function usePriceVisibility(): PriceVisibilityValue {
  const ctx = useContext(PriceVisibilityContext);
  // افتراضياً مخفي عند غياب المزوّد (الأأمن للخصوصية) — لا نرمي استثناءً.
  return ctx ?? { visible: false, toggle: () => {} };
}
