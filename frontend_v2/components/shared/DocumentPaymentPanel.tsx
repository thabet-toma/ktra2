/**
 * T-APPAY — لوحة الدفع الواحدة: تخدم فاتورة البيع وفاتورة الشراء معاً.
 *
 * كانت اللوحة موجودة في محرّر البيع وحده (تحصيل: نقد + شيكات + رصيد العميل)،
 * وجانبُ الشراء يمرّ بنافذةٍ تُلزم بالترحيل أولاً ثم تفتح «سند صرف» — نداءان
 * منفصلان بمفردات مختلفة، فبدا للمالك أن ميزة الدفع غائبةٌ عن المشتريات أصلاً.
 *
 * المكوّن **مُتحكَّم به** (controlled): الحالة تبقى في المحرّر، والمشتقّات كلّها
 * من `deriveDocumentPayment` — دالةٌ نقيّة واحدة. نسختان من هذه الحسبة تعني
 * «متبقّياً» يختلف بين شاشتين، وهو بالضبط ما نُصلحه هنا.
 *
 * الجانبان يختلفان في المفردات فقط (عميل/مورّد · قبض/صرف)، ويتّحدان في الزرّ:
 * «تسجيل دفعة» — كما تفعل Odoo بزرّ *Register Payment* على المستندين سواء.
 */
import React from "react";
import { Loader2, Plus, Receipt, Save, Trash2, Wallet } from "lucide-react";
import { formatMoney } from "../../utils/formatNumber";

export type PaymentChequeRow = {
  key: string;
  cheque_number: string;
  bank_name: string;
  due_date: string;
  amount: string;
};

/** سندٌ مرحّل بقي منه رصيد «على الحساب» يصلح لتسديد هذا المستند. */
export type OnAccountVoucher = { id: number; unallocated: number };

export type DocumentPaymentSide = "customer" | "supplier";

export type DocumentPaymentInput = {
  /** أساس الاحتساب: إجمالي المستند (المحفوظ للمرحّل، وشاشيُّ المسودة). */
  base: number;
  /** المدفوع/المحصَّل سابقاً بسندات مرحّلة. */
  paid: number;
  /** مستندٌ نقديّ: لا يجوز أن يبقى عليه متبقٍّ — الخادم يرفض. */
  isCashDocument: boolean;
  cash: string;
  cheques: PaymentChequeRow[];
  fromBalance: string;
  onAccountVouchers: OnAccountVoucher[];
};

export type DocumentPaymentDerived = {
  remainingBefore: number;
  chequesTotal: number;
  onAccountAvailable: number;
  paidNow: number;
  remainingAfter: number;
  overpay: number;
  chequeError: string | null;
  cashShortfall: number;
  onAccountPlan: Array<{ payment_id: number; amount: number }>;
  /** الدفعة تشمل خصماً من رصيد الطرف — ربطٌ بسندٍ مرحّل، فلا يصحّ على مسودة. */
  usesOnAccount: boolean;
  canSubmit: boolean;
};

/**
 * كلّ ما تعرضه اللوحة مشتقٌّ هنا — مصدرٌ واحد للرقم في الشاشتين.
 * الطرح لا يتكرّر في أيّ مكوّن: أيّ نسخةٍ ثانية تفترق غداً.
 */
export function deriveDocumentPayment(input: DocumentPaymentInput): DocumentPaymentDerived {
  const remainingBefore = Math.max(input.base - input.paid, 0);
  const chequesTotal = input.cheques.reduce(
    (sum, row) => sum + (Number(row.amount) || 0), 0,
  );
  const onAccountAvailable = input.onAccountVouchers.reduce(
    (sum, v) => sum + v.unallocated, 0,
  );
  const cashNum = Number(input.cash) || 0;
  const fromBalanceNum = Number(input.fromBalance) || 0;
  const paidNow = cashNum + chequesTotal + fromBalanceNum;
  const remainingAfter = remainingBefore - paidNow;
  const overpay = Math.max(-remainingAfter, 0);

  let chequeError: string | null = null;
  for (let i = 0; i < input.cheques.length; i++) {
    const row = input.cheques[i];
    if (!row.cheque_number.trim()) { chequeError = `الشيك #${i + 1}: رقم الشيك مطلوب.`; break; }
    if (!row.due_date) { chequeError = `الشيك #${i + 1}: تاريخ الاستحقاق مطلوب.`; break; }
    if (!(Number(row.amount) > 0)) {
      chequeError = `الشيك #${i + 1}: المبلغ يجب أن يكون أكبر من صفر.`; break;
    }
  }

  /* المستند النقدي مدفوعٌ بالتعريف عند الخادم: دفعةٌ لا تغطّيه تُرفض ويرتدّ كلّ
     شيء. نمنع الإرسال هنا ونقول المخرج — رفضٌ كان بالإمكان منعه شاشةٌ سيّئة. */
  const cashShortfall =
    input.isCashDocument && paidNow > 0.009 && remainingAfter > 0.009
      ? remainingAfter
      : 0;

  /** توزيع «من رصيد الطرف» على سنداته المتاحة — الأقدم أولاً كما يعيدها الخادم. */
  const onAccountPlan: Array<{ payment_id: number; amount: number }> = [];
  let left = fromBalanceNum;
  if (left > 0.009) {
    for (const voucher of input.onAccountVouchers) {
      if (left <= 0.009) break;
      const amount = Math.min(voucher.unallocated, left);
      left -= amount;
      if (amount > 0.009) onAccountPlan.push({ payment_id: voucher.id, amount });
    }
  }

  return {
    remainingBefore,
    chequesTotal,
    onAccountAvailable,
    paidNow,
    remainingAfter,
    overpay,
    chequeError,
    cashShortfall,
    onAccountPlan,
    usesOnAccount: onAccountPlan.length > 0,
    canSubmit: paidNow > 0.009 && !chequeError && cashShortfall <= 0,
  };
}

/** حالة تسوية المستند نفسه — لا حالة النموذج الذي يُملأ الآن. */
export type InvoiceSettlement = {
  /** المتبقّي في الدفاتر: ما لم يُرحَّل ليس مدفوعاً. */
  remaining: number;
  /** المتبقّي بعد احتساب الدفعة المرفقة غير المرحّلة — للعرض على المسودة. */
  remainingAfterIntent: number;
  /** المسودة عليها دفعة تغطّي إجماليها — تُوسَم «مدفوعة — غير مرحّلة». */
  intentCoversAll: boolean;
  /** الدفعة المرفقة غير المرحّلة (صفر على المرحّل). */
  pendingIntent: number;
};

/**
 * T-INTENT: مشتقّة «المتبقّي» الوحيدة لشاشتَي الفاتورة.
 *
 * كانت الحسبة مكتوبة أربع مرّات في محرّر البيع وحده (شريط الإجماليات، اللوحة،
 * عرض المستند، الطباعة) بفروقٍ صامتة — إحداها بلا `Math.max` فكانت تُظهر متبقّياً
 * **سالباً** على مسودة. الرقم الآن من موضع واحد.
 *
 * الفصل مقصود: `remaining` حقيقةُ الدفاتر (المرحّل وحده)، و`remainingAfterIntent`
 * ما يراه صاحب المسودة بعد أن سجّل دفعته — موسوماً «غير مرحّل» كي لا يُقرأ
 * أحدهما مكان الآخر.
 */
export function deriveInvoiceSettlement(input: {
  grandTotal: number;
  paid: number;
  pendingIntent: number;
  isPosted: boolean;
}): InvoiceSettlement {
  const remaining = Math.max(input.grandTotal - input.paid, 0);
  // النيّة شأن المسودة وحدها؛ المرحّلة تجسّدت نيّتها سنداً فدخلت `paid`.
  const pendingIntent = input.isPosted ? 0 : Math.max(input.pendingIntent, 0);
  const remainingAfterIntent = Math.max(remaining - pendingIntent, 0);
  return {
    remaining,
    remainingAfterIntent,
    pendingIntent,
    intentCoversAll:
      !input.isPosted
      && pendingIntent > 0.009
      && remainingAfterIntent <= 0.009
      && input.grandTotal > 0.009,
  };
}

const WORDS: Record<DocumentPaymentSide, {
  title: string; balance: string; noBalance: string; voucher: string; hint: string;
}> = {
  customer: {
    title: "تحصيل الفاتورة",
    balance: "من رصيد العميل",
    noBalance: "لا رصيد «على الحساب» لهذا العميل.",
    voucher: "سند قبض",
    hint: "نداء واحد يُنتج سند قبض واحداً مرحّلاً — النقد والشيكات فيه، والخصم من رصيد العميل ربطٌ بسنده القديم.",
  },
  supplier: {
    title: "دفع الفاتورة",
    balance: "من رصيد المورّد (سلف)",
    noBalance: "لا سلفة «على الحساب» لدى هذا المورّد.",
    voucher: "سند صرف",
    hint: "نداء واحد يُنتج سند صرف واحداً مرحّلاً — النقد والشيكات فيه، والخصم من سلف المورّد ربطٌ بسنده القديم.",
  },
};

export type DocumentPaymentPanelProps = {
  side: DocumentPaymentSide;
  derived: DocumentPaymentDerived;
  input: DocumentPaymentInput;
  isPosted: boolean;
  busy: boolean;
  /** حقل حساب الصندوق/البنك — يبنيه المحرّر لأن مصدر الحسابات يخصّه. */
  cashAccountField: React.ReactNode;
  panelRef?: React.Ref<HTMLDivElement>;
  cashInputRef?: React.Ref<HTMLInputElement>;
  chequesOpen: boolean;
  onToggleCheques: () => void;
  onCashChange: (value: string) => void;
  onFromBalanceChange: (value: string) => void;
  onAddCheque: () => void;
  onPatchCheque: (key: string, patch: Partial<PaymentChequeRow>) => void;
  onRemoveCheque: (key: string) => void;
  onFillCashShortfall: () => void;
  /** «المتبقي كاملاً»: يضع كامل المتبقّي في خانة النقد — تعبئةٌ لا إرسال. */
  onFillFull?: () => void;
  onMakeCredit?: () => void;
  /** T-INTENT: حفظ الدفعة على المسودة بلا ترحيل (يُعرض على المسودة وحدها). */
  onSaveIntent?: () => void;
  onSubmit: () => void;
};

export const DocumentPaymentPanel: React.FC<DocumentPaymentPanelProps> = ({
  side, derived, input, isPosted, busy, cashAccountField, panelRef, cashInputRef,
  chequesOpen, onToggleCheques, onCashChange, onFromBalanceChange, onAddCheque,
  onPatchCheque, onRemoveCheque, onFillCashShortfall, onFillFull, onMakeCredit,
  onSaveIntent, onSubmit,
}) => {
  const w = WORDS[side];
  const fmt = (n: number) => formatMoney(n);

  return (
    <div
      ref={panelRef}
      data-testid="document-payment-panel"
      className="flex flex-col gap-2 border border-[var(--ktra-border)] bg-[var(--ktra-panel)] p-2"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-bold text-[var(--color-text)]">
          {w.title} {isPosted ? `(مرحّلة — يُسجَّل ${w.voucher} فوراً)` : "(تُحفظ وتُرحّل مع الدفعة)"}
        </span>
        <span className="text-[11px] text-[var(--color-text-muted)]">
          المسدَّد سابقاً {fmt(input.paid)} · المتبقي قبل هذه الدفعة {fmt(derived.remainingBefore)}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {/* نقداً */}
        <div className="flex flex-col gap-1">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-bold text-[var(--color-text)]">المدفوع نقداً</span>
            <input
              ref={cashInputRef}
              type="number"
              step="0.01"
              min="0"
              className="ktra-input ktra-num"
              data-testid="payment-cash"
              disabled={busy}
              value={input.cash}
              onChange={(e) => onCashChange(e.target.value)}
            />
          </label>
          {/* «المتبقي كاملاً» — التسديد التام هو الحالة الغالبة، وكتابةُ الرقم
              يدوياً كانت ضريبةً عليها (Odoo يفتح *Register Payment* والمبلغ
              معبّأ أصلاً). تعبئةٌ فقط: الإرسال يبقى بزرّ «تسجيل دفعة» أدناه. */}
          {onFillFull && (
            <button
              type="button"
              className="ktra-toolbtn text-[11px]"
              data-testid="payment-fill-full"
              disabled={busy || derived.remainingBefore <= 0.009}
              title="ضع كامل المتبقّي في خانة النقد"
              onClick={onFillFull}
            >
              <Wallet className="h-3 w-3" /> المتبقي كاملاً {fmt(derived.remainingBefore)}
            </button>
          )}
          {cashAccountField}
        </div>

        {/* شيكات */}
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-bold text-[var(--color-text)]">المدفوع شيكات</span>
          <div className="ktra-input ktra-num flex items-center" data-testid="payment-cheques-total">
            {fmt(derived.chequesTotal)}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="ktra-toolbtn text-[11px]"
              disabled={busy}
              onClick={onAddCheque}
            >
              <Plus className="h-3 w-3" /> شيك
            </button>
            {input.cheques.length > 0 && (
              <button type="button" className="ktra-toolbtn text-[11px]" onClick={onToggleCheques}>
                {chequesOpen ? "إخفاء التفاصيل" : `تفاصيل الشيكات (${input.cheques.length})`}
              </button>
            )}
          </div>
        </div>

        {/* من رصيد الطرف — يظهر فقط حين يوجد رصيد مرحّل غير موزَّع */}
        <div className="flex flex-col gap-1">
          {derived.onAccountAvailable > 0.009 ? (
            <>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-bold text-[var(--color-text)]">{w.balance}</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max={derived.onAccountAvailable}
                  className="ktra-input ktra-num"
                  data-testid="payment-from-balance"
                  disabled={busy}
                  value={input.fromBalance}
                  onChange={(e) => onFromBalanceChange(e.target.value)}
                />
              </label>
              <span className="text-[11px] text-[var(--color-text-muted)]">
                المتاح على الحساب {fmt(derived.onAccountAvailable)} — ربطُ سندٍ مرحّل بلا قيد جديد.
              </span>
            </>
          ) : (
            <>
              <span className="text-[11px] font-bold text-[var(--color-text)]">{w.balance}</span>
              <span className="text-[11px] text-[var(--color-text-muted)]">{w.noBalance}</span>
            </>
          )}
        </div>

        {/* المتبقي — مشتقّ حيّ، لا يُدخَل */}
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-bold text-[var(--color-text)]">المتبقي</span>
          <div
            className="ktra-input ktra-num flex items-center font-bold"
            data-testid="payment-remaining"
          >
            {fmt(Math.max(derived.remainingAfter, 0))}
          </div>
          <span className="text-[11px] text-[var(--color-text-muted)]">
            محسوب من الإجمالي ناقص المسدَّد — لا يُدخَل يدوياً.
          </span>
        </div>
      </div>

      {chequesOpen && input.cheques.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-[11px]">
            <thead className="bg-[var(--ktra-surface-2)]">
              <tr>
                <th className="p-1 text-right">رقم الشيك</th>
                <th className="p-1 text-right">البنك</th>
                <th className="p-1 text-right">الاستحقاق</th>
                <th className="p-1 text-right">المبلغ</th>
                <th className="w-8 p-1"></th>
              </tr>
            </thead>
            <tbody>
              {input.cheques.map((row, i) => (
                <tr key={row.key} className="border-t border-[var(--ktra-border)]">
                  <td className="p-0.5">
                    <input
                      className="ktra-input text-[11px]"
                      aria-label={`رقم الشيك ${i + 1}`}
                      disabled={busy}
                      value={row.cheque_number}
                      onChange={(e) => onPatchCheque(row.key, { cheque_number: e.target.value })}
                    />
                  </td>
                  <td className="p-0.5">
                    <input
                      className="ktra-input text-[11px]"
                      aria-label={`بنك الشيك ${i + 1}`}
                      disabled={busy}
                      value={row.bank_name}
                      onChange={(e) => onPatchCheque(row.key, { bank_name: e.target.value })}
                    />
                  </td>
                  <td className="p-0.5">
                    <input
                      type="date"
                      className="ktra-input text-[11px]"
                      aria-label={`استحقاق الشيك ${i + 1}`}
                      disabled={busy}
                      value={row.due_date}
                      onChange={(e) => onPatchCheque(row.key, { due_date: e.target.value })}
                    />
                  </td>
                  <td className="p-0.5">
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      className="ktra-input ktra-num text-[11px]"
                      aria-label={`مبلغ الشيك ${i + 1}`}
                      disabled={busy}
                      value={row.amount}
                      onChange={(e) => onPatchCheque(row.key, { amount: e.target.value })}
                    />
                  </td>
                  <td className="p-0.5 text-center">
                    <button
                      type="button"
                      className="ktra-iconbtn ktra-iconbtn--danger"
                      aria-label={`حذف الشيك ${i + 1}`}
                      disabled={busy}
                      onClick={() => onRemoveCheque(row.key)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {derived.chequeError && (
        <div className="ktra-note ktra-note--warn text-[11px]">{derived.chequeError}</div>
      )}

      {/* الفائض سياسةٌ قائمة في الخادم (دفعة على الحساب) — اللوحة تقولها فقط. */}
      {derived.overpay > 0.009 && (
        <div className="ktra-note ktra-note--warn text-[11px]" data-testid="payment-overpay-note">
          الفائض {fmt(derived.overpay)} يُسجَّل دفعة على الحساب.
        </div>
      )}

      {derived.cashShortfall > 0 && (
        <div className="ktra-note ktra-note--err text-[11px]" data-testid="payment-cash-guard">
          الفاتورة نقدية — المسدَّد لا يغطي الإجمالي. أكمل {fmt(derived.cashShortfall)}
          {onMakeCredit ? " أو اجعلها آجلةً على ذمم الطرف." : "."}
          <button
            type="button"
            className="ktra-toolbtn mr-2 text-[11px]"
            onClick={onFillCashShortfall}
          >
            أكمل المبلغ نقداً
          </button>
          {onMakeCredit && (
            <button type="button" className="ktra-toolbtn mr-2 text-[11px]" onClick={onMakeCredit}>
              اجعلها آجلة
            </button>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {/* T-INTENT: على المسودة يختار المستخدم بين تسجيل الدفعة عليها (بلا
            أثرٍ في الدفاتر) وبين الترحيل والتحصيل فوراً. الفصل مقصود: إجبارُ
            الترحيل ليسجّل دفعةً كان يعني أن مسودةً مدفوعة لا يمكن أن توجد. */}
        {!isPosted && onSaveIntent && (
          <button
            type="button"
            className="ktra-toolbtn"
            data-testid="payment-save-intent"
            disabled={busy || !derived.canSubmit || derived.usesOnAccount}
            title={
              derived.usesOnAccount
                ? "الخصم من رصيد الطرف ربطٌ بسندٍ مرحّل — يلزمه ترحيل المستند."
                : "تُسجَّل الدفعة على المسودة وتتحوّل إلى سند عند الترحيل."
            }
            onClick={onSaveIntent}
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            حفظ الدفعة على المسودة
          </button>
        )}
        <button
          type="button"
          className="ktra-toolbtn"
          data-testid="payment-submit"
          disabled={busy || !derived.canSubmit}
          onClick={onSubmit}
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Receipt className="h-3 w-3" />}
          {busy ? "...جارٍ التسجيل" : isPosted ? "تسجيل دفعة" : "حفظ وترحيل وتسجيل دفعة"}
        </button>
        <span className="text-[11px] text-[var(--color-text-muted)]">{w.hint}</span>
      </div>
    </div>
  );
};
