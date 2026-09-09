import React, { useState } from "react";
import { Loader2, Plus, Trash2, Upload, X } from "lucide-react";
import {
  submitTask,
  type TaskDto,
  type TaskSubmissionDto,
  type TaskSubmissionItemDto,
  type TaskSubmissionAttachmentDto,
} from "../../services/employeeOpsApi";
import { cloudinaryService } from "../../services/cloudinaryService";
import { useToast } from "../../contexts/ToastContext";

interface TaskSubmitModalProps {
  task: TaskDto;
  isOpen: boolean;
  onClose: () => void;
  onSubmitted: (submission: TaskSubmissionDto) => void;
}

export const TaskSubmitModal: React.FC<TaskSubmitModalProps> = ({
  task,
  isOpen,
  onClose,
  onSubmitted,
}) => {
  const toast = useToast();
  const [body, setBody] = useState("");
  const [items, setItems] = useState<Array<{ product_link: string; product_price: string; notes: string }>>([]);
  const [attachments, setAttachments] = useState<Array<{ url: string; name: string }>>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleAddItem = () => {
    if (items.length >= 50) {
      toast("الحد الأقصى لبنود التسليم هو 50 بنداً", "error");
      return;
    }
    setItems([...items, { product_link: "", product_price: "", notes: "" }]);
  };

  const handleRemoveItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index));
  };

  const handleItemChange = (index: number, field: "product_link" | "product_price" | "notes", val: string) => {
    const next = [...items];
    next[index] = { ...next[index], [field]: val };
    setItems(next);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    if (attachments.length + files.length > 5) {
      toast("الحد الأقصى للمرفقات هو 5 مرفقات فقط", "error");
      return;
    }

    setUploading(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const url = await cloudinaryService.uploadFile(file);
        setAttachments((prev) => [...prev, { url, name: file.name }]);
      }
      toast("تم رفع الملف بنجاح", "success");
    } catch (err: any) {
      toast(err?.message || "فشل رفع الملف", "error");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleRemoveAttachment = (index: number) => {
    setAttachments(attachments.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!body.trim() && items.length === 0 && attachments.length === 0) {
      toast("يرجى كتابة نص التسليم أو إرفاق ملف أو إضافة بند على الأقل", "error");
      return;
    }

    setSubmitting(true);
    try {
      const payloadItems: TaskSubmissionItemDto[] = items
        .filter((it) => it.product_link.trim() || it.notes.trim() || it.product_price)
        .map((it, idx) => ({
          product_link: it.product_link.trim(),
          product_price: it.product_price ? Number(it.product_price) : null,
          notes: it.notes.trim(),
          position: idx,
        }));

      const payloadAttachments: TaskSubmissionAttachmentDto[] = attachments.map((att, idx) => ({
        url: att.url,
        name: att.name,
        position: idx,
      }));

      const submission = await submitTask(task.id, {
        body: body.trim(),
        items: payloadItems,
        attachments: payloadAttachments,
      });

      toast("تم تسليم المهمة بنجاح بانتظار مراجعة المدير", "success");
      onSubmitted(submission);
      onClose();
    } catch (err: any) {
      toast(err?.message || "فشل تسليم المهمة", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 overflow-y-auto">
      <div className="relative w-full max-w-2xl rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-4">
          <div>
            <h2 className="text-lg font-bold text-[var(--color-text)]">تسليم المهمة</h2>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{task.title}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] rounded-lg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto space-y-4 pr-1">
          <div>
            <label className="mb-1 block text-xs font-semibold text-[var(--color-text)]">
              بيان التسليم والملاحظات
            </label>
            <textarea
              rows={4}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="اكتب هنا ما تم إنجازه في المهمة وأي ملاحظات تود إيصالها للمدير..."
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-sm text-[var(--color-text)] outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            />
          </div>

          {/* بنود البحث عن منتجات (اختياري) */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-[var(--color-text)]">
                بنود البحث عن منتجات (اختياري)
              </span>
              <button
                type="button"
                onClick={handleAddItem}
                className="flex items-center gap-1 text-xs text-[var(--color-primary)] font-medium hover:underline"
              >
                <Plus className="h-3.5 w-3.5" /> إضافة بند
              </button>
            </div>

            {items.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)] py-1">
                إذا كانت المهمة تتطلب البحث عن روابط أو أسعار منتجات، يمكنك إضافتها هنا.
              </p>
            ) : (
              <div className="space-y-3">
                {items.map((it, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-[var(--color-text-muted)]">
                        بند #{idx + 1}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRemoveItem(idx)}
                        className="text-red-500 hover:text-red-700 p-1"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <input
                        type="url"
                        value={it.product_link}
                        onChange={(e) => handleItemChange(idx, "product_link", e.target.value)}
                        placeholder="رابط المنتج (https://...)"
                        className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)]"
                      />
                      <input
                        type="number"
                        step="0.01"
                        value={it.product_price}
                        onChange={(e) => handleItemChange(idx, "product_price", e.target.value)}
                        placeholder="السعر المعثور عليه"
                        className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)]"
                      />
                    </div>
                    <input
                      type="text"
                      value={it.notes}
                      onChange={(e) => handleItemChange(idx, "notes", e.target.value)}
                      placeholder="ملاحظات حول البند"
                      className="h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-xs text-[var(--color-text)]"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* المرفقات (حتى 5) */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-[var(--color-text)]">
                المرفقات (حتى 5 ملفات أو صور)
              </span>
              {attachments.length < 5 && (
                <label className="flex items-center gap-1 text-xs text-[var(--color-primary)] font-medium cursor-pointer hover:underline">
                  <Upload className="h-3.5 w-3.5" /> رفع ملف
                  <input
                    type="file"
                    multiple
                    disabled={uploading}
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </label>
              )}
            </div>

            {uploading && (
              <div className="flex items-center gap-2 text-xs text-[var(--color-primary)] py-1">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> جاري رفع الملف...
              </div>
            )}

            {attachments.length === 0 ? (
              <p className="text-xs text-[var(--color-text-muted)] py-1">لا توجد مرفقات مضافة بعد.</p>
            ) : (
              <div className="space-y-1.5">
                {attachments.map((att, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs"
                  >
                    <a
                      href={att.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[var(--color-primary)] hover:underline truncate max-w-sm"
                    >
                      {att.name || att.url}
                    </a>
                    <button
                      type="button"
                      onClick={() => handleRemoveAttachment(idx)}
                      className="text-red-500 hover:text-red-700 p-1"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[var(--color-border)]">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-2)]"
            >
              إلغاء
            </button>
            <button
              type="submit"
              disabled={submitting || uploading}
              className="flex items-center gap-1.5 rounded-lg bg-[var(--color-primary)] px-5 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50"
            >
              {submitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              إرسال التسليم
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
