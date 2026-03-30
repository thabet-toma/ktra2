import React, { useState, useEffect, useCallback, useRef } from 'react';
import { cloudinaryService } from '../services/cloudinaryService';
// تأكد من أن مسار الاستيراد صحيح لدوال السيرفس التي قمنا بإنشائها سابقاً
import { createGalleryItem, getGalleryChunk, getGalleryCount } from '../services/firestoreService';
// QueryDocumentSnapshot type — replaced firebase import with a simple type alias
type QueryDocumentSnapshot = any;
import { 
  Upload, Trash2, Camera, Cloud, Zap, X, AlertTriangle, 
  CheckCircle, Clock, ArrowLeft, ChevronRight, ChevronLeft, Image as ImageIcon 
} from 'lucide-react';

// --- Types ---
type GalleryItem = {
  id: string;
  url: string;
  description: string;
  createdAt: string;
};

type LocalFile = {
  file: File;
  preview: string;
  description: string;
  id: string;
  status: 'ready' | 'uploading' | 'done' | 'error';
  errorMessage?: string;
};

// --- Constants ---
const PAGE_SIZE = 20;

const PublicGallery: React.FC = () => {
  // --- Upload State ---
  const [localFiles, setLocalFiles] = useState<LocalFile[]>([]);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragRef = useRef<HTMLDivElement>(null);

  // --- Pagination & Gallery State ---
  const [galleryItems, setGalleryItems] = useState<GalleryItem[]>([]);
  const [loadingImages, setLoadingImages] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItemsCount, setTotalItemsCount] = useState(0);

  // تخزين مؤشرات الصفحات للعودة للخلف (Cursor Pagination)
  const [pageCursors, setPageCursors] = useState<(QueryDocumentSnapshot | null)[]>([null]);

  // --- Initialization ---
  const initGallery = useCallback(async () => {
    setLoadingImages(true);
    try {
      // 1. جلب العدد الكلي
      const count = await getGalleryCount();
      setTotalItemsCount(count);
      setTotalPages(Math.ceil(count / PAGE_SIZE) || 1); // على الأقل صفحة واحدة
      
      // 2. إعادة تعيين المؤشرات والصفحة الحالية
      setPageCursors([null]);
      setCurrentPage(1);

      // 3. جلب الصفحة الأولى
      const { items, lastDoc } = await getGalleryChunk(null, PAGE_SIZE);
      setGalleryItems(items);
      
      // تخزين مؤشر الصفحة التالية
      if (lastDoc) {
        setPageCursors(prev => {
          const newCursors = [...prev];
          newCursors[1] = lastDoc; 
          return newCursors;
        });
      }
    } catch (error) {
      console.error("Error loading gallery:", error);
    } finally {
      setLoadingImages(false);
    }
  }, []);

  useEffect(() => {
    initGallery();
  }, [initGallery]);

  // --- Pagination Logic ---
  const fetchPage = async (pageTarget: number, cursor: QueryDocumentSnapshot | null) => {
    setLoadingImages(true);
    try {
      const { items, lastDoc } = await getGalleryChunk(cursor, PAGE_SIZE);
      setGalleryItems(items);
      
      // تحديث المؤشرات إذا كنا نتقدم لصفحة جديدة
      if (lastDoc) {
        setPageCursors(prev => {
          const newCursors = [...prev];
          newCursors[pageTarget] = lastDoc; // تخزين نهاية الصفحة الحالية كبداية للصفحة التالية
          return newCursors;
        });
      }
      
      setCurrentPage(pageTarget);
      // Scroll to top of gallery section
      window.scrollTo({ top: 400, behavior: 'smooth' });
    } catch (error) {
      console.error("Error fetching page:", error);
    } finally {
      setLoadingImages(false);
    }
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) {
      const cursor = pageCursors[currentPage]; // مؤشر نهاية الصفحة الحالية
      fetchPage(currentPage + 1, cursor);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 1) {
      const cursor = pageCursors[currentPage - 2]; // مؤشر بداية الصفحة السابقة
      fetchPage(currentPage - 1, cursor);
    }
  };

  // --- File Processing Logic ---
  useEffect(() => {
    return () => {
      localFiles.forEach(f => URL.revokeObjectURL(f.preview));
    };
  }, [localFiles]);

  const processFiles = useCallback((files: FileList | File[]): void => {
    setGlobalError(null);
    if (!files || files.length === 0) return;

    const newFiles: LocalFile[] = [];
    Array.from(files).forEach((file) => {
      if (!file.type.startsWith('image/')) {
        setGlobalError(`الملف "${file.name}" ليس صورة. يرجى اختيار ملفات صور فقط.`);
        return;
      }
      newFiles.push({
        file,
        preview: URL.createObjectURL(file),
        description: '',
        id: crypto.randomUUID(),
        status: 'ready'
      });
    });

    setLocalFiles(prev => [...prev, ...newFiles]);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    processFiles(e.target.files as FileList);
    e.currentTarget.value = ''; 
  };

  const handleDescriptionChange = (id: string, value: string) => {
    setLocalFiles(prev => prev.map(f => f.id === id ? { ...f, description: value } : f));
  };

  const handleRemoveLocal = (id: string) => {
    setLocalFiles(prev => {
      const fileToRemove = prev.find(f => f.id === id);
      if (fileToRemove) URL.revokeObjectURL(fileToRemove.preview);
      return prev.filter(f => f.id !== id);
    });
  };

  // --- Drag & Drop / Paste ---
  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); if (!isDragging) setIsDragging(true); }, [isDragging]);
  const handleDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); }, []);
  const handleDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIsDragging(false); processFiles(e.dataTransfer.files); }, [processFiles]);
  
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    setGlobalError(null);
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        const file = items[i].getAsFile();
        if (file) files.push(new File([file], `Pasted_Image_${Date.now()}.png`, { type: file.type }));
      }
    }
    if (files.length > 0) { processFiles(files); e.preventDefault(); }
  }, [processFiles]);

  // --- Upload Function ---
  const uploadAll = async () => {
    if (localFiles.length === 0) return;
    setIsUploading(true);
    setGlobalError(null);

    const newLocalFiles = [...localFiles];
    let uploadCount = 0;

    for (let i = 0; i < newLocalFiles.length; i++) {
      if (newLocalFiles[i].status !== 'ready' && newLocalFiles[i].status !== 'error') continue;

      const lf = newLocalFiles[i];
      try {
        if (!lf.description.trim()) {
          newLocalFiles[i] = { ...lf, status: 'error', errorMessage: 'الوصف مطلوب' };
          setLocalFiles([...newLocalFiles]);
          continue;
        }

        newLocalFiles[i] = { ...lf, status: 'uploading', errorMessage: undefined };
        setLocalFiles([...newLocalFiles]);

        const url = await cloudinaryService.uploadImage(lf.file);

        await createGalleryItem({
          url,
          description: lf.description.trim(),
          createdAt: new Date().toISOString()
        });

        newLocalFiles[i] = { ...lf, status: 'done', errorMessage: undefined };
        setLocalFiles([...newLocalFiles]);
        uploadCount++;

      } catch (err: any) {
        console.error('Upload error', err);
        newLocalFiles[i] = { ...lf, status: 'error', errorMessage: err?.message || 'فشل الرفع' };
        setLocalFiles([...newLocalFiles]);
      }
    }

    setIsUploading(false);
    
    // إزالة الملفات المكتملة
    setTimeout(() => {
      setLocalFiles(prev => prev.filter(f => f.status !== 'done'));
      // تحديث المعرض إذا تم رفع ملف واحد على الأقل
      if (uploadCount > 0) {
        initGallery(); // إعادة تحميل الصفحة الأولى لرؤية الصور الجديدة
      }
    }, 1000);
  };

  const goToHome = () => { window.location.href = '/'; };

  // --- Render ---
  return (
    <div 
        className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors duration-300"
        onPaste={handlePaste}
        tabIndex={0}
    >
      <div className="max-w-7xl mx-auto p-4 sm:p-8">
        {/* --- Header --- */}
        <header className="mb-10 relative flex flex-col items-center">
          <button
            onClick={goToHome}
            className="self-end sm:absolute sm:right-0 sm:top-0 flex items-center gap-2 px-4 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors shadow-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>عودة</span>
          </button>
          
          <div className="text-center mt-4 sm:mt-0">
            <h2 className="text-3xl sm:text-4xl font-extrabold text-blue-600 dark:text-blue-400 flex items-center justify-center gap-3 mb-2">
              <Camera className="w-8 h-8 sm:w-10 sm:h-10" />
              صالة عرض الشركة
            </h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-lg mx-auto">
              مساحة مشتركة لصور المنتجات والمشاريع.
              <br />
              <span className="text-xs sm:text-sm bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300 px-2 py-1 rounded mt-2 inline-block">
                نصيحة: يمكنك لصق الصور مباشرة (Ctrl+V)
              </span>
            </p>
          </div>
        </header>

        {/* --- Upload Section --- */}
        <section className="mb-12 bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-6 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50">
            <h3 className="text-xl font-bold flex items-center gap-2 text-gray-800 dark:text-white">
                <Upload className="w-5 h-5 text-blue-500" />
                رفع صور جديدة
            </h3>
          </div>
          
          <div className="p-6">
            {/* Drag Drop Area */}
            <div 
                ref={dragRef}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`
                  relative border-3 border-dashed rounded-xl p-8 text-center transition-all duration-300
                  ${isDragging 
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 scale-[1.01]' 
                      : 'border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500 bg-gray-50 dark:bg-gray-800/50'
                  }
                `}
            >
                <input 
                    id="file-upload"
                    type="file" 
                    accept="image/*" 
                    multiple 
                    onChange={handleFileChange} 
                    className="hidden"
                    disabled={isUploading}
                />
                <label htmlFor="file-upload" className="cursor-pointer flex flex-col items-center justify-center w-full h-full">
                    <div className="w-16 h-16 bg-blue-100 dark:bg-blue-900/50 rounded-full flex items-center justify-center mb-4 text-blue-600 dark:text-blue-400">
                      <Cloud className="w-8 h-8" />
                    </div>
                    <p className="text-lg font-medium text-gray-700 dark:text-gray-200">
                        {isDragging ? 'أفلت الصور هنا!' : 'اضغط لاختيار الصور أو اسحبها هنا'}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                        يدعم JPG, PNG, WEBP (بحد أقصى 5MB)
                    </p>
                </label>
            </div>

            {globalError && (
                <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 rounded-lg flex items-center gap-2 animate-pulse">
                    <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                    <span>{globalError}</span>
                </div>
            )}

            {/* Local Files List */}
            {localFiles.length > 0 && (
              <div className="mt-8 space-y-4">
                <div className="flex justify-between items-end border-b border-gray-200 dark:border-gray-700 pb-2">
                   <h4 className="font-semibold text-gray-700 dark:text-gray-300">
                    قائمة الرفع <span className="text-sm font-normal text-gray-500">({localFiles.length} ملفات)</span>
                   </h4>
                </div>
                
                <div className="grid grid-cols-1 gap-4 max-h-[400px] overflow-y-auto custom-scrollbar p-1">
                {localFiles.map(f => (
                  <div key={f.id} className="flex gap-4 p-4 bg-white dark:bg-gray-700/50 rounded-xl border border-gray-200 dark:border-gray-600 shadow-sm hover:shadow-md transition-shadow">
                    <div className="w-24 h-24 flex-shrink-0 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-600 bg-gray-100 dark:bg-gray-800">
                      <img src={f.preview} alt="preview" className="w-full h-full object-cover" />
                    </div>
                    
                    <div className="flex-1 flex flex-col justify-between">
                      <div className="w-full">
                        <textarea 
                          placeholder="اكتب وصف الصورة هنا (مطلوب)..." 
                          value={f.description} 
                          onChange={(e) => handleDescriptionChange(f.id, e.target.value)} 
                          className={`w-full p-3 text-sm border rounded-lg bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-gray-100 resize-none focus:ring-2 focus:ring-blue-500 outline-none transition-colors
                            ${!f.description.trim() && f.status === 'error' ? 'border-red-500' : 'border-gray-200 dark:border-gray-600'}
                          `}
                          rows={2}
                          disabled={f.status === 'uploading' || f.status === 'done'}
                        />
                        {/* Status Messages */}
                        <div className="mt-2 text-xs font-medium flex items-center gap-2">
                            {f.status === 'ready' && <span className="text-gray-500 flex items-center gap-1"><Clock className="w-3 h-3"/> جاهز للرفع</span>}
                            {f.status === 'uploading' && <span className="text-blue-500 flex items-center gap-1"><Zap className="w-3 h-3 animate-pulse"/> جارٍ الرفع...</span>}
                            {f.status === 'done' && <span className="text-green-500 flex items-center gap-1"><CheckCircle className="w-3 h-3"/> تم الرفع</span>}
                            {f.status === 'error' && <span className="text-red-500 flex items-center gap-1"><AlertTriangle className="w-3 h-3"/> {f.errorMessage}</span>}
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex flex-col justify-center">
                      <button 
                        onClick={() => handleRemoveLocal(f.id)} 
                        disabled={isUploading} 
                        className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
                        title="إزالة"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    </div>
                  </div>
                ))}
                </div>

                <div className="flex justify-end pt-4">
                  <button 
                    onClick={uploadAll} 
                    disabled={isUploading || localFiles.filter(f => (f.status === 'ready' || f.status === 'error') && f.description.trim()).length === 0} 
                    className="
                      flex items-center gap-2 px-8 py-3 
                      bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500
                      text-white font-bold rounded-xl shadow-lg hover:shadow-xl hover:-translate-y-0.5
                      transition-all disabled:bg-gray-300 dark:disabled:bg-gray-700 disabled:cursor-not-allowed disabled:shadow-none disabled:transform-none
                    "
                  >
                    {isUploading ? <><Zap className="w-5 h-5 animate-spin" /> جاري الرفع...</> : <><Cloud className="w-5 h-5" /> بدء الرفع</>}
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* --- Gallery Section --- */}
        <section className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden min-h-[500px]">
           <div className="p-6 border-b border-gray-100 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/50 flex flex-col sm:flex-row justify-between items-center gap-4">
            <h3 className="text-2xl font-bold text-gray-800 dark:text-white flex items-center gap-2">
                <ImageIcon className="w-6 h-6 text-purple-500" />
                الصور المرفوعة
                <span className="text-sm font-normal text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded-full">
                    {totalItemsCount} صورة
                </span>
            </h3>
            
            {/* Pagination Info */}
            <div className="text-sm font-medium text-gray-600 dark:text-gray-300">
                صفحة <span className="text-blue-600 dark:text-blue-400 font-bold">{currentPage}</span> من {totalPages}
            </div>
           </div>
           
           <div className="p-6">
            {loadingImages ? (
                <div className="flex flex-col items-center justify-center py-20">
                    <div className="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-4"></div>
                    <p className="text-gray-500 dark:text-gray-400">جاري تحميل الصور...</p>
                </div>
            ) : (
                <>
                    {galleryItems.length === 0 ? (
                        <div className="text-center py-20">
                            <div className="w-20 h-20 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mx-auto mb-4 text-gray-400">
                                <ImageIcon className="w-10 h-10" />
                            </div>
                            <p className="text-lg text-gray-600 dark:text-gray-300">المعرض فارغ حالياً</p>
                            <p className="text-sm text-gray-400">كن أول من يشارك الصور!</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                            {galleryItems.map(item => (
                                <div 
                                    key={item.id} 
                                    className="group bg-white dark:bg-gray-700 rounded-xl overflow-hidden border border-gray-200 dark:border-gray-600 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-300"
                                >
                                    <div className="w-full h-48 overflow-hidden bg-gray-100 dark:bg-gray-800 relative">
                                        <img 
                                            src={item.url} 
                                            alt={item.description} 
                                            loading="lazy"
                                            className="w-full h-full object-cover transform group-hover:scale-110 transition-transform duration-700" 
                                        />
                                        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors duration-300"></div>
                                    </div>
                                    <div className="p-4">
                                        <p className="text-gray-800 dark:text-gray-100 font-medium text-sm line-clamp-2 leading-relaxed mb-3 min-h-[2.5rem]" title={item.description}>
                                            {item.description || <span className="italic text-gray-400">بدون وصف</span>}
                                        </p>
                                        <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 border-t border-gray-100 dark:border-gray-600 pt-3">
                                            <Clock className="w-3 h-3" />
                                            {new Date(item.createdAt).toLocaleDateString('ar-EG', { year: 'numeric', month: 'long', day: 'numeric' })}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Pagination Controls */}
                    {totalPages > 1 && (
                        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4 border-t border-gray-100 dark:border-gray-700 pt-6">
                            <button
                                onClick={handlePrevPage}
                                disabled={currentPage === 1 || loadingImages}
                                className="flex items-center gap-2 px-5 py-2.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                <ChevronRight className="w-4 h-4" /> {/* أيقونة اليمين تعني السابق في العربية */}
                                السابق
                            </button>

                            <div className="flex items-center gap-2">
                                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                                    // منطق بسيط لعرض أرقام الصفحات القريبة (يمكن تحسينه للمعارض الضخمة جداً)
                                    let pageNum = i + 1;
                                    if (totalPages > 5 && currentPage > 3) {
                                         pageNum = currentPage - 2 + i;
                                    }
                                    if (pageNum > totalPages) return null;

                                    return (
                                        <button
                                            key={pageNum}
                                            onClick={() => pageNum !== currentPage && fetchPage(pageNum, pageCursors[pageNum - 1])} // ملاحظة: المؤشر للصفحة هو المخزن في الفهرس السابق
                                            disabled={loadingImages}
                                            className={`
                                                w-10 h-10 flex items-center justify-center rounded-lg font-bold transition-all
                                                ${currentPage === pageNum 
                                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30' 
                                                    : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                                                }
                                            `}
                                        >
                                            {pageNum}
                                        </button>
                                    );
                                })}
                            </div>

                            <button
                                onClick={handleNextPage}
                                disabled={currentPage === totalPages || loadingImages}
                                className="flex items-center gap-2 px-5 py-2.5 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-200 font-medium hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                التالي
                                <ChevronLeft className="w-4 h-4" /> {/* أيقونة اليسار تعني التالي في العربية */}
                            </button>
                        </div>
                    )}
                </>
            )}
           </div>
        </section>
      </div>
    </div>
  );
};

export default PublicGallery;