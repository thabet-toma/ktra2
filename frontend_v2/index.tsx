// index.tsx - تحديث المسارات
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import App from './App';

import { AuthProvider } from './contexts/AuthContext';
import { CompanyProvider } from './contexts/CompanyContext';
import { ConfirmProvider } from './contexts/ConfirmContext';
import { ToastProvider } from './contexts/ToastContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { AppearanceProvider } from './contexts/AppearanceContext';
import { PriceVisibilityProvider } from './contexts/PriceVisibilityContext';

import './styles/index.css';

const StorePage = React.lazy(() => import('./components/store/StorePage').then((module) => ({ default: module.StorePage })));
const ProductDetailPage = React.lazy(() => import('./components/store/ProductDetailPage').then((module) => ({ default: module.ProductDetailPage })));

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
      <React.Suspense fallback={<div className="min-h-screen flex items-center justify-center">جاري التحميل...</div>}>
        <Routes>
          {/* مسار App للوحة التحكم والتطبيق الداخلي */}
          <Route path="/*" element={<AuthProvider><CompanyProvider><ThemeProvider><AppearanceProvider><PriceVisibilityProvider><ConfirmProvider><ToastProvider><App /></ToastProvider></ConfirmProvider></PriceVisibilityProvider></AppearanceProvider></ThemeProvider></CompanyProvider></AuthProvider>} />

          {/* الصفحات العامة المنفصلة بالكامل */}
          <Route path="/store" element={<StorePage />} />
          <Route path="/store/product/:id" element={<ProductDetailPage />} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </React.Suspense>
    </BrowserRouter>
  </React.StrictMode>
);
