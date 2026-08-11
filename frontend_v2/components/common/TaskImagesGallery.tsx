// TaskImagesGallery.tsx
import React, { useState } from "react";

interface TaskImagesGalleryProps {
  images: string[];
}

export const TaskImagesGallery: React.FC<TaskImagesGalleryProps> = ({ images }) => {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);

  if (!images || images.length === 0) {
    return null;
  }

  // المودال المخصص لعرض الصورة المكبرة (للتأكد من عدم تكرار الكود مع SubmissionItemGallery)
  const ImageModal = ({ imageUrl, onClose, currentIndex, totalImages }: { 
    imageUrl: string, 
    onClose: () => void,
    currentIndex: number,
    totalImages: number
  }) => (
    <div 
      className="fixed inset-0 bg-black bg-opacity-90 z-50 flex items-center justify-center p-4 animate-fade-in"
      onClick={onClose}
    >
      <div className="relative max-w-4xl max-h-full" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onClose}
          className="absolute -top-12 left-0 text-white text-3xl hover:text-gray-300 z-10"
        >
          &times;
        </button>
        <img
          src={imageUrl}
          alt="صورة مكبرة"
          className="max-w-full max-h-[80vh] object-contain rounded-lg"
        />
        <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 text-white bg-black bg-opacity-50 px-3 py-1 rounded-lg text-sm">
          {currentIndex} / {totalImages}
        </div>
      </div>
    </div>
  );

  return (
    <>
      <div className="mt-4">
        <h4 className="font-semibold text-[var(--color-text)] mb-3">
          صور المهمة ({images.length})
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {images.map((imageUrl, index) => (
            <div
              key={index}
              className="relative group cursor-pointer"
              onClick={() => setSelectedImage(imageUrl)}
            >
              <img
                src={imageUrl}
                alt={`صورة المهمة ${index + 1}`}
                className="w-full h-24 object-cover rounded-lg border border-[var(--color-border)] hover:border-blue-500 transition-colors"
              />
              <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-20 transition-all rounded-lg flex items-center justify-center">
                <span className="text-white opacity-0 group-hover:opacity-100 text-2xl">
                  🔍
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* مودال عرض الصورة بالحجم الكامل */}
      {selectedImage && (
        <ImageModal 
          imageUrl={selectedImage}
          onClose={() => setSelectedImage(null)}
          currentIndex={images.indexOf(selectedImage) + 1}
          totalImages={images.length}
        />
      )}
    </>
  );
};