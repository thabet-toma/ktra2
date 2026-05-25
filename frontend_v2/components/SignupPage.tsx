import React, { useState } from 'react';
import { LogoIcon } from './icons/LogoIcon';
import { signupUser } from '../services/authService';
import { TermsAndConditions } from './TermsAndConditions';
import { Link, useNavigate } from 'react-router-dom';
import {
  Building2, User, Mail, Phone, MapPin, Lock, BookOpen,
  Briefcase, FileText, Eye, EyeOff, ArrowLeft, CheckCircle,
  Shield, Globe, Award, Users, Upload
} from 'lucide-react';

interface SignupPageProps {
  onNavigateToLogin: () => void;
}

export const SignupPage: React.FC<SignupPageProps> = ({ onNavigateToLogin }) => {
  const [formData, setFormData] = useState({
    fullName: '',
    email: '',
    phone: '',
    city: '',
    village: '',
    street: '',
    password: '',
    confirmPassword: '',
    experienceDescription: '',
    educationLevel: ''
  });

  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showTerms, setShowTerms] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const navigate = useNavigate();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];

      // محاكاة تقدم الرفع
      let progress = 0;
      const interval = setInterval(() => {
        progress += 10;
        setUploadProgress(progress);
        if (progress >= 100) {
          clearInterval(interval);
        }
      }, 50);

      if (!['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'].includes(file.type)) {
        setError("نوع الملف غير مدعوم. يرجى رفع ملف PDF أو Word.");
        setResumeFile(null);
        return;
      }
      if (file.size > 800 * 1024) {
        setError("حجم الملف كبير جداً. الحد الأقصى 800 كيلوبايت.");
        setResumeFile(null);
        return;
      }
      setError(null);
      setResumeFile(file);
      setTimeout(() => setUploadProgress(100), 600);
    }
  };

  const convertFileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = error => reject(error);
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (!acceptedTerms) {
      setError("يجب الموافقة على الشروط والأحكام أولاً.");
      return;
    }

    if (formData.password !== formData.confirmPassword) {
      setError("كلمات المرور غير متطابقة.");
      return;
    }

    if (formData.password.length < 6) {
      setError("يجب أن تكون كلمة المرور 6 أحرف على الأقل.");
      return;
    }

    if (!resumeFile) {
      setError("يرجى رفع السيرة الذاتية.");
      return;
    }

    setIsLoading(true);
    try {
      const base64Data = await convertFileToBase64(resumeFile);

      const fullAddress = `${formData.city} - ${formData.village} - ${formData.street}`;

      await signupUser({
        fullName: formData.fullName,
        email: formData.email,
        phone: formData.phone,
        address: fullAddress,
        password: formData.password,
        experienceDescription: formData.experienceDescription,
        educationLevel: formData.educationLevel,
        resumeData: {
          name: resumeFile.name,
          type: resumeFile.type,
          url: base64Data
        }
      });

      setSuccessMessage("✨ تم إنشاء الحساب بنجاح! يرجى تفعيل بريدك الإلكتروني وانتظار موافقة الإدارة.");
      setTimeout(() => {
        onNavigateToLogin();
      }, 6000);
    } catch (err: any) {
      // console suppressed
      if (err.code === 'auth/email-already-in-use') {
        setError("⚠️ البريد الإلكتروني مستخدم بالفعل.");
      } else {
        setError("حدث خطأ أثناء إنشاء الحساب. " + err.message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleAcceptTerms = () => {
    setAcceptedTerms(true);
    setShowTerms(false);
  };

  const handleNavigateToAbout = () => {
    navigate('/about');
  };

  return (
    <div dir="rtl" className="min-h-screen bg-gradient-to-br from-[var(--color-primary)] via-blue-50 to-gray-100 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 flex flex-col items-center justify-center p-4 font-sans overflow-y-auto relative">

      {/* خلفية زخرفية */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-60 -right-60 w-[500px] h-[500px] bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/20 rounded-full blur-3xl opacity-40"></div>
        <div className="absolute -bottom-60 -left-60 w-[500px] h-[500px] bg-blue-200 dark:bg-blue-900/20 rounded-full blur-3xl opacity-40"></div>
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] bg-gradient-to-r from-blue-300 to-[var(--color-primary)] dark:from-blue-800/30 dark:to-[var(--color-primary)]/30 rounded-full blur-3xl opacity-20"></div>
      </div>

      {/* زر العودة للرئيسية */}
      <Link
        to="/"
        className="absolute top-6 left-6 md:top-8 md:left-8 flex items-center gap-2 px-5 py-2.5 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-xl border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-800 hover:shadow-xl transition-all duration-300 z-10 group"
      >
        <ArrowLeft className="w-4 h-4 group-hover:-translate-x-1 transition-transform" />
        <span className="font-medium">الرئيسية</span>
      </Link>

      {/* زر "من نحن" */}
      <button
        onClick={handleNavigateToAbout}
        className="absolute top-6 right-6 md:top-8 md:right-8 group flex items-center gap-3 px-6 py-2.5 bg-gradient-to-r from-[var(--color-primary)] to-blue-600 text-white rounded-xl hover:from-[var(--color-primary)] hover:to-blue-700 hover:shadow-2xl hover:scale-105 transition-all duration-300 z-10 overflow-hidden"
      >
        <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-[var(--color-primary)] opacity-0 group-hover:opacity-20 transition-opacity duration-300"></div>
        <div className="relative z-10 flex items-center gap-2">
          <Building2 className="w-5 h-5" />
          <span className="font-semibold">من نحن</span>
        </div>
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-400/30 to-[var(--color-primary)]/30 rounded-xl blur-md opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
      </button>

      {/* المحتوى الرئيسي */}
      <div className="relative z-10 w-full max-w-4xl">
        {/* الشعار والمقدمة */}
        <div className="flex flex-col items-center justify-center mb-8 animate-fade-in">
          <div className="relative mb-4">
            <div className="absolute inset-0 bg-gradient-to-r from-blue-400 to-[var(--color-primary)] rounded-full blur-xl opacity-30 animate-pulse"></div>
            <div className="relative p-4 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm rounded-2xl shadow-2xl border border-white/20 dark:border-gray-700/50">
              <LogoIcon className="h-16 w-16 text-blue-600 dark:text-blue-400" />
            </div>
          </div>

          <h1 className="mt-2 text-4xl font-bold bg-gradient-to-r from-blue-600 via-[var(--color-primary)] to-blue-600 bg-clip-text text-transparent">
            انضم إلى فريق K.T.R.A
          </h1>
          <p className="mt-3 text-lg text-gray-600 dark:text-gray-400 max-w-2xl text-center">
            انضم إلى عائلة شركة كترا للتجارة العالمية وأبدأ رحلتك المهنية مع أكثر من 20 عاماً من الخبرة في الاستيراد والتجارة الدولية
          </p>

          {/* شارات الشركة */}
          <div className="flex flex-wrap justify-center gap-4 mt-6">
            <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-50 to-blue-100 dark:from-blue-900/30 dark:to-blue-800/30 text-blue-700 dark:text-blue-300 rounded-full text-sm font-medium backdrop-blur-sm">
              <Award className="w-4 h-4" />
              <span>أكثر من 20 سنة خبرة</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-primary)] dark:from-[var(--color-primary)]/30 dark:to-[var(--color-primary)]/30 text-[var(--color-primary)] dark:text-[var(--color-primary)] rounded-full text-sm font-medium backdrop-blur-sm">
              <Globe className="w-4 h-4" />
              <span>تجارة عالمية</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-green-50 to-green-100 dark:from-green-900/30 dark:to-green-800/30 text-green-700 dark:text-green-300 rounded-full text-sm font-medium backdrop-blur-sm">
              <Shield className="w-4 h-4" />
              <span>بيئة عمل محفزة</span>
            </div>
          </div>
        </div>

        {/* بطاقة التسجيل */}
        <div className="relative group mb-12">
          <div className="absolute -inset-1 bg-gradient-to-r from-blue-600 via-[var(--color-primary)] to-pink-600 rounded-3xl blur opacity-30 group-hover:opacity-50 transition duration-700 animate-gradient-x"></div>

          <div className="relative w-full p-8 space-y-8 bg-white/95 dark:bg-gray-800/95 backdrop-blur-lg rounded-3xl shadow-2xl border border-white/20 dark:border-gray-700/30">
            {/* مؤشر تقدم */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-sm font-medium text-green-600 dark:text-green-400">التسجيل مفتوح</span>
              </div>
              <div className="text-sm text-gray-500 dark:text-gray-400">خطوة واحدة للانضمام</div>
            </div>

            {/* رسائل التحذير */}
            {error && (
              <div className="p-4 bg-gradient-to-r from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-l-4 border-red-500 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                  <p className="text-red-700 dark:text-red-300 font-medium">{error}</p>
                </div>
              </div>
            )}

            {successMessage && (
              <div className="p-4 bg-gradient-to-r from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-800/20 border-l-4 border-green-500 rounded-xl animate-fade-in">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                  <p className="text-green-700 dark:text-green-300 font-medium">{successMessage}</p>
                </div>
              </div>
            )}

            {/* النموذج */}
            <form onSubmit={handleSubmit} className="space-y-8">
              {/* المعلومات الشخصية */}
              <div className="space-y-6">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                    <User className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">المعلومات الشخصية</h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                      <User className="w-4 h-4" />
                      الاسم الكامل
                    </label>
                    <input
                      required
                      type="text"
                      name="fullName"
                      value={formData.fullName}
                      onChange={handleChange}
                      className="w-full px-4 py-3.5 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 transition duration-300"
                      placeholder="أحمد محمد علي"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                      <Mail className="w-4 h-4" />
                      البريد الإلكتروني
                    </label>
                    <input
                      required
                      type="email"
                      name="email"
                      value={formData.email}
                      onChange={handleChange}
                      className="w-full px-4 py-3.5 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 transition duration-300"
                      placeholder="example@email.com"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                    <Phone className="w-4 h-4" />
                    رقم الهاتف
                  </label>
                  <input
                    required
                    type="tel"
                    name="phone"
                    value={formData.phone}
                    onChange={handleChange}
                    className="w-full px-4 py-3.5 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 transition duration-300"
                    placeholder="+966 5X XXX XXXX"
                  />
                </div>

                {/* العنوان */}
                <div className="bg-gradient-to-r from-blue-50/50 to-[var(--color-primary)]/50 dark:from-gray-800/30 dark:to-gray-700/30 p-5 rounded-2xl border border-blue-100/50 dark:border-gray-600">
                  <label className="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
                    <MapPin className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    العنوان التفصيلي
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <input
                        required
                        type="text"
                        name="city"
                        placeholder="المدينة"
                        value={formData.city}
                        onChange={handleChange}
                        className="w-full p-3.5 border border-blue-200 dark:border-gray-600 rounded-xl bg-white/80 dark:bg-gray-700/80 dark:text-white text-sm backdrop-blur-sm"
                      />
                    </div>
                    <div>
                      <input
                        required
                        type="text"
                        name="village"
                        placeholder="القرية / البلدة"
                        value={formData.village}
                        onChange={handleChange}
                        className="w-full p-3.5 border border-blue-200 dark:border-gray-600 rounded-xl bg-white/80 dark:bg-gray-700/80 dark:text-white text-sm backdrop-blur-sm"
                      />
                    </div>
                    <div>
                      <input
                        required
                        type="text"
                        name="street"
                        placeholder="الشارع والرقم"
                        value={formData.street}
                        onChange={handleChange}
                        className="w-full p-3.5 border border-blue-200 dark:border-gray-600 rounded-xl bg-white/80 dark:bg-gray-700/80 dark:text-white text-sm backdrop-blur-sm"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* المعلومات المهنية */}
              <div className="space-y-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-[var(--color-surface-2)] dark:bg-[var(--color-surface-2)]/30 rounded-lg">
                    <Briefcase className="w-5 h-5 text-[var(--color-primary)] dark:text-[var(--color-primary)]" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">المعلومات المهنية</h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                      <BookOpen className="w-4 h-4" />
                      المؤهل الدراسي
                    </label>
                    <select
                      required
                      name="educationLevel"
                      value={formData.educationLevel}
                      onChange={handleChange}
                      className="w-full px-4 py-3.5 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm"
                    >
                      <option value="">اختر المؤهل...</option>
                      <option value="High School">ثانوية عامة</option>
                      <option value="Diploma">دبلوم</option>
                      <option value="Bachelor">بكالوريوس</option>
                      <option value="Master">ماجستير</option>
                      <option value="PhD">دكتوراه</option>
                    </select>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      السيرة الذاتية
                    </label>
                    <div className="relative">
                      <input
                        required
                        type="file"
                        accept=".pdf,.doc,.docx"
                        onChange={handleFileChange}
                        className="w-full p-3.5 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-xl bg-gray-50/50 dark:bg-gray-700/50 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-gradient-to-r file:from-blue-500 file:to-[var(--color-primary)] file:text-white hover:file:from-blue-600 hover:file:to-[var(--color-primary)] transition duration-300 backdrop-blur-sm"
                      />
                      {uploadProgress > 0 && uploadProgress < 100 && (
                        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-blue-500 to-[var(--color-primary)] transition-all duration-300"
                            style={{ width: `${uploadProgress}%` }}
                          ></div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    نبذة عن الخبرات السابقة
                  </label>
                  <textarea
                    required
                    name="experienceDescription"
                    value={formData.experienceDescription}
                    onChange={handleChange}
                    rows={4}
                    className="w-full px-4 py-3.5 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 resize-none transition duration-300"
                    placeholder="شاركنا خبراتك السابقة والمهارات التي تتمتع بها..."
                  />
                </div>
              </div>

              {/* كلمة المرور */}
              <div className="space-y-6 pt-6 border-t border-gray-200 dark:border-gray-700">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                    <Lock className="w-5 h-5 text-green-600 dark:text-green-400" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">الأمان والحماية</h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      كلمة المرور
                    </label>
                    <div className="relative">
                      <input
                        required
                        type={showPassword ? "text" : "password"}
                        name="password"
                        value={formData.password}
                        onChange={handleChange}
                        className="w-full px-4 py-3.5 pr-12 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 transition duration-300"
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute left-3 top-1/2 transform -translate-y-1/2 p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition duration-300"
                      >
                        {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                      </button>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      تأكيد كلمة المرور
                    </label>
                    <div className="relative">
                      <input
                        required
                        type={showConfirmPassword ? "text" : "password"}
                        name="confirmPassword"
                        value={formData.confirmPassword}
                        onChange={handleChange}
                        className="w-full px-4 py-3.5 pr-12 text-gray-900 dark:text-gray-200 bg-gray-50/50 dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent backdrop-blur-sm placeholder-gray-400 dark:placeholder-gray-500 transition duration-300"
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        className="absolute left-3 top-1/2 transform -translate-y-1/2 p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition duration-300"
                      >
                        {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* الشروط والأحكام */}
              <div className="bg-gradient-to-r from-gray-50/50 to-blue-50/50 dark:from-gray-800/30 dark:to-gray-700/30 p-5 rounded-2xl border border-gray-200 dark:border-gray-600">
                <div className="flex items-start gap-4">
                  <div className={`p-2 rounded-lg ${acceptedTerms ? 'bg-green-100 dark:bg-green-900/30' : 'bg-gray-100 dark:bg-gray-700'}`}>
                    {acceptedTerms ? (
                      <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
                    ) : (
                      <Shield className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <input
                        type="checkbox"
                        id="terms"
                        checked={acceptedTerms}
                        onChange={(e) => setAcceptedTerms(e.target.checked)}
                        className="w-4 h-4 text-blue-600 bg-white border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:bg-gray-700 dark:border-gray-600"
                      />
                      <label htmlFor="terms" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        أوافق على{' '}
                        <button
                          type="button"
                          onClick={() => setShowTerms(true)}
                          className="text-blue-600 dark:text-blue-400 hover:underline font-semibold"
                        >
                          الشروط والأحكام
                        </button>
                        {' '}وسياسة الخصوصية لشركة K.T.R.A
                      </label>
                    </div>
                    {acceptedTerms && (
                      <div className="flex items-center gap-2 text-green-600 dark:text-green-400 text-sm mt-1 animate-fade-in">
                        <CheckCircle className="w-4 h-4" />
                        <span>تمت الموافقة - يمكنك الآن إنشاء الحساب</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* أزرار الإجراء */}
              <div className="space-y-4 pt-4">
                <button
                  type="submit"
                  disabled={isLoading || !acceptedTerms}
                  className={`w-full relative overflow-hidden group bg-gradient-to-r from-blue-600 to-[var(--color-primary)] text-white font-bold py-4 px-4 rounded-xl text-lg transition-all duration-500 ${isLoading || !acceptedTerms
                    ? 'opacity-70 cursor-not-allowed'
                    : 'hover:from-blue-700 hover:to-[var(--color-primary)] hover:shadow-2xl hover:shadow-purple-500/30 hover:scale-[1.02]'
                    }`}
                >
                  {isLoading ? (
                    <div className="flex items-center justify-center gap-3">
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>جاري إنشاء الحساب...</span>
                    </div>
                  ) : (
                    <div className="flex items-center justify-center gap-3">
                      <span>انضم إلى فريق K.T.R.A</span>
                      <Users className="w-5 h-5 group-hover:scale-110 transition-transform" />
                    </div>
                  )}

                  {/* تأثير خلفي */}
                  <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-[var(--color-primary)] opacity-0 group-hover:opacity-10 transition-opacity duration-500"></div>
                </button>

                <div className="flex items-center justify-center gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
                  <span className="text-gray-600 dark:text-gray-400 text-sm">لديك حساب بالفعل؟</span>
                  <button
                    type="button"
                    onClick={onNavigateToLogin}
                    className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-semibold text-sm px-4 py-2 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition duration-300"
                  >
                    تسجيل الدخول
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* معلومات إضافية */}
        <div className="text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            © {new Date().getFullYear()} شركة K.T.R.A للتجارة العالمية
            <span className="mx-2">•</span>
            جميع الحقوق محفوظة
            <span className="mx-2">•</span>
            <span className="text-blue-600 dark:text-blue-400">Privacy & Security</span>
          </p>
        </div>
      </div>

      {/* نافذة الشروط والأحكام */}
      <TermsAndConditions
        isOpen={showTerms}
        onClose={() => setShowTerms(false)}
        onAccept={handleAcceptTerms}
      />
    </div>
  );
};