import React, { useState } from 'react';
import {
  Paperclip, FileText, Image as ImageIcon,
  Trash2, Download, X, Upload, Loader2
} from 'lucide-react';
import { cloudinaryService } from '../../../services/cloudinaryService'; // تأكد من صحة المسار

interface AttachmentsProps {
  data: any; // Deal or PriceOffer data
  setData: (data: any) => void;
  readOnly?: boolean;
}

export const AttachmentsSection: React.FC<AttachmentsProps> = ({ data, setData, readOnly }) => {
  const [uploadingImages, setUploadingImages] = useState(false);
  const [uploadingPdfs, setUploadingPdfs] = useState(false);

  // --- Helpers --

  // تحديد مفاتيح البيانات بناءً على ما إذا كانت صفقة (CamelCase) أو عرض سعر (SnakeCase)
  // Deal uses: quoteImages, quotePdfs
  // PriceOffer uses: quote_images, quote_pdfs
  // سنقوم بالفحص والتحديث بناءً على الموجود
  const imagesKey = 'quoteImages' in data ? 'quoteImages' : 'quote_images';
  const pdfsKey = 'quotePdfs' in data ? 'quotePdfs' : 'quote_pdfs';

  // --- Handlers ---

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploadingImages(true);

    const files = Array.from(e.target.files);
    const newUrls: string[] = [];

    try {
      for (const file of files) {
        const typedFile = file as File;
        if (!typedFile.type.startsWith('image/')) continue;
        // ✅ نستخدم الدالة الجديدة التي تقبل أي ملف
        const imageUrl = await cloudinaryService.uploadFile(typedFile);
        if (imageUrl) newUrls.push(imageUrl);
      }

      setData((prev: any) => ({
        ...prev,
        [imagesKey]: [...(prev[imagesKey] || []), ...newUrls]
      }));
    } catch (error) {
      // console suppressed
      alert("فشل رفع الصور");
    } finally {
      setUploadingImages(false);
      e.target.value = '';
    }
  };

  const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploadingPdfs(true);

    const files = Array.from(e.target.files);
    const newPdfFiles: any[] = [];

    try {
      for (const file of files) {
        const typedFile = file as File;
        if (typedFile.type !== 'application/pdf') {
          alert(`الملف ${typedFile.name} ليس PDF.`);
          continue;
        }

        // ✅ التعديل الجوهري هنا:
        // نرفع الملف مباشرة إلى كلاودنري ونحصل على الرابط
        const pdfUrl = await cloudinaryService.uploadFile(typedFile);

        if (pdfUrl) {
          newPdfFiles.push({
            name: typedFile.name,
            url: pdfUrl, // الآن الرابط يبدأ بـ https:// وليس data:image...
            size: typedFile.size,
            type: typedFile.type
          });
        }
      }

      setData((prev: any) => ({
        ...prev,
        [pdfsKey]: [...(prev[pdfsKey] || []), ...newPdfFiles]
      }));
    } catch (error) {
      // console suppressed
      alert("حدث خطأ أثناء رفع ملفات PDF");
    } finally {
      setUploadingPdfs(false);
      e.target.value = '';
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
    <div className="bg-white dark:bg-gray-800 p-6 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm">
      <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
        <Paperclip className="w-5 h-5 text-blue-600" />
        الملفات والمرفقات
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* 1. قسم ملفات PDF */}
        <div className="space-y-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            ملفات PDF (عروض أسعار، كتالوجات)
          </label>

          {!readOnly && (
            <div className="relative">
              <input
                type="file"
                accept=".pdf"
                multiple
                onChange={handlePdfUpload}
                className="hidden"
                id="pdf-upload-section"
                disabled={uploadingPdfs}
              />
              <label
                htmlFor="pdf-upload-section"
                className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  {uploadingPdfs ? (
                    <Loader2 className="w-8 h-8 mb-2 text-blue-500 animate-spin" />
                  ) : (
                    <FileText className="w-8 h-8 mb-2 text-gray-400" />
                  )}
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {uploadingPdfs ? 'جاري المعالجة...' : 'اضغط لرفع ملفات PDF'}
                  </p>
                </div>
              </label>
            </div>
          )}

          <div className="space-y-2">
            {(data[pdfsKey] || []).map((file: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/30 rounded-lg border border-gray-100 dark:border-gray-700 group">
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
                      className="text-sm font-medium text-gray-900 dark:text-white truncate hover:text-blue-600 hover:underline block cursor-pointer"
                      title="اضغط لفتح الملف"
                    >
                      {file.name}
                    </a>
                    <div className="text-xs text-gray-500 flex gap-2">
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
                    className="p-1 text-gray-400 hover:text-blue-600 transition-colors"
                    title="فتح في تبويب جديد"
                  >
                    <Download className="w-4 h-4" />
                  </a>
                  {!readOnly && (
                    <button
                      onClick={() => removeFile('pdf', idx)}
                      className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
            {(!data[pdfsKey] || data[pdfsKey].length === 0) && (
              <p className="text-xs text-center text-gray-400 py-2">لا توجد ملفات PDF</p>
            )}
          </div>
        </div>

        {/* 2. قسم الصور */}
        <div className="space-y-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            الصور المرفقة
          </label>

          {!readOnly && (
            <div className="relative">
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={handleImageUpload}
                className="hidden"
                id="image-upload-section"
                disabled={uploadingImages}
              />
              <label
                htmlFor="image-upload-section"
                className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  {uploadingImages ? (
                    <Loader2 className="w-8 h-8 mb-2 text-blue-500 animate-spin" />
                  ) : (
                    <ImageIcon className="w-8 h-8 mb-2 text-gray-400" />
                  )}
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {uploadingImages ? 'جاري الرفع...' : 'اضغط لرفع الصور'}
                  </p>
                </div>
              </label>
            </div>
          )}

          <div className="grid grid-cols-3 gap-2">
            {(data[imagesKey] || []).map((url: string, idx: number) => (
              <div key={idx} className="relative aspect-square rounded-lg overflow-hidden group border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800">
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
            <p className="text-xs text-center text-gray-400 py-2">لا توجد صور مرفقة</p>
          )}
        </div>

      </div>
    </div>
  );
};