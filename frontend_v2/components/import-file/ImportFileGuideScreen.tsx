import React from "react";
import { BookOpen, FileText } from "lucide-react";
import { IMPORT_FILE_GUIDE } from "./importFileGuideContent";

/**
 * شاشة شرح مستندات الاستيراد — لكل مستند: ما هو، ولماذا يُطلب، ومن يصدره.
 *
 * سببها: قائمةُ تحقّقٍ تطلب «شهادة المنشأ» ممن لا يعرف ما هي تُنتج ملفاً ناقصاً
 * أو ورقةً خاطئة. الشرح صفحةٌ مستقلة لا tooltip: تُقرأ مرّة، وتُفتح في تبويب
 * جديد من اللوحة فلا تُفقد تعديلات الصفقة المفتوحة.
 *
 * المحتوى بيانات صرفة في `importFileGuideContent.ts` — لا نصّ هنا.
 */
export const ImportFileGuideScreen: React.FC = () => (
  <div dir="rtl" className="mx-auto flex max-w-4xl flex-col gap-4 p-4">
    <header className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <h1 className="flex items-center gap-2 text-lg font-bold text-[var(--color-text)]">
        <BookOpen className="h-5 w-5 text-blue-600" />
        مستندات ملف الاستيراد
      </h1>
      <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-muted)]">
        كل ورقة تطلبها رحلة الاستيراد: ما هي، ولماذا تُطلب، ومن يصدرها. الأوراق نفسها
        تظهر في تبويب «ملف الاستيراد» داخل كل صفقة، وتُرفع هناك.
      </p>
    </header>

    <ol className="flex flex-col gap-3">
      {IMPORT_FILE_GUIDE.map((entry) => (
        <li
          key={entry.kind}
          className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
        >
          <h2 className="flex items-center gap-2 text-sm font-bold text-[var(--color-text)]">
            <FileText className="h-4 w-4 text-[var(--color-text-muted)]" />
            {entry.title}
          </h2>
          <p className="mt-1.5 text-xs leading-relaxed text-[var(--color-text)]">{entry.what}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-[var(--color-text-muted)]">
            <span className="font-semibold text-[var(--color-text)]">لماذا يُطلب: </span>
            {entry.why}
          </p>
          <p className="mt-1.5 text-xs text-[var(--color-text-muted)]">
            <span className="font-semibold text-[var(--color-text)]">من يصدره: </span>
            {entry.issuer}
          </p>
        </li>
      ))}
    </ol>
  </div>
);
