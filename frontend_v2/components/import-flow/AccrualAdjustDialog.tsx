/**
 * «تعديل الاستحقاق» — بدل «تراجع عن الاستحقاق». القيد الأصلي يبقى، ويُرحَّل قيد فرقٍ
 * واحد بتاريخ يختاره المستخدم؛ وتتعدّل معه تكلفة بضاعة الشحنة (المخزون · ت.ب.م للمبيع ·
 * وسيط الاستلام لغير المستلَم). المعاينة تحسب الأثر نفسه على الخادم بلا ترحيل.
 */
import React, { useState } from "react";
import { Loader2, X } from "lucide-react";
import type { AccrualAdjustOptions, AccrualAdjustResult } from "@/services/clearanceApi";
import { formatMoney } from "@/utils/formatNumber";
import { todayIso } from "@/utils/formatDate";

const fmt = (v: number | string | null | undefined) => formatMoney(v, "—");

type Props = {
  title: string;
  /** حقول المستند المعدَّلة (المبلغ، السعر…) — يملك الأب حالتها. */
  children?: React.ReactNode;
  /** المعاينة والترحيل بالطلب نفسه — المبالغ المعروضة بالعملة الأساسية. */
  request: (opts: AccrualAdjustOptions) => Promise<AccrualAdjustResult>;
  onDone: (result: AccrualAdjustResult) => void;
  onClose: () => void;
};

export const AccrualAdjustDialog: React.FC<Props> = ({ title, children, request, onDone, onClose }) => {
  const [date, setDate] = useState(todayIso());
  const [preview, setPreview] = useState<AccrualAdjustResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (isPreview: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const result = await request({ preview: isPreview, date });
      if (isPreview) setPreview(result);
      else onDone(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (isPreview) setPreview(null);
    } finally {
      setBusy(false);
    }
  };

  const diff = preview ? Number(preview.difference) : 0;

  return (
    <div dir="rtl" className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="mb-3 flex items-start gap-3">
          <h3 className="flex-1 text-lg font-bold">{title}</h3>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]" aria-label="إغلاق">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-3 text-sm text-[var(--color-text-muted)]">
          قيد الاستحقاق الأصلي يبقى كما هو، ويُرحَّل قيدٌ بالفرق وحده. تكلفة بضاعة الشحنة تتعدّل معه:
          الباقي في المخزن على المخزون، والمبيع على تكلفة المبيعات، وغير المستلَم على وسيط الاستلام.
        </p>
        <div className="mb-3 flex flex-wrap items-end gap-3" onChange={() => setPreview(null)}>
          {children}
          <label className="flex flex-col text-xs text-[var(--color-text-muted)]">
            تاريخ قيد التعديل
            <input className="ktra-input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        </div>

        {preview && (
          <div className="mb-3 space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-sm">
            <div className="grid grid-cols-3 gap-2">
              <div><span className="block text-xs text-[var(--color-text-muted)]">المستحق الآن</span><b>{fmt(preview.due_before)} ₪</b></div>
              <div><span className="block text-xs text-[var(--color-text-muted)]">بعد التعديل</span><b>{fmt(preview.due_after)} ₪</b></div>
              <div>
                <span className="block text-xs text-[var(--color-text-muted)]">الفرق</span>
                <b className={diff > 0 ? "text-amber-700" : diff < 0 ? "text-emerald-700" : ""}>{fmt(preview.difference)} ₪</b>
              </div>
            </div>
            {Number(preview.surplus_after) > 0 && (
              <p className="text-emerald-700">
                المدفوع يزيد على المستحق الجديد بـ{fmt(preview.surplus_after)} ₪ — يظهر «فائضاً» في كشف الطرف.
              </p>
            )}
            {preview.revaluations.length > 0 && (
              <div>
                <span className="block text-xs text-[var(--color-text-muted)]">تعديل تكلفة الفواتير المرحّلة</span>
                <table className="mt-1 w-full text-xs">
                  <thead>
                    <tr className="text-[var(--color-text-muted)]">
                      <th className="p-1 text-start">الفاتورة</th>
                      <th className="p-1 text-end">المخزون</th>
                      <th className="p-1 text-end">ت. المبيعات</th>
                      <th className="p-1 text-end">لم يُستلَم</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.revaluations.map((r) => (
                      <tr key={r.invoice_id} className="border-t border-[var(--color-border)]">
                        <td className="p-1">{r.invoice_number}</td>
                        <td className="p-1 text-end">{fmt(r.inventory)}</td>
                        <td className="p-1 text-end">{fmt(r.cogs)}</td>
                        <td className="p-1 text-end">{fmt(r.clearing)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.revaluations.flatMap((r) => r.warnings).map((w) => (
                  <p key={w} className="mt-1 text-xs text-amber-700">{w}</p>
                ))}
              </div>
            )}
          </div>
        )}
        {error && <p className="mb-3 text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2">
          <button type="button" className="ktra-toolbtn" onClick={onClose} disabled={busy}>إلغاء</button>
          <button type="button" className="ktra-toolbtn" onClick={() => void run(true)} disabled={busy}>
            {busy && !preview ? <Loader2 className="h-4 w-4 animate-spin" /> : null} معاينة الفرق
          </button>
          <button
            type="button"
            className="ktra-toolbtn font-bold"
            onClick={() => void run(false)}
            disabled={busy || !preview}
            title={preview ? "ترحيل قيد الفرق وتعديل التكلفة" : "عاين الفرق أولاً"}
          >
            ترحيل التعديل
          </button>
        </div>
      </div>
    </div>
  );
};

export default AccrualAdjustDialog;
