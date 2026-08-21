/**
 * BarcodeScannerModal — قراءة باركود بكاميرا الجهاز من داخل المتصفح (بلا تطبيق).
 *
 * مساران للفكّ، الأسرع أولاً:
 * 1. `BarcodeDetector` الأصلي (كروم/أندرويد وأغلب متصفحات Chromium) — عتادي وسريع.
 * 2. ZXing عبر `@zxing/browser` (استيراد ديناميكي كي لا يُحمَّل إلا عند فتح
 *    الماسح) — يغطي سفاري/آيفون وكل ما لا يدعم الواجهة الأصلية.
 *
 * يقرأ باركود 1D (Code 128/39، EAN، UPC، ITF) وQR — أنواع ملصقات السيريال
 * وIMEI على علب الأجهزة.
 *
 * قيد المنصة الذي لا حيلة لنا فيه: `getUserMedia` لا يعمل إلا في سياق آمن
 * (HTTPS أو localhost). على `http://` عبر الشبكة المحلية نعرض رسالة تشرح ذلك
 * بدل فشل صامت.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Loader2, X } from "lucide-react";

/** واجهة BarcodeDetector غير موجودة في أنواع TS القياسية بعد — تصريح أدنى. */
type NativeBarcode = { rawValue: string };
type NativeDetector = { detect: (source: CanvasImageSource) => Promise<NativeBarcode[]> };
type NativeDetectorCtor = new (options?: { formats?: string[] }) => NativeDetector;
type ZXingControls = { stop: () => void };

const NATIVE_FORMATS = [
  "code_128", "code_39", "code_93", "codabar", "ean_13", "ean_8",
  "itf", "upc_a", "upc_e", "qr_code", "data_matrix",
];

/** نغمة تأكيد قصيرة عند الالتقاط — الموظف يعرف أن القراءة تمّت دون النظر للشاشة. */
const beep = () => {
  try {
    const Ctx = window.AudioContext
      || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 1400;
    gain.gain.value = 0.08;
    osc.start();
    osc.stop(ctx.currentTime + 0.12);
    osc.onended = () => void ctx.close();
  } catch {
    /* الصوت تحسين لا شرط */
  }
};

const friendlyCameraError = (cause: unknown): string => {
  if (!window.isSecureContext) {
    return "المتصفح يمنع فتح الكاميرا على اتصال غير آمن — افتح النظام عبر HTTPS (أو localhost) لتعمل الكاميرا.";
  }
  const name = cause instanceof DOMException ? cause.name : "";
  if (name === "NotAllowedError") {
    return "رُفض إذن الكاميرا — اسمح للموقع باستخدام الكاميرا من إعدادات المتصفح ثم أعد المحاولة.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "لا توجد كاميرا متاحة على هذا الجهاز.";
  }
  if (name === "NotReadableError") {
    return "الكاميرا مشغولة بتطبيق آخر — أغلقه ثم أعد المحاولة.";
  }
  return cause instanceof Error && cause.message
    ? `تعذّر فتح الكاميرا: ${cause.message}`
    : "تعذّر فتح الكاميرا.";
};

/** مهلة تبريد بين قراءتين في الوضع المتتالي — بدونها يُقرأ الملصق نفسه عشرات
 *  المرات في الثانية الواحدة (الفكّ يعمل على كل إطار). */
const CONTINUOUS_COOLDOWN_MS = 1200;

export const BarcodeScannerModal: React.FC<{
  title?: string;
  hint?: string;
  /** يبقى الماسح مفتوحاً بعد كل قراءة — لمسح عدّة وحدات في دفعة واحدة. */
  continuous?: boolean;
  onDetect: (value: string) => void;
  onClose: () => void;
}> = ({ title = "مسح الباركود بالكاميرا", hint, continuous = false, onDetect, onClose }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(true);
  /** آخر قيمة مقروءة — تأكيد بصري في الوضع المتتالي حيث لا يُغلق الماسح. */
  const [lastHit, setLastHit] = useState<string | null>(null);
  // الالتقاط يحدث مرة واحدة — الفكّ المستمر قد يطلق النتيجة عدة مرات في إطار واحد.
  const doneRef = useRef(false);
  const cooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (cooldownRef.current) clearTimeout(cooldownRef.current);
  }, []);

  /** المستدعي يمرّر دوالَّ سهميةً مضمّنةً غالباً، فتتغيّر مع كل رسم. لو دخلت
   *  اعتماديات `handleHit` لأعادت أثرَ الكاميرا الإقلاع مع كل رسم — أي إغلاق
   *  المجرى وفتحه من جديد بينما الموظف يصوّب على ملصق. المرجع يبقيها طازجةً
   *  بلا أن تلمس دورة حياة المجرى. */
  const onDetectRef = useRef(onDetect);
  const onCloseRef = useRef(onClose);
  useEffect(() => { onDetectRef.current = onDetect; onCloseRef.current = onClose; });

  const handleHit = useCallback((raw: string) => {
    const value = (raw || "").trim();
    if (!value || doneRef.current) return;
    doneRef.current = true;
    beep();
    navigator.vibrate?.(80);
    onDetectRef.current(value);
    if (!continuous) {
      onCloseRef.current();
      return;
    }
    // الوحدات المُرقَّمة تُمسح واحدةً تلو الأخرى من نفس الصندوق؛ إغلاق الماسح
    // بعد كل ملصق يجعل مسح عشر وحدات عشر فتحاتٍ للكاميرا.
    setLastHit(value);
    cooldownRef.current = setTimeout(() => { doneRef.current = false; }, CONTINUOUS_COOLDOWN_MS);
  }, [continuous]);

  useEffect(() => {
    let cancelled = false;
    let stream: MediaStream | null = null;
    let rafId = 0;
    let zxingControls: ZXingControls | null = null;

    const stopAll = () => {
      if (rafId) cancelAnimationFrame(rafId);
      zxingControls?.stop();
      stream?.getTracks().forEach((t) => t.stop());
    };

    const start = async () => {
      const video = videoRef.current;
      if (!video) return;
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error(
            window.isSecureContext
              ? "هذا المتصفح لا يدعم فتح الكاميرا."
              : "insecure",
          );
        }

        const DetectorCtor = (window as unknown as { BarcodeDetector?: NativeDetectorCtor })
          .BarcodeDetector;

        if (DetectorCtor) {
          // المسار الأصلي: نملك البثّ ونفحص إطاراً بإطار.
          stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" },
            audio: false,
          });
          if (cancelled) return stopAll();
          video.srcObject = stream;
          await video.play();
          setStarting(false);
          let detector: NativeDetector;
          try {
            detector = new DetectorCtor({ formats: NATIVE_FORMATS });
          } catch {
            detector = new DetectorCtor();
          }
          const tick = async () => {
            if (cancelled || doneRef.current) return;
            if (video.readyState >= 2) {
              try {
                const codes = await detector.detect(video);
                if (codes.length > 0) return handleHit(codes[0].rawValue);
              } catch {
                /* إطار ساقط — نكمل */
              }
            }
            rafId = requestAnimationFrame(() => void tick());
          };
          rafId = requestAnimationFrame(() => void tick());
        } else {
          // مسار ZXing (سفاري/آيفون): المكتبة تدير البثّ والفكّ المستمر معاً.
          const { BrowserMultiFormatReader } = await import("@zxing/browser");
          if (cancelled) return;
          const reader = new BrowserMultiFormatReader();
          zxingControls = await reader.decodeFromConstraints(
            { video: { facingMode: "environment" }, audio: false },
            video,
            (result) => {
              if (result) handleHit(result.getText());
            },
          );
          if (cancelled) return stopAll();
          setStarting(false);
        }
      } catch (cause) {
        if (!cancelled) {
          setStarting(false);
          setErr(friendlyCameraError(cause));
        }
        stopAll();
      }
    };

    void start();
    return () => {
      cancelled = true;
      stopAll();
    };
  }, [handleHit]);

  return (
    <div
      dir="rtl"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-3"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
          <div className="flex min-w-0 items-center gap-2">
            <Camera className="h-5 w-5 shrink-0 text-[var(--color-primary)]" />
            <span className="truncate font-bold text-[var(--color-text)]">{title}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            title="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-3">
          {err ? (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          ) : (
            <div className="relative overflow-hidden rounded-xl bg-black">
              {/* playsInline إلزامي لسفاري iOS — بدونه يقفز الفيديو لملء الشاشة */}
              <video
                ref={videoRef}
                className="aspect-[4/3] w-full object-cover"
                muted
                playsInline
              />
              {starting && (
                <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-white">
                  <Loader2 className="h-5 w-5 animate-spin" /> جارٍ فتح الكاميرا…
                </div>
              )}
              {/* إطار تصويب يوجّه الموظف لموضع الباركود */}
              <div className="pointer-events-none absolute inset-x-8 top-1/2 h-20 -translate-y-1/2 rounded-lg border-2 border-emerald-400/90" />
            </div>
          )}
          {continuous && lastHit && (
            <div className="mt-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-center text-xs font-bold text-emerald-700 dark:text-emerald-300">
              <span dir="ltr" className="font-mono">{lastHit}</span> — تمّت القراءة
            </div>
          )}
          <p className="mt-2 text-center text-[11px] text-[var(--color-text-muted)]">
            {hint || "وجّه الكاميرا نحو الباركود — تُقرأ القيمة وتُعبَّأ تلقائياً"}
          </p>
        </div>
      </div>
    </div>
  );
};

export default BarcodeScannerModal;
