/**
 * SettleFromOnAccountModal — «تسديد» من داخل الفاتورة (بيع أو شراء).
 *
 * قرار المالك (2026-07-25): زر واحد ذكي داخل الفاتورة — يعرض رصيد الطرف
 * «على الحساب» (سندات مرحَّلة لم تُوزَّع) ويتيح تسديد الفاتورة منه، وإن بقي
 * متبقٍّ يفتح سند قبض/صرف جديد. مكوّن واحد للجانبين (عميل/مورد) عبر `kind`.
 *
 * التسديد من الرصيد = توزيع سند قائم على هذه الفاتورة — **بلا قيد جديد**
 * (الذمم عُولجت وقت ترحيل السند).
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Banknote, Check, WalletCards } from "lucide-react";
import { formatMoney } from "@/utils/formatNumber";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import {
  listCustomerPayments,
  allocateCustomerPayment,
} from "../../services/salesApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import type { AccountNodeLike } from "../../utils/accountTree";
import { formatDateLocalized } from "../../utils/formatDate";

/** سند «على الحساب» موحَّد الشكل بين الجانبين. */
type OnAccountVoucher = {
  id: number;
  payment_date: string;
  amount: string;
  unallocated: number;
};

type QuickReceiptConfig = {
  /** الصناديق القابلة للاختيار (تُحكم صحّة الاختيار). */
  accounts: Array<{ id: number; code?: string | null; name?: string | null }>;
  /**
   * T-DEFACC: شجرة الحسابات كاملة لعرض الاختيار داخل مسارها. حين تغيب يُعرض
   * `accounts` وحده (قائمة مسطّحة) — لا تنكسر الشاشة، لكنها بلا شجرة.
   */
  treeAccounts?: AccountNodeLike[];
  defaultAccountId?: number | null;
  onReceive: (amount: number, accountId: number) => Promise<void>;
};

interface Props {
  kind: "customer" | "supplier";
  partnerId: number;
  partnerLabel: string;
  invoiceId: number;
  invoiceLabel: string;
  /** المتبقّي على الفاتورة (بعملة الفاتورة). */
  remaining: number;
  onClose: () => void;
  /** بعد تسديد ناجح — لإعادة تحميل الفاتورة. */
  onSettled: () => void;
  /** فتح نموذج سند جديد للمتبقّي (زر ثانوي). */
  onNewVoucher?: () => void;
  /** تحصيل سريع داخل النافذة نفسها، دون فتح نموذج سند ثانٍ. */
  quickReceipt?: QuickReceiptConfig;
}

export const SettleFromOnAccountModal: React.FC<Props> = ({
  kind,
  partnerId,
  partnerLabel,
  invoiceId,
  invoiceLabel,
  remaining,
  onClose,
  onSettled,
  onNewVoucher,
  quickReceipt,
}) => {
  const isCustomer = kind === "customer";
  const voucherWord = isCustomer ? "سند قبض" : "سند صرف";
  const [vouchers, setVouchers] = useState<OnAccountVoucher[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [submittingAction, setSubmittingAction] = useState<"receipt" | "balance" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [receiptAmount, setReceiptAmount] = useState(remaining.toFixed(2));
  const [balanceAmount, setBalanceAmount] = useState("0.00");
  const [receiptAccountId, setReceiptAccountId] = useState<number | "">(
    quickReceipt?.defaultAccountId ?? quickReceipt?.accounts[0]?.id ?? "",
  );

  useEffect(() => {
    setReceiptAmount(remaining.toFixed(2));
  }, [remaining]);

  useEffect(() => {
    if (!quickReceipt) return;
    const currentIsValid = quickReceipt.accounts.some((account) => account.id === receiptAccountId);
    if (!currentIsValid) {
      setReceiptAccountId(quickReceipt.defaultAccountId ?? quickReceipt.accounts[0]?.id ?? "");
    }
  }, [quickReceipt, receiptAccountId]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const load = isCustomer
      ? listCustomerPayments({ partner: partnerId, page: 1, page_size: 200 }).then((rows) =>
          (rows || []).map((p) => ({
            id: p.id,
            payment_date: p.payment_date,
            amount: p.amount,
            unallocated: Number(p.unallocated_amount ?? 0),
            is_posted: p.is_posted,
          })),
        )
      : purchaseInvoiceApi.listSupplierPayments(partnerId).then((rows) =>
          (rows || []).map((p) => ({
            id: p.id,
            payment_date: p.payment_date,
            amount: p.amount,
            unallocated: Number(p.unallocated_amount ?? 0),
            is_posted: p.is_posted,
          })),
        );
    load
      .then((rows) => {
        if (!alive) return;
        const available = rows.filter((r) => r.is_posted && r.unallocated > 0.009);
        setVouchers(available);
        setBalanceAmount(
          Math.min(remaining, available.reduce((sum, row) => sum + row.unallocated, 0)).toFixed(2),
        );
        setError(null);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : "تعذّر جلب الأرصدة");
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [isCustomer, partnerId, remaining]);

  const totalOnAccount = useMemo(
    () => vouchers.reduce((s, v) => s + v.unallocated, 0),
    [vouchers],
  );

  /** المقترح لكل سند: الأقل بين رصيده والمتبقّي على الفاتورة بعد بقية السطور. */
  const amountFor = useCallback(
    (v: OnAccountVoucher) => {
      const typed = amounts[v.id];
      if (typed !== undefined) return Number(typed) || 0;
      const usedByOthers = vouchers
        .filter((x) => x.id !== v.id && amounts[x.id] !== undefined)
        .reduce((s, x) => s + (Number(amounts[x.id]) || 0), 0);
      return Math.min(v.unallocated, Math.max(0, remaining - usedByOthers));
    },
    [amounts, vouchers, remaining],
  );

  const rows = useMemo(
    () => vouchers.map((v) => ({ v, amount: amountFor(v) })).filter((r) => r.amount > 0.009),
    [vouchers, amountFor],
  );
  const totalSettle = rows.reduce((s, r) => s + r.amount, 0);
  const canSubmit = rows.length > 0 && totalSettle <= remaining + 0.01;

  const requestedBalanceAmount = Number(balanceAmount);
  const quickBalanceRows = useMemo(() => {
    if (!Number.isFinite(requestedBalanceAmount) || requestedBalanceAmount <= 0) return [];
    let left = requestedBalanceAmount;
    return vouchers
      .map((voucher) => {
        const amount = Math.min(voucher.unallocated, Math.max(0, left));
        left -= amount;
        return { v: voucher, amount };
      })
      .filter((row) => row.amount > 0.009);
  }, [requestedBalanceAmount, vouchers]);

  const canQuickBalance = quickBalanceRows.length > 0
    && requestedBalanceAmount <= remaining + 0.01
    && requestedBalanceAmount <= totalOnAccount + 0.01;
  const requestedReceiptAmount = Number(receiptAmount);
  const canQuickReceipt = Boolean(
    quickReceipt
      && Number.isFinite(requestedReceiptAmount)
      && requestedReceiptAmount > 0
      && requestedReceiptAmount <= remaining + 0.01
      && receiptAccountId !== ""
      && quickReceipt.accounts.some((account) => account.id === receiptAccountId),
  );

  const submit = async () => {
    setError(null);
    setSubmittingAction("balance");
    try {
      for (const r of rows) {
        const payload = [{ invoice: invoiceId, amount: r.amount.toFixed(2) }];
        if (isCustomer) {
          await allocateCustomerPayment(r.v.id, payload);
        } else {
          await purchaseInvoiceApi.allocateSupplierPayment(r.v.id, payload);
        }
      }
      onSettled();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل التسديد من الرصيد");
    } finally {
      setSubmittingAction(null);
    }
  };

  const submitQuickBalance = async () => {
    if (!canQuickBalance) {
      setError("أدخل مبلغاً أكبر من صفر ولا يتجاوز المتبقّي أو الرصيد المتاح.");
      return;
    }
    setError(null);
    setSubmittingAction("balance");
    try {
      for (const row of quickBalanceRows) {
        const payload = [{ invoice: invoiceId, amount: row.amount.toFixed(2) }];
        if (isCustomer) {
          await allocateCustomerPayment(row.v.id, payload);
        } else {
          await purchaseInvoiceApi.allocateSupplierPayment(row.v.id, payload);
        }
      }
      onSettled();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل التسديد من الرصيد");
    } finally {
      setSubmittingAction(null);
    }
  };

  const submitQuickReceipt = async () => {
    if (!quickReceipt || !canQuickReceipt || receiptAccountId === "") {
      setError("أدخل مبلغاً صحيحاً واختر حساب الصندوق أو البنك.");
      return;
    }
    setError(null);
    setSubmittingAction("receipt");
    try {
      await quickReceipt.onReceive(requestedReceiptAmount, receiptAccountId);
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل استلام الدفعة");
    } finally {
      setSubmittingAction(null);
    }
  };

  return (
    <PaymentVoucherModal
      title={`تسديد ${invoiceLabel} — ${partnerLabel}`}
      error={error}
      submitting={submittingAction !== null}
      disabled={!canSubmit}
      submitLabel="سدّد من الرصيد"
      secondaryLabel={!quickReceipt && onNewVoucher ? `${voucherWord} جديد` : undefined}
      secondaryDisabled={false}
      onSecondary={!quickReceipt ? onNewVoucher : undefined}
      hideActions={Boolean(quickReceipt)}
      onClose={onClose}
      onSubmit={() => void submit()}
    >
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded border border-[var(--aseel-border)] bg-[var(--aseel-surface-2)] px-3 py-2">
          <dt className="text-xs font-medium text-[var(--aseel-ink-soft)]">المتبقّي على الفاتورة</dt>
          <dd className="mt-1 text-lg font-bold tabular-nums text-[var(--aseel-ink)]">{formatMoney(remaining)}</dd>
        </div>
        <div className="rounded border border-[var(--aseel-border)] bg-[var(--aseel-surface-2)] px-3 py-2">
          <dt className="text-xs font-medium text-[var(--aseel-ink-soft)]">الرصيد على الحساب</dt>
          <dd className="mt-1 text-lg font-bold tabular-nums text-[var(--aseel-warn)]">{formatMoney(totalOnAccount)}</dd>
        </div>
        <div className="rounded border border-[var(--aseel-border)] bg-[var(--aseel-ok-bg)] px-3 py-2">
          <dt className="text-xs font-medium text-[var(--aseel-ink-soft)]">يبقى بعد التسديد</dt>
          <dd className="mt-1 text-lg font-bold tabular-nums text-[var(--aseel-ok)]">
            {formatMoney(Math.max(0, remaining - totalSettle))}
          </dd>
        </div>
      </dl>

      {quickReceipt && (
        <div className="mt-3 grid grid-cols-1 gap-3">
          <section className="rounded border border-[var(--aseel-border)] bg-[var(--aseel-surface)] p-4 shadow-sm">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-[var(--aseel-ok-bg)] text-[var(--aseel-ok)]">
                <Banknote className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h4 className="text-base font-semibold text-balance">استلم دفعة الآن</h4>
                <p className="mt-0.5 text-xs text-pretty text-[var(--aseel-ink-soft)]">
                  ينشئ سند قبض مرحّلاً ويربطه بهذه الفاتورة فوراً.
                </p>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 items-end gap-3 sm:grid-cols-[minmax(150px,0.85fr)_minmax(200px,1.15fr)_auto]">
              <label className="flex min-w-0 flex-col gap-1.5">
                <span className="text-xs font-medium text-[var(--aseel-ink-soft)]">مبلغ الدفعة الآن</span>
                <input
                  type="number"
                  min="0.01"
                  max={remaining}
                  step="0.01"
                  className="aseel-input aseel-num !h-10 !w-full !flex-none !px-3 text-sm tabular-nums"
                  value={receiptAmount}
                  onChange={(event) => setReceiptAmount(event.target.value)}
                />
              </label>
              <label className="flex min-w-0 flex-col gap-1.5">
                <span className="text-xs font-medium text-[var(--aseel-ink-soft)]">الصندوق أو البنك</span>
                <AccountTreeField
                  className="aseel-input !h-10 !w-full !flex-none !px-3 text-sm"
                  accounts={quickReceipt.treeAccounts ?? quickReceipt.accounts}
                  value={receiptAccountId}
                  onChange={(id) => setReceiptAccountId(id ?? "")}
                  isSelectable={(account) =>
                    quickReceipt.accounts.some((row) => row.id === account.id)
                  }
                  placeholder="اختر الحساب"
                  title="اختيار الصندوق / البنك"
                />
              </label>
              <button
                type="button"
                className="aseel-toolbtn !h-10 min-w-[150px] justify-center !border-transparent !bg-[var(--aseel-ok)] !px-4 font-semibold !text-white transition-transform active:scale-[0.96]"
                disabled={!canQuickReceipt || submittingAction !== null}
                onClick={() => void submitQuickReceipt()}
              >
                <Check className="h-4 w-4" aria-hidden="true" />
                {submittingAction === "receipt" ? "جاري الاستلام…" : "استلم دفعة الآن"}
              </button>
            </div>
            {quickReceipt.accounts.length === 0 && (
              <p className="mt-2 text-xs text-[var(--aseel-err)]">لا يوجد حساب صندوق أو بنك صالح للتحصيل.</p>
            )}
          </section>

          <section className="rounded border border-[var(--aseel-border)] bg-[var(--aseel-surface)] p-4 shadow-sm">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-[var(--aseel-surface-2)] text-[var(--aseel-warn)]">
                <WalletCards className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h4 className="text-base font-semibold text-balance">سدّد من رصيد العميل</h4>
                <p className="mt-0.5 text-xs text-pretty text-[var(--aseel-ink-soft)]">
                  المتاح {formatMoney(totalOnAccount)} — يوزّع المبلغ تلقائياً على سندات الرصيد.
                </p>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 items-end gap-3 sm:grid-cols-[minmax(220px,1fr)_auto]">
              <label className="flex min-w-0 flex-col gap-1.5">
                <span className="text-xs font-medium text-[var(--aseel-ink-soft)]">المبلغ من الرصيد</span>
                <input
                  type="number"
                  min="0.01"
                  max={Math.min(remaining, totalOnAccount)}
                  step="0.01"
                  className="aseel-input aseel-num !h-10 !w-full !flex-none !px-3 text-sm tabular-nums"
                  value={balanceAmount}
                  disabled={loading || totalOnAccount <= 0.009}
                  onChange={(event) => setBalanceAmount(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="aseel-toolbtn !h-10 min-w-[150px] justify-center !border-[var(--aseel-border)] !bg-[var(--aseel-surface-2)] !px-4 font-semibold transition-transform active:scale-[0.96]"
                disabled={!canQuickBalance || submittingAction !== null}
                onClick={() => void submitQuickBalance()}
              >
                {submittingAction === "balance" ? "جاري التسديد…" : "سدّد من الرصيد"}
              </button>
            </div>
          </section>
        </div>
      )}

      {!quickReceipt && <div style={{ marginTop: "12px" }}>
        <div style={{ fontWeight: 600, fontSize: "12px", marginBottom: "6px" }}>
          سندات {isCustomer ? "القبض" : "الصرف"} غير الموزَّعة
        </div>
        {loading ? (
          <div style={{ textAlign: "center", fontSize: "11px", padding: "12px", color: "var(--aseel-ink-soft)" }}>
            جاري التحميل…
          </div>
        ) : vouchers.length === 0 ? (
          <div style={{ textAlign: "center", fontSize: "11px", padding: "12px", color: "var(--aseel-ink-soft)", border: "1px dashed var(--aseel-border)", borderRadius: "4px" }}>
            لا يوجد رصيد على الحساب لهذا الطرف — أنشئ {voucherWord} جديداً للمتبقّي.
          </div>
        ) : (
          <table style={{ width: "100%", fontSize: "11px" }}>
            <thead style={{ background: "var(--aseel-surface-2, #f4ede0)" }}>
              <tr>
                <th style={{ padding: "4px", textAlign: "right" }}>السند</th>
                <th style={{ padding: "4px", textAlign: "right" }}>التاريخ</th>
                <th style={{ padding: "4px", textAlign: "right" }}>على الحساب</th>
                <th style={{ padding: "4px", textAlign: "right" }}>يُسدَّد من هذا السند</th>
              </tr>
            </thead>
            <tbody>
              {vouchers.map((v) => (
                <tr key={v.id} style={{ borderTop: "1px solid var(--aseel-border)" }}>
                  <td style={{ padding: "4px" }}>#{v.id}</td>
                  <td style={{ padding: "4px" }}>{formatDateLocalized(v.payment_date)}</td>
                  <td style={{ padding: "4px" }} className="aseel-num">{formatMoney(v.unallocated)}</td>
                  <td style={{ padding: "2px" }}>
                    <input
                      type="number" step="0.01" className="aseel-input aseel-num"
                      style={{ fontSize: "11px" }}
                      value={amounts[v.id] ?? amountFor(v).toFixed(2)}
                      onChange={(e) => setAmounts((m) => ({ ...m, [v.id]: e.target.value }))}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>}

      <div style={{ fontSize: "11px", marginTop: "8px", color: "var(--aseel-ink-soft)" }}>
        التسديد من الرصيد = ربط السند بهذه الفاتورة، بلا قيد محاسبي جديد
        ({isCustomer ? "ذمم العميل خُفِّضت" : "ذمم المورد دُينت"} وقت ترحيل السند).
      </div>
    </PaymentVoucherModal>
  );
};

export default SettleFromOnAccountModal;
