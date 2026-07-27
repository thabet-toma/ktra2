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
import { formatMoney } from "@/utils/formatNumber";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import {
  listCustomerPayments,
  allocateCustomerPayment,
} from "../../services/salesApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { formatDateLocalized } from "../../utils/formatDate";

/** سند «على الحساب» موحَّد الشكل بين الجانبين. */
type OnAccountVoucher = {
  id: number;
  payment_date: string;
  amount: string;
  unallocated: number;
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
}) => {
  const isCustomer = kind === "customer";
  const voucherWord = isCustomer ? "سند قبض" : "سند صرف";
  const [vouchers, setVouchers] = useState<OnAccountVoucher[]>([]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const load = isCustomer
      ? listCustomerPayments({ partner: partnerId }).then((rows) =>
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
        setVouchers(rows.filter((r) => r.is_posted && r.unallocated > 0.009));
        setError(null);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : "تعذّر جلب الأرصدة");
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [isCustomer, partnerId]);

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

  const submit = async () => {
    setError(null);
    setSubmitting(true);
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
      setSubmitting(false);
    }
  };

  return (
    <PaymentVoucherModal
      title={`تسديد ${invoiceLabel} — ${partnerLabel}`}
      error={error}
      submitting={submitting}
      disabled={!canSubmit}
      submitLabel="سدّد من الرصيد"
      secondaryLabel={onNewVoucher ? `${voucherWord} جديد` : undefined}
      onSecondary={onNewVoucher}
      onClose={onClose}
      onSubmit={() => void submit()}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        <label className="aseel-field">
          <span className="aseel-field-label">المتبقّي على الفاتورة</span>
          <input readOnly className="aseel-input aseel-num" value={formatMoney(remaining)}
            style={{ background: "var(--aseel-surface-2)", fontWeight: 700 }} />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">الرصيد على الحساب</span>
          <input readOnly className="aseel-input aseel-num" value={formatMoney(totalOnAccount)}
            style={{ background: "var(--aseel-surface-2)", color: "var(--aseel-warn, #b06800)", fontWeight: 700 }} />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">يبقى بعد التسديد</span>
          <input readOnly className="aseel-input aseel-num"
            value={formatMoney(Math.max(0, remaining - totalSettle))}
            style={{ background: "var(--aseel-ok-bg, #e3f6e9)", color: "var(--aseel-ok, #2d7d46)", fontWeight: 700 }} />
        </label>
      </div>

      <div style={{ marginTop: "12px" }}>
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
      </div>

      <div style={{ fontSize: "11px", marginTop: "8px", color: "var(--aseel-ink-soft)" }}>
        التسديد من الرصيد = ربط السند بهذه الفاتورة، بلا قيد محاسبي جديد
        ({isCustomer ? "ذمم العميل خُفِّضت" : "ذمم المورد دُينت"} وقت ترحيل السند).
      </div>
    </PaymentVoucherModal>
  );
};

export default SettleFromOnAccountModal;
