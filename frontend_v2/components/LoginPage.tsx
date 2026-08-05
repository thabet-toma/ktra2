import React, { useState } from 'react';
import { LogoIcon } from './icons/LogoIcon';
import { loginUser, resendVerificationEmail, fetchUserProfile } from '../services/authService';
import { useAuth } from '../contexts/AuthContext';

import { Link, useNavigate } from 'react-router-dom';
import {
  Building2, Eye, EyeOff, Mail, Lock,
  Users, Globe, Shield, Phone, Home
} from 'lucide-react';
import { PublicNavbar } from './layout/PublicNavbar';
import type { User } from '../types';

interface LoginPageProps {
  onNavigateToSignup: () => void;
  onGoToStore: () => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onNavigateToSignup, onGoToStore }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showResend, setShowResend] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const navigate = useNavigate();
  const { completeLogin } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setShowResend(false);
    setIsLoading(true);

    try {
      const logged = await loginUser(email, password);
      const profile = await fetchUserProfile(String(logged.id));
      // رد تسجيل الدخول أحدث لحقول الحساب؛ الملف الشخصي يكمّل الحقول فقط
      const merged = {
        ...(profile || {}),
        ...logged,
        id: String(logged.id),
      } as User;
      await completeLogin(merged);
    } catch (err: any) {
      // console suppressed
      if (err.message === "EMAIL_NOT_VERIFIED") {
        setError("يجب عليك تفعيل بريدك الإلكتروني قبل تسجيل الدخول.");
        setShowResend(true);
      } else if (err.message === "ACCOUNT_NOT_APPROVED") {
        setError("حسابك بانتظار موافقة المدير.");
      } else if (err.message === "INVALID_CREDENTIALS" || err.message === "Invalid credentials.") {
        setError("البريد الإلكتروني أو كلمة المرور غير صحيحة. إن وُجد الحقلان username و email في قاعدة البيانات، يجب أن يطابقا البريد الذي تدخله.");
      } else if (err.code === 'auth/invalid-credential' || err.code === 'auth/user-not-found' || err.code === 'auth/wrong-password') {
        setError("البريد الإلكتروني أو كلمة المرور غير صحيحة.");
      } else if (err instanceof TypeError && String(err.message).includes("fetch")) {
        setError("تعذر الاتصال بالخادم. تأكد أن Django يعمل وأن VITE_API_URL صحيح.");
      } else {
        setError(err?.message ? `تعذر تسجيل الدخول: ${err.message}` : "حدث خطأ أثناء تسجيل الدخول.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    try {
      setResendMessage(null);
      await resendVerificationEmail(email, password);
      setResendMessage("تم إرسال رابط التفعيل مرة أخرى. تحقق من بريدك.");
    } catch (e) {
      setResendMessage("فشل إرسال الرابط. تأكد من صحة البيانات.");
    }
  }

  // مكون لرابط الناف بار لتقليل التكرار
  const NavItem = ({ to, icon: Icon, label }: { to: string, icon: any, label: string }) => (
    <Link
      to={to}
      className="flex items-center gap-2 px-4 py-2 rounded-full text-gray-600 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-white/5 transition-all duration-300 font-medium text-sm md:text-base"
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
    </Link>
  );

  return (
    <div dir="rtl" className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-[var(--color-primary)] dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex flex-col items-center justify-center p-4 font-sans relative overflow-hidden">
      <PublicNavbar />

      {/* خلفية زخرفية */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-200 dark:bg-blue-900/20 rounded-full blur-3xl opacity-50"></div>
        <div className="absolute bottom-20 -left-40 w-96 h-96 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 rounded-full blur-3xl opacity-50"></div>
      </div>

      {/* المحتوى الرئيسي (أضفنا padding-top عشان الناف بار ما يغطي المحتوى) */}
      <div className="relative z-10 w-full max-w-md pt-20">

        {/* الشعار الكبير مع تأثير */}
        <div className="flex flex-col items-center justify-center mb-10 animate-fade-in">
          <div className="relative group">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-[var(--color-primary)] rounded-full blur-lg opacity-30 animate-pulse group-hover:opacity-50 transition-opacity"></div>
            <div className="relative p-4 bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-100 dark:border-gray-700">
              <LogoIcon className="h-14 w-14 text-blue-600 dark:text-blue-400" />
            </div>
          </div>

          <h1 className="mt-6 text-4xl font-bold bg-gradient-to-r from-blue-600 via-[var(--color-primary)] to-blue-600 bg-clip-text text-transparent text-center">
            منصة البحث الذكي
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400 text-lg text-center">
            نظام متكامل لإدارة الفواتير، الشحنات، الاستيراد، والموردين
          </p>

          {/* شارات الشركة */}
          <div className="flex flex-wrap justify-center gap-3 mt-6">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-full text-sm">
              <Globe className="w-4 h-4" />
              <span>K.T.R.A العالمية</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)] rounded-full text-sm">
              <Shield className="w-4 h-4" />
              <span>أكثر من 20 سنة خبرة</span>
            </div>
          </div>
        </div>

        {/* بطاقة تسجيل الدخول */}
        <div className="relative group">
          {/* تأثير الظل */}
          <div className="absolute -inset-1 bg-gradient-to-r from-blue-600 to-[var(--color-primary)] rounded-3xl blur opacity-30 group-hover:opacity-50 transition duration-500"></div>

          <div className="relative w-full p-8 space-y-8 bg-white/90 dark:bg-gray-800/90 backdrop-blur-sm rounded-3xl shadow-2xl border border-gray-100/50 dark:border-gray-700/50 text-center">
            <div className="space-y-2">
              <h2 className="text-3xl font-bold text-gray-800 dark:text-gray-100">تسجيل الدخول</h2>
              <p className="text-gray-600 dark:text-gray-400">أدخل بياناتك للوصول إلى النظام المتكامل</p>
            </div>

            {error && (
              <div className="p-4 bg-gradient-to-r from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-xl text-sm font-medium flex items-center gap-2">
                <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                {error}
              </div>
            )}

            {resendMessage && (
              <div className="p-4 bg-gradient-to-r from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 rounded-xl text-sm">
                {resendMessage}
              </div>
            )}

            <form onSubmit={handleLogin} className="space-y-6 text-right">
              {/* حقل البريد الإلكتروني */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                  <Mail className="w-4 h-4" />
                  البريد الإلكتروني
                </label>
                <div className="relative">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="block w-full px-5 py-4 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 transition duration-300"
                    placeholder="example@email.com"
                    required
                  />
                </div>
              </div>

              {/* حقل كلمة المرور */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                  <Lock className="w-4 h-4" />
                  كلمة المرور
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="block w-full px-5 py-4 pr-12 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 transition duration-300"
                    placeholder="••••••••"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute left-3 top-1/2 transform -translate-y-1/2 p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className={`w-full relative overflow-hidden bg-gradient-to-r from-blue-600 to-[var(--color-primary)] text-white font-bold py-5 px-4 rounded-xl text-lg hover:from-blue-700 hover:to-[var(--color-primary)] transition-all duration-300 ${isLoading ? 'opacity-90 cursor-not-allowed' : 'hover:shadow-xl hover:shadow-blue-500/25'}`}
              >
                {/* تأثير تحميل */}
                {isLoading && (
                  <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-[var(--color-primary)] animate-pulse"></div>
                )}

                <div className="relative flex items-center justify-center gap-2">
                  {isLoading ? (
                    <>
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>جاري الدخول...</span>
                    </>
                  ) : (
                    <>
                      <span>تسجيل الدخول</span>
                      <div className="w-5 h-5 bg-white/20 rounded-full flex items-center justify-center">
                        <div className="w-2 h-2 bg-white rounded-full"></div>
                      </div>
                    </>
                  )}
                </div>
              </button>
            </form>

            {showResend && (
              <button
                onClick={handleResend}
                className="w-full text-center text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 text-sm font-medium py-2.5 px-4 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition duration-300"
              >
                <span className="flex items-center justify-center gap-2">
                  <Mail className="w-4 h-4" />
                  إعادة إرسال بريد التفعيل
                </span>
              </button>
            )}

            {/* الفاصل */}
            <div className="relative flex py-4 items-center">
              <div className="flex-grow border-t border-gray-300 dark:border-gray-600"></div>
              <span className="flex-shrink mx-4 text-gray-400 dark:text-gray-500 text-sm">أو</span>
              <div className="flex-grow border-t border-gray-300 dark:border-gray-600"></div>
            </div>

            {/* زر إنشاء حساب جديد */}
            <button
              onClick={onNavigateToSignup}
              className="w-full group bg-white dark:bg-gray-700 border-2 border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300 font-bold py-4 px-4 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-600 hover:border-gray-300 dark:hover:border-gray-500 hover:shadow-lg transition-all duration-300"
            >
              <div className="flex items-center justify-center gap-2">
                <span>إنشاء حساب جديد</span>
                <div className="w-6 h-6 rounded-full bg-gray-100 dark:bg-gray-600 flex items-center justify-center group-hover:bg-gray-200 dark:group-hover:bg-gray-500 transition duration-300">
                  <div className="w-2 h-2 bg-gray-600 dark:bg-gray-300 rounded-full"></div>
                </div>
              </div>
            </button>

            {/* T-EXTACCT: مدخل المحاسب القانوني — كان المسار موجوداً بلا أي رابط يقود إليه */}
            <a
              href="/accountant/signup"
              className="block w-full mt-4 group bg-emerald-50 dark:bg-emerald-900/10 border-2 border-emerald-100 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 font-bold py-4 px-4 rounded-xl hover:bg-emerald-100 dark:hover:bg-emerald-900/30 transition-all duration-300 text-center"
            >
              <div className="flex items-center justify-center gap-2">
                <span>تسجيل كمحاسب قانوني خارجي</span>
              </div>
            </a>

            {/* زر الذهاب للمتجر */}
            <Link
              to="/store"
              className="block w-full mt-4 group bg-blue-50 dark:bg-blue-900/10 border-2 border-blue-100 dark:border-blue-800 text-blue-700 dark:text-blue-300 font-bold py-4 px-4 rounded-xl hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-all duration-300 text-center"
            >
              <div className="flex items-center justify-center gap-2">
                <span>تصفح المتجر (تسجيل سريع)</span>
              </div>
            </Link>

            {/* معلومات إضافية */}
            <div className="pt-6 border-t border-gray-100 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                © {new Date().getFullYear()} شركة K.T.R.A للتجارة العالمية
                <br />
                جميع الحقوق محفوظة | نظام إدارة متكامل
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* شعار الشركة في الأسفل */}
      <div className="mt-12 flex items-center gap-3 text-gray-600 dark:text-gray-400">
        <Building2 className="w-5 h-5" />
        <span className="text-sm">شركة K.T.R.A للتجارة العالمية</span>
        <div className="w-1 h-1 bg-gray-400 rounded-full"></div>
        <span className="text-sm">أكثر من 20 سنة خبرة</span>
      </div>
    </div>
  );
};