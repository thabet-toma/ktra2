import React, { useState, useEffect } from 'react';
import { User } from '../types';
import { NoteIcon } from './icons/NoteIcon';

interface EmployeeNotesProps {
    users: User[];
    onSaveNotes: (userId: string, notes: string) => Promise<void>;
}

const NoteCard: React.FC<{ user: User; onSave: (userId: string, notes: string) => Promise<void> }> = ({ user, onSave }) => {
    const [notes, setNotes] = useState(user.notes || '');
    const [isSaving, setIsSaving] = useState(false);
    const [isDirty, setIsDirty] = useState(false);

    useEffect(() => {
        setNotes(user.notes || '');
        setIsDirty(false);
    }, [user.notes]);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await onSave(user.id, notes);
            setIsDirty(false);
        } catch (error) {
            // console suppressed
            alert("حدث خطأ أثناء حفظ الملاحظات");
        } finally {
            setIsSaving(false);
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setNotes(e.target.value);
        setIsDirty(true);
    }

    return (
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-md border border-gray-200 dark:border-gray-700 p-6 flex flex-col h-full transition-all hover:shadow-lg">
            <div className="flex items-center gap-4 mb-4 border-b border-gray-100 dark:border-gray-700 pb-4">
                <div className="w-12 h-12 rounded-full bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center text-blue-600 dark:text-blue-300 font-bold text-xl">
                    {user.name.charAt(0).toUpperCase()}
                </div>
                <div>
                    <h3 className="text-lg font-bold text-gray-800 dark:text-gray-100">{user.name}</h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{user.email}</p>
                </div>
            </div>

            <div className="flex-grow">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    ملاحظات خاصة (سري)
                </label>
                <textarea
                    value={notes}
                    onChange={handleChange}
                    className="w-full h-40 p-3 border border-yellow-200 dark:border-yellow-900/50 rounded-lg bg-yellow-50/50 dark:bg-gray-900 text-gray-700 dark:text-gray-300 focus:ring-2 focus:ring-yellow-400 focus:border-transparent resize-none text-sm leading-relaxed shadow-inner"
                    placeholder="اكتب ملاحظاتك هنا..."
                />
            </div>

            <div className="mt-4 flex justify-end">
                <button
                    onClick={handleSave}
                    disabled={!isDirty || isSaving}
                    className={`px-6 py-2 rounded-lg font-bold transition-all shadow-sm flex items-center gap-2 ${
                        !isDirty 
                        ? 'bg-gray-100 text-gray-400 cursor-default dark:bg-gray-700 dark:text-gray-500' 
                        : 'bg-yellow-500 text-white hover:bg-yellow-600 hover:shadow-md'
                    }`}
                >
                    {isSaving ? 'جاري الحفظ...' : (isDirty ? 'حفظ التغييرات' : 'تم الحفظ')}
                </button>
            </div>
        </div>
    );
};

export const EmployeeNotes: React.FC<EmployeeNotesProps> = ({ users, onSaveNotes }) => {
    const employees = users.filter(u => u.role === 'employee');

    return (
        <div className="animate-fade-in pb-8">
            <div className="flex items-center gap-3 mb-8">
                <div className="p-3 bg-yellow-100 dark:bg-yellow-900/30 rounded-xl">
                    <NoteIcon className="h-8 w-8 text-yellow-600 dark:text-yellow-400" />
                </div>
                <div>
                    <h1 className="text-3xl font-bold text-gray-800 dark:text-gray-100">ملاحظات الموظفين</h1>
                    <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
                        مساحة خاصة لتدوين الملاحظات الإدارية حول أداء الموظفين. هذه الملاحظات لا تظهر للموظف.
                    </p>
                </div>
            </div>

            {employees.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {employees.map(user => (
                        <NoteCard key={user.id} user={user} onSave={onSaveNotes} />
                    ))}
                </div>
            ) : (
                <div className="text-center py-16 bg-white dark:bg-gray-800 rounded-2xl border dark:border-gray-700">
                    <p className="text-gray-500 dark:text-gray-400">لا يوجد موظفين حالياً.</p>
                </div>
            )}
        </div>
    );
};