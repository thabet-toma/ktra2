import React, { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw, ShieldAlert, UserCheck, UserMinus, UserPlus } from "lucide-react";

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
      {/* بطاقة نموذج إسناد الدور */}
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm space-y-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            إسناد دور مسؤول التوظيف المنصي
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            يمنح المستخدم صلاحية الوصول لشاشة التوظيف ومتابعة إعلانات الوظائف والطلبات دون منحه أي صلاحيات أخرى على المنصة.
          </p>
        </div>

        {formError && (
          <div className="rounded-lg bg-rose-50 dark:bg-rose-950/40 p-2.5 text-xs font-semibold text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
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
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={submitting || !identifier.trim()}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition disabled:opacity-50"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserCheck className="w-4 h-4" />}
            إسناد الدور
          </button>
        </form>
      </div>

      {/* جدول مسؤولي التوظيف */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
            قائمة مسؤولي التوظيف ({formatNumber(recruiters.length)})
          </span>
          <button
            type="button"
            onClick={() => void loadRecruiters()}
            disabled={loading}
            className="p-1 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 rounded hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            title="تحديث القائمة"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
          <table className="w-full text-right text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="p-3">الاسم الكامل</th>
                <th className="p-3">اسم المستخدم</th>
                <th className="p-3">البريد الإلكتروني</th>
                <th className="p-3">الحالة</th>
                <th className="p-3">تاريخ الإسناد</th>
                <th className="p-3 text-center">الإجراءات</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-slate-800 dark:text-slate-200">
              {recruiters.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-400 dark:text-slate-500">
                    {loading ? "جاري تحميل المسؤولين..." : "لم يتم إسناد دور مسؤول توظيف لأي مستخدم بعد."}
                  </td>
                </tr>
              ) : (
                recruiters.map((rec) => (
                  <tr key={rec.id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition">
                    <td className="p-3 font-semibold text-slate-900 dark:text-slate-100">
                      {rec.full_name || rec.username}
                    </td>
                    <td className="p-3 font-mono text-slate-600 dark:text-slate-400">
                      {rec.username}
                    </td>
                    <td className="p-3 text-slate-600 dark:text-slate-400">
                      {rec.email || "—"}
                    </td>
                    <td className="p-3">
                      {rec.is_active ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
                          نشط
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-600 border border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700">
                          ملغى
                        </span>
                      )}
                    </td>
                    <td className="p-3 text-slate-500 dark:text-slate-400">
                      {formatDateValue(rec.created_at)}
                    </td>
                    <td className="p-3 text-center">
                      {rec.is_active && (
                        <button
                          type="button"
                          onClick={() => handleRevoke(rec)}
                          disabled={revokingId === rec.id}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-300 dark:hover:bg-rose-900/60 rounded border border-rose-200 dark:border-rose-800 transition disabled:opacity-50"
                        >
                          <UserMinus className="w-3 h-3" />
                          إلغاء الدور
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
