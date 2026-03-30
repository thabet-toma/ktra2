import { cloudinaryService } from './cloudinaryService';

export interface UploadedFile {
    name: string;
    url: string;
    size: number;
    type: string;
}

/** رفع الملفات عبر Cloudinary — بدون Firebase */
export const firebaseStorageService = {
    async uploadFile(file: File, _folder: string = 'invoice-pdfs'): Promise<UploadedFile> {
        try {
            const url = await cloudinaryService.uploadFile(file);
            return {
                name: file.name,
                url,
                size: file.size,
                type: file.type
            };
        } catch (error) {
            console.error('Error uploading file:', error);
            throw new Error('فشل رفع الملف');
        }
    },

    async uploadPdfFile(file: File): Promise<UploadedFile> {
        if (file.type !== 'application/pdf') {
            throw new Error('يسمح فقط بملفات PDF');
        }
        return this.uploadFile(file, 'invoice-pdfs');
    }
};
