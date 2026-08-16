
import React, { useState, useEffect } from 'react';
import { SearchQuery, Task } from '../types';
import { FileDropZone } from './ui/FileDropZone';
import { useToast } from '../contexts/ToastContext';

interface SearchFormProps {
  onSearch: (query: SearchQuery) => void;
  activeTask: Task | null;
  onBackToDashboard: () => void;
}

export const SearchForm: React.FC<SearchFormProps> = ({ onSearch, activeTask, onBackToDashboard }) => {
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [description, setDescription] = useState('');
  const [targetPrice, setTargetPrice] = useState('');
  const toast = useToast();

  useEffect(() => {
    if (activeTask) {
        setDescription(activeTask.description);
        if (activeTask.targetPrice) {
            setTargetPrice(activeTask.targetPrice.toString());
        } else {
            const priceMatch = activeTask.description.match(/\$?(\d+(\.\d+)?)/);
            if (priceMatch) setTargetPrice(priceMatch[1]);
        }
    }
  }, [activeTask]);

  // الاختيار والسحب واللصق (Ctrl+V) صارت كلها داخل `FileDropZone`؛ يبقى هنا حصر
  // الصيغ الثلاث التي يقبلها محرّك التحليل — أضيق ممّا تقبله المنطقة (`image/*`).
  const ANALYZABLE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

  const handleFiles = (files: File[]) => {
    const file = files[0];
    if (!file) return;
    if (!ANALYZABLE_TYPES.includes(file.type)) {
      toast('صيغة غير مدعومة — الصيغ المقبولة للتحليل: JPG أو PNG أو WEBP.', 'error');
      return;
    }
    setImage(file);
    const reader = new FileReader();
    reader.onloadend = () => setPreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (image && description && targetPrice) {
      onSearch({ image, description, targetPrice: parseFloat(targetPrice) });
    } else {
      toast('يرجى تعبئة جميع الحقول ورفع صورة.', 'error');
    }
  };

  return (
    <div className="max-w-5xl mx-auto bg-[var(--color-surface)] rounded-2xl shadow-lg border border-[var(--color-border)] animate-fade-in overflow-hidden">
        {/* Active Task Banner */}
        {activeTask && (
            <div className="bg-blue-50 dark:bg-blue-900/30 p-4 border-b border-blue-100 dark:border-blue-800 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
                <div>
                    <h3 className="text-lg font-bold text-blue-800 dark:text-blue-300 flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
                        مهمة قيد التنفيذ: {activeTask.title}
                    </h3>
                    <p className="text-sm text-blue-600 dark:text-blue-400 mt-1">المواقع: {activeTask.allowedSites.join(', ')}</p>
                </div>
            </div>
        )}

      <div className="p-4 sm:p-8">
          <div className="grid lg:grid-cols-2 gap-6 lg:gap-12 items-start">
            {/* Image Upload Area */}
            <div className="w-full">
                <label className="block text-lg font-medium text-[var(--color-text)] mb-3">صورة المنتج</label>
                {preview ? (
                    <>
                        <div className="w-full aspect-video sm:aspect-square lg:aspect-[4/3] rounded-2xl border-2 border-[var(--color-border)] bg-[var(--color-surface-2)] overflow-hidden">
                            <img src={preview} alt="معاينة صورة المنتج" className="w-full h-full object-contain p-4" />
                        </div>
                        <FileDropZone
                            onFiles={handleFiles}
                            accept="image"
                            variant="compact"
                            hint="تغيير الصورة — اضغط، اسحب، أو الصق (Ctrl+V)"
                            className="mt-2"
                        />
                    </>
                ) : (
                    <FileDropZone
                        onFiles={handleFiles}
                        accept="image"
                        hint="اضغط لرفع صورة، اسحبها إلى هنا، أو الصق (Ctrl+V)"
                        subHint="الصيغ المقبولة للتحليل: JPG أو PNG أو WEBP"
                        className="w-full aspect-video sm:aspect-square lg:aspect-[4/3]"
                    />
                )}
            </div>

            {/* Form Fields */}
            <form onSubmit={handleSubmit} className="space-y-6 flex flex-col h-full justify-center">
                <div>
                    <label htmlFor="description" className="block text-lg font-medium text-[var(--color-text)] mb-2">وصف المنتج</label>
                    <textarea
                        id="description"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className="w-full p-4 text-base bg-[var(--color-surface-2)] rounded-xl border-2 border-[var(--color-border)] focus:border-blue-500 focus:ring-0 transition-colors min-h-[120px]"
                        placeholder="صف المنتج بدقة (اللون، المادة، الاستخدام...)"
                        rows={4}
                    />
                </div>
            
                <div>
                    <label htmlFor="targetPrice" className="block text-lg font-medium text-[var(--color-text)] mb-2">السعر المستهدف ($)</label>
                    <div className="relative">
                        <input
                            type="number"
                            id="targetPrice"
                            value={targetPrice}
                            onChange={(e) => setTargetPrice(e.target.value)}
                            className="w-full p-4 pl-12 text-base bg-[var(--color-surface-2)] rounded-xl border-2 border-[var(--color-border)] focus:border-blue-500 focus:ring-0 transition-colors"
                            placeholder="0.00"
                            min="0"
                            step="0.01"
                        />
                        <span className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] font-bold">$</span>
                    </div>
                </div>

                <div className="flex gap-4 pt-4 mt-auto">
                    {activeTask && (
                        <button
                            type="button"
                            onClick={onBackToDashboard}
                            className="flex-1 bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold py-3 px-6 rounded-xl hover:bg-[var(--color-surface-3)] transition-colors"
                        >
                            تأجيل
                        </button>
                    )}
                    <button
                        type="submit"
                        className="flex-[2] bg-blue-600 text-white font-bold py-3 px-6 rounded-xl text-lg hover:bg-blue-700 shadow-lg hover:shadow-blue-500/30 transition-all transform active:scale-95"
                    >
                        بدء التحليل الذكي
                    </button>
                </div>
            </form>
          </div>
      </div>
    </div>
  );
};
