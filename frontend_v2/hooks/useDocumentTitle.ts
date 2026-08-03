import { useEffect } from "react";

/**
 * يضبط عنوان التبويب (وما يقرأه Google عند فهرسة الصفحة) لكل شاشة عامة على
 * حدة، بدل عنوان index.html الثابت الواحد لكل مسارات الموقع. يُستخدم فقط في
 * الشاشات العامة غير المصادَق عليها (الهبوط، من نحن، تواصل معنا، المتجر) —
 * الشاشات الداخلية لا تحتاج عنواناً مفهرَساً.
 */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
