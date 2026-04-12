import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type {
  AccountingAccount,
  AccountingPartner,
  CostCenterDto,
  CurrencyDto,
} from "../../types/accounting";
import {
  ArrowRight,
  Plus,
  Trash2,
  Save,
  CheckCircle,
  Loader2,
  ExternalLink,
  Handshake,
  AlertTriangle,
  Info,
} from "lucide-react";

/* ─────────── types ─────────── */

type LineState = {
  id?: number;
  accountId: string;
  partnerId: string;
  costCenterId: string;
  debit: string;
  credit: string;
  description: string;
};

type DealRef = {
  dealId: string;
  dealNumber: string;
  displayName: string;
};

interface Props {
  journalId: number | null;
  onBack: () => void;
  dealRef?: DealRef | null;
  /** من أين فُتح القيد — لربط «فتح الشحنة» بدل صفقة خاطئة */
  relatedKind?: "deal" | "shipment" | null;
  onNavigateToDeal?: (dealId: string) => void;
  onNavigateToShipment?: (shipmentId: string) => void;
}

/* ─────────── helpers ─────────── */

const emptyLine = (): LineState => ({
  accountId: "",
  partnerId: "",
  costCenterId: "",
  debit: "",
  credit: "",
  description: "",
});

const REF_TYPE_LABELS: Record<string, string> = {
  LOGISTICS_PAYMENT: "دفعة صفقة",
  PURCHASE_RECEIPT: "استلام مخزون",
  JOURNAL_REVERSAL: "عكس قيد",
  LOGISTICS_EXPENSE: "مصروف لوجستي",
};

function refTypeLabel(t: string, description?: string) {
  if (
    t === "LOGISTICS_PAYMENT" &&
    description &&
    /\bشحنة\b/i.test(description)
  ) {
    return "دفعة لوجستيات";
  }
  return REF_TYPE_LABELS[t] || t;
}

function fmtAmount(v: string | number) {
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!n || isNaN(n)) return "";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/* ─────────── component ─────────── */

export const AccountingJournalEntryPage: React.FC<Props> = ({
  journalId,
  onBack,
  dealRef,
  relatedKind = null,
  onNavigateToDeal,
  onNavigateToShipment,
}) => {
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  const [costCenters, setCostCenters] = useState<CostCenterDto[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [posted, setPosted] = useState(false);

  const [header, setHeader] = useState({
    transaction_date: new Date().toISOString().split("T")[0],
    description: "",
    reference_type: "",
    reference_id: "",
    reference_summary: "",
    deal_ref_number: "",
    currency: "" as string,
    exchange_rate: "1",
    currency_code: "" as string,
  });

  const [lines, setLines] = useState<LineState[]>([emptyLine(), emptyLine(), emptyLine()]);

  /* ── load data ── */
  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [acc, part, cc, cur] = await Promise.all([
        accountingApi.getAccounts(),
        accountingApi.getPartners().catch(() => []),
        accountingApi.getCostCenters().catch(() => []),
        accountingApi.getCurrencies().catch(() => []),
      ]);
      setAccounts((acc as AccountingAccount[]).filter((a) => a.is_active));
      setPartners(part as AccountingPartner[]);
      setCostCenters(cc as CostCenterDto[]);
      setCurrencies(cur as CurrencyDto[]);

      const baseCurrency = (cur as CurrencyDto[]).find((c) => c.IsBaseCurrency);

      if (journalId != null) {
        const j = await accountingApi.getJournal(journalId);
        setPosted(!!j.is_posted);
        setHeader({
          transaction_date: j.transaction_date || "",
          description: j.description || "",
          reference_type: j.reference_type || "",
          reference_id: j.reference_id != null ? String(j.reference_id) : "",
          reference_summary: j.reference_summary || "",
          deal_ref_number: j.deal_ref_number || "",
          currency: j.currency != null ? String(j.currency) : (baseCurrency ? String(baseCurrency.CurrencyID) : ""),
          exchange_rate: j.exchange_rate != null ? String(j.exchange_rate) : "1",
          currency_code: j.currency_code || "",
        });
        const mapped: LineState[] = (j.lines || []).map(
          (line: {
            id?: number;
            account: number;
            debit: string;
            credit: string;
            partner?: number | null;
            cost_center?: number | null;
            description?: string | null;
          }) => ({
            id: line.id,
            accountId: String(line.account),
            partnerId: line.partner != null ? String(line.partner) : "",
            costCenterId: line.cost_center != null ? String(line.cost_center) : "",
            debit: parseFloat(String(line.debit)) > 0 ? String(line.debit) : "",
            credit: parseFloat(String(line.credit)) > 0 ? String(line.credit) : "",
            description: line.description || "",
          })
        );
        while (mapped.length < 3) mapped.push(emptyLine());
        setLines(mapped);
      } else {
        setPosted(false);
        setLines([emptyLine(), emptyLine(), emptyLine()]);
        if (baseCurrency) {
          setHeader((h) => ({
            ...h,
            currency: String(baseCurrency.CurrencyID),
            exchange_rate: "1",
            currency_code: baseCurrency.Code,
          }));
        }
        if (dealRef?.displayName) {
          setHeader((h) => ({
            ...h,
            description: h.description || `صفقة: ${dealRef.displayName}`,
          }));
        }
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [journalId, dealRef?.displayName]);

  useEffect(() => { void load(); }, [load]);

  /* ── line helpers ── */
  const updateLine = (i: number, patch: Partial<LineState>) => {
    if (posted) return;
    setLines((prev) => {
      const next = [...prev];
      const row = { ...next[i], ...patch };
      if (patch.debit && parseFloat(patch.debit) > 0) row.credit = "";
      if (patch.credit && parseFloat(patch.credit) > 0) row.debit = "";
      next[i] = row;
      if (i === next.length - 1 && (row.accountId || row.debit || row.credit)) {
        next.push(emptyLine());
      }
      return next;
    });
  };

  const removeLine = (i: number) => {
    if (posted) return;
    setLines((prev) => {
      const next = prev.filter((_, idx) => idx !== i);
      return next.length ? next : [emptyLine()];
    });
  };

  /* ── totals ── */
  const totalDebit = lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0);
  const totalCredit = lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0);
  const diff = totalDebit - totalCredit;
  const balanced = Math.abs(diff) < 0.005 && totalDebit > 0;

  /* ── validation ── */
  const validate = (): string | null => {
    if (!header.transaction_date) return "التاريخ مطلوب";
    if (!header.description.trim()) return "البيان مطلوب";
    const active = lines.filter(
      (l) => l.accountId && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)
    );
    if (active.length < 2) return "يجب طرفان على الأقل بمبالغ";
    if (!balanced) return `القيد غير متوازن (فرق ${diff.toFixed(2)})`;
    return null;
  };

  /* ── payload ── */
  const buildPayload = () => {
    const active = lines.filter(
      (l) => l.accountId && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)
    );
    return {
      transaction_date: header.transaction_date,
      description: header.description.trim(),
      reference_type: header.reference_type.trim() || null,
      reference_id: header.reference_id.trim() ? parseInt(header.reference_id, 10) : null,
      is_posted: false,
      currency: header.currency ? parseInt(header.currency, 10) : null,
      exchange_rate: parseFloat(header.exchange_rate) || 1,
      lines: active.map((l) => {
        const line: Record<string, unknown> = {
          account: parseInt(l.accountId, 10),
          debit: parseFloat(l.debit) || 0,
          credit: parseFloat(l.credit) || 0,
          partner: l.partnerId ? parseInt(l.partnerId, 10) : null,
          cost_center: l.costCenterId ? parseInt(l.costCenterId, 10) : null,
          description: l.description.trim() || null,
        };
        if (l.id) line.id = l.id;
        return line;
      }),
    };
  };

  /* ── save / post ── */
  const saveOnly = async () => {
    const v = validate();
    if (v) { setErr(v); return; }
    setSaving(true);
    setErr(null);
    try {
      const payload = buildPayload();
      if (journalId != null) await accountingApi.updateJournal(journalId, payload);
      else await accountingApi.createJournal(payload);
      onBack();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally { setSaving(false); }
  };

  const saveAndPost = async () => {
    const v = validate();
    if (v) { setErr(v); return; }
    setSaving(true);
    setErr(null);
    try {
      const payload = buildPayload();
      let id = journalId;
      if (id != null) await accountingApi.updateJournal(id, payload);
      else {
        const created = await accountingApi.createJournal(payload);
        id = created.id;
      }
      if (id != null) await accountingApi.postJournal(id);
      onBack();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ أو الترحيل");
    } finally { setSaving(false); }
  };

  /* ── loading state ── */
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-gray-400">
        <Loader2 className="w-6 h-6 animate-spin ml-2" />
        جاري التحميل…
      </div>
    );
  }

  /* ── render ── */
  const activeDealRef: DealRef | null = dealRef ?? (
    header.reference_type === "LOGISTICS_PAYMENT" && (header.reference_summary || header.deal_ref_number)
      ? {
          dealId: "",
          dealNumber: header.deal_ref_number || "",
          displayName: header.reference_summary || header.deal_ref_number || "",
        }
      : null
  );

  const isShipmentLink =
    relatedKind === "shipment" ||
    (relatedKind == null &&
      header.reference_type === "LOGISTICS_PAYMENT" &&
      /\bشحنة\b/i.test(header.description || ""));

  return (
    <div className="space-y-5 max-w-5xl mx-auto">

      {/* ── شريط العنوان ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-blue-600 dark:text-blue-400 hover:underline"
          >
            <ArrowRight className="w-4 h-4" />
            العودة
          </button>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <h1 className="text-base font-bold text-gray-800 dark:text-white">
            {journalId ? `قيد رقم #${journalId}` : "قيد يومية جديد"}
          </h1>
          {posted && (
            <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
              <CheckCircle className="w-3 h-3" />
              مرحّل — للقراءة فقط
            </span>
          )}
        </div>
      </div>

      {/* ── ارتباط بصفقة أو شحنة (تنقّل فقط — لا ترحيل من هنا) ── */}
      {activeDealRef && (
        <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700">
          <div className="p-2 bg-slate-200/80 dark:bg-slate-800 rounded-lg flex-shrink-0">
            <Handshake className="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-0.5">
              {isShipmentLink ? "مرتبط بشحنة" : "مرتبط بصفقة"}
            </p>
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">
              {activeDealRef.displayName}
            </p>
          </div>
          {isShipmentLink &&
            activeDealRef.dealId &&
            onNavigateToShipment &&
            /^\d+$/.test(String(activeDealRef.dealId).trim()) && (
              <button
                type="button"
                onClick={() => onNavigateToShipment(String(activeDealRef.dealId).trim())}
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-700 text-white hover:bg-slate-800 transition-colors flex-shrink-0"
              >
                فتح الشحنة
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            )}
          {!isShipmentLink &&
            (activeDealRef.dealId || activeDealRef.dealNumber) &&
            onNavigateToDeal && (
              <button
                type="button"
                onClick={() =>
                  onNavigateToDeal(activeDealRef.dealId || activeDealRef.dealNumber)
                }
                className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-slate-700 text-white hover:bg-slate-800 transition-colors flex-shrink-0"
              >
                فتح الصفقة
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            )}
        </div>
      )}

      {/* ── خطأ ── */}
      {err && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          {err}
        </div>
      )}

      {/* ── رأس القيد ── */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700 pb-2">
          بيانات القيد
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* التاريخ */}
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              تاريخ القيد <span className="text-red-500">*</span>
            </label>
            <input
              type="date"
              disabled={posted}
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-900 dark:text-white disabled:opacity-60 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              value={header.transaction_date}
              onChange={(e) => setHeader((h) => ({ ...h, transaction_date: e.target.value }))}
            />
          </div>

          {/* المرجع */}
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              المرجع
            </label>
            {posted ? (
              /* عرض قراءة فقط للمرجع */
              header.reference_type ? (
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-xs font-medium text-gray-700 dark:text-gray-300">
                    <Info className="w-3.5 h-3.5" />
                    {refTypeLabel(header.reference_type, header.description)}
                    {header.reference_id && (
                      <span className="text-gray-400 dark:text-gray-500">
                        · #{header.reference_id}
                      </span>
                    )}
                  </span>
                </div>
              ) : (
                <div className="px-3 py-2 text-sm text-gray-400">—</div>
              )
            ) : (
              <div className="flex gap-2">
                <select
                  className="flex-1 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  value={header.reference_type}
                  onChange={(e) => setHeader((h) => ({ ...h, reference_type: e.target.value }))}
                >
                  <option value="">— نوع المرجع —</option>
                  {Object.entries(REF_TYPE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>{v}</option>
                  ))}
                  <option value="OTHER">أخرى</option>
                </select>
                <input
                  type="number"
                  placeholder="رقم"
                  className="w-24 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  value={header.reference_id}
                  onChange={(e) => setHeader((h) => ({ ...h, reference_id: e.target.value }))}
                />
              </div>
            )}
          </div>
        </div>

        {/* العملة + سعر الصرف */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              العملة
            </label>
            {posted ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-xs font-medium text-gray-700 dark:text-gray-300">
                {header.currency_code || currencies.find((c) => String(c.CurrencyID) === header.currency)?.Code || "—"}
              </span>
            ) : (
              <select
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                value={header.currency}
                onChange={(e) => {
                  const sel = currencies.find((c) => String(c.CurrencyID) === e.target.value);
                  setHeader((h) => ({
                    ...h,
                    currency: e.target.value,
                    exchange_rate: sel?.IsBaseCurrency ? "1" : h.exchange_rate,
                    currency_code: sel?.Code || "",
                  }));
                }}
              >
                <option value="">— اختر العملة —</option>
                {currencies.map((c) => (
                  <option key={c.CurrencyID} value={c.CurrencyID}>
                    {c.Code} — {c.Name} {c.IsBaseCurrency ? "(أساسية)" : ""}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              سعر الصرف (مقابل العملة الأساسية)
            </label>
            {posted ? (
              <span className="inline-flex items-center px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-700 text-xs font-mono font-medium text-gray-700 dark:text-gray-300">
                {Number(header.exchange_rate).toFixed(6)}
              </span>
            ) : (
              <input
                type="number"
                step="0.000001"
                min="0"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm font-mono bg-white dark:bg-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                value={header.exchange_rate}
                onChange={(e) => setHeader((h) => ({ ...h, exchange_rate: e.target.value }))}
                disabled={
                  !!currencies.find((c) => String(c.CurrencyID) === header.currency)?.IsBaseCurrency
                }
              />
            )}
          </div>
        </div>

        {/* البيان */}
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            البيان <span className="text-red-500">*</span>
          </label>
          <textarea
            disabled={posted}
            rows={2}
            placeholder="وصف موجز للقيد — مثال: دفعة أولى · صفقة D-0023 — مصنع ABC"
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-900 dark:text-white disabled:opacity-60 focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            value={header.description}
            onChange={(e) => setHeader((h) => ({ ...h, description: e.target.value }))}
          />
        </div>
      </div>

      {/* ── بنود القيد ── */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300">بنود القيد</h2>
          {totalDebit > 0 || totalCredit > 0 ? (
            balanced ? (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle className="w-3.5 h-3.5" /> متوازن
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs text-rose-600 dark:text-rose-400 font-medium">
                <AlertTriangle className="w-3.5 h-3.5" />
                فرق: {diff > 0 ? "+" : ""}{diff.toFixed(2)}
              </span>
            )
          ) : null}
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th className="text-right px-3 py-2.5 font-medium text-gray-600 dark:text-gray-400 min-w-[180px]">
                  الحساب <span className="text-red-400">*</span>
                </th>
                <th className="text-right px-3 py-2.5 font-medium text-gray-600 dark:text-gray-400 min-w-[160px]">
                  بيان السطر
                </th>
                <th className="text-right px-3 py-2.5 font-medium text-gray-600 dark:text-gray-400 hidden lg:table-cell min-w-[140px]">
                  شريك / جهة
                </th>
                <th className="text-right px-3 py-2.5 font-medium text-gray-600 dark:text-gray-400 hidden xl:table-cell min-w-[130px]">
                  مركز تكلفة
                </th>
                <th className="text-center px-3 py-2.5 font-medium text-blue-600 dark:text-blue-400 w-32">
                  مدين (Dr)
                </th>
                <th className="text-center px-3 py-2.5 font-medium text-rose-600 dark:text-rose-400 w-32">
                  دائن (Cr)
                </th>
                <th className="w-9" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {lines.map((line, i) => {
                const hasAmount = parseFloat(line.debit) > 0 || parseFloat(line.credit) > 0;
                const isDebit = parseFloat(line.debit) > 0;
                const isCredit = parseFloat(line.credit) > 0;
                return (
                  <tr
                    key={i}
                    className={`transition-colors ${
                      hasAmount
                        ? isDebit
                          ? "bg-blue-50/30 dark:bg-blue-900/10"
                          : "bg-rose-50/30 dark:bg-rose-900/10"
                        : "hover:bg-gray-50 dark:hover:bg-gray-900/20"
                    }`}
                  >
                    {/* الحساب */}
                    <td className="px-3 py-2">
                      {posted ? (
                        <span className="text-xs text-gray-700 dark:text-gray-300">
                          {accounts.find((a) => String(a.id) === line.accountId)
                            ? `${accounts.find((a) => String(a.id) === line.accountId)!.code} — ${accounts.find((a) => String(a.id) === line.accountId)!.name}`
                            : "—"}
                        </span>
                      ) : (
                        <select
                          className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs bg-white dark:bg-gray-900 dark:text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                          value={line.accountId}
                          onChange={(e) => updateLine(i, { accountId: e.target.value })}
                        >
                          <option value="">— اختر الحساب —</option>
                          {accounts.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.code} — {a.name}
                            </option>
                          ))}
                        </select>
                      )}
                    </td>

                    {/* بيان السطر */}
                    <td className="px-3 py-2">
                      {posted ? (
                        <span className="text-xs text-gray-600 dark:text-gray-400">
                          {line.description || "—"}
                        </span>
                      ) : (
                        <input
                          type="text"
                          placeholder="وصف اختياري"
                          className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs bg-white dark:bg-gray-900 dark:text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                          value={line.description}
                          onChange={(e) => updateLine(i, { description: e.target.value })}
                        />
                      )}
                    </td>

                    {/* الشريك */}
                    <td className="px-3 py-2 hidden lg:table-cell">
                      {posted ? (
                        <span className="text-xs text-gray-600 dark:text-gray-400">
                          {partners.find((p) => String(p.id) === line.partnerId)?.name || "—"}
                        </span>
                      ) : (
                        <select
                          className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs bg-white dark:bg-gray-900 dark:text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                          value={line.partnerId}
                          onChange={(e) => updateLine(i, { partnerId: e.target.value })}
                        >
                          <option value="">—</option>
                          {partners.map((p) => (
                            <option key={p.id} value={p.id}>{p.name}</option>
                          ))}
                        </select>
                      )}
                    </td>

                    {/* مركز التكلفة */}
                    <td className="px-3 py-2 hidden xl:table-cell">
                      {posted ? (
                        <span className="text-xs text-gray-600 dark:text-gray-400">
                          {costCenters.find((c) => String(c.id) === line.costCenterId)?.name || "—"}
                        </span>
                      ) : (
                        <select
                          className="w-full border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs bg-white dark:bg-gray-900 dark:text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                          value={line.costCenterId}
                          onChange={(e) => updateLine(i, { costCenterId: e.target.value })}
                        >
                          <option value="">—</option>
                          {costCenters.map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                          ))}
                        </select>
                      )}
                    </td>

                    {/* مدين */}
                    <td className="px-3 py-2">
                      {posted ? (
                        <span className={`block text-center text-xs font-mono font-semibold ${isDebit ? "text-blue-700 dark:text-blue-300" : "text-gray-300 dark:text-gray-600"}`}>
                          {isDebit ? fmtAmount(line.debit) : ""}
                        </span>
                      ) : (
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="0.00"
                          className={`w-full border rounded-lg px-2 py-1.5 text-center text-xs font-mono focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-gray-900 dark:text-white ${
                            isDebit
                              ? "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20"
                              : "border-gray-200 dark:border-gray-600"
                          }`}
                          value={line.debit}
                          onChange={(e) => updateLine(i, { debit: e.target.value })}
                        />
                      )}
                    </td>

                    {/* دائن */}
                    <td className="px-3 py-2">
                      {posted ? (
                        <span className={`block text-center text-xs font-mono font-semibold ${isCredit ? "text-rose-700 dark:text-rose-300" : "text-gray-300 dark:text-gray-600"}`}>
                          {isCredit ? fmtAmount(line.credit) : ""}
                        </span>
                      ) : (
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="0.00"
                          className={`w-full border rounded-lg px-2 py-1.5 text-center text-xs font-mono focus:ring-1 focus:ring-rose-500 focus:border-rose-500 bg-white dark:bg-gray-900 dark:text-white ${
                            isCredit
                              ? "border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-900/20"
                              : "border-gray-200 dark:border-gray-600"
                          }`}
                          value={line.credit}
                          onChange={(e) => updateLine(i, { credit: e.target.value })}
                        />
                      )}
                    </td>

                    {/* حذف */}
                    <td className="px-2 py-2">
                      {!posted && lines.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeLine(i)}
                          className="p-1 text-gray-300 hover:text-red-500 dark:hover:text-red-400 rounded transition-colors"
                          title="حذف السطر"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>

            {/* مجموع */}
            <tfoot className="bg-gray-50 dark:bg-gray-900/40 border-t-2 border-gray-200 dark:border-gray-600">
              <tr>
                <td colSpan={2} className="px-3 py-3 text-xs text-gray-500 dark:text-gray-400">
                  {lines.filter((l) => l.accountId && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)).length} سطر نشط
                </td>
                <td className="hidden lg:table-cell" />
                <td className="hidden xl:table-cell" />
                <td className="px-3 py-3 text-center">
                  <span className="block text-xs text-blue-600 dark:text-blue-400 mb-0.5">مدين</span>
                  <span className="font-mono font-bold text-blue-700 dark:text-blue-300 text-sm">
                    {totalDebit.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </td>
                <td className="px-3 py-3 text-center">
                  <span className="block text-xs text-rose-600 dark:text-rose-400 mb-0.5">دائن</span>
                  <span className="font-mono font-bold text-rose-700 dark:text-rose-300 text-sm">
                    {totalCredit.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {/* ── أزرار الحفظ ── */}
      {!posted && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setLines((prev) => [...prev, emptyLine()])}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            إضافة سطر
          </button>
          <div className="flex-1" />
          <button
            type="button"
            disabled={saving}
            onClick={saveOnly}
            className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            حفظ مسودة
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={saveAndPost}
            className={`flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors ${
              balanced && totalDebit > 0
                ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                : "bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 cursor-not-allowed"
            }`}
            title={!balanced ? "يجب توازن القيد أولاً" : ""}
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
            حفظ وترحيل
          </button>
        </div>
      )}

      {/* تذكير متوازن */}
      {posted && (
        <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl px-4 py-3">
          <CheckCircle className="w-4 h-4 flex-shrink-0" />
          هذا القيد مرحّل ومؤكد — لا يمكن تعديله.
        </div>
      )}
    </div>
  );
};
