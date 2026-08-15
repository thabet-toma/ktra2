// index.tsx - تحديث المسارات
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import App from './App';

import { AuthProvider } from './contexts/AuthContext';
import { CompanyProvider } from './contexts/CompanyContext';
import { useCompany } from './contexts/CompanyContext';
import { useAuth } from './contexts/AuthContext';
import { FirstCompanyOnboarding } from './components/onboarding/FirstCompanyOnboarding';
import { LoadingSpinner } from './components/LoadingSpinner';
import { ConfirmProvider } from './contexts/ConfirmContext';
import { ToastProvider } from './contexts/ToastContext';
import { ThemeProvider, applyThemeOnBoot } from './contexts/ThemeContext';
import { AppearanceProvider } from './contexts/AppearanceContext';
import { SessionSettingsProvider } from './contexts/SessionSettingsContext';
import { PriceVisibilityProvider } from './contexts/PriceVisibilityContext';
import { PermissionsProvider } from './contexts/PermissionsContext';
import { applySkinOnBoot } from './styles/skin';

import './styles/index.css';

applySkinOnBoot();
applyThemeOnBoot();

// المتجر العام: خارج `AuthProvider`/`CompanyProvider` عمداً — زائرٌ بلا جلسة لا
// ينتظر إقلاع مساحة عمل لا تخصّه، ولا يحمّل chunk لوحة التحكم كي يرى صنفاً.
// `ToastProvider` وحده مطلوب هنا (نسخ الرابط)، وهو قانون المشروع بدل `alert`.
const StoreIndexPage = React.lazy(() => import('./components/store/StoreIndexPage').then((module) => ({ default: module.StoreIndexPage })));
const StorefrontPage = React.lazy(() => import('./components/store/StorefrontPage').then((module) => ({ default: module.StorefrontPage })));
const StoreProductPage = React.lazy(() => import('./components/store/StoreProductPage').then((module) => ({ default: module.StoreProductPage })));

const PublicStoreShell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <ToastProvider>{children}</ToastProvider>
);

/** `/store` وحده: صفحة تعريف، أو تحويلٌ إلى متجر المجموعة إن ضُبط في البيئة. */
const StoreIndexRoute: React.FC = () => {
  const fallbackSlug = String(import.meta.env.VITE_DEFAULT_STORE_SLUG || '').trim();
  if (fallbackSlug) return <Navigate to={`/store/${encodeURIComponent(fallbackSlug)}`} replace />;
  return <StoreIndexPage />;
};

// شاشات المتجر لا تعرف المسارات ولا تستورد `react-router`: المحوِّلان هنا
// يحوّلان معاملات المسار إلى props، فيبقى التوجيه في ملف واحد.
const StorefrontRoute: React.FC = () => {
  const { slug = '' } = useParams();
  const navigate = useNavigate();
  return (
    <StorefrontPage
      slug={slug}
      onOpenProduct={(productId) => navigate(`/store/${encodeURIComponent(slug)}/p/${productId}`)}
    />
  );
};

const StoreProductRoute: React.FC = () => {
  const { slug = '', productId = '' } = useParams();
  const navigate = useNavigate();
  return (
    <StoreProductPage
      slug={slug}
      productId={productId}
      onBack={() => navigate(`/store/${encodeURIComponent(slug)}`)}
    />
  );
};

const ApplicationProviders: React.FC = () => (
  <ThemeProvider>
    <AppearanceProvider>
      <SessionSettingsProvider>
        <PriceVisibilityProvider>
          {/* THA-110: `ToastProvider` فوق `PermissionsProvider` لا تحته — الأخير
              يحتاج `useToast` ليخبر المستخدم أن وضع العرض لم يُحفَظ عبر الأجهزة
              (و`useToast` يرمي بلا مزوّد). توسيعٌ صرف: كل مستهلك قائم يبقى داخله. */}
          <ToastProvider>
            <PermissionsProvider>
              <ConfirmProvider>
                <App />
              </ConfirmProvider>
            </PermissionsProvider>
          </ToastProvider>
        </PriceVisibilityProvider>
      </SessionSettingsProvider>
    </AppearanceProvider>
  </ThemeProvider>
);

const ApplicationBoundary: React.FC = () => {
  const location = useLocation();
  const { currentUser, loading: authLoading } = useAuth();
  const { companies, currentCompany, loading: companiesLoading, error, refreshCompanies } = useCompany();

  if (authLoading || (currentUser && companiesLoading)) {
    return <div dir="rtl" className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900"><div className="text-center"><LoadingSpinner /><p className="mt-4 text-sm text-gray-600 dark:text-gray-300">جاري تجهيز مساحة العمل...</p></div></div>;
  }

  if (currentUser && error) {
    return (
      <div dir="rtl" className="flex min-h-screen items-center justify-center bg-gray-50 px-4 dark:bg-gray-900">
        <div className="w-full max-w-md rounded-2xl border border-red-200 bg-white p-6 text-center shadow-xl dark:border-red-900 dark:bg-gray-800">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">تعذّر تحميل مساحة العمل</h1>
          <p className="mt-3 text-sm leading-6 text-gray-600 dark:text-gray-300">{error}</p>
          <button type="button" onClick={() => void refreshCompanies()} className="mt-6 rounded-xl bg-blue-600 px-6 py-3 font-bold text-white transition hover:bg-blue-700">إعادة المحاولة</button>
        </div>
      </div>
    );
  }

  const accountantTenantlessPath =
    location.pathname.startsWith('/accountant/profile') ||
    location.pathname.startsWith('/accountant/engagements');

  if (currentUser && companies.length === 0 && !accountantTenantlessPath) {
    return <FirstCompanyOnboarding />;
  }

  if (currentUser && !currentCompany && !accountantTenantlessPath) {
    return null;
  }

  return <ApplicationProviders />;
};

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
          <Route path="/*" element={<AuthProvider><CompanyProvider><ApplicationBoundary /></CompanyProvider></AuthProvider>} />

          {/* الصفحات العامة المنفصلة بالكامل */}
          <Route path="/store" element={<PublicStoreShell><StoreIndexRoute /></PublicStoreShell>} />
          <Route path="/store/:slug" element={<PublicStoreShell><StorefrontRoute /></PublicStoreShell>} />
          <Route path="/store/:slug/p/:productId" element={<PublicStoreShell><StoreProductRoute /></PublicStoreShell>} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </React.Suspense>
    </BrowserRouter>
  </React.StrictMode>
);
