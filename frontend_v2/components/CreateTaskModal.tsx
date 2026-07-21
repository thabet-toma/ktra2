import React, { useState, useRef, useEffect } from 'react';
import { User, Task, TaskCategory, TaskPriority, Category } from '../types';
import { cloudinaryService } from '../services/cloudinaryService';
import { getCategories } from '../services/firestoreService';

interface CreateTaskModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (task: Omit<Task, 'id' | 'status' | 'totalWorkTime' | 'logs' | 'createdAt' | 'updatedAt' | 'submissions'> & { 
        assignedTo: string[];
        images?: string[];
    }) => void;
    employees: User[];
    categories?: Category[]; // إضافة prop للفئات
}

export const CreateTaskModal: React.FC<CreateTaskModalProps> = ({ 
    isOpen, 
    onClose, 
    onSubmit, 
    employees,
    categories: propCategories // تلقي الفئات كـ prop
}) => {
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [assignedTo, setAssignedTo] = useState<string[]>([]);
    const [dueDate, setDueDate] = useState('');
    const [category, setCategory] = useState<TaskCategory>('');
    const [priority, setPriority] = useState<TaskPriority>('medium');
    const [targetPrice, setTargetPrice] = useState('');
    const [allowedSites, setAllowedSites] = useState<string[]>(['alibaba.com']);
    const [selectedImages, setSelectedImages] = useState<File[]>([]);
    const [imagePreviews, setImagePreviews] = useState<string[]>([]);
    const [uploading, setUploading] = useState(false);
    const [loadingCategories, setLoadingCategories] = useState(false);
    const [categories, setCategories] = useState<Category[]>([]);
    
    const fileInputRef = useRef<HTMLInputElement>(null);

    // جلب الفئات إذا لم تكن ممررة
    useEffect(() => {
        const fetchCategories = async () => {
            if (propCategories && propCategories.length > 0) {
                setCategories(propCategories);
                // تعيين أول فئة كافتراضية
                if (propCategories[0] && !category) {
                    setCategory(propCategories[0].id as TaskCategory);
                }
                return;
            }
            
            setLoadingCategories(true);
            try {
                const fetchedCategories = await getCategories();
                setCategories(fetchedCategories);
                // تعيين أول فئة كافتراضية
                if (fetchedCategories[0] && !category) {
                    setCategory(fetchedCategories[0].id as TaskCategory);
                }
            } catch (error) {
                // console suppressed
                // فئات افتراضية للطوارئ
                setCategories([
                    { id: 'electronics', name: 'إلكترونيات' },
                    { id: 'electrical', name: 'كهربائيات' },
                    { id: 'clothing', name: 'ملابس' },
                ]);
            } finally {
                setLoadingCategories(false);
            }
        };

        if (isOpen) {
            fetchCategories();
        }
    }, [isOpen, propCategories, category]);

    if (!isOpen) return null;

    // معالجة اختيار الصور
    const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files) return;

        const newFiles = Array.from(files);
        
        // التحقق من عدد الصور
        if (selectedImages.length + newFiles.length > 10) {
            alert('يمكنك رفع最多 10 صور فقط');
            return;
        }

        setSelectedImages(prev => [...prev, ...newFiles]);

        // إنشاء معاينات للصور
        newFiles.forEach((file: File) => {
            const reader = new FileReader();
            
            reader.onload = (event: ProgressEvent<FileReader>) => {
                const target = event.target;
                if (target && target.result && typeof target.result === 'string') {
                    setImagePreviews(prev => [...prev, target.result as string]);
                }
            };
            
            reader.onerror = () => {
                // console suppressed
            };
            
            reader.readAsDataURL(file);
        });

        // إعادة تعيين حقل الإدخال
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    // حذف صورة محددة
    const removeImage = (index: number) => {
        setSelectedImages(prev => prev.filter((_, i) => i !== index));
        setImagePreviews(prev => prev.filter((_, i) => i !== index));
    };

    // رفع الصور إلى Cloudinary
    const uploadImages = async (): Promise<string[]> => {
        if (selectedImages.length === 0) return [];
        
        setUploading(true);
        try {
            const imageUrls = await cloudinaryService.uploadMultipleImages(selectedImages);
            return imageUrls;
        } catch (error) {
            // console suppressed
            throw new Error('فشل في رفع الصور إلى السحابة');
        } finally {
            setUploading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        
        if (!title || !description || assignedTo.length === 0 || !dueDate) {
            alert('يرجى ملء جميع الحقول وتحديد موظف واحد على الأقل');
            return;
        }

        if (!category) {
            alert('يرجى اختيار فئة للمهمة');
            return;
        }

        setUploading(true);

        try {
            let uploadedImageUrls: string[] = [];
            
            // رفع الصور إذا كانت موجودة
            if (selectedImages.length > 0) {
                uploadedImageUrls = await uploadImages();
            }

            // إعداد بيانات المهمة
            const taskData = {
                title,
                description,
                assignedTo,
                dueDate,
                category,
                allowedSites,
                priority,
                targetPrice: targetPrice ? parseFloat(targetPrice) : undefined,
                images: uploadedImageUrls,
                imageUrl: uploadedImageUrls[0] || undefined,
            };
            onSubmit(taskData);

            // إعادة تعيين النموذج
            resetForm();
            onClose();
            
        } catch (error) {
            // console suppressed
            alert('حدث خطأ أثناء إنشاء المهمة. يرجى المحاولة مرة أخرى.');
        } finally {
            setUploading(false);
        }
    };

    const resetForm = () => {
        setTitle('');
        setDescription('');
        setAssignedTo([]);
        setDueDate('');
        setCategory(categories[0]?.id as TaskCategory || 'electronics');
        setAllowedSites(['alibaba.com']);
        setPriority('medium');
        setTargetPrice('');
        setSelectedImages([]);
        setImagePreviews([]);
    };

    const handleSiteChange = (site: string) => {
        setAllowedSites(prev => 
            prev.includes(site) ? prev.filter(s => s !== site) : [...prev, site]
        );
    };

    const handleEmployeeSelect = (employeeId: string) => {
        setAssignedTo(prev => 
            prev.includes(employeeId) 
                ? prev.filter(id => id !== employeeId)
                : [...prev, employeeId]
        );
    };

    const handleSelectAll = () => {
        if (assignedTo.length === employees.length) {
            setAssignedTo([]);
        } else {
            setAssignedTo(employees.map(emp => emp.id));
        }
    };

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-50 z-40 flex items-center justify-center p-4 animate-fade-in"
            onClick={onClose}
        >
            <div 
                className="bg-[var(--color-surface)] rounded-2xl shadow-xl w-full max-w-2xl p-8 space-y-6 transform transition-all max-h-[90vh] overflow-y-auto"
                onClick={e => e.stopPropagation()}
            >
                <div className="flex justify-between items-center">
                    <h2 className="text-2xl font-bold text-[var(--color-text)]">إنشاء مهمة جديدة</h2>
                    <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-muted)] text-3xl">&times;</button>
                </div>
               
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label htmlFor="taskName" className="block text-md font-medium text-[var(--color-text)] mb-1">
                                عنوان المهمة *
                            </label>
                            <input 
                                type="text" 
                                id="taskName" 
                                value={title} 
                                onChange={e => setTitle(e.target.value)} 
                                className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]" 
                                required 
                                disabled={uploading}
                            />
                        </div>
                        <div>
                            <label htmlFor="dueDate" className="block text-md font-medium text-[var(--color-text)] mb-1">
                                تاريخ التسليم *
                            </label>
                            <input 
                                type="date" 
                                id="dueDate" 
                                value={dueDate} 
                                onChange={e => setDueDate(e.target.value)} 
                                className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]" 
                                required 
                                disabled={uploading}
                            />
                        </div>
                    </div>
                    
                    <div>
                        <label htmlFor="description" className="block text-md font-medium text-[var(--color-text)] mb-1">
                            وصف المهمة *
                        </label>
                        <textarea 
                            id="description" 
                            value={description} 
                            onChange={e => setDescription(e.target.value)} 
                            rows={3} 
                            className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]" 
                            required
                            disabled={uploading}
                        ></textarea>
                    </div>

                    {/* قسم رفع الصور */}
                    <div>
                        <label className="block text-md font-medium text-[var(--color-text)] mb-2">
                            صور المهمة (اختياري)
                            <span className="text-sm text-[var(--color-text-muted)] mr-2">
                                ({selectedImages.length} / 10 صور)
                            </span>
                        </label>
                        
                        <div className="mb-3">
                            <input
                                ref={fileInputRef}
                                type="file"
                                multiple
                                accept="image/*"
                                onChange={handleImageSelect}
                                className="hidden"
                                id="image-upload"
                                disabled={uploading}
                            />
                            <label
                                htmlFor="image-upload"
                                className={`inline-flex items-center px-4 py-2 rounded-lg cursor-pointer transition-colors ${
                                    uploading 
                                        ? 'bg-gray-400 text-gray-200 cursor-not-allowed' 
                                        : 'bg-blue-500 text-white hover:bg-blue-600'
                                }`}
                            >
                                <span>📷</span>
                                <span className="mr-2">اختر الصور</span>
                            </label>
                            <p className="text-sm text-[var(--color-text-muted)] mt-1">
                                يمكنك رفع حتى 10 صور (JPEG, PNG, GIF)
                            </p>
                        </div>

                        {imagePreviews.length > 0 && (
                            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mt-4">
                                {imagePreviews.map((preview, index) => (
                                    <div key={index} className="relative group">
                                        <img
                                            src={preview}
                                            alt={`معاينة ${index + 1}`}
                                            className="w-full h-24 object-cover rounded-lg border border-[var(--color-border)]"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => removeImage(index)}
                                            disabled={uploading}
                                            className="absolute top-1 left-1 bg-red-500 text-white rounded-full w-6 h-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-50"
                                        >
                                            ×
                                        </button>
                                        <div className="text-xs text-[var(--color-text-muted)] truncate mt-1">
                                            {selectedImages[index].name}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    
                    {/* قسم إسناد المهمة */}
                    <div>
                        <label className="block text-md font-medium text-[var(--color-text)] mb-2">
                            إسناد إلى الموظفين *
                            <span className="text-sm text-[var(--color-text-muted)] mr-2">
                                ({assignedTo.length} / {employees.length} محددين)
                            </span>
                        </label>
                        
                        <div className="mb-3">
                            <button
                                type="button"
                                onClick={handleSelectAll}
                                disabled={uploading}
                                className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                                    assignedTo.length === employees.length
                                        ? 'bg-green-500 text-white'
                                        : 'bg-[var(--color-surface-3)] text-[var(--color-text)] hover:bg-gray-300 dark:hover:bg-gray-600'
                                } ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}
                            >
                                {assignedTo.length === employees.length ? 'إلغاء تحديد الكل' : 'تحديد جميع الموظفين'}
                            </button>
                        </div>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-40 overflow-y-auto p-2 border border-[var(--color-border)] rounded-lg">
                            {employees.map(emp => (
                                <label key={emp.id} className="flex items-center space-x-3 p-2 hover:bg-[var(--color-surface-2)] rounded cursor-pointer">
                                    <input 
                                        type="checkbox"
                                        checked={assignedTo.includes(emp.id)}
                                        onChange={() => handleEmployeeSelect(emp.id)}
                                        className="h-5 w-5 rounded border-[var(--color-border)] text-blue-600 focus:ring-blue-500" 
                                        disabled={uploading}
                                    />
                                    <span className="flex-1 text-[var(--color-text)]">{emp.name}</span>
                                    <span className="text-xs text-[var(--color-text-muted)]">{emp.email}</span>
                                </label>
                            ))}
                        </div>
                        
                        {assignedTo.length === 0 && (
                            <p className="text-red-500 text-sm mt-1">يجب تحديد موظف واحد على الأقل</p>
                        )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label htmlFor="targetPrice" className="block text-md font-medium text-[var(--color-text)] mb-1">
                                السعر المستهدف ($)
                            </label>
                            <input 
                                type="number" 
                                id="targetPrice" 
                                value={targetPrice} 
                                onChange={e => setTargetPrice(e.target.value)} 
                                className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]" 
                                disabled={uploading}
                            />
                        </div>
                        <div>
                            <label htmlFor="priority" className="block text-md font-medium text-[var(--color-text)] mb-1">
                                الأولوية
                            </label>
                            <select 
                                id="priority" 
                                value={priority} 
                                onChange={e => setPriority(e.target.value as TaskPriority)} 
                                className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]"
                                disabled={uploading}
                            >
                                <option value="low">منخفضة</option>
                                <option value="medium">متوسطة</option>
                                <option value="high">عالية</option>
                                <option value="urgent">عاجلة</option>
                            </select>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label htmlFor="category" className="block text-md font-medium text-[var(--color-text)] mb-1">
                                فئة المهمة *
                            </label>
                            {loadingCategories ? (
                                <div className="flex items-center justify-center p-4 border border-[var(--color-border)] rounded-lg">
                                    <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mr-2"></div>
                                    <span className="text-[var(--color-text-muted)]">جاري تحميل الفئات...</span>
                                </div>
                            ) : categories.length > 0 ? (
                                <select 
                                    id="category" 
                                    value={category} 
                                    onChange={e => setCategory(e.target.value as TaskCategory)} 
                                    className="w-full p-2 border border-[var(--color-border)] rounded-lg bg-[var(--color-surface-2)] text-[var(--color-text)]"
                                    disabled={uploading}
                                    required
                                >
                                    <option value="">اختر فئة</option>
                                    {categories.map((cat) => (
                                        <option key={cat.id} value={cat.id}>
                                            {cat.name}
                                        </option>
                                    ))}
                                </select>
                            ) : (
                                <div className="p-2 border border-red-300 dark:border-red-600 rounded-lg bg-red-50 dark:bg-red-900/20">
                                    <p className="text-red-600 dark:text-red-400 text-sm">
                                        لا توجد فئات متاحة. يرجى إضافة فئات أولاً.
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    <div>
                        <label className="block text-md font-medium text-[var(--color-text)] mb-2">المواقع المسموح بها</label>
                        <div className="flex items-center gap-4">
                            <label className="flex items-center space-x-2">
                                <input 
                                    type="checkbox" 
                                    checked={allowedSites.includes('alibaba.com')} 
                                    onChange={() => handleSiteChange('alibaba.com')} 
                                    className="h-5 w-5 rounded border-[var(--color-border)] text-blue-600 focus:ring-blue-500" 
                                    disabled={uploading}
                                />
                                <span>alibaba.com</span>
                            </label>
                            <label className="flex items-center space-x-2">
                                <input 
                                    type="checkbox" 
                                    checked={allowedSites.includes('1688.com')} 
                                    onChange={() => handleSiteChange('1688.com')} 
                                    className="h-5 w-5 rounded border-[var(--color-border)] text-blue-600 focus:ring-blue-500" 
                                    disabled={uploading}
                                />
                                <span>1688.com</span>
                            </label>
                        </div>
                    </div>

                    <div className="pt-4 flex justify-end gap-3">
                        <button 
                            type="button" 
                            onClick={onClose} 
                            disabled={uploading}
                            className="bg-[var(--color-surface-3)] text-[var(--color-text)] font-bold py-2 px-6 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-500 transition disabled:opacity-50"
                        >
                            إلغاء
                        </button>
                        <button 
                            type="submit" 
                            disabled={uploading || !category || loadingCategories}
                            className="bg-blue-600 text-white font-bold py-2 px-6 rounded-lg hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            {uploading ? (
                                <>
                                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                    جاري الإنشاء...
                                </>
                            ) : (
                                'إنشاء المهمة'
                            )}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};