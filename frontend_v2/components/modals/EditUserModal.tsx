import React, { useState, useEffect } from 'react';
import { User, UserRole } from '../../types';
import { ASSIGNABLE_MEMBER_ROLES, MEMBER_ROLE_LABELS } from '../../utils/memberRoles';

interface EditUserModalProps {
    isOpen: boolean;
    onClose: () => void;
    user: User;
    onSave: (user: User) => void;
}

export const EditUserModal: React.FC<EditUserModalProps> = ({ isOpen, onClose, user, onSave }) => {
    const [name, setName] = useState(user.name);
    const [role, setRole] = useState<UserRole>(user.role);

    useEffect(() => {
        setName(user.name);
        setRole(user.role);
    }, [user]);

    if (!isOpen) return null;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSave({ ...user, name, role });
    };

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-center justify-center p-4 animate-fade-in"
            onClick={onClose}
        >
            <div 
                className="bg-[var(--color-surface)] rounded-2xl shadow-xl w-full max-w-md p-8 space-y-6 transform transition-all"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex justify-between items-center">
                    <h2 className="text-2xl font-bold text-[var(--color-text)]">تعديل المستخدم</h2>
                    <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] text-3xl">&times;</button>
                </div>
               
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label htmlFor="userName" className="block text-md font-medium text-[var(--color-text)] mb-1">اسم المستخدم</label>
                        <input 
                            type="text" 
                            id="userName" 
                            value={name} 
                            onChange={e => setName(e.target.value)} 
                            className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]" 
                            required 
                        />
                    </div>
                    <div>
                        <label htmlFor="userRole" className="block text-md font-medium text-[var(--color-text)] mb-1">الدور</label>
                        <select 
                            id="userRole" 
                            value={role} 
                            onChange={e => setRole(e.target.value as UserRole)} 
                            className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]"
                        >
                            {/* قائمةُ **الإسناد** لا قائمةُ العرض: `legal_accountant`
                                يرفضه الخادمُ من هذا الباب، و`ess`/`field_staff`
                                يُمنحان من وحدتيهما. انظر `utils/memberRoles.ts`. */}
                            {ASSIGNABLE_MEMBER_ROLES.map((value) => (
                                <option key={value} value={value}>{MEMBER_ROLE_LABELS[value]}</option>
                            ))}
                        </select>
                    </div>
                    <div className="pt-4 flex justify-end gap-3">
                        <button type="button" onClick={onClose} className="bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold py-2 px-6 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500 transition">
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