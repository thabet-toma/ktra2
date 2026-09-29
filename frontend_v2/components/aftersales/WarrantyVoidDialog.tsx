import React, { useEffect, useState } from "react";
import { Loader2, ShieldOff, X } from "lucide-react";
import {
  getWarrantyVoidImpact,
  refuseServiceOrderCoverage,
  voidWarrantyCard,
  type WarrantyVoidImpact,
} from "../../services/afterSalesApi";
import {
  WARRANTY_VOID_REASONS,
  warrantyVoidImpactLine,
  warrantyVoidProblem,
} from "../../utils/warranty";

/**
 * #236 — نافذة إلغاء كفالة التاجر أو رفضها لهذا العطل.
 *
 * وضعان بسببٍ واحد وقائمة أسبابٍ واحدة: `void` يلغي البطاقة كلّها ويعرض قبل
 * التأكيد ما سيمسّه (`void-impact/` — الدالة نفسها التي تنفّذ، فالمعاينة لا
 * تكذب)؛ و`refuse` يُسقط تغطية أمرٍ واحد وتبقى البطاقة سارية. الخادم هو الحَكَم:
 * ما تمنعه المعاينة هنا (أمرٌ فيه قطعٌ مرحَّلة) يمنعه هو أيضاً.
 */

type Props =
  | {
      mode: "void";
      cardId: number;
      /** أمر الصيانة الذي أُلغيت الكفالة بسببه — يُسجَّل في البطاقة إن وُجد. */
      serviceOrderId?: number | null;
      onClose: () => void;
      onDone: () => void;
    }
  | {
      mode: "refuse";
      orderId: number;
      orderNumber: string;
      onClose: () => void;
      onDone: () => void;
    };

const fieldClass =
  "h-10 w-full px-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] " +
  "text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] " +
  "disabled:opacity-60";

const messageOf = (cause: unknown, fallback: string) =>
  cause instanceof Error ? cause.message : fallback;

export const WarrantyVoidDialog: React.FC<Props> = (props) => {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [impact, setImpact] = useState<WarrantyVoidImpact | null>(null);
  const [loading, setLoading] = useState(props.mode === "void");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const cardId = props.mode === "void" ? props.cardId : null;
  useEffect(() => {
    if (cardId === null) return;
    let alive = true;
    setLoading(true);
    getWarrantyVoidImpact(cardId)
      .then((data) => { if (alive) setImpact(data); })
      .catch((e) => { if (alive) setErr(messageOf(e, "تعذّرت معاينة أثر الإلغاء")); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [cardId]);

  const problem = warrantyVoidProblem(reason, note);
  const blocked = props.mode === "void" && (impact === null || !impact.can_void);

  const submit = async () => {
    if (problem) { setErr(problem); return; }
    setBusy(true);
    setErr(null);
    try {
      if (props.mode === "void") {
        await voidWarrantyCard(props.cardId, {
          reason,
          note: note.trim(),
          service_order: props.serviceOrderId ?? null,
        });
      } else {
        await refuseServiceOrderCoverage(props.orderId, { reason, note: note.trim() });
      }
      props.onDone();
    } catch (e) {
      setErr(messageOf(e, props.mode === "void" ? "تعذّر إلغاء الكفالة" : "تعذّر رفض الكفالة"));
    } finally {
      setBusy(false);
    }
  };

  const title = props.mode === "void" ? "إلغاء الكفالة" : "رفض الكفالة لهذا العطل";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-black/50 p-3 md:p-6"
    >
      <div className="w-full max-w-lg rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
        <div className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] p-3">
          <div className="flex items-center gap-2 font-bold text-[var(--color-text)]">
            <ShieldOff className="h-5 w-5 text-red-600" />
            {title}
          </div>
          <button
            type="button"
            onClick={props.onClose}
            disabled={busy}
            className="rounded-lg p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
            aria-label="إغلاق"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3 p-3 md:p-4">
          {err && (
            <div role="alert" className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5 text-sm text-red-600 dark:text-red-400">
              {err}
            </div>
          )}

          {props.mode === "refuse" ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              تسقط تغطية الكفالة عن الأمر {props.orderNumber} وحده، وتبقى البطاقة سارية لأعطالٍ أخرى.
              القطع المغطاة غير المرحَّلة تُحاسَب بسعر البيع، وإن كان الأمر في الإصلاح أو جاهزاً
              عاد إلى «بانتظار الموافقة» ليوافق الزبون على التكلفة من جديد.
            </p>
          ) : loading ? (
            <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
              <Loader2 className="h-4 w-4 animate-spin" /> جارٍ حساب الأثر…
            </div>
          ) : impact ? (
            <div className="space-y-2 text-sm text-[var(--color-text)]">
              {impact.blockers.length > 0 && (
                <ul className="space-y-1 rounded-lg border border-red-300 bg-red-50 p-2.5 text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
                  {impact.blockers.map((b) => <li key={b}>{b}</li>)}
                </ul>
              )}
              {impact.orders.length > 0 ? (
                <div>
                  <div className="mb-1 font-semibold">أوامر الصيانة المفتوحة التي سيمسّها الإلغاء</div>
                  <ul className="list-disc space-y-1 ps-5 text-[13px]">
                    {impact.orders.map((order) => (
                      <li key={order.id}>{warrantyVoidImpactLine(order)}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                impact.can_void && (
                  <p className="text-[var(--color-text-muted)]">لا أمر صيانة مفتوح يتأثر بالإلغاء.</p>
                )
              )}
            </div>
          ) : null}

          <div>
            <label className="mb-1 block text-[11px] text-[var(--color-text-muted)]" htmlFor="void-reason">
              السبب
            </label>
            <select
              id="void-reason"
              className={fieldClass}
              value={reason}
              disabled={busy}
              onChange={(e) => setReason(e.target.value)}
            >
              <option value="">— اختر السبب —</option>
              {WARRANTY_VOID_REASONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-[var(--color-text-muted)]" htmlFor="void-note">
              {reason === "other" ? "ملاحظة (مطلوبة)" : "ملاحظة"}
            </label>
            <textarea
              id="void-note"
              className="min-h-20 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-[var(--color-text)] outline-none focus:ring-1 focus:ring-[var(--color-primary)] disabled:opacity-60"
              value={note}
              disabled={busy}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>

        <div className="flex flex-col-reverse gap-2 border-t border-[var(--color-border)] p-3 sm:flex-row">
          <button
            type="button"
            onClick={props.onClose}
            disabled={busy}
            className="rounded-lg border border-[var(--color-border)] px-4 py-2 text-sm font-semibold text-[var(--color-text)] hover:bg-[var(--color-surface-2)] disabled:opacity-50 sm:w-32"
          >
            تراجع
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || loading || blocked || problem !== null}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {title}
          </button>
        </div>
      </div>
    </div>
  );
};

export default WarrantyVoidDialog;
