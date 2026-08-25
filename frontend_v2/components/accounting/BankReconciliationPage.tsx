import React, { useCallback, useEffect, useMemo, useState } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import { formatDateValue } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import type {
  BankAccountDto,
  BankReconciliationDto,
  BankReconciliationSummaryDto,
} from "../../types/accounting";
import { KitDocumentShell, KitDenseTable } from "../kit";
import type { KitToolbarAction, DenseColumn } from "../kit";
import { CheckCircle, Lock, Plus, RefreshCw, Unlock } from "lucide-react";

/** مبلغ مع رمز عملة الحساب — الوسيط الثاني في `formatMoney` بديلٌ عند الفشل لا عملة. */
const money = (value: unknown, code?: string): string =>
  `${formatMoney(value)}${code ? ` ${code}` : ""}`;

/**
 * T-BANKS — المطابقة البنكية: كشف البنك مقابل حركة الدفاتر.
 *
 * تُؤشَّر الحركات التي ظهرت في كشف البنك؛ الفرق = رصيد الكشف − المؤشَّر،
 * ولا تُقفل المطابقة إلا بفرق صفر.
 */
export const BankReconciliationPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();

  const [accounts, setAccounts] = useState<BankAccountDto[]>([]);
  const [accountId, setAccountId] = useState("");
  const [list, setList] = useState<BankReconciliationDto[]>([]);
  const [current, setCurrent] = useState<BankReconciliationSummaryDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [stmtDate, setStmtDate] = useState(new Date().toISOString().split("T")[0]);
  const [stmtBalance, setStmtBalance] = useState("");

  const selectedAccount = useMemo(
    () => accounts.find((a) => String(a.id) === accountId) || null,
    [accounts, accountId],
  );
  const currencyCode = selectedAccount?.currency_code || "";

  const loadAccounts = useCallback(async () => {
    try {
      const a = (await accountingApi.getBankAccounts({ activeOnly: true })) as BankAccountDto[];
      setAccounts(a);
      if (!accountId && a.length) setAccountId(String(a[0].id));
    } catch (e: unknown) {
      setErr(humanizeThrown(e));
    }
  }, [accountId]);

  const loadReconciliations = useCallback(async (bankAccountId: string) => {
    if (!bankAccountId) { setList([]); setCurrent(null); return; }
    setLoading(true);
    setErr(null);
    try {
      const recs = (await accountingApi.getBankReconciliations(
        Number(bankAccountId),
      )) as BankReconciliationDto[];
      setList(recs);
      const open = recs.find((r) => r.status === "Open") || recs[0] || null;
      setCurrent(open ? await accountingApi.getBankReconciliationSummary(open.id) : null);
    } catch (e: unknown) {
      setErr(humanizeThrown(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadAccounts(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void loadReconciliations(accountId); }, [accountId, loadReconciliations]);

  const run = async (fn: () => Promise<unknown>, okMessage: string) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      toast(okMessage, "success");
    } catch (e: unknown) {
      const message = humanizeThrown(e);
      setErr(message);
      toast(message, "error");
    } finally {
      setBusy(false);
    }
  };

  const startReconciliation = () =>
    run(async () => {
      const created = await accountingApi.createBankReconciliation({
        bank_account: Number(accountId),
        statement_date: stmtDate,
        statement_balance: parseFloat(stmtBalance || "0") || 0,
      });
      await loadReconciliations(accountId);
      setCurrent(await accountingApi.getBankReconciliationSummary(created.id));
    }, "بدأت مطابقة جديدة");

  const openReconciliation = (rec: BankReconciliationDto) =>
    run(async () => {
      setCurrent(await accountingApi.getBankReconciliationSummary(rec.id));
    }, "تم فتح المطابقة");

  const toggleLine = (journalLineId: number, cleared: boolean) => {
    if (!current) return;
    void run(async () => {
      setCurrent(await accountingApi.toggleBankReconciliationLine(
        current.id, journalLineId, cleared,
      ));
    }, cleared ? "تم تأشير الحركة" : "أُلغي تأشير الحركة");
  };

  const closeCurrent = async () => {
    if (!current) return;
    if (!(await confirm({
      message: `إقفال المطابقة حتى ${formatDateValue(current.statement_date)}؟ لن تُعدَّل أسطرها بعد الإقفال.`,
    }))) return;
    void run(async () => {
      setCurrent(await accountingApi.closeBankReconciliation(current.id));
      await loadReconciliations(accountId);
    }, "أُقفلت المطابقة");
  };

  const reopenCurrent = () => {
    if (!current) return;
    void run(async () => {
      setCurrent(await accountingApi.reopenBankReconciliation(current.id));
      await loadReconciliations(accountId);
    }, "أُعيد فتح المطابقة");
  };

  const isClosed = current?.status === "Closed";
  const difference = Number(current?.difference ?? 0);
  const balanced = Math.abs(difference) < 0.005;

  const rowColumns: DenseColumn<BankReconciliationSummaryDto["rows"][number]>[] = [
    {
      key: "cleared", header: "مطابَق",
      render: (r) => (
        <input
          type="checkbox"
          checked={r.is_cleared}
          disabled={busy || isClosed}
          onChange={(e) => toggleLine(r.journal_line_id, e.target.checked)}
          title={isClosed ? "المطابقة مُقفلة" : "تأشير أن الحركة ظهرت في كشف البنك"}
        />
      ),
    },
    { key: "date", header: "التاريخ", render: (r) => formatDateValue(r.date) },
    { key: "journal", header: "القيد", render: (r) => `#${r.journal_id}` },
    { key: "description", header: "البيان", render: (r) => r.description || "—" },
    { key: "partner", header: "الجهة", render: (r) => r.partner || "—" },
    {
      key: "debit", header: "وارد", numeric: true,
      render: (r) => (Number(r.debit) > 0 ? formatMoney(r.debit, "") : ""),
    },
    {
      key: "credit", header: "صادر", numeric: true,
      render: (r) => (Number(r.credit) > 0 ? formatMoney(r.credit, "") : ""),
    },
    { key: "balance", header: "الرصيد", numeric: true, render: (r) => formatMoney(r.balance, "") },
  ];

  const actions: KitToolbarAction[] = [
    { key: "refresh", label: "تحديث", icon: <RefreshCw />, onClick: () => void loadReconciliations(accountId) },
  ];

  const headerBand = (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end" }}>
      <div className="ktra-field" style={{ minWidth: "220px" }}>
        <label className="ktra-field-label">الحساب البنكي</label>
        <select className="ktra-input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">— اختر —</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.bank_name} — {a.name} ({a.currency_code})
            </option>
          ))}
        </select>
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">تاريخ الكشف</label>
        <input type="date" className="ktra-input" value={stmtDate}
          onChange={(e) => setStmtDate(e.target.value)} />
      </div>
      <div className="ktra-field">
        <label className="ktra-field-label">رصيد الكشف</label>
        <input type="number" step="0.01" className="ktra-input ktra-num" style={{ width: "140px" }}
          value={stmtBalance} placeholder="0.00" onChange={(e) => setStmtBalance(e.target.value)} />
      </div>
      <button type="button" className="ktra-toolbtn" disabled={busy || !accountId}
        onClick={() => void startReconciliation()}>
        <Plus className="w-4 h-4" /> مطابقة جديدة
      </button>
      <div style={{ flex: 1 }} />
      {current && !isClosed && (
        <button type="button" className="ktra-toolbtn" disabled={busy || !balanced}
          title={balanced ? "إقفال المطابقة" : "لا يمكن الإقفال قبل تصفير الفرق"}
          onClick={() => void closeCurrent()}
          style={{ background: balanced ? "var(--ktra-ok, #2d7d46)" : undefined, color: balanced ? "#fff" : undefined }}>
          <Lock className="w-4 h-4" /> إقفال المطابقة
        </button>
      )}
      {current && isClosed && (
        <button type="button" className="ktra-toolbtn" disabled={busy}
          onClick={() => void reopenCurrent()}>
          <Unlock className="w-4 h-4" /> إعادة فتح
        </button>
      )}
    </div>
  );

  return (
    <div>
      <KitDocumentShell
        title="المطابقة البنكية"
        state={current ? `مطابقة #${current.id} — ${isClosed ? "مُقفلة" : "مفتوحة"}` : "لا مطابقة مفتوحة"}
        actions={actions}
        header={headerBand}
        status={
          current ? (
            <>
              <span className="ktra-status-item">
                رصيد الدفاتر <b className="ktra-num">{money(current.book_balance, currencyCode)}</b>
              </span>
              <span className="ktra-status-item">
                المؤشَّر <b className="ktra-num">{money(current.cleared_balance, currencyCode)}</b>
              </span>
              <span className="ktra-status-item">
                رصيد الكشف <b className="ktra-num">{money(current.statement_balance, currencyCode)}</b>
              </span>
              <span className="ktra-status-item"
                style={{ color: balanced ? "var(--ktra-ok, #27ae60)" : "var(--ktra-err, #c0392b)" }}>
                {balanced ? "مطابق ✓" : <>الفرق <b className="ktra-num">{money(difference, currencyCode)}</b></>}
              </span>
              <span className="ktra-status-item">غير مؤشَّر <b>{current.uncleared_count}</b></span>
            </>
          ) : (
            <span className="ktra-status-item">اختر حساباً وابدأ مطابقة</span>
          )
        }
      >
        <div style={{ padding: "8px 12px" }}>
          {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}

          {isClosed && (
            <div className="ktra-banner" style={{ marginBottom: "8px", background: "var(--ktra-ok-bg, #e3f6e9)", color: "var(--ktra-ok, #2d7d46)" }}>
              <CheckCircle className="w-3 h-3" style={{ marginInlineEnd: "6px" }} />
              هذه المطابقة مُقفلة — أعِد فتحها لتعديل أسطرها.
            </div>
          )}

          <KitDenseTable<BankReconciliationSummaryDto["rows"][number]>
            columns={rowColumns}
            rows={current?.rows || []}
            getRowKey={(r) => r.journal_line_id}
            loading={loading}
            emptyHint={accountId ? "لا حركات على هذا الحساب حتى تاريخ الكشف" : "اختر حساباً بنكياً"}
          />

          {list.length > 1 && (
            <div style={{ marginTop: "12px" }}>
              <div className="ktra-field-label" style={{ marginBottom: "4px" }}>مطابقات سابقة</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                {list.map((r) => (
                  <button key={r.id} type="button" className="ktra-toolbtn" disabled={busy}
                    onClick={() => void openReconciliation(r)}
                    style={{ fontWeight: current?.id === r.id ? 700 : 400 }}>
                    {formatDateValue(r.statement_date)} · {r.status === "Closed" ? "مُقفلة" : "مفتوحة"}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </KitDocumentShell>
    </div>
  );
};
