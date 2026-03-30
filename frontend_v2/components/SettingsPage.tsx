
import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { updateUserInDb } from '../services/firestoreService';
import { changeUserPassword } from '../services/authService';

interface SettingsPageProps {
  user: User;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ user }) => {
  const [profileForm, setProfileForm] = useState({
    name: user.name,
    phone: user.phone || '',
    address: user.address || '',
    educationLevel: user.educationLevel || '',
    experienceDescription: user.experienceDescription || ''
  });
  
  const [resumeFile, setResumeFile] = useState<File | null>(null);

  const [passwordForm, setPasswordForm] = useState({
    oldPassword: '',
    newPassword: '',
    confirmPassword: ''
  });

  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [loadingPassword, setLoadingPassword] = useState(false);

  useEffect(() => {
    setProfileForm({
        name: user.name,
        phone: user.phone || '',
        address: user.address || '',
        educationLevel: user.educationLevel || '',
        experienceDescription: user.experienceDescription || ''
    });
  }, [user]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
        const file = e.target.files[0];
        if (file.size > 800 * 1024) {
            setMessage({ type: 'error', text: 'حجم الملف كبير جداً. الحد الأقصى 800 كيلوبايت.' });
            return;
        }
        setResumeFile(file);
        setMessage(null);
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

  const handleProfileUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoadingProfile(true);
    setMessage(null);
    try {
        const updates: any = {
            id: user.id,
            name: profileForm.name,
            phone: profileForm.phone,
            address: profileForm.address,
            educationLevel: profileForm.educationLevel,
            experienceDescription: profileForm.experienceDescription
        };

        if (resumeFile) {
            const base64Data = await convertFileToBase64(resumeFile);
            updates.resumeData = {
                name: resumeFile.name,
                type: resumeFile.type,
                data: base64Data
            };
        }

        await updateUserInDb(updates);
        setMessage({ type: 'success', text: 'تم تحديث البيانات الشخصية بنجاح.' });
        setResumeFile(null); // Reset file input
    } catch (err) {
        console.error(err);
        setMessage({ type: 'error', text: 'حدث خطأ أثناء تحديث البيانات.' });
    } finally {
        setLoadingProfile(false);
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
        setMessage({ type: 'error', text: 'كلمة المرور الجديدة غير متطابقة.' });
        return;
    }

    if (passwordForm.newPassword.length < 6) {
        setMessage({ type: 'error', text: 'كلمة المرور يجب أن تكون 6 خانات على الأقل.' });
        return;
    }

    setLoadingPassword(true);
    try {
        await changeUserPassword(passwordForm.oldPassword, passwordForm.newPassword);
        setMessage({ type: 'success', text: 'تم تغيير كلمة المرور بنجاح.' });
        setPasswordForm({ oldPassword: '', newPassword: '', confirmPassword: '' });
    } catch (err: any) {
        console.error(err);
        if (err.code === 'auth/invalid-credential' || err.code === 'auth/wrong-password') {
            setMessage({ type: 'error', text: 'كلمة المرور الحالية غير صحيحة.' });
        } else {
            setMessage({ type: 'error', text: 'حدث خطأ. يرجى التأكد من كلمة المرور والمحاولة مرة أخرى.' });
        }
    } finally {
        setLoadingPassword(false);
    }
  };

  return (
    <div className="animate-fade-in max-w-4xl mx-auto space-y-8 pb-10">
      <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-100 mb-6">الإعدادات</h1>

      {message && (
        <div className={`p-4 rounded-lg mb-4 text-center ${message.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
            {message.text}
        </div>
      )}

      {/* Profile Settings */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 p-6 sm:p-8">
        <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100 mb-4 border-b pb-2 dark:border-gray-700">المعلومات الشخصية والمهنية</h2>
        <form onSubmit={handleProfileUpdate} className="space-y-4">
            {/* Personal Info Section */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">الاسم الكامل</label>
                    <input 
                        type="text" 
                        value={profileForm.name} 
                        onChange={e => setProfileForm({...profileForm, name: e.target.value})}
                        className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        required
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">البريد الإلكتروني (للقراءة فقط)</label>
                    <input 
                        type="email" 
                        value={user.email} 
                        disabled
                        className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-400 cursor-not-allowed"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">رقم الهاتف</label>
                    <input 
                        type="tel" 
                        value={profileForm.phone} 
                        onChange={e => setProfileForm({...profileForm, phone: e.target.value})}
                        className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">العنوان</label>
                    <input 
                        type="text" 
                        value={profileForm.address} 
                        onChange={e => setProfileForm({...profileForm, address: e.target.value})}
                        className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                    />
                </div>
            </div>

            {/* Professional Info Section */}
            <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">البيانات المهنية</h3>
                <div className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">المؤهل الدراسي</label>
                        <select 
                            value={profileForm.educationLevel} 
                            onChange={e => setProfileForm({...profileForm, educationLevel: e.target.value})}
                            className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        >
                            <option value="">اختر المؤهل...</option>
                            <option value="High School">ثانوية عامة</option>
                            <option value="Diploma">دبلوم</option>
                            <option value="Bachelor">بكالوريوس</option>
                            <option value="Master">ماجستير</option>
                            <option value="PhD">دكتوراه</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">نبذة عن الخبرات</label>
                        <textarea 
                            value={profileForm.experienceDescription} 
                            onChange={e => setProfileForm({...profileForm, experienceDescription: e.target.value})}
                            rows={3}
                            className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            تحديث السيرة الذاتية 
                            {user.resumeData && <span className="text-green-600 text-xs mr-2">(يوجد ملف محفوظ: {user.resumeData.name})</span>}
                        </label>
                        <input 
                            type="file" 
                            accept=".pdf,.doc,.docx"
                            onChange={handleFileChange}
                            className="w-full p-2 text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-gray-600 dark:file:text-gray-200" 
                        />
                        <p className="text-xs text-gray-500 mt-1">الحد الأقصى 800 كيلوبايت</p>
                    </div>
                </div>
            </div>

            <div className="flex justify-end pt-4">
                <button 
                    type="submit" 
                    disabled={loadingProfile}
                    className="bg-blue-600 text-white font-bold py-2 px-6 rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
                >
                    {loadingProfile ? 'جاري الحفظ...' : 'حفظ التغييرات'}
                </button>
            </div>
        </form>
      </div>

      {/* Password Change */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 p-6 sm:p-8">
        <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100 mb-4 border-b pb-2 dark:border-gray-700">تغيير كلمة المرور</h2>
        <form onSubmit={handlePasswordChange} className="space-y-4 max-w-md">
             <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">كلمة المرور الحالية</label>
                <input 
                    type="password" 
                    value={passwordForm.oldPassword} 
                    onChange={e => setPasswordForm({...passwordForm, oldPassword: e.target.value})}
                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                    required
                />
            </div>
            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">كلمة المرور الجديدة</label>
                <input 
                    type="password" 
                    value={passwordForm.newPassword} 
                    onChange={e => setPasswordForm({...passwordForm, newPassword: e.target.value})}
                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                    required
                />
            </div>
            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">تأكيد كلمة المرور الجديدة</label>
                <input 
                    type="password" 
                    value={passwordForm.confirmPassword} 
                    onChange={e => setPasswordForm({...passwordForm, confirmPassword: e.target.value})}
                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                    required
                />
            </div>
             <div className="flex justify-start pt-2">
                <button 
                    type="submit" 
                    disabled={loadingPassword}
                    className="bg-gray-800 dark:bg-gray-600 text-white font-bold py-2 px-6 rounded-lg hover:bg-gray-900 dark:hover:bg-gray-500 transition disabled:opacity-50"
                >
                    {loadingPassword ? 'جاري التحديث...' : 'تحديث كلمة المرور'}
                </button>
            </div>
        </form>
      </div>
    </div>
  );
};
