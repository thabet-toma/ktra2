import { useCallback, useEffect, useRef, useState } from 'react';
import { CustomerNote, listPageNotes } from '../services/customerNotesApi';

/**
 * ملاحظات الصفحة الحالية (مفتاحها مسارها) في طلب واحد: الشريط الأصفر يشتقّ منها
 * المثبّت غير المنجز، وشارة زر الملاحظات تعدّ المفتوح — بلا طلبين.
 *
 * الفشل لا يحجب الصفحة أبداً: القائمة تفرغ ويُسجَّل تحذيرٌ واحد فقط (لا ضجيج
 * في كل تنقّل). `scopeKey` (الشركة النشطة) يعيد الجلب عند تبديلها. الردّ المتأخّر
 * لصفحة سابقة يُهمَل بترقيم الطلبات.
 */
export function usePageNotes(pathname: string, scopeKey?: string | number) {
  const [notes, setNotes] = useState<CustomerNote[]>([]);
  const seq = useRef(0);
  const warned = useRef(false);

  const refresh = useCallback(() => {
    const id = ++seq.current;
    listPageNotes(pathname)
      .then((rows) => { if (id === seq.current) setNotes(rows); })
      .catch((error) => {
        if (id === seq.current) setNotes([]);
        if (!warned.current) {
          warned.current = true;
          console.warn('تعذّر تحميل ملاحظات الصفحة المثبّتة', error);
        }
      });
  }, [pathname, scopeKey]);

  useEffect(() => {
    setNotes([]);
    refresh();
    return () => { seq.current += 1; };
  }, [refresh]);

  return { notes, refresh };
}
