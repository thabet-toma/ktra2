/**
 * N4-T9 — SupplierPaymentsPage (N-F4، جديد) «سند صرف»
 * Ref: task5.md:744-746 + المعاملات المالية.txt:1-80
 *
 * مرآة N4-T4 (CustomerPayments) لكن للموردين:
 *   - Dr Accounts Payable (المورد) / Cr Cash/Bank
 *   - يَدعم نقد + شيكات + خصم المصدر (withholding) + توزيع على فواتير شراء
 *
 * يَعتمد على N8-T12 backend (SupplierPayment + endpoint /purchase/payments/).
 */
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { apiGetList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { accountingApi } from "../../services/accountingApi";
import { purchaseInvoiceApi } from "../../services/purchaseInvoiceApi";
import {
  AseelDocumentShell,
  AseelDenseTable,
  useAseelKeymap,
  type DenseColumn,
  type AseelToolbarAction,
  type AseelTab,
} from "../aseel";
import { Plus, Save, X, RefreshCw, AlertTriangle, Trash2, Banknote } from "lucide-react";

type Partner = { id: number; name: string };
type Account = { id: number; code: string; name: string; account_type?: string };
type Currency = { CurrencyID: number; Code: string };

interface SupplierPaymentRow {
  id: number;
  partner: number;
  partner_name?: string;
  payment_date: string;
  amount: string;
  cash_or_bank_account: number;
  is_posted: boolean;
  journal?: number | null;
  notes?: string | null;
}

interface ChequeLine {
  cheque_number: string;
  payee_name: string;
  due_date: string;
  amount: string;
  bank_name: string;
  branch: string;
}

const newChequeLine = (): ChequeLine => ({
  cheque_number: "",
  payee_name: "",
  due_date: "",
  amount: "",
  bank_name: "",
  branch: "",
});

const fmt = (n: string | number) =>
  Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const SupplierPaymentsPage: React.FC = () => {
  const navigate = useNavigate();
  const today = new Date().toISOString().slice(0, 10);
  const [payments, setPayments] = useState<SupplierPaymentRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [supplierId, setSupplierId] = useState<number | "">("");
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
    setWithholdingAmt(String((computedTotal * (pct / 100)).toFixed(2)));
  }, [withholdingPct, computedTotal]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    const tenantId = resolveTenantId();
    try {
      const [pays, parts, accs, currs] = await Promise.allSettled([
        // T-V1: المسار الصحيح المُسجَّل (api/logistics/supplier-payments/) —
        // كان يستدعي purchase/payments/ غير الموجود فيفشل بـ 404 عند الفتح.
        apiGetList<SupplierPaymentRow>("logistics/supplier-payments/", { tenantId }),
        accountingApi.getPartners() as Promise<Partner[]>,
        accountingApi.getAccounts() as Promise<Account[]>,
        accountingApi.getCurrencies() as Promise<Currency[]>,
      ]);
      if (pays.status === "fulfilled") setPayments(pays.value || []);
      if (parts.status === "fulfilled") setPartners(parts.value || []);
      if (accs.status === "fulfilled") setAccounts(accs.value || []);
      if (currs.status === "fulfilled") setCurrencies(currs.value || []);
      if (pays.status === "rejected") {
        setErr(pays.reason instanceof Error ? pays.reason.message : "فشل تحميل سندات الصرف");
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useAseelKeymap({
    F2: () => window.print(),
    F5: () => void load(),
    F12: () => void submit(),
    Escape: () => {
      if (showForm) {
        setShowForm(false);
      } else {
        navigate(-1);
      }
    },
    CtrlIns: () => setShowForm(true),
  });

  const submit = async () => {
    if (!supplierId || !cashAccountId || computedTotal <= 0) {
      setErr("المورد + الصندوق + مبلغ > 0");
      return;
    }
    setSubmitting(true);
    setErr(null);
    setMsg(null);
    try {
      // T-V1: ينشئ SupplierPayment ويرحّله عبر المسار الصحيح
      // (logistics/supplier-payments/ + /post/). نموذج SupplierPayment مبسّط
      // (مبلغ واحد)، فتفصيل الشيكات/خصم المصدر في الواجهة لا يُحفظ بعد — يُسجّل
      // المبلغ الإجمالي المصروف. (تفصيل الشيكات: خارطة طريق.)
      await purchaseInvoiceApi.addSupplierPayment({
        partner: Number(supplierId),
        payment_date: paymentDate,
        amount: String(computedTotal.toFixed(2)),
        currency: currencyId ? Number(currencyId) : null,
        cash_or_bank_account: Number(cashAccountId),
        notes: notes || undefined,
      });
      setMsg("✓ تم إنشاء سند الصرف وترحيله");
      setShowForm(false);
      // reset
      setSupplierId(""); setCashAmount(""); setCheques([]); setNotes("");
      setWithholdingPct("0"); setWithholdingAmt("0");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل حفظ سند الصرف");
    } finally {
      setSubmitting(false);
    }
  };

  const filtered = payments.filter((p) => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (p.partner_name || "").toLowerCase().includes(s) || String(p.id).includes(s);
  });

  const partnerName = (id: number) => partners.find((p) => p.id === id)?.name || `#${id}`;
  const accountName = (id: number) => {
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} ${a.name}` : `#${id}`;
  };

  const columns: DenseColumn<SupplierPaymentRow>[] = [
    { key: "id", header: "#", width: "60px", align: "center", render: (r) => <span className="font-mono text-xs">#{r.id}</span> },
    { key: "payment_date", header: "التاريخ", width: "110px", align: "center", render: (r) => <span className="text-xs">{r.payment_date}</span> },
    { key: "supplier", header: "المورد", render: (r) => <span className="text-xs">{r.partner_name || partnerName(r.partner)}</span> },
    { key: "amount", header: "المبلغ", width: "120px", align: "left", numeric: true, render: (r) => <span className="aseel-num font-mono text-xs font-semibold">{fmt(r.amount)}</span> },
    { key: "cash_account", header: "الصندوق", render: (r) => <span className="text-xs">{accountName(r.cash_or_bank_account)}</span> },
    {
      key: "status", header: "الحالة", width: "100px", align: "center",
      render: (r) => (
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: r.is_posted ? "var(--aseel-ok, #2d7d46)" : "var(--aseel-warn, #b06800)",
          }}
        >
          {r.is_posted ? `مرحَّل ${r.journal ? "#" + r.journal : ""}` : "مسودة"}
        </span>
      ),
    },
  ];

  const totalPending = payments.filter((p) => !p.is_posted).reduce((s, p) => s + Number(p.amount), 0);
  const totalPosted = payments.filter((p) => p.is_posted).reduce((s, p) => s + Number(p.amount), 0);

  const actions: AseelToolbarAction[] = [
    { key: "new", label: "سند صرف جديد (Ctrl+Ins)", icon: <Plus />, onClick: () => setShowForm(true) },
    {
      key: "refresh",
      label: "تحديث",
      icon: <RefreshCw className={loading ? "animate-spin" : ""} />,
      onClick: () => void load(),
      separatorBefore: true,
    },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: () => {
        if (showForm) {
          setShowForm(false);
        } else {
          navigate(-1);
        }
      },
      danger: true,
      separatorBefore: true,
    },
  ];

  const tabs: AseelTab[] = [
    {
      key: "list",
      label: "سندات الصرف",
      content: (
        <div style={{ padding: "8px" }}>
          {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
          {msg && <div className="aseel-banner" style={{ marginBottom: "8px", color: "var(--aseel-ok, #2d7d46)" }}>{msg}</div>}

          <div className="aseel-banner" style={{ marginBottom: "8px", background: "var(--aseel-surface-2, #f4ede0)", fontSize: "11px", padding: "8px 12px" }}>
            <AlertTriangle className="w-3 h-3 inline" style={{ marginInlineEnd: "4px", color: "var(--aseel-warn, #b06800)" }} />
            يُسجَّل المبلغ الإجمالي المصروف ويُرحَّل (Dr ذمم المورد / Cr الصندوق).
            تفصيل الشيكات وخصم المصدر لا يُحفظان بعد (نموذج مبسّط) — قيد التطوير.
          </div>

          <AseelDenseTable<SupplierPaymentRow>
            columns={columns}
            rows={filtered}
            getRowKey={(r) => r.id}
            loading={loading}
            emptyHint="لا سندات صرف — اضغط Ctrl+Ins للإضافة"
          />
        </div>
      ),
    },
  ];

  return (
    <div data-skin="aseel" style={{ minHeight: "calc(100vh - 5rem)" }}>
      <AseelDocumentShell
        title="سندات الصرف للموردين"
        state={`${filtered.length} سند`}
        actions={actions}
        header={
          <label className="aseel-field" style={{ flex: 1, minWidth: "200px" }}>
            <span className="aseel-field-label">بحث (مورد / رقم)</span>
            <input
              className="aseel-input"
              data-aseel-field="search"
              placeholder="بحث... (F6)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
        }
        tabs={tabs}
        status={
          <>
            <span className="aseel-status-item"><Banknote className="w-3 h-3 inline" /> {filtered.length} سند</span>
            <span className="aseel-status-item">مرحَّل <b className="aseel-num">{fmt(totalPosted)}</b></span>
            <span className="aseel-status-item" style={{ color: "var(--aseel-warn, #b06800)" }}>
              مسودة <b className="aseel-num">{fmt(totalPending)}</b>
            </span>
          </>
        }
      />

      {/* Form modal */}
      {showForm && (
        <div
          className="fixed inset-0 z-[60] bg-black/40"
          style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "16px" }}
          onMouseDown={(e) => { if (e.target === e.currentTarget) setShowForm(false); }}
        >
          <div
            style={{
              background: "var(--aseel-surface, #fff)",
              border: "1px solid var(--aseel-border, #c8b99a)",
              borderRadius: "var(--aseel-radius, 6px)",
              width: "100%",
              maxWidth: "780px",
              maxHeight: "90vh",
              overflow: "auto",
              padding: "16px",
            }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid var(--aseel-border)", paddingBottom: "8px" }}>
              <h3 style={{ fontWeight: 600, fontSize: "14px" }}>سند صرف جديد</h3>
              <button type="button" className="aseel-toolbtn" onClick={() => setShowForm(false)}>
                <X className="w-3 h-3" />
              </button>
            </div>

            {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
              <label className="aseel-field" style={{ gridColumn: "span 2" }}>
                <span className="aseel-field-label">المورد *</span>
                <select className="aseel-input" value={supplierId} onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")}>
                  <option value="">— اختر —</option>
                  {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
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
                  <span className="aseel-field-label">نقدا (Space=remaining)</span>
                  <input
                    type="number" step="0.01"
                    data-aseel-field="remaining-amount"
                    className="aseel-input aseel-num"
                    value={cashAmount}
                    onChange={(e) => setCashAmount(e.target.value)}
                  />
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
                    if (computedTotal > 0) setWithholdingPct(((Number(e.target.value) || 0) / computedTotal * 100).toFixed(2));
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
              <button type="button" className="aseel-toolbtn" onClick={() => setShowForm(false)}>إلغاء</button>
              <button
                type="button"
                className="aseel-toolbtn"
                disabled={submitting}
                onClick={() => void submit()}
                style={{ background: "var(--aseel-ok, #2d7d46)", color: "#fff" }}
              >
                <Save className="w-3 h-3" /> {submitting ? "..." : "حفظ السند (F12)"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
