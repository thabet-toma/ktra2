import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
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
import { ChequeMaturityPanel } from "./ChequeMaturityPanel";
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

const DIRECTIONS = [
  { v: "", l: "الكل" },
  { v: "Incoming", l: "وارد" },
  { v: "Outgoing", l: "صادر" },
];

export const AccountingChequesPage: React.FC = () => {
  const navigate = useNavigate();
  const [rows, setRows] = useState<ChequeDto[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  // CHQ-4: التظهير يُسدَّد به مورد — قيدُه مدين ذممه، فالقائمة موردون لا كل الأطراف.
  const [suppliers, setSuppliers] = useState<AccountingPartner[]>([]);
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
  // CHQ-4: المستفيد من التظهير — يُطلب فقط حين تعلن الحركة `requires_endorsee`.
  const [transferEndorsee, setTransferEndorsee] = useState("");
  // T-CHQ2: مسار الشيك — الحركات كانت تُسجَّل في الخادم ولا تُعرض في أي مكان.
  const [movements, setMovements] = useState<ChequeMovementDto[]>([]);
  const [walletKey, setWalletKey] = useState(0);

  // CHQ-4: لا جدول انتقالات ولا جدول تسميات في الواجهة بعد اليوم. الحركات
  // المتاحة وتسمياتها وما تطلبه من مدخلات تصل مع كل شيك (`allowed_movements`)،
  // فحالةٌ جديدة في الخادم تظهر هنا، وحركةٌ مُنعت هناك تختفي من الشاشة بدل أن
  // تبقى زرّاً يعطي 400.
  const moves = transferCheque?.allowed_movements ?? [];
  const selectedMove = moves.find((m) => m.value === newMovement) || null;

  // CHQ-4: تسمية الحالة بدلالة الاتجاه — تُقرأ من الشيكات المحمّلة نفسها
  // (`status_label` من الخادم)، فالمحفظة والقائمة والنافذة تنطق بتسمية واحدة.
  const statusLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of rows) {
      if (r.status_label) map.set(`${r.direction}|${r.status}`, r.status_label);
    }
    return map;
  }, [rows]);

  const statusLabelFor = useCallback(
    (direction: string, status: string) =>
      statusLabels.get(`${direction}|${status}`) || status,
    [statusLabels],
  );

  // فلتر الحالة يعرض الحالات الموجودة فعلاً في هذا الاتجاه — بتسمياتها الصحيحة.
  // حالةٌ مختارة لم تعد ضمنها تبقى معروضة كي لا يتغيّر فلتر المستخدم من تحته.
  const statusOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const r of rows) {
      if (filterDirection && r.direction !== filterDirection) continue;
      if (!seen.has(r.status)) seen.set(r.status, r.status_label || r.status);
    }
    if (filterStatus && !seen.has(filterStatus)) {
      seen.set(filterStatus, statusLabelFor(filterDirection || "Incoming", filterStatus));
    }
    return [...seen.entries()].map(([v, l]) => ({ v, l }));
  }, [rows, filterDirection, filterStatus, statusLabelFor]);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [ch, pr, ba, sup] = await Promise.all([
        accountingApi.getCheques(),
        accountingApi.getPartners().catch(() => []),
        accountingApi.getBankAccounts({ activeOnly: true }).catch(() => []),
        accountingApi.getPartners("Supplier").catch(() => []),
      ]);
      setRows(ch as ChequeDto[]);
      setPartners(pr as AccountingPartner[]);
      setBankAccounts(ba as BankAccountDto[]);
      setSuppliers(sup as AccountingPartner[]);
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
    setErr(null);
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
    setErr(null);
    try {
      await accountingApi.transferCheque(transferCheque.id, {
        movement_type: newMovement,
        movement_date: transferDate,
        notes: transferNotes,
        ...(selectedMove?.requires_bank_account && transferBankAccount
          ? { bank_account: parseInt(transferBankAccount, 10) } : {}),
        ...(selectedMove?.requires_endorsee && transferEndorsee
          ? { endorsed_to: parseInt(transferEndorsee, 10) } : {}),
      });
      setTransferCheque(null);
      setTransferNotes("");
      setTransferBankAccount("");
      setTransferEndorsee("");
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
      render: (r) => <span>{r.status_label || r.status}</span>,
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
            setErr(null);
            setNewMovement("");
            setTransferDate(new Date().toISOString().split("T")[0]);
            setTransferNotes("");
            setTransferBankAccount("");
            setTransferEndorsee("");
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
          {statusOptions.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
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
          statusLabel={statusLabelFor}
          onPickStatus={(direction, status) => {
            setFilterDirection(direction);
            setFilterStatus(status);
            setActiveTab("list");
          }}
        />
      ),
    },
    // CHQ-4: المحفظة تقول كم في اليد، وهذا التبويب يقول **متى** — أسبوعاً
    // بأسبوع بصافٍ تراكمي، من تقرير `cheques-maturity` كما يبنيه الخادم.
    {
      key: "maturity",
      label: "الاستحقاق والسيولة",
      content: <ChequeMaturityPanel refreshKey={walletKey} />,
    },
  ];

  return (
    <div>
      {/* CHQ-5: رفض الخادم كان يُكتب في `err` ولا يُعرض في أي مكان — والحارس
          الجديد (سند غير مرحّل، انتقال غير مسموح) يردّ هنا. الرسالة تظهر داخل
          نافذة التحويل حين تكون مفتوحة لأن النافذة تغطّي الصفحة، وعلى الصفحة
          نفسها حين يكون الفشل في التحميل أو الحذف. */}
      {err && !transferCheque && (
        <div className="aseel-banner aseel-banner--err" data-testid="cheque-page-error"
          style={{ marginBottom: "8px" }}>{err}</div>
      )}
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
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50"
          data-testid="cheque-transfer-dialog">
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
                الحالة الحالية: <strong>{transferCheque.status_label || transferCheque.status}</strong>
              </div>
              <div className="aseel-field">
                <label className="aseel-field-label">الحركة</label>
                <select className="aseel-input" data-testid="cheque-move-select"
                  value={newMovement} onChange={(e) => setNewMovement(e.target.value)}>
                  <option value="">— اختر الحركة —</option>
                  {moves.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
                {moves.length === 0 && (
                  <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                    حالة نهائية — لا حركات متاحة من «{transferCheque.status_label || transferCheque.status}»
                  </span>
                )}
              </div>
              {selectedMove?.requires_bank_account && (
                <div className="aseel-field">
                  <label className="aseel-field-label">حساب الإيداع/التحصيل البنكي</label>
                  <select className="aseel-input" data-testid="cheque-bank-select"
                    value={transferBankAccount}
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
              {/* CHQ-4: التظهير يسدّد مورداً بالورقة بدل النقد — بلا مستفيدٍ لا
                  يكون للحركة قيد ذمم، فالحقل شرطٌ لا اختيار. */}
              {selectedMove?.requires_endorsee && (
                <div className="aseel-field">
                  <label className="aseel-field-label">المورد المستفيد من التظهير</label>
                  <select className="aseel-input" data-testid="cheque-endorsee-select"
                    value={transferEndorsee}
                    onChange={(e) => setTransferEndorsee(e.target.value)}>
                    <option value="">— اختر المورد —</option>
                    {suppliers.map((sup) => (
                      <option key={sup.id} value={sup.id}>{sup.name}</option>
                    ))}
                  </select>
                  {!transferEndorsee && (
                    <span style={{ fontSize: "0.75rem", color: "var(--aseel-ink-soft)" }}>
                      تنخفض ذمة هذا المورد بقيمة الشيك عند التظهير.
                    </span>
                  )}
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
              {/* T-CHQ2 · CHQ-4: مسار الشيك — كل خطوة بتاريخها ومنفّذها **وقيدها**.
                  رقم القيد رابطٌ إلى شاشة القيد ولا مبلغ بجانبه عمداً: سند قبض
                  موزَّع على فاتورتين يشقّ مبلغ الشيك على قيدين (THA-489)، فرقمٌ
                  هنا كان سيزعم أنه «قيد مبلغ هذا الشيك». القيد يتكلّم عن نفسه. */}
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
                      <li key={m.id} data-testid="cheque-movement-row"
                        style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
                        <span>
                          {m.movement_type_label || m.movement_type_display}
                          {m.notes ? ` — ${m.notes}` : ""}
                          {m.created_by_name ? ` (${m.created_by_name})` : ""}
                        </span>
                        <span style={{ color: "var(--aseel-ink-soft)", whiteSpace: "nowrap", display: "flex", gap: "8px" }}>
                          {m.journal ? (
                            <button
                              type="button"
                              data-testid="cheque-journal-link"
                              className="text-[var(--color-accent,#2563eb)] underline-offset-2 hover:underline"
                              title={`فتح القيد${m.journal_date ? ` — ${formatDateLocalized(m.journal_date)}` : ""}`}
                              onClick={() => navigate(`/accounting/journals/${m.journal}`)}
                            >
                              قيد {m.journal_number}
                            </button>
                          ) : (
                            <span title="خطوة لم تمسّ الدفاتر — لا قيد لها">بلا قيد</span>
                          )}
                          {formatDateTimeValue(m.created_at)}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
            {err && (
              <div className="aseel-banner aseel-banner--err" data-testid="cheque-transfer-error"
                style={{ marginTop: "12px" }}>{err}</div>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "16px" }}>
              <button type="button" className="aseel-toolbtn" onClick={() => setTransferCheque(null)}>إلغاء</button>
              <OfflineGuard
                action="تحويل حالة الشيك"
                warningMessage="تَحويل حالة الشيك يتطلب اتصالاً — state machine يَنفَّذ على الـserver"
              >
                <button
                  type="button"
                  className="aseel-toolbtn"
                  data-testid="cheque-transfer-submit"
                  disabled={busy || !newMovement || (selectedMove?.requires_endorsee === true && !transferEndorsee)}
                  onClick={doTransfer}
                >
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
