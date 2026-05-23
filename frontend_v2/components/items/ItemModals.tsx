import React, { useState } from 'react';
import { X } from 'lucide-react';
import { Category } from '@/types';
import { categoriesService, brandsService } from '@/services/firestoreService';
import { subCategoriesService } from '@/services/subCategoriesService';

interface ModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: () => void;
}

// --- مودال الفئة الرئيسية ---
export const CategoryModal: React.FC<ModalProps> = ({ isOpen, onClose, onSuccess }) => {
    const [name, setName] = useState('');

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await categoriesService.addCategoryToDb({
                id: crypto.randomUUID(),
                name,
                createdAt: new Date().toISOString()
            });
            setName('');
            onSuccess();
            onClose();
        } catch (error) {
            console.error(error);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[101] p-4" onClick={onClose}>
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl w-full max-w-md" onClick={e => e.stopPropagation()}>
                <div className="p-6 border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-center">
                    <h2 className="text-xl font-bold dark:text-white">إضافة فئة رئيسية</h2>
                    <button onClick={onClose}><X className="w-6 h-6 aseel-text-soft" /></button>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <input
                        type="text"
                        required
                        placeholder="اسم الفئة الرئيسية"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                    />
                    <button type="submit" className="w-full py-2 aseel-btn-primary">إضافة</button>
                </form>
            </div>
        </div>
    );
};

// --- مودال الفئة الفرعية ---
interface SubCategoryModalProps extends ModalProps {
    categories: Category[];
    initialCategoryId?: string;
}

export const SubCategoryModal: React.FC<SubCategoryModalProps> = ({ isOpen, onClose, onSuccess, categories, initialCategoryId }) => {
    const [name, setName] = useState('');
    const [categoryId, setCategoryId] = useState(initialCategoryId || '');

    // تحديث القيمة إذا تغيرت من الخارج
    React.useEffect(() => {
        if (initialCategoryId) setCategoryId(initialCategoryId);
    }, [initialCategoryId]);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!categoryId) return alert('الرجاء اختيار فئة رئيسية');

        try {
            await subCategoriesService.addSubCategoryToDb({
                id: crypto.randomUUID(),
                name,
                categoryId,
                createdAt: new Date().toISOString()
            });
            setName('');
            onSuccess();
            onClose();
        } catch (error) {
            console.error(error);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[101] p-4" onClick={onClose}>
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl w-full max-w-md" onClick={e => e.stopPropagation()}>
                <div className="p-6 border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-center">
                    <h2 className="text-xl font-bold dark:text-white">إضافة فئة فرعية</h2>
                    <button onClick={onClose}><X className="w-6 h-6 aseel-text-soft" /></button>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm mb-1 dark:aseel-text-soft">تابع للفئة الرئيسية</label>
                        <select
                            value={categoryId}
                            onChange={(e) => setCategoryId(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                            required
                        >
                            <option value="">اختر فئة رئيسية...</option>
                            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm mb-1 dark:aseel-text-soft">اسم الفئة الفرعية</label>
                        <input
                            type="text"
                            required
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="w-full px-3 py-2 rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                        />
                    </div>
                    <button type="submit" className="w-full py-2 aseel-btn-primary">إضافة</button>
                </form>
            </div>
        </div>
    );
};

// --- مودال الماركة ---
export const BrandModal: React.FC<ModalProps> = ({ isOpen, onClose, onSuccess }) => {
    const [name, setName] = useState('');

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await brandsService.addBrand({
                id: crypto.randomUUID(),
                name,
                createdAt: new Date().toISOString()
            });
            setName('');
            onSuccess();
            onClose();
        } catch (error) {
            console.error(error);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[101] p-4" onClick={onClose}>
            <div className="aseel-bg-field dark:aseel-bg-panel rounded-xl w-full max-w-md" onClick={e => e.stopPropagation()}>
                <div className="p-6 border-b aseel-border-soft dark:aseel-border-soft flex justify-between items-center">
                    <h2 className="text-xl font-bold dark:text-white">إضافة ماركة جديدة</h2>
                    <button onClick={onClose}><X className="w-6 h-6 aseel-text-soft" /></button>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <input
                        type="text"
                        required
                        placeholder="اسم الماركة"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border dark:aseel-bg-panel dark:aseel-border-soft dark:text-white"
                    />
                    <button type="submit" className="w-full py-2 aseel-btn-primary">إضافة</button>
                </form>
            </div>
        </div>
    );
};