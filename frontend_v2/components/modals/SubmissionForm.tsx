import React, { useState, useEffect } from "react";
import { Submission, SubmissionItem } from "../../types";
import { DeleteIcon } from "../icons/DeleteIcon";
import { cloudinaryService } from "../../services/cloudinaryService";
import { FileDropZone } from "../ui/FileDropZone";
import { useToast } from "../../contexts/ToastContext";

interface SubmissionFormProps {
  initialData?: Submission;
  onSubmit: (data: any) => void;
  onCancel: () => void;
  isEditMode?: boolean;
  userRole: string;
  taskId?: string;
  userId?: string;
}

const SubmissionForm: React.FC<SubmissionFormProps> = ({
  initialData,
  onSubmit,
  onCancel,
  isEditMode = false,
  userRole,
  taskId,
  userId,
}) => {
  const [items, setItems] = useState<SubmissionItem[]>([]);
  const [currentLink, setCurrentLink] = useState("");
  const [currentPrice, setCurrentPrice] = useState("");
  const [currentNotes, setCurrentNotes] = useState("");
  const [currentAttachment, setCurrentAttachment] = useState<{
    name: string;
    url: string;
    type: "file" | "images";
  } | null>(null);
  const [selectedImages, setSelectedImages] = useState<File[]>([]);
  const [imagePreviews, setImagePreviews] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const toast = useToast();

  const storageKey =
    taskId && userId ? `submission_draft_${taskId}_${userId}` : null;

  useEffect(() => {
    let initialItems: SubmissionItem[] = [];
    if (storageKey) {
      const savedData = localStorage.getItem(storageKey);
      if (savedData) {
        try {
          const parsedData = JSON.parse(savedData);
          if (parsedData.items && Array.isArray(parsedData.items)) {
            initialItems = parsedData.items;
          }
        } catch (error) {
          // console suppressed
        }
      }
    }

    if (initialItems.length === 0 && initialData?.items) {
      initialItems = initialData.items.map((item) => ({
        ...item,
        isNew: false,
      }));
    }
    setItems(initialItems);
  }, [initialData, storageKey]);

  useEffect(() => {
    if (storageKey && items.length > 0) {
      const saveData = {
        items: items,
        timestamp: new Date().toISOString(),
      };
      localStorage.setItem(storageKey, JSON.stringify(saveData));
    }
  }, [items, storageKey]);

  // معالجة اختيار ملف PDF أو Word
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];

      // التحقق من نوع الملف
      const allowedTypes = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      ];
      if (!allowedTypes.includes(file.type)) {
        alert("يُسمح فقط بملفات PDF و Word");
        return;
      }

      // التحقق من حجم الملف (10MB كحد أقصى)
      if (file.size > 10 * 1024 * 1024) {
        alert("حجم الملف كبير جداً. الحد الأقصى 10MB");
        return;
      }

      const reader = new FileReader();
      reader.onloadend = () => {
        setCurrentAttachment({
          name: file.name,
          url: reader.result as string,
          type: "file",
        });
        // مسح الصور إذا كان هناك ملف
        setSelectedImages([]);
        setImagePreviews([]);
      };
      reader.readAsDataURL(file);
    }
  };

  // معالجة إضافة صور (اختيار ملف، سحب، أو لصق من الحافظة) — يُبقي حدّ 3 صور.
  // فحص النوع والحجم صار داخل `FileDropZone` (برسالة toast)، فما يصل هنا مقبول.
  // الصور مؤجّلة: تبقى ملفات محلية بمعاينة، وتُرفع عند «إضافة البند».
  const addImageFiles = (newFiles: File[]) => {
    if (newFiles.length === 0) return;

    if (selectedImages.length + newFiles.length > 3) {
      toast("يمكنك إرفاق 3 صور كحدّ أقصى للبند الواحد.", "info");
      return;
    }

    setSelectedImages((prev) => [...prev, ...newFiles]);

    newFiles.forEach((file: File) => {
      const reader = new FileReader();
      reader.onload = (event: ProgressEvent<FileReader>) => {
        const target = event.target;
        if (target && target.result && typeof target.result === "string") {
          setImagePreviews((prev) => [...prev, target.result]);
        }
      };
      reader.readAsDataURL(file);
    });

    setCurrentAttachment(null);
  };

  // حذف صورة محددة
  const removeImage = (index: number) => {
    setSelectedImages((prev) => prev.filter((_, i) => i !== index));
    setImagePreviews((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddItem = async () => {
    if (!currentLink.trim()) {
      alert("رابط المنتج مطلوب");
      return;
    }
    if (!currentPrice.trim()) {
      alert("سعر المنتج مطلوب");
      return;
    }

    setUploading(true);

    try {
      let imageUrls: string[] = [];

      // رفع الصور إلى Cloudinary إذا كانت موجودة
      if (selectedImages.length > 0) {
        imageUrls = await cloudinaryService.uploadMultipleImages(
          selectedImages
        );
      }

      const newItem: SubmissionItem = {
        id: crypto.randomUUID(),
        productLink: currentLink.trim(),
        productPrice: parseFloat(currentPrice),
        notes: currentNotes.trim(),
        attachmentName: currentAttachment?.name,
        attachmentUrl: currentAttachment?.url,
        images: imageUrls,
        attachmentType:
          selectedImages.length > 0
            ? "images"
            : currentAttachment?.type || undefined,
        isNew: true,
        createdAt: new Date().toISOString(),
      };

      const updatedItems = [...items, newItem];
      setItems(updatedItems);

      if (storageKey) {
        const saveData = {
          items: updatedItems,
          timestamp: new Date().toISOString(),
        };
        localStorage.setItem(storageKey, JSON.stringify(saveData));
      }

      resetCurrentItem();
    } catch (error) {
      // console suppressed
      toast("حدث خطأ أثناء رفع الصور. يرجى المحاولة مرة أخرى.", "error");
    } finally {
      setUploading(false);
    }
  };

  const resetCurrentItem = () => {
    setCurrentLink("");
    setCurrentPrice("");
    setCurrentNotes("");
    setCurrentAttachment(null);
    setSelectedImages([]);
    setImagePreviews([]);

    // إعادة تعيين حقل المرفق. حقل الصور صار داخل `FileDropZone` ويمسح نفسه بعد كل اختيار.
    const fileInput = document.getElementById(
      "submission-file-input"
    ) as HTMLInputElement;
    if (fileInput) fileInput.value = "";
  };

  const handleRemoveItem = (id: string) => {
    const itemToRemove = items.find((item) => item.id === id);
    if (itemToRemove?.isNew) {
      const updatedItems = items.filter((item) => item.id !== id);
      setItems(updatedItems);
      if (storageKey) {
        const saveData = {
          items: updatedItems,
          timestamp: new Date().toISOString(),
        };
        localStorage.setItem(storageKey, JSON.stringify(saveData));
      }
    }
  };

  const canAddNewItems = () => {
    if (!isEditMode) return true;
    if (initialData?.status === "approved") {
      return false;
    }
    return true;
  };

  const getNewItems = () => items.filter((item) => item.isNew);
  const getExistingItems = () => items.filter((item) => !item.isNew);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const totalItems = items.length;
    const newItemsCount = getNewItems().length;

    if (totalItems === 0) {
      alert("لا يمكنك تسليم المهمة بدون إضافة بند واحد على الأقل.");
      return;
    }
    if (isEditMode && newItemsCount === 0) {
      alert("لم تقم بإضافة أي بنود جديدة.");
      return;
    }
    setShowConfirmDialog(true);
  };

  const confirmSubmit = () => {
    const submissionData = {
      items: isEditMode ? getNewItems() : items,
      status: "pending",
      newItemsCount: isEditMode ? getNewItems().length : items.length,
    };
    if (storageKey) {
      localStorage.removeItem(storageKey);
    }
    onSubmit(submissionData);
    setShowConfirmDialog(false);
  };

  const handleCancel = () => {
    const hasNewItems = getNewItems().length > 0;
    if (hasNewItems) {
      const confirmCancel = window.confirm(
        "هل تريد حقاً إلغاء العملية؟ البنود التي أضفتها محفوظة محلياً."
      );
      if (confirmCancel) onCancel();
    } else {
      onCancel();
    }
  };

  const clearSavedData = () => {
    if (storageKey) {
      localStorage.removeItem(storageKey);
      setItems(
        initialData?.items?.map((item) => ({ ...item, isNew: false })) || []
      );
    }
  };

  const hasSavedData = storageKey && localStorage.getItem(storageKey);

  const getFormTitle = () => {
    if (!isEditMode) return "تسليم جديد";
    if (
      initialData?.status === "submitted" ||
      initialData?.status === "pending"
    )
      return "إضافة بنود إضافية";
    if (initialData?.status === "rejected") return "تعديل التسليم المرفوض";
    return "عرض التسليم";
  };

  return (
    <div className="flex flex-col h-full bg-[var(--color-surface-2)] sm:rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex justify-between items-center p-4 md:p-6 bg-[var(--color-surface)] border-b border-[var(--color-border)] shadow-sm z-10 sticky top-0">
        <div>
          <h4 className="font-bold text-lg md:text-xl text-[var(--color-text)]">
            {getFormTitle()}
          </h4>
          {isEditMode && (
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              البنود القديمة مثبتة، يمكنك إضافة المزيد فقط.
            </p>
          )}
        </div>

        {hasSavedData && (
          <div className="flex items-center gap-2 md:gap-3 bg-green-50 dark:bg-green-900/30 px-3 py-1.5 rounded-full border border-green-100 dark:border-green-800">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
            <span className="text-xs font-medium text-green-700 dark:text-green-300 hidden sm:inline">
              مسودة محفوظة
            </span>
            <button
              onClick={clearSavedData}
              className="text-xs text-red-500 hover:text-red-700 hover:underline mr-2 border-r border-green-200 dark:border-green-700 pr-2"
            >
              حذف
            </button>
          </div>
        )}
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 custom-scrollbar">
        {/* Existing Items */}
        {isEditMode && getExistingItems().length > 0 && (
          <section className="space-y-3">
            <h5 className="text-xs font-bold uppercase tracking-wider text-[var(--color-text-muted)] px-1">
              البنود المُرسلة سابقاً ({getExistingItems().length})
            </h5>
            <div className="grid grid-cols-1 gap-3">
              {getExistingItems().map((item, idx) => (
                <div
                  key={item.id}
                  className="group p-4 bg-[var(--color-surface-3)] rounded-xl border border-transparent dark:border-gray-700 flex gap-4 items-start select-none opacity-80 hover:opacity-100 transition-opacity"
                >
                  <div className="w-8 h-8 rounded-full bg-[var(--color-surface-3)] flex items-center justify-center text-xs font-bold text-[var(--color-text-muted)] shrink-0">
                    {idx + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start">
                      <a
                        href={item.productLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-semibold text-[var(--color-text-muted)] hover:text-blue-600 truncate block max-w-[90%]"
                      >
                        {item.productLink}
                      </a>
                      <span className="text-xs bg-[var(--color-surface-3)] text-[var(--color-text-muted)] px-2 py-0.5 rounded text-[10px]">
                        مثبت
                      </span>
                    </div>
                    <div className="text-sm text-[var(--color-text-muted)] mt-1 flex items-center gap-2">
                      <span>💰 {item.productPrice} $</span>
                      {item.attachmentName && (
                        <span>📎 {item.attachmentName}</span>
                      )}
                      {item.images && item.images.length > 0 && (
                        <span>🖼️ {item.images.length} صورة</span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Input Form */}
        {canAddNewItems() ? (
          <section className="bg-[var(--color-surface)] p-5 md:p-6 rounded-2xl shadow-sm border border-[var(--color-border)]">
            <h5 className="text-sm font-bold text-[var(--color-text)] mb-4 flex items-center gap-2">
              <span className="w-1 h-5 bg-blue-500 rounded-full"></span>
              إضافة بند جديد
            </h5>

            <div className="space-y-4">
              {/* Link & Price */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[var(--color-text-muted)]">
                    رابط المنتج <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="url"
                    value={currentLink}
                    onChange={(e) => setCurrentLink(e.target.value)}
                    placeholder="https://..."
                    className="w-full h-11 px-4 text-sm bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-[var(--color-text-muted)]">
                    السعر ($) <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="number"
                    value={currentPrice}
                    onChange={(e) => setCurrentPrice(e.target.value)}
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                    className="w-full h-11 px-4 text-sm bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                  />
                </div>
              </div>

              {/* Notes */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[var(--color-text-muted)]">
                  ملاحظات
                </label>
                <textarea
                  value={currentNotes}
                  onChange={(e) => setCurrentNotes(e.target.value)}
                  rows={2}
                  placeholder="تفاصيل إضافية..."
                  className="w-full p-4 text-sm bg-[var(--color-surface-2)] border border-[var(--color-border)] rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
                />
              </div>

              {/* File Upload - PDF/Word */}
              {/* <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[var(--color-text-muted)]">
                  مرفق PDF أو Word (اختياري)
                </label>
                <div className="relative">
                  <input
                    id="submission-file-input"
                    type="file"
                    accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={handleFileChange}
                    className="block w-full text-xs text-[var(--color-text-muted)] file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 dark:file:bg-gray-700 dark:file:text-gray-300 cursor-pointer"
                  />
                </div>
                {currentAttachment && currentAttachment.type === "file" && (
                  <p className="text-xs text-green-600 flex items-center gap-1 mt-1">
                    <svg
                      className="w-3 h-3"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    {currentAttachment.name}
                  </p>
                )}
              </div> */}

              {/* Image Upload */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-[var(--color-text-muted)]">
                  صور المنتج (اختياري - 3 صور)
                </label>
                <FileDropZone
                  onFiles={addImageFiles}
                  accept="image"
                  multiple
                  busy={uploading}
                  disabled={selectedImages.length >= 3}
                  variant="compact"
                  hint={
                    selectedImages.length >= 3
                      ? "اكتمل الحد الأقصى (3 صور)"
                      : "اضغط لاختيار الصور، اسحبها إلى هنا، أو الصق (Ctrl+V)"
                  }
                />

                {/* معاينات الصور */}
                {imagePreviews.length > 0 && (
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    {imagePreviews.map((preview, index) => (
                      <div key={index} className="relative group">
                        <img
                          src={preview}
                          alt={`معاينة ${index + 1}`}
                          className="w-full h-20 object-cover rounded-lg border border-[var(--color-border)]"
                        />
                        <button
                          type="button"
                          onClick={() => removeImage(index)}
                          className="absolute top-1 left-1 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {selectedImages.length > 0 && (
                  <p className="text-xs text-green-600 mt-1">
                    {selectedImages.length} / 3 صور محددة
                  </p>
                )}
              </div>

              {/* Add Button */}
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleAddItem}
                  disabled={uploading}
                  className="h-11 px-6 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl shadow-lg shadow-blue-500/30 hover:shadow-blue-500/50 transition-all active:scale-95 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {uploading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      جاري الإضافة...
                    </>
                  ) : (
                    <>
                      <span className="text-lg leading-none">+</span>
                      <span>إضافة البند</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </section>
        ) : (
          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-xl p-6 text-center">
            <div className="w-12 h-12 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto mb-3 text-xl">
              ✅
            </div>
            <p className="text-sm font-bold text-green-800 dark:text-green-200">
              تم قبول هذه المهمة واعتمادها نهائياً.
            </p>
            <p className="text-xs text-green-600 dark:text-green-300 mt-1">
              لا يمكن إضافة المزيد من البنود.
            </p>
          </div>
        )}

        {/* New Items List */}
        {getNewItems().length > 0 && (
          <section className="space-y-3 pb-20">
            <div className="flex items-center justify-between px-1">
              <h5 className="text-xs font-bold uppercase tracking-wider text-green-600 dark:text-green-400">
                بنود جاهزة للإرسال ({getNewItems().length})
              </h5>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {getNewItems().map((item, idx) => (
                <div
                  key={item.id}
                  className="relative group p-4 bg-[var(--color-surface)] rounded-xl border border-green-200 dark:border-green-900 shadow-sm hover:shadow-md transition-all"
                >
                  <div className="flex gap-4 items-start">
                    <div className="w-8 h-8 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-xs font-bold shrink-0">
                      {getExistingItems().length + idx + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <a
                        href={item.productLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-bold text-[var(--color-text)] hover:text-blue-600 truncate block"
                      >
                        {item.productLink}
                      </a>
                      <div className="flex flex-wrap items-center gap-3 mt-1.5">
                        <span className="text-xs font-medium text-[var(--color-text-muted)] bg-[var(--color-surface-3)] px-2 py-0.5 rounded">
                          {item.productPrice} $
                        </span>
                        {item.notes && (
                          <span className="text-xs text-[var(--color-text-muted)] truncate max-w-[200px]">
                            📝 {item.notes}
                          </span>
                        )}
                        {item.attachmentName && (
                          <span className="text-xs text-blue-500">
                            📎 {item.attachmentName}
                          </span>
                        )}
                        {item.images && item.images.length > 0 && (
                          <span className="text-xs text-green-500">
                            🖼️ {item.images.length} صورة
                          </span>
                        )}
                      </div>

                      {/* عرض معاينات الصور */}
                      {item.images && item.images.length > 0 && (
                        <div className="grid grid-cols-3 gap-2 mt-3">
                          {item.images.map((imageUrl, imgIndex) => (
                            <img
                              key={imgIndex}
                              src={imageUrl}
                              alt={`صورة المنتج ${imgIndex + 1}`}
                              className="w-full h-16 object-cover rounded-lg border border-[var(--color-border)]"
                            />
                          ))}
                        </div>
                      )}
                    </div>

                    <button
                      onClick={() => handleRemoveItem(item.id)}
                      className="w-8 h-8 flex items-center justify-center rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                      title="حذف"
                    >
                      <DeleteIcon className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Footer Actions */}
      <div className="p-4 md:p-6 bg-white/90 dark:bg-gray-800/90 backdrop-blur-md border-t border-[var(--color-border)] flex flex-col-reverse md:flex-row gap-3 z-20">
        <button
          type="button"
          onClick={handleCancel}
          className="md:w-1/3 w-full py-3.5 rounded-xl font-bold text-[var(--color-text)] bg-[var(--color-surface-3)] hover:bg-[var(--color-surface-3)] transition-colors"
        >
          إلغاء
        </button>
        <button
          onClick={handleSubmit}
          disabled={
            getNewItems().length === 0 &&
            (!initialData || getExistingItems().length === 0)
          }
          className={`md:w-2/3 w-full py-3.5 rounded-xl font-bold text-white shadow-lg transition-all transform active:scale-[0.98] ${
            getNewItems().length === 0 &&
            (!initialData || getExistingItems().length === 0)
              ? "bg-gray-300 dark:bg-gray-700 text-[var(--color-text-muted)] cursor-not-allowed shadow-none"
              : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-blue-500/30"
          }`}
        >
          {isEditMode
            ? `إضافة وإرسال (${getNewItems().length})`
            : `إرسال التسليم (${items.length})`}
        </button>
      </div>

      {/* Confirm Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-in overflow-y-auto">
          <div className="bg-[var(--color-surface)] rounded-2xl p-6 w-full max-w-sm shadow-2xl border border-[var(--color-border)] transform transition-all scale-100 mt-16 sm:mt-0 mb-4 sm:mb-0">
            <div className="w-12 h-12 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center mb-4 mx-auto text-2xl">
              📢
            </div>
            <h3 className="text-lg font-bold text-center text-[var(--color-text)] mb-2">
              تأكيد التسليم
            </h3>
            <p className="text-[var(--color-text-muted)] text-center text-sm mb-6 leading-relaxed">
              لن تتمكن من تعديل هذه البنود بعد الإرسال، ولكن يمكنك إضافة بنود
              جديدة لاحقاً إذا لزم الأمر.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirmDialog(false)}
                className="flex-1 py-2.5 rounded-xl font-bold text-[var(--color-text)] bg-[var(--color-surface-3)] hover:bg-[var(--color-surface-3)] transition"
              >
                تراجع
              </button>
              <button
                onClick={confirmSubmit}
                className="flex-1 py-2.5 rounded-xl font-bold text-white bg-blue-600 hover:bg-blue-700 transition"
              >
                تأكيد
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SubmissionForm;
