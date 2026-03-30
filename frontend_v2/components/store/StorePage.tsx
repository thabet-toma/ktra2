// components/store/StorePage.tsx
import React, { useEffect, useState, useCallback } from 'react';
import { ProductCard } from './ProductCard';
import { Item, User } from '../../types';
import { itemsService } from '../../services/firestoreService';
import { loginWithGoogle, logoutUser, fetchUserProfile } from '../../services/authService';
import { LoadingSpinner } from '../LoadingSpinner';
import {
    LogIn, LogOut, ShoppingBag, Home, Search, Filter,
    Menu, X, Bell, User as UserIcon, ShoppingCart,
    ChevronDown, Globe, Phone, Mail, Instagram, Facebook
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

export const StorePage: React.FC = () => {
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [authLoading, setAuthLoading] = useState(false);
    const [currentUser, setCurrentUser] = useState<User | null>(null);
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState<string>('');
    const [showFilters, setShowFilters] = useState(false);
    const navigate = useNavigate();

    // تحميل العناصر
    useEffect(() => {
        const unsubscribe = itemsService.subscribeToActiveItems((fetchedItems) => {
            setItems(fetchedItems);
            setLoading(false);
        });
        return () => unsubscribe();
    }, []);

    // استخراج الفئات الفريدة
    const categories = Array.from(new Set(items.map(item => item.categoryName))).filter(Boolean);

    // فلترة العناصر
    const filteredItems = items.filter(item => {
        const matchesSearch = searchQuery === '' ||
            item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            item.specifications.toLowerCase().includes(searchQuery.toLowerCase()) ||
            (item.modelNumber && item.modelNumber.toLowerCase().includes(searchQuery.toLowerCase()));

        const matchesCategory = selectedCategory === '' || item.categoryName === selectedCategory;

        return matchesSearch && matchesCategory;
    });

    // في StorePage.tsx، عدل دالة handleGoogleLogin:
    const handleGoogleLogin = async () => {
        setAuthLoading(true);
        try {
            const firebaseUser = await loginWithGoogle();
            // firebaseUser هنا سيكون UserCredential أو User من Firebase Auth
            // في حال كان loginWithGoogle يرجع UserCredential:
            if (firebaseUser && firebaseUser.id) {
                const userProfile = await fetchUserProfile(firebaseUser.id);
                if (userProfile) {
                    setCurrentUser(userProfile);
                }
            }
        } catch (error: any) {
            console.error("Google Login Error:", error);
            if (error.code === 'auth/operation-not-allowed') {
                alert("عذراً، خدمة الدخول عبر جوجل غير مفعلة حالياً.\n(للإدارة: يرجى تفعيل Google Auth Provider من لوحة تحكم Firebase)");
            } else if (error.code === 'auth/popup-closed-by-user') {
                // User closed popup, do nothing
            } else {
                alert("حدث خطأ أثناء تسجيل الدخول: " + (error.message || "خطأ غير معروف"));
            }
        } finally {
            setAuthLoading(false);
        }
    };

    const handleLogout = async () => {
        await logoutUser();
        setCurrentUser(null);
        navigate('/');
    };

    const resetFilters = useCallback(() => {
        setSearchQuery('');
        setSelectedCategory('');
        setShowFilters(false);
    }, []);

    if (loading) return <LoadingSpinner />;

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900" dir="rtl">
            {/* Top Bar - Mobile First */}
            <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white">
                <div className="max-w-7xl mx-auto px-4 py-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Phone className="w-4 h-4" />
                            <span className="text-sm">٠٧٩-١٢٣٤٥٦٧</span>
                        </div>
                        <div className="flex items-center gap-4">
                            <Link to="/contact" className="text-sm hover:underline hidden sm:block">
                                تواصل معنا
                            </Link>
                            <div className="flex gap-3">
                                <a href="#" className="hover:text-blue-200">
                                    <Instagram className="w-4 h-4" />
                                </a>
                                <a href="#" className="hover:text-blue-200">
                                    <Facebook className="w-4 h-4" />
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Header */}
            <header className="bg-white dark:bg-gray-800 shadow-sm sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-4 py-4">
                    <div className="flex items-center justify-between">
                        {/* Logo and Hamburger */}
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                                className="lg:hidden p-2 text-gray-700 dark:text-gray-300"
                            >
                                {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
                            </button>

                            <Link to="/" className="flex items-center gap-2">
                                <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
                                    <ShoppingBag className="w-6 h-6 text-white" />
                                </div>
                                <div>
                                    <h1 className="text-xl font-bold text-gray-900 dark:text-white">المتجر</h1>
                                    <p className="text-xs text-gray-500 dark:text-gray-400">K.T.R.A العالمية</p>
                                </div>
                            </Link>
                        </div>

                        {/* Desktop Navigation */}
                        <nav className="hidden lg:flex items-center gap-6">
                            <Link to="/store" className="text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                المتجر
                            </Link>
                            <Link to="/gallery" className="text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                معرض الصور
                            </Link>
                            <Link to="/about-us" className="text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                عن الشركة
                            </Link>
                            <Link to="/contact" className="text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                اتصل بنا
                            </Link>
                        </nav>

                        {/* Auth & Actions */}
                        <div className="flex items-center gap-3">
                            <div className="relative hidden sm:block">
                                <input
                                    type="text"
                                    placeholder="ابحث عن منتج..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="w-64 px-4 py-2 pr-10 bg-gray-100 dark:bg-gray-700 rounded-lg text-sm border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                            </div>

                            {currentUser ? (
                                <div className="flex items-center gap-3">
                                    <div className="hidden sm:flex items-center gap-2">
                                        <div className="w-8 h-8 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center">
                                            <UserIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                            {currentUser.name}
                                        </span>
                                    </div>
                                    <button
                                        onClick={handleLogout}
                                        className="hidden sm:flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors"
                                    >
                                        <LogOut className="w-4 h-4" />
                                        خروج
                                    </button>
                                </div>
                            ) : (
                                <button
                                    onClick={handleGoogleLogin}
                                    disabled={authLoading}
                                    className="hidden sm:flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-all"
                                >
                                    {authLoading ? <LoadingSpinner size="sm" /> : <LogIn className="w-4 h-4" />}
                                    تسجيل دخول
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Mobile Search */}
                    <div className="mt-4 sm:hidden">
                        <div className="relative">
                            <input
                                type="text"
                                placeholder="ابحث عن منتج..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full px-4 py-3 pr-10 bg-gray-100 dark:bg-gray-700 rounded-xl text-sm border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                        </div>
                    </div>
                </div>
            </header>

            {/* Mobile Menu */}
            {mobileMenuOpen && (
                <div className="lg:hidden bg-white dark:bg-gray-800 shadow-lg z-40">
                    <div className="px-4 py-6 space-y-4">
                        <nav className="space-y-3">
                            <Link to="/store" className="block py-2 text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                المتجر
                            </Link>
                            <Link to="/gallery" className="block py-2 text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                معرض الصور
                            </Link>
                            <Link to="/about-us" className="block py-2 text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                عن الشركة
                            </Link>
                            <Link to="/contact" className="block py-2 text-gray-700 dark:text-gray-300 hover:text-blue-600 font-medium">
                                اتصل بنا
                            </Link>
                        </nav>

                        <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                            {currentUser ? (
                                <div className="space-y-3">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center">
                                            <UserIcon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <div>
                                            <p className="font-medium text-gray-900 dark:text-white">{currentUser.name}</p>
                                            <p className="text-sm text-gray-500">{currentUser.email}</p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={handleLogout}
                                        className="w-full flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors"
                                    >
                                        <LogOut className="w-5 h-5" />
                                        تسجيل الخروج
                                    </button>
                                </div>
                            ) : (
                                <button
                                    onClick={handleGoogleLogin}
                                    disabled={authLoading}
                                    className="w-full flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
                                >
                                    {authLoading ? <LoadingSpinner size="sm" /> : <LogIn className="w-5 h-5" />}
                                    تسجيل دخول
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Filters Bar */}
            <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                <div className="max-w-7xl mx-auto px-4 py-3">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                                المنتجات ({filteredItems.length})
                            </h2>
                            <button
                                onClick={() => setShowFilters(!showFilters)}
                                className="sm:hidden flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400"
                            >
                                <Filter className="w-4 h-4" />
                                تصفية
                            </button>
                        </div>

                        <div className={`${showFilters ? 'flex' : 'hidden'} sm:flex flex-col sm:flex-row gap-3`}>
                            {/* Category Filter */}
                            {categories.length > 0 && (
                                <div className="relative">
                                    <select
                                        value={selectedCategory}
                                        onChange={(e) => setSelectedCategory(e.target.value)}
                                        className="w-full sm:w-auto px-4 py-2 bg-gray-100 dark:bg-gray-700 rounded-lg text-sm border border-gray-200 dark:border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none"
                                    >
                                        <option value="">كل الفئات</option>
                                        {categories.map(category => (
                                            <option key={category} value={category}>
                                                {category}
                                            </option>
                                        ))}
                                    </select>
                                    <ChevronDown className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                                </div>
                            )}

                            {/* Reset Filters */}
                            {(searchQuery || selectedCategory) && (
                                <button
                                    onClick={resetFilters}
                                    className="px-4 py-2 text-sm text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-900/20 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                                >
                                    إلغاء الفلترة
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-4 py-6">
                {filteredItems.length === 0 ? (
                    <div className="text-center py-12">
                        <ShoppingBag className="w-20 h-20 text-gray-300 dark:text-gray-600 mx-auto mb-6" />
                        <h3 className="text-xl font-bold text-gray-700 dark:text-gray-300 mb-2">
                            {searchQuery || selectedCategory ? 'لم يتم العثور على منتجات' : 'لا توجد منتجات حالياً'}
                        </h3>
                        <p className="text-gray-500 dark:text-gray-400 mb-6">
                            {searchQuery || selectedCategory
                                ? 'جرب استخدام كلمات بحث أخرى أو إلغاء الفلترة'
                                : 'يرجى العودة لاحقاً'}
                        </p>
                        {(searchQuery || selectedCategory) && (
                            <button
                                onClick={resetFilters}
                                className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
                            >
                                عرض كل المنتجات
                            </button>
                        )}
                    </div>
                ) : (
                    <>
                        {/* Product Grid */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-6">
                            {filteredItems.map((item) => (
                                <ProductCard key={item.id} item={item} />
                            ))}
                        </div>

                        {/* Load More / Pagination (يمكن تطويره لاحقاً) */}
                        {filteredItems.length > 12 && (
                            <div className="mt-12 text-center">
                                <button className="px-6 py-3 bg-white dark:bg-gray-800 border-2 border-blue-600 text-blue-600 dark:text-blue-400 font-medium rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors">
                                    عرض المزيد
                                </button>
                            </div>
                        )}
                    </>
                )}
            </main>

            {/* Footer */}
            <footer className="bg-gray-900 text-white mt-12">
                <div className="max-w-7xl mx-auto px-4 py-12">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
                        {/* Company Info */}
                        <div>
                            <div className="flex items-center gap-2 mb-4">
                                <Globe className="w-6 h-6" />
                                <h3 className="text-xl font-bold">K.T.R.A العالمية</h3>
                            </div>
                            <p className="text-gray-400 text-sm">
                                أكثر من 20 سنة خبرة في مجال التجارة الدولية والاستيراد والتصدير.
                            </p>
                        </div>

                        {/* Quick Links */}
                        <div>
                            <h4 className="text-lg font-bold mb-4">روابط سريعة</h4>
                            <ul className="space-y-2">
                                <li><Link to="/store" className="text-gray-400 hover:text-white transition-colors">المتجر</Link></li>
                                <li><Link to="/about-us" className="text-gray-400 hover:text-white transition-colors">عن الشركة</Link></li>
                                <li><Link to="/gallery" className="text-gray-400 hover:text-white transition-colors">معرض الصور</Link></li>
                                <li><Link to="/contact" className="text-gray-400 hover:text-white transition-colors">اتصل بنا</Link></li>
                            </ul>
                        </div>

                        {/* Contact Info */}
                        <div>
                            <h4 className="text-lg font-bold mb-4">تواصل معنا</h4>
                            <ul className="space-y-3">
                                <li className="flex items-center gap-2 text-gray-400">
                                    <Phone className="w-4 h-4" />
                                    <span>٠٧٩-١٢٣٤٥٦٧</span>
                                </li>
                                <li className="flex items-center gap-2 text-gray-400">
                                    <Mail className="w-4 h-4" />
                                    <span>info@ktra.com</span>
                                </li>
                            </ul>
                        </div>

                        {/* Social Media */}
                        <div>
                            <h4 className="text-lg font-bold mb-4">تابعنا</h4>
                            <div className="flex gap-4">
                                <a href="#" className="w-10 h-10 bg-blue-600 rounded-full flex items-center justify-center hover:bg-blue-700 transition-colors">
                                    <Facebook className="w-5 h-5" />
                                </a>
                                <a href="#" className="w-10 h-10 bg-pink-600 rounded-full flex items-center justify-center hover:bg-pink-700 transition-colors">
                                    <Instagram className="w-5 h-5" />
                                </a>
                            </div>
                        </div>
                    </div>

                    <div className="mt-8 pt-8 border-t border-gray-800 text-center text-gray-400 text-sm">
                        <p>© {new Date().getFullYear()} شركة K.T.R.A للتجارة العالمية. جميع الحقوق محفوظة.</p>
                    </div>
                </div>
            </footer>

            {/* Floating Action Button - Mobile */}
            {!currentUser && (
                <button
                    onClick={handleGoogleLogin}
                    disabled={authLoading}
                    className="fixed bottom-6 right-6 sm:hidden w-14 h-14 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition-colors flex items-center justify-center z-50"
                >
                    {authLoading ? <LoadingSpinner size="sm" /> : <LogIn className="w-6 h-6" />}
                </button>
            )}
        </div>
    );
};