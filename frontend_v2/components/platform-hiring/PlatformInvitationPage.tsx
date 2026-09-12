import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  AlertTriangle,
  Briefcase,
  CheckCircle2,
  Clock,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  XCircle,
} from "lucide-react";

import {
  publicInvitationAcceptUrl,
  publicInvitationUrl,
  type InvitationAcceptance,
  type PublicInvitationDetail,
} from "../../services/platformHiringApi";
import { formatDateTimeValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { MIN_PASSWORD_LENGTH, firstApiErrorMessage, passwordProblem } from "../../utils/platformHiring";

/**
 * صفحةُ قبول دعوة التوظيف — `/careers/invite/:token` (#207 م٨-ب، القصّة ٧٨).
 *
 * **الحسابُ يولد هنا لا قبلها**: المرشّحُ المقبولُ لا مستخدمَ له حتى يضع كلمةَ مروره
 * بنفسه، فلا تمتلئ القاعدةُ بحساباتٍ ميّتة. ورابطُ الدعوة يقود إلى **صفحة** لا إلى
 * نقطة API تردّ JSON — عيبٌ وقع في `employee_ops` وأُصلح هناك.
 *
 * المسارُ يطابق `PLATFORM_HIRING_INVITATION_PATH` في الخادم، والصفحةُ خارج مزوّد
 * المصادقة فتنادي الخادمَ بطلبٍ عارٍ.
 */
type Phase = "loading" | "ready" | "expired" | "missing" | "unavailable" | "accepted";

export const PlatformInvitationPage: React.FC = () => {
  const { token = "" } = useParams<{ token: string }>();

  const [phase, setPhase] = useState<Phase>("loading");
  const [reloadKey, setReloadKey] = useState(0);
  const [detail, setDetail] = useState<PublicInvitationDetail | null>(null);
  const [acceptance, setAcceptance] = useState<InvitationAcceptance | null>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    let alive = true;
    setPhase("loading");
    fetch(publicInvitationUrl(token), { headers: { Accept: "application/json" } })
      .then(async (res) => {
        if (!alive) return;
        if (res.status === 410) {
          setPhase("expired");
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
        setDetail((await res.json()) as PublicInvitationDetail);
        setPhase("ready");
      })
      .catch(() => {
        if (alive) setPhase("unavailable");
      });
    return () => {
      alive = false;
    };
  }, [token, reloadKey]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const problem = passwordProblem(password, confirmation);
    if (problem) {
      setFormError(problem);
      return;
    }
    setFormError("");
    setSubmitting(true);
    try {
      const res = await fetch(publicInvitationAcceptUrl(token), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (res.status === 410) {
        setPhase("expired");
        return;
      }
      if (res.status === 404) {
        setPhase("missing");
        return;
      }
      if (res.status === 429) {
        setFormError("محاولاتٌ كثيرةٌ من هذا الجهاز. انتظر قليلاً ثم أعد المحاولة.");
        return;
      }
      const data: unknown = await res.json().catch(() => null);
      if (!res.ok) {
        setFormError(firstApiErrorMessage(data, "تعذّر إنشاء الحساب."));
        return;
      }
      const accepted = data as InvitationAcceptance;
      // **211-A — الجلسةُ تُحفَظ بمفتاحَي الدخول نفسِهما** (`authService.loginUser`)
      // لا بمفتاحٍ ثالثٍ يعرفه هذا الملفُّ وحدَه: `restApi` يقرأ `token` و`userId`
      // من هنا في كلّ نداءٍ تالٍ، فمفتاحٌ مختلفٌ يعني حساباً أُنشئ وجلسةً تُهدَر.
      if (accepted?.token) {
        try {
          window.localStorage.setItem("token", accepted.token);
          if (accepted.user?.id) {
            window.localStorage.setItem("userId", String(accepted.user.id));
          }
        } catch {
          // تخزينٌ محليٌّ محجوبٌ (تصفّحٌ خاصّ) — تبقى شاشةُ النجاح ويدخل يدوياً.
        }
      }
      setAcceptance(accepted);
      setPhase("accepted");
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
      <main className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        {phase === "loading" && (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500" role="status">
            <Loader2 className="h-5 w-5 animate-spin" /> جاري التحقّق من الدعوة...
          </div>
        )}

        {phase === "expired" && (
          <Notice
            icon={<Clock className="h-10 w-10 mx-auto text-amber-500" />}
            title="انتهت صلاحية هذه الدعوة"
            body="قُبلت الدعوة من قبل، أو أُلغيت، أو مضى موعدها. اطلب من فريق التوظيف رابطاً جديداً."
          />
        )}

        {phase === "missing" && (
          <Notice
            icon={<XCircle className="h-10 w-10 mx-auto text-slate-400" />}
            title="رابط الدعوة غير صالح"
            body="لا توجد دعوة خلف هذا الرابط. تأكّد من نسخه كاملاً كما وصلك."
          />
        )}

        {phase === "unavailable" && (
          <Notice
            icon={<AlertTriangle className="h-10 w-10 mx-auto text-amber-500" />}
            title="تعذّر الوصول إلى الخادم"
            body="الدعوة قد تكون صالحة — لكنّ الخادم لم يُجب الآن."
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

        {phase === "accepted" && acceptance && (
          <div className="py-8 text-center space-y-4" role="status">
            <CheckCircle2 className="h-12 w-12 mx-auto text-emerald-500" />
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">أهلاً بك في فريق كترا</h1>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {acceptance.token
                ? "أُنشئ حسابك ودخلتَ بالفعل. احفظ اسم المستخدم لدخولك القادم:"
                : "أُنشئ حسابك. ادخل باسم المستخدم:"}
            </p>
            <p
              dir="ltr"
              className="mx-auto max-w-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 p-3 font-mono text-base font-bold text-slate-900 dark:text-slate-100 select-all"
            >
              {acceptance.username}
            </p>
            <a
              href={acceptance.token ? "/platform/employee-space" : "/"}
              className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-bold text-white hover:bg-blue-700"
            >
              {acceptance.token ? "ادخل إلى مساحتك" : "تسجيل الدخول"}
            </a>
          </div>
        )}

        {phase === "ready" && detail && (
          <div className="space-y-5">
            <header className="space-y-2 pb-4 border-b border-slate-200 dark:border-slate-800">
              <p className="text-xs font-semibold text-blue-700 dark:text-blue-300">دعوة انضمام · فريق منصة K.T.R.A</p>
              <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">مرحباً {detail.applicant_name}</h1>
              <p className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <Briefcase className="h-4 w-4 text-blue-600 flex-shrink-0" />
                قُبلتَ على وظيفة «{detail.job_title}». أنشئ حسابك لتبدأ.
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                تنتهي صلاحية الدعوة: {formatDateTimeValue(detail.expires_at)}
              </p>
            </header>

            <form onSubmit={handleSubmit} className="space-y-3.5" noValidate>
              <div>
                <label htmlFor="invite-username" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  اسم المستخدم (اختياري)
                </label>
                <input
                  id="invite-username"
                  type="text"
                  dir="ltr"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder={detail.email || ""}
                  className={`${inputClass} text-right`}
                />
                <p className="mt-1 text-[11px] text-slate-400">
                  {detail.email
                    ? "اتركه فارغاً لنستعمل بريدك إن كان متاحاً."
                    : "اتركه فارغاً فنولّد لك اسماً ونعرضه بعد الإنشاء."}
                </p>
              </div>

              <div>
                <label htmlFor="invite-password" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  كلمة المرور <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <input
                    id="invite-password"
                    type={showPassword ? "text" : "password"}
                    dir="ltr"
                    autoComplete="new-password"
                    minLength={MIN_PASSWORD_LENGTH}
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className={`${inputClass} pl-10 text-right`}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-pressed={showPassword}
                    aria-label={showPassword ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"}
                    className="absolute inset-y-0 left-0 flex w-10 items-center justify-center text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  {formatNumber(MIN_PASSWORD_LENGTH)} محارف على الأقل.
                </p>
              </div>

              <div>
                <label htmlFor="invite-confirmation" className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  تأكيد كلمة المرور <span className="text-red-500">*</span>
                </label>
                <input
                  id="invite-confirmation"
                  type={showPassword ? "text" : "password"}
                  dir="ltr"
                  autoComplete="new-password"
                  required
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  className={`${inputClass} text-right`}
                />
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
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                {submitting ? "جاري إنشاء الحساب..." : "قبول الدعوة وإنشاء الحساب"}
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
