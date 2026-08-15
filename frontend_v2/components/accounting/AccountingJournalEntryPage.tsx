import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { accountingApi } from "../../services/accountingApi";
import { formatMoney, formatNumber } from "../../utils/formatNumber";
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
  Printer,
  RefreshCw,
  X,
  Search,
} from "lucide-react";
import {
  AseelDocumentShell,
  AseelGrid,
  useRecordNavigation,
  useAseelKeymap,
  useAseelFieldShortcuts,
  type AseelGridColumn,
} from "../aseel";
import { AccountTreePicker } from "./AccountTreePicker";
import OfflineGuard from "../offline/OfflineGuard";
import { entityPathForReference } from "../../utils/entityLinks";
import {
  buildHeaderNarration,
  buildLineNarration,
  isGeneratedLineNarration,
  isGeneratedNarration,
  type NarrationLine,
} from "../../utils/journalNarration";

/* ─────────── types ─────────── */

type LineState = {
  id?: number;
  accountId: string;
  partnerId: string;
  costCenterId: string;
  debit: string;
  credit: string;
  description: string;
  /** كتب المستخدم بيان السطر بيده — فلا يدهسه التوليد التلقائي. */
  descriptionTouched?: boolean;
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
  descriptionTouched: false,
});

/** القيد المزدوج طرفان — تبدأ الشبكة بسطرين ويُضاف الثالث عند الحاجة. */
const MIN_LINES = 2;

const startingLines = (): LineState[] =>
  Array.from({ length: MIN_LINES }, emptyLine);

const REF_TYPE_LABELS: Record<string, string> = {
  LOGISTICS_PAYMENT: "دفعة صفقة",
  PURCHASE_RECEIPT: "استلام مخزون",
  JOURNAL_REVERSAL: "عكس قيد",
  LOGISTICS_EXPENSE: "مصروف لوجستي",
  MANUAL: "قيد يدوي",
  // A3: قيد يدوي وسمه المحاسب «تسوية» — لا شاشة مستقلة له عمداً: نفس الشاشة
  // ونفس قواعد التوازن، ووسمٌ يجعله قابلاً للتصفية في دفتر اليومية.
  ADJUSTMENT: "قيد تسوية",
};

function refTypeLabel(t: string, description?: string, sourceLabel?: string) {
  if (
    t === "LOGISTICS_PAYMENT" &&
    description &&
    /\bشحنة\b/i.test(description)
  ) {
    return "دفعة لوجستيات";
  }
  // الخادم يسمّي كل مصادر القيود (source_label) — لا نكرّر الخريطة هنا.
  return REF_TYPE_LABELS[t] || sourceLabel || t;
}

function fmtAmount(v: string | number) {
  return formatMoney(v, "");
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
  const navigate = useNavigate();
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
    source_label: "" as string,
  });

  const [lines, setLines] = useState<LineState[]>(startingLines);
  /** كتب المستخدم البيان الإجمالي بيده — فيتوقّف التوليد التلقائي. */
  const [headerDescTouched, setHeaderDescTouched] = useState(false);

  // N3-T1: Aseel Navigation + account picker state
  const [journalsList, setJournalsList] = useState<any[]>([]);
  const [showAccountPicker, setShowAccountPicker] = useState(false);
  // which line index is waiting for account pick
  const [pickerTargetLine, setPickerTargetLine] = useState<number | null>(null);
  // tooltip: { lineIdx, balance }
  const [balanceTooltip, setBalanceTooltip] = useState<{ lineIdx: number; balance: string } | null>(null);
  const tooltipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** سطر القيد بصيغة مولّد البيان (أسماء بدل معرّفات). */
  const toNarrationLine = useCallback(
    (l: LineState, accs: AccountingAccount[], parts: AccountingPartner[]): NarrationLine => ({
      accountName: accs.find((a) => String(a.id) === l.accountId)?.name || "",
      partnerName: parts.find((p) => String(p.id) === l.partnerId)?.name || "",
      debit: l.debit,
      credit: l.credit,
    }),
    [],
  );

  /** ملء النموذج من قيد محمَّل — مشترك بين التحميل الأول والتنقّل بين السجلات. */
  const hydrateFromJournal = useCallback(
    (j: any, accs: AccountingAccount[], parts: AccountingPartner[]) => {
      setPosted(!!j.is_posted);
      const desc = j.description || "";
      setHeader((h) => ({
        ...h,
        transaction_date: j.transaction_date || "",
        description: desc,
        reference_type: j.reference_type || "",
        reference_id: j.reference_id != null ? String(j.reference_id) : "",
        reference_summary: j.reference_summary || "",
        deal_ref_number: j.deal_ref_number || "",
        currency: j.currency != null ? String(j.currency) : h.currency,
        exchange_rate: j.exchange_rate != null ? String(j.exchange_rate) : "1",
        currency_code: j.currency_code || "",
        source_label: j.source_label || "",
      }));
      const mapped: LineState[] = (j.lines || []).map((line: any) => ({
        id: line.id,
        accountId: line.account != null ? String(line.account) : "",
        partnerId: line.partner != null ? String(line.partner) : "",
        costCenterId: line.cost_center != null ? String(line.cost_center) : "",
        debit: parseFloat(String(line.debit)) > 0 ? String(line.debit) : "",
        credit: parseFloat(String(line.credit)) > 0 ? String(line.credit) : "",
        description: line.description || "",
        descriptionTouched: false,
      }));
      // بيان محفوظ يوافق ما يولّده النظام يبقى تلقائياً (يتبع تغيير الحسابات)،
      // وما كتبه المستخدم بيده يُصان كما هو.
      const narration = mapped.map((l) => toNarrationLine(l, accs, parts));
      mapped.forEach((l, i) => {
        l.descriptionTouched = !isGeneratedLineNarration(l.description, narration[i], desc);
      });
      setHeaderDescTouched(!isGeneratedNarration(desc, narration));
      while (mapped.length < MIN_LINES) mapped.push(emptyLine());
      setLines(mapped);
    },
    [toNarrationLine],
  );

  const nav = useRecordNavigation<any>({
    items: journalsList,
    getId: (j) => j.id || 0,
    currentId: journalId,
    onSelect: async (id) => {
      if (id === null) {
        // New journal - reset form
        setHeader({
          transaction_date: new Date().toISOString().split("T")[0],
          description: "",
          reference_type: "MANUAL",
          reference_id: "",
          reference_summary: "",
          deal_ref_number: "",
          currency: "",
          exchange_rate: "1",
          currency_code: "",
          source_label: "",
        });
        setLines(startingLines());
        setHeaderDescTouched(false);
        setPosted(false);
      } else {
        try {
          const j = await accountingApi.getJournal(Number(id));
          hydrateFromJournal(j, accounts, partners);
        } catch (err) {
          // console suppressed
        }
      }
    },
  });

  // N3-T1: Aseel keyboard shortcuts.
  useAseelKeymap({
    F2: () => window.print(),
    F5: () => load(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    F12: () => saveAndPost(),
    Escape: () => {
      if (balanceTooltip) { setBalanceTooltip(null); return; }
      if (showAccountPicker) { setShowAccountPicker(false); setPickerTargetLine(null); return; }
      onBack();
    },
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => nav.goNew(),
  }, { enabled: !showAccountPicker });

  // N3-T1: Field shortcuts — Space=auto-balance, *=balance-lookup, +=account-picker
  useAseelFieldShortcuts({
    'remaining-fill': () => {
      // autofill the remaining diff on the focused debit/credit cell
      const ae = document.activeElement as HTMLInputElement | null;
      if (!ae) return;
      const lineIdx = Number(ae.getAttribute('data-line-idx'));
      if (isNaN(lineIdx)) return;
      const side = ae.getAttribute('data-side') as 'debit' | 'credit' | null;
      if (!side) return;
      const remaining = Math.abs(diff);
      if (remaining < 0.005) return;
      if (side === 'debit' && diff < 0) {
        updateLine(lineIdx, { debit: formatNumber(remaining, { maxDecimals: 2 }) });
      } else if (side === 'credit' && diff > 0) {
        updateLine(lineIdx, { credit: formatNumber(remaining, { maxDecimals: 2 }) });
      }
    },
  }, { enabled: !showAccountPicker });

  // P0-5: قائمة التنقّل (الأول/السابق/التالي) كانت تجلب **كل** القيود —
  // صارت أحدث 200 قيد (القائمة مُرقَّمة إلزامياً خادمياً). فتح قيد أقدم
  // مباشرةً بالرابط يبقى شغّالاً؛ التنقّل التسلسلي يغطي الأحدث.
  useEffect(() => {
    const loadJournals = async () => {
      try {
        const paged = await accountingApi.getJournalsPaged({
          page: "1", page_size: "200",
        });
        setJournalsList(paged.results);
      } catch (err) {
        // console suppressed
      }
    };
    loadJournals();
  }, []);

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
      const activeAccounts = (acc as AccountingAccount[]).filter((a) => a.is_active);
      setAccounts(activeAccounts);
      setPartners(part as AccountingPartner[]);
      setCostCenters(cc as CostCenterDto[]);
      setCurrencies(cur as CurrencyDto[]);

      const baseCurrency = (cur as CurrencyDto[]).find((c) => c.IsBaseCurrency);

      if (journalId != null) {
        const j = await accountingApi.getJournal(journalId);
        if (j.currency == null && baseCurrency) j.currency = baseCurrency.CurrencyID;
        hydrateFromJournal(j, activeAccounts, part as AccountingPartner[]);
      } else {
        setPosted(false);
        setLines(startingLines());
        setHeader((h) => ({ ...h, reference_type: h.reference_type || "MANUAL" }));
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
          setHeaderDescTouched(true);
        } else {
          setHeaderDescTouched(false);
        }
      }
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [journalId, dealRef?.displayName, hydrateFromJournal]);

  useEffect(() => { void load(); }, [load]);

  /* ── توليد البيان تلقائياً من الحسابات (يتوقف عند أي كتابة يدوية) ── */
  useEffect(() => {
    if (posted || loading) return;
    const narration = lines.map((l) => toNarrationLine(l, accounts, partners));
    const nextHeaderDesc = headerDescTouched
      ? header.description
      : buildHeaderNarration(narration);
    if (!headerDescTouched && nextHeaderDesc !== header.description) {
      setHeader((h) => ({ ...h, description: nextHeaderDesc }));
    }
    // بيان السطر يتبع حسابه حين يكون البيان الإجمالي مولَّداً (صيغة «من ح/ … إلى ح/ …»
    // لا تصلح بياناً لسطر مفرد)، ويتبع ما كتبه المستخدم حين يكتبه بيده.
    const lineBase = headerDescTouched ? nextHeaderDesc : "";
    setLines((prev) => {
      let changed = false;
      const next = prev.map((l, i) => {
        if (l.descriptionTouched || !narration[i]) return l;
        const want = buildLineNarration(narration[i], lineBase);
        if (want === l.description) return l;
        changed = true;
        return { ...l, description: want };
      });
      return changed ? next : prev;
    });
  }, [lines, accounts, partners, header.description, headerDescTouched, posted, loading, toNarrationLine]);

  /* ── N3-T1: account balance lookup helper (يَستخدم getGeneralLedger مع YTD) ── */
  const showAccountBalance = useCallback(async (lineIdx: number, accountId: string) => {
    if (!accountId) return;
    if (tooltipTimerRef.current) clearTimeout(tooltipTimerRef.current);
    setBalanceTooltip({ lineIdx, balance: '...' });
    try {
      const today = new Date();
      const ledger = await accountingApi.getGeneralLedger({
        account_id: accountId,
        start_date: `${today.getFullYear()}-01-01`,
        end_date: today.toISOString().split('T')[0],
      });
      const closing = Number((ledger as { closing_balance?: number | string })?.closing_balance ?? 0);
      const fmt = (v: number) => formatMoney(v);
      const label = `الرصيد: ${fmt(Math.abs(closing))} ${closing >= 0 ? 'مدين' : 'دائن'}`;
      setBalanceTooltip({ lineIdx, balance: label });
      tooltipTimerRef.current = setTimeout(() => setBalanceTooltip(null), 4000);
    } catch {
      setBalanceTooltip({ lineIdx, balance: 'تعذّر جلب الرصيد' });
      tooltipTimerRef.current = setTimeout(() => setBalanceTooltip(null), 3000);
    }
  }, []);

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
    if (!balanced) return `القيد غير متوازن (فرق ${formatMoney(diff)})`;
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
      <div className="flex items-center justify-center py-24 text-[var(--color-text-muted)]">
        <Loader2 className="w-6 h-6 animate-spin ml-2" />
        جاري التحميل…
      </div>
    );
  }

  /* ── N3-T1: AseelGrid columns for journal lines ── */
  const journalGridColumns: AseelGridColumn<LineState & { _idx: number }>[] = [
    { key: 'seq',         header: '#',          width: '40px',  align: 'center', readOnly: true },
    { key: 'account',     header: 'الحساب',      width: '22%' },
    { key: 'description', header: 'البيان',      width: '20%' },
    { key: 'partner',     header: 'الجهة',       width: '13%' },
    { key: 'costCenter',  header: 'مركز التكلفة', width: '13%' },
    { key: 'debit',       header: 'مدين (Dr)',    width: '110px', align: 'center', type: 'number' },
    { key: 'credit',      header: 'دائن (Cr)',    width: '110px', align: 'center', type: 'number' },
    { key: 'del',         header: '',            width: '36px',  align: 'center' },
  ];

  type GridLine = LineState & { _idx: number };

  const gridLines: GridLine[] = lines.map((l, i) => ({ ...l, _idx: i }));

  const gridGetCell = (row: GridLine, key: string): string | number => {
    switch (key) {
      case 'seq':    return row._idx + 1;
      case 'debit':  return row.debit;
      case 'credit': return row.credit;
      case 'description': return row.description;
      default: return '';
    }
  };

  const renderCostCenterCell = (row: GridLine) => {
    if (posted) return <span className="text-xs">{costCenters.find((c) => String(c.id) === row.costCenterId)?.name || '—'}</span>;
    return (
      <select
        className="aseel-input"
        value={row.costCenterId}
        onChange={(e) => updateLine(row._idx, { costCenterId: e.target.value })}
      >
        <option value="">—</option>
        {costCenters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
    );
  };

  const gridOnChange = (rowIndex: number, key: string, value: string) => {
    // تفريغ البيان يدوياً يعيده إلى التوليد التلقائي.
    if (key === 'description') updateLine(rowIndex, { description: value, descriptionTouched: !!value.trim() });
    else if (key === 'debit')  updateLine(rowIndex, { debit: value });
    else if (key === 'credit') updateLine(rowIndex, { credit: value });
  };

  const renderAccountCell = (row: GridLine) => {
    const acc = accounts.find((a) => String(a.id) === row.accountId);
    const label = acc ? `${acc.code} — ${acc.name}` : '— اختر الحساب —';
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', position: 'relative' }}>
        <button
          type="button"
          className="aseel-cell-picker"
          disabled={posted}
          data-aseel-key="1"
          title="+ فتح شجرة الحسابات  |  * عرض الرصيد"
          onKeyDown={(e) => {
            if (e.key === '+') { e.preventDefault(); setPickerTargetLine(row._idx); setShowAccountPicker(true); }
            if (e.key === '*') { e.preventDefault(); void showAccountBalance(row._idx, row.accountId); }
          }}
          onClick={() => { if (!posted) { setPickerTargetLine(row._idx); setShowAccountPicker(true); } }}
        >
          {label}
        </button>
        {balanceTooltip?.lineIdx === row._idx && (
          <span style={{
            position: 'absolute', top: '100%', right: 0, zIndex: 50,
            background: 'var(--aseel-bg, #fffbf5)',
            border: '1px solid var(--aseel-border, #c8b99a)',
            borderRadius: '4px', padding: '3px 8px',
            fontSize: '11px', whiteSpace: 'nowrap', fontWeight: 600,
            boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
          }}>
            {balanceTooltip.balance}
          </span>
        )}
      </div>
    );
  };

  const renderDebitCell = (row: GridLine) => {
    const isDebit = parseFloat(row.debit) > 0;
    if (posted) return (
      <span className={`block text-center text-xs font-mono font-semibold ${isDebit ? 'aseel-text-accent' : 'aseel-text-soft'}`}>
        {isDebit ? fmtAmount(row.debit) : ''}
      </span>
    );
    return (
      <input
        type="number" step="0.01" min="0" placeholder="0.00"
        className="aseel-input aseel-num"
        data-aseel-field="remaining-amount"
        data-aseel-key="1"
        data-line-idx={String(row._idx)}
        data-side="debit"
        value={row.debit}
        onChange={(e) => updateLine(row._idx, { debit: e.target.value })}
        title="Space = تعبئة الفرق تلقائياً"
        style={{ color: isDebit ? 'var(--color-primary, #3b5bdb)' : undefined }}
      />
    );
  };

  const renderCreditCell = (row: GridLine) => {
    const isCredit = parseFloat(row.credit) > 0;
    if (posted) return (
      <span className={`block text-center text-xs font-mono font-semibold ${isCredit ? 'aseel-text-ink' : 'aseel-text-soft'}`}>
        {isCredit ? fmtAmount(row.credit) : ''}
      </span>
    );
    return (
      <input
        type="number" step="0.01" min="0" placeholder="0.00"
        className="aseel-input aseel-num"
        data-aseel-field="remaining-amount"
        data-aseel-key="1"
        data-line-idx={String(row._idx)}
        data-side="credit"
        value={row.credit}
        onChange={(e) => updateLine(row._idx, { credit: e.target.value })}
        title="Space = تعبئة الفرق تلقائياً"
        style={{ color: isCredit ? 'var(--color-danger, #e03131)' : undefined }}
      />
    );
  };

  const renderPartnerCell = (row: GridLine) => {
    if (posted) return <span className="text-xs">{partners.find((p) => String(p.id) === row.partnerId)?.name || '—'}</span>;
    return (
      <select
        className="aseel-input"
        value={row.partnerId}
        onChange={(e) => updateLine(row._idx, { partnerId: e.target.value })}
      >
        <option value="">—</option>
        {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    );
  };

  const renderDelCell = (row: GridLine) =>
    (!posted && lines.length > 1) ? (
      <button type="button" className="aseel-iconbtn aseel-iconbtn--danger" onClick={() => removeLine(row._idx)} title="حذف السطر">
        <Trash2 className="h-3 w-3" />
      </button>
    ) : null;

  journalGridColumns[1].render = renderAccountCell;     // الحساب
  journalGridColumns[3].render = renderPartnerCell;     // الجهة
  journalGridColumns[4].render = renderCostCenterCell;  // مركز التكلفة
  journalGridColumns[5].render = renderDebitCell;       // مدين
  journalGridColumns[6].render = renderCreditCell;      // دائن
  journalGridColumns[7].render = renderDelCell;         // حذف

  /* ── render ── */
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

  /**
   * مسار المستند المصدر (فاتورة/سند/قيد أصلي). `reference_id` نصّ في الحالة،
   * والمرجع غير الرقمي لا مسار له فيسقط إلى null.
   */
  const sourceRefId = Number(header.reference_id);
  const sourceDocumentPath =
    header.reference_type && Number.isFinite(sourceRefId) && sourceRefId > 0
      ? entityPathForReference(header.reference_type, sourceRefId)
      : null;

  /** A3: قيد كتبه المستخدم بيده (لا مستند مصدر) — وحده يقبل وسم «تسوية». */
  const isManualEntry =
    !header.reference_type ||
    header.reference_type === 'MANUAL' ||
    header.reference_type === 'ADJUSTMENT';
  const isAdjustment = header.reference_type === 'ADJUSTMENT';

  const isShipmentLink =
    relatedKind === "shipment" ||
    (relatedKind == null &&
      header.reference_type === "LOGISTICS_PAYMENT" &&
      /\bشحنة\b/i.test(header.description || ""));

  return (
    <div
      style={{ minHeight: 'calc(100vh - 5rem)', display: 'flex', flexDirection: 'column' }}
    >
    <AseelDocumentShell
      title="قيود المحاسبة"
      state={journalId ? `قيد #${journalId}` : 'قيد جديد'}
      nav={nav}
      actions={[
        {
          key: 'save',
          label: posted ? 'مرحَّل' : 'تخزين',
          icon: <Save />,
          onClick: !posted ? saveAndPost : undefined,
          disabled: posted,
        },
        {
          key: 'reload',
          label: 'تحديث',
          icon: <RefreshCw />,
          onClick: load,
          separatorBefore: true,
        },
        {
          key: 'back',
          label: 'خروج',
          icon: <X />,
          onClick: onBack,
          danger: true,
          separatorBefore: true,
        },
        {
          key: 'print',
          label: 'طباعة',
          icon: <Printer />,
          onClick: () => window.print(),
        },
      ]}
      header={
        <>
          {/* رقم القيد */}
          <label className="aseel-field">
            <span className="aseel-field-label">رقم القيد</span>
            <input className="aseel-input" readOnly value={journalId ? `#${journalId}` : '— جديد —'} />
          </label>
          {/* التاريخ */}
          <label className="aseel-field">
            <span className="aseel-field-label">التاريخ</span>
            <input
              className="aseel-input"
              type="date"
              disabled={posted}
              value={header.transaction_date}
              onChange={(e) => setHeader((h) => ({ ...h, transaction_date: e.target.value }))}
            />
          </label>
          {/* العملة */}
          <label className="aseel-field">
            <span className="aseel-field-label">العملة</span>
            <select
              className="aseel-input"
              disabled={posted}
              value={header.currency}
              onChange={(e) => {
                const sel = currencies.find((c) => String(c.CurrencyID) === e.target.value);
                setHeader((h) => ({
                  ...h,
                  currency: e.target.value,
                  exchange_rate: sel?.IsBaseCurrency ? '1' : h.exchange_rate,
                  currency_code: sel?.Code || '',
                }));
              }}
            >
              <option value="">— اختر —</option>
              {currencies.map((c) => (
                <option key={c.CurrencyID} value={c.CurrencyID}>
                  {c.Code} {c.IsBaseCurrency ? '(أساسية)' : ''}
                </option>
              ))}
            </select>
          </label>
          {/* سعر العملة */}
          <label className="aseel-field">
            <span className="aseel-field-label">سعر العملة</span>
            <input
              className="aseel-input"
              type="number"
              step="0.000001"
              min="0"
              disabled={posted || !!currencies.find((c) => String(c.CurrencyID) === header.currency)?.IsBaseCurrency}
              value={header.exchange_rate}
              onChange={(e) => setHeader((h) => ({ ...h, exchange_rate: e.target.value }))}
            />
          </label>
          {/* نوع المرجع — يحدده النظام من مصدر القيد ولا يُدخَل يدوياً */}
          <label className="aseel-field">
            <span className="aseel-field-label">نوع المرجع</span>
            <input
              className="aseel-input"
              readOnly
              value={header.reference_type
                ? refTypeLabel(header.reference_type, header.description, header.source_label)
                : '—'}
            />
          </label>
          {/* A3: وسم «قيد تسوية» — يدويٌّ فقط، ويجعل القيد قابلاً للتصفية في الدفتر */}
          {isManualEntry && (
            <label className="aseel-field">
              <span className="aseel-field-label">قيد تسوية</span>
              <div
                className="aseel-input"
                style={{ display: 'flex', alignItems: 'center', gap: '6px', minHeight: '28px' }}
              >
                <input
                  type="checkbox"
                  disabled={posted}
                  checked={isAdjustment}
                  onChange={(e) =>
                    setHeader((h) => ({
                      ...h,
                      reference_type: e.target.checked ? 'ADJUSTMENT' : 'MANUAL',
                    }))
                  }
                />
                <span style={{ fontSize: '11px' }}>قيد تسوية محاسبية</span>
              </div>
            </label>
          )}
          {/* البيان الإجمالي — يتولد من الحسابات ما لم يُكتب يدوياً */}
          <label className="aseel-field" style={{ gridColumn: 'span 2' }}>
            <span className="aseel-field-label">
              البيان الإجمالي {headerDescTouched ? '(يدوي)' : '(تلقائي)'}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <input
                className="aseel-input"
                style={{ flex: 1 }}
                disabled={posted}
                placeholder="يتولد تلقائياً: من ح/ … إلى ح/ …"
                value={header.description}
                onChange={(e) => {
                  // تفريغ البيان يدوياً يعيده إلى التوليد التلقائي.
                  setHeaderDescTouched(!!e.target.value.trim());
                  setHeader((h) => ({ ...h, description: e.target.value }));
                }}
              />
              {!posted && headerDescTouched && (
                <button
                  type="button"
                  className="aseel-iconbtn"
                  title="إرجاع البيان إلى التوليد التلقائي حسب الحسابات"
                  onClick={() => {
                    setHeaderDescTouched(false);
                    setLines((prev) => prev.map((l) => ({ ...l, descriptionTouched: false })));
                  }}
                >
                  <RefreshCw className="h-3 w-3" />
                </button>
              )}
            </div>
          </label>
        </>
      }
      status={
        <>
          <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
          <span className="aseel-status-item">الحالة <b>{posted ? 'مرحَّل' : 'مسودة'}</b></span>
          {journalId && <span className="aseel-status-item">رقم القيد <b>{journalId}</b></span>}
          <span className="aseel-status-item">
            مدين <b className="aseel-num">{formatMoney(totalDebit)}</b>
          </span>
          <span className="aseel-status-item">
            دائن <b className="aseel-num">{formatMoney(totalCredit)}</b>
          </span>
          {!balanced && totalDebit > 0 && (
            <span className="aseel-status-item" style={{ color: 'var(--aseel-err, #c0392b)' }}>
              فرق <b>{formatMoney(Math.abs(diff))}</b>
            </span>
          )}
          {balanced && totalDebit > 0 && (
            <span className="aseel-status-item" style={{ color: 'var(--aseel-ok, #27ae60)' }}>
              متوازن ✓
            </span>
          )}
        </>
      }
    >
    <div style={{ height: '100%', overflow: 'auto', padding: '8px 12px', background: 'var(--aseel-bg, #fffbf5)' }}>

      {/* ── ارتباط بصفقة/شحنة (تنقّل) ── */}
      {activeDealRef && (
        <div className="aseel-banner" style={{ marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 12px' }}>
          <Handshake className="w-4 h-4" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontSize: '11px', color: 'var(--aseel-ink-soft)' }}>
              {isShipmentLink ? 'مرتبط بشحنة:' : 'مرتبط بصفقة:'}
            </span>
            <span style={{ fontWeight: 600, marginInlineStart: '6px' }}>{activeDealRef.displayName}</span>
          </div>
          {isShipmentLink && activeDealRef.dealId && onNavigateToShipment && /^\d+$/.test(String(activeDealRef.dealId).trim()) && (
            <button type="button" className="aseel-toolbtn" onClick={() => onNavigateToShipment(String(activeDealRef.dealId).trim())}>
              <ExternalLink className="w-3 h-3" /> فتح الشحنة
            </button>
          )}
          {!isShipmentLink && (activeDealRef.dealId || activeDealRef.dealNumber) && onNavigateToDeal && (
            <button type="button" className="aseel-toolbtn" onClick={() => onNavigateToDeal(activeDealRef.dealId || activeDealRef.dealNumber)}>
              <ExternalLink className="w-3 h-3" /> فتح الصفقة
            </button>
          )}
        </div>
      )}

      {/* ── خطأ ── */}
      {err && (
        <div className="aseel-banner aseel-banner--err" style={{ marginBottom: '8px' }}>
          <AlertTriangle className="w-4 h-4" style={{ marginInlineEnd: '6px' }} />
          {err}
        </div>
      )}

      {/* ── مصدر القيد: يعرضه النظام ولا يُدخَل يدوياً ── */}
      <div className="aseel-input" style={{ display: 'flex', alignItems: 'center', minHeight: '28px', marginBottom: '8px', background: 'var(--aseel-surface-2, #f4ede0)' }}>
        <Info className="w-3 h-3" style={{ marginInlineEnd: '6px', color: 'var(--aseel-ink-soft)' }} />
        <span style={{ fontSize: '12px' }}>
          {!isManualEntry
            ? `مصدر القيد: ${refTypeLabel(header.reference_type, header.description, header.source_label)}${header.reference_id ? ' · #' + header.reference_id : ''}`
            : isAdjustment
              ? 'قيد تسوية يدوي — لا مستند مصدر'
              : 'قيد يدوي — لا مستند مصدر'}
        </span>
        {/* القفزة الثالثة في التنقيب: من القيد إلى المستند الذي أنشأه. */}
        {sourceDocumentPath && (
          <button
            type="button"
            className="aseel-toolbtn"
            style={{ marginInlineStart: 'auto' }}
            title="فتح المستند المصدر"
            onClick={() => navigate(sourceDocumentPath)}
          >
            <ExternalLink className="w-3 h-3" /> فتح المستند
          </button>
        )}
      </div>

      {/* ── AseelGrid لبنود القيد ── */}
      <AseelGrid<GridLine>
        columns={journalGridColumns}
        rows={gridLines}
        getCell={gridGetCell}
        getRowKey={(r) => r._idx}
        onChange={gridOnChange}
        onAddRow={() => setLines((prev) => [...prev, emptyLine()])}
        variant="journal"
        emptyHint="ابدأ إدخال بنود القيد — Enter للسطر التالي"
      />

      {/* ── إجمالي/فرق row ── */}
      <div className="aseel-total-row aseel-total-row--grand" style={{ marginTop: '6px', display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: '12px', padding: '8px 12px' }}>
        <span style={{ fontSize: '12px', color: 'var(--aseel-ink-soft)' }}>
          {lines.filter((l) => l.accountId && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0)).length} سطر نشط
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--aseel-ink-soft)' }}>مدين</span>
          <span className="aseel-num" style={{ fontWeight: 700, color: 'var(--color-primary, #3b5bdb)' }}>{fmtAmount(totalDebit)}</span>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--aseel-ink-soft)' }}>دائن</span>
          <span className="aseel-num" style={{ fontWeight: 700, color: 'var(--color-danger, #e03131)' }}>{fmtAmount(totalCredit)}</span>
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <span style={{ fontSize: '10px', color: 'var(--aseel-ink-soft)' }}>{balanced ? 'متوازن' : 'فرق'}</span>
          <span className="aseel-num" style={{
            fontWeight: 700,
            color: balanced && totalDebit > 0 ? 'var(--aseel-ok, #2d7d46)' : 'var(--aseel-err, #c0392b)',
          }}>
            {balanced && totalDebit > 0 ? '✓' : fmtAmount(Math.abs(diff))}
          </span>
        </span>
      </div>

      {/* ── أزرار سفلية ── */}
      {!posted && (
        <div style={{ display: 'flex', gap: '8px', marginTop: '10px', justifyContent: 'flex-end' }}>
          <button
            type="button"
            className="aseel-toolbtn"
            onClick={() => setLines((prev) => [...prev, emptyLine()])}
          >
            <Plus className="w-3 h-3" /> سطر جديد
          </button>
          <button
            type="button"
            className="aseel-toolbtn"
            disabled={saving}
            onClick={saveOnly}
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            حفظ مسودة
          </button>
          <OfflineGuard
            action="ترحيل القيد"
            warningMessage="الترحيل يتطلب اتصالاً — أرقام القيود تُولَّد على الـserver"
          >
            <button
              type="button"
              className="aseel-toolbtn"
              disabled={saving || !balanced || totalDebit <= 0}
              onClick={saveAndPost}
              title={!balanced ? 'يجب توازن القيد أولاً (F12)' : 'F12 = حفظ وترحيل'}
              style={{
                background: balanced && totalDebit > 0 ? 'var(--aseel-ok, #2d7d46)' : undefined,
                color: balanced && totalDebit > 0 ? '#fff' : undefined,
              }}
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
              حفظ وترحيل (F12)
            </button>
          </OfflineGuard>
        </div>
      )}

      {posted && (
        <div className="aseel-banner" style={{ marginTop: '10px', background: 'var(--aseel-ok-bg, #e3f6e9)', color: 'var(--aseel-ok, #2d7d46)' }}>
          <CheckCircle className="w-3 h-3" style={{ marginInlineEnd: '6px' }} />
          هذا القيد مرحَّل — لا يمكن تعديله.
        </div>
      )}
    </div>

    {/* ── T-DEFACC: شجرة الحسابات (تُفتح بـ + على خلية الحساب) ── */}
    <AccountTreePicker
      open={showAccountPicker}
      accounts={accounts}
      value={pickerTargetLine != null && lines[pickerTargetLine]?.accountId
        ? Number(lines[pickerTargetLine].accountId)
        : null}
      title="شجرة الحسابات"
      onSelect={(a) => {
        if (pickerTargetLine != null) {
          updateLine(pickerTargetLine, { accountId: String(a.id) });
        }
        setShowAccountPicker(false);
        setPickerTargetLine(null);
      }}
      onClose={() => { setShowAccountPicker(false); setPickerTargetLine(null); }}
    />
    </AseelDocumentShell>
    </div>
  );
};
