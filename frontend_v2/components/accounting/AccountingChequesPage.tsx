import React, { useEffect, useState, useCallback } from "react";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import type {
  AccountingPartner,
  BankAccountDto,
  ChequeDto,
  ChequeMovementDto,
} from "../../types/accounting";
import { ChequeWalletPanel } from "./ChequeWalletPanel";
import { NewPaymentModal } from "../sales/SalesCustomerPaymentsPage";
import { NewSupplierPaymentModal } from "../sales/NewSupplierPaymentModal";
import {
  AseelDocumentShell,
  AseelDenseTable,
} from "../aseel";
import type { AseelToolbarAction, AseelTab, DenseColumn } from "../aseel";
import { Plus, X, ArrowRightLeft, Loader2 } from "lucide-react";
import OfflineGuard from "../offline/OfflineGuard";
import { formatDateLocalized, formatDateTimeValue } from "../../utils/formatDate";

const CHEQUE_STATUSES = [
  { v: "Draft", l: "مسودة" },
  { v: "Under_Collection", l: "قيد التحصيل" },
  { v: "Collected", l: "محصّل" },
  { v: "Bounced", l: "مرتد" },
  { v: "Returned", l: "معاد للعميل" },
  { v: "Settled", l: "مسوّى نقداً" },
];

/** حركات تُدخل/تُخرج المال من حساب بنكي فعلي — تحتاج تحديد الحساب. */
const NEEDS_BANK_ACCOUNT = ["collect", "withdraw", "settle"];

const DIRECTIONS = [
  { v: "", l: "الكل" },
  { v: "Incoming", l: "وارد" },
  { v: "Outgoing", l: "صادر" },
];

export const AccountingChequesPage: React.FC = () => {
  const [rows, setRows] = useState<ChequeDto[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  // T-BANKS: حساب الإيداع/الصرف يُختار من حسابات الشركة عند التحويل.
  const [bankAccounts, setBankAccounts] = useState<BankAccountDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const toast = useToast();
  // الحذف والتحويل يولّدان حركة محاسبية على الشيك؛ قفل أثناء التنفيذ يمنع
  // إرسال الطلب مرتين، وتأكيد النجاح يمنع ظنّ المستخدم أن شيئاً لم يحدث.
  const [busy, setBusy] = useState(false);
  const confirm = useConfirm();
  // T-CHQ3: أي سند يُفتح للإدخال — سند قبض للوارد وسند صرف للصادر.
  const [voucher, setVoucher] = useState<"Incoming" | "Outgoing" | null>(null);

  // Filters — تاريخ الاستحقاق + شريك + حالة + اتجاه (per N3-T4 spec)
  const [filterDirection, setFilterDirection] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDueFrom, setFilterDueFrom] = useState("");
  const [filterDueTo, setFilterDueTo] = useState("");
  const [filterPartner, setFilterPartner] = useState("");
  const [activeTab, setActiveTab] = useState("list");

  // Transfer dialog — task11 R2-A3: الحركة (وليست الحالة) هي ما يُرسل للسيرفر،
  // فيمر التحويل بآلة الانتقالات ويُرحَّل القيد المحاسبي المرافق.
  const [transferCheque, setTransferCheque] = useState<ChequeDto | null>(null);
  const [newMovement, setNewMovement] = useState("");
  const [transferDate, setTransferDate] = useState(new Date().toISOString().split("T")[0]);
  const [transferNotes, setTransferNotes] = useState("");
  const [transferBankAccount, setTransferBankAccount] = useState("");
  // T-CHQ2: مسار الشيك — الحركات كانت تُسجَّل في الخادم ولا تُعرض في أي مكان.
  const [movements, setMovements] = useState<ChequeMovementDto[]>([]);
  const [walletKey, setWalletKey] = useState(0);

  // T-CHQ2: الحركة نفسها معناها مختلف حسب الاتجاه — كانت التسميات واردةً دوماً
  // فيقرأ المستخدم «تحصيل — دخل الصندوق» على شيك يخرج من حسابه.
  const CHEQUE_MOVES: Record<string, Record<string, { v: string; l: string }[]>> = {
    Incoming: {
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
    },
    Outgoing: {
      Draft: [
        { v: "deposit", l: "تسليم الشيك للمورد" },
        { v: "withdraw", l: "صرف مباشر من حسابنا" },
      ],
      Under_Collection: [
        { v: "collect", l: "صُرف من حسابنا — إغلاق الالتزام" },
        { v: "bounce", l: "ارتداد — عاد الدين على المورد" },
      ],
      Bounced: [
        { v: "return_to_customer", l: "استرجاع الورقة من المورد" },
        { v: "settle", l: "تسوية نقدية للمورد" },
      ],
      Collected: [],
      Returned: [],
      Settled: [],
    },
  };

  const movesFor = (cheque: ChequeDto) =>
    (CHEQUE_MOVES[cheque.direction] || CHEQUE_MOVES.Incoming)[cheque.status] || [];

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [ch, pr, ba] = await Promise.all([
        accountingApi.getCheques(),
        accountingApi.getPartners().catch(() => []),
        accountingApi.getBankAccounts({ activeOnly: true }).catch(() => []),
      ]);
      setRows(ch as ChequeDto[]);
      setPartners(pr as AccountingPartner[]);
      setBankAccounts(ba as BankAccountDto[]);
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحميل"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const remove = async (id: number) => {
    if (busy) return;
    if (!(await confirm({ message: "حذف الشيك؟" }))) return;
    setBusy(true);
    try {
      await accountingApi.deleteCheque(id);
      toast("تم حذف الشيك", "success");
      await load();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل الحذف"));
    } finally {
      setBusy(false);
    }
  };

  const doTransfer = async () => {
    if (!transferCheque || !newMovement || busy) return;
    setBusy(true);
    try {
      await accountingApi.transferCheque(transferCheque.id, {
        movement_type: newMovement,
        movement_date: transferDate,
        notes: transferNotes,
        ...(transferBankAccount ? { bank_account: parseInt(transferBankAccount, 10) } : {}),
      });
      setTransferCheque(null);
      setTransferNotes("");
      setTransferBankAccount("");
      setWalletKey((k) => k + 1);
      toast("تم تحويل حالة الشيك", "success");
      await load();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحويل"));
    } finally {
      setBusy(false);
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
    { key: "account_number", header: "حساب الساحب", width: "120px", render: (r) => <span style={{ fontFamily: "monospace" }}>{r.account_number || "—"}</span> },
    { key: "bank_name", header: "البنك المسحوب عليه", width: "120px", render: (r) => r.bank_display || r.bank_name || "—" },
    // T-CHQ3: الاسم المكتوب على الورقة (صاحب الشيك في الوارد / المستفيد في الصادر).
    { key: "payee_name", header: "الاسم على الشيك", width: "140px", render: (r) => r.payee_name || "—" },
    { key: "bank_branch", header: "الفرع", width: "100px", render: (r) => r.bank_branch_display || r.bank_branch || "—" },
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
            setMovements([]);
            accountingApi.getChequeMovements(r.id)
              .then((rows) => setMovements(rows as ChequeMovementDto[]))
              .catch(() => setMovements([]));
          }}
        >
          <ArrowRightLeft className="w-3 h-3" />
          تحويل
        </button>
      ),
    },
  ];

  // T-CHQ3: الشيك ليس مستنداً مستقلاً — يدخل الدفاتر ضمن سنده كما في الأنظمة
  // المهنية. فزرّا الإدخال يفتحان سند القبض/الصرف نفسه المستعمل في بطاقة
  // الطرف وفي الفاتورة: بلا توزيع = دفعة على الحساب، وبتوزيع = تسوية فاتورة.
  const actions: AseelToolbarAction[] = [
    {
      key: "new-in", label: "شيك وارد (سند قبض)",
      icon: <Plus className="w-4 h-4" />, onClick: () => setVoucher("Incoming"),
    },
    {
      key: "new-out", label: "شيك صادر (سند صرف)",
      icon: <Plus className="w-4 h-4" />, onClick: () => setVoucher("Outgoing"),
    },
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
    {
      key: "wallet",
      label: "محفظة الشيكات",
      content: (
        <ChequeWalletPanel
          refreshKey={walletKey}
          onPickStatus={(direction, status) => {
            setFilterDirection(direction);
            setFilterStatus(status);
            setActiveTab("list");
          }}
        />
      ),
    },
  ];

  return (
    <div>
      <AseelDocumentShell
        title="الشيكات"
        actions={actions}
        header={filterBar}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        status={
          <span className="aseel-status-item">{filteredRows.length} شيك</span>
        }
      >
        <></>
      </AseelDocumentShell>

      {/* T-CHQ3: إدخال الشيك عبر سنده — نفس النافذة المستعملة في بطاقة الطرف
          وفي الفاتورة، فلا يوجد مسار ثانٍ للشيك ولا قيد موازٍ. */}
      {voucher === "Incoming" && (
        <NewPaymentModal
          onClose={() => setVoucher(null)}
          onSaved={() => { setVoucher(null); void load(); }}
        />
      )}
      {voucher === "Outgoing" && (
        <NewSupplierPaymentModal
          onClose={() => setVoucher(null)}
          onSaved={() => { setVoucher(null); void load(); }}
        />
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
                {transferCheque.direction === "Incoming" ? "شيك وارد" : "شيك صادر"} ·
                الحالة الحالية: <strong>{CHEQUE_STATUSES.find((s) => s.v === transferCheque.status)?.l || transferCheque.status}</strong>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">الحركة</label>
                <select className="aseel-input" value={newMovement} onChange={(e) => setNewMovement(e.target.value)}>
                  <option value="">— اختر الحركة —</option>
                  {movesFor(transferCheque).map((m) => (
                    <option key={m.v} value={m.v}>{m.l}</option>
                  ))}
                </select>
                {movesFor(transferCheque).length === 0 && (
                  <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                    حالة نهائية — لا حركات متاحة من «{CHEQUE_STATUSES.find((s) => s.v === transferCheque.status)?.l}»
                  </span>
                )}
              </div>
              {NEEDS_BANK_ACCOUNT.includes(newMovement) && (
                <div className="aseel-field">
                  <label className="aseel-field-label">حساب الإيداع/التحصيل البنكي</label>
                  <select className="aseel-input" value={transferBankAccount}
                    onChange={(e) => setTransferBankAccount(e.target.value)}>
                    <option value="">— الصندوق الافتراضي —</option>
                    {bankAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.bank_name} — {a.name} ({a.currency_code})
                      </option>
                    ))}
                  </select>
                </div>
              )}
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
              {/* T-CHQ2: مسار الشيك — كل حركة سابقة بتاريخها ومنفّذها. */}
              <div style={{ borderTop: "1px solid var(--aseel-border)", paddingTop: "8px" }}>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--aseel-ink-soft)", marginBottom: "4px" }}>
                  مسار الشيك
                </div>
                {movements.length === 0 ? (
                  <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                    لا حركات سابقة.
                  </span>
                ) : (
                  <ol style={{ display: "grid", gap: "2px", fontSize: "0.8rem" }}>
                    {movements.map((m) => (
                      <li key={m.id} style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
                        <span>
                          {m.movement_type_display}
                          {m.notes ? ` — ${m.notes}` : ""}
                          {m.created_by_name ? ` (${m.created_by_name})` : ""}
                        </span>
                        <span style={{ color: "var(--aseel-ink-soft)", whiteSpace: "nowrap" }}>
                          {formatDateTimeValue(m.created_at)}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setTransferCheque(null)}>إلغاء</button>
              <OfflineGuard
                action="تحويل حالة الشيك"
                warningMessage="تَحويل حالة الشيك يتطلب اتصالاً — state machine يَنفَّذ على الـserver"
              >
                <button type="button" className="aseel-toolbtn" disabled={busy} onClick={doTransfer}>
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRightLeft className="w-4 h-4" />}تحويل
                </button>
              </OfflineGuard>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
