/**
 * T-IMPOFFER — FilePreviewModal: معاينة ملف مرفوع في نافذة وسط الشاشة.
 *
 * المالك: «لما أكبس على الملف يطلعلي نافذة بالنص أشوف الملف.» النمط القائم في
 * المشروع كان `window.open(url)` (تبويب جديد) أو `ImagePreviewModal` للصور
 * وحدها — فملف عرض السعر (PDF) لم يكن له معاينة داخل الصفحة أبداً.
 *
 * تعميم مقصود على `ImagePreviewModal`: يعرض الصور داخلياً و PDF في إطار، وما
 * لا يُعرض في المتصفح يُقدَّم برابط صريح بدل نافذة فارغة تكذب على المستخدم.
 */
import React from "react";
import { Download, ExternalLink, FileText } from "lucide-react";
import { KitFloatWindow } from "../kit/KitFloatWindow";

export interface PreviewableFile {
  name?: string;
  url: string;
  type?: string;
}

const isImage = (file: PreviewableFile): boolean =>
  String(file.type || "").startsWith("image/")
  || /\.(png|jpe?g|gif|webp|bmp|svg)(\?|$)/i.test(file.url);

const isPdf = (file: PreviewableFile): boolean =>
  String(file.type || "") === "application/pdf"
  || /\.pdf(\?|$)/i.test(file.url);

export const FilePreviewModal: React.FC<{
  file: PreviewableFile | null;
  onClose: () => void;
}> = ({ file, onClose }) => {
  if (!file) return null;

  const label = file.name || "ملف مرفق";

  /* T-WIN: المعاينة صارت نافذة عائمة تُسحب وتُحجَّم — كانت مستطيلاً ثابتاً
     في المنتصف، فمقارنة الملف بالمستند خلفه كانت متعذّرة. */
  return (
    <KitFloatWindow
      open
      onClose={onClose}
      name="file-preview"
      title={(
        <span className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-blue-600" />
          <span className="truncate">{label}</span>
        </span>
      )}
      defaultWidth={900}
      defaultHeight={640}
      barExtras={(
        <>
          <a
            className="ktra-toolbtn"
            href={file.url}
            target="_blank"
            rel="noopener noreferrer"
            title="فتح في تبويب جديد"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
          <a className="ktra-toolbtn" href={file.url} download title="تنزيل">
            <Download className="h-4 w-4" />
          </a>
        </>
      )}
    >
      <div className="flex h-full items-center justify-center overflow-auto bg-[var(--color-surface-2)] p-2">
        {isImage(file) ? (
          <img src={file.url} alt={label} className="max-h-full max-w-full object-contain" />
        ) : isPdf(file) ? (
          <iframe src={file.url} title={label} className="h-full w-full border-0 bg-white" />
        ) : (
          <div className="p-8 text-center text-sm text-[var(--color-text-muted)]">
            <FileText className="mx-auto mb-3 h-10 w-10 opacity-50" />
            <p>هذا النوع لا يُعرض داخل الصفحة.</p>
            <a
              className="mt-2 inline-block font-bold text-blue-600 hover:underline"
              href={file.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              افتح «{label}» في تبويب جديد
            </a>
          </div>
        )}
      </div>
    </KitFloatWindow>
  );
};
