/**
 * نافذة «مشاركة المستند» — نقطة إنشاء الرابط العام ونسخه وإبطاله.
 *
 * مكوّن واحد يخدم كل أنواع المستندات: النوع خاصية لا فرع في الكود، فإضافة
 * الصفقة أو سند القبض لاحقاً لا تفتح هذا الملف — يكفي أن يعرفها الخادم.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Copy, Link2, RotateCcw, ShieldOff, X } from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  DEFAULT_SHARE_EXPIRY_DAYS,
  SHARE_EXPIRY_OPTIONS,
  createDocumentShare,
  listDocumentShares,
  revokeDocumentShare,
  whatsappShareUrl,
  type DocumentShare,
  type ShareDocType,
} from "../../services/docShareApi";
import { formatDateTimeValue, formatDateValue } from "../../utils/formatDate";

export interface ShareDocumentModalProps {
  open: boolean;
  onClose: () => void;
  docType: ShareDocType;
  docId: number;
  /** «فاتورة بيع 2026-114» — يظهر في العنوان وفي نصّ رسالة واتساب. */
  docLabel: string;
  /** اسم الزبون، لتحية الرسالة. اختياري. */
  partyName?: string;
  tenantId?: number;
  /** مسودة عرض سعر: المشاركة تُرسله فعلياً — والنافذة تقول ذلك قبل الضغط. */
  warnDraftWillBeSent?: boolean;
  /** يُستدعى بعد إنشاء أول رابط، ليُحدِّث المستدعي حالة المستند لديه. */
  onShared?: (share: DocumentShare) => void;
}

const CARD = "rounded-lg border border-slate-200 bg-white";

export const ShareDocumentModal: React.FC<ShareDocumentModalProps> = ({
  open,
  onClose,
  docType,
  docId,
  docLabel,
  partyName,
  tenantId,
  warnDraftWillBeSent = false,
  onShared,
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [share, setShare] = useState<DocumentShare | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [days, setDays] = useState<number>(DEFAULT_SHARE_EXPIRY_DAYS);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await listDocumentShares(docType, docId, tenantId);
      setShare(rows.find((row) => row.is_live) ?? null);
    } catch {
      // القراءة الفاشلة ليست خطأً يُصرخ به: النافذة تُعرض فارغة وزر الإنشاء
      // يبقى متاحاً، فالمستخدم لا يعلق أمام رسالة لا يملك إزاءها شيئاً.
      setShare(null);
    } finally {
      setLoading(false);
    }
  }, [docType, docId, tenantId]);

  useEffect(() => {
    if (!open) return;
    setShare(null);
    setDays(DEFAULT_SHARE_EXPIRY_DAYS);
    void load();
  }, [open, load]);

  if (!open) return null;

  const message = `${docLabel}${partyName ? ` — ${partyName}` : ""}\n${share?.public_url ?? ""}`;

  const handleCreate = async () => {
    setBusy(true);
    try {
      const created = await createDocumentShare(docType, docId, days, tenantId);
      setShare(created);
      onShared?.(created);
      toast("تم إنشاء الرابط", "success");
    } catch (error: any) {
      toast(error?.message || "تعذّر إنشاء الرابط", "error");
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    if (!share) return;
    try {
      await navigator.clipboard.writeText(share.public_url);
      toast("نُسخ الرابط", "success");
    } catch {
      // متصفّح بلا صلاحية حافظة (http أو iframe) — الحقل قابل للتحديد يدوياً،
      // فالمستخدم لا يعلق بلا مخرج.
      toast("انسخ الرابط يدوياً من الحقل", "info");
    }
  };

  const handleRevoke = async () => {
    if (!share) return;
    const ok = await confirm({
      title: "إبطال الرابط",
      message:
        "سيتوقف الرابط عن العمل فوراً لكل من يملكه. يمكنك إنشاء رابط جديد بعدها.",
      confirmText: "إبطال",
      danger: true,
    });
    if (!ok) return;

    setBusy(true);
    try {
      await revokeDocumentShare(share.id, tenantId);
      setShare(null);
      toast("أُبطل الرابط", "success");
    } catch (error: any) {
      toast(error?.message || "تعذّر إبطال الرابط", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="مشاركة المستند"
    >
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="flex items-center gap-2 text-base font-bold text-slate-800">
            <Link2 className="h-4 w-4 text-blue-700" />
            مشاركة {docLabel}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          {loading ? (
            <p className="py-6 text-center text-sm text-slate-500">جارٍ التحميل…</p>
          ) : share ? (
            <>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500">
                  الرابط العام
                </label>
                <div className="flex gap-2">
                  <input
                    readOnly
                    dir="ltr"
                    value={share.public_url}
                    onFocus={(event) => event.currentTarget.select()}
                    className="flex-1 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700"
                  />
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 rounded-lg bg-blue-700 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-800"
                  >
                    <Copy className="h-4 w-4" />
                    نسخ
                  </button>
                </div>
              </div>

              <a
                href={whatsappShareUrl(message)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-700"
              >
                إرسال عبر واتساب
              </a>

              <div className={`${CARD} px-4 py-3 text-sm`}>
                <div className="flex justify-between py-0.5">
                  <span className="text-slate-500">صالح حتى</span>
                  <span className="font-semibold text-slate-700">
                    {formatDateValue(share.expires_at)}
                  </span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span className="text-slate-500">المشاهدات</span>
                  <span className="font-semibold text-slate-700">
                    {share.view_count === 0
                      ? "لم يُفتح بعد"
                      : `${share.view_count} · آخرها ${formatDateTimeValue(share.last_viewed_at)}`}
                  </span>
                </div>
                {share.decision ? (
                  <>
                    <div className="flex justify-between py-0.5">
                      {/* «الزبون» صارت «المستلم»: نصفُ الأنواع طرفُها مورّد. */}
                      <span className="text-slate-500">قرار المستلم</span>
                      <span
                        className={
                          share.decision === "accepted"
                            ? "font-semibold text-emerald-700"
                            : "font-semibold text-red-700"
                        }
                      >
                        {share.decision === "accepted" ? "موافق" : "مرفوض"} — {share.decided_name}
                      </span>
                    </div>
                    {/* السبب هو ما يمنع مكالمةً ليعرف الموظف «لماذا رفضوا». */}
                    {share.decided_note ? (
                      <div className="py-0.5 text-slate-600">
                        السبب: {share.decided_note}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>

              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={handleRevoke}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
                >
                  <ShieldOff className="h-4 w-4" />
                  إبطال الرابط
                </button>
                <button
                  type="button"
                  onClick={() => void load()}
                  disabled={busy}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  <RotateCcw className="h-4 w-4" />
                  تحديث الحالة
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-slate-600">
                رابط يفتحه الزبون على أي جهاز فيرى المستند ويحمّله PDF ويطبعه — بلا
                حساب وبلا تطبيق.
              </p>

              {warnDraftWillBeSent ? (
                <p className={`${CARD} border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800`}>
                  هذا العرض ما زال مسودة — إنشاء الرابط يعني إرساله، وستصير حالته
                  «أُرسل» ليصير القبول من الزبون ممكناً.
                </p>
              ) : null}

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500">
                  مدة الصلاحية
                </label>
                <div className="flex gap-2">
                  {SHARE_EXPIRY_OPTIONS.map((option) => (
                    <button
                      key={option.days}
                      type="button"
                      onClick={() => setDays(option.days)}
                      className={
                        option.days === days
                          ? "flex-1 rounded-lg border border-blue-700 bg-blue-50 px-3 py-2 text-sm font-bold text-blue-800"
                          : "flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                      }
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={handleCreate}
                disabled={busy}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-blue-800 disabled:opacity-50"
              >
                <Link2 className="h-4 w-4" />
                {busy ? "جارٍ الإنشاء…" : "إنشاء رابط المشاركة"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
