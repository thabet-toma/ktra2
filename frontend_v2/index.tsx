// index.tsx - تحديث المسارات
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import App from './App';
import PublicGallery from './components/PublicGallery';
import AboutUs from './components/AboutUs';
import Contact from './components/pages/Contact';
import DepartmentModal from './components/pages/DepartmentModal';
import { PublicLayout } from './components/layout/PublicLayout';
import { StorePage } from './components/store/StorePage';
import { ProductDetailPage } from './components/store/ProductDetailPage'; // استيراد صفحة التفاصيل

import { AuthProvider } from './contexts/AuthContext';
import { CompanyProvider } from './contexts/CompanyContext';
import { ThemeProvider } from './contexts/ThemeContext';

import './styles/index.css';

// عند تفعيل Service Worker جديد (بناء أحدث) أعِد تحميل الصفحة مرة واحدة كي يعمل
// المستخدم دائماً على آخر كود — بلا مسح كاش يدوي. الحارس يمنع حلقة إعادة التحميل،
// ولا يُعاد التحميل عند أول تثبيت (لا يوجد controller سابق).
if ('serviceWorker' in navigator) {
  let _swReloaded = false;
  // أعِد التحميل فقط عند *تحديث* (كان هناك controller أصلاً)، لا عند أول تثبيت.
  const _hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (_swReloaded || !_hadController) return;
    _swReloaded = true;
    window.location.reload();
  });
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error("Could not find root element to mount to");
}

const root = ReactDOM.createRoot(rootElement);
root.render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        {/* مسار App للوحة التحكم والتطبيق الداخلي */}
        <Route path="/*" element={<AuthProvider><CompanyProvider><ThemeProvider><App /></ThemeProvider></CompanyProvider></AuthProvider>} />

        {/* الصفحات العامة */}
        <Route path="/store" element={<StorePage />} />
        <Route path="/store/product/:id" element={<ProductDetailPage />} />

        {/* باقي الصفحات العامة مع PublicLayout */}
        <Route element={<PublicLayout />}>
          <Route path="/about-us" element={<AboutUs />} />
          <Route path="/gallery" element={<PublicGallery />} />
          <Route path="/public-gallery" element={<PublicGallery />} />

          {/* صفحة اتصل بنا مع المودال الخاص بها */}
          <Route path="/contact" element={<Contact />}>
            <Route path=":departmentId" element={<DepartmentModal />} />
          </Route>
        </Route>

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);