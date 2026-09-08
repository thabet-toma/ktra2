/**
 * أجهزةُ الدخول — عميلُ نقاط `hr/auth/devices/` (ISSUE #168).
 *
 * **ليست `devicesApi.ts`**: ذاك سجلُّ الأجهزة الحسّاسة التي **تُباع** (IMEI)،
 * ولا صلةَ له بهذا إطلاقاً. الاسمان لا يُخلطان لا هنا ولا في الواجهة.
 *
 * ولا تُستعمل كلمة «جلسة» لاعتمادِ دخول: «الجلسة» في معجم هذا المستودع جلسةُ
 * عملٍ في الحضور والانصراف. المصطلح هنا **«جهاز»**.
 *
 * كلُّ النقاط تخدم صاحبَ الحساب عن نفسه — لا مُعامِلَ مستخدمٍ في أيٍّ منها،
 * فلا بابَ لقراءة أجهزة غيرك.
 */
import { apiFetch } from "./restApi";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const headers = () => {
  const token = localStorage.getItem("token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Token ${token}` } : {}),
  };
};

export type LoginDevice = {
  id: number;
  /** الاسمُ المعروض: تسميةُ المستخدم إن وُجدت، وإلّا المشتقُّ من وكيل المستخدم. */
  name: string;
  device_name: string;
  label: string;
  ip_address: string;
  /** ISO — يُنسَّق عبر `utils/formatDate` لا بـ`toLocale*`. */
  created_at: string | null;
  last_active_at: string | null;
  is_primary: boolean;
  is_current: boolean;
};

export type LoginDevicesResult =
  | {
      kind: "ok";
      devices: LoginDevice[];
      has_primary: boolean;
      /** دعوةُ اختيار أساسيّ — تظهر ما لم يُختَر واحدٌ بعد. */
      primary_invitation: string | null;
    }
  | {
      /**
       * حارسُ الجهاز الأساسيّ (403). **نتيجةٌ من الدرجة الأولى لا فشلٌ عامّ**:
       * الجهازُ الثانويُّ يستحقّ تفسيراً يسمّي الأساسيَّ، لا قائمةً فارغة.
       */
      kind: "primary_required";
      detail: string;
      primary_device_name: string;
    };

/** يستخرج رسالةَ الخادم العربية كما هي — تسطيحُها إلى «فشل الطلب» يُضيّع السبب. */
async function detailOf(res: Response, fallback: string): Promise<string> {
  const data = await res.json().catch(() => ({}));
  return typeof data?.detail === "string" ? data.detail : fallback;
}

export async function listLoginDevices(): Promise<LoginDevicesResult> {
  const res = await apiFetch(`${API_URL}/hr/auth/devices/`, { headers: headers() });
  if (res.status === 403) {
    const data = await res.json().catch(() => ({}));
    return {
      kind: "primary_required",
      detail: typeof data?.detail === "string" ? data.detail : "الإدارةُ من الجهاز الأساسيّ.",
      primary_device_name: String(data?.primary_device_name || ""),
    };
  }
  if (!res.ok) throw new Error(await detailOf(res, "تعذّر جلب أجهزة الدخول."));
  const data = await res.json();
  return {
    kind: "ok",
    devices: (data.devices || []) as LoginDevice[],
    has_primary: Boolean(data.has_primary),
    primary_invitation: data.primary_invitation ?? null,
  };
}

export async function evictLoginDevice(id: number): Promise<string> {
  const res = await apiFetch(`${API_URL}/hr/auth/devices/${id}/evict/`, {
    method: "POST",
    headers: headers(),
  });
  if (!res.ok) throw new Error(await detailOf(res, "تعذّر إنهاء الجهاز."));
  return await detailOf(res, "تم إنهاء الجهاز.");
}

export async function evictOtherLoginDevices(): Promise<number> {
  const res = await apiFetch(`${API_URL}/hr/auth/devices/evict-others/`, {
    method: "POST",
    headers: headers(),
  });
  if (!res.ok) throw new Error(await detailOf(res, "تعذّر إنهاء الأجهزة الأخرى."));
  const data = await res.json().catch(() => ({}));
  return Number(data?.evicted_count || 0);
}

/** تنصيبُ الجهاز الحاليّ أساسيّاً — بكلمة المرور، ومن الجهاز نفسِه. */
export async function setPrimaryLoginDevice(password: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/hr/auth/devices/set-primary/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ password }),
  });
  if (!res.ok) throw new Error(await detailOf(res, "تعذّر تعيين الجهاز الأساسيّ."));
}

export async function renameLoginDevice(id: number, label: string): Promise<void> {
  const res = await apiFetch(`${API_URL}/hr/auth/devices/${id}/rename/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error(await detailOf(res, "تعذّرت إعادة التسمية."));
}
