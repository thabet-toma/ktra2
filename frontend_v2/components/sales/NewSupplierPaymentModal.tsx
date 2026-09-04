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
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { AlertCircle, Info, Undo2, X } from "lucide-react";
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
import { formatTimeValue } from "../../utils/formatDate";
import { buildVoucherEntryPreview } from "../../utils/voucherEntryPreview";
import { PartnerNoteAlert } from "../partners/PartnerNoteAlert";
import { AccountTreeField } from "../accounting/AccountTreePicker";
import {
  ChequeGrid,
  PaymentFinanceFields,
  PaymentVoucherModal,
  type ChequeLine,
} from "./PaymentVoucherParts";
import { useDocumentDraft } from "../../hooks/useDocumentDraft";
import { orphanDraftsBannerText } from "../../utils/documentDraft";

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

  // ISSUE #121: مسودّة محلية عبر الخطّاف المشترك (issue #118) — توأم سند القبض
  // في `SalesCustomerPaymentsPage.tsx`. مستندٌ جديد دائماً (لا تحرير سندٍ قائم
  // عبر هذه النافذة)، فـ`docId` ثابتٌ على `null` و`isPosted` تبقى `false`.
  // «لُمِس» حالةٌ تُرفَع مباشرةً داخل كل معالج تغيير — لا اشتقاقاً من الحمولة
  // داخل أثرٍ يجري بعد الرسم (الدرس المكلف في issue #121).
  const [touched, setTouched] = useState(false);
  const markTouched = () => setTouched(true);

  const draftPayload = useMemo(
    () => ({
      supplierId, paymentDate, cashAmount, cashAccountId, currencyId, exchangeRate,
      notes, withholdingPct, withholdingAmt, cheques,
    }),
    [supplierId, paymentDate, cashAmount, cashAccountId, currencyId, exchangeRate, notes, withholdingPct, withholdingAmt, cheques],
  );

  const onRestoreDraft = useCallback((p: {
    supplierId: number | "";
    paymentDate: string;
    cashAmount: string;
    cashAccountId: number | "";
    currencyId: number | "";
    exchangeRate: string;
    notes: string;
    withholdingPct: string;
    withholdingAmt: string;
    cheques: ChequeLine[];
  }) => {
    setSupplierId(p.supplierId);
    setPaymentDate(p.paymentDate);
    setCashAmount(p.cashAmount);
    setCashAccountId(p.cashAccountId);
    setCurrencyId(p.currencyId);
    setExchangeRate(p.exchangeRate);
    setNotes(p.notes);
    setWithholdingPct(p.withholdingPct);
    setWithholdingAmt(p.withholdingAmt);
    setCheques(p.cheques || []);
    setTouched(true);
  }, []);

  const {
    draftSavedAt,
    draftSaveFailed,
    restoredBanner: draftBanner,
    discardDraft,
    orphanDrafts,
  } = useDocumentDraft({
    docType: "supplier_payment_voucher",
    docId: null,
    payload: draftPayload,
    isTouched: touched,
    onRestore: onRestoreDraft,
    isPosted: false,
    docUpdatedAt: null,
  });

  /* الحارسُ مقلوب — يعترض المغادرة فقط إن فشل الحفظ المحلي فعلاً (مرآة
     `InvoiceForm.tsx`، issue #120). */
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (draftSaveFailed) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [draftSaveFailed]);

  const [orphanBarDismissed, setOrphanBarDismissed] = useState(false);

  const handleUndoDraft = useCallback(() => {
    setSupplierId(initialPartner?.id ?? "");
    setPaymentDate(today);
    setCashAmount(initialInvoice ? String(initialInvoice.remaining) : "");
    setCashAccountId("");
    setCurrencyId("");
    setExchangeRate("1");
    setNotes("");
    setWithholdingPct("0");
    setWithholdingAmt("0");
    setCheques([]);
    setTouched(false);
    void discardDraft();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPartner, initialInvoice, today, discardDraft]);

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
      {/* ISSUE #121: الحفظ المحلي فشل فعلاً — لافتةٌ لاصقة تطلب حفظاً يدوياً. */}
      {draftSaveFailed && (
        <div
          role="alert"
          aria-live="assertive"
          data-testid="draft-save-failed-banner"
          className="mb-2 flex items-center gap-2 rounded border border-red-200 bg-red-100 px-3 py-2 text-[11px] font-medium text-red-800"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>تعذّر حفظ نسخة محلية من هذا السند — اضغط «حفظ» يدوياً كي لا يضيع عملك.</span>
        </div>
      )}
      {/* ISSUE #121: شريط الاستعادة التلقائية — بلا لافتة تسأل. */}
      {draftBanner && (
        <div className="ktra-banner ktra-banner--warn mb-2" role="status" data-testid="draft-restored-banner">
          <Info className="h-4 w-4 shrink-0" />
          <span>
            {draftBanner.eligibility === "restore" &&
              `استُعيدت مسودةٌ غير محفوظة (${formatTimeValue(draftBanner.updatedAt)})`}
            {draftBanner.eligibility === "stale" &&
              `تغيّر السند بعد مسودتك (مسودتُك ${formatTimeValue(draftBanner.updatedAt)})`}
            {draftBanner.eligibility === "posted" &&
              `توجد مسودّةٌ محلية غير محفوظة (${formatTimeValue(draftBanner.updatedAt)}) — للاطّلاع فقط.`}
          </span>
          {draftBanner.eligibility === "restore" && (
            <button type="button" className="ktra-toolbtn" onClick={handleUndoDraft} data-testid="draft-restored-undo">
              <Undo2 className="h-4 w-4" /> تراجع
            </button>
          )}
          {draftBanner.eligibility === "stale" && (
            <>
              <button type="button" className="ktra-toolbtn" onClick={() => onRestoreDraft(draftBanner.payload)} data-testid="draft-stale-preview">
                استعرض مسودتي
              </button>
              <button type="button" className="ktra-toolbtn" onClick={() => void discardDraft()} data-testid="draft-stale-discard">
                تجاهلها
              </button>
            </>
          )}
        </div>
      )}
      {/* ISSUE #121: شريط اليتامى — مسودّات سندٍ صرفٍ جديد أخرى تُركت بتبويبات أخرى. */}
      {orphanDrafts.length > 0 && !orphanBarDismissed && (
        <div className="ktra-banner mb-2" role="status" data-testid="orphan-drafts-banner">
          <Info className="h-4 w-4 shrink-0" />
          <div className="flex flex-col gap-1">
            <span>{orphanDraftsBannerText(orphanDrafts.length)}</span>
            <ul className="list-disc pr-4 text-xs">
              {orphanDrafts.map((o) => (
                <li key={o.key}>{formatTimeValue(o.updatedAt)} — {o.previewLine || "—"}</li>
              ))}
            </ul>
          </div>
          <button type="button" className="ktra-toolbtn" onClick={() => setOrphanBarDismissed(true)} data-testid="orphan-drafts-dismiss">
            <X className="h-4 w-4" /> إخفاء
          </button>
        </div>
      )}
      {/* ملاحظة عاجلة مستحقة على هذا المورد — تظهر قبل إتمام السند. */}
      <PartnerNoteAlert partnerId={supplierId === "" ? null : supplierId} className="mb-2" />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        <label className="ktra-field" style={{ gridColumn: "span 2" }}>
          <span className="ktra-field-label">المورد *</span>
          {lockPartner && initialPartner ? (
            <input className="ktra-input" value={initialPartner.name} readOnly style={{ background: "var(--ktra-surface-2)" }} />
          ) : (
            <select className="ktra-input" value={supplierId} onChange={(e) => { setSupplierId(e.target.value ? Number(e.target.value) : ""); markTouched(); }}>
              <option value="">— اختر —</option>
              {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          )}
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">التاريخ</span>
          <input type="date" className="ktra-input" value={paymentDate} onChange={(e) => { setPaymentDate(e.target.value); markTouched(); }} />
        </label>

        <label className="ktra-field">
          <span className="ktra-field-label">الصندوق / البنك *</span>
          <AccountTreeField
            accounts={accounts}
            value={cashAccountId}
            onChange={(id) => { setCashAccountId(id ?? ""); markTouched(); }}
            purpose="cash"
            title="اختيار الصندوق / البنك"
          />
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">العملة</span>
          <select className="ktra-input" value={currencyId} onChange={(e) => { setCurrencyId(e.target.value ? Number(e.target.value) : ""); markTouched(); }}>
            <option value="">—</option>
            {currencies.map((c) => <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>)}
          </select>
        </label>
        <label className="ktra-field">
          <span className="ktra-field-label">سعر الصرف</span>
          <input type="number" step="0.000001" className="ktra-input ktra-num" value={exchangeRate} onChange={(e) => { setExchangeRate(e.target.value); markTouched(); }} />
        </label>
      </div>

      <PaymentFinanceFields
        cashAmount={cashAmount}
        onCashAmount={(v) => { setCashAmount(v); markTouched(); }}
        totalCheques={totalCheques}
        total={computedTotal}
        withholdingPct={withholdingPct}
        onWithholdingPct={(v) => { setWithholdingPct(v); markTouched(); }}
        withholdingAmt={withholdingAmt}
        onWithholdingAmt={(v) => { setWithholdingAmt(v); markTouched(); }}
        netLabel="صافي المستحق"
      />

      <ChequeGrid
        cheques={cheques}
        onChange={(next) => { setCheques(next); markTouched(); }}
        onError={setErr}
        direction="Outgoing"
        newLineDefaults={chequeDefaults}
      />

      <label className="ktra-field" style={{ marginTop: "12px", display: "block" }}>
        <span className="ktra-field-label">ملاحظات</span>
        <textarea className="ktra-input" rows={2} placeholder="ملاحظات السند…" value={notes} onChange={(e) => { setNotes(e.target.value); markTouched(); }} />
      </label>

      {/* ISSUE #121: مؤشّر «حُفظ HH:mm» — لا يضغط المستخدم «حفظ» احتياطاً. */}
      {draftSavedAt && (
        <div style={{ fontSize: "11px", marginTop: "6px", color: "var(--ktra-ink-soft)" }} data-testid="draft-saved-indicator">
          مسودة محلية — حُفظ {formatTimeValue(draftSavedAt)}
        </div>
      )}

      {/* T-CHQ3/و: سطر القيد كما سيُرحَّل — الشيك الصادر التزام على «شيكات برسم
          الدفع» لا نقدٌ خرج من الصندوق. */}
      <div style={{ fontSize: "11px", marginTop: "8px", color: "var(--ktra-ink-soft)" }}>
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
