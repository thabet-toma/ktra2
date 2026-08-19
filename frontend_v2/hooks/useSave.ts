/**
 * SAVE-1 — الحالات الثلاث لأي عملية حفظ: جارٍ · نجح · فشل مع السبب.
 * الصمت ليس حالة، ولذلك `run` لا يبتلع خطأً أبداً: يلتقطه ويضعه في `error`
 * كي تعرضه الشاشة، ويعيد `undefined` فيتوقّف المتصل عند حدّه (لا يُغلق نافذة
 * ولا يصفّر نموذجاً بعد فشل).
 *
 * تأكيد النجاح **ليس** من مسؤولية الخطّاف: ما يلي النجاح يختلف بين شاشة وأخرى
 * (إغلاق · تنقّل · إعادة تحميل · toast)، وفرضُ نمطٍ واحد عليه كان سيجبر شاشاتٍ
 * تعمل اليوم على إعادة الكتابة بلا مقابل.
 *
 * تعتمد على ما ترميه `services/restApi.handleResponseError`: رسالة معرّبة عبر
 * `humanizeDrfError` + `fieldErrors` + `status`، و`NetworkError` عند فشل الاتصال.
 */
import { useCallback, useRef, useState } from "react";
import { NetworkError } from "../services/restApi";
import { humanizeThrown } from "../utils/drfError";

export interface SaveError {
  /** السبب معرّباً وجاهزاً للعرض في لافتة النموذج. */
  message: string;
  /** «اسم حقل DRF → رسالة» لعرضها بجانب الحقل نفسه عبر `FieldError`. */
  fieldErrors: Record<string, string>;
  /** فشل شبكة/مهلة — الطلب لم يكتمل، وليس رفضاً من الخادم. */
  network: boolean;
  /** رمز HTTP إن وُجد (يغيب في فشل الشبكة). */
  status?: number;
}

export interface UseSave {
  saving: boolean;
  error: SaveError | null;
  clearError: () => void;
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
}

export function useSave(): UseSave {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<SaveError | null>(null);
  // نداءان متتاليان (نقرة مزدوجة على «حفظ») — الثاني يُهمَل بدل أن يُرسل الطلب
  // مرتين. `saving` وحده لا يكفي: تحديث الحالة غير متزامن.
  const inFlight = useRef(false);

  const clearError = useCallback(() => setError(null), []);

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    if (inFlight.current) return undefined;
    inFlight.current = true;
    setSaving(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      const fieldErrors =
        (e as { fieldErrors?: Record<string, string> })?.fieldErrors ?? {};
      setError({
        message: humanizeThrown(e, "تعذّر الحفظ"),
        fieldErrors,
        network: e instanceof NetworkError,
        status: (e as { status?: number })?.status,
      });
      return undefined;
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }, []);

  return { saving, error, clearError, run };
}
