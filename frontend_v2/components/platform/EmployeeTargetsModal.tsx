import React, { useCallback, useEffect, useState } from "react";
import { Gauge, X } from "lucide-react";

import {
  getEmployeeTargets,
  setEmployeeTargets,
  type EmployeeTargets,
  type MonthlyUnitsSuggestion,
} from "../../services/platformEmployeeTargetsApi";
import { formatNumber } from "../../utils/formatNumber";
import { describePlatformOpsError } from "../../utils/platformSubscriptionManagement";
import { useToast } from "../../contexts/ToastContext";

interface EmployeeTargetsModalProps {
  employeeId: number;
  employeeName: string;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * المقادير مرتّبة من الأيسر إلى الأشدّ: المستهدَف **سقفٌ على المقام**، فرقمٌ أصغر
 * يعني مقاماً أصغر ودرجةً أعلى على العمل نفسه. «الأدنى» تطلّب أقلّ، و«الأعلى» أشدّ.
 */
const PRESET_LABELS: { key: "low" | "medium" | "high"; label: string; hint: string }[] = [
  { key: "low", label: "الأدنى", hint: "كأضعف أشهره — الأيسر" },
  { key: "medium", label: "المتوسط", hint: "كشهره الوسيط" },
  { key: "high", label: "الأعلى", hint: "كأقوى أشهره — الأشدّ" },
];

const BASIS_NOTE: Record<MonthlyUnitsSuggestion["basis"], string> = {
  self: "المقادير مشتقّة من أشهر هذا الموظّف المكتملة — لا أرقام مخترَعة.",
  peers: "لا تاريخ لهذا الموظّف بعد، فالمقادير مشتقّة من توزيع زملائه للأشهر نفسها.",
  no_history:
    "لا تاريخ في المنصّة بعد، فلا مقادير تُقترح — اكتب رقمك، أو اترك صفراً فيكون المقام وحدات المُسنَد كلّها.",
};

/**
 * ضبطُ مستهدفَي الموظّف (التذكرة 210-ز).
 *
 * الحقلان **سُلَّمان لا رقمٌ واحد**، ولذلك يظهران مفصولَين بعنوانَيهما: مقامُ
 * الإنجاز بوحدات المستندات شهرياً، وطاقةُ الإسناد بالشركات الموزونة وبعدد الأوامر.
 * وخلطُهما هو بعينه ما كان يُعطّل أحدَهما بصمتٍ حين يُضبط الآخر.
 */
export const EmployeeTargetsModal: React.FC<EmployeeTargetsModalProps> = ({
  employeeId,
  employeeName,
  onClose,
  onSaved,
}) => {
  const toast = useToast();
  const [data, setData] = useState<EmployeeTargets | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [units, setUnits] = useState("");
  const [capacity, setCapacity] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const row = await getEmployeeTargets(employeeId);
      setData(row);
      setUnits(row.monthly_units_target);
      setCapacity(row.capacity_target);
    } catch (cause) {
      setError(
        describePlatformOpsError(cause, "قراءة المستهدفات لصاحبها أو لمدير العمليات.", "تعذّر تحميل المستهدفات."),
      );
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [employeeId]);

  useEffect(() => { void load(); }, [load]);

  const submit = async () => {
    if (!data) return;
    const payload: { capacity_target?: string; monthly_units_target?: string } = {};
    // لا يُمرَّر حقلٌ لم يتغيّر: التمريرُ يكتب سطرَ «قبلُ وبعدُ» في سجلّ النشاط بلا تغيير.
    // والمقارنةُ **رقميّةٌ لا نصّيّة**: المخزَّنُ "400.00" والمكتوبُ "400" رقمٌ واحدٌ
    // ونصّان، فمقارنةُ النصّ تُرسل تغييراً لم يقع.
    const changed = (next: string, current: string) => Number(next) !== Number(current);
    if (changed(units, data.monthly_units_target)) payload.monthly_units_target = units.trim();
    if (changed(capacity, data.capacity_target)) payload.capacity_target = capacity.trim();
    if (Object.keys(payload).length === 0) {
      toast("لم يتغيّر شيء.", "info");
      return;
    }
    setSaving(true);
    try {
      await setEmployeeTargets(employeeId, payload);
      toast("ضُبطت المستهدفات.", "success");
      onSaved();
      onClose();
    } catch (cause) {
      toast(
        describePlatformOpsError(cause, "ضبط المستهدفات لمدير العمليات وحده.", "تعذّر حفظ المستهدفات."),
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  const suggestion = data?.monthly_units_suggestion;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" dir="rtl">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <div className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-blue-600" />
            <h3 className="text-sm font-bold text-slate-800">مستهدفات {employeeName}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="إغلاق"
            className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {loading ? (
          <div className="py-14 text-center text-xs text-slate-400">جاري التحميل...</div>
        ) : error ? (
          <div className="m-5 flex items-center justify-between gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => void load()}
              className="rounded-lg bg-rose-100 px-3 py-1 text-[11px] font-bold hover:bg-rose-200"
            >
              إعادة المحاولة
            </button>
          </div>
        ) : (
          <div className="space-y-5 px-5 py-4">
            <section className="space-y-2">
              <div>
                <h4 className="text-xs font-bold text-slate-800">مقام الإنجاز الشهري — بالوحدات</h4>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">
                  <strong className="font-bold text-slate-700">سقفٌ</strong> على المقام الذي تُقاس عليه
                  وحدات الموظّف المعتمدة في محور «إنجاز العمل»: رقمٌ أصغر يعني مقاماً أصغر ودرجةً أعلى
                  على العمل نفسه. ورقمٌ يفوق ما أُسند إليه ذلك الشهر لا أثر له، فالمقام يبقى المُسنَد.
                  صفرٌ يعني «لم يُضبط» فيكون المقام وحدات المُسنَد كلّها. ولا يمسّ شهراً التُقطت لقطته:
                  المستهدَف يُجمَّد معها.
                </p>
              </div>

              {suggestion?.targets ? (
                <div className="flex flex-wrap gap-2">
                  {PRESET_LABELS.map(({ key, label, hint }) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setUnits(String(suggestion.targets?.[key] ?? 0))}
                      className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-right transition hover:border-blue-300 hover:bg-blue-50"
                    >
                      <span className="block text-[11px] font-bold text-slate-700">{label}</span>
                      <span className="block text-base font-black text-slate-900">
                        {formatNumber(suggestion.targets?.[key] ?? 0)}
                      </span>
                      <span className="block text-[10px] text-slate-400">{hint}</span>
                    </button>
                  ))}
                </div>
              ) : null}

              {suggestion && (
                <p className="text-[11px] leading-5 text-slate-400">{BASIS_NOTE[suggestion.basis]}</p>
              )}

              <label className="block">
                <span className="mb-1 block text-[11px] font-bold text-slate-600">أو اكتب الرقم بنفسك</span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  value={units}
                  onChange={(event) => setUnits(event.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
              </label>
            </section>

            <section className="space-y-2 border-t border-slate-100 pt-4">
              <div>
                <h4 className="text-xs font-bold text-slate-800">طاقة الإسناد — بالشركات الموزونة</h4>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">
                  سُلَّمٌ آخرُ تماماً: تُقارَن بمجموع وحدات حِمل الشركات المرتبطة (١ أو ٢ أو ٣ للشركة)
                  عند الإسناد والنقل، وبعدد أوامر العمل النشطة في شريط التدخّل، وهي كذلك مقام مقياس
                  «الإنتاجية المنجزة» القديم. صفرٌ يعني «لم تُضبط» لا «طاقة صفر».
                </p>
              </div>
              <input
                type="number"
                min={0}
                step="0.01"
                aria-label="طاقة الإسناد بالشركات الموزونة"
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              />
            </section>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-slate-100 px-3 py-1.5 text-[11px] font-bold text-slate-600 transition hover:bg-slate-200"
          >
            إلغاء
          </button>
          <button
            type="button"
            disabled={loading || saving || !data}
            onClick={() => void submit()}
            className="rounded-lg bg-blue-600 px-4 py-1.5 text-[11px] font-bold text-white transition hover:bg-blue-700 disabled:opacity-50"
          >
            حفظ
          </button>
        </div>
      </div>
    </div>
  );
};

export default EmployeeTargetsModal;
