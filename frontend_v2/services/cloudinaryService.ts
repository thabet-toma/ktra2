export class CloudinaryService {
  private readonly cloudName = 'dc66alhhk';
  private readonly uploadPreset = 'kitra_66';
  private readonly folder = 'Smart_product_system_KTRA';

  /**
   * رفع ملف (صورة أو PDF) وإرجاع الرابط
   */
  async uploadFile(file: File): Promise<string> {
    const formData = new FormData();

    // تحديد نوع المورد والمجلد بناءً على نوع الملف
    let resourceType = 'auto'; // القيمة الافتراضية
    let subFolder = 'others';

    if (file.type.startsWith('image/')) {
      resourceType = 'image';
      subFolder = 'images';
    } else if (file.type === 'application/pdf') {
      // ✅ للملفات غير الصور، يفضل استخدام raw أو تحديدها بدقة لتجنب مشاكل الـ Unsigned
      resourceType = 'raw';
      subFolder = 'documents';
    }

    formData.append('file', file);
    formData.append('upload_preset', this.uploadPreset);
    // ملاحظة: الـ Unsigned upload قد يرفض تحديد المجلد (folder) إذا لم يكن مسموحاً به في إعدادات الـ Preset 
    // إذا استمر الخطأ، جرب تعطيل سطر الـ folder مؤقتاً للتأكد
    formData.append('folder', `${this.folder}/${subFolder}`);

    try {
      // ✅ نستخدم resourceType المتغير هنا (image أو raw أو auto)
      const response = await fetch(
        `https://api.cloudinary.com/v1_1/${this.cloudName}/${resourceType}/upload`,
        {
          method: 'POST',
          body: formData, // لا تضع Headers يدوية مثل Content-Type، المتصفح سيتكفل بها مع FormData
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        console.error("Cloudinary Detailed Error:", errorData);
        throw new Error(`فشل في الرفع: ${errorData.error?.message || response.status}`);
      }

      const data = await response.json();
      return data.secure_url || data.url;

    } catch (error) {
      console.error('خطأ في رفع الملف:', error);
      throw error;
    }
  }
  /**
   * دالة للإبقاء على التوافق مع الكود القديم إذا كان مستخدماً في أماكن أخرى
   * (يمكنك استخدام uploadFile مباشرة للكل)
   */
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