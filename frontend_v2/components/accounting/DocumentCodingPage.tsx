/**
 * issue #85 (#77 القسم ٧، الجانب الأمامي) — شاشة الترميز الدفعي.
 *
 * شبكةٌ واحدة كثيفة تُدار بلوحة المفاتيح لا نمط العمودين (عمودا Xero شاشةُ
 * مطابقةٍ بنكية تلزمها تغذيةٌ آلية لا نملكها؛ والمحاسب هنا يعمل من رزمة ورق).
 * تستهلك نقطة الحفظ الدفعي وقواعد الترميز التي بنتها التذكرة #84 خادمياً —
 * لا نقطة جديدة هنا.
 *
 * Enter ينزل صفّاً (`KitGrid` — نفس محرّك قيد اليومية)، وTab ينتقل حقلاً
 * بترتيب DOM الطبيعي بلا جافاسكربت إضافي. الحساب يُقترح من الطرف فور كتابة
 * اسمٍ رُمِّز من قبل، وتجاوز الاقتراح مجرّد كتابةٍ فوقه — بلا سؤال ولا تحذير.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { accountingApi } from "../../services/accountingApi";
import { createReviewQuery } from "../../services/accountantApi";
import { cloudinaryService } from "../../services/cloudinaryService";
import { useToast } from "../../contexts/ToastContext";
import { humanizeThrown } from "../../utils/drfError";
import { formatMoney } from "../../utils/formatNumber";
import { resolveTenantId } from "../../utils/tenantContext";
import { FileDropZone } from "../ui/FileDropZone";
import { PaymentVoucherModal } from "../sales/PaymentVoucherParts";
import { KitDocumentShell, KitGrid } from "../kit";
import type { KitGridColumn, KitToolbarAction } from "../kit";
import { MessageCircle, Plus, Save, Trash2, X } from "lucide-react";
import type { AccountingPartner, CodingRuleDto, VoucherBatchSaveRow } from "../../types/accounting";

type AccountRow = {
  id: number; code: string | null; name: string | null; parent: number | null; account_type?: string | null;
};
type CurrencyRow = { CurrencyID: number; Code: string };
type Direction = "expense" | "revenue";

type CodingRow = {
  key: number;
  date: string;
  direction: Direction;
  partnerText: string;
  partnerId: number | null;
  docNumber: string;
  amount: string;
  taxAmount: string;
  accountText: string;
  accountId: number | null;
  /** اليد لمست الحساب يدوياً — يوقف اقتراح الطرف من الكتابة فوق اختيار المستخدم. */
  accountTouched: boolean;
  attachmentUrl: string;
  attachmentBusy: boolean;
  /** رسالة الفشل من آخر محاولة حفظ — الصفّ الخاطئ يبقى في الشبكة بخطئه. */
  error: string | null;
};

const today = () => new Date().toISOString().slice(0, 10);

const accountLabel = (a: { code?: string | null; name?: string | null }) =>
  `${a.code ?? ""} ${a.name ?? ""}`.trim();

/** هل الصفّ يحمل ما يستحق إرساله؟ صفٌّ فارغٌ تماماً (الأخير الجاهز للكتابة) يُتجاهل. */
const rowIsFillable = (r: CodingRow) =>
  r.amount.trim() !== "" || r.accountText.trim() !== "" || r.partnerText.trim() !== "" || r.docNumber.trim() !== "";

export const DocumentCodingPage: React.FC = () => {
  const toast = useToast();

  const keySeqRef = useRef(0);
  const makeRow = useCallback((): CodingRow => {
    keySeqRef.current += 1;
    return {
      key: keySeqRef.current,
      date: today(),
      direction: "expense",
      partnerText: "",
      partnerId: null,
      docNumber: "",
      amount: "",
      taxAmount: "",
      accountText: "",
      accountId: null,
      accountTouched: false,
      attachmentUrl: "",
      attachmentBusy: false,
      error: null,
    };
  }, []);

  const [rows, setRows] = useState<CodingRow[]>(() => [makeRow()]);
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [currencies, setCurrencies] = useState<CurrencyRow[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  const [codingRules, setCodingRules] = useState<CodingRuleDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [discussRowKey, setDiscussRowKey] = useState<number | null>(null);

  const refreshCodingRules = useCallback(async () => {
    try {
      const rules = await accountingApi.getCodingRules();
      setCodingRules(rules || []);
    } catch {
      // الاقتراح ثانويّ — فشل تحديثه لا يوقف الشاشة.
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [accs, currs, parts, rules] = await Promise.all([
        accountingApi.getAccounts() as Promise<AccountRow[]>,
        accountingApi.getCurrencies() as Promise<CurrencyRow[]>,
        accountingApi.getPartners() as Promise<AccountingPartner[]>,
        accountingApi.getCodingRules(),
      ]);
      setAccounts(accs || []);
      setCurrencies(currs || []);
      setPartners(parts || []);
      setCodingRules(rules || []);
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل التحميل"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const defaultCurrencyId = currencies[0]?.CurrencyID ?? null;

  const codingRuleByPartner = useMemo(() => {
    const map = new Map<number, CodingRuleDto>();
    for (const rule of codingRules) map.set(rule.partner, rule);
    return map;
  }, [codingRules]);

  const expenseAccountOptions = useMemo(
    () => accounts.filter((a) => a.account_type === "Expense"), [accounts],
  );
  const revenueAccountOptions = useMemo(
    () => accounts.filter((a) => a.account_type === "Revenue"), [accounts],
  );

  const updateRow = useCallback((idx: number, patch: Partial<CodingRow>) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }, []);

  const removeRow = useCallback((idx: number) => {
    setRows((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      return next.length ? next : [makeRow()];
    });
  }, [makeRow]);

  /** T85: اقتراح الحساب فور كتابة اسم طرفٍ رُمِّز من قبل — يبقى قابلاً للتجاوز
   * بلا سؤال ولا تحذير؛ `accountTouched` وحدها توقف الاقتراح، لا تأكيدٌ من المستخدم. */
  const handlePartnerChange = useCallback((idx: number, value: string) => {
    const needle = value.trim().toLowerCase();
    const matched = needle ? partners.find((p) => p.name.trim().toLowerCase() === needle) : undefined;
    setRows((prev) => prev.map((r, i) => {
      if (i !== idx) return r;
      const next: CodingRow = { ...r, partnerText: value, partnerId: matched?.id ?? null };
      if (matched && !r.accountTouched) {
        const rule = codingRuleByPartner.get(matched.id);
        if (rule) {
          next.accountId = rule.account;
          next.accountText = accountLabel({ code: rule.account_code, name: rule.account_name });
        }
      }
      return next;
    }));
  }, [partners, codingRuleByPartner]);

  const handleAccountChange = useCallback((idx: number, value: string) => {
    const needle = value.trim().toLowerCase();
    const matched = needle
      ? (accounts.find((a) => accountLabel(a).toLowerCase() === needle)
        || accounts.find((a) => (a.code ?? "").toLowerCase() === needle))
      : undefined;
    updateRow(idx, { accountText: value, accountId: matched?.id ?? null, accountTouched: true });
  }, [accounts, updateRow]);

  const handleDirectionChange = useCallback((idx: number, direction: Direction) => {
    // شجرتا المصروف والإيراد منفصلتان — حسابٌ من الاتجاه السابق لا يصلح هنا.
    setRows((prev) => prev.map((r, i) => (
      i === idx ? { ...r, direction, accountId: null, accountText: "", accountTouched: false } : r
    )));
  }, []);

  const handleAttachmentUpload = useCallback(async (idx: number, file: File) => {
    updateRow(idx, { attachmentBusy: true });
    try {
      const url = await cloudinaryService.uploadFile(file);
      updateRow(idx, { attachmentUrl: url, attachmentBusy: false });
    } catch (e: unknown) {
      updateRow(idx, { attachmentBusy: false });
      toast(humanizeThrown(e, "فشل رفع المرفق"), "error");
    }
  }, [updateRow, toast]);

  const totals = useMemo(() => {
    let amount = 0;
    let tax = 0;
    for (const r of rows) {
      amount += Number(r.amount) || 0;
      tax += Number(r.taxAmount) || 0;
    }
    return { count: rows.length, amount, tax };
  }, [rows]);

  const handleSave = useCallback(async () => {
    if (defaultCurrencyId == null) {
      setErr("لا عملة معرَّفة لهذه الشركة بعد");
      return;
    }
    const candidates = rows.map((r, idx) => ({ r, idx })).filter(({ r }) => rowIsFillable(r));
    if (candidates.length === 0) return;

    setSaving(true);
    setErr(null);
    try {
      const body: VoucherBatchSaveRow[] = candidates.map(({ r }) => ({
        direction: r.direction,
        date: r.date,
        amount: r.amount || "0",
        tax_amount: r.taxAmount || "0",
        currency: defaultCurrencyId,
        exchange_rate: "1",
        // بلا صندوق/بنك في هذه الشاشة عمداً — الترميز الدفعي يسجّل «على الحساب»؛
        // تسوية النقد مسارٌ آخر (سندات القبض/الصرف).
        payment_method: "on_account",
        ...(r.accountId ? { account: r.accountId } : (r.accountText.trim() ? { account_name: r.accountText.trim() } : {})),
        ...(r.partnerId ? { partner: r.partnerId } : (r.partnerText.trim() ? { partner_name: r.partnerText.trim() } : {})),
        ...(r.docNumber.trim() ? { description: r.docNumber.trim() } : {}),
        ...(r.attachmentUrl ? { attachment_url: r.attachmentUrl } : {}),
      }));

      const result = await accountingApi.batchSaveVouchers(body);

      const successOriginalIdx = new Set<number>();
      const errorByOriginalIdx = new Map<number, string>();
      for (const outcome of result.rows) {
        const original = candidates[outcome.index]?.idx;
        if (original == null) continue;
        if (outcome.success) successOriginalIdx.add(original);
        else errorByOriginalIdx.set(original, outcome.error || "فشل حفظ الصفّ");
      }

      setRows((prev) => {
        const kept: CodingRow[] = [];
        prev.forEach((r, i) => {
          if (successOriginalIdx.has(i)) return;
          kept.push(errorByOriginalIdx.has(i) ? { ...r, error: errorByOriginalIdx.get(i)! } : { ...r, error: null });
        });
        return kept.length ? kept : [makeRow()];
      });

      if (result.succeeded > 0) {
        toast(`تم حفظ ${result.succeeded} سند${result.succeeded > 1 ? "اً" : ""}`, "success");
        await refreshCodingRules();
      }
      if (result.failed > 0) {
        toast(`فشل حفظ ${result.failed} صفّ${result.failed > 1 ? "اً" : ""} — راجع الشبكة`, "error");
      }
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل الحفظ الدفعي"));
    } finally {
      setSaving(false);
    }
  }, [rows, defaultCurrencyId, makeRow, toast, refreshCodingRules]);

  type GridRow = CodingRow & { _idx: number };
  const gridRows: GridRow[] = rows.map((r, i) => ({ ...r, _idx: i }));

  const getCell = (row: GridRow, key: string): string | number => {
    switch (key) {
      case "date": return row.date;
      case "docNumber": return row.docNumber;
      case "amount": return row.amount;
      case "taxAmount": return row.taxAmount;
      default: return "";
    }
  };

  const onCellChange = (rowIndex: number, key: string, value: string) => {
    if (key === "date") updateRow(rowIndex, { date: value });
    else if (key === "docNumber") updateRow(rowIndex, { docNumber: value });
    else if (key === "amount") updateRow(rowIndex, { amount: value });
    else if (key === "taxAmount") updateRow(rowIndex, { taxAmount: value });
  };

  const renderDateCell = (row: GridRow) => (
    <div>
      <input
        type="date" className="ktra-input" data-ktra-key="1"
        value={row.date}
        onChange={(e) => updateRow(row._idx, { date: e.target.value })}
      />
      {row.error && (
        <div className="text-[10px] leading-tight mt-1" style={{ color: "var(--ktra-danger, #e03131)" }}>
          {row.error}
        </div>
      )}
    </div>
  );

  const renderDirectionCell = (row: GridRow) => (
    <select
      className="ktra-input" data-ktra-key="1"
      value={row.direction}
      onChange={(e) => handleDirectionChange(row._idx, e.target.value as Direction)}
    >
      <option value="expense">مصروف</option>
      <option value="revenue">إيراد</option>
    </select>
  );

  const renderPartnerCell = (row: GridRow) => (
    <input
      className="ktra-input" data-ktra-key="1"
      list="ktra-coding-partners"
      placeholder="اسم الطرف (اختياري)"
      value={row.partnerText}
      onChange={(e) => handlePartnerChange(row._idx, e.target.value)}
    />
  );

  const renderDocNumberCell = (row: GridRow) => (
    <input
      className="ktra-input" data-ktra-key="1"
      placeholder="رقم الفاتورة/الإيصال"
      value={row.docNumber}
      onChange={(e) => updateRow(row._idx, { docNumber: e.target.value })}
    />
  );

  const renderAmountCell = (row: GridRow) => (
    <input
      type="number" step="0.01" min="0" className="ktra-input ktra-num" data-ktra-key="1"
      value={row.amount}
      onChange={(e) => updateRow(row._idx, { amount: e.target.value })}
    />
  );

  const renderTaxCell = (row: GridRow) => (
    <input
      type="number" step="0.01" min="0" className="ktra-input ktra-num" data-ktra-key="1"
      value={row.taxAmount}
      onChange={(e) => updateRow(row._idx, { taxAmount: e.target.value })}
    />
  );

  const renderAccountCell = (row: GridRow) => (
    <input
      className="ktra-input" data-ktra-key="1"
      list={row.direction === "expense" ? "ktra-coding-accounts-expense" : "ktra-coding-accounts-revenue"}
      placeholder="حساب المصروف/الإيراد"
      value={row.accountText}
      onChange={(e) => handleAccountChange(row._idx, e.target.value)}
    />
  );

  const renderAttachmentCell = (row: GridRow) => {
    if (row.attachmentUrl) {
      return (
        <div className="flex items-center gap-1">
          <a href={row.attachmentUrl} target="_blank" rel="noopener noreferrer" className="text-xs underline">
            مرفق
          </a>
          <button
            type="button" className="ktra-iconbtn" title="إزالة المرفق"
            onClick={() => updateRow(row._idx, { attachmentUrl: "" })}
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      );
    }
    return (
      <div style={{ width: "92px", height: "36px" }}>
        <FileDropZone
          variant="compact"
          accept="image-pdf"
          interactionRequired
          busy={row.attachmentBusy}
          hint="إرفاق"
          ariaLabel={`مرفق صفّ الترميز رقم ${row._idx + 1}`}
          onFiles={(files) => { if (files[0]) void handleAttachmentUpload(row._idx, files[0]); }}
        />
      </div>
    );
  };

  const renderActionsCell = (row: GridRow) => (
    <div className="flex items-center gap-1">
      <button
        type="button" className="ktra-iconbtn" title="ناقِش هذا الصفّ"
        onClick={() => setDiscussRowKey(row.key)}
      >
        <MessageCircle className="w-3 h-3" />
      </button>
      {rows.length > 1 && (
        <button
          type="button" className="ktra-iconbtn ktra-iconbtn--danger" title="حذف الصفّ"
          onClick={() => removeRow(row._idx)}
        >
          <Trash2 className="w-3 h-3" />
        </button>
      )}
    </div>
  );

  const gridColumns: KitGridColumn<GridRow>[] = [
    { key: "date", header: "التاريخ", width: "130px", render: renderDateCell },
    { key: "direction", header: "الاتجاه", width: "90px", render: renderDirectionCell },
    { key: "partner", header: "الطرف", width: "16%", render: renderPartnerCell },
    { key: "docNumber", header: "رقم المستند", width: "14%", render: renderDocNumberCell },
    { key: "amount", header: "المبلغ", width: "110px", type: "number", render: renderAmountCell },
    { key: "taxAmount", header: "الضريبة", width: "100px", type: "number", render: renderTaxCell },
    { key: "account", header: "الحساب", width: "20%", render: renderAccountCell },
    { key: "attachment", header: "مرفق", width: "110px", render: renderAttachmentCell },
    { key: "actions", header: "", width: "70px", render: renderActionsCell },
  ];

  const actions: KitToolbarAction[] = [
    { key: "add", label: "إضافة صفّ", icon: <Plus className="w-4 h-4" />, onClick: () => setRows((prev) => [...prev, makeRow()]) },
    {
      key: "save", label: saving ? "جارٍ الحفظ…" : "حفظ", icon: <Save className="w-4 h-4" />,
      onClick: () => void handleSave(), disabled: saving || loading,
    },
  ];

  const discussRow = discussRowKey != null ? rows.find((r) => r.key === discussRowKey) ?? null : null;

  return (
    <div>
      {err && <div className="ktra-banner ktra-banner--err" style={{ marginBottom: "8px" }}>{err}</div>}
      <datalist id="ktra-coding-partners">
        {partners.map((p) => <option key={p.id} value={p.name} />)}
      </datalist>
      <datalist id="ktra-coding-accounts-expense">
        {expenseAccountOptions.map((a) => <option key={a.id} value={accountLabel(a)} />)}
      </datalist>
      <datalist id="ktra-coding-accounts-revenue">
        {revenueAccountOptions.map((a) => <option key={a.id} value={accountLabel(a)} />)}
      </datalist>

      <KitDocumentShell
        title="ترميز مستندات"
        actions={actions}
        status={
          <span className="ktra-status-item">
            {totals.count} صفّ · إجمالي {formatMoney(totals.amount)} · ضريبة {formatMoney(totals.tax)}
          </span>
        }
      >
        <KitGrid<GridRow>
          columns={gridColumns}
          rows={gridRows}
          getCell={getCell}
          getRowKey={(r) => r.key}
          onChange={onCellChange}
          onAddRow={() => setRows((prev) => [...prev, makeRow()])}
          variant="journal"
          emptyHint="ابدأ الترميز — Enter للصفّ التالي"
        />
      </KitDocumentShell>

      {discussRow && (
        <DiscussRowModal row={discussRow} onClose={() => setDiscussRowKey(null)} />
      )}
    </div>
  );
};

const DiscussRowModal: React.FC<{ row: CodingRow; onClose: () => void }> = ({ row, onClose }) => {
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [severity, setSeverity] = useState<"blocker" | "warning" | "info">("warning");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const rowSummary = [row.date, row.partnerText, row.docNumber, row.amount && formatMoney(row.amount)]
    .filter(Boolean).join(" — ") || "صفّ ترميز بلا بيانات بعد";

  const submit = useCallback(async () => {
    if (!title.trim() || !body.trim()) {
      setErr("العنوان والنص مطلوبان");
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      await createReviewQuery(resolveTenantId(), {
        title: title.trim(),
        body: body.trim(),
        severity,
        // #85: لا نوع كيانٍ مسجَّل لسندات الإيراد/المصروف في `ReviewQuery.ENTITY_TYPES`
        // بعد — «other» + وصف الصفّ في `entity_label` بدل توسيع تلك القائمة هنا.
        entity_type: "other",
        entity_label: rowSummary,
      });
      toast("أُرسل طلب التوضيح", "success");
      onClose();
    } catch (e: unknown) {
      setErr(humanizeThrown(e, "فشل إرسال طلب التوضيح"));
    } finally {
      setSubmitting(false);
    }
  }, [title, body, severity, rowSummary, toast, onClose]);

  return (
    <PaymentVoucherModal
      title="ناقِش هذا الصفّ"
      error={err}
      submitting={submitting}
      submitLabel="إرسال طلب التوضيح"
      onClose={onClose}
      onSubmit={() => void submit()}
    >
      <div className="text-xs mb-3" style={{ color: "var(--ktra-ink-soft)" }}>{rowSummary}</div>
      <label className="ktra-field">
        <span className="ktra-field-label">العنوان *</span>
        <input className="ktra-input" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="ktra-field" style={{ marginTop: "8px", display: "block" }}>
        <span className="ktra-field-label">النص *</span>
        <textarea className="ktra-input" rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
      </label>
      <label className="ktra-field" style={{ marginTop: "8px" }}>
        <span className="ktra-field-label">الأهمية</span>
        <select className="ktra-input" value={severity} onChange={(e) => setSeverity(e.target.value as typeof severity)}>
          <option value="info">معلومة</option>
          <option value="warning">تحذير</option>
          <option value="blocker">مانع</option>
        </select>
      </label>
    </PaymentVoucherModal>
  );
};

export default DocumentCodingPage;
