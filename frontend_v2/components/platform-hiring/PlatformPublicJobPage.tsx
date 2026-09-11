import React, { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  AlertTriangle,
  Briefcase,
  CheckCircle2,
  Clock,
  Loader2,
  MapPin,
  Paperclip,
  Wallet,
  XCircle,
} from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import {
  publicCareersApplyUrl,
  publicCareersJobUrl,
  type PublicApplicationReceipt,
  type PublicPlatformJob,
} from "../../services/platformHiringApi";
import { formatNumber } from "../../utils/formatNumber";
import { CV_ACCEPT_ATTRIBUTE, cvFileProblem, firstApiErrorMessage } from "../../utils/platformHiring";

/**
 * صفحةُ وظيفةٍ منصّيّةٍ والتقديمُ عليها — `/careers/job/:token` (#207 م٨-ب، القصّتان ٧٤ و٧٥).
 *
 * **خارج مزوّد المصادقة** ويفتحها مجهول، فتُنادي الخادمَ بطلبٍ عارٍ لا بـ`restApi`
 * (ذلك يحمل رأسَ الجلسة وشركتَها). والمسارُ يطابق `PLATFORM_JOB_PUBLIC_PATH` في الخادم.
 *
 * حالاتٌ لا تُخلَط: مفتوحةٌ · «انتهى التقديم» (٤١٠) · «لا وجودَ للرابط» (٤٠٤) ·
 * «الخادمُ لا يجيب». الأخيرةُ كانت تُقرأ في السابقة (`employee-ops/PublicJobPage`)
 * رابطاً غيرَ صالح، فيظنّ من فتح رابطاً صحيحاً أثناء انقطاعٍ أنّ الوظيفةَ لم توجد قطّ.
 */
type Phase = "loading" | "open" | "closed" | "missing" | "unavailable" | "submitted";

export const PlatformPublicJobPage: React.FC = () => {
  const { token = "" } = useParams<{ token: string }>();
  const confirm = useConfirm();

  const [phase, setPhase] = useState<Phase>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [job, setJob] = useState<PublicPlatformJob | null>(null);
  const [receipt, setReceipt] = useState<PublicApplicationReceipt | null>(null);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [about, setAbout] = useState("");
  const [cv, setCv] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let alive = true;
    setPhase("loading");
    fetch(publicCareersJobUrl(token), { headers: { Accept: "application/json" } })
      .then(async (res) => {
        if (!alive) return;
        if (res.status === 410) {
          setPhase("closed");
          return;
        }
        if (res.status === 404) {
          setPhase("missing");
          return;
        }
        if (!res.ok) {
          setPhase("unavailable");
          return;
        }
        setJob((await res.json()) as PublicPlatformJob);
        setPhase("open");
      })
      .catch(() => {
        if (alive) setPhase("unavailable");
      });
    return () => {
      alive = false;
    };
  }, [token, reloadKey]);

  const handleFile = (file: File | null) => {
    const problem = cvFileProblem(file);
    if (problem) {
      setFormError(problem);
      setCv(null);
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setFormError("");
    setCv(file);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError("");
    if (!name.trim() || !phone.trim()) {
      setFormError("الاسم ورقم التواصل مطلوبان.");
      return;
    }
    const problem = cvFileProblem(cv);
    if (problem) {
      setFormError(problem);
      return;
    }
    if (!cv) {
      const proceed = await confirm({
        title: "إرسال الطلب دون سيرة ذاتية؟",
        message: "تكفي نبذةٌ ورقمُ تواصل، لكنّ السيرةَ الذاتيّةَ تُسرّع فرزَ طلبك.",
        confirmText: "إرسال دون سيرة",
        cancelText: "إضافة السيرة",
        danger: false,
      });
      if (!proceed) return;
    }

    const body = new FormData();
    body.append("name", name.trim());
    body.append("phone", phone.trim());
    if (email.trim()) body.append("email", email.trim());
    if (about.trim()) body.append("about", about.trim());
    if (cv) body.append("cv_file", cv);

    setSubmitting(true);
    try {
      const res = await fetch(publicCareersApplyUrl(token), {
        method: "POST",
        headers: { Accept: "application/json" },
        body,
      });
      if (res.status === 410) {
        setPhase("closed");
        return;
      }
      if (res.status === 429) {
        setFormError("محاولاتٌ كثيرةٌ من هذا الجهاز. انتظر قليلاً ثم أعد المحاولة.");
        return;
      }
      const data: unknown = await res.json().catch(() => null);
      if (!res.ok) {
        setFormError(
          firstApiErrorMessage(data, res.status === 413 ? "حجم الطلب يتجاوز الحد المسموح." : "تعذّر إرسال الطلب."),
        );
        return;
      }
      setReceipt(data as PublicApplicationReceipt);
      setPhase("submitted");
    } catch {
      setFormError("تعذّر الاتصال بالخادم. تحقّق من اتصالك وأعد المحاولة.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass =
    "h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20";

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-start justify-center p-4 py-10" dir="rtl">
      <main className="w-full max-w-xl rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        {phase === "loading" && (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500" role="status">
            <Loader2 className="h-5 w-5 animate-spin" /> جاري تحميل الوظيفة...
          </div>
        )}

        {phase === "closed" && (
          <Notice
            icon={<Clock className="h-10 w-10 mx-auto text-amber-500" />}
            title="انتهى التقديم على هذه الوظيفة"
            body="كانت هذه الوظيفة مفتوحةً وأُغلقت. تابع إعلانات فريق كترا القادمة."
          />
        )}

        {phase === "missing" && (
          <Notice
            icon={<XCircle className="h-10 w-10 mx-auto text-slate-400" />}
            title="الرابط غير صالح"
            body="لا توجد وظيفة خلف هذا الرابط. تأكّد من نسخه كاملاً، أو اطلب رابطاً جديداً ممن أرسله."
          />
        )}

        {phase === "unavailable" && (
          <Notice
            icon={<AlertTriangle className="h-10 w-10 mx-auto text-amber-500" />}
            title="تعذّر الوصول إلى الخادم"
            body="الرابط قد يكون صحيحاً — لكنّ الخادم لم يُجب الآن."
            action={
              <button
                type="button"
                onClick={() => setReloadKey((key) => key + 1)}
                className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-700"
              >
                إعادة المحاولة
              </button>
            }
          />
        )}

        {phase === "submitted" && receipt && (
          <div className="py-8 text-center space-y-4" role="status">
            <CheckCircle2 className="h-12 w-12 mx-auto text-emerald-500" />
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              تم استلام طلبك على «{receipt.job_title}»
            </h1>
            <div className="mx-auto max-w-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 p-4 space-y-1">
              <p className="text-xs text-slate-500 dark:text-slate-400">رقم المرجع — احتفظ به</p>
              <p dir="ltr" className="font-mono text-lg font-bold tracking-wide text-slate-900 dark:text-slate-100 select-all">
                {receipt.reference_code}
              </p>
            </div>
            {receipt.cv_name && (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                السيرة المرفقة: <span dir="ltr">{receipt.cv_name}</span>
              </p>
            )}
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
              طلبك بانتظار الفرز. سيتواصل معك فريق التوظيف إن كان ملفك مناسباً.
            </p>
          </div>
        )}

        {phase === "open" && job && (
          <div className="space-y-5">
            <header className="space-y-2 pb-4 border-b border-slate-200 dark:border-slate-800">
              <p className="text-xs font-semibold text-blue-700 dark:text-blue-300">التوظيف · فريق منصة K.T.R.A</p>
              <h1 className="flex items-center gap-2 text-lg font-bold text-slate-900 dark:text-slate-100">
                <Briefcase className="h-5 w-5 text-blue-600 flex-shrink-0" />
                {job.title}
              </h1>

              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
                {job.location && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3.5 w-3.5" /> {job.location}
                  </span>
                )}
                {job.employment_type_display && (
                  <span className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" /> {job.employment_type_display}
                  </span>
                )}
                {job.salary_range && (
                  <span className="flex items-center gap-1">
                    <Wallet className="h-3.5 w-3.5" /> {job.salary_range}
                  </span>
                )}
              </div>

              <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                {job.description}
              </p>

              {job.requirements && (
                <div className="rounded-lg bg-slate-50 dark:bg-slate-950/50 p-3">
                  <h2 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">المتطلبات</h2>
                  <p className="text-xs text-slate-600 dark:text-slate-400 whitespace-pre-wrap leading-relaxed">
                    {job.requirements}
                  </p>
                </div>
              )}
            </header>

            <form onSubmit={handleSubmit} className="space-y-3.5" noValidate>
              <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">التقديم على الوظيفة</h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="careers-name" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    الاسم <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="careers-name"
                    type="text"
                    autoComplete="name"
                    maxLength={200}
                    required
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label htmlFor="careers-phone" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    رقم التواصل <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="careers-phone"
                    type="tel"
                    dir="ltr"
                    autoComplete="tel"
                    maxLength={40}
                    required
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    className={`${inputClass} text-right`}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="careers-email" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  البريد الإلكتروني
                </label>
                <input
                  id="careers-email"
                  type="email"
                  dir="ltr"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className={`${inputClass} text-right`}
                />
                <p className="mt-1 text-[11px] text-slate-400">إن قُبلت، يصلح اسمَ مستخدمٍ لحسابك.</p>
              </div>

              <div>
                <label htmlFor="careers-about" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  نبذة عنك
                </label>
                <textarea
                  id="careers-about"
                  rows={4}
                  value={about}
                  onChange={(event) => setAbout(event.target.value)}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                />
              </div>

              <div>
                <label htmlFor="careers-cv" className="mb-1 flex items-center gap-1 text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <Paperclip className="h-3.5 w-3.5" /> السيرة الذاتية (اختيارية)
                </label>
                <input
                  id="careers-cv"
                  ref={fileRef}
                  type="file"
                  accept={CV_ACCEPT_ATTRIBUTE}
                  onChange={(event) => handleFile(event.target.files?.[0] || null)}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-xs text-slate-700 dark:text-slate-300 outline-none"
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  PDF أو Word أو صورة، بحد أقصى {formatNumber(5)} ميجابايت.
                </p>
              </div>

              {formError && (
                <p role="alert" className="text-xs font-semibold text-red-600 dark:text-red-400">
                  {formError}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 py-2.5 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-60"
              >
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                {submitting ? "جاري الإرسال..." : "إرسال الطلب"}
              </button>
            </form>
          </div>
        )}
      </main>
    </div>
  );
};

const Notice: React.FC<{ icon: React.ReactNode; title: string; body: string; action?: React.ReactNode }> = ({
  icon,
  title,
  body,
  action,
}) => (
  <div className="text-center py-10 space-y-3">
    {icon}
    <h1 className="text-base font-bold text-slate-900 dark:text-slate-100">{title}</h1>
    <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">{body}</p>
    {action}
  </div>
);
