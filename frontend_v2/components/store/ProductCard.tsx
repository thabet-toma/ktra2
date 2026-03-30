import React from 'react';
import { Item } from '../../types';
import { Link } from 'react-router-dom';
import { Eye, Share2, Tag } from 'lucide-react';

interface ProductCardProps {
    item: Item;
}

export const ProductCard: React.FC<ProductCardProps> = ({ item }) => {
    // تحديد البيانات المراد عرضها (المتجر أولاً، ثم البيانات الأصلية)
    const displayName = item.storeName || item.name;
    const displayDescription = item.storeDescription || item.specifications;

    const handleShare = (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        const url = `${window.location.origin}/store/product/${item.id}`;

        if (navigator.share) {
            navigator.share({
                title: displayName,
                text: displayDescription,
                url: url,
            });
        } else {
            navigator.clipboard.writeText(url);
            alert('تم نسخ رابط المنتج!');
        }
    };

    return (
        <Link
            to={`/store/product/${item.id}`}
            className="group bg-white dark:bg-gray-800 rounded-2xl shadow-sm hover:shadow-xl transition-all duration-300 border border-gray-100 dark:border-gray-700 flex flex-col h-full overflow-hidden"
        >
            {/* Image Container */}
            <div className="relative h-56 sm:h-64 overflow-hidden bg-gray-50 dark:bg-gray-900">
                <img
                    src={item.imageUrls?.[0] || '/placeholder-image.png'}
                    alt={displayName}
                    className="w-full h-full object-cover transform group-hover:scale-110 transition-transform duration-500"
                    loading="lazy"
                />

                {/* Overlay */}
                <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

                {/* Price Tag (If exists) */}
                {item.salePrice && item.salePrice > 0 && (
                    <div className="absolute bottom-3 right-3 bg-white/95 dark:bg-gray-800/95 backdrop-blur-sm px-3 py-1.5 rounded-lg shadow-lg flex items-center gap-1">
                        <span className="text-sm font-bold text-gray-900 dark:text-white">
                            {item.salePrice.toLocaleString()}
                        </span>
                        <span className="text-xs text-gray-500">ILS</span>
                    </div>
                )}

                {/* Share Button */}
                <button
                    onClick={handleShare}
                    className="absolute top-3 left-3 p-2 bg-white/90 dark:bg-gray-800/90 rounded-full shadow-sm opacity-0 group-hover:opacity-100 transition-all duration-300 hover:bg-blue-50 hover:text-blue-600"
                >
                    <Share2 className="w-4 h-4" />
                </button>
            </div>

            {/* Content */}
            <div className="p-4 flex flex-col flex-grow">
                {/* Categories & Brand Badges */}
                <div className="flex flex-wrap gap-2 mb-2 text-[10px] sm:text-xs">
                    {item.brandName && (
                        <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-md font-medium">
                            {item.brandName}
                        </span>
                    )}
                    <span className="px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-md">
                        {item.categoryName}
                    </span>
                </div>

                {/* Title */}
                <h3 className="text-lg font-bold text-gray-900 dark:text-white line-clamp-2 mb-2 group-hover:text-blue-600 transition-colors" title={displayName}>
                    {displayName}
                </h3>

                {/* Description */}
                <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-4 flex-grow">
                    {displayDescription}
                </p>

                {/* Footer Info */}
                <div className="pt-3 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between mt-auto">
                    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                        {item.modelNumber && (
                            <span className="flex items-center gap-1">
                                <Tag className="w-3 h-3" />
                                {item.modelNumber}
                            </span>
                        )}
                    </div>

                    <div className="flex items-center gap-1 text-blue-600 dark:text-blue-400 text-xs font-bold">
                        <span>عرض التفاصيل</span>
                        <Eye className="w-3 h-3" />
                    </div>
                </div>
            </div>
        </Link>
    );
};