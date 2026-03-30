import React from 'react';
import { X } from 'lucide-react';

export const ImagePreviewModal = ({ url, onClose }: { url: string | null, onClose: () => void }) => {
    if (!url) return null;
    return (
        <div
            className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-4 animate-in fade-in duration-200"
            onClick={onClose}
        >
            <button
                className="absolute top-4 right-4 text-white p-2 hover:bg-white/20 rounded-full transition-colors"
                onClick={onClose}
            >
                <X className="w-8 h-8" />
            </button>
            <img
                src={url}
                alt="Full size"
                className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
                onClick={(e) => e.stopPropagation()}
            />
        </div>
    );
};
