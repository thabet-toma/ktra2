import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Home, Users, Phone, Images } from 'lucide-react';
import { LogoIcon } from '../icons/LogoIcon'; // تأكد من المسار الصحيح للأيقونة

export const PublicNavbar = () => {
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path
      ? "text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-white/10"
      : "text-gray-600 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-white/5";
  };

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 px-6 py-4 flex justify-between items-center bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-b border-gray-200/50 dark:border-gray-700/50 shadow-sm transition-all duration-300" dir="rtl">
      {/* الجزء الأيمن: الشعار */}
      <Link to="/" className="flex items-center gap-3 group">
        <div className="bg-gradient-to-tr from-blue-600 to-purple-600 p-2 rounded-lg shadow-lg group-hover:scale-105 transition-transform">
          {/* تأكد من وجود LogoIcon أو استبدله بـ <Building2 /> من lucide-react */}
          <LogoIcon className="w-6 h-6 text-white" />
        </div>
        <span className="text-xl font-bold bg-gradient-to-r from-blue-700 to-purple-700 dark:from-blue-400 dark:to-purple-400 bg-clip-text text-transparent hidden sm:block">
          K.T.R.A
        </span>
      </Link>

      {/* الجزء الأيسر: الروابط */}
      <div className="flex items-center gap-1 md:gap-2 bg-gray-100/50 dark:bg-gray-800/50 p-1.5 rounded-full border border-gray-200/50 dark:border-gray-700/50 backdrop-blur-sm">
        <Link to="/" className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all duration-300 font-medium text-sm md:text-base ${isActive('/')}`}>
          <Home className="w-4 h-4" />
          <span className="hidden md:inline">Home</span>
        </Link>

        <Link to="/about-us" className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all duration-300 font-medium text-sm md:text-base ${isActive('/about-us')}`}>
          <Users className="w-4 h-4" />
          <span className="hidden md:inline">About Us</span>
        </Link>

        <Link to="/contact" className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all duration-300 font-medium text-sm md:text-base ${isActive('/contact')}`}>
          <Phone className="w-4 h-4" />
          <span className="hidden md:inline">Contact Us</span>
        </Link>

        {/* إذا كان لديك معرض صور */}
        <Link to="/gallery" className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all duration-300 font-medium text-sm md:text-base ${isActive('/gallery')}`}>
          <Images className="w-4 h-4" />
          <span className="hidden md:inline">Gallery</span>
        </Link>
        <Link to="/store" className={`flex items-center gap-2 px-4 py-2 rounded-full transition-all duration-300 font-medium text-sm md:text-base ${isActive('/store')}`}>
          <Images className="w-4 h-4" />
          Store
        </Link>
      </div>
    </nav>
  );
};