import React, { useEffect } from "react";

import { PublicNavbar } from "./layout/PublicNavbar";
import { clientLogger } from "../services/logger";

/**
 * مسارٌ غير موجود لزائر غير مسجَّل — بدل صفحة الهبوط بحالة 200 (soft 404).
 * `noindex` يُخرج العنوان من الفهرس بعد تنفيذ JS؛ الحالة 404 الحقيقية شأن nginx.
 */
export const NotFoundPage: React.FC<{ path: string }> = ({ path }) => {
  useEffect(() => {
    // المسار وحده بلا query — لا PII؛ يكشف روابط مكسورة يتبعها الزوّار.
    clientLogger.info("seo.not_found", { path });
  }, [path]);

  return (
    <div>
      <title>الصفحة غير موجودة — K.T.R.A</title>
      <meta name="robots" content="noindex" />
      <PublicNavbar />
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-gray-50 px-4 pt-20 dark:bg-gray-900">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-xl dark:bg-gray-800">
          <p className="text-5xl font-black text-blue-600">404</p>
          <h1 className="mt-4 text-xl font-bold text-gray-900 dark:text-white">الصفحة غير موجودة</h1>
          <p className="mt-3 text-sm leading-6 text-gray-600 dark:text-gray-300">
            الرابط الذي فتحته غير موجود أو نُقل. تابع من الصفحة الرئيسية.
          </p>
          <a href="/" className="mt-6 inline-block rounded-xl bg-blue-600 px-6 py-3 font-bold text-white transition hover:bg-blue-700">
            الصفحة الرئيسية
          </a>
        </div>
      </div>
    </div>
  );
};
