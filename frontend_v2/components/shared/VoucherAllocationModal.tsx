/**
 * VoucherAllocationModal — توزيع سند واحد على عدّة مستندات (مصدر واحد للجانبين).
 *
 * T-ONACC: سند القبض يُوزَّع على فواتير البيع، وسند الصرف على فواتير الشراء —
 * نفس النافذة ونفس التحقّقات، يتبدّل فقط مصدر البيانات عبر `kind`. التوزيع بعد
 * الترحيل **ربط فقط بلا قيد جديد** (الذمم عولجت وقت الترحيل).
 */
import React, { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { formatMoney } from "@/utils/formatNumber";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import { allocateCustomerPayment } from "../../services/salesApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";

/** مستند مفتوح قابل لاستقبال التوزيع. */
export type AllocatableDoc = {
  id: number;
  label: string;
  /** المتبقّي على المستند (نص أو رقم). */
  remaining: string | number;
};

export type AllocatableVoucher = {
  id: number;
  amount: string | number;
  /** المتبقّي غير الموزَّع من السند. */
  unallocated: number;
  is_posted: boolean;
};

interface Props {
  kind: "customer" | "supplier";
  voucher: AllocatableVoucher;
  partnerLabel: string;
  docs: AllocatableDoc[];
  onClose: () => void;
  onSaved: () => void;
}

export const VoucherAllocationModal: React.FC<Props> = ({
  kind, voucher, partnerLabel, docs, onClose, onSaved,
}) => {
  const isCustomer = kind === "customer";
  const available = voucher.unallocated;
  const [rows, setRows] = useState<Array<{ invoice: number; label: string; amount: string }>>([]);
  const [pickId, setPickId] = useState<number | "">("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const totalNew = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const remainingAfter = available - totalNew;
  const canSubmit = rows.length > 0 && totalNew > 0 && remainingAfter >= -0.01;

  const addRow = () => {
    const doc = docs.find((d) => d.id === Number(pickId));
    if (!doc) return;
    if (rows.some((r) => r.invoice === doc.id)) {
      setError("المستند مضاف مسبقاً");
      return;
    }
    const amt = Math.min(Math.max(0, available - totalNew), Number(doc.remaining) || 0);
    setRows((rs) => [...rs, { invoice: doc.id, label: doc.label, amount: amt.toFixed(2) }]);
    setPickId("");
    setError(null);
  };

  const submit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const payload = rows.map((r) => ({ invoice: r.invoice, amount: r.amount }));
      if (isCustomer) {
        await allocateCustomerPayment(voucher.id, payload);
      } else {
        await purchaseInvoiceApi.allocateSupplierPayment(voucher.id, payload);
      }
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "فشل التوزيع");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <PaymentVoucherModal
      title={`توزيع سند #${voucher.id} — ${partnerLabel}`}
      error={error}
      submitting={submitting}
      disabled={!canSubmit}
      submitLabel="توزيع"
      onClose={onClose}
      onSubmit={() => void submit()}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        <label className="ktra-field">
          <span className="ktra-field-label">مبلغ السند</span>
          <input readOnly className="ktra-input ktra-num" value={formatMoney(voucher.amount)}
            style={{ background: "var(--ktra-surface-2)" }} />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">المتاح للتوزيع</span>
          <input readOnly className="ktra-input ktra-num" value={formatMoney(available)}
            style={{ background: "var(--ktra-surface-2)", fontWeight: 700 }} />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">يبقى على الحساب</span>
          <input
            readOnly className="ktra-input ktra-num" value={formatMoney(remainingAfter)}
            style={{
              background: "var(--ktra-ok-bg, #e3f6e9)",
              color: remainingAfter < -0.01 ? "var(--ktra-err, #c0392b)" : "var(--ktra-ok, #2d7d46)",
              fontWeight: 700,
            }}
          />
        </label>
      </div>

      <div style={{ display: "flex", gap: "6px", marginTop: "12px" }}>
        <select
          className="ktra-input"
          style={{ flex: 1, fontSize: "11px" }}
          value={pickId}
          onChange={(e) => setPickId(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">— اختر فاتورة —</option>
          {docs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label} — متبقٍ {formatMoney(d.remaining)}
            </option>
          ))}
        </select>
        <button type="button" className="ktra-toolbtn" style={{ fontSize: "11px" }} onClick={addRow} disabled={!pickId}>
          <Plus className="w-3 h-3" /> أضف
        </button>
      </div>

      {rows.length === 0 ? (
        <div style={{ textAlign: "center", fontSize: "11px", padding: "12px", marginTop: "8px", color: "var(--ktra-ink-soft)", border: "1px dashed var(--ktra-border)", borderRadius: "4px" }}>
          {docs.length === 0
            ? `لا فواتير مفتوحة لهذا ${isCustomer ? "العميل" : "المورد"}`
            : "أضف فاتورة لتوزيع المبلغ عليها"}
        </div>
      ) : (
        <table style={{ width: "100%", fontSize: "11px", marginTop: "8px" }}>
          <thead style={{ background: "var(--ktra-surface-2, #f4ede0)" }}>
            <tr>
              <th style={{ padding: "4px", textAlign: "right" }}>الفاتورة</th>
              <th style={{ padding: "4px", textAlign: "right" }}>المبلغ</th>
              <th style={{ width: "30px" }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, idx) => (
              <tr key={r.invoice} style={{ borderTop: "1px solid var(--ktra-border)" }}>
                <td style={{ padding: "2px" }}>{r.label}</td>
                <td style={{ padding: "2px" }}>
                  <input
                    type="number" step="0.01" className="ktra-input ktra-num" style={{ fontSize: "11px" }}
                    value={r.amount}
                    onChange={(e) => setRows((rs) => rs.map((x, i) => (i === idx ? { ...x, amount: e.target.value } : x)))}
                  />
                </td>
                <td style={{ padding: "2px", textAlign: "center" }}>
                  <button type="button" onClick={() => setRows((rs) => rs.filter((_, i) => i !== idx))} style={{ color: "var(--ktra-err, #c0392b)" }}>
                    <Trash2 className="w-3 h-3" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ fontSize: "11px", marginTop: "8px", color: "var(--ktra-ink-soft)" }}>
        {voucher.is_posted
          ? `السند مرحَّل — التوزيع ربط بالفواتير فقط ولا يُنشئ قيداً جديداً (${isCustomer ? "ذمم العميل خُفِّضت" : "ذمم المورد دُينت"} وقت الترحيل).`
          : "السند غير مرحَّل — التوزيع يُحفظ الآن ويُطبَّق محاسبياً عند الترحيل."}
      </div>
    </PaymentVoucherModal>
  );
};

export default VoucherAllocationModal;
