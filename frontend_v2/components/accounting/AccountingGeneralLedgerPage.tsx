import React, { useState, useEffect, useCallback, useRef } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney, formatBalanceWithSide, formatNumber } from "../../utils/formatNumber";
import type { AccountingAccount, GeneralLedgerResponse, CurrencyDto } from "../../types/accounting";
import {
  KitDocumentShell,
  KitReportTable,
} from "../kit";
import type { KitToolbarAction, KitTab, ReportColumn } from "../kit";
import { Search } from "lucide-react";
import { formatDateLocalized } from "../../utils/formatDate";
import { AccountTreeField } from "./AccountTreePicker";

type LedgerRow = GeneralLedgerResponse["transactions"][number];

export interface AccountingGeneralLedgerPageProps {
  initialAccountId?: number | null;
  onInitialAccountConsumed?: () => void;
  /**
   * التنقيب: نقر رقم القيد يفتحه. الحساب المعروض يُمرَّر معه كي يعود المستخدم
   * إلى الكشف نفسه لا إلى شاشة فارغة.
   */
  onOpenJournal?: (journalId: number, accountId: number | null) => void;
}

export const AccountingGeneralLedgerPage: React.FC<AccountingGeneralLedgerPageProps> = ({
  initialAccountId,
  onInitialAccountConsumed,
  onOpenJournal,
}) => {
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyDto[]>([]);
  const [accountId, setAccountId] = useState("");
  const [currencyId, setCurrencyId] = useState("");
  const today = new Date();
  const [start, setStart] = useState(`${today.getFullYear()}-01-01`);
  const [end, setEnd] = useState(today.toISOString().split("T")[0]);
  const [unposted, setUnposted] = useState(false);
  const [data, setData] = useState<GeneralLedgerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const appliedInitial = useRef<number | null>(null);

  useEffect(() => {
    accountingApi
      .getAccounts()
      .then((a) =>
        setAccounts((a as AccountingAccount[]).filter((x) => x.is_active))
      )
      .catch(() => setAccounts([]));
    accountingApi.getCurrencies().then((c) => setCurrencies(c as CurrencyDto[])).catch(() => setCurrencies([]));
  }, []);

  useEffect(() => {
    if (initialAccountId == null) {
      appliedInitial.current = null;
      return;
    }
    if (appliedInitial.current === initialAccountId) return;
    appliedInitial.current = initialAccountId;
    setAccountId(String(initialAccountId));
    onInitialAccountConsumed?.();
    // التشغيل نفسه يتكفّل به التحميل التلقائي أدناه بمجرد ضبط الحساب.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialAccountId]);

  const run = useCallback(async () => {
    if (!accountId) {
      setErr("اختر حساباً");
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      const params: Record<string, string> = {
        account_id: accountId,
        start_date: start,
        end_date: end,
      };
      if (unposted) params.include_unposted = "true";
      if (currencyId) params.currency_id = currencyId;
      const res = await accountingApi.getGeneralLedger(params);
      setData(res as GeneralLedgerResponse);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التقرير");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [accountId, start, end, unposted, currencyId]);

  // تحميل تلقائي عند تغيّر الحساب أو الفترة أو العملة. كان لا بدّ من ضغط «عرض»
  // يدوياً، فيبدو الحساب فارغاً بينما لم يُنفَّذ أي استعلام أصلاً. الإمهال القصير
  // يمنع نداءً لكل ضغطة في حقول التاريخ.
  useEffect(() => {
    if (!accountId) {
      setData(null);
      setErr(null);
      return;
    }
    const timer = window.setTimeout(() => { void run(); }, 350);
    return () => window.clearTimeout(timer);
  }, [accountId, run]);

  const fmt = (n: number) => formatMoney(n);
  const fmtBalance = (n: number) => formatBalanceWithSide(n);

  // Use transactions from GeneralLedgerResponse
  const ledgerRows: LedgerRow[] = data?.transactions || [];

  const columns: ReportColumn<LedgerRow>[] = [
    { key: "date", header: "التاريخ", render: (r) => formatDateLocalized(r.date) },
    {
      key: "journal_id", header: "رقم القيد",
      // القفزة الثانية في التنقيب: من سطر الأستاذ إلى القيد الذي أنشأه.
      render: (r) =>
        onOpenJournal ? (
          <button
            type="button"
            className="text-blue-700 hover:underline"
            title="فتح القيد"
            onClick={() => onOpenJournal(r.journal_id, accountId ? Number(accountId) : null)}
          >
            #{r.journal_id}
          </button>
        ) : (
          `#${r.journal_id}`
        ),
    },
    { key: "description", header: "البيان", render: (r) => r.description },
    { key: "debit", header: "مدين", numeric: true, render: (r) => fmt(Number(r.debit)), exportValue: (r) => Number(r.debit) },
    { key: "credit", header: "دائن", numeric: true, render: (r) => fmt(Number(r.credit)), exportValue: (r) => Number(r.credit) },
    // الجانب صريح: «1,112 دائن» — الإشارة وحدها تُرسم في نهاية الرقم بـRTL فتلتبس.
    // التصدير يحمل الرصيد الموقّع الخام (لا نص الجانب) كي يُعاد حسابه آلياً.
    { key: "balance", header: "الرصيد المتراكم", numeric: true, render: (r) => fmtBalance(Number(r.balance)), exportValue: (r) => Number(r.balance) },
  ];

  const totalDebit = ledgerRows.reduce((s, r) => s + Number(r.debit), 0);
  const totalCredit = ledgerRows.reduce((s, r) => s + Number(r.credit), 0);
  const totals = data ? {
    debit: fmt(totalDebit),
    credit: fmt(totalCredit),
    balance: fmtBalance(Number(data.closing_balance)),
  } : undefined;

  const filterBar = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="ktra-field" style={{ flex: "1", minWidth: "200px" }}>
        <label className="ktra-field-label">الحساب</label>
        {/* THA-111: فلتر عرض لا هدف ترحيل — يُسمح فيه باختيار حساب أب. */}
        <AccountTreeField
          accounts={accounts}
          value={accountId === "" ? "" : Number(accountId)}
          onChange={(id) => setAccountId(id == null ? "" : String(id))}
          purpose="any"
          allowParents
          title="اختيار الحساب من الشجرة"
        />
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">من</label>
        <input type="date" className="ktra-input" value={start} onChange={(e) => setStart(e.target.value)} />
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">إلى</label>
        <input type="date" className="ktra-input" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <div className="ktra-field" style={{ minWidth: "120px" }}>
        <label className="ktra-field-label">العملة</label>
        <select className="ktra-input" value={currencyId} onChange={(e) => setCurrencyId(e.target.value)}>
          <option value="">كل العملات</option>
          {currencies.map((c) => (
            <option key={c.CurrencyID} value={c.CurrencyID}>{c.Code}</option>
          ))}
        </select>
      </div>
      <label className="flex items-center gap-2 text-sm" style={{ paddingTop: "18px" }}>
        <input type="checkbox" checked={unposted} onChange={(e) => setUnposted(e.target.checked)} />
        غير المرحّل
      </label>
      <button type="button" className="ktra-toolbtn" onClick={run} style={{ marginTop: "18px" }}>
        <Search className="w-4 h-4" />عرض
      </button>
    </div>
  );

  const reportContent = (
    <>
      {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      {data?.truncated && (
        <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>
          الكشف مقصوص: عُرض {formatNumber(data.max_rows ?? 0)} سطراً من أصل{" "}
          {formatNumber(data.total_count ?? 0)} — الرصيد الختامي أدناه يخصّ المعروض فقط.
          ضيّق مدى التاريخ لعرض الكشف كاملاً.
        </div>
      )}
      {data && (
        <div style={{ padding: "8px 0", fontSize: "0.85rem", color: "var(--ktra-ink-soft)" }}>
          <strong>{data.account_code} — {data.account_name}</strong>
          &nbsp;|&nbsp; رصيد افتتاحي: <strong>{fmtBalance(Number(data.opening_balance))}</strong>
          &nbsp;|&nbsp; رصيد ختامي: <strong>{fmtBalance(Number(data.closing_balance))}</strong>
        </div>
      )}
      <KitReportTable<LedgerRow>
        filterBar={filterBar}
        columns={columns}
        rows={ledgerRows}
        totals={totals}
        exportable={true}
        exportFilename={`general-ledger-${start}_${end}`}
        loading={loading}
        emptyHint={
          data
            // الفرق مهم: «لم تبحث بعد» ≠ «بحثت ولا يوجد». المستند المؤرَّخ بعد «إلى»
            // (فاتورة بتاريخ لاحق) لا يظهر، وكانت الرسالة الثابتة توحي بأن الحساب فارغ.
            ? `لا توجد حركات على هذا الحساب بين ${start} و${end}. المستندات المؤرَّخة خارج هذه الفترة لا تظهر — إن كان تاريخ الفاتورة لاحقاً فوسّع حقل «إلى».`
            : "اختر حساباً لعرض حركته"
        }
        getRowKey={(r, idx) => `${r.journal_id}-${idx}`}
      />
    </>
  );

  const shellActions: KitToolbarAction[] = [
    { key: "run", label: "عرض", icon: <Search className="w-4 h-4" />, onClick: run },
  ];

  const tabs: KitTab[] = [
    { key: "ledger", label: "حركة الحساب", content: reportContent },
  ];

  return (
    <div>
      <KitDocumentShell
        title="الأستاذ العام"
        actions={shellActions}
        header={<></>}
        tabs={tabs}
        status={
          data ? (
            <span className="ktra-status-item">{ledgerRows.length} حركة</span>
          ) : undefined
        }
      >
        <></>
      </KitDocumentShell>
    </div>
  );
};
