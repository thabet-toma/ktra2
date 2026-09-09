import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { API_BASE } from "../../services/restApi";
import { CheckCircle2, Loader2, ShieldAlert, UserPlus } from "lucide-react";


/**
 * صفحةُ قبول دعوة الموظف — **خارج مزوّد المصادقة** كصفحة المتجر العامّة.
 *
 * كان رابطُ الدعوة يشير إلى نقطة الـAPI مباشرةً، فيفتحه الموظفُ فيرى JSON لا
 * نموذجَ كلمةِ مرور — أي أنّ الوحدةَ لم تكن تعمل من طرفٍ إلى طرف رغم أنّ كلَّ
 * ما تحتها أخضر. هذه الصفحةُ هي الحلقةُ المفقودة.
 */
interface InvitationInfo {
  company_name: string;
  employee_name: string;
  /** الموظفُ العائد يملك حسابَه أصلاً، فلا تُسأل كلمةُ مرورٍ جديدة. */
  needs_account: boolean;
}

type Phase = "loading" | "form" | "done" | "invalid";

/** `API_BASE` قد يكون أصلاً آخر في التطوير — لا تُثبَّت البادئة يدوياً. */
const BASE = `${API_BASE}/employee-ops`;

export const PublicJoinPage: React.FC = () => {
  const { token = "" } = useParams();

  const [phase, setPhase] = useState<Phase>("loading");
  const [info, setInfo] = useState<InvitationInfo | null>(null);
  const [error, setError] = useState("");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  // طلبٌ عارٍ لا `restApi`: عميلُ المنصة يحمل رأسَ المصادقة وشركةَ الجلسة،
  // وهذه صفحةٌ يفتحها من لا جلسةَ له بعد.
  useEffect(() => {
    let alive = true;
    fetch(`${BASE}/invitations/accept/${encodeURIComponent(token)}/`)
      .then(async (res) => {
        if (!alive) return;
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          setError(body?.detail || "هذه الدعوة لم تعد صالحة.");
          setPhase("invalid");
          return;
        }
        setInfo(await res.json());
        setPhase("form");
      })
      .catch(() => {
        if (alive) {
          setError("تعذّر الاتصال بالخادم.");
          setPhase("invalid");
        }
      });
    return () => {
      alive = false;
    };
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");

    if (info?.needs_account) {
      if (!username.trim()) {
        setFormError("اسم المستخدم مطلوب.");
        return;
      }
      if (password !== confirm) {
        setFormError("كلمتا المرور غير متطابقتين.");
        return;
      }
    }

    setSubmitting(true);
    try {
      const res = await fetch(
        `${BASE}/invitations/accept/${encodeURIComponent(token)}/`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: username.trim(),
            password,
            first_name: firstName.trim(),
            last_name: lastName.trim(),
          }),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const first = Object.values(body)[0];
        setFormError(
          Array.isArray(first)
            ? String(first[0])
            : String(first || "تعذّر إتمام الانضمام."),
        );
        return;
      }
      setPhase("done");
    } catch (err: any) {
      setFormError(err?.message || "تعذّر إتمام الانضمام.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
        {phase === "loading" && (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" /> جاري التحقق من الدعوة...
          </div>
        )}

        {phase === "invalid" && (
          <div className="text-center py-8 space-y-3">
            <ShieldAlert className="h-10 w-10 mx-auto text-amber-500" />
            <h1 className="text-base font-bold text-slate-900 dark:text-slate-100">
              الدعوة غير صالحة
            </h1>
            <p className="text-sm text-slate-500 leading-relaxed">{error}</p>
            <p className="text-xs text-slate-400">
              اطلب من مديرك إرسال دعوة جديدة.
            </p>
          </div>
        )}

        {phase === "done" && (
          <div className="text-center py-8 space-y-3">
            <CheckCircle2 className="h-10 w-10 mx-auto text-emerald-500" />
            <h1 className="text-base font-bold text-slate-900 dark:text-slate-100">
              تم الانضمام بنجاح
            </h1>
            <p className="text-sm text-slate-500 leading-relaxed">
              صار بإمكانك تسجيل الدخول ومتابعة مهامك من شاشة «يومي».
            </p>
            <a
              href="/"
              className="inline-block rounded-lg bg-blue-600 px-5 py-2 text-sm font-bold text-white hover:bg-blue-700"
            >
              الذهاب لتسجيل الدخول
            </a>
          </div>
        )}

        {phase === "form" && info && (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="text-center space-y-1 pb-2 border-b border-slate-200 dark:border-slate-800">
              <UserPlus className="h-8 w-8 mx-auto text-blue-600" />
              <h1 className="text-base font-bold text-slate-900 dark:text-slate-100">
                دعوة للانضمام إلى {info.company_name}
              </h1>
              <p className="text-sm text-slate-500">مرحباً {info.employee_name}</p>
            </div>

            {info.needs_account ? (
              <>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    اسم المستخدم
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      الاسم الأول
                    </label>
                    <input
                      type="text"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      اسم العائلة
                    </label>
                    <input
                      type="text"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    كلمة المرور
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    تأكيد كلمة المرور
                  </label>
                  <input
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    autoComplete="new-password"
                    className="h-10 w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-blue-500"
                  />
                </div>
              </>
            ) : (
              <p className="rounded-lg bg-blue-50 dark:bg-blue-950/30 p-3 text-sm text-blue-800 dark:text-blue-300 leading-relaxed">
                لديك حساب على المنصة بالفعل — اضغط «انضمام» لإعادة تفعيل عضويتك في هذه
                الشركة، ثم سجّل الدخول بحسابك المعتاد.
              </p>
            )}

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
              انضمام
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
