import axios from 'axios';

const CLOUDINARY_UPLOAD_PRESET = process.env.REACT_APP_CLOUDINARY_UPLOAD_PRESET || '';
const CLOUDINARY_CLOUD_NAME = process.env.REACT_APP_CLOUDINARY_CLOUD_NAME || '';

const cloudinaryService = {
    uploadImage: async (file) => {
        if (!CLOUDINARY_CLOUD_NAME || !CLOUDINARY_UPLOAD_PRESET) {
            throw new Error("بيانات Cloudinary غير مكتملة في ملف .env الكلاود نيم او البريسيت");
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('upload_preset', CLOUDINARY_UPLOAD_PRESET);

        console.log("Attempting Cloudinary Upload with:", {
            cloudName: CLOUDINARY_CLOUD_NAME,
            preset: CLOUDINARY_UPLOAD_PRESET
        });

        try {
            const response = await axios.post(
                `https://api.cloudinary.com/v1_1/${CLOUDINARY_CLOUD_NAME}/image/upload`,
                formData
            );
            return {
                url: response.data.secure_url,
                public_id: response.data.public_id
            };
        } catch (error) {
            console.error("Cloudinary Upload Error:", error);
            throw error;
        }
    },

    uploadFile: async (file) => {
        if (!CLOUDINARY_CLOUD_NAME || !CLOUDINARY_UPLOAD_PRESET) {
            throw new Error("Cloudinary configuration missing");
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('upload_preset', CLOUDINARY_UPLOAD_PRESET);

        try {
            const response = await axios.post(
                `https://api.cloudinary.com/v1_1/${CLOUDINARY_CLOUD_NAME}/auto/upload`,
                formData
            );
            return {
                url: response.data.secure_url,
                public_id: response.data.public_id
            };
        } catch (error) {
            console.error("Cloudinary Upload Error:", error);
            throw error;
        }
    }
};

export default cloudinaryService;
