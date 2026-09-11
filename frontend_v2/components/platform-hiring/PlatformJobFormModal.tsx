import React, { useEffect, useState } from "react";
import { X, Loader2 } from "lucide-react";

import {
  createPlatformJob,
  listPolicyProfileOptions,
  updatePlatformJob,
  type PlatformJobPosting,
  type PlatformJobPostingDraft,
  type PolicyProfileOption,
} from "../../services/platformHiringApi";
import { dateTimeLocalToIso, isoToDateTimeLocal } from "../../utils/dateTimeLocal";
import { EMPLOYMENT_TYPE_OPTIONS, firstApiErrorMessage } from "../../utils/platformHiring";

interface PlatformJobFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  jobToEdit: PlatformJobPosting | null;
  canListPolicyProfiles: boolean;
  onSaved: (job: PlatformJobPosting) => void;
}

const EMPLOYMENT_TYPES = [
  { value: "", label: "غير محدد" },
  ...EMPLOYMENT_TYPE_OPTIONS,
];

export const PlatformJobFormModal: React.FC<PlatformJobFormModalProps> = ({
  isOpen,
  onClose,
  jobToEdit,
  canListPolicyProfiles,
  onSaved,
}) => {
  const [title, setTitle] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [description, setDescription] = useState("");
  const [requirements, setRequirements] = useState("");
  const [location, setLocation] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [salaryRange, setSalaryRange] = useState("");
  const [expiresAtLocal, setExpiresAtLocal] = useState("");

  const [policyProfiles, setPolicyProfiles] = useState<PolicyProfileOption[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!isOpen) return;

    if (jobToEdit) {
      setTitle(jobToEdit.title || "");
      setSpecialty(jobToEdit.specialty || "");
      setDescription(jobToEdit.description || "");
      setRequirements(jobToEdit.requirements || "");
      setLocation(jobToEdit.location || "");
      setEmploymentType(jobToEdit.employment_type || "");
      setSalaryRange(jobToEdit.salary_range || "");
      setExpiresAtLocal(isoToDateTimeLocal(jobToEdit.expires_at));
    } else {
      setTitle("");
      setSpecialty("");
      setDescription("");
      setRequirements("");
      setLocation("");
      setEmploymentType("");
      setSalaryRange("");
      setExpiresAtLocal("");
    }
    setErrorMessage("");
  }, [isOpen, jobToEdit]);

  useEffect(() => {
    if (isOpen && canListPolicyProfiles) {
      listPolicyProfileOptions()
        .then((profiles) => setPolicyProfiles(profiles))
        .catch(() => setPolicyProfiles([]));
    }
  }, [isOpen, canListPolicyProfiles]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMessage("عنوان الوظيفة إلزامي.");
      return;
    }
    if (!description.trim()) {
      setErrorMessage("وصف الوظيفة إلزامي.");
      return;
    }

    setSubmitting(true);
    setErrorMessage("");

    const draft: PlatformJobPostingDraft = {
      title: title.trim(),
      specialty: specialty.trim(),
      description: description.trim(),
      requirements: requirements.trim(),
      location: location.trim(),
      employment_type: employmentType,
      salary_range: salaryRange.trim(),
      expires_at: dateTimeLocalToIso(expiresAtLocal),
    };

    try {
      let saved: PlatformJobPosting;
      if (jobToEdit) {
        saved = await updatePlatformJob(jobToEdit.id, draft);
      } else {
        saved = await createPlatformJob(draft);
      }
      onSaved(saved);
      onClose();
    } catch (err: any) {
      setErrorMessage(firstApiErrorMessage(err?.data || err, "تعذر حفظ إعلان الوظيفة."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4" dir="rtl">
      <div className="relative w-full max-w-2xl rounded-2xl bg-white dark:bg-slate-900 p-6 shadow-2xl border border-slate-200 dark:border-slate-800 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-4 mb-5">
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            {jobToEdit ? "تعديل إعلان الوظيفة" : "إعلان وظيفة جديدة"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="إغلاق"
            className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {errorMessage && (
          <div className="mb-4 rounded-lg bg-rose-50 dark:bg-rose-950/40 p-3 text-xs font-semibold text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
            {errorMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-sm text-slate-800 dark:text-slate-200">
          <div>
            <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
              عنوان الوظيفة <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder="مثال: مهندس عمليات منصية"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
              التخصص المنصي
            </label>
            <input
              type="text"
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              list={canListPolicyProfiles ? "policy-profiles-list" : undefined}
              placeholder="مثال: operations أو data_entry"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {canListPolicyProfiles && (
              <datalist id="policy-profiles-list">
                {policyProfiles.map((p) => (
                  <option key={p.id} value={p.specialty}>
                    {p.name}
                  </option>
                ))}
              </datalist>
            )}
            <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
              الموظف المقبول يرث هذا التخصص ليُطابق بملف سياسة أداء لحساب نقاطه.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
                نوع التوظيف
              </label>
              <select
                value={employmentType}
                onChange={(e) => setEmploymentType(e.target.value)}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {EMPLOYMENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
                الموقع
              </label>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="مثال: عن بعد أو رام الله"
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
                نطاق الراتب
              </label>
              <input
                type="text"
                value={salaryRange}
                onChange={(e) => setSalaryRange(e.target.value)}
                placeholder="مثال: 4000 - 6000 ₪"
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
                تاريخ انتهاء الإعلان
              </label>
              <input
                type="datetime-local"
                value={expiresAtLocal}
                onChange={(e) => setExpiresAtLocal(e.target.value)}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                اتركه فارغاً لإعلان دائم لا ينتهي تلقائياً.
              </p>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
              وصف الوظيفة <span className="text-rose-500">*</span>
            </label>
            <textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              placeholder="وصف المهام والمسؤوليات الأساسية..."
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold mb-1 text-slate-700 dark:text-slate-300">
              المتطلبات
            </label>
            <textarea
              rows={3}
              value={requirements}
              onChange={(e) => setRequirements(e.target.value)}
              placeholder="الخبرات والمهارات المطلوبة..."
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition"
            >
              إلغاء
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center gap-2 px-5 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow transition disabled:opacity-50"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              {jobToEdit ? "حفظ التعديلات" : "إنشاء الإعلان"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
