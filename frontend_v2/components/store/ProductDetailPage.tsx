import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Item } from '../../types';
import { itemsService } from '../../services/firestoreService';
import { LoadingSpinner } from '../LoadingSpinner';
import {
    ArrowRight, ShoppingBag, Home, ChevronLeft,
    Package, Tag, Info, Hash, Share2, Printer,
    Heart, CheckCircle2, Layers, BookOpen
} from 'lucide-react';

export const ProductDetailPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [item, setItem] = useState<Item | null>(null);
    const [loading, setLoading] = useState(true);
    const [selectedImageIndex, setSelectedImageIndex] = useState(0);
    const [isFavorite, setIsFavorite] = useState(false);

    useEffect(() => {
        if (!id) {
            navigate('/store');
            return;
        }
        const fetchItem = async () => {
            setLoading(true);
            try {
                const fetchedItem = await itemsService.getItemById(id);
                if (fetchedItem) setItem(fetchedItem);
                else navigate('/store');
            } catch (error) {
                console.error('Error fetching item:', error);
                navigate('/store');
            } finally {
                setLoading(false);
            }
        };
        fetchItem();
    }, [id, navigate]);

    const handleShare = () => {
        const displayName = item?.storeName || item?.name;
        if (navigator.share) {
            navigator.share({
                title: displayName,
                text: item?.storeDescription || item?.specifications,
                url: window.location.href,
            });
        } else {
            navigator.clipboard.writeText(window.location.href);
            alert('تم نسخ الرابط!');
        }
    };

    if (loading) return <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900"><LoadingSpinner /></div>;
    if (!item) return null;

    // تجهيز البيانات للعرض
    const displayName = item.storeName || item.name;
    const displayDescription = item.storeDescription || item.specifications;
    const hasTechnicalSpecs = item.specifications && item.specifications !== item.storeDescription;

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900 pb-24" dir="rtl">
            {/* Header */}
            <header className="bg-white dark:bg-gray-800 shadow-sm sticky top-0 z-40">
                <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-gray-600 dark:text-gray-300">
                        <button onClick={() => navigate('/store')} className="hover:text-blue-600"><ArrowRight className="w-5 h-5" /></button>
                        <span className="h-4 w-px bg-gray-300 dark:bg-gray-600 mx-2"></span>
                        <div className="text-sm flex items-center gap-1 overflow-hidden">
                            <span className="hidden sm:inline">{item.categoryName}</span>
                            {item.subCategoryName && (
                                <>
                                    <span className="text-gray-400">/</span>
                                    <span className="truncate">{item.subCategoryName}</span>
                                </>
                            )}
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={() => setIsFavorite(!isFavorite)} className={`p-2 rounded-full ${isFavorite ? 'text-red-500 bg-red-50' : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}>
                            <Heart className="w-5 h-5" fill={isFavorite ? 'currentColor' : 'none'} />
                        </button>
                        <button onClick={handleShare} className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-full">
                            <Share2 className="w-5 h-5" />
                        </button>
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 py-6">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12">

                    {/* Right Column: Gallery */}
                    <div className="space-y-4">
                        <div className="aspect-square bg-white dark:bg-gray-800 rounded-2xl overflow-hidden shadow-sm border border-gray-100 dark:border-gray-700 relative">
                            <img
                                src={item.imageUrls?.[selectedImageIndex] || '/placeholder-image.png'}
                                alt={displayName}
                                className="w-full h-full object-contain"
                            />
                            {item.brandName && (
                                <div className="absolute top-4 right-4 bg-white/90 dark:bg-gray-800/90 backdrop-blur px-3 py-1 rounded-full text-xs font-bold text-gray-700 dark:text-gray-300 shadow-sm">
                                    {item.brandName}
                                </div>
                            )}
                        </div>
                        {/* Thumbnails */}
                        {item.imageUrls && item.imageUrls.length > 1 && (
                            <div className="grid grid-cols-4 gap-3">
                                {item.imageUrls.map((url, index) => (
                                    <button
                                        key={index}
                                        onClick={() => setSelectedImageIndex(index)}
                                        className={`aspect-square rounded-lg overflow-hidden border-2 transition-all ${selectedImageIndex === index ? 'border-blue-600 ring-2 ring-blue-100' : 'border-transparent hover:border-gray-300'}`}
                                    >
                                        <img src={url} alt="" className="w-full h-full object-cover" />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Left Column: Details */}
                    <div className="flex flex-col">
                        <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700 mb-6">

                            {/* Title & Model */}
                            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-2 leading-tight">
                                {displayName}
                            </h1>
                            <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400 mb-6">
                                {item.modelNumber && (
                                    <span className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs font-mono">
                                        Model: {item.modelNumber}
                                    </span>
                                )}
                                {item.isActive ? (
                                    <span className="flex items-center gap-1 text-green-600 text-xs font-medium">
                                        <CheckCircle2 className="w-3 h-3" /> متوفر في المتجر
                                    </span>
                                ) : (
                                    <span className="text-red-500 text-xs">غير متوفر حالياً</span>
                                )}
                            </div>

                            {/* Price Section */}
                            {item.salePrice && item.salePrice > 0 ? (
                                <div className="mb-6 pb-6 border-b border-gray-100 dark:border-gray-700">
                                    <p className="text-sm text-gray-500 mb-1">سعر البيع</p>
                                    <div className="flex items-baseline gap-2">
                                        <span className="text-4xl font-bold text-blue-600 dark:text-blue-400">
                                            {item.salePrice.toLocaleString()}
                                        </span>
                                        <span className="text-lg text-gray-500 font-medium">ILS</span>
                                    </div>
                                </div>
                            ) : (
                                <div className="mb-6 pb-6 border-b border-gray-100 dark:border-gray-700">
                                    <span className="text-xl font-bold text-gray-400">السعر عند الطلب</span>
                                </div>
                            )}

                            {/* Store Description (Marketing) */}
                            <div className="prose prose-sm dark:prose-invert max-w-none text-gray-600 dark:text-gray-300">
                                <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
                                    <Info className="w-4 h-4" /> وصف المنتج
                                </h3>
                                <p className="whitespace-pre-line leading-relaxed">
                                    {displayDescription}
                                </p>
                            </div>
                        </div>

                        {/* Technical Specs (If different from Store Description) */}
                        <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 shadow-sm border border-gray-100 dark:border-gray-700">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                                <Layers className="w-5 h-5 text-gray-400" />
                                تفاصيل إضافية
                            </h3>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                                <div className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                                    <span className="block text-gray-500 text-xs mb-1">التصنيف الرئيسي</span>
                                    <span className="font-medium text-gray-900 dark:text-white">{item.categoryName}</span>
                                </div>
                                <div className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                                    <span className="block text-gray-500 text-xs mb-1">التصنيف الفرعي</span>
                                    <span className="font-medium text-gray-900 dark:text-white">{item.subCategoryName || '-'}</span>
                                </div>
                                <div className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                                    <span className="block text-gray-500 text-xs mb-1">الماركة</span>
                                    <span className="font-medium text-gray-900 dark:text-white">{item.brandName || '-'}</span>
                                </div>
                                <div className="p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                                    <span className="block text-gray-500 text-xs mb-1">حالة التوفر</span>
                                    <span className={`font-medium ${item.quantity && item.quantity > 0 ? 'text-green-600' : 'text-red-500'}`}>
                                        {item.quantity && item.quantity > 0 ? 'متوفر بالمخزون' : 'نفذت الكمية'}
                                    </span>
                                </div>
                            </div>

                            {/* Full Specifications if available */}
                            {hasTechnicalSpecs && (
                                <div className="mt-6 pt-6 border-t border-gray-100 dark:border-gray-700">
                                    <h4 className="text-sm font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
                                        <BookOpen className="w-4 h-4 text-gray-400" /> المواصفات التقنية
                                    </h4>
                                    <div className="bg-gray-50 dark:bg-gray-900/30 p-4 rounded-lg text-xs sm:text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono leading-relaxed">
                                        {item.specifications}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </main>

            {/* Bottom Sticky Action Bar */}
            <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 p-4 z-50 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)]">
                <div className="max-w-7xl mx-auto flex flex-col sm:flex-row gap-3 items-center justify-between">
                    <div className="hidden sm:block">
                        <p className="text-xs text-gray-500">السعر النهائي</p>
                        <p className="text-xl font-bold text-blue-600 dark:text-blue-400">
                            {item.salePrice ? `${item.salePrice.toLocaleString()} ILS` : 'السعر عند الطلب'}
                        </p>
                    </div>

                    <div className="flex gap-3 w-full sm:w-auto">
                        <button
                            onClick={() => window.print()}
                            className="px-4 py-3 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-gray-200 transition-colors"
                        >
                            <Printer className="w-5 h-5" />
                            <span className="hidden sm:inline">طباعة</span>
                        </button>
                        <Link
                            to="/contact"
                            className="flex-1 sm:flex-none px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-500/30"
                        >
                            <ShoppingBag className="w-5 h-5" />
                            تواصل للطلب
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
};