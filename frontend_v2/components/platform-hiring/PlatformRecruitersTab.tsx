import React, { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, UserCheck, UserMinus, UserPlus } from "lucide-react";

import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import {
  assignPlatformRecruiter,
  listPlatformRecruiters,
  revokePlatformRecruiter,
  type PlatformRecruiter,
} from "../../services/platformHiringApi";
import { formatDateValue } from "../../utils/formatDate";
import { formatNumber } from "../../utils/formatNumber";
import { firstApiErrorMessage } from "../../utils/platformHiring";
import {
  CcAvatar,
  CcCard,
  CcEmpty,
  CcPill,
  CcTable,
  CcTd,
  CcTh,
  CcThead,
  CcTr,
} from "../platform/ui";

export const PlatformRecruitersTab: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();

  const [recruiters, setRecruiters] = useState<PlatformRecruiter[]>([]);
  const [loading, setLoading] = useState(false);

  const [identifier, setIdentifier] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  const [revokingId, setRevokingId] = useState<number | null>(null);

  const loadRecruiters = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listPlatformRecruiters();
      setRecruiters(data);
    } catch (err: any) {
      toast(firstApiErrorMessage(err?.data || err, "تعذر تحميل مسؤولي التوظيف."), "error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void loadRecruiters();
  }, [loadRecruiters]);

  const handleAssign = async (e: React.FormEvent) => {
    e.preventDefault();
    const idf = identifier.trim();
    if (!idf) {
      setFormError("اكتب اسم المستخدم أو بريده الإلكتروني.");
      return;
    }

    setSubmitting(true);
    setFormError("");
    try {
      await assignPlatformRecruiter(idf);
      toast("تم إسناد دور مسؤول التوظيف بنجاح.", "success");
      setIdentifier("");
      await loadRecruiters();
    } catch (err: any) {
      setFormError(firstApiErrorMessage(err?.data || err, "تعذر إسناد دور مسؤول التوظيف."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevoke = async (recruiter: PlatformRecruiter) => {
    const displayName = recruiter.full_name || recruiter.username;
    const ok = await confirm({
      title: "إلغاء دور مسؤول التوظيف",
      message: `هل أنت متأكد من إلغاء دور مسؤول التوظيف عن «${displayName}»؟ سيتوقف وصوله فوراً لشاشة التوظيف (يمكن إعادة إسناد الدور له لاحقاً).`,
      confirmText: "إلغاء الدور",
      danger: true,
    });
    if (!ok) return;

    setRevokingId(recruiter.id);
    try {
      await revokePlatformRecruiter(recruiter.id);
      toast("تم إلغاء دور مسؤول التوظيف.", "success");
      await loadRecruiters();
    } catch (err: any) {
      toast(firstApiErrorMessage(err?.data || err, "تعذر إلغاء الدور."), "error");
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div className="space-y-6 text-right" dir="rtl">
      {/* بطاقة نموذج إسناد الدور بـ CcCard */}
      <CcCard className="p-5 space-y-4">
        <div>
          <h3 className="text-sm font-bold text-cc-text flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-sky-400" />
            إسناد دور مسؤول التوظيف المنصي
          </h3>
          <p className="text-xs text-cc-text-muted mt-1">
            يمنح المستخدم صلاحية الوصول لشاشة التوظيف ومتابعة إعلانات الوظائف والطلبات دون منحه أي صلاحيات أخرى على المنصة.
          </p>
        </div>

        {formError && (
          <div className="rounded-lg bg-rose-500/10 p-3 text-xs font-semibold text-rose-300 border border-rose-500/30">
            {formError}
          </div>
        )}

        <form onSubmit={handleAssign} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="flex-1">
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="اسم المستخدم أو البريد الإلكتروني للموظف..."
              className="w-full rounded-lg border border-cc-border bg-cc-surface-2 px-3 py-2 text-xs text-cc-text placeholder:text-cc-text-muted focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>
          <button
            type="submit"
            disabled={submitting || !identifier.trim()}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-500 rounded-lg shadow-sm transition disabled:opacity-50"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserCheck className="w-4 h-4" />}
            <span>إسناد الدور</span>
          </button>
        </form>
      </CcCard>

      {/* جدول مسؤولي التوظيف بـ CcTable و CcAvatar */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-cc-text">
            قائمة مسؤولي التوظيف ({formatNumber(recruiters.length)})
          </span>
          <button
            type="button"
            onClick={() => void loadRecruiters()}
            disabled={loading}
            className="p-1.5 text-cc-text-muted hover:text-cc-text rounded-lg hover:bg-cc-surface-2 transition"
            title="تحديث القائمة"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        <CcTable>
          <CcThead>
            <tr>
              <CcTh>الاسم الكامل</CcTh>
              <CcTh>اسم المستخدم</CcTh>
              <CcTh>البريد الإلكتروني</CcTh>
              <CcTh>الحالة</CcTh>
              <CcTh>تاريخ الإسناد</CcTh>
              <CcTh className="text-center">الإجراءات</CcTh>
            </tr>
          </CcThead>
          <tbody>
            {recruiters.length === 0 ? (
              <tr>
                <CcTd colSpan={6} className="p-8 text-center">
                  {loading ? (
                    <div className="flex items-center justify-center gap-2 text-xs text-cc-text-muted">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>جاري تحميل المسؤولين...</span>
                    </div>
                  ) : (
                    <CcEmpty
                      title="لم يتم إسناد دور مسؤول توظيف لأي مستخدم بعد"
                      hint="أدخل اسم مستخدم أو بريده في النموذج أعلاه لمنحه صلاحيات التوظيف."
                    />
                  )}
                </CcTd>
              </tr>
            ) : (
              recruiters.map((rec) => (
                <CcTr key={rec.id}>
                  <CcTd className="font-semibold">
                    <div className="flex items-center gap-2.5">
                      <CcAvatar name={rec.full_name || rec.username} size="sm" />
                      <span className="text-cc-text">{rec.full_name || rec.username}</span>
                    </div>
                  </CcTd>
                  <CcTd className="font-mono text-cc-text-muted text-xs">
                    @{rec.username}
                  </CcTd>
                  <CcTd className="text-cc-text-muted text-xs">
                    {rec.email || "—"}
                  </CcTd>
                  <CcTd>
                    <CcPill tone={rec.is_active ? "success" : "neutral"} dot>
                      {rec.is_active ? "نشط" : "ملغى"}
                    </CcPill>
                  </CcTd>
                  <CcTd className="text-cc-text-muted text-xs">
                    {formatDateValue(rec.created_at)}
                  </CcTd>
                  <CcTd className="text-center">
                    {rec.is_active && (
                      <button
                        type="button"
                        onClick={() => handleRevoke(rec)}
                        disabled={revokingId === rec.id}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-rose-400 bg-rose-500/10 hover:bg-rose-500/20 rounded-md border border-rose-500/30 transition disabled:opacity-50"
                      >
                        <UserMinus className="w-3 h-3" />
                        <span>إلغاء الدور</span>
                      </button>
                    )}
                  </CcTd>
                </CcTr>
              ))
            )}
          </tbody>
        </CcTable>
      </div>
    </div>
  );
};
