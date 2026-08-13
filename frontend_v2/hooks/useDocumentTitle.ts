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

/**
 * وصف الصفحة (`<meta name="description">`) — ما يظهر تحت العنوان في نتائج
 * البحث وفي معاينة الرابط على واتساب. صفحات المتاجر تُشارَك بالرابط أساساً،
 * فوصفٌ واحد ثابت لكل الموقع يجعل كل متجر يبدو كأنه الموقع نفسه.
 *
 * الوسم قد لا يكون موجوداً في `index.html` فيُنشأ عند الحاجة، وتُعاد القيمة
 * السابقة عند مغادرة الصفحة كي لا يتسرّب وصف متجرٍ إلى بقية الشاشات.
 */
export function useDocumentDescription(description: string): void {
  useEffect(() => {
    if (!description) return;
    let tag = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    let created = false;
    if (!tag) {
      tag = document.createElement("meta");
      tag.setAttribute("name", "description");
      document.head.appendChild(tag);
      created = true;
    }
    const previous = tag.getAttribute("content") || "";
    tag.setAttribute("content", description);
    return () => {
      if (created) tag?.remove();
      else tag?.setAttribute("content", previous);
    };
  }, [description]);
}
