/**
 * NewSupplierPaymentModal — «سند صرف» قابل لإعادة الاستخدام.
 *
 * توأم {@link NewPaymentModal} (سند القبض للعميل): الاثنان يُبنيان من نفس القطع
 * المشتركة في {@link PaymentVoucherParts} (غلاف النافذة + حقول الدفع + شبكة
 * الشيكات) فيخرجان بتصميم واحد. يحمّل حساباته وعملاته ومورّديه ذاتياً؛ عند تثبيت
 * المورد (`lockPartner`) يُعرَض اسمه فقط.
 *
 * القيد المحاسبي: Dr ذمم المورد (المجموع) = Cr الصندوق/البنك (الجزء النقدي)
 * + Cr «شيكات برسم الدفع» (جزء الشيكات) — الشيك الصادر التزام حتى يُصرف لا
 * نقدٌ خرج من الصندوق. (خصم المصدر في الواجهة لا يُحفَظ بعد.)
 */
import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { apiGetObject } from "../../services/restApi";
import { getSalesSettings } from "../../services/salesApi";
import {
  buildPartnerChequeDefaults,
  validateChequeLines,
  type OwnBankAccount,
} from "../../utils/partnerChequeDefaults";
import type { BankAccountDto } from "../../types/accounting";
import { formatMoney, formatNumber } from "@/utils/formatNumber";
import { buildVoucherEntryPreview } from "../../utils/voucherEntryPreview";
import { PartnerNoteAlert } from "../partners/PartnerNoteAlert";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import { isCashAccount } from "../../utils/accountTree";
import {
  ChequeGrid,
  PaymentFinanceFields,
  PaymentVoucherModal,
  type ChequeLine,
} from "./PaymentVoucherParts";

export type SupplierPaymentPartner = { id: number; name: string };
/** صف الشريك كما يعيده lookup (يحمل النوع) — نفلتره على الموردين فقط. */
type PartnerRow = SupplierPaymentPartner & { partner_type?: string };
type Account = {
  id: number; code: string; name: string; parent: number | null; account_type?: string;
};

const isSupplierRow = (p: PartnerRow) =>
  String(p.partner_type || "").toLowerCase() === "supplier";
type Currency = { CurrencyID: number; Code: string };

interface Props {
  /** المورد المثبّت مسبقاً (من بطاقة الشريك مثلاً). */
  initialPartner?: SupplierPaymentPartner | null;
  /** يمنع تغيير المورد ويعرض اسمه فقط. */
  lockPartner?: boolean;
  /** T-ONEPAY: فاتورة شراء يُربط بها السند عند الفتح من داخلها (المبلغ = متبقّيها). */
  initialInvoice?: { id: number; number?: string; remaining: number } | null;
  onClose: () => void;
  /** `posted` = هل رُحِّل السند فور الحفظ (T-AUTOPOST). */
  onSaved: (posted: boolean) => void;
}

export const NewSupplierPaymentModal: React.FC<Props> = ({
  initialPartner,
  lockPartner = false,
  initialInvoice,
  onClose,
  onSaved,
}) => {
  const today = new Date().toISOString().slice(0, 10);
  const [partners, setPartners] = useState<SupplierPaymentPartner[]>(initialPartner ? [initialPartner] : []);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const [supplierId, setSupplierId] = useState<number | "">(initialPartner?.id ?? "");
  const [paymentDate, setPaymentDate] = useState(today);
  const [cashAmount, setCashAmount] = useState(
    initialInvoice ? String(initialInvoice.remaining) : "",
  );
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [currencyId, setCurrencyId] = useState<number | "">("");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [notes, setNotes] = useState("");
  const [withholdingPct, setWithholdingPct] = useState("0");
  const [withholdingAmt, setWithholdingAmt] = useState("0");
  const [cheques, setCheques] = useState<ChequeLine[]>([]);
  // T-CHQ3/هـ: بيانات الشيك تُعبَّأ من بطاقة الطرف كما في سند القبض — الاسم من
  // كرت المورد، والبنك/الحساب من حساب **الشركة** البنكي لأن الشيك الصادر
  // يُسحب من حسابنا نحن. وتبقى كل الحقول قابلة للتعديل يدوياً.
  const [chequeDefaults, setChequeDefaults] = useState<Partial<ChequeLine>>({});
  const [submitting, setSubmitting] = useState(false);
  // T-AUTOPOST: إعداد الشركة «ترحيل السندات تلقائياً» (الافتراضي مُفعَّل).
  const [autoPost, setAutoPost] = useState(true);

  const totalCheques = cheques.reduce((s, c) => s + (Number(c.amount) || 0), 0);
  const cashNum = Number(cashAmount) || 0;
  const computedTotal = cashNum + totalCheques;

  useEffect(() => {
    const pct = Number(withholdingPct) || 0;
    setWithholdingAmt(formatNumber(computedTotal * (pct / 100), { maxDecimals: 2 }));
  }, [withholdingPct, computedTotal]);

  // تحميل ذاتي للحسابات/العملات، والمورّدين إن لم يكن مثبّتاً.
  useEffect(() => {
    let alive = true;
    void (async () => {
      const tasks: [Promise<Account[]>, Promise<Currency[]>, Promise<PartnerRow[]>] = [
        accountingApi.getAccounts() as Promise<Account[]>,
        accountingApi.getCurrencies() as Promise<Currency[]>,
        lockPartner && initialPartner
          ? Promise.resolve([initialPartner as PartnerRow])
          : (accountingApi.getPartners() as Promise<PartnerRow[]>),
      ];
      const [accs, currs, parts, settings] = await Promise.allSettled([
        ...tasks,
        getSalesSettings(),
      ] as const);
      if (!alive) return;
      if (accs.status === "fulfilled") setAccounts(accs.value || []);
      if (currs.status === "fulfilled") setCurrencies(currs.value || []);
      if (settings.status === "fulfilled") {
        setAutoPost(!!settings.value?.auto_post_payments);
        // T-DEFACC: سند الصرف كان وحده بلا صندوق افتراضي — يُملأ كما في سند القبض.
        const defaultCash = settings.value?.default_cash_account;
        if (defaultCash) setCashAccountId((prev) => prev || defaultCash);
      }
      if (parts.status === "fulfilled") {
        // المورد المثبّت مسبقاً يمرّ كما هو؛ وإلا نعرض الموردين فقط (لا العملاء).
        const list = parts.value || [];
        setPartners((lockPartner && initialPartner) ? list : list.filter(isSupplierRow));
      }
    })();
    return () => { alive = false; };
  }, [lockPartner, initialPartner]);

  // T-CHQ3/هـ: افتراضيات الشيك من كرت المورد + حسابنا البنكي الافتراضي.
  useEffect(() => {
    const partner = partners.find((p) => p.id === supplierId) || initialPartner || null;
    if (!supplierId || !partner) {
      setChequeDefaults({});
      return;
    }
    let cancelled = false;
    const ownAccountOf = (rows: BankAccountDto[]): OwnBankAccount | null => {
      const active = rows.filter((a) => a.is_active);
      const matching = currencyId
        ? active.filter((a) => a.currency === Number(currencyId))
        : active;
      const picked = matching.find((a) => a.is_default)
        ?? (matching.length === 1 ? matching[0] : null);
      return picked
        ? {
            bank_name: picked.bank_name,
            account_number: picked.account_number,
            branch_name: picked.branch_name,
          }
        : null;
    };
    void (async () => {
      const [defaults, ownAccounts] = await Promise.all([
        apiGetObject<{ payee_name?: string; legal_name?: string | null }>(
          `partners/${supplierId}/payment-defaults/?direction=Outgoing`,
        ).catch(() => null),
        accountingApi.getBankAccounts({ activeOnly: true }).catch(() => []),
      ]);
      if (cancelled) return;
      setChequeDefaults(buildPartnerChequeDefaults(
        // اسم المستفيد من كرت المورد (المستفيد أو الاسم القانوني ثم الاسم).
        { id: partner.id, name: partner.name, legal_name: defaults?.payee_name ?? null },
        null,
        "Outgoing",
        ownAccountOf(ownAccounts as BankAccountDto[]),
      ));
    })();
    return () => { cancelled = true; };
  }, [currencyId, initialPartner, partners, supplierId]);

  // T-AUTOPOST: الحفظ يُرحّل مباشرةً حسب إعداد الشركة، والزر الثانوي هو البديل الصريح.
  const submit = useCallback(async (postNow: boolean) => {
    if (!supplierId || !cashAccountId || computedTotal <= 0) {
      setErr("المورد + الصندوق + مبلغ > 0");
      return;
    }
    // T-CHQ3/ط: سطور الشيكات تُفحص قبل الإرسال — الرسالة تسمّي السطر الناقص.
    const chequeError = validateChequeLines(cheques);
    if (chequeError) {
      setErr(chequeError);
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      const saved = await purchaseInvoiceApi.addSupplierPayment({
        partner: Number(supplierId),
        payment_date: paymentDate,
        amount: String(computedTotal.toFixed(2)),
        currency: currencyId ? Number(currencyId) : null,
        cash_or_bank_account: Number(cashAccountId),
        notes: notes || (initialInvoice ? `سند صرف فاتورة ${initialInvoice.number || initialInvoice.id}` : undefined),
        ...(initialInvoice ? { purchase_invoice: initialInvoice.id } : {}),
        // T-ONEPAY: الشيكات جزء من مبلغ السند — تُرسَل ليُدائَن جزؤها على
        // «شيكات برسم الدفع» لا على الصندوق، وتُنشأ شيكات صادرة حقيقية.
        ...(cheques.length > 0
          ? {
              cheques: cheques.map((c) => ({
                cheque_number: c.cheque_number,
                amount: c.amount,
                bank_name: c.bank_name || "",
                account_number: c.account_number || "",
                bank_branch: c.branch || "",
                payee_name: c.payee_name || "",
                due_date: c.due_date || null,
                issue_date: c.issue_date || null,
              })),
            }
          : {}),
        auto_post: postNow,
      });
      // فشل الترحيل التلقائي لا يُضيع السند — يبقى مسودة ونُظهر السبب.
      if (saved?.auto_post_error) {
        setErr(`حُفظ السند كمسودة — تعذّر الترحيل: ${saved.auto_post_error}`);
        setSubmitting(false);
        return;
      }
      onSaved(postNow);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ سند الصرف");
    } finally {
      setSubmitting(false);
    }
  }, [supplierId, cashAccountId, computedTotal, paymentDate, currencyId, notes, cheques, initialInvoice, onSaved]);

  return (
    <PaymentVoucherModal
      title="سند صرف جديد"
      error={err}
      submitting={submitting}
      submitLabel={autoPost ? "حفظ وترحيل" : "حفظ"}
      secondaryLabel={autoPost ? "حفظ كمسودة" : "حفظ وترحيل"}
      onSecondary={() => void submit(!autoPost)}
      onClose={onClose}
      onSubmit={() => void submit(autoPost)}
    >
      {/* ملاحظة عاجلة مستحقة على هذا المورد — تظهر قبل إتمام السند. */}
      <PartnerNoteAlert partnerId={supplierId === "" ? null : supplierId} className="mb-2" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        <label className="aseel-field" style={{ gridColumn: "span 2" }}>
          <span className="aseel-field-label">المورد *</span>
          {lockPartner && initialPartner ? (
            <input className="aseel-input" value={initialPartner.name} readOnly style={{ background: "var(--aseel-surface-2)" }} />
          ) : (
            <select className="aseel-input" value={supplierId} onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">— اختر —</option>
              {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )}
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">التاريخ</span>
          <input type="date" className="aseel-input" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} />
        </label>

        <label className="aseel-field">
          <span className="aseel-field-label">الصندوق / البنك *</span>
          <AccountTreeField
            accounts={accounts}
            value={cashAccountId}
            onChange={(id) => setCashAccountId(id ?? "")}
            isSelectable={isCashAccount}
            title="اختيار الصندوق / البنك"
          />
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">العملة</span>
          <select className="aseel-input" value={currencyId} onChange={(e) => setCurrencyId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">—</option>
            {currencies.map((c) => <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>)}
          </select>
        </label>
        <label className="aseel-field">
          <span className="aseel-field-label">سعر الصرف</span>
          <input type="number" step="0.000001" className="aseel-input aseel-num" value={exchangeRate} onChange={(e) => setExchangeRate(e.target.value)} />
        </label>
      </div>

      <PaymentFinanceFields
        cashAmount={cashAmount}
        onCashAmount={setCashAmount}
        totalCheques={totalCheques}
        total={computedTotal}
        withholdingPct={withholdingPct}
        onWithholdingPct={setWithholdingPct}
        withholdingAmt={withholdingAmt}
        onWithholdingAmt={setWithholdingAmt}
        netLabel="صافي المستحق"
      />

      <ChequeGrid
        cheques={cheques}
        onChange={setCheques}
        onError={setErr}
        direction="Outgoing"
        newLineDefaults={chequeDefaults}
      />

      <label className="aseel-field" style={{ marginTop: "12px", display: "block" }}>
        <span className="aseel-field-label">ملاحظات</span>
        <textarea className="aseel-input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>

      {/* T-CHQ3/و: سطر القيد كما سيُرحَّل — الشيك الصادر التزام على «شيكات برسم
          الدفع» لا نقدٌ خرج من الصندوق. */}
      <div style={{ fontSize: "11px", marginTop: "8px", color: "var(--aseel-ink-soft)" }}>
        القيد: {buildVoucherEntryPreview({
          cashAmount: cashNum,
          chequesAmount: totalCheques,
          cashAccountLabel: (() => {
            const a = accounts.find((x) => x.id === cashAccountId);
            return a ? `${a.code} ${a.name}` : "—";
          })(),
          partnerLabel:
            partners.find((p) => p.id === supplierId)?.name
            || initialPartner?.name || "—",
          direction: "Outgoing",
        }).map((line) => `${line.side} ${line.label} ${formatMoney(line.amount)}`)
          .join(" / ") || "—"}
      </div>
    </PaymentVoucherModal>
  );
};

export default NewSupplierPaymentModal;
