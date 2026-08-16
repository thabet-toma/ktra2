import React, { useState } from 'react';
import {
  Paperclip, FileText,
  Trash2, Download, X
} from 'lucide-react';
import { cloudinaryService } from '../../../services/cloudinaryService'; // تأكد من صحة المسار
import { FileDropZone } from '../../ui/FileDropZone';
import { useToast } from '../../../contexts/ToastContext';

interface AttachmentsProps {
  data: any; // Deal or PriceOffer data
  setData: (data: any) => void;
  readOnly?: boolean;
}

export const AttachmentsSection: React.FC<AttachmentsProps> = ({ data, setData, readOnly }) => {
  const [uploadingImages, setUploadingImages] = useState(false);
  const [uploadingPdfs, setUploadingPdfs] = useState(false);
  const toast = useToast();

  // --- Helpers --

  // تحديد مفاتيح البيانات بناءً على ما إذا كانت صفقة (CamelCase) أو عرض سعر (SnakeCase)
  // Deal uses: quoteImages, quotePdfs
  // PriceOffer uses: quote_images, quote_pdfs
  // سنقوم بالفحص والتحديث بناءً على الموجود
  const imagesKey = 'quoteImages' in data ? 'quoteImages' : 'quote_images';
  const pdfsKey = 'quotePdfs' in data ? 'quotePdfs' : 'quote_pdfs';

  // --- Handlers ---

  // فحص النوع والحجم صار داخل `FileDropZone` (برسالة toast)، فما يصل هنا مقبول.
  const uploadImageFiles = async (files: File[]) => {
    if (files.length === 0) return;
    setUploadingImages(true);
    const newUrls: string[] = [];
    try {
      for (const file of files) {
        // ✅ نستخدم الدالة الجديدة التي تقبل أي ملف
        const imageUrl = await cloudinaryService.uploadFile(file);
        if (imageUrl) newUrls.push(imageUrl);
      }

      setData((prev: any) => ({
        ...prev,
        [imagesKey]: [...(prev[imagesKey] || []), ...newUrls]
      }));
    } catch (error) {
      // console suppressed
      toast('فشل رفع الصور', 'error');
    } finally {
      setUploadingImages(false);
    }
  };

  const uploadPdfFiles = async (files: File[]) => {
    if (files.length === 0) return;
    setUploadingPdfs(true);

    const newPdfFiles: any[] = [];

    try {
      for (const file of files) {
        // ✅ التعديل الجوهري هنا:
        // نرفع الملف مباشرة إلى كلاودنري ونحصل على الرابط
        const pdfUrl = await cloudinaryService.uploadFile(file);

        if (pdfUrl) {
          newPdfFiles.push({
            name: file.name,
            url: pdfUrl, // الآن الرابط يبدأ بـ https:// وليس data:image...
            size: file.size,
            type: file.type
          });
        }
      }

      setData((prev: any) => ({
        ...prev,
        [pdfsKey]: [...(prev[pdfsKey] || []), ...newPdfFiles]
      }));
    } catch (error) {
      // console suppressed
      toast('حدث خطأ أثناء رفع ملفات PDF', 'error');
    } finally {
      setUploadingPdfs(false);
    }
  };

  const removeFile = (type: 'image' | 'pdf', index: number) => {
    if (type === 'image') {
      setData((prev: any) => ({
        ...prev,
        [imagesKey]: prev[imagesKey]?.filter((_: any, i: number) => i !== index)
      }));
    } else {
      setData((prev: any) => ({
        ...prev,
        [pdfsKey]: prev[pdfsKey]?.filter((_: any, i: number) => i !== index)
      }));
    }
  };

  // --- Render ---

  return (
    <div className="bg-[var(--color-surface)] p-6 rounded-xl border border-[var(--color-border)] shadow-sm">
      <h3 className="text-lg font-bold text-[var(--color-text)] mb-6 flex items-center gap-2">
        <Paperclip className="w-5 h-5 text-blue-600" />
        الملفات والمرفقات
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* 1. قسم ملفات PDF */}
        <div className="space-y-4">
          <label className="block text-sm font-medium text-[var(--color-text)]">
            ملفات PDF (عروض أسعار، كتالوجات)
          </label>

          {!readOnly && (
            <FileDropZone
              onFiles={(files) => { void uploadPdfFiles(files); }}
              accept="pdf"
              multiple
              busy={uploadingPdfs}
              hint="اضغط لرفع ملفات PDF، أو اسحبها إلى هنا"
              className="h-32"
            />
          )}

          <div className="space-y-2">
            {(data[pdfsKey] || []).map((file: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-[var(--color-surface-2)] rounded-lg border border-[var(--color-border)] group">
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="p-2 bg-red-100 dark:bg-red-900/20 rounded-lg flex-shrink-0">
                    <FileText className="w-5 h-5 text-red-600 dark:text-red-400" />
                  </div>
                  <div className="min-w-0">
                    {/* 🟢 التعديل 1: جعل اسم الملف رابطاً يفتح في صفحة جديدة */}
                    <a
                      href={file.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-[var(--color-text)] truncate hover:text-blue-600 hover:underline block cursor-pointer"
                      title="اضغط لفتح الملف"
                    >
                      {file.name}
                    </a>
                    <div className="text-xs text-[var(--color-text-muted)] flex gap-2">
                      <span>{(file.size / 1024).toFixed(1)} KB</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {/* 🟢 التعديل 2: تحديث أيقونة التحميل لتفتح في صفحة جديدة أيضاً */}
                  <a
                    href={file.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1 text-[var(--color-text-muted)] hover:text-blue-600 transition-colors"
                    title="فتح في تبويب جديد"
                  >
                    <Download className="w-4 h-4" />
                  </a>
                  {!readOnly && (
                    <button
                      onClick={() => removeFile('pdf', idx)}
                      className="p-1 text-[var(--color-text-muted)] hover:text-red-600 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
            {(!data[pdfsKey] || data[pdfsKey].length === 0) && (
              <p className="text-xs text-center text-[var(--color-text-muted)] py-2">لا توجد ملفات PDF</p>
            )}
          </div>
        </div>

        {/* 2. قسم الصور */}
        <div className="space-y-4">
          <label className="block text-sm font-medium text-[var(--color-text)]">
            الصور المرفقة
          </label>

          {!readOnly && (
            <FileDropZone
              onFiles={(files) => { void uploadImageFiles(files); }}
              accept="image"
              multiple
              busy={uploadingImages}
              className="h-32"
            />
          )}

          <div className="grid grid-cols-3 gap-2">
            {(data[imagesKey] || []).map((url: string, idx: number) => (
              <div key={idx} className="relative aspect-square rounded-lg overflow-hidden group border border-[var(--color-border)] bg-[var(--color-surface-3)]">
                <img
                  src={url}
                  alt={`att-${idx}`}
                  className="w-full h-full object-cover cursor-pointer hover:scale-105 transition-transform"
                  onClick={() => window.open(url, '_blank')} // فتح الصورة في تبويب جديد للمعاينة السريعة
                />
                {!readOnly && (
                  <button
                    onClick={() => removeFile('image', idx)}
                    className="absolute top-1 right-1 p-1 bg-red-500 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
          {(!data[imagesKey] || data[imagesKey].length === 0) && (
            <p className="text-xs text-center text-[var(--color-text-muted)] py-2">لا توجد صور مرفقة</p>
          )}
        </div>

      </div>
    </div>
  );
};