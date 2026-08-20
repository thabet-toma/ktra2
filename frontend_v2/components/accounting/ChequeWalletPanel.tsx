import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import type { ChequeWalletDto, ChequeWalletSide } from "../../types/accounting";

/**
 * T-CHQ2 — محفظة الشيكات.
 *
 * شاشة الشيكات كانت قائمة صفوف فقط: لا أحد يعرف كم في اليد الآن ولا أي ورقة
 * تأخّرت. المحفظة تجمع الأوراق **المفتوحة** وحدها (مسودة/برسم التحصيل/مرتدة)
 * — المحصّلة والمُعادة والمسوّاة خرجت من اليد فلا مكان لها في الرصيد.
 */
/**
 * CHQ-4: تسمية الحالة لم تعد جدولاً هنا. الرمز واحد والدلالة تختلف بالاتجاه
 * («برسم التحصيل» للوارد مقابل «مسلَّم — بانتظار الصرف» للصادر)، والتسمية
 * الصحيحة تأتي مع كل شيك من الخادم (`status_label`) — فالشاشة تمرّرها هنا،
 * ويبقى الرمز نفسه احتياطاً إن لم تُعرف الحالة.
 */
type StatusLabelFn = (direction: string, status: string) => string;

const Side: React.FC<{
  title: string;
  hint: string;
  side: ChequeWalletSide;
  tone: string;
  direction: string;
  statusLabel: StatusLabelFn;
  onPick?: (status: string) => void;
}> = ({ title, hint, side, tone, direction, statusLabel, onPick }) => (
  <div
    className="rounded-lg border border-[var(--aseel-border)] p-3"
    style={{ background: "var(--aseel-panel)" }}
  >
    <div className="mb-2 flex items-baseline justify-between gap-2">
      <div>
        <div className="font-bold">{title}</div>
        <div className="text-xs text-[var(--aseel-ink-soft)]">{hint}</div>
      </div>
      <div className="text-left">
        <div className="text-lg font-bold" style={{ color: tone }}>
          {formatMoney(side.open_total)}
        </div>
        <div className="text-xs text-[var(--aseel-ink-soft)]">{side.open_count} ورقة</div>
      </div>
    </div>

    <div className="mb-2 grid gap-1">
      {side.buckets.length === 0 ? (
        <span className="text-xs text-[var(--aseel-ink-soft)]">لا أوراق مفتوحة.</span>
      ) : (
        side.buckets.map((bucket) => (
          <button
            key={bucket.status}
            type="button"
            className="flex items-center justify-between rounded px-2 py-1 text-sm hover:bg-[var(--aseel-tab-bg)]"
            onClick={() => onPick?.(bucket.status)}
            title="عرض هذه الحالة في القائمة"
          >
            <span>
              {statusLabel(direction, bucket.status)}
              <span className="text-xs text-[var(--aseel-ink-soft)]"> ({bucket.count})</span>
            </span>
            <span className="font-mono">{formatMoney(bucket.amount)}</span>
          </button>
        ))
      )}
    </div>

    <div className="border-t border-[var(--aseel-border)] pt-2">
      <div className="mb-1 text-xs font-bold text-[var(--aseel-ink-soft)]">حسب الاستحقاق</div>
      <div className="grid gap-1">
        {side.due_buckets
          .filter((bucket) => bucket.count > 0)
          .map((bucket) => (
            <div key={bucket.key} className="flex items-center justify-between text-sm">
              <span
                style={bucket.key === "overdue"
                  ? { color: "var(--aseel-danger, #dc2626)", fontWeight: 600 }
                  : undefined}
              >
                {bucket.label}
                <span className="text-xs text-[var(--aseel-ink-soft)]"> ({bucket.count})</span>
              </span>
              <span className="font-mono">{formatMoney(bucket.amount)}</span>
            </div>
          ))}
        {side.due_buckets.every((bucket) => bucket.count === 0) && (
          <span className="text-xs text-[var(--aseel-ink-soft)]">—</span>
        )}
      </div>
    </div>
  </div>
);

export const ChequeWalletPanel: React.FC<{
  refreshKey?: number;
  /** تسمية الحالة بدلالة الاتجاه — من `status_label` الذي يصل مع الشيكات. */
  statusLabel?: StatusLabelFn;
  onPickStatus?: (direction: string, status: string) => void;
}> = ({ refreshKey = 0, statusLabel = (_d, status) => status, onPickStatus }) => {
  const [wallet, setWallet] = useState<ChequeWalletDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setWallet((await accountingApi.getChequeWallet()) as ChequeWalletDto);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "تعذّر تحميل المحفظة");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (loading) {
    return <div className="p-4 text-sm text-[var(--aseel-ink-soft)]">جاري تحميل المحفظة…</div>;
  }
  if (err) return <div className="aseel-banner aseel-banner--err m-3">{err}</div>;
  if (!wallet) return null;

  const net = Number(wallet.net_open);

  return (
    <div className="p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="text-sm text-[var(--aseel-ink-soft)]">
          حتى {formatDateLocalized(wallet.as_of)}
        </div>
        <button type="button" className="aseel-toolbtn" onClick={() => void load()}>
          <RefreshCw className="h-3 w-3" /> تحديث
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Side
          title="شيكات واردة في اليد"
          hint="أوراق العملاء التي لم تُحصَّل بعد"
          side={wallet.incoming}
          tone="var(--aseel-ok, #16a34a)"
          direction="Incoming"
          statusLabel={statusLabel}
          onPick={(status) => onPickStatus?.("Incoming", status)}
        />
        <Side
          title="شيكات صادرة قائمة"
          hint="التزامات لم تُصرف من حسابنا بعد"
          side={wallet.outgoing}
          tone="var(--aseel-danger, #dc2626)"
          direction="Outgoing"
          statusLabel={statusLabel}
          onPick={(status) => onPickStatus?.("Outgoing", status)}
        />
      </div>

      <div
        className="mt-3 flex items-center justify-between rounded-lg border border-[var(--aseel-border)] p-3"
        style={{ background: "var(--aseel-panel)" }}
      >
        <span className="font-bold">صافي المحفظة (وارد − صادر)</span>
        <span
          className="text-lg font-bold font-mono"
          style={{ color: net < 0 ? "var(--aseel-danger, #dc2626)" : "var(--aseel-ok, #16a34a)" }}
        >
          {formatMoney(wallet.net_open)}
        </span>
      </div>
    </div>
  );
};
