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
  createPlatformApplicantNotice,
  listPlatformApplicantUpdates,
  ratePlatformApplicant,
  transitionPlatformApplicant,
  type ApplicantInvitation,
  type PlatformApplicantUpdate,
  type PlatformJobApplicant,
} from "../../services/platformHiringApi";
import { formatNumber } from "../../utils/formatNumber";
import { applicantStatusTone, firstApiErrorMessage } from "../../utils/platformHiring";
import { CcAvatar, CcCard, CcPill, CcSectionTitle } from "../platform/ui";
import { ApplicantUpdateThread } from "./ApplicantUpdateThread";

interface PlatformApplicantPanelProps {
  applicant: PlatformJobApplicant | null;
  onClose: () => void;
  onUpdated: (updated: PlatformJobApplicant) => void;
}

export const PlatformApplicantPanel: React.FC<PlatformApplicantPanelProps> = ({
  applicant,
  onClose,
  onUpdated,
}: PlatformApplicantPanelProps) => {
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
  const [invitationNote, setInvitationNote] = useState<string>("");
  const [invitationContactPhone, setInvitationContactPhone] = useState<string>("");
  const [issuingInvite, setIssuingInvite] = useState(false);
  const [issuedInvitation, setIssuedInvitation] = useState<ApplicantInvitation | null>(null);

  const [updates, setUpdates] = useState<PlatformApplicantUpdate[]>([]);
  const [updatesLoading, setUpdatesLoading] = useState(false);
  const [updatesError, setUpdatesError] = useState("");
  const [noticeBody, setNoticeBody] = useState("");
  const [noticeLink, setNoticeLink] = useState("");
  const [noticePhone, setNoticePhone] = useState("");
  const [sendingNotice, setSendingNotice] = useState(false);

  useEffect(() => {
    if (applicant) {
      setRating(applicant.rating ?? 0);
      setNotes(applicant.notes || "");
      setIssuedInvitation(null);
      setExpiresInHours("72");
      setInvitationNote("");
      setInvitationContactPhone("");
      setUpdates([]);
      setUpdatesError("");
      setNoticeBody("");
      setNoticeLink("");
      setNoticePhone("");
    }
  }, [applicant?.id]);

  useEffect(() => {
    if (!applicant) return;
    let active = true;
    setUpdatesLoading(true);
    listPlatformApplicantUpdates(applicant.id)
      .then((data) => {
        if (!active) return;
        setUpdates(data);
        // الخادمُ علّم ردودَه مقروءةً عند هذا النداء؛ فلتُطفأ الشارةُ في
        // القائمة أيضاً بدل أن تبقى تصرخ حتى إعادة تحميل الصفحة.
        if (applicant.unread_reply_count > 0) {
          onUpdated({ ...applicant, unread_reply_count: 0 });
        }
      })
      .catch((err: any) => {
        if (active) setUpdatesError(firstApiErrorMessage(err?.data || err, "تعذّر تحميل الرسائل."));
      })
      .finally(() => {
        if (active) setUpdatesLoading(false);
      });
    return () => {
      active = false;
    };
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
      const invitation = await invitePlatformApplicant(applicant.id, {
        expiresInHours: hours,
        note: invitationNote.trim() ? invitationNote : undefined,
        contactPhone: invitationContactPhone.trim() || undefined,
      });
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

  const handleSendNotice = async (event: React.FormEvent) => {
    event.preventDefault();
    setSendingNotice(true);
    try {
      const update = await createPlatformApplicantNotice(applicant.id, {
        body: noticeBody,
        link: noticeLink.trim() || undefined,
        phone: noticePhone.trim() || undefined,
      });
      setUpdates((current) => [...current, update]);
      setNoticeBody("");
      setNoticeLink("");
      setNoticePhone("");
      toast("تم إرسال الرسالة للمتقدّم.", "success");
    } catch (err: any) {
      toast(firstApiErrorMessage(err?.data || err, "تعذّر إرسال الرسالة."), "error");
    } finally {
      setSendingNotice(false);
    }
  };

  const tone = applicantStatusTone(applicant.status);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/60" dir="rtl">
      <div className="relative w-full max-w-xl h-full bg-cc-surface border-r border-cc-border shadow-2xl overflow-y-auto p-6 space-y-6 text-right">
        {/* رأس اللوحة: وجه واسم ورقاقات حالة */}
        <div className="flex items-start justify-between border-b border-cc-border pb-5">
          <div className="flex items-start gap-3">
            <CcAvatar name={applicant.name} size="lg" />
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-bold text-cc-text">{applicant.name}</h2>
                <CcPill tone={tone}>
                  {applicant.status_display}
                </CcPill>
              </div>
              <p className="text-xs text-cc-text-muted mt-1">
                متقدم على وظيفة: <span className="font-semibold text-cc-text">{applicant.job_title}</span>
              </p>
              <div className="flex items-center gap-2 mt-1 font-mono text-[11px] text-cc-text-muted">
                <span>رمز المرجع:</span>
                <span className="text-cc-text font-bold">{applicant.reference_code}</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="إغلاق"
            className="p-1.5 text-cc-text-muted hover:text-cc-text hover:bg-cc-surface-2 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 1. أزرار الانتقال بين الحالات — صفاً واحداً بـ CcSectionTitle */}
        <div className="space-y-3">
          <CcSectionTitle
            title="تحريك حالة المتقدم"
            subtitle="نقل المرشح إلى المرحلة التالية في تدفق التوظيف"
          />

          <div className="rounded-xl bg-cc-surface-2/60 p-4 border border-cc-border">
            {applicant.next_statuses && applicant.next_statuses.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2">
                {applicant.next_statuses.map((next) => {
                  const isThisTransitioning = transitioningTo === next.value;
                  const isReject = next.value === "rejected";

                  return (
                    <button
                      key={next.value}
                      type="button"
                      disabled={transitioningTo !== null}
                      onClick={() => handleTransition(next.value, next.label)}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition shadow-sm disabled:opacity-50 ${
                        isReject
                          ? "bg-rose-500/15 text-rose-400 border border-rose-500/30 hover:bg-rose-500/25"
                          : "bg-sky-600 text-white hover:bg-sky-500"
                      }`}
                    >
                      {isThisTransitioning ? (
                        <span className="flex items-center gap-1.5">
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>جاري النقل...</span>
                        </span>
                      ) : (
                        `الانتقال إلى: ${next.label}`
                      )}
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-cc-text-muted">
                لا توجد انتقالات مسموحة من هذه الحالة حالياً.
              </p>
            )}
          </div>
        </div>

        {/* 2. بيانات المتقدم */}
        <div className="space-y-3">
          <CcSectionTitle title="بيانات الاتصال" />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div className="rounded-xl border border-cc-border bg-cc-surface-2/50 p-3 flex items-center gap-2.5">
              <Phone className="w-4 h-4 text-sky-400 shrink-0" />
              <div>
                <span className="text-[11px] text-cc-text-muted block">الهاتف</span>
                <span dir="ltr" className="font-semibold text-cc-text inline-block">
                  {applicant.phone || "—"}
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-cc-border bg-cc-surface-2/50 p-3 flex items-center gap-2.5">
              <Mail className="w-4 h-4 text-sky-400 shrink-0" />
              <div className="overflow-hidden">
                <span className="text-[11px] text-cc-text-muted block">البريد</span>
                <span className="font-semibold text-cc-text truncate block">
                  {applicant.email || "—"}
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-cc-border bg-cc-surface-2/50 p-3 flex items-center gap-2.5 sm:col-span-2">
              <span className="text-xs font-mono font-bold text-sky-400">#</span>
              <div>
                <span className="text-[11px] text-cc-text-muted block">رمز المرجع</span>
                <span className="font-mono font-semibold text-cc-text">
                  {applicant.reference_code}
                </span>
              </div>
            </div>
          </div>

          {applicant.about && (
            <div className="rounded-xl border border-cc-border bg-cc-surface-2/50 p-3.5 space-y-1">
              <span className="text-xs font-semibold text-cc-text block">
                نبذة عن المتقدم:
              </span>
              <p className="text-xs text-cc-text-muted whitespace-pre-wrap leading-relaxed">
                {applicant.about}
              </p>
            </div>
          )}
        </div>

        {/* 3. الرسائل والتحديثات */}
        <div className="space-y-3">
          <CcSectionTitle title="الرسائل والتحديثات" />

          <CcCard className="p-4 space-y-3">
            {updatesLoading ? (
              <p className="flex items-center gap-2 text-xs text-cc-text-muted">
                <Loader2 className="h-4 w-4 animate-spin" />
                جاري تحميل الرسائل...
              </p>
            ) : updatesError ? (
              <p className="text-xs font-semibold text-rose-400">{updatesError}</p>
            ) : updates.length > 0 ? (
              <ApplicantUpdateThread updates={updates} showAuthorName />
            ) : (
              <p className="text-xs text-cc-text-muted">لا توجد رسائل أو تحديثات بعد.</p>
            )}

            <form onSubmit={handleSendNotice} className="space-y-2 border-t border-cc-border pt-3">
              <label htmlFor="applicant-notice" className="block text-xs font-semibold text-cc-text">
                إرسال رسالة للمتقدّم
              </label>
              <textarea
                id="applicant-notice"
                rows={3}
                maxLength={4000}
                value={noticeBody}
                onChange={(event) => setNoticeBody(event.target.value)}
                placeholder="اكتب نص الرسالة أو التعليمات للمتقدم..."
                className="w-full rounded-lg border border-cc-border bg-cc-surface-2 p-2 text-xs text-cc-text placeholder:text-cc-text-muted outline-none focus:ring-2 focus:ring-sky-500"
              />
              <details className="text-xs text-cc-text-muted">
                <summary className="cursor-pointer font-semibold text-sky-400 hover:text-sky-300">
                  إضافة رابط أو رقم اتصال
                </summary>
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <label className="space-y-1">
                    <span className="block text-[11px]">رابط (اختياري)</span>
                    <input
                      type="url"
                      dir="ltr"
                      value={noticeLink}
                      onChange={(event) => setNoticeLink(event.target.value)}
                      className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-2 py-1.5 text-left text-xs text-cc-text outline-none focus:ring-2 focus:ring-sky-500"
                    />
                  </label>
                  <label className="space-y-1">
                    <span className="block text-[11px]">رقم هاتف (اختياري)</span>
                    <input
                      type="tel"
                      dir="ltr"
                      value={noticePhone}
                      onChange={(event) => setNoticePhone(event.target.value)}
                      className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-2 py-1.5 text-left text-xs text-cc-text outline-none focus:ring-2 focus:ring-sky-500"
                    />
                  </label>
                </div>
              </details>
              <button
                type="submit"
                disabled={sendingNotice || !noticeBody.trim()}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-sky-600 px-4 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50 transition"
              >
                {sendingNotice ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                <span>إرسال الرسالة</span>
              </button>
            </form>
          </CcCard>
        </div>

        {/* 4. السيرة الذاتية */}
        <div className="space-y-3">
          <CcSectionTitle title="السيرة الذاتية" />

          <CcCard className="p-4">
            {applicant.has_cv ? (
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs text-cc-text">
                  <FileText className="w-4 h-4 text-sky-400" />
                  <span>{applicant.cv_name || "ملف السيرة الذاتية"}</span>
                </div>
                <button
                  type="button"
                  onClick={handleOpenCv}
                  disabled={openingCv}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-sky-400 bg-sky-500/15 hover:bg-sky-500/25 rounded-lg border border-sky-500/30 transition disabled:opacity-50"
                >
                  {openingCv ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                  <span>فتح السيرة</span>
                </button>
              </div>
            ) : (
              <p className="text-xs text-cc-text-muted">
                لم يرفق المتقدم ملف سيرة ذاتية.
              </p>
            )}
          </CcCard>
        </div>

        {/* 5. قسم الدعوة: يظهر فقط حين status === "offered" ولا يوجد hired_employee */}
        {applicant.status === "offered" && !applicant.hired_employee && (
          <div className="space-y-3">
            <CcSectionTitle title="إصدار رابط دعوة المرشح" />

            <CcCard tone="warning" className="p-4 space-y-3">
              <p className="text-xs text-amber-300 leading-relaxed">
                المرشح في حالة «عرض عمل». يمكنك إصدار رابط دعوة قبول التوظيف لمشاركته معه لإنشاء حسابه بنفسه.
              </p>

              <div className="flex flex-wrap items-center gap-3">
                <label className="text-xs font-semibold text-cc-text whitespace-nowrap">
                  الصلاحية بالساعات:
                </label>
                <input
                  type="number"
                  min={1}
                  max={168}
                  value={expiresInHours}
                  onChange={(e) => setExpiresInHours(e.target.value)}
                  className="w-24 rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-xs text-cc-text focus:ring-2 focus:ring-amber-500 outline-none"
                />
              </div>

              <div>
                <label htmlFor="invitation-note" className="mb-1 block text-xs font-semibold text-cc-text">
                  رسالة للمرشح قبل إنشاء الحساب (اختيارية)
                </label>
                <textarea
                  id="invitation-note"
                  rows={3}
                  value={invitationNote}
                  onChange={(event) => setInvitationNote(event.target.value)}
                  placeholder="اكتب توضيحاً أو تعليمات سيقرأها المرشح قبل قبول الدعوة..."
                  className="w-full rounded-lg border border-cc-border bg-cc-surface-2 p-2 text-xs text-cc-text placeholder:text-cc-text-muted outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div>
                <label htmlFor="invitation-contact-phone" className="mb-1 block text-xs font-semibold text-cc-text">
                  رقم التواصل للاستفسارات قبل القبول (اختياري)
                </label>
                <input
                  id="invitation-contact-phone"
                  type="tel"
                  dir="ltr"
                  value={invitationContactPhone}
                  onChange={(event) => setInvitationContactPhone(event.target.value)}
                  placeholder="+970000000000"
                  className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-1.5 text-left text-xs text-cc-text outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <button
                type="button"
                onClick={handleIssueInvite}
                disabled={issuingInvite}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-amber-500 disabled:opacity-50"
              >
                {issuingInvite && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>إصدار رابط الدعوة</span>
              </button>

              {issuedInvitation && (
                <div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-emerald-400">
                      رابط الدعوة المُصدَر:
                    </span>
                    <button
                      type="button"
                      onClick={handleCopyInviteUrl}
                      className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-emerald-300 bg-emerald-500/20 rounded-md border border-emerald-500/40 hover:bg-emerald-500/30 transition"
                    >
                      <Copy className="w-3.5 h-3.5" />
                      <span>نسخ الرابط</span>
                    </button>
                  </div>
                  <div className="font-mono text-xs text-cc-text break-all p-2 rounded-lg bg-cc-surface-2 border border-cc-border">
                    {issuedInvitation.invite_url}
                  </div>
                  <p className="text-[11px] font-semibold text-emerald-400">
                    احفظه الآن — لا يمكن عرضه مرّةً أخرى، وإصدارُ رابطٍ جديد يُبطل هذا.
                  </p>
                  {((issuedInvitation.note || "").trim() || (issuedInvitation.contact_phone || "").trim()) && (
                    <div className="space-y-2 border-t border-emerald-500/20 pt-2">
                      <p className="text-[11px] font-bold text-emerald-300">ما سيقرأه المرشح قبل إنشاء حسابه:</p>
                      {(issuedInvitation.note || "").trim() && (
                        <p className="whitespace-pre-wrap text-xs leading-relaxed text-cc-text-muted">
                          {issuedInvitation.note}
                        </p>
                      )}
                      {(issuedInvitation.contact_phone || "").trim() && (
                        <p className="text-xs text-cc-text-muted">
                          رقم التواصل: <a href={`tel:${(issuedInvitation.contact_phone || "").trim()}`} dir="ltr" className="font-semibold text-emerald-400 underline hover:text-emerald-300">{(issuedInvitation.contact_phone || "").trim()}</a>
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </CcCard>
          </div>
        )}

        {/* 6. التقييم والملاحظات */}
        <div className="space-y-3">
          <CcSectionTitle title="تقييم مسؤول التوظيف" />

          <CcCard className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-cc-text">
                الدرجة والتقييم بالنجوم
              </span>
              <span className="text-xs text-cc-text-muted">
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
                  className="p-1 text-amber-400 hover:scale-110 transition focus:outline-none"
                  title={`تقييم ${starNum}`}
                >
                  <Star
                    className={`w-6 h-6 ${
                      starNum <= rating ? "fill-amber-400 text-amber-400" : "text-cc-border"
                    }`}
                  />
                </button>
              ))}
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-cc-text-muted mb-1">
                ملاحظات مسؤول التوظيف
              </label>
              <textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="انطباع المقابلة، نقاط القوة، الملاحظات الإدارية..."
                className="w-full rounded-lg border border-cc-border bg-cc-surface-2 p-2 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <button
              type="button"
              onClick={handleSaveRating}
              disabled={savingRating}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg shadow-sm transition disabled:opacity-50"
            >
              {savingRating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>حفظ التقييم والملاحظات</span>
            </button>
          </CcCard>
        </div>
      </div>
    </div>
  );
};
