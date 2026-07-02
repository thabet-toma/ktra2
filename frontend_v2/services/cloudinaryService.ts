import { apiPostFormData } from './restApi';

/**
 * رفع الملفات عبر خادم KTRA (‎/api/media/upload/‎) إلى Cloudinary.
 * السرّ محفوظ على الخادم (settings.CLOUDINARY_STORAGE) — لا يُعرَّض للمتصفح.
 * أي موقع يستدعي uploadFile يستفيد تلقائياً من السحابة المضبوطة على الخادم.
 */
export class CloudinaryService {
  /**
   * رفع ملف (صورة أو PDF/داتا شيت) وإرجاع الرابط الآمن.
   */
  async uploadFile(file: File): Promise<string> {
    const formData = new FormData();
    formData.append('file', file);

    const data = await apiPostFormData<{ url?: string }>('media/upload/', formData);
    if (!data?.url) {
      throw new Error('فشل في الرفع: لم يُعَد رابط الملف');
    }
    return data.url;
  }

  /** توافق مع الشيفرة القديمة */
  async uploadImage(file: File): Promise<string> {
    return this.uploadFile(file);
  }

  /**
   * رفع عدة ملفات
   */
  async uploadMultipleFiles(files: File[]): Promise<string[]> {
    const uploadPromises = files.map(file => this.uploadFile(file));
    return Promise.all(uploadPromises);
  }

  /** Alias للتوافق مع الشيفرة القديمة */
  uploadMultipleImages = this.uploadMultipleFiles;
}

export const cloudinaryService = new CloudinaryService();
