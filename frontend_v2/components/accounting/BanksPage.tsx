import React, { useCallback, useEffect, useMemo, useState } from "react";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney } from "../../utils/formatNumber";
import { humanizeThrown } from "../../utils/drfError";
import { useToast } from "../../contexts/ToastContext";
import { useConfirm } from "../../contexts/ConfirmContext";
import type {
  BankAccountDto,
  BankBranchDto,
  BankDto,
  CurrencyDto,
} from "../../types/accounting";
import { AseelDocumentShell, AseelDenseTable } from "../aseel";
import type { AseelTab, AseelToolbarAction, DenseColumn } from "../aseel";
import { Building2, Landmark, Plus, Trash2, Wallet } from "lucide-react";

/**
 * T-BANKS — إدارة البنوك وفروعها وحسابات الشركة لديها.
 *
 * كل حساب بنكي يحصل على حساب مستقل في شجرة الحسابات تحت «1102 البنوك»
 * (ينشئه الخادم)، فتُرحَّل حركته وتُطابَق بكشف البنك على حِدة.
 */
export const BanksPage: React.FC = () => {
  const toast = useToast();
  const confirm = useConfirm();

  const [banks, setBanks] = useState<BankDto[]>([]);
  const [accounts, setAccounts] = useState<BankAccountDto[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // نموذج بنك جديد
  const [bankName, setBankName] = useState("");
  const [bankSwift, setBankSwift] = useState("");
  // نموذج فرع جديد
  const [branchBank, setBranchBank] = useState("");
  const [branchName, setBranchName] = useState("");
  const [branchCode, setBranchCode] = useState("");
  // نموذج حساب بنكي جديد
  const [accBank, setAccBank] = useState("");
  const [accBranch, setAccBranch] = useState("");
  const [accName, setAccName] = useState("");
  const [accNumber, setAccNumber] = useState("");
  const [accIban, setAccIban] = useState("");
  const [accCurrency, setAccCurrency] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [b, a, c] = await Promise.all([
        accountingApi.getBanks(),
        accountingApi.getBankAccounts(),
        accountingApi.getCurrencies(),
      ]);
      setBanks(b as BankDto[]);
      setAccounts(a as BankAccountDto[]);
      setCurrencies(c as CurrencyDto[]);
      if (!accCurrency) {
        const base = (c as CurrencyDto[]).find((x) => x.IsBaseCurrency);
        if (base) setAccCurrency(String(base.CurrencyID));
      }
    } catch (e: unknown) {
      setErr(humanizeThrown(e));
    } finally {
      setLoading(false);
    }
  }, [accCurrency]);

  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const branches = useMemo<BankBranchDto[]>(
    () => banks.flatMap((b) => (b.branches || []).map((br) => ({ ...br, bank_name: b.name }))),
    [banks],
  );

  const branchesOfSelectedBank = useMemo(
    () => branches.filter((br) => String(br.bank) === accBank),
    [branches, accBank],
  );

  const run = async (fn: () => Promise<unknown>, okMessage: string) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      await load();
      toast(okMessage, "success");
    } catch (e: unknown) {
      const message = humanizeThrown(e);
      setErr(message);
      toast(message, "error");
    } finally {
      setBusy(false);
    }
  };

  const addBank = () =>
    run(async () => {
      await accountingApi.createBank({
        name: bankName.trim(),
        swift_code: bankSwift.trim() || null,
      });
      setBankName("");
      setBankSwift("");
    }, "تمت إضافة البنك");

  const addBranch = () =>
    run(async () => {
      await accountingApi.createBankBranch({
        bank: Number(branchBank),
        name: branchName.trim(),
        branch_code: branchCode.trim() || null,
      });
      setBranchName("");
      setBranchCode("");
    }, "تمت إضافة الفرع");

  const addAccount = () =>
    run(async () => {
      await accountingApi.createBankAccount({
        bank: Number(accBank),
        branch: accBranch ? Number(accBranch) : null,
        name: accName.trim(),
        account_number: accNumber.trim() || null,
        iban: accIban.trim() || null,
        currency: Number(accCurrency),
      });
      setAccName("");
      setAccNumber("");
      setAccIban("");
    }, "تم إنشاء الحساب البنكي وحسابه في الشجرة");

  const removeBank = async (bank: BankDto) => {
    if (!(await confirm({ message: `حذف البنك «${bank.name}»؟` }))) return;
    void run(() => accountingApi.deleteBank(bank.id), "تم حذف البنك");
  };

  const removeBranch = async (branch: BankBranchDto) => {
    if (!(await confirm({ message: `حذف الفرع «${branch.name}»؟` }))) return;
    void run(() => accountingApi.deleteBankBranch(branch.id), "تم حذف الفرع");
  };

  const removeAccount = async (acc: BankAccountDto) => {
    if (!(await confirm({ message: `حذف الحساب البنكي «${acc.name}»؟` }))) return;
    void run(() => accountingApi.deleteBankAccount(acc.id), "تم حذف الحساب البنكي");
  };

  const toggleActive = (acc: BankAccountDto) =>
    run(
      () => accountingApi.updateBankAccount(acc.id, { is_active: !acc.is_active }),
      acc.is_active ? "تم تعطيل الحساب" : "تم تفعيل الحساب",
    );

  const bankColumns: DenseColumn<BankDto>[] = [
    { key: "name", header: "البنك", render: (b) => b.name },
    { key: "swift", header: "SWIFT", render: (b) => b.swift_code || "—" },
    { key: "branches", header: "الفروع", numeric: true, render: (b) => String((b.branches || []).length) },
    { key: "accounts", header: "الحسابات", numeric: true, render: (b) => String(b.accounts_count ?? 0) },
    { key: "active", header: "الحالة", render: (b) => (b.is_active ? "فعّال" : "معطّل") },
    {
      key: "del", header: "حذف",
      render: (b) => (
        <button type="button" className="aseel-toolbtn aseel-toolbtn--danger" disabled={busy}
          onClick={(e) => { e.stopPropagation(); void removeBank(b); }}>
          <Trash2 className="w-3 h-3" />
        </button>
      ),
    },
  ];

  const branchColumns: DenseColumn<BankBranchDto>[] = [
    { key: "bank", header: "البنك", render: (b) => b.bank_name || "—" },
    { key: "name", header: "الفرع", render: (b) => b.name },
    { key: "code", header: "رمز الفرع", render: (b) => b.branch_code || "—" },
    { key: "phone", header: "الهاتف", render: (b) => b.phone || "—" },
    {
      key: "del", header: "حذف",
      render: (b) => (
        <button type="button" className="aseel-toolbtn aseel-toolbtn--danger" disabled={busy}
          onClick={(e) => { e.stopPropagation(); void removeBranch(b); }}>
          <Trash2 className="w-3 h-3" />
        </button>
      ),
    },
  ];

  const accountColumns: DenseColumn<BankAccountDto>[] = [
    { key: "bank", header: "البنك", render: (a) => a.bank_name || "—" },
    { key: "branch", header: "الفرع", render: (a) => a.branch_name || "—" },
    { key: "name", header: "الحساب", render: (a) => a.name },
    { key: "number", header: "رقم الحساب", render: (a) => a.account_number || "—" },
    { key: "iban", header: "IBAN", render: (a) => a.iban || "—" },
    { key: "currency", header: "العملة", render: (a) => a.currency_code || "—" },
    { key: "gl", header: "حساب الشجرة", render: (a) => a.account_code || "—" },
    {
      key: "balance", header: "الرصيد", numeric: true,
      render: (a) => `${formatMoney(a.balance ?? 0)} ${a.currency_code || ""}`.trim(),
    },
    {
      key: "active", header: "الحالة",
      render: (a) => (
        <button type="button" className="aseel-toolbtn" disabled={busy}
          onClick={(e) => { e.stopPropagation(); void toggleActive(a); }}>
          {a.is_active ? "فعّال" : "معطّل"}
        </button>
      ),
    },
    {
      key: "del", header: "حذف",
      render: (a) => (
        <button type="button" className="aseel-toolbtn aseel-toolbtn--danger" disabled={busy}
          onClick={(e) => { e.stopPropagation(); void removeAccount(a); }}>
          <Trash2 className="w-3 h-3" />
        </button>
      ),
    },
  ];

  const banner = err ? (
    <div className="aseel-banner aseel-banner--err" style={{ marginBottom: "8px" }}>{err}</div>
  ) : null;

  const banksTab = (
    <>
      {banner}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end", marginBottom: "10px" }}>
        <div className="aseel-field">
          <label className="aseel-field-label">اسم البنك</label>
          <input className="aseel-input" value={bankName} placeholder="بنك فلسطين"
            onChange={(e) => setBankName(e.target.value)} />
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">SWIFT</label>
          <input className="aseel-input" value={bankSwift} placeholder="PALSPS22"
            onChange={(e) => setBankSwift(e.target.value)} />
        </div>
        <button type="button" className="aseel-toolbtn" disabled={busy || !bankName.trim()}
          onClick={() => void addBank()}>
          <Plus className="w-4 h-4" /> إضافة بنك
        </button>
      </div>
      <AseelDenseTable<BankDto>
        columns={bankColumns}
        rows={banks}
        getRowKey={(b) => b.id}
        loading={loading}
        emptyHint="لا توجد بنوك — أضِف البنك الذي تتعامل معه أولاً"
      />
    </>
  );

  const branchesTab = (
    <>
      {banner}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end", marginBottom: "10px" }}>
        <div className="aseel-field">
          <label className="aseel-field-label">البنك</label>
          <select className="aseel-input" value={branchBank} onChange={(e) => setBranchBank(e.target.value)}>
            <option value="">— اختر —</option>
            {banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">اسم الفرع</label>
          <input className="aseel-input" value={branchName} placeholder="فرع رام الله"
            onChange={(e) => setBranchName(e.target.value)} />
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">رمز الفرع</label>
          <input className="aseel-input" value={branchCode} style={{ width: "110px" }}
            onChange={(e) => setBranchCode(e.target.value)} />
        </div>
        <button type="button" className="aseel-toolbtn"
          disabled={busy || !branchBank || !branchName.trim()} onClick={() => void addBranch()}>
          <Plus className="w-4 h-4" /> إضافة فرع
        </button>
      </div>
      <AseelDenseTable<BankBranchDto>
        columns={branchColumns}
        rows={branches}
        getRowKey={(b) => b.id}
        loading={loading}
        emptyHint="لا توجد فروع"
      />
    </>
  );

  const accountsTab = (
    <>
      {banner}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "flex-end", marginBottom: "10px" }}>
        <div className="aseel-field">
          <label className="aseel-field-label">البنك</label>
          <select className="aseel-input" value={accBank}
            onChange={(e) => { setAccBank(e.target.value); setAccBranch(""); }}>
            <option value="">— اختر —</option>
            {banks.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">الفرع</label>
          <select className="aseel-input" value={accBranch} disabled={!accBank}
            onChange={(e) => setAccBranch(e.target.value)}>
            <option value="">— بلا فرع —</option>
            {branchesOfSelectedBank.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">تسمية الحساب</label>
          <input className="aseel-input" value={accName} placeholder="جاري شيكل"
            onChange={(e) => setAccName(e.target.value)} />
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">رقم الحساب</label>
          <input className="aseel-input" value={accNumber} onChange={(e) => setAccNumber(e.target.value)} />
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">IBAN</label>
          <input className="aseel-input" value={accIban} onChange={(e) => setAccIban(e.target.value)} />
        </div>
        <div className="aseel-field">
          <label className="aseel-field-label">العملة</label>
          <select className="aseel-input" value={accCurrency} onChange={(e) => setAccCurrency(e.target.value)}>
            <option value="">— اختر —</option>
            {currencies.map((c) => (
              <option key={c.CurrencyID} value={c.CurrencyID}>
                {c.Code}{c.IsBaseCurrency ? " (أساسية)" : ""}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="aseel-toolbtn"
          disabled={busy || !accBank || !accName.trim() || !accCurrency}
          onClick={() => void addAccount()}>
          <Plus className="w-4 h-4" /> إضافة حساب بنكي
        </button>
      </div>
      <AseelDenseTable<BankAccountDto>
        columns={accountColumns}
        rows={accounts}
        getRowKey={(a) => a.id}
        loading={loading}
        emptyHint="لا توجد حسابات بنكية — كل حساب يُنشئ حسابه في الشجرة تلقائياً"
      />
    </>
  );

  const tabs: AseelTab[] = [
    { key: "banks", label: "البنوك", content: banksTab },
    { key: "branches", label: "الفروع", content: branchesTab },
    { key: "accounts", label: "الحسابات البنكية", content: accountsTab },
  ];

  const actions: AseelToolbarAction[] = [
    { key: "refresh", label: "تحديث", onClick: load },
  ];

  return (
    <div>
      <AseelDocumentShell
        title="البنوك وفروعها"
        actions={actions}
        tabs={tabs}
        status={
          <>
            <span className="aseel-status-item"><Landmark className="w-3 h-3" /> بنوك <b>{banks.length}</b></span>
            <span className="aseel-status-item"><Building2 className="w-3 h-3" /> فروع <b>{branches.length}</b></span>
            <span className="aseel-status-item"><Wallet className="w-3 h-3" /> حسابات <b>{accounts.length}</b></span>
          </>
        }
      >
        <></>
      </AseelDocumentShell>
    </div>
  );
};
