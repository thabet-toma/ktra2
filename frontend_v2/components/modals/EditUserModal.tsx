import React, { useState, useEffect } from 'react';
import { User, UserRole } from '../../types';

// تحديد نوع حالة التوظيف
type EmploymentStatus = 'probation' | 'permanent' | 'intern';

interface EditUserModalProps {
    isOpen: boolean;
    onClose: () => void;
    user: User;
    onSave: (user: User) => void;
}

export const EditUserModal: React.FC<EditUserModalProps> = ({ isOpen, onClose, user, onSave }) => {
    const [name, setName] = useState(user.name);
    const [role, setRole] = useState<UserRole>(user.role);
    // إضافة حالة لحالة التوظيف، مع افتراض أن الحقل موجود في واجهة User
    const [employmentStatus, setEmploymentStatus] = useState<EmploymentStatus>(
        (user.employmentStatus as EmploymentStatus) || 'probation' 
    ); 

    useEffect(() => {
        setName(user.name);
        setRole(user.role);
        setEmploymentStatus((user.employmentStatus as EmploymentStatus) || 'probation');
    }, [user]);

    if (!isOpen) return null;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSave({ 
            ...user, 
            name, 
            role,
            employmentStatus // حفظ الحالة الجديدة
        });
    };

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-center justify-center p-4 animate-fade-in"
            onClick={onClose}
        >
            <div 
                className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl w-full max-w-md p-8 space-y-6 transform transition-all"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex justify-between items-center">
                    <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100">تعديل المستخدم</h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-3xl">&times;</button>
                </div>
               
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label htmlFor="userName" className="block text-md font-medium text-gray-700 dark:text-gray-300 mb-1">اسم المستخدم</label>
                        <input 
                            type="text" 
                            id="userName" 
                            value={name} 
                            onChange={e => setName(e.target.value)} 
                            className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200" 
                            required 
                        />
                    </div>
                    {/* حقل حالة التوظيف الجديد */}
                    <div>
                        <label htmlFor="employmentStatus" className="block text-md font-medium text-gray-700 dark:text-gray-300 mb-1">الحالة الوظيفية</label>
                        <select 
                            id="employmentStatus" 
                            value={employmentStatus} 
                            onChange={e => setEmploymentStatus(e.target.value as EmploymentStatus)} 
                            className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        >
                            <option value="probation">تحت الاختبار</option>
                            <option value="permanent">موظف ثابت</option>
                            <option value="intern">متدرب</option>
                        </select>
                    </div>
                    <div>
                        <label htmlFor="userRole" className="block text-md font-medium text-gray-700 dark:text-gray-300 mb-1">الدور</label>
                        <select 
                            id="userRole" 
                            value={role} 
                            onChange={e => setRole(e.target.value as UserRole)} 
                            className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-200"
                        >
                            <option value="manager">مدير</option>
                            <option value="employee">موظف</option>
                            <option value="procurement">مشتريات</option> {/* إضافة دور المشتريات */}
                        </select>
                    </div>
                    <div className="pt-4 flex justify-end gap-3">
                        <button type="button" onClick={onClose} className="bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-200 font-bold py-2 px-6 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500 transition">
                            إلغاء
                        </button>
                        <button type="submit" className="bg-blue-600 text-white font-bold py-2 px-6 rounded-lg hover:bg-blue-700 transition">
                            حفظ التغييرات
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};