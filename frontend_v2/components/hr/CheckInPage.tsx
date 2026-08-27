import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Fingerprint, LogIn, LogOut, MapPin, Loader2, AlertTriangle, Camera, X,
  CalendarDays, Clock, Check,
} from "lucide-react";
import {
  essPunch, fetchEssMe, fetchEssMonth, fetchEssSchedule,
  type EssMe, type EssMonth, type EssScheduleRow, type EssToday,
  WEEKDAY_LABELS,
} from "../../services/hrAttendanceApi";
import {
  currentMonth, formatCounter, formatMinutes, formatShiftPeriods, rejectMessage,
  sessionSeconds, statusPillClass,
} from "../../utils/attendance";
import { formatNumber } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { cloudinaryService } from "../../services/cloudinaryService";
import { useToast } from "../../contexts/ToastContext";

/**
 * T-HR M3 — «تسجيل حضوري»: زرٌّ واحد كبير وعدّادٌ حيّ وملخّصُ شهر.
 *
 * **كل قرارٍ خادميّ.** الشاشة تطلب الموقع من المتصفّح وترسله؛ القبولُ والرفض
 * وسببُهما يأتيان من `hr/attendance.py` — ولا فحصَ مسافةٍ هنا يسبق الخادم أو
 * يناقضه، وإلا صار للقاعدة موضعان ينزاحان.
 *
 * **والعدّاد يَعُدّ من لحظةٍ يرسلها الخادم** لا من ساعة الجهاز: ساعةٌ متأخّرة
 * دقائقَ كانت تُظهر رقماً كاذباً وأحياناً سالباً (`utils/attendance.ts`).
 *
 * والحالة التي لا مخرجَ منها ممنوعة: رفضُ الموقع يترك الزرّ حيّاً مع رسالةٍ
 * تقول ماذا يفعل، ومنعُ إذن المتصفّح يشرح كيف يُعاد.
 */

const cardClass =
  "rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4";
const btnGhost =
  "inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-3 h-9 " +
  "text-sm text-[var(--color-text)] disabled:opacity-50";

const GEO_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  timeout: 15_000,
  maximumAge: 30_000,
};

type GeoState =
  | { kind: "idle" }
  | { kind: "asking" }
  | { kind: "ready"; lat: number; lng: number; accuracy: number }
  | { kind: "denied"; message: string };

/** يلفّ `navigator.geolocation` في وعدٍ — بلا رمي، فالرفض حالةٌ لا عطل. */
const readPosition = (): Promise<GeoState> =>
  new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      resolve({ kind: "denied", message: "متصفّحك لا يدعم تحديد الموقع." });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        kind: "ready",
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        accuracy: Math.round(position.coords.accuracy || 0),
      }),
      (error) => {
        // 1 = رفض الإذن · 2 = تعذّر تحديد الموقع · 3 = انتهت المهلة
        const message =
          error.code === 1
            ? "أذِن للموقع من إعدادات المتصفّح (أيقونة القفل بجانب العنوان) ثم أعد المحاولة."
            : error.code === 3
              ? "تعذّر تحديد موقعك في الوقت المتاح — جرّب مرة أخرى قرب نافذة."
              : "تعذّر تحديد موقعك. تأكد من تشغيل خدمة الموقع.";
        resolve({ kind: "denied", message });
      },
      GEO_OPTIONS,
    );
  });

export const CheckInPage: React.FC = () => {
  const toast = useToast();
  const [me, setMe] = useState<EssMe | null>(null);
  const [today, setToday] = useState<EssToday | null>(null);
  const [month, setMonth] = useState<EssMonth | null>(null);
  const [schedule, setSchedule] = useState<EssScheduleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [geo, setGeo] = useState<GeoState>({ kind: "idle" });
  const [refusal, setRefusal] = useState("");
  const [photoUrl, setPhotoUrl] = useState("");
  const [cameraOpen, setCameraOpen] = useState(false);

  // لحظةُ الجلب المحلية — مرساةُ العدّاد التي تُقاس منها الثواني المحلية.
  const fetchedAtRef = useRef<number>(Date.now());
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  const applyToday = useCallback((next: EssToday) => {
    setToday(next);
    fetchedAtRef.current = Date.now();
    setNowMs(Date.now());
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [identity, monthly, rota] = await Promise.all([
        fetchEssMe(),
        fetchEssMonth(currentMonth()),
        fetchEssSchedule(),
      ]);
      setMe(identity);
      applyToday(identity.today);
      setMonth(monthly);
      setSchedule(rota);
    } catch (cause) {
      setLoadError(humanizeThrown(cause, "تعذّر تحميل بيانات حضورك."));
    } finally {
      setLoading(false);
    }
  }, [applyToday]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const openSession = today?.open_session ?? null;

  // العدّاد يدقّ ثانيةً بثانية، وفقط حين تكون هناك جلسة مفتوحة — مؤقّتٌ يعمل
  // بلا سبب يُعيد رسم الشاشة كل ثانية بلا فائدة.
  useEffect(() => {
    if (!openSession) return undefined;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [openSession]);

  const counterText = useMemo(() => {
    if (!openSession) return "";
    return formatCounter(
      sessionSeconds(openSession.since, openSession.server_now, fetchedAtRef.current, nowMs));
  }, [openSession, nowMs]);

  const requiresPhoto = me?.requires_photo ?? false;
  const requiresGeo = me?.requires_geo ?? false;

  const punch = async (kind: "in" | "out") => {
    if (!me) return;
    setBusy(true);
    setRefusal("");
    try {
      let position: GeoState = geo;
      if (requiresGeo || geo.kind !== "ready") {
        setGeo({ kind: "asking" });
        position = await readPosition();
        setGeo(position);
      }
      if (requiresGeo && position.kind !== "ready") {
        setRefusal(position.kind === "denied" ? position.message : "تعذّر تحديد موقعك.");
        return;
      }
      if (requiresPhoto && !photoUrl) {
        setRefusal("هذا الموقع يشترط صورة عند التسجيل — التقط صورة أولاً.");
        return;
      }

      const payload = position.kind === "ready"
        ? { lat: position.lat, lng: position.lng, accuracy: position.accuracy,
            photo_url: photoUrl || undefined }
        : { photo_url: photoUrl || undefined };
      const result = await essPunch(kind, payload);
      applyToday(result.today);

      if (!result.accepted) {
        const site = me.work_location || me.check_in_sites[0] || null;
        setRefusal(rejectMessage(
          result.reject_reason, result.reject_label,
          result.event.distance_m == null ? null : Number(result.event.distance_m),
          site?.radius_m ?? null));
        return;
      }
      setPhotoUrl("");
      toast(kind === "in" ? "تم تسجيل حضورك." : "تم تسجيل انصرافك.", "success");
      const monthly = await fetchEssMonth(currentMonth());
      setMonth(monthly);
    } catch (cause) {
      setRefusal(humanizeThrown(cause, "تعذّر تسجيل البصمة."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-16"><Loader2 className="animate-spin" /></div>;
  }

  if (loadError || !me) {
    return (
      <div role="alert" className="mx-auto max-w-xl rounded-2xl border border-amber-300 bg-amber-50 p-6 text-center font-bold text-amber-900">
        {loadError || "لا يوجد ملفّ موظف مرتبط بحسابك في هذه الشركة."}
        <div className="mt-3">
          <button type="button" className={btnGhost} onClick={() => void reload()}>
            إعادة المحاولة
          </button>
        </div>
      </div>
    );
  }

  const day = today?.day ?? null;
  const site = me.work_location || me.check_in_sites[0] || null;

  return (
    <div className="mx-auto max-w-2xl space-y-3">
      <header className="flex flex-wrap items-center gap-2">
        <Fingerprint size={20} className="text-[var(--color-primary)]" />
        <h1 className="text-lg font-bold">تسجيل حضوري</h1>
        <span className="ms-auto text-sm text-[var(--color-text-muted)]">
          {me.name}{me.job_title ? ` — ${me.job_title}` : ""}
        </span>
      </header>

      <section className={cardClass}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs text-[var(--color-text-muted)]">
              {formatDateLocalized(today?.date || "")}
            </div>
            {today?.shift ? (
              <div className="mt-0.5 inline-flex items-center gap-1 text-sm">
                <Clock size={13} />
                {today.shift.name} · {formatShiftPeriods(today.shift)}
              </div>
            ) : (
              <div className="mt-0.5 text-sm text-[var(--color-text-muted)]">
                لا وردية مُسنَدة لك اليوم
              </div>
            )}
          </div>
          {day && (
            <span className={statusPillClass(day.status)}>{day.status_label}</span>
          )}
        </div>

        {openSession ? (
          <div className="mt-4 rounded-xl bg-[var(--color-surface-2)] p-4 text-center">
            <div className="text-xs text-[var(--color-text-muted)]">أنت الآن على رأس عملك منذ</div>
            <div
              className="mt-1 font-mono text-2xl font-bold tabular-nums"
              role="timer"
              aria-live="off"
            >
              {counterText}
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-xl bg-[var(--color-surface-2)] p-4 text-center text-sm text-[var(--color-text-muted)]">
            لا يوجد تسجيل دخول مفتوح.
          </div>
        )}

        <button
          type="button"
          disabled={busy}
          onClick={() => void punch(openSession ? "out" : "in")}
          className={`mt-4 flex h-14 w-full items-center justify-center gap-2 rounded-xl text-base font-bold text-white disabled:opacity-60 ${
            openSession ? "bg-rose-600" : "bg-[var(--color-primary)]"
          }`}
        >
          {busy ? <Loader2 size={18} className="animate-spin" />
            : openSession ? <LogOut size={18} /> : <LogIn size={18} />}
          {openSession ? "تسجيل الانصراف" : "تسجيل حضوري"}
        </button>

        {site && (
          <p className="mt-2 flex items-center justify-center gap-1 text-xs text-[var(--color-text-muted)]">
            <MapPin size={12} />
            {site.name}
            {site.require_geo && ` — يجب أن تكون ضمن ${formatNumber(site.radius_m, { maxDecimals: 0 })} م`}
          </p>
        )}

        {geo.kind === "ready" && (
          <p className="mt-1 text-center text-[11px] text-[var(--color-text-muted)]">
            دقّة الموقع ±{formatNumber(geo.accuracy, { maxDecimals: 0 })} م
          </p>
        )}

        {requiresPhoto && (
          <div className="mt-3 flex items-center justify-center gap-2">
            {photoUrl ? (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
                <Check size={13} /> الصورة جاهزة
                <button type="button" className="underline" onClick={() => setPhotoUrl("")}>
                  إزالة
                </button>
              </span>
            ) : (
              <button type="button" className={btnGhost} onClick={() => setCameraOpen(true)}>
                <Camera size={14} /> التقاط صورة
              </button>
            )}
          </div>
        )}

        {refusal && (
          <div
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
          >
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>{refusal}</span>
          </div>
        )}
      </section>

      {month && (
        <section className={cardClass}>
          <h2 className="mb-2 flex items-center gap-1.5 text-sm font-bold">
            <CalendarDays size={15} /> ملخّص الحضور خلال الشهر
          </h2>
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {[
              ["أيام الحضور", formatNumber(month.summary.present_days, { maxDecimals: 0 })],
              ["أيام الغياب", formatNumber(month.summary.absent_days, { maxDecimals: 0 })],
              ["ساعات العمل", formatMinutes(month.summary.worked_minutes)],
              ["ساعات إضافية", formatMinutes(month.summary.overtime_minutes)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-[var(--color-surface-2)] p-2 text-center">
                <div className="text-[11px] text-[var(--color-text-muted)]">{label}</div>
                <div className="font-bold">{value}</div>
              </div>
            ))}
          </div>
          {month.summary.attendance_rate != null && (
            <p className="mt-2 text-center text-xs text-[var(--color-text-muted)]">
              نسبة الحضور {formatNumber(month.summary.attendance_rate, { maxDecimals: 1 })}٪
              من {formatNumber(month.summary.expected_days, { maxDecimals: 0 })} يوم دوام
            </p>
          )}
        </section>
      )}

      {schedule.length > 0 && (
        <section className={cardClass}>
          <h2 className="mb-2 text-sm font-bold">جدول مناوباتي</h2>
          <ul className="space-y-1 text-sm">
            {schedule.slice(0, 5).map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{row.shift_name}</span>
                <span className="text-[var(--color-text-muted)]">{formatShiftPeriods(row)}</span>
                <span className="text-xs text-[var(--color-text-muted)]">
                  من {formatDateLocalized(row.start_date)}
                  {row.end_date ? ` إلى ${formatDateLocalized(row.end_date)}` : ""}
                </span>
                {row.weekly_off_days.length > 0 && (
                  <span className="text-xs text-[var(--color-text-muted)]">
                    عطلة: {row.weekly_off_days.map((d) => WEEKDAY_LABELS[d]).join("، ")}
                  </span>
                )}
                {row.is_current && (
                  <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] text-emerald-800">
                    سارية
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {cameraOpen && (
        <SelfieCapture
          onClose={() => setCameraOpen(false)}
          onCaptured={(url) => { setPhotoUrl(url); setCameraOpen(false); }}
          onError={(message) => { setCameraOpen(false); toast(message, "error"); }}
        />
      )}
    </div>
  );
};

/**
 * التقاط صورة من الكاميرا ورفعها عبر مسار الوسائط القائم.
 *
 * `getUserMedia` **لا يعمل إلا على HTTPS** (أو localhost) — والرسالة تقول ذلك
 * صراحةً بدل أن يبدو الزرّ معطّلاً بلا سبب.
 */
const SelfieCapture: React.FC<{
  onClose: () => void;
  onCaptured: (url: string) => void;
  onError: (message: string) => void;
}> = ({ onClose, onCaptured, onError }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const start = async () => {
      if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
        onError("الكاميرا تحتاج اتصالاً آمناً (HTTPS) — افتح الموقع برابط آمن.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" }, audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      } catch {
        onError("تعذّر فتح الكاميرا — تأكّد من الإذن ومن أن الرابط آمن (HTTPS).");
      }
    };
    void start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [onError]);

  const capture = async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setUploading(true);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d")?.drawImage(video, 0, 0);
      const blob: Blob | null = await new Promise((resolve) =>
        canvas.toBlob((value) => resolve(value), "image/jpeg", 0.8));
      if (!blob) throw new Error("تعذّر التقاط الصورة.");
      const file = new File([blob], "check-in.jpg", { type: "image/jpeg" });
      const url = await cloudinaryService.uploadImage(file);
      onCaptured(url);
    } catch (cause) {
      onError(humanizeThrown(cause, "تعذّر رفع الصورة."));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-3">
      <div className={`${cardClass} w-full max-w-sm`}>
        <div className="mb-2 flex items-center gap-2">
          <h2 className="font-bold">صورة التسجيل</h2>
          <button type="button" className="ms-auto" onClick={onClose} aria-label="إغلاق">
            <X size={16} />
          </button>
        </div>
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full rounded-xl bg-black"
        />
        <button
          type="button"
          disabled={uploading}
          onClick={() => void capture()}
          className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] font-bold text-white disabled:opacity-60"
        >
          {uploading ? <Loader2 size={16} className="animate-spin" /> : <Camera size={16} />}
          التقاط
        </button>
      </div>
    </div>
  );
};

export default CheckInPage;
