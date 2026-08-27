/**
 * `/store` بلا معرّف متجر — صفحة تعريف، لا خطأ ولا شاشة فارغة.
 *
 * زرّا «المتجر» في صفحة الهبوط وصفحة الدخول، و`robots.txt`، و`sitemap.xml`
 * كلها تشير إلى `/store` منذ وقت طويل بينما لم تكن هناك صفحة خلفه. لكل شركة
 * متجرها على معرّفها الخاص، فهذا العنوان لا يملك كتالوجاً يعرضه — يشرح ذلك
 * ويعطي الطريق بدل أن يترك الزائر أمام صفحة بيضاء.
 *
 * `VITE_DEFAULT_STORE_SLUG` (إن ضُبط) يحوّل هذا العنوان مباشرة إلى متجر
 * المجموعة نفسها — والتحويل يتم في `index.tsx` حيث يعيش التوجيه.
 */
import React from "react";
import { Link2, Store as StoreIcon } from "lucide-react";

import { useDocumentDescription, useDocumentTitle } from "../../hooks/useDocumentTitle";

export const StoreIndexPage: React.FC = () => {
  useDocumentTitle("المتاجر الإلكترونية — K.T.R.A");
  useDocumentDescription(
    "لكل شركة على منصة K.T.R.A متجرها الإلكتروني الخاص برابطه المستقل — اطلب رابط المتجر من الشركة مباشرة.",
  );

  return (
    <div dir="rtl" className="flex min-h-screen items-center justify-center bg-slate-100 p-6 dark:bg-slate-900">
      <div className="w-full max-w-xl rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-slate-800">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600 text-white">
          <StoreIcon className="h-8 w-8" />
        </div>
        <h1 className="mt-5 text-2xl font-black text-slate-900 dark:text-white">المتاجر الإلكترونية</h1>
        <p className="mt-4 text-sm leading-7 text-slate-600 dark:text-slate-300">
          لكل شركة على منصة K.T.R.A متجرها الخاص برابطه المستقل، يعرض ما اختارت الشركة نشره من منتجاتها
          بأسعارها المحدّثة. لا يوجد كتالوج موحّد لكل الشركات — اطلب من الشركة رابط متجرها،
          ويكون على الشكل:
        </p>
        <p className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-100 px-4 py-3 font-mono text-sm font-bold text-slate-700 dark:bg-slate-700 dark:text-slate-200" dir="ltr">
          <Link2 className="h-4 w-4" />
          {`${typeof window === "undefined" ? "" : window.location.origin}/store/<اسم-المتجر>`}
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <a href="/" className="rounded-xl bg-blue-600 px-6 py-3 font-bold text-white transition hover:bg-blue-700">
            الصفحة الرئيسية
          </a>
          <a href="/contact" className="rounded-xl border border-slate-300 px-6 py-3 font-bold text-slate-700 transition hover:bg-slate-50 dark:border-slate-600 dark:text-slate-200">
            تواصل معنا
          </a>
        </div>
      </div>
    </div>
  );
};

export default StoreIndexPage;
