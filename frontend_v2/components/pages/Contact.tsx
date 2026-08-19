import { departments as defaultDepartments } from '@/data/departments';
import React, { useState, useEffect } from 'react';
import DepartmentCard from '../DepartmentCard';
import DepartmentModal from './DepartmentModal';
import { departmentsService, Department } from '../../services/firestoreService';
import { useToast } from '../../contexts/ToastContext';
import { useConfirm } from '../../contexts/ConfirmContext';
import { humanizeThrown } from '../../utils/drfError';

// مكون بسيط لأيقونات التواصل الاجتماعي (SVG)
const SocialIcon = ({ path, href, colorClass }: { path: string; href: string; colorClass: string }) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    className={`p-2 bg-white dark:bg-slate-800 rounded-full shadow-md hover:shadow-lg transform hover:-translate-y-1 transition-all duration-300 ${colorClass}`}
  >
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
      <path d={path} />
    </svg>
  </a>
);

export const Contact: React.FC<{ currentUser?: any }> = ({ currentUser }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingDept, setEditingDept] = useState<Department | null>(null);
  const [selectedDept, setSelectedDept] = useState<Department | null>(null);

  const isManager = currentUser?.role === 'manager';

  useEffect(() => {
    const unsub = departmentsService.subscribeToDepartments((deps) => {
      if (deps.length === 0) {
        setDepartments(defaultDepartments as any);
      } else {
        setDepartments(deps);
      }
      setLoading(false);
    });
    return () => unsub();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingDept) return;

    try {
      const existingDeps = await departmentsService.getDepartments();
      if (existingDeps.length === 0) {
        // أول حفظ: نثبّت مجموعة الأقسام الافتراضية مرة واحدة (upsert بمعرّفات ثابتة —
        // فلا تكرار حتى لو تكرّر النداء)، مع تطبيق التعديل الحالي على بطاقته. الترتيب
        // يُحفظ عبر createdAt متدرّج. (سابقاً كان addDepartment يولّد معرّفاً عشوائياً
        // في كل مرة ⇒ تُلحق نسخة كاملة من القائمة في كل حفظ = عيب تكرار البطاقات.)
        for (let i = 0; i < defaultDepartments.length; i++) {
          const dept = defaultDepartments[i] as Department;
          const base = dept.id === editingDept.id ? editingDept : dept;
          await departmentsService.saveDepartment({
            ...base,
            createdAt: new Date(Date.now() + i).toISOString(),
          });
        }
      } else {
        // تحديث القسم المُعدَّل فقط بمعرّفه الثابت (upsert — لا نسخة جديدة).
        await departmentsService.saveDepartment(editingDept);
      }
      setEditingDept(null);
    } catch (err) {
      console.error(err);
      toast(humanizeThrown(err), 'error');
    }
  };

  // تنظيف التكرارات القائمة: يحذف كل وثائق الأقسام ثم يعيد زرع المجموعة الافتراضية
  // بمعرّفات ثابتة. للمدير فقط — إجراء صريح (لا يعمل تلقائياً) لتفادي أي حذف غير مقصود.
  const handleResetDepartments = async () => {
    if (!(await confirm({ message: 'سيُعاد ضبط الأقسام للوضع الافتراضي وتُحذف أي بطاقات مكرّرة. متابعة؟' }))) return;
    try {
      const existingDeps = await departmentsService.getDepartments();
      for (const dept of existingDeps) {
        await departmentsService.deleteDepartment(dept.id);
      }
      for (let i = 0; i < defaultDepartments.length; i++) {
        await departmentsService.saveDepartment({
          ...(defaultDepartments[i] as Department),
          createdAt: new Date(Date.now() + i).toISOString(),
        });
      }
    } catch (err) {
      console.error(err);
      toast(humanizeThrown(err), 'error');
    }
  };
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 font-sans transition-colors duration-300" dir="rtl">
      
      {/* --- الهيدر الرئيسي مع الشعار (مصغر) --- */}
      <header className="bg-gradient-to-r from-cyan-600 to-slate-800 dark:from-slate-800 dark:to-slate-900 pt-6 pb-8 px-4 shadow-md">
        <div className="container mx-auto">
          
          {/* عنوان الصفحة */}
          <div className="text-center">
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-3">
              تواصل معنا
            </h1>
            <p className="text-slate-200 dark:text-slate-300 max-w-xl mx-auto text-sm md:text-base leading-relaxed">
              فريقنا جاهز لخدمتكم في كافة أقسام شركتنا
            </p>
          </div>
        </div>
      </header>

      {/* --- قسم الأقسام --- */}
      <main className="container mx-auto px-4 py-8 relative">
        {loading ? (
          <div className="flex justify-center items-center py-20">
             <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-600"></div>
          </div>
        ) : (
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-lg p-5 mb-6 border border-slate-100 dark:border-slate-700">
            <div className="flex items-center justify-center relative mb-4">
              <h2 className="text-xl font-bold text-slate-800 dark:text-white text-center">
                أقسام الشركة
              </h2>
              {isManager && (
                <button
                  type="button"
                  onClick={handleResetDepartments}
                  className="absolute left-0 text-xs px-3 py-1.5 rounded-lg text-slate-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-slate-700 transition-colors"
                  title="حذف البطاقات المكرّرة وإعادة الأقسام للوضع الافتراضي"
                >
                  إعادة تعيين الأقسام
                </button>
              )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {departments.map((dept) => (
                <DepartmentCard 
                  key={dept.id} 
                  department={dept} 
                  onEdit={isManager ? setEditingDept : undefined}
                  onClick={setSelectedDept}
                />
              ))}
            </div>
          </div>
        )}

        {/* Modal for editing */}
        {editingDept && isManager && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
             <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setEditingDept(null)} />
             <div className="relative bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-md p-6 animate-in fade-in zoom-in duration-200">
                <h3 className="text-xl font-bold mb-4 dark:text-white">تعديل القسم</h3>
                <form onSubmit={handleSave} className="space-y-4">
                  <div>
                    <label className="block text-sm mb-1 dark:text-slate-300">اسم القسم (عربي)</label>
                    <input required value={editingDept.name} onChange={e => setEditingDept({...editingDept, name: e.target.value})} className="w-full p-2 border rounded dark:bg-slate-700 dark:border-slate-600 dark:text-white" />
                  </div>
                  <div>
                    <label className="block text-sm mb-1 dark:text-slate-300">اسم القسم (انجليزي)</label>
                    <input required value={editingDept.nameEn} onChange={e => setEditingDept({...editingDept, nameEn: e.target.value})} className="w-full p-2 border rounded dark:bg-slate-700 dark:border-slate-600 dark:text-white" />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-sm mb-1 dark:text-slate-300">لقب المسؤول</label>
                      <input required value={editingDept.managerTitle} onChange={e => setEditingDept({...editingDept, managerTitle: e.target.value})} className="w-full p-2 border rounded dark:bg-slate-700 dark:border-slate-600 dark:text-white" />
                    </div>
                    <div>
                      <label className="block text-sm mb-1 dark:text-slate-300">اسم المسؤول</label>
                      <input required value={editingDept.managerName} onChange={e => setEditingDept({...editingDept, managerName: e.target.value})} className="w-full p-2 border rounded dark:bg-slate-700 dark:border-slate-600 dark:text-white" />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm mb-1 dark:text-slate-300">البريد الإلكتروني</label>
                    <input required type="email" value={editingDept.email} onChange={e => setEditingDept({...editingDept, email: e.target.value})} className="w-full p-2 border rounded dark:bg-slate-700 dark:border-slate-600 dark:text-white" />
                  </div>
                  <div>
                    <label className="block text-sm mb-1 dark:text-slate-300">رقم الواتساب</label>
                    <input required value={editingDept.whatsapp} onChange={e => setEditingDept({...editingDept, whatsapp: e.target.value})} className="w-full p-2 border rounded dark:bg-slate-700 dark:border-slate-600 dark:text-white" dir="ltr" />
                  </div>
                  <div className="flex gap-2 justify-end mt-4">
                    <button type="button" onClick={() => setEditingDept(null)} className="px-4 py-2 text-slate-500 hover:bg-slate-100 rounded">إلغاء</button>
                    <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">حفظ التغييرات</button>
                  </div>
                </form>
             </div>
          </div>
        )}
      </main>

      {selectedDept && (
        <DepartmentModal 
          department={selectedDept} 
          onClose={() => setSelectedDept(null)} 
        />
      )}
      
      {/* --- الفوتر مع الشعار الصغير (مصغر) --- */}
      <footer className="bg-slate-800 dark:bg-slate-900 pt-6 pb-4 px-4 border-t border-slate-700">
        <div className="container mx-auto">
          
          {/* الشعار الصغير في الفوتر */}
          <div className="flex justify-center mb-4">
            <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-700/50 backdrop-blur-sm">
              {/* استخدام صورة الشعار الصغيرة من مجلد public */}
              <img 
                src="/logo-small.png" 
                alt="K.T.R.A Logo"
                className="h-6 w-auto"
                onError={(e) => {
                  // في حال فشل تحميل الصورة، نعرض الشعار النصي الصغير
                  e.currentTarget.style.display = 'none';
                  const parent = e.currentTarget.parentElement;
                  if (parent) {
                    parent.innerHTML = `
                      <div class="flex items-center gap-2">
                        <div class="text-sm font-bold text-white tracking-wide">
                          K.T.R.A
                        </div>
                        <div class="h-5 w-0.5 bg-cyan-500 rounded-full"></div>
                        <div class="text-lg font-bold text-cyan-400">
                          K
                        </div>
                      </div>
                    `;
                  }
                }}
              />
            </div>
          </div>
          
          {/* وسائل التواصل الاجتماعي */}
          <div className="text-center mb-4">
            <h3 className="text-white font-medium mb-3 text-base">
              تابعونا على وسائل التواصل
            </h3>
            
            <div className="flex justify-center gap-3 mb-4">
              <SocialIcon 
                href="https://facebook.com"
                colorClass="text-blue-600 hover:bg-blue-50 dark:hover:bg-slate-700"
                path="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"
              />

              <SocialIcon 
                href="https://www.tiktok.com/@ktra.import.group?_r=1&_t=ZS-92CBUzi08iW"
                colorClass="text-pink-600 hover:bg-pink-50 dark:hover:bg-slate-700"
                path="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"
              />

              <SocialIcon 
                href="https://www.tiktok.com/@ktra.import.group?_r=1&_t=ZS-92CBUzi08iW"
                colorClass="text-black dark:text-white hover:bg-slate-200 dark:hover:bg-slate-700"
                path="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.35-1.17 1.02-1.25 1.73-.04.55.03 1.1.27 1.6.41.87 1.27 1.54 2.23 1.66 1.09.13 2.23-.39 2.82-1.29.35-.53.53-1.17.53-1.81.01-4.52.01-9.03 0-13.55.01-.73-.01-1.47.01-2.2z"
              />
              
              {/* أيقونة LinkedIn */}
              <SocialIcon 
                href="https://linkedin.com"
                colorClass="text-blue-700 hover:bg-blue-50 dark:hover:bg-slate-700"
                path="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
              />
            </div>
          </div>

          {/* معلومات الاتصال المختصرة */}
          <div className="flex flex-col md:flex-row justify-center gap-3 md:gap-6 mb-4 text-center">
            <div>
              <div className="text-white font-medium text-xs mb-1">الهاتف</div>
              <div className="text-slate-300 text-sm">+966 11 123 4567</div>
            </div>
            <div className="hidden md:block text-slate-500">|</div>
            <div>
              <div className="text-white font-medium text-xs mb-1">البريد الإلكتروني</div>
              <div className="text-slate-300 text-sm">info@ktra-sa.com</div>
            </div>
          </div>

          {/* الحقوق */}
          <div className="text-center pt-4 border-t border-slate-700">
            <div className="text-slate-400 text-xs">
              <p>© 2024 K.T.R.A - المؤسسة العامة للنقل</p>
              <p className="mt-1">جميع الحقوق محفوظة</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Contact;