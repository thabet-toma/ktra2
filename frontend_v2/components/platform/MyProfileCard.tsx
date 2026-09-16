import React, { useRef, useState } from "react";
import { Camera, Loader2, Pencil, Phone } from "lucide-react";

import {
  setEmployeeProfileCard,
  uploadEmployeePhoto,
} from "../../services/platformEmployeeProfileApi";
import type { MyPlatformEmployeeProfile } from "../../services/platformEmployeeSpaceApi";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useToast } from "../../contexts/ToastContext";
import { CcAvatar, CcCard, CcPill } from "./ui";

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
    <CcCard className="mb-6 p-4" dir="rtl">
      <div className="flex items-start gap-4">
        <div className="relative shrink-0">
          <CcAvatar
            name={displayName}
            photoUrl={profile.photo_url}
            size="lg"
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={uploading}
            title="تغيير صورتي"
            className="absolute -bottom-1 -left-1 flex h-6 w-6 items-center justify-center rounded-full bg-cc-surface-2 text-cc-text shadow border border-cc-border transition hover:bg-cc-surface disabled:opacity-60"
          >
            {uploading ? <Loader2 className="h-3 w-3 animate-spin text-sky-400" /> : <Camera className="h-3 w-3 text-cc-text-muted" />}
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
            <h2 className="truncate text-base font-bold text-cc-text">{displayName}</h2>
            {!editing && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="flex shrink-0 items-center gap-1 rounded-lg border border-cc-border bg-cc-surface-2 px-2.5 py-1 text-xs font-semibold text-cc-text transition hover:bg-cc-border"
              >
                <Pencil className="h-3 w-3" /> تعديل رقمي
              </button>
            )}
          </div>

          {profile.job_title && <p className="mt-1 text-xs font-semibold text-sky-400">{profile.job_title}</p>}

          {!editing ? (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-cc-text-muted">
              {profile.specialty && (
                <CcPill tone="neutral">{profile.specialty}</CcPill>
              )}
              <span className="flex items-center gap-1.5 text-cc-text-muted">
                <Phone className="h-3.5 w-3.5" /> {profile.phone || "لا رقم"}
              </span>
            </div>
          ) : (
            <div className="mt-3 space-y-2">
              <label className="block">
                <span className="mb-1 block text-xs font-semibold text-cc-text">هاتفي</span>
                <input
                  type="text"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  className="w-full rounded-lg bg-cc-bg border border-cc-border px-2.5 py-1.5 text-xs text-cc-text focus:outline-none focus:border-sky-500"
                />
              </label>
              {/* المسمّى الوظيفيّ للعرض لا للتعديل — الخادمُ يردّه 403 لغير المدير. */}
              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setPhone(profile.phone);
                  }}
                  className="rounded-lg bg-cc-surface-2 hover:bg-cc-border border border-cc-border px-3 py-1.5 text-xs font-semibold text-cc-text transition-colors"
                >
                  إلغاء
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void savePhone()}
                  className="rounded-lg bg-sky-600 hover:bg-sky-500 px-3.5 py-1.5 text-xs font-bold text-white disabled:opacity-50 transition-colors"
                >
                  حفظ
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </CcCard>
  );
};

export default MyProfileCard;
