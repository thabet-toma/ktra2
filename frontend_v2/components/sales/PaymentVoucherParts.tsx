/**
 * أجزاء مشتركة لسند القبض (العميل) وسند الصرف (المورد) — مصدر تصميم واحد.
 *
 * قرار المالك (2026-07-25): توحيد تصميم «دفعات العملاء» و«سندات صرف الموردين»
 * على نمط سند الصرف. بدل نسختين متباعدتين من نفس النموذج، تسكن هنا القطع
 * المشتركة (غلاف النافذة + حقول الدفع + شبكة الشيكات) وتُستهلك في
 * {@link NewPaymentModal} و{@link NewSupplierPaymentModal} فتخرج النافذتان
 * بنفس الهيكل والألوان تماماً.
 */
import React, { useState } from "react";
import { PromptDialog } from "../common/PromptDialog";
import { formatMoney, formatNumber } from "@/utils/formatNumber";
import { Plus, Save, Trash2, X } from "lucide-react";
import { applyBlankDefaults } from "@/utils/partnerChequeDefaults";

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
  /** عند الإغفال يتبع الزر الثانوي حالة الزر الأساسي كما كان سابقاً. */
  secondaryDisabled?: boolean;
  disabled?: boolean;
  /** يخفي شريط الأزرار عندما يقدّم جسم النافذة إجراءات سياقية كاملة. */
  hideActions?: boolean;
  onClose: () => void;
  onSubmit: () => void;
  children: React.ReactNode;
}> = ({
  title, error, submitting = false, submitLabel = "حفظ السند",
  secondaryLabel, onSecondary, secondaryDisabled, disabled = false,
  hideActions = false, onClose, onSubmit, children,
}) => (
  <div
    className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
    onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
  >
    {/* بلا `data-skin` محليّ — انظر التعليل نفسه في `PartnerProfilePage.tsx`:
        الوسم كان يفرض اللوحة الكلاسيكية على النافذة داخل الجلد الحديث. */}
    <div
      dir="rtl"
      className="max-h-[90vh] w-full max-w-[780px] overflow-auto rounded-[var(--ktra-radius)] border border-[var(--ktra-border)] bg-[var(--ktra-surface)] p-4"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="mb-3 flex items-center justify-between border-b border-[var(--ktra-border)] pb-2">
        <h3 className="text-[14px] font-semibold">{title}</h3>
        <button type="button" className="ktra-toolbtn" onClick={onClose} aria-label="إغلاق نافذة السند">
          <X className="w-3 h-3" />
        </button>
      </div>

      {error && <div className="ktra-banner ktra-banner--err mb-2">{error}</div>}

      {children}

      {!hideActions && <div className="mt-4 flex justify-end gap-2">
        <button type="button" className="ktra-toolbtn" onClick={onClose}>إلغاء</button>
        {secondaryLabel && onSecondary && (
          <button
            type="button"
            className="ktra-toolbtn disabled:opacity-50"
            disabled={submitting || (secondaryDisabled ?? disabled)}
            onClick={onSecondary}
          >
            {secondaryLabel}
          </button>
        )}
        <button
          type="button"
          className="ktra-toolbtn bg-[var(--ktra-ok)] text-white disabled:opacity-50"
          disabled={submitting || disabled}
          onClick={onSubmit}
        >
          <Save className="w-3 h-3" /> {submitting ? "..." : submitLabel}
        </button>
      </div>}
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
    <div className="mt-3 rounded border border-[rgba(245,158,11,0.3)] bg-[rgba(245,158,11,0.08)] p-2">
      <div className="mb-1.5 text-[11px] font-semibold text-[var(--ktra-warn)]">حقول الدفع</div>
      <div className="grid grid-cols-3 gap-2">
        <label className="ktra-field">
          <span className="ktra-field-label">نقدا</span>
          <input
            type="number" step="0.01"
            data-ktra-field="remaining-amount"
            className="ktra-input ktra-num"
            value={cashAmount}
            onChange={(e) => onCashAmount(e.target.value)}
          />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">مجموع الشيكات (auto)</span>
          <input type="text" readOnly className="ktra-input ktra-num bg-[var(--ktra-surface-2)]" value={fmt(totalCheques)} />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">المجموع</span>
          <input type="text" readOnly className="ktra-input ktra-num bg-[var(--ktra-surface-2)] font-bold" value={fmt(total)} />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">نسبة خصم المصدر %</span>
          <input type="number" step="0.01" className="ktra-input ktra-num" value={withholdingPct} onChange={(e) => onWithholdingPct(e.target.value)} />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">مبلغ خصم المصدر</span>
          <input
            type="number" step="0.01" className="ktra-input ktra-num" value={withholdingAmt}
            onChange={(e) => {
              onWithholdingAmt(e.target.value);
              if (total > 0) onWithholdingPct(formatNumber(((Number(e.target.value) || 0) / total) * 100, { maxDecimals: 2 }));
            }}
          />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">{netLabel}</span>
          <input type="text" readOnly className="ktra-input ktra-num bg-[var(--ktra-ok-bg)] font-bold text-[var(--ktra-ok)]" value={fmt(net)} />
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
  /** T-CHQ3: الاسم على الورقة يختلف بالاتجاه — الوارد ساحبه الزبون، والصادر
   *  نحن ساحبه والمورد مستفيده. */
  direction?: "Incoming" | "Outgoing";
}> = ({ cheques, onChange, onError, newLineDefaults, direction = "Incoming" }) => {
  const nameHeader = direction === "Outgoing" ? "المستفيد" : "صاحب الشيك";
  const patch = (i: number, part: Partial<ChequeLine>) =>
    onChange(cheques.map((x, j) => (i === j ? { ...x, ...part } : x)));

  // T-CHQ3/هـ: الافتراضيات تصل بعد اختيار الطرف (نداء بطاقته)، فالسطر الذي
  // أُضيف قبلها كان يبقى فارغاً ويُملأ يدوياً. تُملأ الحقول **الفارغة** وحدها —
  // ما كتبه المستخدم لا يُلمس.
  React.useEffect(() => {
    if (!newLineDefaults || !cheques.length) return;
    const filled = cheques.map((line) => applyBlankDefaults(line, newLineDefaults));
    if (filled.some((line, i) => line !== cheques[i])) onChange(filled);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newLineDefaults]);

  // SAVE-3: كان `window.prompt` — يولّد شيكات (التزامات مالية) من نافذة متصفح
  // بلا RTL ولا حقل رقمي. الحوار المشترك يقابله بالسلوك نفسه.
  const [askingMonths, setAskingMonths] = useState(false);

  const fillSimilar = () => {
    const last = cheques[cheques.length - 1];
    if (!last || !last.bank_name) {
      onError?.("أضف شيكاً واحداً بكل البيانات أولاً");
      return;
    }
    setAskingMonths(true);
  };

  const applyFillSimilar = (raw: string) => {
    setAskingMonths(false);
    const last = cheques[cheques.length - 1];
    if (!last) return;
    const months = Number(raw || "0");
    if (!Number.isFinite(months) || months <= 0) return;
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
    <div className="mt-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[12px] font-semibold">شيكات السند</span>
        <div className="flex gap-1.5">
          <button
            type="button" className="ktra-toolbtn text-[11px]"
            onClick={fillSimilar}
            title="تعبئة شيكات بنفس البنك/المبلغ لشهور متتالية"
          >
            تعبئة متشابهة
          </button>
          <button type="button" className="ktra-toolbtn text-[11px]" onClick={() => onChange([...cheques, newChequeLine(newLineDefaults)])}>
            <Plus className="w-3 h-3" /> شيك
          </button>
        </div>
      </div>
      {cheques.length === 0 ? (
        <div className="rounded border border-dashed border-[var(--ktra-border)] p-3 text-center text-[11px] text-[var(--ktra-ink-soft)]">
          لا شيكات — اضغط «شيك» للإضافة
        </div>
      ) : (
        // T-CHQ3/ي: العناوين الأوضح («حساب الساحب»/«البنك المسحوب عليه») وسّعت
        // الجدول فوق عرض النافذة فانحشر عمود الحذف خارج الشاشة — «عملت اثنين
        // بالغلط وبدي أحذف واحد وفش زر». الجدول يمرّر أفقياً داخل حاويته، وعمود
        // الحذف ملتصق بالحافة فيبقى ظاهراً مهما ضاقت الشاشة.
        <div className="overflow-x-auto">
          <table className="ktra-compact-grid ktra-compact-grid--tight w-full min-w-[760px] text-[11px]">
          <thead className="bg-[var(--ktra-surface-2)]">
            <tr>
              <th>#</th>
              <th>رقم</th>
              <th>حساب الساحب</th>
              <th>{nameHeader}</th>
              <th>الاستحقاق</th>
              <th>المبلغ</th>
              <th>البنك المسحوب عليه</th>
              <th>الفرع</th>
              <th className="sticky left-0 w-[34px] bg-[var(--ktra-surface-2)]"></th>
            </tr>
          </thead>
          <tbody>
            {cheques.map((c, i) => (
              <tr key={i} className="border-t border-[var(--ktra-border)]">
                <td className="text-center">{i + 1}</td>
                <td><input className="ktra-input text-[11px]" value={c.cheque_number} onChange={(e) => patch(i, { cheque_number: e.target.value })} /></td>
                <td><input className="ktra-input text-[11px]" value={c.account_number} onChange={(e) => patch(i, { account_number: e.target.value })} /></td>
                <td><input className="ktra-input text-[11px]" value={c.payee_name} onChange={(e) => patch(i, { payee_name: e.target.value })} /></td>
                <td><input type="date" className="ktra-input text-[11px]" value={c.due_date} onChange={(e) => patch(i, { due_date: e.target.value })} /></td>
                <td><input type="number" step="0.01" className="ktra-input ktra-num text-[11px]" value={c.amount} onChange={(e) => patch(i, { amount: e.target.value })} /></td>
                <td><input className="ktra-input text-[11px]" value={c.bank_name} onChange={(e) => patch(i, { bank_name: e.target.value })} /></td>
                <td><input className="ktra-input text-[11px]" value={c.branch} onChange={(e) => patch(i, { branch: e.target.value })} /></td>
                <td className="sticky left-0 bg-[var(--ktra-surface)] text-center">
                  <button
                    type="button"
                    title={`حذف الشيك #${i + 1}`}
                    aria-label={`حذف الشيك #${i + 1}`}
                    onClick={() => onChange(cheques.filter((_, j) => j !== i))}
                    className="p-1 text-[var(--ktra-err)]"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      <PromptDialog
        isOpen={askingMonths}
        title="تعبئة شيكات متشابهة"
        message="عدد الشيكات المتتالية (شهور)؟"
        initialValue="3"
        type="number"
        confirmText="تعبئة"
        onCancel={() => setAskingMonths(false)}
        onSubmit={applyFillSimilar}
      />
    </div>
  );
};
