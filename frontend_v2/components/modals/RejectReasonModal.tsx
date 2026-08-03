import React, { useState } from 'react';

interface RejectReasonModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (reason: string) => void;
}

export const RejectReasonModal: React.FC<RejectReasonModalProps> = ({ isOpen, onClose, onSubmit }) => {
    const [reason, setReason] = useState('');

    if (!isOpen) return null;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!reason.trim()) {
            alert('يرجى إدخال سبب الرفض.');
            return;
        }
        onSubmit(reason);
    };

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4 animate-fade-in"
            onClick={onClose}
        >
            <div 
                className="bg-[var(--color-surface)] rounded-2xl shadow-xl w-full max-w-lg p-8 space-y-6 transform transition-all"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex justify-between items-center">
                    <h2 className="text-2xl font-bold text-[var(--color-text)]">رفض المهمة</h2>
                    <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] text-3xl">&times;</button>
                </div>
               
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label htmlFor="rejectReason" className="block text-md font-medium text-[var(--color-text)] mb-1">سبب الرفض</label>
                        <textarea 
                            id="rejectReason" 
                            value={reason} 
                            onChange={e => setReason(e.target.value)} 
                            rows={4}
                            className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]" 
                            required 
                            placeholder="يرجى توضيح سبب رفض هذه المهمة..."
                        />
                    </div>
                    <div className="pt-4 flex justify-end gap-3">
                        <button type="button" onClick={onClose} className="bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold py-2 px-6 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500 transition">
                            إلغاء
                        </button>
                        <button type="submit" className="bg-red-600 text-white font-bold py-2 px-6 rounded-lg hover:bg-red-700 transition">
                            تأكيد الرفض
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};