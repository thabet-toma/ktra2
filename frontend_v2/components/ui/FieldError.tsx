/**
 * SAVE-1 — رسالة خطأ الخادم بجانب الحقل الذي سبّبها.
 *
 * الخادم يرسل مع كل رفض خريطة «حقل → سبب» (`extractDrfFieldErrors` في
 * `utils/drfError.ts`، تُلحق بالاستثناء في `services/restApi.handleResponseError`)،
 * وكانت الشاشات تسحقها في لافتة واحدة أعلى النموذج فيقرأ المستخدم «الكمية مطلوبة»
 * دون أن يعرف أيّ سطر. هذا المكوّن يعيدها إلى مكانها.
 *
 * القاعدة: ما له حقل مرئي يُعرض تحته، وما لا حقل له (`detail` / `non_field_errors`)
 * يبقى في لافتة النموذج. لا يُعرَض شيء حين لا رسالة — فلا يقفز التخطيط.
 *
 * الأنماط مطابقة لرسالة الخطأ في `Input` داخل `components/ui/index.tsx` كي يكون
 * الخطأ الحقلي شكلاً واحداً في التطبيق كلّه.
 */
import React from 'react';

interface FieldErrorProps {
  /** الرسالة المعرّبة، عادةً `error.fieldErrors[<اسم الحقل>]`. */
  message?: string;
  /** يُربط بـ `aria-describedby` على الحقل نفسه ليقرأه قارئ الشاشة. */
  id?: string;
  className?: string;
}

export const FieldError: React.FC<FieldErrorProps> = ({ message, id, className = '' }) => {
  if (!message) return null;
  return (
    <span
      id={id}
      role="alert"
      className={`block text-[var(--font-size-xs)] text-[var(--color-danger)] ${className}`}
    >
      {message}
    </span>
  );
};

export default FieldError;
