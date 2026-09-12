import React, { useRef, useState } from "react";
import { Camera, Loader2, Pencil, Phone } from "lucide-react";

import {
  setEmployeeProfileCard,
  uploadEmployeePhoto,
} from "../../services/platformEmployeeProfileApi";
import type { MyPlatformEmployeeProfile } from "../../services/platformEmployeeSpaceApi";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useToast } from "../../contexts/ToastContext";

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "؟";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[1][0]}`;
}

interface MyProfileCardProps {
  profile: MyPlatformEmployeeProfile;
  /** يُستدعى بعد حفظٍ ناجح ليُعيد المُستضيفُ تحميلَ ملفّه. */
  onSaved: () => void;
}

/**
 * بطاقةُ الموظّف في مساحته هو (211-Q): صورتُه وهاتفُه **يضبطهما بنفسه**.
 *
 * **ولماذا هنا لا في درج المدير**: الخادمُ يسمح لصاحب الصفّ بـ`photo_url`
 * و`phone` دون `job_title` — المسمّى تعيينُ صاحب العمل ويظهر على لوحة الفريق،
 * أمّا وجهُه ورقمُه فبياناتُه. ودرجُ الملفّ الـ360 يُفتح من لوحة المدير وحدَها،
 * فلولا هذه البطاقةُ لبقي ذلك الإذنُ الخادميُّ **باباً بلا طارق**: صورةُ الموظّف
 * لا يرفعها إلاّ مديرُه، وهي أوّلُ ما يظهر على مقعده في الغرفة.
 */
export const MyProfileCard: React.FC<MyProfileCardProps> = ({ profile, onSaved }) => {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [phone, setPhone] = useState(profile.phone);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const displayName = profile.username;

  const savePhone = async () => {
    const trimmed = phone.trim();
    if (trimmed === profile.phone) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await setEmployeeProfileCard(profile.id, { phone: trimmed });
      toast("حُفظ رقمُك.", "success");
      setEditing(false);
      onSaved();
    } catch (cause) {
      toast(describePlatformOpsError(cause, "لا تصريح لك بتعديل هذه البطاقة.", "تعذّر حفظ الرقم."), "error");
    } finally {
      setSaving(false);
    }
  };

  const pickPhoto = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await uploadEmployeePhoto(profile.id, file);
      toast("حُفظت صورتُك.", "success");
      onSaved();
    } catch (cause) {
      toast(describePlatformOpsError(cause, "لا تصريح لك برفع صورةٍ لهذه البطاقة.", "تعذّر رفع الصورة."), "error");
    } finally {
      setUploading(false);
    }
  };

  return (
    <section className="mb-6 rounded-xl border border-slate-200 bg-white p-4" dir="rtl">
      <div className="flex items-start gap-3">
        <div className="relative">
          {profile.photo_url ? (
            <img
              src={profile.photo_url}
              alt={displayName}
              className="h-14 w-14 rounded-full object-cover ring-2 ring-slate-100"
            />
          ) : (
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-100 text-base font-bold text-blue-700 ring-2 ring-slate-100">
              {initialsOf(displayName)}
            </span>
          )}
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
            title="تغيير صورتي"
            className="absolute -bottom-1 -left-1 flex h-6 w-6 items-center justify-center rounded-full bg-slate-800 text-white shadow ring-2 ring-white transition hover:bg-slate-900 disabled:opacity-60"
          >
            {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Camera className="h-3 w-3" />}
          </button>
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => void pickPhoto(event)}
          />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h2 className="truncate text-sm font-bold text-slate-900">{displayName}</h2>
            {!editing && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[11px] font-bold text-slate-600 transition hover:bg-slate-50"
              >
                <Pencil className="h-3 w-3" /> تعديل رقمي
              </button>
            )}
          </div>

          {profile.job_title && <p className="mt-1 text-xs font-semibold text-slate-700">{profile.job_title}</p>}

          {!editing ? (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              {profile.specialty && (
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
                  {profile.specialty}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Phone className="h-3 w-3" /> {profile.phone || "لا رقم"}
              </span>
            </div>
          ) : (
            <div className="mt-2 space-y-2">
              <label className="block">
                <span className="mb-1 block text-[11px] font-bold text-slate-600">هاتفي</span>
                <input
                  type="text"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs"
                />
              </label>
              {/* المسمّى الوظيفيّ للعرض لا للتعديل — الخادمُ يردّه 403 لغير المدير. */}
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setPhone(profile.phone);
                  }}
                  className="rounded-lg bg-slate-100 px-3 py-1 text-[11px] font-bold text-slate-600 hover:bg-slate-200"
                >
                  إلغاء
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void savePhone()}
                  className="rounded-lg bg-blue-600 px-3 py-1 text-[11px] font-bold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  حفظ
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default MyProfileCard;
