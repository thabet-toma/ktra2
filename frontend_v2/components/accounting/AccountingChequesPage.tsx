import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import type { ChequeDto, AccountingPartner } from "../../types/accounting";
import {
  AseelDocumentShell,
  AseelDenseTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, DenseColumn } from "../aseel";
import { Plus, Save, X, ArrowRightLeft } from "lucide-react";
import OfflineGuard from "../offline/OfflineGuard";
import { formatDateLocalized } from "../../utils/formatDate";

const CHEQUE_STATUSES = [
  { v: "Draft", l: "مسودة" },
  { v: "Under_Collection", l: "قيد التحصيل" },
  { v: "Collected", l: "محصّل" },
  { v: "Bounced", l: "مرتد" },
  { v: "Returned", l: "معاد للعميل" },
  { v: "Settled", l: "مسوّى نقداً" },
];

const DIRECTIONS = [
  { v: "", l: "الكل" },
  { v: "Incoming", l: "وارد" },
  { v: "Outgoing", l: "صادر" },
];

export const AccountingChequesPage: React.FC = () => {
  const [rows, setRows] = useState<ChequeDto[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    cheque_number: "",
    bank_name: "",
    account_number: "",
    bank_branch: "",
    amount: "",
    due_date: "",
    issue_date: new Date().toISOString().split("T")[0],
    payee_name: "",
    direction: "Incoming",
    status: "Draft",
    partner: "",
    currency: "1",
    notes: "",
  });

  // Filters — تاريخ الاستحقاق + شريك + حالة + اتجاه (per N3-T4 spec)
  const [filterDirection, setFilterDirection] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDueFrom, setFilterDueFrom] = useState("");
  const [filterDueTo, setFilterDueTo] = useState("");
  const [filterPartner, setFilterPartner] = useState("");

  // Transfer dialog — task11 R2-A3: الحركة (وليست الحالة) هي ما يُرسل للسيرفر،
  // فيمر التحويل بآلة الانتقالات ويُرحَّل القيد المحاسبي المرافق.
  const [transferCheque, setTransferCheque] = useState<ChequeDto | null>(null);
  const [newMovement, setNewMovement] = useState("");
  const [transferDate, setTransferDate] = useState(new Date().toISOString().split("T")[0]);
  const [transferNotes, setTransferNotes] = useState("");

  const CHEQUE_MOVES: Record<string, { v: string; l: string }[]> = {
    Draft: [
      { v: "deposit", l: "إيداع للتحصيل (بنك)" },
      { v: "withdraw", l: "تحصيل مباشر" },
    ],
    Under_Collection: [
      { v: "collect", l: "تحصيل — دخل الصندوق/البنك" },
      { v: "bounce", l: "ارتداد — إعادة الذمم على العميل" },
    ],
    Bounced: [
      { v: "return_to_customer", l: "إعادة الورقة للعميل" },
      { v: "settle", l: "تسوية نقدية" },
    ],
    Collected: [],
    Returned: [],
    Settled: [],
  };

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [ch, pr] = await Promise.all([
        accountingApi.getCheques(),
        accountingApi.getPartners().catch(() => []),
      ]);
      setRows(ch as ChequeDto[]);
      setPartners(pr as AccountingPartner[]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (!form.cheque_number.trim()) {
      setErr("رقم الشيك مطلوب");
      return;
    }
    setErr(null);
    try {
      await accountingApi.createCheque({
        cheque_number: form.cheque_number.trim(),
        bank_name: form.bank_name || null,
        account_number: form.account_number || null,
        bank_branch: form.bank_branch || null,
        amount: form.amount || "0",
        due_date: form.due_date || null,
        issue_date: form.issue_date || null,
        payee_name: form.payee_name || null,
        direction: form.direction,
        status: form.status,
        partner: form.partner ? parseInt(form.partner, 10) : null,
        currency: parseInt(form.currency, 10) || 1,
        notes: form.notes || null,
      });
      setShowForm(false);
      setForm({
        cheque_number: "",
        bank_name: "",
        account_number: "",
        bank_branch: "",
        amount: "",
        due_date: "",
        issue_date: new Date().toISOString().split("T")[0],
        payee_name: "",
        direction: "Incoming",
        status: "Draft",
        partner: "",
        currency: "1",
        notes: "",
      });
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    }
  };

  const remove = async (id: number) => {
    if (!confirm("حذف الشيك؟")) return;
    try {
      await accountingApi.deleteCheque(id);
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const doTransfer = async () => {
    if (!transferCheque || !newMovement) return;
    try {
      await accountingApi.transferCheque(transferCheque.id, {
        movement_type: newMovement,
        movement_date: transferDate,
        notes: transferNotes,
      });
      setTransferCheque(null);
      setTransferNotes("");
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "فشل التحويل");
    }
  };

  const filteredRows = rows.filter((r) => {
    if (filterDirection && r.direction !== filterDirection) return false;
    if (filterStatus && r.status !== filterStatus) return false;
    // فلتر تاريخ الاستحقاق (per spec)
    if (filterDueFrom && r.due_date && r.due_date < filterDueFrom) return false;
    if (filterDueTo && r.due_date && r.due_date > filterDueTo) return false;
    if (filterPartner && String(r.partner ?? "") !== filterPartner) return false;
    return true;
  });

  const getPartnerName = (id: number | null | undefined) => {
    if (!id) return "—";
    const p = partners.find((x) => x.id === id);
    return p?.name || String(id);
  };

  const columns: DenseColumn<ChequeDto>[] = [
    { key: "cheque_number", header: "رقم الشيك", width: "100px", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.cheque_number}</span> },
    { key: "account_number", header: "رقم الحساب", width: "120px", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.account_number || "—"}</span> },
    { key: "bank_name", header: "البنك", width: "120px", render: (r) => r.bank_name || "—" },
    { key: "bank_branch", header: "الفرع", width: "100px", render: (r) => r.bank_branch || "—" },
    { key: "amount", header: "المبلغ", width: "110px", numeric: true, render: (r) => formatMoney(r.amount) },
    { key: "due_date", header: "تاريخ الاستحقاق", width: "110px", render: (r) => formatDateLocalized(r.due_date) || "—" },
    { key: "issue_date", header: "تاريخ الإصدار", width: "110px", render: (r) => formatDateLocalized(r.issue_date) || "—" },
    { key: "partner", header: "الشريك", width: "140px", render: (r) => getPartnerName(r.partner) },
    {
      key: "account", header: "الحساب", width: "110px",
      render: (r) => {
        const acc = (r as ChequeDto & { account_code?: string; account_name?: string });
        return acc.account_code ? `${acc.account_code}${acc.account_name ? ' — ' + acc.account_name : ''}` : "—";
      },
    },
    {
      key: "direction", header: "الاتجاه",
      render: (r) => (
        <span style={{
          padding: "2px 8px", borderRadius: "12px",
          background: r.direction === "Incoming" ? "var(--color-success,#22c55e)15" : "var(--color-primary,#3b82f6)15",
          color: r.direction === "Incoming" ? "var(--color-success,#16a34a)" : "var(--color-primary,#2563eb)",
          fontSize: "0.75rem",
        }}>
          {r.direction === "Incoming" ? "وارد" : "صادر"}
        </span>
      ),
    },
    {
      key: "status", header: "الحالة",
      render: (r) => <span>{CHEQUE_STATUSES.find((s) => s.v === r.status)?.l || r.status}</span>,
    },
    {
      key: "actions", header: "",
      render: (r) => (
        <button
          type="button"
          className="aseel-toolbtn"
          title="تحويل الشيك"
          onClick={(e) => {
            e.stopPropagation();
            setTransferCheque(r);
            setNewMovement("");
            setTransferDate(new Date().toISOString().split("T")[0]);
            setTransferNotes("");
          }}
        >
          <ArrowRightLeft className="w-3 h-3" />
          تحويل
        </button>
      ),
    },
  ];

  const actions: AseelToolbarAction[] = [
    { key: "new", label: "شيك جديد", icon: <Plus className="w-4 h-4" />, onClick: () => setShowForm(true) },
    { key: "refresh", label: "تحديث", onClick: load },
  ];

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "flex-end" }}>
      <div className="aseel-field">
        <label className="aseel-field-label">الاتجاه</label>
        <select className="aseel-input" value={filterDirection} onChange={(e) => setFilterDirection(e.target.value)}>
          {DIRECTIONS.map((d) => <option key={d.v} value={d.v}>{d.l}</option>)}
        </select>
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">الحالة</label>
        <select className="aseel-input" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="">الكل</option>
          {CHEQUE_STATUSES.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
        </select>
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">استحقاق من</label>
        <input type="date" className="aseel-input" value={filterDueFrom} onChange={(e) => setFilterDueFrom(e.target.value)} />
      </div>
      <div className="aseel-field">
        <label className="aseel-field-label">استحقاق إلى</label>
        <input type="date" className="aseel-input" value={filterDueTo} onChange={(e) => setFilterDueTo(e.target.value)} />
      </div>
      <div className="aseel-field" style={{ minWidth: "160px" }}>
        <label className="aseel-field-label">الشريك</label>
        <select className="aseel-input" value={filterPartner} onChange={(e) => setFilterPartner(e.target.value)}>
          <option value="">الكل</option>
          {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
    </div>
  );

  const tableContent = (
    <AseelDenseTable<ChequeDto>
      columns={columns}
      rows={filteredRows}
      getRowKey={(r) => r.id}
      loading={loading}
      emptyHint="لا توجد شيكات"
    />
  );

  const tabs: AseelTab[] = [
    { key: "list", label: "قائمة الشيكات", content: tableContent },
  ];

  return (
    <div>
      <AseelDocumentShell
        title="الشيكات"
        actions={actions}
        header={filterBar}
        tabs={tabs}
        status={
          <span className="aseel-status-item">{filteredRows.length} شيك</span>
        }
      >
        <></>
      </AseelDocumentShell>

      {/* Add cheque dialog */}
      {showForm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50">
          <div style={{
            background: "var(--aseel-surface)", borderRadius: "var(--aseel-radius)",
            boxShadow: "0 8px 32px #0004", maxWidth: "520px", width: "100%",
            padding: "24px", border: "1px solid var(--aseel-border)", maxHeight: "90vh", overflowY: "auto",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3 style={{ fontWeight: "bold", fontSize: "1.1rem" }}>شيك جديد</h3>
              <button type="button" className="aseel-toolbtn" onClick={() => setShowForm(false)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            {err && <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
            <div style={{ display: "grid", gap: "10px" }}>
              <div className="aseel-field">
                <label className="aseel-field-label">رقم الشيك *</label>
                <input className="aseel-input" value={form.cheque_number}
                  onChange={(e) => setForm((f) => ({ ...f, cheque_number: e.target.value }))} />
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">البنك</label>
                <input className="aseel-input" value={form.bank_name}
                  onChange={(e) => setForm((f) => ({ ...f, bank_name: e.target.value }))} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <div className="aseel-field">
                  <label className="aseel-field-label">رقم الحساب</label>
                  <input className="aseel-input" value={form.account_number}
                    onChange={(e) => setForm((f) => ({ ...f, account_number: e.target.value }))} />
                </div>
                <div className="aseel-field">
                  <label className="aseel-field-label">فرع البنك</label>
                  <input className="aseel-input" value={form.bank_branch}
                    onChange={(e) => setForm((f) => ({ ...f, bank_branch: e.target.value }))} />
                </div>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">المبلغ</label>
                <input type="number" step="0.01" className="aseel-input aseel-num" value={form.amount}
                  onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <div className="aseel-field">
                  <label className="aseel-field-label">تاريخ الإصدار</label>
                  <input type="date" className="aseel-input" value={form.issue_date}
                    onChange={(e) => setForm((f) => ({ ...f, issue_date: e.target.value }))} />
                </div>
                <div className="aseel-field">
                  <label className="aseel-field-label">تاريخ الاستحقاق</label>
                  <input type="date" className="aseel-input" value={form.due_date}
                    onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))} />
                </div>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">اسم المستفيد</label>
                <input className="aseel-input" value={form.payee_name}
                  onChange={(e) => setForm((f) => ({ ...f, payee_name: e.target.value }))} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                <div className="aseel-field">
                  <label className="aseel-field-label">الاتجاه</label>
                  <select className="aseel-input" value={form.direction}
                    onChange={(e) => setForm((f) => ({ ...f, direction: e.target.value }))}>
                    <option value="Incoming">وارد</option>
                    <option value="Outgoing">صادر</option>
                  </select>
                </div>
                <div className="aseel-field">
                  <label className="aseel-field-label">الحالة</label>
                  <select className="aseel-input" value={form.status}
                    onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
                    {CHEQUE_STATUSES.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
                  </select>
                </div>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">الشريك</label>
                <select className="aseel-input" value={form.partner}
                  onChange={(e) => setForm((f) => ({ ...f, partner: e.target.value }))}>
                  <option value="">— اختياري —</option>
                  {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">ملاحظات</label>
                <textarea className="aseel-input" rows={2} value={form.notes}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setShowForm(false)}>إلغاء</button>
              <button type="button" className="aseel-toolbtn" onClick={submit}>
                <Save className="w-4 h-4" />حفظ
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Transfer dialog */}
      {transferCheque && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50">
          <div style={{
            background: "var(--aseel-surface)", borderRadius: "var(--aseel-radius)",
            boxShadow: "0 8px 32px #0004", maxWidth: "420px", width: "100%",
            padding: "24px", border: "1px solid var(--aseel-border)",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3 style={{ fontWeight: "bold" }}>تحويل الشيك #{transferCheque.cheque_number}</h3>
              <button type="button" className="aseel-toolbtn" onClick={() => setTransferCheque(null)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div style={{ display: "grid", gap: "10px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--aseel-ink-soft)" }}>
                الحالة الحالية: <strong>{CHEQUE_STATUSES.find((s) => s.v === transferCheque.status)?.l || transferCheque.status}</strong>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">الحركة</label>
                <select className="aseel-input" value={newMovement} onChange={(e) => setNewMovement(e.target.value)}>
                  <option value="">— اختر الحركة —</option>
                  {(CHEQUE_MOVES[transferCheque.status] || []).map((m) => (
                    <option key={m.v} value={m.v}>{m.l}</option>
                  ))}
                </select>
                {(CHEQUE_MOVES[transferCheque.status] || []).length === 0 && (
                  <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                    حالة نهائية — لا حركات متاحة من «{CHEQUE_STATUSES.find((s) => s.v === transferCheque.status)?.l}»
                  </span>
                )}
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">تاريخ التحويل</label>
                <input type="date" className="aseel-input" value={transferDate}
                  onChange={(e) => setTransferDate(e.target.value)} />
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">ملاحظات</label>
                <textarea className="aseel-input" rows={2} value={transferNotes}
                  onChange={(e) => setTransferNotes(e.target.value)} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setTransferCheque(null)}>إلغاء</button>
              <OfflineGuard
                action="تحويل حالة الشيك"
                warningMessage="تَحويل حالة الشيك يتطلب اتصالاً — state machine يَنفَّذ على الـserver"
              >
                <button type="button" className="aseel-toolbtn" onClick={doTransfer}>
                  <ArrowRightLeft className="w-4 h-4" />تحويل
                </button>
              </OfflineGuard>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
