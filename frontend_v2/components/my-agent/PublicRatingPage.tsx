import React, { useState, useEffect, useCallback } from "react";
import { useParams } from "react-router-dom";
import { API_BASE } from "../../services/restApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { DailyStarRating } from "./DailyStarRating";
import {
  Star,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Building2,
  User,
  Calendar,
  RefreshCw,
} from "lucide-react";

interface PublicRatingData {
  company_name: string;
  employee_name: string;
  service_date: string;
  stars: number | null;
  note: string;
  already_rated: boolean;
  can_rate: boolean;
  can_edit: boolean;
}

export const PublicRatingPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();

  const [data, setData] = useState<PublicRatingData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [stateError, setStateError] = useState<"not_found" | "expired" | "general" | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");

  // حالة التقييم والملاحظة
  const [currentStars, setCurrentStars] = useState<number>(0);
  const [noteText, setNoteText] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitSuccess, setSubmitSuccess] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchTokenData = useCallback(async () => {
    if (!token) {
      setStateError("not_found");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setStateError(null);
      setErrorMessage("");

      const res = await fetch(`${API_BASE}/my-agent/ratings/public/${encodeURIComponent(token)}/`, {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      });

      if (res.status === 404) {
        setStateError("not_found");
        return;
      }
      if (res.status === 410) {
        setStateError("expired");
        return;
      }
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        setStateError("general");
        setErrorMessage(errJson?.detail || "تعذر جلب بيانات الرابط.");
        return;
      }

      const json: PublicRatingData = await res.json();
      setData(json);
      if (json.stars != null) {
        setCurrentStars(json.stars);
      }
      if (json.note) {
        setNoteText(json.note);
      }
    } catch (err: any) {
      setStateError("general");
      setErrorMessage(err?.message || "تعذر الاتصال بالخادم.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void fetchTokenData();
  }, [fetchTokenData]);

  // إرسال التقييم
  const handleSubmitRating = async (starsToSubmit: number, noteToSubmit: string) => {
    if (!token) return;

    try {
      setIsSubmitting(true);
      setSubmitError(null);
      setSubmitSuccess(false);

      const res = await fetch(`${API_BASE}/my-agent/ratings/public/${encodeURIComponent(token)}/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          stars: starsToSubmit,
          note: noteToSubmit.trim(),
        }),
      });

      if (res.status === 410) {
        setStateError("expired");
        return;
      }
      if (res.status === 404) {
        setStateError("not_found");
        return;
      }

      const resJson = await res.json().catch(() => ({}));
      if (!res.ok) {
        setSubmitError(resJson?.detail || "تعذر تسجيل التقييم.");
        return;
      }

      setData(resJson);
      setCurrentStars(resJson.stars);
      setNoteText(resJson.note || "");
      setSubmitSuccess(true);
    } catch (err: any) {
      setSubmitError(err?.message || "تعذر الاتصال بالخادم لإرسال التقييم.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStarClick = async (star: number) => {
    if (!data) return;
    if (data.already_rated && !data.can_edit) return;
    setCurrentStars(star);
    await handleSubmitRating(star, noteText);
  };

  const handleSaveNote = async () => {
    if (!data || currentStars < 1) return;
    if (data.already_rated && !data.can_edit) return;
    await handleSubmitRating(currentStars, noteText);
  };

  // شاشة التحميل
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex flex-col items-center justify-center p-4 text-slate-600 dark:text-slate-400">
        <RefreshCw className="w-10 h-10 animate-spin text-emerald-600 mb-3" />
        <p className="text-sm font-medium">جاري التحقق من صلاحية رابط التقييم...</p>
      </div>
    );
  }

  // شاشة انتهاء صلاحية الرابط (410)
  if (stateError === "expired") {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4" dir="rtl">
        <div className="max-w-md w-full rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 text-center space-y-4 shadow-sm">
          <div className="w-14 h-14 rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center mx-auto">
            <Clock className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            انتهت صلاحيّةُ هذا الرابط
          </h2>
          <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            تنتهي صلاحية روابط التقييم اليومية تلقائياً بعد مرور {formatNumber(72)} ساعة من تاريخ إنشائها لحماية دقة التقييمات.
          </p>
        </div>
      </div>
    );
  }

  // شاشة الرابط غير صالح (404)
  if (stateError === "not_found") {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4" dir="rtl">
        <div className="max-w-md w-full rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 text-center space-y-4 shadow-sm">
          <div className="w-14 h-14 rounded-full bg-red-100 dark:bg-red-950/60 text-red-600 dark:text-red-400 flex items-center justify-center mx-auto">
            <XCircle className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            الرابط غير صالح
          </h2>
          <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            الرابط المطلوب غير موجود أو تم إبطاله. يرجى مراجعة صاحب الشركة للحصول على رابط جديد.
          </p>
        </div>
      </div>
    );
  }

  // شاشة خطأ عام
  if (stateError === "general" || !data) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4" dir="rtl">
        <div className="max-w-md w-full rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 text-center space-y-4 shadow-sm">
          <div className="w-14 h-14 rounded-full bg-red-100 dark:bg-red-950/60 text-red-600 flex items-center justify-center mx-auto">
            <AlertTriangle className="w-7 h-7" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            تعذر تحميل صفحة التقييم
          </h2>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            {errorMessage || "حدث خطأ غير متوقع أثناء الاتصال بالخادم."}
          </p>
          <button
            onClick={() => void fetchTokenData()}
            className="px-4 py-2 text-xs font-semibold text-white bg-emerald-600 rounded-lg hover:bg-emerald-700 transition"
          >
            إعادة المحاولة
          </button>
        </div>
      </div>
    );
  }

  const isLocked = data.already_rated && !data.can_edit;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4 text-right" dir="rtl">
      <div className="max-w-lg w-full rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-lg p-6 md:p-8 space-y-6">
        {/* الترويسة والشعار */}
        <div className="text-center space-y-2 border-b border-slate-100 dark:border-slate-800 pb-4">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 mb-1">
            <Star className="w-6 h-6 fill-emerald-600 dark:fill-emerald-400" />
          </div>
          <h1 className="text-xl font-extrabold text-slate-900 dark:text-slate-100">
            تقييم أداء الوكيل اليومي
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            شهادتك المباشرة تساهم في تحسين جودة الخدمة والمتابعة المستمرة.
          </p>
        </div>

        {/* بطاقة معلومات الخدمة المعتمدة */}
        <div className="rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 p-4 space-y-2 text-xs">
          <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
            <Building2 className="w-4 h-4 text-slate-500 flex-shrink-0" />
            <span className="font-semibold">الشركة:</span>
            <span>{data.company_name}</span>
          </div>

          <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
            <User className="w-4 h-4 text-slate-500 flex-shrink-0" />
            <span className="font-semibold">الوكيل المكلّف:</span>
            <span>{data.employee_name}</span>
          </div>

          <div className="flex items-center gap-2 text-slate-700 dark:text-slate-300">
            <Calendar className="w-4 h-4 text-slate-500 flex-shrink-0" />
            <span className="font-semibold">تاريخ الخدمة:</span>
            <span>{formatDateValue(data.service_date)}</span>
          </div>
        </div>

        {/* رسائل التنبيه والنجاح والخطأ */}
        {submitSuccess && (
          <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>تم تسجيل تقييمك بنجاح. شكراً لتعاونك!</span>
          </div>
        )}

        {submitError && (
          <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs flex items-center gap-2">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            <span>{submitError}</span>
          </div>
        )}

        <DailyStarRating
          stars={currentStars}
          note={noteText}
          locked={isLocked}
          busy={isSubmitting}
          onPick={(star) => void handleStarClick(star)}
          onNoteChange={setNoteText}
          onSaveNote={() => void handleSaveNote()}
          label={data.already_rated ? "تقييمك المسجل:" : "انقر على النجوم لتسجيل تقييمك:"}
          saveLabel="حفظ التقييم والملاحظة"
          size="lg"
        />

        <div className="text-center pt-2">
          <p className="text-[11px] text-slate-400 dark:text-slate-500">
            رابط تقييم آمن ومحمي · منصة K.T.R.A
          </p>
        </div>
      </div>
    </div>
  );
};
