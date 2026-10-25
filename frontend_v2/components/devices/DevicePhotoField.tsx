import React, { useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { uploadDevicePhoto } from "../../services/devicesApi";
import { useToast } from "../../contexts/ToastContext";
import { FileDropZone } from "../ui/FileDropZone";

/**
 * TKT-DEV-1 — كتلة صورة الجهاز، مستخرجةٌ من نموذج الاستقبال ليستعملها نموذج
 * التعديل نفسه: التقاطٌ مباشر من كاميرا الجهاز المحمول (`capture="environment"`)،
 * أو سحب، أو لصق (Ctrl+V) — والرفع يبدأ من هنا.
 *
 * `uploadDevicePhoto` يرفع الثنائيات إلى `/api/media/upload/` **فور الاختيار**؛
 * المؤجَّل هو كتابة الرابط في السجل: يذهب إلى المسودّة وحدها، ولا يُرسَل إلا مع
 * `PATCH` عند الحفظ. وردُّ رفعٍ يصل بعد تفكيك الكتلة (إلغاء التعديل أو إغلاق
 * النافذة) يُهمل بـ`aliveRef` — و`requestId` حارسٌ ثانٍ لا يتغيّر عملياً لأن
 * `FileDropZone` يردّ ملفاً ثانياً ما دام الرفع جارياً.
 */

const labelClass = "mb-1 block text-[11px] text-[var(--color-text-muted)]";

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

interface Props {
  /** الرابط المعروض — من المسودّة دائماً، لا من السجل المحفوظ. */
  photoUrl: string;
  onChange: (url: string) => void;
  /** بدء الرفع وانتهاؤه — «تسجيل»/«حفظ» يُعطَّل خلاله. */
  onBusyChange?: (busy: boolean) => void;
  disabled?: boolean;
  /** ذيل رسالة فشل الرفع: «… — يمكن التسجيل بلا صورة». */
  failureHint?: string;
  className?: string;
}

// الوسيط مُعنوَن صراحةً: لا `@types/react` كاملة هنا، فـ`React.FC<Props>` هو ما
// يجعل خصائص المكوّن مُتحقَّقة (النمط نفسه في `FileDropZone`).
export const DevicePhotoField: React.FC<Props> = ({
  photoUrl,
  onChange,
  onBusyChange,
  disabled = false,
  failureHint = "يمكن الحفظ بلا صورة",
  className = "",
}) => {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const requestRef = useRef(0);
  const aliveRef = useRef(true);
  // رفعٌ لم يصل ردُّه بعد — يُطفأ عند التفكيك كي لا تعلق إشارته في الأب.
  const pendingRef = useRef(false);
  // آخر `onBusyChange` وصل، يقرأه تنظيفُ التفكيك لا نسخةَ أول رسم.
  const onBusyChangeRef = useRef(onBusyChange);

  useEffect(() => { onBusyChangeRef.current = onBusyChange; });

  // الكتلة تُفكَّك حين يخرج النموذج من وضع التعديل أو تُغلق النافذة — فما يصل
  // بعدها من ردٍّ لا صاحب له (`aliveRef`). ورفعٌ قائمٌ وقتها تصل `finally`ـه
  // والكتلة مفكّكة فلا تُطفئ إشارتَه، فتُطفأ هنا وإلا بقي «حفظ» معطّلاً بلا مؤشّر.
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      if (pendingRef.current) {
        pendingRef.current = false;
        onBusyChangeRef.current?.(false);
      }
    };
  }, []);

  const pickPhoto = async (file: File | null) => {
    if (!file) return;
    const requestId = ++requestRef.current;
    pendingRef.current = true;
    setBusy(true);
    onBusyChange?.(true);
    try {
      const url = await uploadDevicePhoto(file);
      if (!aliveRef.current || requestRef.current !== requestId) return;
      onChange(url);
    } catch (e) {
      if (!aliveRef.current || requestRef.current !== requestId) return;
      // فشل الرفع لا يمحو الصورة القائمة ولا يمنع الحفظ — السجل هو المطلوب.
      toast(`${messageOf(e, "تعذّر رفع الصورة")} — ${failureHint}`, "error");
    } finally {
      const settled = aliveRef.current && requestRef.current === requestId;
      // الراية تُصفَّر لصاحبها وحده: ردُّ طلبٍ قديم لا يمحو رايةَ طلبٍ أحدث.
      if (requestRef.current === requestId) pendingRef.current = false;
      if (settled) {
        setBusy(false);
        onBusyChange?.(false);
      }
    }
  };

  return (
    <div className={className}>
      <span className={labelClass}>صورة الجهاز</span>
      {photoUrl ? (
        <>
          <div className="flex h-36 w-full items-center justify-center overflow-hidden rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-2)]">
            <img src={photoUrl} alt="صورة الجهاز" className="h-full w-full object-cover" />
          </div>
          <div className="mt-1 flex items-center gap-2">
            <FileDropZone
              onFiles={(files) => { void pickPhoto(files[0]); }}
              accept="image"
              capture="environment"
              variant="compact"
              busy={busy}
              disabled={disabled}
              hint="تغيير الصورة"
              className="flex-1"
            />
            <button
              type="button"
              className="rounded-lg p-1.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
              title="إزالة الصورة"
              onClick={() => onChange("")}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </>
      ) : (
        <FileDropZone
          onFiles={(files) => { void pickPhoto(files[0]); }}
          accept="image"
          capture="environment"
          variant="compact"
          busy={busy}
          disabled={disabled}
          hint="صورة الجهاز — اضغط أو التقطها"
          subHint="أو اسحب الصورة إلى هنا، أو الصق (Ctrl+V)"
          className="h-36 w-full"
        />
      )}
    </div>
  );
};

export default DevicePhotoField;
