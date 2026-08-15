import { apiPostFormData } from './restApi';

/**
 * رفع الملفات عبر خادم KTRA (‎/api/media/upload/‎) إلى Cloudinary.
 * السرّ محفوظ على الخادم (settings.CLOUDINARY_STORAGE) — لا يُعرَّض للمتصفح.
 * أي موقع يستدعي uploadFile يستفيد تلقائياً من السحابة المضبوطة على الخادم.
 */
/**
 * نطاق الرفع: بلا قيمة يُنسب الملف لشركة الترويسة النشطة، و`platform` يجعله
 * أصلاً منصّياً بلا شركة (سوبر أدمن حصراً — من غيره يتجاهله الخادم). صور
 * ملاحظات التطوير مثاله: يرفعها سوبر أدمن وشركةٌ ما نشطةٌ عنده، فنسبُها إليها
 * تحمّل شركةً بريئةً بايتاتٍ لا تراها في تخزينها.
 */
export type UploadScope = 'platform';

export class CloudinaryService {
  /**
   * رفع ملف (صورة أو PDF/داتا شيت) وإرجاع الرابط الآمن.
   */
  async uploadFile(file: File, scope?: UploadScope): Promise<string> {
    const formData = new FormData();
    formData.append('file', file);
    if (scope) {
      formData.append('scope', scope);
    }

    const data = await apiPostFormData<{ url?: string }>('media/upload/', formData);
    if (!data?.url) {
      throw new Error('فشل في الرفع: لم يُعَد رابط الملف');
    }
    return data.url;
  }

  /** توافق مع الشيفرة القديمة */
  async uploadImage(file: File, scope?: UploadScope): Promise<string> {
    return this.uploadFile(file, scope);
  }

  /**
   * رفع عدة ملفات
   */
  async uploadMultipleFiles(files: File[], scope?: UploadScope): Promise<string[]> {
    const uploadPromises = files.map(file => this.uploadFile(file, scope));
    return Promise.all(uploadPromises);
  }

  /** Alias للتوافق مع الشيفرة القديمة */
  uploadMultipleImages = this.uploadMultipleFiles;
}

export const cloudinaryService = new CloudinaryService();
