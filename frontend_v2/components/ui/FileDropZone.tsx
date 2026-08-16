/**
 * منطقة رفع موحّدة: اختيار بالضغط + سحب وإفلات + لصق من الحافظة (Ctrl+V) —
 * الطريق الوحيد لإرفاق صورة في التطبيق. المنطقة **لا ترفع شيئاً**: مخرجها الوحيد
 * `onFiles`، فيبقى قرار الرفع (فوري إلى cloudinary، أو مؤجّل في الحالة) عند الشاشة.
 * اللصق يمرّ بسجلّ المناطق في `utils/clipboardImage.ts` فلا تفوز بلصقة إلا منطقة واحدة.
 */
import React, { useCallback, useId, useRef, useState } from 'react';
import { Loader2, Trash2, UploadCloud } from 'lucide-react';
import { useToast } from '../../contexts/ToastContext';
import { usePasteZone } from '../../utils/clipboardImage';
import { formatBytes } from '../../utils/formatBytes';

export type FileDropAccept = 'image' | 'pdf' | 'image-pdf';

interface FileDropZoneProps {
  /** المخرج الوحيد: الملفات المقبولة بعد فحص النوع والحجم. */
  onFiles: (files: File[]) => void;
  accept?: FileDropAccept;
  multiple?: boolean;
  /** جارٍ الرفع: مؤشّر دوّار، والملفات الجديدة مرفوضة برسالة بدل أن تُبتلع صامتة. */
  busy?: boolean;
  disabled?: boolean;
  variant?: 'zone' | 'compact';
  /** كاميرا الهاتف مباشرة (`environment`) — يُمرَّر كما هو إلى `input`. */
  capture?: boolean | 'user' | 'environment';
  /** الحدّ الأقصى للملف. الافتراضي 25 = سقف الخادم الحقيقي؛ للشاشة أن تشدّده. */
  maxSizeMB?: number;
  hint?: string;
  /** سطر صغير تحت العبارة الرئيسية (الصيغ المدعومة، الحدّ الأقصى…). */
  subHint?: string;
  /** لصفوف متكرّرة: لا تستقبل لصقاً إلا بعد نقر/سحب داخلها. */
  interactionRequired?: boolean;
  /** معاينة روابط مرفوعة داخل المنطقة — تُترك فارغة إن كانت الشاشة تعرض معاينتها بنفسها. */
  previewUrls?: string[];
  onRemove?: (index: number) => void;
  className?: string;
}

const DEFAULT_HINT = 'اضغط للاختيار، اسحب الملف إلى هنا، أو الصق (Ctrl+V)';

const ACCEPT_ATTR: Record<FileDropAccept, string> = {
  image: 'image/*',
  pdf: 'application/pdf',
  'image-pdf': 'image/*,application/pdf',
};

const ACCEPT_LABEL: Record<FileDropAccept, string> = {
  image: 'الصور فقط',
  // منطقة PDF تجاور دائماً منطقة صور (§4.2)، فالرسالة تدلّ على البديل بدل أن ترفض فقط.
  pdf: 'ملفات PDF فقط — الصور تُرفَع في منطقة الصور',
  'image-pdf': 'الصور وملفات PDF فقط',
};

function matchesAccept(file: File, accept: FileDropAccept): boolean {
  const isImage = file.type.startsWith('image/');
  const isPdf = file.type === 'application/pdf';
  if (accept === 'image') return isImage;
  if (accept === 'pdf') return isPdf;
  return isImage || isPdf;
}

// الوسيط مُعنوَن صراحةً بـ`FileDropZoneProps`: لا يوجد `@types/react` في هذا
// المستودع، فـ`React.FC<...>` يؤول إلى `any` ويضيع تحقّق الأنواع داخل المكوّن.
export const FileDropZone: React.FC<FileDropZoneProps> = ({
  onFiles,
  accept = 'image',
  multiple = false,
  busy = false,
  disabled = false,
  variant = 'zone',
  capture,
  maxSizeMB = 25,
  hint = DEFAULT_HINT,
  subHint,
  interactionRequired = false,
  previewUrls,
  onRemove,
  className = '',
}: FileDropZoneProps) => {
  const toast = useToast();
  const rootRef = useRef<HTMLDivElement>(null);
  const inputId = useId();
  const [dragging, setDragging] = useState(false);

  const handleIncoming = useCallback(
    (incoming: File[]) => {
      if (disabled || incoming.length === 0) return;
      if (busy) {
        toast('جارٍ الرفع الآن — انتظر انتهاءه ثم أعد المحاولة.', 'info');
        return;
      }

      const limitBytes = maxSizeMB * 1024 * 1024;
      const accepted: File[] = [];
      for (const file of incoming) {
        if (!matchesAccept(file, accept)) {
          toast(`«${file.name}» غير مقبول هنا — ${ACCEPT_LABEL[accept]}.`, 'error');
          continue;
        }
        if (file.size > limitBytes) {
          toast(`«${file.name}» حجمه ${formatBytes(file.size)} ويتجاوز الحدّ المسموح (${maxSizeMB} م.ب).`, 'error');
          continue;
        }
        accepted.push(file);
      }
      if (accepted.length === 0) return;

      if (!multiple && accepted.length > 1) {
        toast('هذا الحقل يقبل ملفاً واحداً — أُخذ الأول.', 'info');
      }
      onFiles(multiple ? accepted : accepted.slice(0, 1));
    },
    [accept, busy, disabled, maxSizeMB, multiple, onFiles, toast],
  );

  usePasteZone(rootRef, handleIncoming, { enabled: !disabled, interactionRequired });

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
    if (disabled) return;
    handleIncoming(Array.from(e.dataTransfer.files));
  }, [disabled, handleIncoming]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    handleIncoming(Array.from(e.target.files ?? []));
    e.target.value = '';
  }, [handleIncoming]);

  const compact = variant === 'compact';
  const stateClasses = disabled
    ? 'border-[var(--color-border)] bg-[var(--color-muted)] opacity-60 cursor-not-allowed'
    : dragging
      ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10'
      : 'border-[var(--color-border)] bg-[var(--color-surface-2)] hover:border-[var(--color-primary)]';

  return (
    <div ref={rootRef} className={className}>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        // `h-full` بلا أثر حين لا يُحدَّد للجذر ارتفاع (الحالة العامة)، ويملأ
        // المربّع حين تعطيه الشاشة ارتفاعاً عبر `className` (خانات صور الصنف).
        className={`relative h-full border-2 border-dashed rounded-xl text-center transition-colors ${compact ? 'p-3' : 'p-8'} ${stateClasses}`}
      >
        <input
          id={inputId}
          type="file"
          accept={ACCEPT_ATTR[accept]}
          multiple={multiple}
          capture={capture}
          disabled={disabled || busy}
          onChange={handleChange}
          className="hidden"
        />
        <label
          htmlFor={inputId}
          className={`flex h-full flex-col items-center justify-center gap-2 ${disabled || busy ? 'cursor-not-allowed' : 'cursor-pointer'}`}
        >
          {busy ? (
            <Loader2 className={`${compact ? 'w-5 h-5' : 'w-8 h-8'} animate-spin text-[var(--color-primary)]`} />
          ) : (
            <UploadCloud className={`${compact ? 'w-5 h-5' : 'w-8 h-8'} text-[var(--color-text-muted)]`} />
          )}
          <span className={`${compact ? 'text-xs' : 'text-sm'} font-medium text-[var(--color-text)]`}>
            {busy ? 'جارٍ الرفع…' : dragging ? 'أفلت الملفات هنا' : hint}
          </span>
          {subHint && !busy && (
            <span className="text-xs text-[var(--color-text-muted)]">{subHint}</span>
          )}
        </label>
      </div>

      {previewUrls && previewUrls.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {previewUrls.map((url, index) => (
            <div key={`${url}-${index}`} className="relative w-20 h-20 rounded-lg overflow-hidden border border-[var(--color-border)]">
              <img src={url} alt={`مرفق ${index + 1}`} className="w-full h-full object-cover" />
              {onRemove && !disabled && (
                <button
                  type="button"
                  onClick={() => onRemove(index)}
                  title="إزالة"
                  className="absolute top-1 start-1 p-1 rounded-md bg-black/60 text-white hover:bg-[var(--color-danger)] transition-colors"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default FileDropZone;
