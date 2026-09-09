import React, { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { API_BASE } from "../../services/restApi";
import {
  Briefcase,
  CheckCircle2,
  Clock,
  Loader2,
  MapPin,
  Paperclip,
  Wallet,
  XCircle,
} from "lucide-react";

/**
 * صفحةُ التقديم على وظيفة — **خارج مزوّد المصادقة**، الاستثناءُ الوحيد الذي
 * تسمّيه المواصفة في §9.
 *
 * ثلاثُ حالات: الوظيفةُ مفتوحة · «انتهى التقديم» (٤١٠) · «لا وجود للرابط» (٤٠٤).
 * والفرقُ بين الأخيرتين يهمّ من فتح الرابط: «كان هنا وانتهى» غيرُ «لم يكن قطّ».
 *
 * ولا `restApi` هنا: عميلُ المنصة يحمل رأسَ المصادقة وشركةَ الجلسة، وهذه صفحةٌ
 * يفتحها مجهولٌ لا جلسةَ له — فطلبٌ عارٍ أصدقُ وأخفّ.
 */
const EMPLOYMENT_TYPE_LABELS: Record<string, string> = {
  full_time: "دوام كامل",
  part_time: "دوام جزئي",
  contract: "عقد",
  temporary: "مؤقت",
};

/** مرآةُ `MAX_CV_BYTES` في الخادم — رسالةٌ قبل الرفع بدل رفضٍ بعده. */
const MAX_CV_BYTES = 5 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = ".pdf,.doc,.docx,.jpg,.jpeg,.png,.webp";

interface PublicJob {
  title: string;
  description: string;
  requirements: string;
  location: string;
  employment_type: string;
  salary_range: string;
}

type Phase = "loading" | "open" | "closed" | "missing" | "submitted";

export const PublicJobPage: React.FC = () => {
  const { token = "" } = useParams();

  const [phase, setPhase] = useState<Phase>("loading");
  const [job, setJob] = useState<PublicJob | null>(null);
  const [reference, setReference] = useState("");

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
    fetch(`${API_BASE}/employee-ops/public/jobs/${encodeURIComponent(token)}/`)
      .then(async (res) => {
        if (!alive) return;
        if (res.status === 410) {
          setPhase("closed");
          return;
        }
        if (!res.ok) {
          setPhase("missing");
          return;
        }
        setJob(await res.json());
        setPhase("open");
      })
      .catch(() => {
        if (alive) setPhase("missing");
      });
    return () => {
      alive = false;
    };
  }, [token]);

  const handleFile = (file: File | null) => {
    setFormError("");
    if (file && file.size > MAX_CV_BYTES) {
      setFormError("حجم السيرة الذاتية يتجاوز الحد المسموح (٥ ميجابايت).");
      if (fileRef.current) fileRef.current.value = "";
      setCv(null);
      return;
    }
    setCv(file);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    if (!name.trim() || !phone.trim()) {
      setFormError("الاسم ورقم التواصل مطلوبان.");
      return;
    }

    const body = new FormData();
    body.append("name", name.trim());
    body.append("phone", phone.trim());
    if (email.trim()) body.append("email", email.trim());
    if (about.trim()) body.append("about", about.trim());
    if (cv) body.append("cv", cv);

    setSubmitting(true);
    try {
      const res = await fetch(
        `${API_BASE}/employee-ops/public/jobs/${encodeURIComponent(token)}/apply/`,
        { method: "POST", body },
      );
      if (res.status === 410) {
        setPhase("closed");
        return;
      }
      if (res.status === 429) {
        setFormError("عدد المحاولات كبير. حاول بعد قليل.");
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const first = Object.values(data)[0];
        setFormError(
          Array.isArray(first) ? String(first[0]) : String(first || "تعذّر إرسال الطلب."),
        );
        return;
      }
      setReference(data.reference_code || "");
      setPhase("submitted");
    } catch {
      setFormError("تعذّر الاتصال بالخادم. حاول مرة أخرى.");
    } finally {
      setSubmitting(false);
    }
  };

  const notice = (icon: React.ReactNode, title: string, body: string) => (
    <div className="text-center py-10 space-y-3">
      {icon}
      <h1 className="text-base font-bold text-slate-900 dark:text-slate-100">{title}</h1>
      <p className="text-sm text-slate-500 leading-relaxed">{body}</p>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-start justify-center p-4 py-10">
      <div className="w-full max-w-xl rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        {phase === "loading" && (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" /> جاري تحميل الوظيفة...
          </div>
        )}

        {phase === "closed" &&
          notice(
            <XCircle className="h-10 w-10 mx-auto text-amber-500" />,
            "انتهى التقديم على هذه الوظيفة",
            "كانت هذه الوظيفة مفتوحة وأُغلقت. تابع صفحات الشركة لإعلانات جديدة.",
          )}

        {phase === "missing" &&
          notice(
            <XCircle className="h-10 w-10 mx-auto text-slate-400" />,
            "الرابط غير صالح",
            "لا توجد وظيفة خلف هذا الرابط. تأكّد من نسخه كاملاً.",
          )}

        {phase === "submitted" &&
          notice(
            <CheckCircle2 className="h-10 w-10 mx-auto text-emerald-500" />,
            "تم استلام طلبك",
            `احتفظ برقم المرجع: ${reference}. سيتواصل معك المسؤول إن كان ملفك مناسباً.`,
          )}

        {phase === "open" && job && (
          <div className="space-y-5">
            <div className="space-y-2 pb-4 border-b border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <Briefcase className="h-5 w-5 text-blue-600" />
                <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                  {job.title}
                </h1>
              </div>

              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
                {job.location && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3.5 w-3.5" /> {job.location}
                  </span>
                )}
                {job.employment_type && (
                  <span className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    {EMPLOYMENT_TYPE_LABELS[job.employment_type] || job.employment_type}
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
                  <h2 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                    المتطلبات
                  </h2>
                  <p className="text-xs text-slate-600 dark:text-slate-400 whitespace-pre-wrap leading-relaxed">
                    {job.requirements}
                  </p>
                </div>
              )}
            </div>

            <form onSubmit={handleSubmit} className="space-y-3.5">
              <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                التقديم على الوظيفة
              </h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    الاسم <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    رقم التواصل <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  البريد الإلكتروني
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  نبذة عنك
                </label>
                <textarea
                  value={about}
                  onChange={(e) => setAbout(e.target.value)}
                  rows={4}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="mb-1 flex items-center gap-1 text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <Paperclip className="h-3.5 w-3.5" /> السيرة الذاتية (اختيارية)
                </label>
                <input
                  ref={fileRef}
                  type="file"
                  accept={ACCEPTED_EXTENSIONS}
                  onChange={(e) => handleFile(e.target.files?.[0] || null)}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-xs text-slate-700 dark:text-slate-300 outline-none"
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  PDF أو Word أو صورة، بحد أقصى ٥ ميجابايت. وليس إلزامياً — تكفي نبذة
                  ورقم تواصل.
                </p>
              </div>

              {formError && (
                <p role="alert" className="text-xs font-semibold text-red-600">
                  {formError}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 py-2.5 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-60"
              >
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                إرسال الطلب
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
