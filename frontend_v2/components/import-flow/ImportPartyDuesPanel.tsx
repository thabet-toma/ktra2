import React from "react";
import { formatMoney } from "@/utils/formatNumber";

/**
 * «لمن أدفع وكم؟» — لوحة واحدة لأطراف الاستيراد الثلاثة.
 *
 * كانت ذمم وكيل الشحن والمخلّص والناقل المحلي موزّعة على تبويبين بثلاثة نماذج
 * مختلفة الشكل، فيتنقّل المستخدم بينها ليجمع صورة واحدة. هنا لغة واحدة لكل طرف:
 * **مستحق ← مدفوع ← متبقٍ**، وزرّان لا أكثر — «أثبت الاستحقاق» (إن لم يُثبَّت)
 * و«ادفع». والفصل بين الاستحقاق والدفع يبقى كما هو: الدفع لا يُشترط له ترتيب.
 */

export interface ImportPartyDue {
  key: string;
  /** «وكيل الشحن الدولي» / «المخلّص الجمركي» / «الناقل المحلي» */
  role: string;
  /** اسم الطرف كما هو مسجَّل، أو null إن لم يُختَر بعد. */
  party: string | null;
  /** رمز العملة المعروض بجانب المبالغ. */
  symbol: string;
  due: number;
  paid: number;
  /** هل أُثبت الاستحقاق (صار الطرف دائناً)؟ */
  accrued: boolean;
  /** توضيح صغير أسفل البطاقة — سبب أو تنبيه. */
  note?: string;
  accrueLabel?: string;
  onAccrue?: () => void;
  payLabel?: string;
  onPay?: () => void;
}

const fmt = (value: number) => formatMoney(value, "0");

export function ImportPartyDuesPanel({
  parties,
  busy = false,
}: {
  parties: ImportPartyDue[];
  busy?: boolean;
}) {
  if (parties.length === 0) return null;
  return (
    <section className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
      <h4 className="mb-2 text-xs font-bold text-[var(--color-text)]">
        من عليه مستحقات في هذه الشحنة
        <span className="ms-2 font-normal text-[var(--color-text-muted)]">
          الاستحقاق يجعل الطرف دائناً، والدفع حركة مستقلة متى شئت.
        </span>
      </h4>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {parties.map((p) => {
          const remaining = Math.max(0, p.due - p.paid);
          const advance = Math.max(0, p.paid - p.due);
          const settled = p.due > 0 && remaining <= 0.02;
          return (
            <article
              key={p.key}
              data-testid={`import-party-${p.key}`}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold text-[var(--color-text-muted)]">{p.role}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    p.accrued
                      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"
                      : "bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-200"
                  }`}
                >
                  {p.accrued ? "مُستحق" : "بلا استحقاق"}
                </span>
              </div>
              <div className="mt-0.5 truncate text-sm font-bold text-[var(--color-text)]" title={p.party || undefined}>
                {p.party || "— لم يُحدَّد —"}
              </div>
              <dl className="mt-1.5 grid grid-cols-3 gap-1 text-center text-[11px]">
                <div>
                  <dt className="text-[var(--color-text-muted)]">المستحق</dt>
                  <dd className="font-mono font-semibold">{p.symbol}{fmt(p.due)}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)]">المدفوع</dt>
                  <dd className="font-mono font-semibold text-emerald-700 dark:text-emerald-400">{p.symbol}{fmt(p.paid)}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)]">المتبقي</dt>
                  <dd className={`font-mono font-semibold ${remaining > 0.02 ? "text-amber-700 dark:text-amber-400" : "text-[var(--color-text-muted)]"}`}>
                    {p.symbol}{fmt(remaining)}
                  </dd>
                </div>
              </dl>
              {advance > 0.02 && (
                <p className="mt-1 text-[10px] text-emerald-700 dark:text-emerald-400">
                  دفعة مقدمة لديه {p.symbol}{fmt(advance)} — رصيد لصالحنا.
                </p>
              )}
              {settled && advance <= 0.02 && (
                <p className="mt-1 text-[10px] text-emerald-700 dark:text-emerald-400">مسدَّد بالكامل.</p>
              )}
              {p.note && <p className="mt-1 text-[10px] text-[var(--color-text-muted)]">{p.note}</p>}
              <div className="mt-1.5 flex flex-wrap gap-1">
                {!p.accrued && p.onAccrue && (
                  <button type="button" className="aseel-toolbtn" style={{ fontSize: 11 }} disabled={busy} onClick={p.onAccrue}>
                    {p.accrueLabel || "أثبت الاستحقاق"}
                  </button>
                )}
                {p.onPay && (
                  <button type="button" className="aseel-toolbtn" style={{ fontSize: 11 }} disabled={busy} onClick={p.onPay}>
                    {p.payLabel || (remaining > 0.02 ? `ادفع ${p.symbol}${fmt(remaining)}` : "تسجيل دفعة")}
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
