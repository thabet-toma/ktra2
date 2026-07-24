/**
 * NewSupplierPaymentModal — «سند صرف» قابل لإعادة الاستخدام.
 *
 * مرآة {@link NewPaymentModal} (سند القبض للعميل): نموذج مشترك يُستهلك في صفحة
 * سندات صرف الموردين وفي بطاقة الشريك (كبسة سريعة على المورد). يحمّل حساباته
 * وعملاته ومورّديه ذاتياً؛ عند تثبيت المورد (`lockPartner`) يُعرَض اسمه فقط.
 *
 * القيد المحاسبي: Dr ذمم المورد / Cr الصندوق/البنك — عبر
 * `purchaseInvoiceApi.addSupplierPayment` (نموذج مبسّط بمبلغ إجمالي؛ تفصيل
 * الشيكات/خصم المصدر في الواجهة لا يُحفَظ بعد، كما في الصفحة الأصلية).
 */
import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import { formatMoney, formatNumber } from "@/utils/formatNumber";
import { Plus, Save, X, Trash2 } from "lucide-react";

export type SupplierPaymentPartner = { id: number; name: string };
/** صف الشريك كما يعيده lookup (يحمل النوع) — نفلتره على الموردين فقط. */
type PartnerRow = SupplierPaymentPartner & { partner_type?: string };
type Account = { id: number; code: string; name: string; account_type?: string };

const isSupplierRow = (p: PartnerRow) =>
  String(p.partner_type || "").toLowerCase() === "supplier";
type Currency = { CurrencyID: number; Code: string };

interface ChequeLine {
  cheque_number: string;
  payee_name: string;
  due_date: string;
  amount: string;
  bank_name: string;
  branch: string;
}

const newChequeLine = (): ChequeLine => ({
  cheque_number: "", payee_name: "", due_date: "", amount: "", bank_name: "", branch: "",
});

const fmt = (n: string | number) => formatMoney(n);

interface Props {
  /** المورد المثبّت مسبقاً (من بطاقة الشريك مثلاً). */
  initialPartner?: SupplierPaymentPartner | null;
  /** يمنع تغيير المورد ويعرض اسمه فقط. */
  lockPartner?: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export const NewSupplierPaymentModal: React.FC<Props> = ({
  initialPartner,
  lockPartner = false,
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
  const [cashAmount, setCashAmount] = useState("");
  const [cashAccountId, setCashAccountId] = useState<number | "">("");
  const [currencyId, setCurrencyId] = useState<number | "">("");
  const [exchangeRate, setExchangeRate] = useState("1");
  const [notes, setNotes] = useState("");
  const [withholdingPct, setWithholdingPct] = useState("0");
  const [withholdingAmt, setWithholdingAmt] = useState("0");
  const [cheques, setCheques] = useState<ChequeLine[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const totalCheques = cheques.reduce((s, c) => s + (Number(c.amount) || 0), 0);
  const cashNum = Number(cashAmount) || 0;
  const computedTotal = cashNum + totalCheques;
  const netAfterWh = Math.max(0, computedTotal - (Number(withholdingAmt) || 0));

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
      const [accs, currs, parts] = await Promise.allSettled(tasks);
      if (!alive) return;
      if (accs.status === "fulfilled") setAccounts(accs.value || []);
      if (currs.status === "fulfilled") setCurrencies(currs.value || []);
      if (parts.status === "fulfilled") {
        // المورد المثبّت مسبقاً يمرّ كما هو؛ وإلا نعرض الموردين فقط (لا العملاء).
        const list = parts.value || [];
        setPartners((lockPartner && initialPartner) ? list : list.filter(isSupplierRow));
      }
    })();
    return () => { alive = false; };
  }, [lockPartner, initialPartner]);

  const submit = useCallback(async () => {
    if (!supplierId || !cashAccountId || computedTotal <= 0) {
      setErr("المورد + الصندوق + مبلغ > 0");
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      await purchaseInvoiceApi.addSupplierPayment({
        partner: Number(supplierId),
        payment_date: paymentDate,
        amount: String(computedTotal.toFixed(2)),
        currency: currencyId ? Number(currencyId) : null,
        cash_or_bank_account: Number(cashAccountId),
        notes: notes || undefined,
      });
      onSaved();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ سند الصرف");
    } finally {
      setSubmitting(false);
    }
  }, [supplierId, cashAccountId, computedTotal, paymentDate, currencyId, notes, onSaved]);

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/40"
      style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "16px" }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        dir="rtl"
        style={{
          background: "var(--aseel-surface, #fff)",
          border: "1px solid var(--aseel-border, #c8b99a)",
          borderRadius: "var(--aseel-radius, 6px)",
          width: "100%", maxWidth: "780px", maxHeight: "90vh", overflow: "auto", padding: "16px",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid var(--aseel-border)", paddingBottom: "8px" }}>
          <h3 style={{ fontWeight: 600, fontSize: "14px" }}>سند صرف جديد</h3>
          <button type="button" className="aseel-toolbtn" onClick={onClose}>
            <X className="w-3 h-3" />
          </button>
        </div>

        {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}

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
            <select className="aseel-input" value={cashAccountId} onChange={(e) => setCashAccountId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">— اختر —</option>
              {accounts.filter((a) => (a.account_type === "Asset") && /^110|صندوق|بنك|cash|bank/i.test(`${a.code} ${a.name}`)).map((a) => (
                <option key={a.id} value={a.id}>{a.code} {a.name}</option>
              ))}
            </select>
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

        {/* الحقول المالية */}
        <div style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.3)", borderRadius: "4px", padding: "8px", marginTop: "12px" }}>
          <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--aseel-warn, #b06800)", marginBottom: "6px" }}>حقول الدفع</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
            <label className="aseel-field">
              <span className="aseel-field-label">نقدا</span>
              <input type="number" step="0.01" className="aseel-input aseel-num" value={cashAmount} onChange={(e) => setCashAmount(e.target.value)} />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">مجموع الشيكات (auto)</span>
              <input type="text" readOnly className="aseel-input aseel-num" value={fmt(totalCheques)} style={{ background: "var(--aseel-surface-2)" }} />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">المجموع</span>
              <input type="text" readOnly className="aseel-input aseel-num" value={fmt(computedTotal)} style={{ background: "var(--aseel-surface-2)", fontWeight: 700 }} />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">نسبة خصم المصدر %</span>
              <input type="number" step="0.01" className="aseel-input aseel-num" value={withholdingPct} onChange={(e) => setWithholdingPct(e.target.value)} />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">مبلغ خصم المصدر</span>
              <input type="number" step="0.01" className="aseel-input aseel-num" value={withholdingAmt} onChange={(e) => {
                setWithholdingAmt(e.target.value);
                if (computedTotal > 0) setWithholdingPct(formatNumber((Number(e.target.value) || 0) / computedTotal * 100, { maxDecimals: 2 }));
              }} />
            </label>
            <label className="aseel-field">
              <span className="aseel-field-label">صافي المستحق</span>
              <input type="text" readOnly className="aseel-input aseel-num" value={fmt(netAfterWh)} style={{ background: "var(--aseel-ok-bg, #e3f6e9)", color: "var(--aseel-ok, #2d7d46)", fontWeight: 700 }} />
            </label>
          </div>
        </div>

        {/* شيكات */}
        <div style={{ marginTop: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
            <span style={{ fontWeight: 600, fontSize: "12px" }}>شيكات السند</span>
            <button type="button" className="aseel-toolbtn" onClick={() => setCheques((cs) => [...cs, newChequeLine()])} style={{ fontSize: "11px" }}>
              <Plus className="w-3 h-3" /> شيك
            </button>
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
                  <th style={{ padding: "4px" }}>المستفيد</th>
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
                    <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.cheque_number} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, cheque_number: e.target.value } : x))} /></td>
                    <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.payee_name} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, payee_name: e.target.value } : x))} /></td>
                    <td style={{ padding: "2px" }}><input type="date" className="aseel-input" style={{ fontSize: "11px" }} value={c.due_date} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, due_date: e.target.value } : x))} /></td>
                    <td style={{ padding: "2px" }}><input type="number" step="0.01" className="aseel-input aseel-num" style={{ fontSize: "11px" }} value={c.amount} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, amount: e.target.value } : x))} /></td>
                    <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.bank_name} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, bank_name: e.target.value } : x))} /></td>
                    <td style={{ padding: "2px" }}><input className="aseel-input" style={{ fontSize: "11px" }} value={c.branch} onChange={(e) => setCheques((cs) => cs.map((x, j) => i === j ? { ...x, branch: e.target.value } : x))} /></td>
                    <td style={{ padding: "2px", textAlign: "center" }}>
                      <button type="button" onClick={() => setCheques((cs) => cs.filter((_, j) => j !== i))} style={{ color: "var(--aseel-err, #c0392b)" }}>
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <label className="aseel-field" style={{ marginTop: "12px", display: "block" }}>
          <span className="aseel-field-label">ملاحظات</span>
          <textarea className="aseel-input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
          <button type="button" className="aseel-toolbtn" onClick={onClose}>إلغاء</button>
          <button
            type="button"
            className="aseel-toolbtn"
            disabled={submitting}
            onClick={() => void submit()}
            style={{ background: "var(--aseel-ok, #2d7d46)", color: "#fff" }}
          >
            <Save className="w-3 h-3" /> {submitting ? "..." : "حفظ السند"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default NewSupplierPaymentModal;
