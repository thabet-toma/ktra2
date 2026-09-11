import React, { useEffect, useState } from "react";
import {
  Copy,
  FileText,
  Loader2,
  Mail,
  Phone,
  Send,
  Star,
  X,
} from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  getPlatformApplicantCv,
  invitePlatformApplicant,
  ratePlatformApplicant,
  transitionPlatformApplicant,
  type ApplicantInvitation,
  type PlatformJobApplicant,
} from "../../services/platformHiringApi";
import { formatNumber } from "../../utils/formatNumber";
import { applicantStatusBadgeClass, firstApiErrorMessage } from "../../utils/platformHiring";

interface PlatformApplicantPanelProps {
  applicant: PlatformJobApplicant | null;
  onClose: () => void;
  onUpdated: (updated: PlatformJobApplicant) => void;
}

export const PlatformApplicantPanel: React.FC<PlatformApplicantPanelProps> = ({
  applicant,
  onClose,
  onUpdated,
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  // تقييم وملاحظات
  const [rating, setRating] = useState<number>(0);
  const [notes, setNotes] = useState<string>("");
  const [savingRating, setSavingRating] = useState(false);

  // السيرة الذاتية
  const [openingCv, setOpeningCv] = useState(false);

  // حالة النقل
  const [transitioningTo, setTransitioningTo] = useState<string | null>(null);

  // إصدار الدعوة
  const [expiresInHours, setExpiresInHours] = useState<string>("72");
  const [issuingInvite, setIssuingInvite] = useState(false);
  const [issuedInvitation, setIssuedInvitation] = useState<ApplicantInvitation | null>(null);

  useEffect(() => {
    if (applicant) {
      setRating(applicant.rating ?? 0);
      setNotes(applicant.notes || "");
      setIssuedInvitation(null);
      setExpiresInHours("72");
    }
  }, [applicant?.id]);

  if (!applicant) return null;

  const handleStarClick = (num: number) => {
    // نقر النجمة الحالية يصفّر التقييم
    setRating((prev) => (prev === num ? 0 : num));
  };

  const handleSaveRating = async () => {
    setSavingRating(true);
    try {
      const updated = await ratePlatformApplicant(applicant.id, { rating, notes });
      onUpdated(updated);
      toast("تم حفظ التقييم والملاحظات بنجاح.", "success");
    } catch (err: any) {
      toast(firstApiErrorMessage(err?.data || err, "تعذر حفظ التقييم."), "error");
    } finally {
      setSavingRating(false);
    }
  };

  const handleTransition = async (targetStatus: string, label: string) => {
    if (targetStatus === "rejected") {
      const ok = await confirm({
        title: "رفض المتقدم",
        message: `هل أنت متأكد من رفض طلب «${applicant.name}»؟`,
        confirmText: "تأكيد الرفض",
        danger: true,
      });
      if (!ok) return;
    }

    setTransitioningTo(targetStatus);
    try {
      const updated = await transitionPlatformApplicant(applicant.id, targetStatus);
      onUpdated(updated);
      toast(`تم نقل المتقدم إلى: ${label}`, "success");
    } catch (err: any) {
      toast(firstApiErrorMessage(err?.data || err, "تعذر تغيير حالة المتقدم."), "error");
    } finally {
      setTransitioningTo(null);
    }
  };

  const handleOpenCv = async () => {
    const popup = window.open("about:blank", "_blank");
    if (!popup) {
      toast("تعذّر فتح تبويب السيرة — اسمح بالنوافذ المنبثقة ثم حاول مجدداً", "error");
      return;
    }
    setOpeningCv(true);
    try {
      const cvBlob = await getPlatformApplicantCv(applicant.id);
      const objectUrl = URL.createObjectURL(cvBlob);
      popup.document.title = applicant.cv_name || "السيرة الذاتية";
      const viewer = popup.document.createElement("iframe");
      viewer.src = objectUrl;
      viewer.title = applicant.cv_name || "السيرة الذاتية";
      viewer.width = "100%";
      viewer.height = String(Math.max(popup.innerHeight - 24, 480));
      viewer.setAttribute("frameborder", "0");
      popup.document.body.replaceChildren(viewer);
      popup.opener = null;
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
    } catch (err: any) {
      popup.close();
      toast(err?.message || "تعذّر فتح السيرة الذاتية", "error");
    } finally {
      setOpeningCv(false);
    }
  };

  const handleIssueInvite = async () => {
    const hours = parseInt(expiresInHours, 10);
    if (!Number.isInteger(hours) || hours < 1 || hours > 168) {
      toast("مدة الصلاحية يجب أن تكون بين 1 و168 ساعة.", "error");
      return;
    }

    setIssuingInvite(true);
    try {
      const invitation = await invitePlatformApplicant(applicant.id, hours);
      setIssuedInvitation(invitation);
      toast("تم إصدار رابط الدعوة بنجاح.", "success");
    } catch (err: any) {
      toast(firstApiErrorMessage(err?.data || err, "تعذر إصدار رابط الدعوة."), "error");
    } finally {
      setIssuingInvite(false);
    }
  };

  const handleCopyInviteUrl = async () => {
    if (!issuedInvitation) return;
    try {
      await navigator.clipboard.writeText(issuedInvitation.invite_url);
      toast("تم نسخ رابط الدعوة.", "success");
    } catch {
      toast("تعذر نسخ الرابط.", "error");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-end bg-slate-900/60" dir="rtl">
      <div className="relative w-full max-w-xl h-full bg-white dark:bg-slate-900 shadow-2xl border-r border-slate-200 dark:border-slate-800 overflow-y-auto p-6 space-y-6 text-right">
        {/* رأس اللوحة */}
        <div className="flex items-start justify-between border-b border-slate-200 dark:border-slate-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">{applicant.name}</h2>
              <span
                className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${applicantStatusBadgeClass(
                  applicant.status,
                )}`}
              >
                {applicant.status_display}
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              متقدم على وظيفة: <span className="font-semibold text-slate-700 dark:text-slate-300">{applicant.job_title}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="إغلاق"
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* أزرار الانتقال بين الحالات */}
        <div className="rounded-xl bg-slate-50 dark:bg-slate-800/50 p-4 border border-slate-200 dark:border-slate-800 space-y-2">
          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block">
            تحريك حالة المتقدم:
          </span>
          {applicant.next_statuses && applicant.next_statuses.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {applicant.next_statuses.map((next) => {
                const isThisTransitioning = transitioningTo === next.value;
                return (
                  <button
                    key={next.value}
                    type="button"
                    disabled={transitioningTo !== null}
                    onClick={() => handleTransition(next.value, next.label)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition shadow-sm disabled:opacity-50 ${
                      next.value === "rejected"
                        ? "bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800"
                        : "bg-blue-600 text-white hover:bg-blue-700"
                    }`}
                  >
                    {isThisTransitioning ? "جاري النقل..." : `الانتقال إلى: ${next.label}`}
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-slate-400 dark:text-slate-500">
              لا توجد انتقالات مسموحة من هذه الحالة حالياً.
            </p>
          )}
        </div>

        {/* بيانات الاتصال والمعلومات */}
        <div className="space-y-3">
          <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            بيانات المتقدم
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 flex items-center gap-2.5">
              <Phone className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
              <div>
                <span className="text-[11px] text-slate-400 block">الهاتف</span>
                <span dir="ltr" className="font-semibold text-slate-800 dark:text-slate-200 inline-block">
                  {applicant.phone || "—"}
                </span>
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 flex items-center gap-2.5">
              <Mail className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
              <div className="overflow-hidden">
                <span className="text-[11px] text-slate-400 block">البريد</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200 truncate block">
                  {applicant.email || "—"}
                </span>
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3 flex items-center gap-2.5 sm:col-span-2">
              <span className="text-xs font-mono font-bold text-slate-400">#</span>
              <div>
                <span className="text-[11px] text-slate-400 block">رمز المرجع</span>
                <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">
                  {applicant.reference_code}
                </span>
              </div>
            </div>
          </div>

          {applicant.about && (
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-3.5 space-y-1">
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block">
                نبذة عن المتقدم:
              </span>
              <p className="text-xs text-slate-600 dark:text-slate-400 whitespace-pre-wrap leading-relaxed">
                {applicant.about}
              </p>
            </div>
          )}
        </div>

        {/* السيرة الذاتية */}
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-2">
          <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
            السيرة الذاتية
          </span>
          {applicant.has_cv ? (
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
                <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                <span>{applicant.cv_name || "ملف السيرة الذاتية"}</span>
              </div>
              <button
                type="button"
                onClick={handleOpenCv}
                disabled={openingCv}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/40 dark:text-blue-300 dark:hover:bg-blue-900/60 rounded-lg border border-blue-200 dark:border-blue-800 transition disabled:opacity-50"
              >
                {openingCv ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                فتح السيرة
              </button>
            </div>
          ) : (
            <p className="text-xs text-slate-400 dark:text-slate-500">
              لم يرفق المتقدم ملف سيرة ذاتية.
            </p>
          )}
        </div>

        {/* قسم الدعوة: يظهر فقط حين status === "offered" ولا يوجد hired_employee */}
        {applicant.status === "offered" && !applicant.hired_employee && (
          <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/30 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Send className="w-4 h-4 text-amber-700 dark:text-amber-400" />
              <h3 className="text-xs font-bold text-amber-900 dark:text-amber-200">
                إصدار رابط دعوة المرشح
              </h3>
            </div>
            <p className="text-[11px] text-amber-800 dark:text-amber-300">
              المرشح في حالة «عرض عمل». يمكنك إصدار رابط دعوة قبول التوظيف لمشاركته معه لإنشاء حسابه بنفسه.
            </p>

            <div className="flex items-center gap-3">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 whitespace-nowrap">
                الصلاحية بالساعات:
              </label>
              <input
                type="number"
                min={1}
                max={168}
                value={expiresInHours}
                onChange={(e) => setExpiresInHours(e.target.value)}
                className="w-24 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-900 dark:text-slate-100"
              />
              <button
                type="button"
                onClick={handleIssueInvite}
                disabled={issuingInvite}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 rounded-lg shadow-sm transition disabled:opacity-50 mr-auto"
              >
                {issuingInvite && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                إصدار رابط الدعوة
              </button>
            </div>

            {issuedInvitation && (
              <div className="mt-3 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40 p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-emerald-800 dark:text-emerald-200">
                    رابط الدعوة المُصدَر:
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyInviteUrl}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-emerald-700 bg-white dark:bg-slate-800 rounded border border-emerald-300 dark:border-emerald-700 hover:bg-emerald-100 dark:hover:bg-emerald-900/60 transition"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    نسخ الرابط
                  </button>
                </div>
                <div className="font-mono text-xs text-slate-800 dark:text-slate-200 break-all p-2 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                  {issuedInvitation.invite_url}
                </div>
                <p className="text-[11px] font-semibold text-emerald-800 dark:text-emerald-300">
                  احفظه الآن — لا يمكن عرضه مرّةً أخرى، وإصدارُ رابطٍ جديد يُبطل هذا.
                </p>
              </div>
            )}
          </div>
        )}

        {/* التقييم والملاحظات */}
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
              تقييم مسؤول التوظيف
            </span>
            <span className="text-xs text-slate-400">
              {rating > 0 ? `${formatNumber(rating)} من 5 نجوم` : "بلا تقييم"}
            </span>
          </div>

          <div className="flex items-center gap-1.5" dir="ltr">
            {[1, 2, 3, 4, 5].map((starNum) => (
              <button
                key={starNum}
                type="button"
                onClick={() => handleStarClick(starNum)}
                aria-pressed={starNum <= rating}
                className="p-1 text-amber-400 hover:scale-110 transition"
                title={`تقييم ${starNum}`}
              >
                <Star
                  className={`w-6 h-6 ${
                    starNum <= rating ? "fill-amber-400 text-amber-400" : "text-slate-300 dark:text-slate-600"
                  }`}
                />
              </button>
            ))}
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
              ملاحظات مسؤول التوظيف
            </label>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="انطباع المقابلة، نقاط القوة، الملاحظات الإدارية..."
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 p-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <button
            type="button"
            onClick={handleSaveRating}
            disabled={savingRating}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition disabled:opacity-50"
          >
            {savingRating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            حفظ التقييم والملاحظات
          </button>
        </div>
      </div>
    </div>
  );
};
