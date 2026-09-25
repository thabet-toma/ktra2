/**
 * VoucherAllocationModal — توزيع سند واحد على عدّة مستندات (مصدر واحد للجانبين).
 *
 * T-ONACC: سند القبض يُوزَّع على فواتير البيع، وسند الصرف على فواتير الشراء —
 * نفس النافذة ونفس التحقّقات، يتبدّل فقط مصدر البيانات عبر `kind`. التوزيع بعد
 * الترحيل **ربط فقط بلا قيد جديد** (الذمم عولجت وقت الترحيل).
 */
import React, { useState } from "react";
import { ListOrdered, Plus, Trash2 } from "lucide-react";
import { formatMoney } from "@/utils/formatNumber";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import { allocateCustomerPayment } from "../../services/salesApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { docKey, fifoFill, type AllocatableDoc } from "../../utils/voucherAllocation";

export type { AllocatableDoc };

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
  /** ملخّص سياقي اختياري (مثل رصيد الطرف) قبل حقول التوزيع. */
  summary?: React.ReactNode;
  onClose: () => void;
  onSaved: () => void;
}

export const VoucherAllocationModal: React.FC<Props> = ({
  kind, voucher, partnerLabel, docs, summary, onClose, onSaved,
}) => {
  const isCustomer = kind === "customer";
  const available = voucher.unallocated;
  const [rows, setRows] = useState<Array<{ key: string; doc: AllocatableDoc; amount: string }>>([]);
  const [pickKey, setPickKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const totalNew = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const remainingAfter = available - totalNew;
  const canSubmit = rows.length > 0 && totalNew > 0 && remainingAfter >= -0.01;

  const addRow = () => {
    const doc = docs.find((d) => docKey(d) === pickKey);
    if (!doc) return;
    if (rows.some((r) => r.key === pickKey)) {
      setError("المستند مضاف مسبقاً");
      return;
    }
    const amt = Math.min(Math.max(0, available - totalNew), Number(doc.remaining) || 0);
    setRows((rs) => [...rs, { key: pickKey, doc, amount: amt.toFixed(2) }]);
    setPickKey("");
    setError(null);
  };

  /** «توزيع تلقائي»: المتاح على المستندات من الأقدم استحقاقاً — يُراجَع قبل الحفظ. */
  const autoFill = () => {
    setRows(fifoFill(docs, available).map(({ doc, amount }) => ({ key: docKey(doc), doc, amount })));
    setError(null);
  };

  const submit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const invoiceRows = rows
        .filter((r) => !r.doc.target)
        .map((r) => ({ invoice: r.doc.id, amount: r.amount }));
      const accrualRows = rows.flatMap((r) =>
        r.doc.target ? [{ kind: r.doc.target.kind, id: r.doc.target.id, amount: r.amount }] : []);
      if (isCustomer) {
        await allocateCustomerPayment(voucher.id, invoiceRows);
      } else {
        if (invoiceRows.length) await purchaseInvoiceApi.allocateSupplierPayment(voucher.id, invoiceRows);
        if (accrualRows.length) await purchaseInvoiceApi.allocateSupplierPaymentAccruals(voucher.id, accrualRows);
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
      {summary}
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
          value={pickKey}
          onChange={(e) => setPickKey(e.target.value)}
        >
          <option value="">— اختر مستنداً —</option>
          {docs.map((d) => (
            <option key={docKey(d)} value={docKey(d)}>
              {d.label} — متبقٍ {formatMoney(d.remaining)}
            </option>
          ))}
        </select>
        <button type="button" className="ktra-toolbtn" style={{ fontSize: "11px" }} onClick={addRow} disabled={!pickKey}>
          <Plus className="w-3 h-3" /> أضف
        </button>
        <button
          type="button"
          className="ktra-toolbtn text-[11px]"
          onClick={autoFill}
          disabled={docs.length === 0 || available <= 0}
          title="وزّع المتاح على المستندات من الأقدم استحقاقاً"
        >
          <ListOrdered className="w-3 h-3" /> توزيع تلقائي (الأقدم أولاً)
        </button>
      </div>

      {rows.length === 0 ? (
        <div style={{ textAlign: "center", fontSize: "11px", padding: "12px", marginTop: "8px", color: "var(--ktra-ink-soft)", border: "1px dashed var(--ktra-border)", borderRadius: "4px" }}>
          {docs.length === 0
            ? `لا مستندات مفتوحة لهذا ${isCustomer ? "العميل" : "الطرف"} — يبقى السند دفعة تحت الحساب`
            : "أضف مستنداً أو «توزيع تلقائي» لتوزيع المبلغ"}
        </div>
      ) : (
        <table style={{ width: "100%", fontSize: "11px", marginTop: "8px" }}>
          <thead style={{ background: "var(--ktra-surface-2, #f4ede0)" }}>
            <tr>
              <th style={{ padding: "4px", textAlign: "right" }}>المستند</th>
              <th style={{ padding: "4px", textAlign: "right" }}>المبلغ</th>
              <th style={{ width: "30px" }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, idx) => (
              <tr key={r.key} style={{ borderTop: "1px solid var(--ktra-border)" }}>
                <td style={{ padding: "2px" }}>{r.doc.label}</td>
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
          ? `السند مرحَّل — التوزيع ربط بالمستندات فقط ولا يُنشئ قيداً جديداً (${isCustomer ? "ذمم العميل خُفِّضت" : "ذمم المورد دُينت"} وقت الترحيل).`
          : "السند غير مرحَّل — التوزيع يُحفظ الآن ويُطبَّق محاسبياً عند الترحيل."}
      </div>
    </PaymentVoucherModal>
  );
};

export default VoucherAllocationModal;
