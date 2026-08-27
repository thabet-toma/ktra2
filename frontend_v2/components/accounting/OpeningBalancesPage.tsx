/**
 * THA-119 (T119-3) — الأرصدة الافتتاحية: حسابات · أطراف · مخزون.
 *
 * مستند واحد لكل شركة. الحسابات وبضاعة أول المدة تُرحَّل في **قيد موحّد واحد**
 * بتاريخ `start_date − 1`، وطرفه الموازن حساب «3300 أرصدة افتتاحية» — وهو
 * «صافي حقوق الملكية الافتتاحية» الذي يعرضه الرأس. أرصدة الأطراف تبقى على
 * آليتها القائمة (قيد لكل طرف على 3300 نفسه) فلا يُدخَل الرقم نفسه مرتين:
 * تبويب «حسابات» يرفض خادمياً الذمم والمخزون وحساب 3300 وأي حساب مربوط بطرف.
 *
 * الخادم: `accounting/opening_balance.py` + `OpeningBalanceViewSet`.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Barcode, CalendarDays, Plus, RefreshCw, RotateCcw, Save, Send, Trash2 } from "lucide-react";

import { accountingApi } from "../../services/accountingApi";
import { inventoryApi } from "../../services/inventoryApi";
import { useConfirm } from "../../contexts/ConfirmContext";
import { useToast } from "../../contexts/ToastContext";
import { formatMoney, formatQuantity } from "../../utils/formatNumber";
import { formatDateLocalized } from "../../utils/formatDate";
import { humanizeThrown } from "../../utils/drfError";
import { KitDocumentShell, KitAutocomplete, KitDateInput } from "../kit";
import type { KitTab, KitToolbarAction } from "../kit";
import { AccountTreeField } from "./AccountTreePicker";
import type { AccountingAccount, OpeningBalanceDto } from "../../types/accounting";

type Warehouse = { id: number; name: string };
type Product = { id: number; sku?: string; name_ar?: string; name_en?: string; display_name?: string | null };
type PartnerLookup = { id: number; name: string; partner_type?: string; linked_account?: number | null };

/** سطر حساب في المسودة — `key` محليّ كي لا يقفز التركيز عند إعادة الترقيم. */
type AccountRow = { key: string; account: number | ""; debit: string; credit: string; notes: string };
type StockRow = { key: string; product: number | ""; warehouse: number | ""; quantity: string; unit_cost: string };

/** التصنيفات التي يرفضها الخادم في تبويب «حسابات» — أرقامها تأتي من رِجل أخرى. */
const FORBIDDEN_SUB_TYPES = new Set(["receivable", "payable", "inventory"]);

let rowSeq = 0;
const nextKey = () => `r${++rowSeq}`;

const num = (v: unknown): number => {
  const n = Number(v ?? 0);
  return Number.isFinite(n) ? n : 0;
};

/**
 * اليوم السابق لتاريخ ISO — نفس اشتقاق `OpeningBalance.entry_date` في الخادم،
 * يُعرض قبل الحفظ كي يرى المستخدم تاريخ قيده وهو يكتب تاريخ البدء.
 */
const previousDay = (iso: string | null | undefined): string | null => {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  d.setDate(d.getDate() - 1);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

/** خطأ الفترة المالية يستحق زرّاً لا نصّاً: المستخدم لا يعرف أين يُنشئ فترة. */
const isFiscalPeriodError = (message: string): boolean =>
  message.includes("فترة مالية") || message.includes("الفترة المالية");

const productLabel = (p: Product): string =>
  p.display_name || p.name_ar || p.name_en || p.sku || `منتج #${p.id}`;

export const OpeningBalancesPage: React.FC = () => {
  const navigate = useNavigate();
  const confirm = useConfirm();
  const toast = useToast();

  const [data, setData] = useState<OpeningBalanceDto | null>(null);
  const [accounts, setAccounts] = useState<AccountingAccount[]>([]);
  const [partners, setPartners] = useState<PartnerLookup[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);

  const [startDate, setStartDate] = useState("");
  const [accountRows, setAccountRows] = useState<AccountRow[]>([]);
  const [stockRows, setStockRows] = useState<StockRow[]>([]);
  /** أرصدة الأطراف قيد التحرير — المفتاح معرّف الطرف. */
  const [partnerDrafts, setPartnerDrafts] = useState<Record<number, string>>({});
  const [newPartner, setNewPartner] = useState<number | "">("");
  const [newPartnerAmount, setNewPartnerAmount] = useState("");

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const posted = data?.status === "posted";

  /** يملأ حالة الشاشة من حمولة الخادم — كل نداء كتابة يُرجعها كاملةً. */
  const applyPayload = useCallback((payload: OpeningBalanceDto) => {
    setData(payload);
    setStartDate(payload.start_date ?? "");
    setAccountRows(
      payload.account_lines.map((l) => ({
        key: nextKey(),
        account: l.account,
        debit: num(l.debit) === 0 ? "" : String(l.debit),
        credit: num(l.credit) === 0 ? "" : String(l.credit),
        notes: l.notes ?? "",
      })),
    );
    setStockRows(
      payload.stock_lines.map((l) => ({
        key: nextKey(),
        product: l.product,
        warehouse: l.warehouse,
        quantity: String(l.quantity),
        unit_cost: String(l.unit_cost),
      })),
    );
    setPartnerDrafts({});
    setNewPartner("");
    setNewPartnerAmount("");
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [payload, accs, prts, prods, whs] = await Promise.all([
        accountingApi.getOpeningBalance(),
        accountingApi.getAccounts() as Promise<AccountingAccount[]>,
        accountingApi.getPartners() as Promise<PartnerLookup[]>,
        inventoryApi.getAllProducts() as Promise<Product[]>,
        inventoryApi.getWarehouses({ active_only: "true" }) as Promise<Warehouse[]>,
      ]);
      applyPayload(payload);
      setAccounts(accs || []);
      setPartners(prts || []);
      setProducts(prods || []);
      setWarehouses(whs || []);
    } catch (e) {
      setErr(humanizeThrown(e, "تعذّر تحميل الأرصدة الافتتاحية"));
    } finally {
      setLoading(false);
    }
  }, [applyPayload]);

  useEffect(() => { void load(); }, [load]);

  // ── الحسابات الممنوعة: نفس حرّاس الخادم، مطبَّقة على الشجرة قبل الاختيار ──
  const parentIds = useMemo(() => {
    const ids = new Set<number>();
    for (const a of accounts) if (a.parent != null) ids.add(a.parent);
    return ids;
  }, [accounts]);

  const partnerAccountIds = useMemo(() => {
    const ids = new Set<number>();
    for (const p of partners) if (p.linked_account != null) ids.add(p.linked_account);
    return ids;
  }, [partners]);

  const offsetCode = data?.offset_account_code ?? "3300";

  const accountSelectable = useCallback(
    (a: { id: number; code?: string | null; sub_type?: string | null; is_active?: boolean }) =>
      a.is_active !== false
      && !parentIds.has(a.id)
      && !FORBIDDEN_SUB_TYPES.has(String(a.sub_type ?? ""))
      && String(a.code ?? "") !== offsetCode
      && !partnerAccountIds.has(a.id),
    [parentIds, partnerAccountIds, offsetCode],
  );

  // ── المجاميع محسوبة محلياً بنفس معادلة `opening_balance_summary` كي يرى ──
  // المستخدم أثر ما يكتبه قبل الحفظ؛ المرحَّل يقرأ مجاميع الخادم لا المسودة.
  const totals = useMemo(() => {
    if (posted && data) {
      return {
        debit: num(data.totals.accounts_debit),
        credit: num(data.totals.accounts_credit),
        stock: num(data.totals.stock_value),
        plug: num(data.totals.equity_plug),
      };
    }
    const debit = accountRows.reduce((s, r) => s + num(r.debit), 0);
    const credit = accountRows.reduce((s, r) => s + num(r.credit), 0);
    const stock = stockRows.reduce((s, r) => s + num(r.quantity) * num(r.unit_cost), 0);
    return { debit, credit, stock, plug: debit + stock - credit };
  }, [posted, data, accountRows, stockRows]);

  const entryDate = posted ? data?.entry_date ?? null : previousDay(startDate);

  const linesPayload = () => ({
    start_date: startDate || null,
    account_lines: accountRows
      .filter((r) => r.account !== "" && (num(r.debit) !== 0 || num(r.credit) !== 0))
      .map((r) => ({
        account: Number(r.account),
        debit: String(num(r.debit)),
        credit: String(num(r.credit)),
        notes: r.notes,
      })),
    stock_lines: stockRows
      .filter((r) => r.product !== "" && r.warehouse !== "" && num(r.quantity) > 0)
      .map((r) => ({
        product: Number(r.product),
        warehouse: Number(r.warehouse),
        quantity: String(num(r.quantity)),
        unit_cost: String(num(r.unit_cost)),
      })),
  });

  const saveDraft = async (): Promise<boolean> => {
    setBusy(true);
    setErr(null);
    try {
      applyPayload(await accountingApi.saveOpeningBalanceLines(linesPayload()));
      return true;
    } catch (e) {
      setErr(humanizeThrown(e, "تعذّر حفظ المسودة"));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const onSave = async () => {
    if (await saveDraft()) toast("تم حفظ مسودة الأرصدة الافتتاحية", "success");
  };

  /**
   * الترحيل يحفظ أولاً ثم يرحّل: ما يُرحَّل هو ما تراه الشاشة بالضبط، لا آخر
   * مسودة محفوظة قد تكون أقدم مما بين يدي المستخدم.
   */
  const onPost = async () => {
    if (!startDate) { setErr("حدّد تاريخ بدء التشغيل أولاً — تاريخ القيد يُشتقّ منه."); return; }
    const ok = await confirm({
      title: "ترحيل القيد الافتتاحي",
      message: (
        <div className="space-y-1 text-sm">
          <div>تاريخ القيد: <strong>{formatDateLocalized(entryDate)}</strong> (اليوم السابق لبدء التشغيل)</div>
          <div>صافي حقوق الملكية الافتتاحية: <strong>{formatMoney(totals.plug)}</strong> على حساب «{offsetCode}»</div>
          <div>بضاعة أول المدة تدخل المخزون بتاريخ القيد نفسه، ولا يُرحَّل قيد افتتاحي ثانٍ إلا بإلغاء هذا.</div>
        </div>
      ),
      confirmText: "رحّل",
      danger: false,
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await accountingApi.saveOpeningBalanceLines(linesPayload());
      applyPayload(await accountingApi.postOpeningBalance());
      toast("تم ترحيل القيد الافتتاحي", "success");
    } catch (e) {
      setErr(humanizeThrown(e, "تعذّر الترحيل"));
    } finally {
      setBusy(false);
    }
  };

  const onUnpost = async () => {
    const ok = await confirm({
      title: "إلغاء ترحيل القيد الافتتاحي",
      message:
        "سيُحذف القيد الافتتاحي وتُعكس حركات بضاعة أول المدة. "
        + "إن كانت بضاعة الافتتاح قد بيعت فسيرفض النظام الإلغاء ويعرض المستندات المعتمِدة عليها.",
      confirmText: "ألغِ الترحيل",
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      applyPayload(await accountingApi.unpostOpeningBalance());
      toast("أُلغي ترحيل القيد الافتتاحي — الأرصدة صارت مسودة", "success");
    } catch (e) {
      setErr(humanizeThrown(e, "تعذّر إلغاء الترحيل"));
    } finally {
      setBusy(false);
    }
  };

  const savePartner = async (partnerId: number, amount: string) => {
    setBusy(true);
    setErr(null);
    try {
      // بلا تاريخ: يتبع تاريخ القيد الافتتاحي للشركة فتتوحّد تواريخ أرجل الافتتاح.
      await accountingApi.savePartnerOpeningBalance(partnerId, { opening_balance: String(num(amount)) });
      applyPayload(await accountingApi.getOpeningBalance());
      toast("تم حفظ رصيد الطرف الافتتاحي", "success");
    } catch (e) {
      setErr(humanizeThrown(e, "تعذّر حفظ رصيد الطرف"));
    } finally {
      setBusy(false);
    }
  };

  const reversePartner = async (partnerId: number, name: string) => {
    const ok = await confirm({
      title: "إلغاء ترحيل رصيد الطرف",
      message: `سيُحذف قيد الرصيد الافتتاحي للطرف «${name}» ويعود رصيده قابلاً للتعديل. `
        + "حفظُ رصيد جديد بعدها يُنشئ قيداً بالمبلغ الجديد.",
      confirmText: "ألغِ الترحيل",
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      applyPayload(await accountingApi.reversePartnerOpeningBalance(partnerId));
      toast(`أُلغي ترحيل رصيد «${name}»`, "success");
    } catch (e) {
      setErr(humanizeThrown(e, "تعذّر إلغاء ترحيل رصيد الطرف"));
    } finally {
      setBusy(false);
    }
  };

  // ── التبويبات ────────────────────────────────────────────────────────────
  const accountsTab = (
    <div className="p-2">
      <table className="ktra-grid" data-variant="list">
        <thead>
          <tr>
            <th>الحساب</th>
            <th className="w-[15%]">مدين</th>
            <th className="w-[15%]">دائن</th>
            <th className="w-[25%]">ملاحظات</th>
            <th className="w-10"></th>
          </tr>
        </thead>
        <tbody>
          {accountRows.length === 0 && (
            <tr>
              <td colSpan={5} className="p-4 text-center text-[var(--ktra-ink-soft)]">
                لا أرصدة حسابات — أضف سطراً. (الذمم من تبويب «الأطراف»، والمخزون من تبويب «المخزون»)
              </td>
            </tr>
          )}
          {accountRows.map((row, i) => (
            <tr key={row.key}>
              <td>
                <AccountTreeField
                  accounts={accounts}
                  value={row.account}
                  disabled={posted}
                  title="اختيار حساب للرصيد الافتتاحي"
                  isSelectable={accountSelectable}
                  onChange={(id) =>
                    setAccountRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, account: id ?? "" } : r)))
                  }
                />
              </td>
              <td>
                <input
                  type="number" step="any" min="0" className="ktra-input ktra-num"
                  value={row.debit} disabled={posted}
                  onChange={(e) =>
                    setAccountRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, debit: e.target.value, credit: "" } : r)))
                  }
                />
              </td>
              <td>
                <input
                  type="number" step="any" min="0" className="ktra-input ktra-num"
                  value={row.credit} disabled={posted}
                  onChange={(e) =>
                    setAccountRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, credit: e.target.value, debit: "" } : r)))
                  }
                />
              </td>
              <td>
                <input
                  className="ktra-input" value={row.notes} disabled={posted}
                  onChange={(e) =>
                    setAccountRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, notes: e.target.value } : r)))
                  }
                />
              </td>
              <td className="text-center">
                {!posted && (
                  <button
                    type="button" className="ktra-iconbtn" title="حذف السطر"
                    onClick={() => setAccountRows((rs) => rs.filter((_, idx) => idx !== i))}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="font-bold">المجموع</td>
            <td className="ktra-num font-bold">{formatMoney(totals.debit)}</td>
            <td className="ktra-num font-bold">{formatMoney(totals.credit)}</td>
            <td colSpan={2}></td>
          </tr>
        </tfoot>
      </table>
      {!posted && (
        <button
          type="button" className="ktra-toolbtn mt-2"
          onClick={() => setAccountRows((rs) => [...rs, { key: nextKey(), account: "", debit: "", credit: "", notes: "" }])}
        >
          <Plus className="h-4 w-4" /> سطر حساب
        </button>
      )}
    </div>
  );

  const partnerRows = data?.partners ?? [];
  const partnerOptions = useMemo(
    () => partners.map((p) => ({ id: p.id, label: `${p.name}${p.partner_type ? ` — ${p.partner_type === "Customer" ? "عميل" : "مورّد"}` : ""}` })),
    [partners],
  );

  const partnersTab = (
    <div className="p-2">
      <div className="mb-2 text-xs text-[var(--ktra-ink-soft)]">
        رصيد الطرف يُرحَّل بقيد مستقلّ على حساب «{offsetCode}» نفسه — موجبٌ يعني أن العميل مدين لنا
        (أو أننا مدينون للمورّد)، وسالبٌ يعني دفعةً مقدَّمة. تعديل رصيدٍ مُرحَّل لا يصل الدفاتر إلا
        بإلغاء ترحيله أولاً.
      </div>
      <table className="ktra-grid" data-variant="list">
        <thead>
          <tr>
            <th>الطرف</th>
            <th className="w-[12%]">النوع</th>
            <th className="w-[16%]">الرصيد الافتتاحي</th>
            <th className="w-[14%]">المرحَّل في الدفاتر</th>
            <th className="w-[12%]">التاريخ</th>
            <th className="w-[22%]">الحالة</th>
          </tr>
        </thead>
        <tbody>
          {partnerRows.length === 0 && (
            <tr>
              <td colSpan={6} className="p-4 text-center text-[var(--ktra-ink-soft)]">
                لا أرصدة أطراف افتتاحية بعد
              </td>
            </tr>
          )}
          {partnerRows.map((p) => {
            const draft = partnerDrafts[p.id];
            const value = draft !== undefined ? draft : String(p.opening_balance);
            const drifted = p.is_posted && p.posted_amount != null
              && num(p.posted_amount) !== num(p.opening_balance);
            return (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td className="text-center">{p.partner_type === "Customer" ? "عميل" : "مورّد"}</td>
                <td>
                  <input
                    type="number" step="any" className="ktra-input ktra-num"
                    value={value} disabled={p.is_posted}
                    onChange={(e) => setPartnerDrafts((d) => ({ ...d, [p.id]: e.target.value }))}
                  />
                </td>
                <td className="ktra-num">
                  {p.posted_amount != null ? formatMoney(p.posted_amount) : "—"}
                </td>
                <td className="text-center">{formatDateLocalized(p.opening_balance_date)}</td>
                <td>
                  <div className="flex flex-wrap items-center gap-2">
                    {p.is_posted ? (
                      <>
                        <span className="badge badge-success">مرحّل{p.journal ? ` #${p.journal}` : ""}</span>
                        <button
                          type="button" className="ktra-toolbtn" disabled={busy}
                          onClick={() => void reversePartner(p.id, p.name)}
                        >
                          <RotateCcw className="h-3 w-3" /> إلغاء الترحيل
                        </button>
                      </>
                    ) : (
                      <>
                        <span className="badge badge-warning">غير مرحّل</span>
                        <button
                          type="button" className="ktra-toolbtn" disabled={busy}
                          onClick={() => void savePartner(p.id, value)}
                        >
                          <Save className="h-3 w-3" /> حفظ وترحيل
                        </button>
                      </>
                    )}
                    {drifted && (
                      <span className="text-xs text-amber-700">
                        المُدخل ({formatMoney(p.opening_balance)}) يخالف المرحَّل — ألغِ الترحيل ليصل التعديل الدفاتر
                      </span>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="ktra-field min-w-[280px] flex-1">
          <span className="ktra-field-label">إضافة رصيد افتتاحي لطرف</span>
          <KitAutocomplete
            value={newPartner === "" ? "" : (partners.find((p) => p.id === newPartner)?.name ?? "")}
            options={partnerOptions}
            onPick={(id) => setNewPartner(Number(id))}
            placeholder="اكتب اسم العميل أو المورّد…"
          />
        </label>
        <label className="ktra-field w-[160px]">
          <span className="ktra-field-label">المبلغ</span>
          <input
            type="number" step="any" className="ktra-input ktra-num"
            value={newPartnerAmount} onChange={(e) => setNewPartnerAmount(e.target.value)}
          />
        </label>
        <button
          type="button" className="ktra-toolbtn"
          disabled={busy || newPartner === "" || num(newPartnerAmount) === 0}
          onClick={() => void savePartner(Number(newPartner), newPartnerAmount)}
        >
          <Plus className="h-4 w-4" /> إضافة وترحيل
        </button>
      </div>
    </div>
  );

  /**
   * THA-411 — منتجات الافتتاح المتتبَّعة تسلسلياً بعد الترحيل.
   *
   * الترحيل يُدخل الكمية للمخزن ولا يُنشئ وحدةً مُرقَّمة واحدة، فشركةٌ نمط بيعها
   * «إجباري» تُصدَم عند أول فاتورة برسالة «المتوفر في المخزن 0 والمطلوب N» بلا ما
   * يقول أين تُرقَّم. هذه اللوحة تقول المُسجَّل والمطلوب وتفتح كرت المنتج على تبويب
   * الأرقام التسلسلية — لا ترقيمَ من هنا: المسار القائم هو الذي يُرقِّم.
   *
   * قبل الترحيل لا تُعرض: لا رصيد بعد يُرقَّم (سقف الترقيم رصيد المخزن).
   */
  const serialItems = data?.serial_items ?? [];
  const serialsPanel = !posted || serialItems.length === 0 ? null : (
    <div className="mt-3 rounded border border-amber-300 bg-amber-50 p-2 text-xs dark:border-amber-700 dark:bg-amber-950/40">
      <div className="mb-2 font-bold">منتجات تتتبّع أرقاماً تسلسلية في بضاعة أول المدة</div>
      <div className="mb-2 text-[var(--ktra-ink-soft)]">
        القيد الافتتاحي أدخل الكميات للمخزن ولا يُنشئ أرقاماً تسلسلية — تُنشأ من استلام الشراء.
        إن كان إدخال الرقم التسلسلي إجبارياً في البيع فلن تُباع هذه الوحدات قبل ترقيمها،
        ورقّمها من كرت المنتج. الافتتاح صحيح بلا أرقام؛ البيع وحده هو ما يحتاجها.
      </div>
      <table className="ktra-grid" data-variant="list">
        <thead>
          <tr>
            <th>المنتج</th>
            <th className="w-[14%]">المسجَّل</th>
            <th className="w-[14%]">المطلوب</th>
            <th className="w-[28%]"></th>
          </tr>
        </thead>
        <tbody>
          {serialItems.map((item) => {
            const complete = item.serials_registered >= item.quantity;
            return (
              <tr key={item.product}>
                <td>{item.product_name}{item.product_sku ? ` — ${item.product_sku}` : ""}</td>
                <td className="ktra-num">{formatQuantity(item.serials_registered, "0")}</td>
                <td className="ktra-num">{formatQuantity(item.quantity, "0")}</td>
                <td>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={complete ? "badge badge-success" : "badge badge-warning"}>
                      {complete
                        ? "مُرقَّم بالكامل"
                        : `ناقص ${formatQuantity(item.quantity - item.serials_registered, "0")}`}
                    </span>
                    <button
                      type="button" className="ktra-toolbtn"
                      title="يفتح كرت المنتج على تبويب الأرقام التسلسلية"
                      onClick={() => navigate(`/products/${item.product}?tab=serials`)}
                    >
                      <Barcode className="h-3 w-3" /> رقّم وحدات هذا المنتج
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const stockTab = (
    <div className="p-2">
      <div className="mb-2 text-xs text-[var(--ktra-ink-soft)]">
        بضاعة أول المدة: كمية وتكلفة وحدة لكل منتج/مستودع. تدخل المخزون بتاريخ القيد الافتتاحي
        فيتكوّن متوسط التكلفة صحيحاً قبل أول شراء، وقيمتها تُرحَّل مدينةً على حساب المخزون في
        الأستاذ — فيتطابق الرقمان بالضرورة.
      </div>
      <table className="ktra-grid" data-variant="list">
        <thead>
          <tr>
            <th>المنتج</th>
            <th className="w-[18%]">المستودع</th>
            <th className="w-[13%]">الكمية</th>
            <th className="w-[13%]">تكلفة الوحدة</th>
            <th className="w-[13%]">القيمة</th>
            <th className="w-10"></th>
          </tr>
        </thead>
        <tbody>
          {stockRows.length === 0 && (
            <tr>
              <td colSpan={6} className="p-4 text-center text-[var(--ktra-ink-soft)]">
                لا بضاعة أول مدة — أضف سطراً
              </td>
            </tr>
          )}
          {stockRows.map((row, i) => {
            const product = products.find((p) => p.id === Number(row.product));
            return (
              <tr key={row.key}>
                <td>
                  {row.product !== "" ? (
                    <span>{product ? productLabel(product) : `منتج #${row.product}`}</span>
                  ) : (
                    <KitAutocomplete
                      value=""
                      options={products.map((p) => ({ id: p.id, label: productLabel(p) }))}
                      onPick={(id) =>
                        setStockRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, product: Number(id) } : r)))
                      }
                      placeholder="اكتب الاسم أو الكود للبحث…"
                    />
                  )}
                </td>
                <td>
                  <select
                    className="ktra-input" value={row.warehouse} disabled={posted}
                    onChange={(e) =>
                      setStockRows((rs) => rs.map((r, idx) => (
                        idx === i ? { ...r, warehouse: e.target.value ? Number(e.target.value) : "" } : r
                      )))
                    }
                  >
                    <option value="">— اختر مستودعاً —</option>
                    {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </td>
                <td>
                  <input
                    type="number" step="any" min="0" className="ktra-input ktra-num"
                    value={row.quantity} disabled={posted}
                    onChange={(e) =>
                      setStockRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, quantity: e.target.value } : r)))
                    }
                  />
                </td>
                <td>
                  <input
                    type="number" step="any" min="0" className="ktra-input ktra-num"
                    value={row.unit_cost} disabled={posted}
                    onChange={(e) =>
                      setStockRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, unit_cost: e.target.value } : r)))
                    }
                  />
                </td>
                <td className="ktra-num">{formatMoney(num(row.quantity) * num(row.unit_cost))}</td>
                <td className="text-center">
                  {!posted && (
                    <button
                      type="button" className="ktra-iconbtn" title="حذف السطر"
                      onClick={() => setStockRows((rs) => rs.filter((_, idx) => idx !== i))}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={2} className="font-bold">قيمة بضاعة أول المدة</td>
            <td className="ktra-num">
              {formatQuantity(stockRows.reduce((s, r) => s + num(r.quantity), 0), "0")}
            </td>
            <td></td>
            <td className="ktra-num font-bold">{formatMoney(totals.stock)}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
      {!posted && (
        <button
          type="button" className="ktra-toolbtn mt-2"
          onClick={() => setStockRows((rs) => [...rs, {
            key: nextKey(), product: "", warehouse: warehouses.length === 1 ? warehouses[0].id : "",
            quantity: "", unit_cost: "",
          }])}
        >
          <Plus className="h-4 w-4" /> سطر بضاعة
        </button>
      )}
      {serialsPanel}
    </div>
  );

  const tabs: KitTab[] = [
    { key: "accounts", label: `حسابات (${accountRows.length})`, content: accountsTab },
    { key: "partners", label: `أطراف (${partnerRows.length})`, content: partnersTab },
    { key: "stock", label: `مخزون (${stockRows.length})`, content: stockTab },
  ];

  const actions: KitToolbarAction[] = [
    { key: "save", label: "حفظ المسودة", icon: <Save />, disabled: busy || posted, onClick: () => void onSave() },
    posted
      ? { key: "unpost", label: "إلغاء الترحيل", icon: <RotateCcw />, danger: true, disabled: busy, onClick: () => void onUnpost() }
      : { key: "post", label: "ترحيل القيد الافتتاحي", icon: <Send />, disabled: busy, onClick: () => void onPost() },
    { key: "refresh", label: "تحديث", icon: <RefreshCw className={loading ? "animate-spin" : ""} />, separatorBefore: true, onClick: () => void load() },
  ];

  const header = (
    <div className="flex flex-wrap items-end gap-4">
      <label className="ktra-field w-[170px]">
        <span className="ktra-field-label">تاريخ بدء التشغيل</span>
        <KitDateInput
          className="ktra-input"
          value={startDate}
          disabled={posted}
          onChange={setStartDate}
        />
      </label>
      <div className="ktra-field">
        <span className="ktra-field-label">تاريخ القيد الافتتاحي</span>
        <div className="flex h-[30px] items-center gap-1 text-sm font-bold">
          <CalendarDays className="h-4 w-4" />
          {entryDate ? formatDateLocalized(entryDate) : "—"}
          <span className="text-xs font-normal text-[var(--ktra-ink-soft)]">(اليوم السابق للبدء)</span>
        </div>
      </div>
      <div className="ktra-field">
        <span className="ktra-field-label">الحالة</span>
        <div className="flex h-[30px] items-center">
          {posted ? (
            <span className="badge badge-success">
              مرحّل{data?.journal ? ` — قيد #${data.journal}` : ""}
            </span>
          ) : (
            <span className="badge badge-warning">مسودة</span>
          )}
        </div>
      </div>
      <div className="ktra-field">
        <span className="ktra-field-label">صافي حقوق الملكية الافتتاحية</span>
        <div className="flex h-[30px] items-center gap-2">
          <strong className="ktra-num text-base">{formatMoney(totals.plug)}</strong>
          <span className="text-xs text-[var(--ktra-ink-soft)]">
            على حساب «{offsetCode}» — {totals.plug >= 0 ? "دائن" : "مدين"}
          </span>
        </div>
      </div>
    </div>
  );

  const banner = err ? (
    <div className="ktra-banner ktra-banner--err mb-2">
      <div>{err}</div>
      {isFiscalPeriodError(err) && (
        <button
          type="button" className="ktra-toolbtn mt-1"
          onClick={() => navigate("/accounting/fiscal-periods")}
        >
          <CalendarDays className="h-4 w-4" /> افتح الفترات المالية
        </button>
      )}
    </div>
  ) : null;

  return (
    <KitDocumentShell
      title="الأرصدة الافتتاحية"
      state={posted ? `مرحّل${data?.journal ? ` #${data.journal}` : ""}` : "مسودة"}
      actions={actions}
      header={<>{header}{banner}</>}
      tabs={tabs}
      status={
        <>
          <span className="ktra-status-item">مدين {formatMoney(totals.debit)}</span>
          <span className="ktra-status-item">دائن {formatMoney(totals.credit)}</span>
          <span className="ktra-status-item">بضاعة أول المدة {formatMoney(totals.stock)}</span>
        </>
      }
    >
      <></>
    </KitDocumentShell>
  );
};

export default OpeningBalancesPage;
