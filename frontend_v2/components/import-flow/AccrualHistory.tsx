/**
 * «سجل الاستحقاق» لمستندٍ واحد (تخليص · شحن وكيل · إرسالية): لقطة بنود قيد الاستحقاق الأصلي
 * ثم لقطة كل «تعديل الاستحقاق» — التاريخ ورقم القيد والمبلغ، و«عرض الفرق» بين كل تعديلٍ وما قبله.
 * لقطةٌ بلا تفصيل (استحقاقٌ قديم) يُكمل المستخدم بنودها بـ«إضافة بنود»: لا تُقبل إلا بمجموعٍ
 * يساوي الإجمالي بالسنت، والخادم لا يمسّ القيود.
 */
import React, { useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { fillAccrualSnapshot, listAccrualSnapshots } from "@/services/clearanceApi";
import { formatMoney } from "@/utils/formatNumber";
import { formatDateLocalized } from "@/utils/formatDate";
import {
  accrualTypeLabel, accrualTypeOptions, diffRowClass, fillProgress, signedMoney,
  type AccrualKind, type AccrualSnapshot, type FillLineDraft,
} from "@/utils/accrualBreakdown";
import { AccrualBreakdownTable } from "./AccrualBreakdownTable";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

const FillEditor: React.FC<{
  snapshot: AccrualSnapshot;
  onSaved: (history: AccrualSnapshot[]) => void;
  onCancel: () => void;
}> = ({ snapshot, onSaved, onCancel }) => {
  const defaultType = accrualTypeOptions(snapshot.kind)[0];
  const [lines, setLines] = useState<FillLineDraft[]>([{ label: "", type: defaultType, amount: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const progress = fillProgress(lines, snapshot.total);

  const patch = (i: number, p: Partial<FillLineDraft>) =>
    setLines((cur) => cur.map((l, j) => (j === i ? { ...l, ...p } : l)));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onSaved(await fillAccrualSnapshot(snapshot.id, lines.map((l) => ({ ...l, label: l.label.trim() }))));
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2" data-testid="accrual-fill-editor">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="text-right">
            <th className="px-1 py-1">البند</th>
            <th className="px-1 py-1">النوع</th>
            <th className="px-1 py-1">المبلغ (₪)</th>
            <th className="w-8 px-1 py-1"><span className="sr-only">حذف</span></th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i}>
              <td className="px-1 py-0.5">
                <input className="ktra-input w-full" value={l.label} onChange={(e) => patch(i, { label: e.target.value })} aria-label="البند" />
              </td>
              <td className="px-1 py-0.5">
                <select className="ktra-input w-full" value={l.type} onChange={(e) => patch(i, { type: e.target.value })} aria-label="النوع">
                  {accrualTypeOptions(snapshot.kind).map((t) => (
                    <option key={t} value={t}>{accrualTypeLabel(t)}</option>
                  ))}
                </select>
              </td>
              <td className="px-1 py-0.5">
                <input
                  className="ktra-input w-28" type="number" step="0.01" value={l.amount}
                  onChange={(e) => patch(i, { amount: e.target.value })} aria-label="المبلغ"
                />
              </td>
              <td className="px-1 py-0.5 text-center">
                <button
                  type="button" className="rounded p-1 text-red-600 hover:bg-[var(--color-surface-3)] disabled:opacity-40"
                  onClick={() => setLines((cur) => cur.filter((_, j) => j !== i))}
                  disabled={lines.length <= 1} aria-label="حذف البند"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button" className="ktra-toolbtn inline-flex items-center gap-1 text-[11px]"
          onClick={() => setLines((cur) => [...cur, { label: "", type: defaultType, amount: "" }])}
        >
          <Plus className="h-3 w-3" /> بند
        </button>
        <span
          className={`text-xs font-semibold ${progress.matches ? "text-emerald-700" : "text-amber-700"}`}
          data-testid="accrual-fill-counter"
        >
          المجموع {formatMoney(progress.sumCents / 100)} من {formatMoney(progress.totalCents / 100)}
        </span>
        <span className="flex-1" />
        <button type="button" className="ktra-toolbtn text-[11px]" onClick={onCancel} disabled={busy}>إلغاء</button>
        <button
          type="button" className="ktra-toolbtn text-[11px] font-bold" onClick={() => void save()}
          disabled={busy || !progress.canSave} data-testid="accrual-fill-save"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : "حفظ البنود"}
        </button>
      </div>
      {error && <div role="alert" className="text-xs text-red-600">{error}</div>}
    </div>
  );
};

const SnapshotRow: React.FC<{
  snapshot: AccrualSnapshot;
  onHistory: (history: AccrualSnapshot[]) => void;
}> = ({ snapshot, onHistory }) => {
  const [open, setOpen] = useState(false);
  const [filling, setFilling] = useState(false);
  const isAdjustment = snapshot.role === "adjustment";
  const diff = snapshot.difference ?? "0";

  return (
    <li className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2 text-xs" data-testid="accrual-snapshot">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-semibold">{isAdjustment ? "تعديل" : "الأصل"}</span>
        <span className="text-[var(--color-text-muted)]">{formatDateLocalized(snapshot.date) || "—"}</span>
        <span className="font-mono">قيد #{snapshot.journal_id}</span>
        {isAdjustment ? (
          <span>
            <b className={`ktra-num ${diffRowClass(diff)}`}><span dir="ltr" className="inline-block">{signedMoney(diff)}</span> ₪</b>
            <span className="text-[var(--color-text-muted)]"> · الإجمالي بعده </span>
            <b className="ktra-num">{formatMoney(snapshot.total)} ₪</b>
          </span>
        ) : (
          <b className="ktra-num">{formatMoney(snapshot.total)} ₪</b>
        )}
        <span className="flex-1" />
        {!snapshot.detailed && !filling && (
          <button type="button" className="ktra-toolbtn text-[11px]" onClick={() => setFilling(true)}>إضافة بنود</button>
        )}
        {isAdjustment && snapshot.diff && (
          <button type="button" className="ktra-toolbtn text-[11px]" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? "إخفاء الفرق" : "عرض الفرق"}
          </button>
        )}
        {!isAdjustment && snapshot.detailed && (
          <button type="button" className="ktra-toolbtn text-[11px]" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? "إخفاء البنود" : "عرض البنود"}
          </button>
        )}
      </div>
      {open && (isAdjustment ? snapshot.diff : snapshot.detailed) && (
        <div className="mt-2"><AccrualBreakdownTable snapshot={snapshot} /></div>
      )}
      {filling && (
        <FillEditor
          snapshot={snapshot}
          onCancel={() => setFilling(false)}
          onSaved={(history) => { setFilling(false); onHistory(history); }}
        />
      )}
    </li>
  );
};

export const AccrualHistory: React.FC<{
  kind: AccrualKind;
  documentId: number;
  /** يتغيّر بعد «تعديل الاستحقاق» فيُعاد الجلب. */
  refreshKey?: number;
}> = ({ kind, documentId, refreshKey = 0 }) => {
  const [history, setHistory] = useState<AccrualSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    listAccrualSnapshots(kind, documentId)
      .then((rows) => { if (live) setHistory(rows); })
      .catch((e) => { if (live) { setHistory([]); setError(errText(e)); } })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [kind, documentId, refreshKey]);

  if (!loading && !error && history.length === 0) return null;

  return (
    <section className="mb-3 space-y-1" dir="rtl" aria-label="سجل الاستحقاق" data-testid="accrual-history">
      <h5 className="flex items-center gap-2 text-xs font-bold">
        سجل الاستحقاق
        {loading && <Loader2 className="h-3 w-3 animate-spin" />}
      </h5>
      {error && <div role="alert" className="text-xs text-red-600">{error}</div>}
      <ul className="space-y-1">
        {history.map((s) => <SnapshotRow key={s.id} snapshot={s} onHistory={setHistory} />)}
      </ul>
    </section>
  );
};

export default AccrualHistory;
