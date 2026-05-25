import React, { useState, useEffect } from 'react';
import { User } from '../../types';

interface EmployeeDetailsModalProps {
    isOpen: boolean;
    onClose: () => void;
    user: User;
    onApprove: (user: User) => void;
    onReject: (userId: string) => void;
    onSaveNotes: (userId: string, notes: string) => Promise<void>; // New prop
}

export const EmployeeDetailsModal: React.FC<EmployeeDetailsModalProps> = ({ 
    isOpen, 
    onClose, 
    user, 
    onApprove, 
    onReject,
    onSaveNotes
}) => {
    const [notes, setNotes] = useState(user.notes || '');
    const [isSavingNotes, setIsSavingNotes] = useState(false);

    // Update local state when user prop changes
    useEffect(() => {
        setNotes(user.notes || '');
    }, [user]);

    if (!isOpen) return null;

    const handleSaveNotesClick = async () => {
        setIsSavingNotes(true);
        try {
            await onSaveNotes(user.id, notes);
            // Optional: Show success indication visually if needed
        } catch (error) {
            // console suppressed
            alert("فشل حفظ الملاحظات");
        } finally {
            setIsSavingNotes(false);
        }
    };

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-60 z-50 flex items-center justify-center p-4 animate-fade-in"
            onClick={onClose}
        >
            <div 
                className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col max-h-[90vh] overflow-hidden"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <header className="bg-blue-600 dark:bg-blue-800 p-6 flex justify-between items-center">
                    <div>
                        <h2 className="text-2xl font-bold text-white">{user.name}</h2>
                        <p className="text-blue-100 text-sm mt-1">{user.email}</p>
                    </div>
                    <button onClick={onClose} className="text-white/80 hover:text-white text-3xl">&times;</button>
                </header>

                {/* Content */}
                <main className="p-6 overflow-y-auto space-y-6">
                    {/* Status Banner */}
                    <div className={`p-3 rounded-lg border ${user.isApproved ? 'bg-green-50 border-green-200 text-green-700' : 'bg-yellow-50 border-yellow-200 text-yellow-700'}`}>
                        <span className="font-bold">الحالة: </span>
                        {user.isApproved ? 'معتمد (Active)' : 'بانتظار الموافقة (Pending)'}
                        {!user.isEmailVerified && <span className="text-red-500 text-sm block mt-1">⚠ البريد الإلكتروني غير مفعل</span>}
                    </div>

                    {/* Personal Info */}
                    <div>
                        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-3 border-b dark:border-gray-700 pb-2">البيانات الشخصية</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                            <div>
                                <span className="block text-gray-500 dark:text-gray-400 mb-1">رقم الهاتف</span>
                                <p className="text-gray-800 dark:text-gray-200 font-medium">{user.phone || '-'}</p>
                            </div>
                            <div>
                                <span className="block text-gray-500 dark:text-gray-400 mb-1">العنوان</span>
                                <p className="text-gray-800 dark:text-gray-200 font-medium">{user.address || '-'}</p>
                            </div>
                            <div>
                                <span className="block text-gray-500 dark:text-gray-400 mb-1">تاريخ التسجيل</span>
                                <p className="text-gray-800 dark:text-gray-200 font-medium">{user.createdAt ? new Date(user.createdAt).toLocaleDateString() : '-'}</p>
                            </div>
                        </div>
                    </div>

                    {/* Professional Info */}
                    <div>
                        <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100 mb-3 border-b dark:border-gray-700 pb-2">البيانات المهنية</h3>
                        <div className="space-y-4 text-sm">
                            <div>
                                <span className="block text-gray-500 dark:text-gray-400 mb-1">المؤهل الدراسي</span>
                                <p className="text-gray-800 dark:text-gray-200 font-medium bg-gray-50 dark:bg-gray-700/50 p-2 rounded">{user.educationLevel || 'غير محدد'}</p>
                            </div>
                            <div>
                                <span className="block text-gray-500 dark:text-gray-400 mb-1">الخبرات السابقة</span>
                                <p className="text-gray-800 dark:text-gray-200 font-medium bg-gray-50 dark:bg-gray-700/50 p-3 rounded whitespace-pre-wrap leading-relaxed">
                                    {user.experienceDescription || 'لا يوجد وصف للخبرات.'}
                                </p>
                            </div>
                            <div>
                                <span className="block text-gray-500 dark:text-gray-400 mb-2">السيرة الذاتية</span>
                                {user.resumeData ? (
                                    <a 
                                        href={user.resumeData.data} 
                                        download={user.resumeData.name}
                                        className="inline-flex items-center gap-2 bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 px-4 py-2 rounded-lg hover:bg-indigo-200 dark:hover:bg-indigo-800 transition font-bold"
                                    >
                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                                        تحميل السيرة الذاتية ({user.resumeData.name})
                                    </a>
                                ) : (
                                    <p className="text-gray-500 italic">لم يتم إرفاق سيرة ذاتية.</p>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Admin Notes Section (New) */}
                    <div className="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded-lg border border-yellow-200 dark:border-yellow-700">
                        <h3 className="text-lg font-bold text-yellow-800 dark:text-yellow-200 mb-2 flex items-center gap-2">
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                            </svg>
                            ملاحظات المدير (سري - لا تظهر للموظف)
                        </h3>
                        <textarea 
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            rows={3}
                            className="w-full p-3 border border-yellow-300 dark:border-yellow-600 rounded-lg bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                            placeholder="اكتب ملاحظاتك الخاصة حول هذا الموظف هنا..."
                        />
                        <div className="flex justify-end mt-2">
                            <button 
                                onClick={handleSaveNotesClick}
                                disabled={isSavingNotes}
                                className="bg-yellow-600 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-yellow-700 transition flex items-center gap-2 disabled:opacity-50"
                            >
                                {isSavingNotes ? 'جاري الحفظ...' : 'حفظ الملاحظات'}
                            </button>
                        </div>
                    </div>
                </main>

                {/* Footer Actions */}
                <footer className="bg-gray-50 dark:bg-gray-700/30 p-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                    {!user.isApproved && (
                        <button 
                            onClick={() => onApprove(user)} 
                            className="bg-green-600 text-white font-bold py-2 px-6 rounded-lg hover:bg-green-700 transition shadow-lg"
                        >
                            قبول الموظف
                        </button>
                    )}
                    <button 
                        onClick={() => onReject(user.id)} 
                        className="bg-red-500 text-white font-bold py-2 px-6 rounded-lg hover:bg-red-600 transition shadow-lg"
                    >
                        {user.isApproved ? 'حذف الموظف' : 'رفض الطلب'}
                    </button>
                    <button 
                        onClick={onClose} 
                        className="bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-200 font-bold py-2 px-6 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500 transition"
                    >
                        إغلاق
                    </button>
                </footer>
            </div>
        </div>
    );
};