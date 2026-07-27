/**
 * أجزاء مشتركة لسند القبض (العميل) وسند الصرف (المورد) — مصدر تصميم واحد.
 *
 * قرار المالك (2026-07-25): توحيد تصميم «دفعات العملاء» و«سندات صرف الموردين»
 * على نمط سند الصرف. بدل نسختين متباعدتين من نفس النموذج، تسكن هنا القطع
 * المشتركة (غلاف النافذة + حقول الدفع + شبكة الشيكات) وتُستهلك في
 * {@link NewPaymentModal} و{@link NewSupplierPaymentModal} فتخرج النافذتان
 * بنفس الهيكل والألوان تماماً.
 */
import React from "react";
import { formatMoney, formatNumber } from "@/utils/formatNumber";
import { Plus, Save, Trash2, X } from "lucide-react";

const fmt = (n: string | number) => formatMoney(n);

export interface ChequeLine {
  cheque_number: string;
  payee_name: string;
  due_date: string;
  amount: string;
  bank_name: string;
  branch: string;
  account_number: string;
  issue_date?: string;
}

export const newChequeLine = (defaults: Partial<ChequeLine> = {}): ChequeLine => ({
  cheque_number: "",
  payee_name: "",
  due_date: "",
  amount: "",
  bank_name: "",
  branch: "",
  account_number: "",
  ...defaults,
});

/**
 * غلاف نافذة السند: ترويسة + شريط خطأ + جسم + أزرار الحفظ/الإلغاء.
 *
 * T-AUTOPOST: زرّ ثانوي اختياري (`secondaryLabel`/`onSecondary`) — الزر الأساسي
 * يتبع إعداد الشركة «ترحيل السندات تلقائياً»، والثانوي هو البديل الصريح
 * («حفظ كمسودة» أو «حفظ وترحيل»).
 */
export const PaymentVoucherModal: React.FC<{
  title: string;
  error?: string | null;
  submitting?: boolean;
  submitLabel?: string;
  secondaryLabel?: string;
  onSecondary?: () => void;
  disabled?: boolean;
  onClose: () => void;
  onSubmit: () => void;
  children: React.ReactNode;
}> = ({
  title, error, submitting = false, submitLabel = "حفظ السند",
  secondaryLabel, onSecondary, disabled = false, onClose, onSubmit, children,
}) => (
  <div
    className="fixed inset-0 z-[60] bg-black/40"
    style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "16px" }}
    onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
  >
    <div
      dir="rtl"
      data-skin="aseel"
      style={{
        background: "var(--aseel-surface, #fff)",
        border: "1px solid var(--aseel-border, #c8b99a)",
        borderRadius: "var(--aseel-radius, 6px)",
        width: "100%", maxWidth: "780px", maxHeight: "90vh", overflow: "auto", padding: "16px",
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid var(--aseel-border)", paddingBottom: "8px" }}>
        <h3 style={{ fontWeight: 600, fontSize: "14px" }}>{title}</h3>
        <button type="button" className="aseel-toolbtn" onClick={onClose}>
          <X className="w-3 h-3" />
        </button>
      </div>

      {error && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{error}</div>}

      {children}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
        <button type="button" className="aseel-toolbtn" onClick={onClose}>إلغاء</button>
        {secondaryLabel && onSecondary && (
          <button
            type="button"
            className="aseel-toolbtn"
            disabled={submitting || disabled}
            onClick={onSecondary}
            style={{ opacity: submitting || disabled ? 0.5 : 1 }}
          >
            {secondaryLabel}
          </button>
        )}
        <button
          type="button"
          className="aseel-toolbtn"
          disabled={submitting || disabled}
          onClick={onSubmit}
          style={{ background: "var(--aseel-ok, #2d7d46)", color: "#fff", opacity: submitting || disabled ? 0.5 : 1 }}
        >
          <Save className="w-3 h-3" /> {submitting ? "..." : submitLabel}
        </button>
      </div>
    </div>
  </div>
);

/** حقول الدفع: نقدا + مجموع الشيكات + المجموع + خصم المصدر + الصافي. */
export const PaymentFinanceFields: React.FC<{
  cashAmount: string;
  onCashAmount: (v: string) => void;
  totalCheques: number;
  total: number;
  withholdingPct: string;
  onWithholdingPct: (v: string) => void;
  withholdingAmt: string;
  onWithholdingAmt: (v: string) => void;
  /** تسمية الحقل الأخير — «صافي المستحق» للصرف و«مبلغ الحساب» للقبض. */
  netLabel?: string;
}> = ({
  cashAmount, onCashAmount, totalCheques, total,
  withholdingPct, onWithholdingPct, withholdingAmt, onWithholdingAmt,
  netLabel = "صافي المستحق",
}) => {
  const net = Math.max(0, total - (Number(withholdingAmt) || 0));
  return (
    <div style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.3)", borderRadius: "4px", padding: "8px", marginTop: "12px" }}>
      <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--aseel-warn, #b06800)", marginBottom: "6px" }}>حقول الدفع</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        <label className="aseel-field">
          <span className="aseel-field-label">نقدا</span>
          <input
            type="number" step="0.01"
            data-aseel-field="remaining-amount"
            className="aseel-input aseel-num"
            value={cashAmount}
            onChange={(e) => onCashAmount(e.target.value)}
          />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">مجموع الشيكات (auto)</span>
          <input type="text" readOnly className="aseel-input aseel-num" value={fmt(totalCheques)} style={{ background: "var(--aseel-surface-2)" }} />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">المجموع</span>
          <input type="text" readOnly className="aseel-input aseel-num" value={fmt(total)} style={{ background: "var(--aseel-surface-2)", fontWeight: 700 }} />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">نسبة خصم المصدر %</span>
          <input type="number" step="0.01" className="aseel-input aseel-num" value={withholdingPct} onChange={(e) => onWithholdingPct(e.target.value)} />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">مبلغ خصم المصدر</span>
          <input
            type="number" step="0.01" className="aseel-input aseel-num" value={withholdingAmt}
            onChange={(e) => {
              onWithholdingAmt(e.target.value);
              if (total > 0) onWithholdingPct(formatNumber(((Number(e.target.value) || 0) / total) * 100, { maxDecimals: 2 }));
            }}
          />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">{netLabel}</span>
          <input type="text" readOnly className="aseel-input aseel-num" value={fmt(net)} style={{ background: "var(--aseel-ok-bg, #e3f6e9)", color: "var(--aseel-ok, #2d7d46)", fontWeight: 700 }} />
        </label>
      </div>
    </div>
  );
};

/** شبكة شيكات السند + زر «تعبئة متشابهة» (شيكات متتالية بنفس البنك/المبلغ). */
export const ChequeGrid: React.FC<{
  cheques: ChequeLine[];
  onChange: (next: ChequeLine[]) => void;
  onError?: (msg: string) => void;
  newLineDefaults?: Partial<ChequeLine>;
}> = ({ cheques, onChange, onError, newLineDefaults }) => {
  const patch = (i: number, part: Partial<ChequeLine>) =>
    onChange(cheques.map((x, j) => (i === j ? { ...x, ...part } : x)));

  const fillSimilar = () => {
    const last = cheques[cheques.length - 1];
    if (!last || !last.bank_name) {
      onError?.("أضف شيكاً واحداً بكل البيانات أولاً");
      return;
    }
    const months = Number(window.prompt("عدد الشيكات المتتالية (شهور)؟", "3") || "0");
    if (months <= 0) return;
    const baseDate = new Date(last.due_date || new Date().toISOString().slice(0, 10));
    const extra: ChequeLine[] = [];
    for (let i = 1; i <= months; i++) {
      const d = new Date(baseDate);
      d.setMonth(d.getMonth() + i);
      extra.push({ ...last, cheque_number: "", due_date: d.toISOString().split("T")[0] });
    }
    onChange([...cheques, ...extra]);
  };

  return (
    <div style={{ marginTop: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
        <span style={{ fontWeight: 600, fontSize: "12px" }}>شيكات السند</span>
        <div style={{ display: "flex", gap: "6px" }}>
          <button
            type="button" className="aseel-toolbtn" style={{ fontSize: "11px" }}
            onClick={fillSimilar}
            title="تعبئة شيكات بنفس البنك/المبلغ لشهور متتالية"
          >
            تعبئة متشابهة
          </button>
          <button type="button" className="aseel-toolbtn" style={{ fontSize: "11px" }} onClick={() => onChange([...cheques, newChequeLine(newLineDefaults)])}>
            <Plus className="w-3 h-3" /> شيك
          </button>
        </div>
      </div>
      {cheques.length === 0 ? (
        <div style={{ textAlign: "center", fontSize: "11px", padding: "12px", color: "var(--aseel-ink-soft)", border: "1px dashed var(--aseel-border)", borderRadius: "4px" }}>
          لا شيكات — اضغط «شيك» للإضافة
        </div>
      ) : (
        <table style={{ width: "100%", fontSize: "11px" }}>
          <thead style={{ background: "var(--aseel-surface-2, #f4ede0)" }}>
            <tr>
              <th style={{ padding: "4px" }}>#</th>
              <th style={{ padding: "4px" }}>رقم</th>
              <th style={{ padding: "4px" }}>رقم الحساب</th>
              <th style={{ padding: "4px" }}>صاحب الشيك</th>
              <th style={{ padding: "4px" }}>الاستحقاق</th>
              <th style={{ padding: "4px" }}>المبلغ</th>
              <th style={{ padding: "4px" }}>البنك</th>
              <th style={{ padding: "4px" }}>الفرع</th>
              <th style={{ width: "30px" }}></th>
            </tr>
          </thead>
          <tbody>
            {cheques.map((c, i) => (
              <tr key={i} style={{ borderTop: "1px solid var(--aseel-border)" }}>
                <td style={{ padding: "2px", textAlign: "center" }}>{i + 1}</td>
                <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.cheque_number} onChange={(e) => patch(i, { cheque_number: e.target.value })} /></td>
                <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.account_number} onChange={(e) => patch(i, { account_number: e.target.value })} /></td>
                <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.payee_name} onChange={(e) => patch(i, { payee_name: e.target.value })} /></td>
                <td style={{ padding: "2px" }}><input type="date" className="aseel-input" style={{ fontSize: "11px" }} value={c.due_date} onChange={(e) => patch(i, { due_date: e.target.value })} /></td>
                <td style={{ padding: "2px" }}><input type="number" step="0.01" className="aseel-input aseel-num" style={{ fontSize: "11px" }} value={c.amount} onChange={(e) => patch(i, { amount: e.target.value })} /></td>
                <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.bank_name} onChange={(e) => patch(i, { bank_name: e.target.value })} /></td>
                <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.branch} onChange={(e) => patch(i, { branch: e.target.value })} /></td>
                <td style={{ padding: "2px", textAlign: "center" }}>
                  <button type="button" onClick={() => onChange(cheques.filter((_, j) => j !== i))} style={{ color: "var(--aseel-err, #c0392b)" }}>
                    <Trash2 className="w-3 h-3" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};
