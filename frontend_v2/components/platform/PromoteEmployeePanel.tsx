import React, { useCallback, useEffect, useState } from "react";
import { Loader2, UserPlus } from "lucide-react";

import { useToast } from "../../contexts/ToastContext";
import {
  listPolicyProfileOptions,
  promoteUserToPlatformEmployee,
  type PolicyProfileOption,
} from "../../services/platformHiringApi";
import { firstApiErrorMessage } from "../../utils/platformHiring";

interface PromoteEmployeePanelProps {
  /** يُنادى بعد ضمٍّ ناجحٍ كي تُعيد اللوحةُ تحميلَ فريقها. */
  onPromoted: () => void;
}

/**
 * «اجعله موظّفَ منصّة» — البابُ الثاني إلى الفريق (212-Q4).
 *
 * كان الطريقُ الوحيدُ إلى صفِّ `PlatformEmployee` هو قبولُ دعوةِ توظيف: إعلانٌ
 * ← متقدّمٌ ← دعوةٌ بمهلة ← قبولٌ يُنشئ الحسابَ والصفَّ معاً. فمن له حسابٌ على
 * المنصّة أصلاً لا يُضَمُّ إلّا باختلاق إعلانٍ وهميٍّ ودعوةٍ لنفسه.
 *
 * **والتعريفُ بالاسم أو البريد لا بالمعرّف** — بنمط `PlatformRecruitersTab`:
 * المديرُ يعرف زميلَه باسمه، ولا شاشةَ في النظام تسرد مستخدمي المنصّة كلَّهم،
 * ولا يُفتَح سردٌ كهذا لأجل زرّ.
 *
 * **والتخصّصُ يُختار من ملفّات السياسة القائمة لا يُكتب حرّاً**: يُطابَق
 * بـ`PolicyProfile.specialty` في احتساب الأداء، ودرجةُ الأداء مالٌ في المحفظة —
 * فنصٌّ حرٌّ لا يطابق شيئاً يعني تقييماً بسياسةٍ افتراضيّةٍ بلا أن يلاحظ أحد.
 */
export const PromoteEmployeePanel: React.FC<PromoteEmployeePanelProps> = ({ onPromoted }) => {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [identifier, setIdentifier] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [profiles, setProfiles] = useState<PolicyProfileOption[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const loadProfiles = useCallback(async () => {
    try {
      setProfiles(await listPolicyProfileOptions());
    } catch {
      // فشلُ قائمة التخصّصات لا يُقفل البابَ: الحقلُ اختياريٌّ ويُضبَط لاحقاً
      // من درج الملفّ، والضمُّ نفسُه أهمُّ من زينته.
      setProfiles([]);
    }
  }, []);

  useEffect(() => {
    if (open) void loadProfiles();
  }, [open, loadProfiles]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = identifier.trim();
    if (!value) {
      setError("اكتب اسم المستخدم أو بريده الإلكتروني.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const employee = await promoteUserToPlatformEmployee(value, {
        specialty: specialty || undefined,
        job_title: jobTitle.trim() || undefined,
      });
      // «أُعيد» لا «أُضيف» لمن كان في الفريق وغادر: من يقرأ تاريخَه لا يظنّه جديداً.
      toast(
        employee.created
          ? `${employee.username} صار موظّفَ منصّة.`
          : `${employee.username} أُعيد إلى فريق المنصّة.`,
        "success",
      );
      setIdentifier("");
      setSpecialty("");
      setJobTitle("");
      setOpen(false);
      onPromoted();
    } catch (cause: unknown) {
      setError(
        firstApiErrorMessage(
          (cause as { data?: unknown })?.data || cause,
          "تعذّر ضمُّ المستخدم إلى فريق المنصّة.",
        ),
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mb-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-xs font-bold text-white hover:bg-blue-700"
      >
        <UserPlus className="h-4 w-4" />
        اجعله موظّف منصّة
      </button>
    );
  }

  return (
    <section className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm" dir="rtl">
      <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800">
        <UserPlus className="h-4 w-4" />
        ضمُّ مستخدمٍ مسجَّلٍ إلى فريق المنصّة
      </h3>
      <p className="mt-0.5 text-xs text-slate-400">
        يرفع الدورَ على حسابٍ قائمٍ ولا يُنشئ حساباً — إنشاءُ الحسابات بابُه دعوةُ التوظيف حيث يختار صاحبُها
        كلمةَ مروره. ومن كان في الفريق وغادر يعود إلى صفّه نفسِه بتاريخه كلِّه.
      </p>

      {error && (
        <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs font-semibold text-rose-700" role="alert">
          {error}
        </p>
      )}

      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-semibold text-slate-700">
          اسم المستخدم أو بريده
          <input
            type="text"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            placeholder="مثال: nour أو nour@ktra.local"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>
        <label className="text-xs font-semibold text-slate-700">
          التخصّص (سياسةُ تقييمه)
          <select
            value={specialty}
            onChange={(event) => setSpecialty(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">بلا تخصّص — يُضبط لاحقاً</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.specialty}>
                {profile.name} · {profile.specialty}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-semibold text-slate-700">
          المسمّى الوظيفي (عرضٌ فقط)
          <input
            type="text"
            value={jobTitle}
            onChange={(event) => setJobTitle(event.target.value)}
            placeholder="اختياري"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>
        <div className="flex items-end gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
            {submitting ? "جارٍ الضمّ..." : "ضُمَّه إلى الفريق"}
          </button>
          <button
            type="button"
            onClick={() => { setOpen(false); setError(""); }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700"
          >
            إلغاء
          </button>
        </div>
      </form>
    </section>
  );
};

export default PromoteEmployeePanel;
