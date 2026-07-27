import React, { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useConfirm } from "../../contexts/ConfirmContext";
import {
  Trash2,
  Save,
  Loader2,
  Printer,
  X,
} from "lucide-react";
import {
  listQuotationsPage,
  getQuotation,
  createQuotation,
  updateQuotation,
  deleteQuotation,
  convertQuotation,
  cancelQuotation,
  getCustomerPriceList,
  getSalesSettings,
  type SalesQuotationRow,
  type SalesQuotationDetail,
} from "../../services/salesApi";
import { useToast } from "../../contexts/ToastContext";
import { ConvertTargetDialog } from "./ConvertTargetDialog";
import { clientLogger } from "../../services/logger";
import { accountingApi } from "../../services/accountingApi";
import { apiGetList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { formatQuantity } from "../../utils/formatNumber";
import type { SqlProduct } from "../../types/inventory";
import {
  useRecordNavigation,
  useAseelKeymap,
} from "../aseel";
import { SalesProductPickerModal, type SalesProductPickerItem, formatProductPrimaryName } from "./SalesProductPickerModal";
import { SalesOrdersPage } from "./SalesOrdersPage";
import {
  CommercialDocumentEditor,
  type CommercialHeaderField,
  type CommercialLineColumn,
  type CommercialToolbarAction,
} from "../shared/CommercialDocumentEditor";
import {
  CommercialDocumentsList,
  type CommercialListColumn,
} from "../shared/CommercialDocumentsList";

type Partner = { id: number; name: string };
type Product = SalesProductPickerItem & { name: string; unit_price?: string };

type LineState = {
  id?: number;
  product_id: string;
  product_name: string;
  quantity: string;
  unit_price: string;
  discount: string;
  tax_rate: string;
  total: string;
};

export const SalesQuotationsPage: React.FC = () => {
  const confirm = useConfirm();
  const toast = useToast();
  // T-ORDERS: صلاحية العرض ومدة الحجز وإظهار الحذف — كلها من إعدادات الشركة.
  const [quotationValidDays, setQuotationValidDays] = useState(14);
  const [allowDelete, setAllowDelete] = useState(true);
  // العرض المطلوب تحويله — يفتح حوار «طلبية أم فاتورة؟» داخل الموقع (لا حوار متصفح).
  const [convertId, setConvertId] = useState<number | null>(null);
  const [quotations, setQuotations] = useState<SalesQuotationRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [page, setPage] = useState(1);
  const [totalQuotations, setTotalQuotations] = useState(0);
  const pageSize = 50;

  // Form state
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formCustomer, setFormCustomer] = useState("");
  const [formDate, setFormDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [formValidUntil, setFormValidUntil] = useState("");
  const [formNotes, setFormNotes] = useState("");
  // N4-T6: حقول إضافية per spec — فعال checkbox + prices include VAT
  const [formIsActive, setFormIsActive] = useState(true);
  const [formPricesIncludeTax, setFormPricesIncludeTax] = useState(false);
  const [formCustomerAddress, setFormCustomerAddress] = useState("");
  const [formCustomerTaxNumber, setFormCustomerTaxNumber] = useState("");
  const [formLines, setFormLines] = useState<LineState[]>([{
    id: undefined, product_id: "", product_name: "", quantity: "1", unit_price: "", discount: "0", tax_rate: "0", total: "0"
  }]);

  const [productPickerLineIdx, setProductPickerLineIdx] = useState<number | null>(null);

  // معاينة بنود العرض داخل القائمة (طيّ/فتح) — لتُرى البنود بلا فتح النموذج.
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [expandedLines, setExpandedLines] = useState<
    Record<number, Array<{ name: string; quantity: string; unit_price: string; line_total: string }>>
  >({});

  // سعر الزبون من كرته (عرض السعر اليدوي / آخر فاتورة) — يُملأ عند اختيار المنتج.
  const [customerPriceMap, setCustomerPriceMap] = useState<Map<number, string>>(new Map());
  useEffect(() => {
    if (!formCustomer) { setCustomerPriceMap(new Map()); return; }
    let alive = true;
    getCustomerPriceList(formCustomer)
      .then((rows) => {
        if (!alive) return;
        const m = new Map<number, string>();
        for (const r of rows) {
          if (r.price != null && String(r.price).trim() !== "") m.set(r.product_id, String(r.price));
        }
        setCustomerPriceMap(m);
      })
      .catch(() => { if (alive) setCustomerPriceMap(new Map()); });
    return () => { alive = false; };
  }, [formCustomer]);

  // السعر المقترح لبند العرض: سعر كرت الزبون إن وُجد، وإلا سعر المنتج الافتراضي.
  const quotePriceFor = useCallback(
    (productId: number, fallback?: string): string => {
      const cp = customerPriceMap.get(productId);
      if (cp != null && cp !== "") {
        clientLogger.info("quotation.customer_price_applied", { product: productId });
        return cp;
      }
      return fallback || "0";
    },
    [customerPriceMap]
  );

  // Aseel Navigation
  const [showPartnerPicker, setShowPartnerPicker] = useState(false);

  // تحميل عرض سعر وفتح نموذجه (يعرض البنود) — مصدر واحد يخدم «تعديل» ورقم العرض
  // والرابط العميق (?open=) القادم من شارة الفاتورة.
  const openQuotation = useCallback(async (id: number) => {
    try {
      const detail = await getQuotation(id);
      setSelectedId(detail.id);
      setFormCustomer(String(detail.customer));
      setFormDate(detail.quotation_date?.slice(0, 10) || "");
      setFormValidUntil(detail.valid_until?.slice(0, 10) || "");
      setFormNotes(detail.notes || "");
      setFormLines((detail.lines || []).map((l) => ({
        id: l.id,
        product_id: String(l.product),
        product_name: l.product_name || "",
        quantity: l.quantity,
        unit_price: l.unit_price,
        discount: l.line_discount || "0",
        tax_rate: String(l.tax_rate || 0),
        total: l.line_total,
      })));
      setShowForm(true);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  }, []);

  const nav = useRecordNavigation<SalesQuotationRow>({
    items: quotations,
    getId: (q) => q.id || 0,
    currentId: selectedId,
    onSelect: async (id) => {
      if (id === null) {
        resetForm();
        setShowForm(true);
      } else {
        await openQuotation(Number(id));
      }
    },
  });

  // رابط عميق: فتح عرض محدد عند وصول ?open=<id> (من شارة «عرض السعر» بالفاتورة).
  const location = useLocation();
  useEffect(() => {
    const mOpen = location.search.match(/[?&]open=(\d+)/);
    if (mOpen) {
      void openQuotation(Number(mOpen[1]));
      return;
    }
    const isNew = location.search.match(/[?&]action=new/);
    if (isNew) {
      setShowForm(true);
      setSelectedId(null);
      const mCust = location.search.match(/[?&]customer_id=(\d+)/);
      if (mCust) {
        setFormCustomer(mCust[1]);
      }
    }
  }, [location.search, openQuotation]);

  // طيّ/فتح معاينة البنود داخل القائمة — يجلب البنود عند أول فتح ويخزّنها.
  const toggleExpand = useCallback(async (id: number) => {
    setExpandedId((cur) => (cur === id ? null : id));
    if (expandedLines[id]) return;
    try {
      const detail = await getQuotation(id);
      const rows = (detail.lines || []).map((l) => {
        const pr = products.find((p) => String(p.id) === String(l.product));
        return {
          name: l.product_name || (pr ? formatProductPrimaryName(pr) : `#${l.product}`),
          quantity: l.quantity,
          unit_price: l.unit_price,
          line_total: l.line_total,
        };
      });
      setExpandedLines((prev) => ({ ...prev, [id]: rows }));
    } catch { /* تجاهل — تبقى الرسالة «جارٍ التحميل» ثم تُعاد المحاولة عند الطيّ/الفتح */ }
  }, [expandedLines, products]);

  // M4-T5: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => window.print(),
    F5: () => loadQuotations(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    F12: () => handleSave(),
    Escape: () => {
      if (showPartnerPicker) { setShowPartnerPicker(false); return; }
      setShowForm(false);
      setSelectedId(null);
    },
    plus: () => {
      if (document.activeElement?.getAttribute('data-aseel-key') === '1') {
        setShowPartnerPicker(true);
      }
    },
    // N0-T11: Ctrl+nav handlers
    CtrlHome: () => nav?.first?.(),
    CtrlEnd: () => nav?.last?.(),
    CtrlPageUp: () => nav?.prev?.(),
    CtrlPageDown: () => nav?.next?.(),
    CtrlIns: () => { setSelectedId(null); setShowForm(true); },
  });

  const loadQuotations = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const qs = await listQuotationsPage({ page, page_size: pageSize });
      setQuotations(qs.results || []);
      setTotalQuotations(qs.count);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [page]);

  const loadMasterData = useCallback(async () => {
    try {
      // task16 E17: منتقي الصنف في عرض السعر كان يحمّل شجرة الحسابات
      // (getAccounts) بدل الأصناف — يُصحَّح إلى أصناف المخزون (inventory/products).
      const tenantId = resolveTenantId();
      const [parts, prods] = await Promise.all([
        accountingApi.getPartners() as Promise<Partner[]>,
        apiGetList<SqlProduct & { sale_price?: string; selling_price?: string }>(
          "inventory/products/",
          { tenantId }
        ),
      ]);
      setPartners(parts || []);
      setProducts(
        (prods || []).map((p: any) => ({
          id: p.id,
          sku: p.sku || "",
          barcode: p.barcode,
          quantity_on_hand: String(p.available_quantity ?? p.quantity_on_hand ?? "0"),
          name_ar: p.name_ar || p.name || "",
          name_en: p.name_en || "",
          name: p.name_ar || p.name_en || p.name || p.sku || `#${p.id}`,
          unit_price: p.sale_price ?? p.selling_price ?? p.unit_price ?? "",
        }))
      );
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    }
  }, []);

  useEffect(() => {
    void loadQuotations();
  }, [loadQuotations]);

  useEffect(() => { void loadMasterData(); }, [loadMasterData]);

  // T-ORDERS: صلاحية العرض وإظهار «حذف» من إعدادات الشركة (لا قيم مثبّتة بالكود).
  useEffect(() => {
    let alive = true;
    getSalesSettings()
      .then((st) => {
        if (!alive) return;
        setQuotationValidDays(Number(st.quotation_valid_days ?? 14));
        setAllowDelete(st.allow_document_delete !== false);
      })
      .catch(() => { /* الافتراضيات تكفي */ });
    return () => { alive = false; };
  }, []);

  /** T-ORDERS: العرض فعّال افتراضياً حتى (اليوم + أيام الإعداد، 14 يوماً). */
  const defaultValidUntil = useCallback((from?: string) => {
    if (!quotationValidDays) return "";
    const base = from ? new Date(from) : new Date();
    base.setDate(base.getDate() + quotationValidDays);
    return base.toISOString().slice(0, 10);
  }, [quotationValidDays]);

  const resetForm = () => {
    setSelectedId(null);
    setFormCustomer("");
    setFormDate(new Date().toISOString().slice(0, 10));
    setFormValidUntil(defaultValidUntil());
    setFormNotes("");
    setFormLines([{
      id: undefined, product_id: "", product_name: "", quantity: "1", unit_price: "", discount: "0", tax_rate: "0", total: "0"
    }]);
  };

  const handleAddLine = () => {
    setFormLines([...formLines, {
      id: undefined, product_id: "", product_name: "", quantity: "1", unit_price: "", discount: "0", tax_rate: "0", total: "0"
    }]);
  };

  const handleRemoveLine = (idx: number) => {
    if (formLines.length > 1) {
      setFormLines(formLines.filter((_, i) => i !== idx));
    }
  };

  const handleLineChange = (idx: number, field: string, value: string) => {
    handleLineUpdate(idx, { [field]: value });
  };

  const handleLineUpdate = (idx: number, updates: Partial<LineState>) => {
    setFormLines((prev) => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], ...updates };
      // Recalculate total
      const qty = Number(updated[idx].quantity) || 0;
      const price = Number(updated[idx].unit_price) || 0;
      const disc = Number(updated[idx].discount) || 0;
      const tax = Number(updated[idx].tax_rate) || 0;
      const subtotal = qty * price - disc;
      const taxAmt = subtotal * (tax / 100);
      updated[idx].total = String(subtotal + taxAmt);
      return updated;
    });
  };

  const handleSave = async () => {
    if (!formCustomer) {
      setErr("يرجى اختيار العميل");
      return;
    }
    // البنود بلا منتج تُستبعد؛ يجب وجود بند واحد صالح على الأقل.
    const validLines = formLines.filter((l) => l.product_id);
    if (validLines.length === 0) {
      setErr("أضف صنفاً واحداً على الأقل للعرض.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const body = {
        customer: Number(formCustomer),
        // N4-T6 new fields (backend may ignore unknown keys)
        is_active: formIsActive,
        prices_include_tax: formPricesIncludeTax,
        customer_address: formCustomerAddress || null,
        customer_tax_number: formCustomerTaxNumber || null,
        quotation_date: formDate,
        valid_until: formValidUntil || null,
        notes: formNotes,
        lines: validLines.map((l) => ({
          product: Number(l.product_id),
          quantity: l.quantity,
          unit_price: l.unit_price,
          line_discount: l.discount,
          // tax_rate مفتاح أجنبي لنسبة ضريبة — 0/فارغ يعني «بلا ضريبة» ⇒ null (لا 0).
          tax_rate: l.tax_rate && Number(l.tax_rate) > 0 ? Number(l.tax_rate) : null,
        })),
      };
      if (selectedId) {
        await updateQuotation(selectedId, body);
      } else {
        await createQuotation(body);
      }
      resetForm();
      setShowForm(false);
      await loadQuotations();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  /** T-ORDERS: التحويل يختار وجهته — طلبية (تحجز الكمية) أو فاتورة. */
  const handleConvert = async (id: number, target: "invoice" | "order") => {
    setConvertId(null);
    try {
      const result = await convertQuotation(id, target);
      toast(
        target === "order"
          ? `تم التحويل — طلبية رقم ${result.order?.order_number ?? ""}`
          : `تم التحويل — فاتورة رقم ${result.invoice?.invoice_number ?? ""}`,
        "success",
      );
      await loadQuotations();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحويل");
    }
  };

  /** إلغاء بلا حذف — المستند وسجلّه يبقيان. */
  const handleCancel = async (id: number) => {
    if (!(await confirm({
      title: "إلغاء عرض السعر",
      message: "سيُعلَّم العرض «ملغى» ويبقى في السجل (لن يُحذف). متابعة؟",
      confirmText: "إلغاء العرض",
    }))) return;
    try {
      await cancelQuotation(id);
      toast("تم إلغاء العرض", "success");
      await loadQuotations();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الإلغاء");
    }
  };

  const handleDelete = async (id: number) => {
    if (!(await confirm({ title: "حذف عرض السعر", message: "هل أنت متأكد من حذف هذا العرض؟" }))) return;
    try {
      await deleteQuotation(id);
      await loadQuotations();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const statusLabel = (s: string) => {
    const map: Record<string, string> = {
      draft: "مسودة",
      sent: "مُرسل",
      accepted: "مقبول",
      rejected: "مرفوض",
      converted: "مُحوَّل",
      cancelled: "ملغى",
      expired: "منتهي الصلاحية",
    };
    return map[s] || s;
  };

  const statusColor = (s: string) => {
    const map: Record<string, string> = {
      draft: "aseel-bg-panel aseel-text-ink",
      sent: "aseel-bg-accent-bg aseel-text-accent",
      accepted: "bg-green-100 text-green-700",
      rejected: "aseel-bg-panel aseel-text-state",
      converted: "aseel-bg-panel aseel-text-ink",
      cancelled: "bg-amber-100 text-amber-700",
      expired: "aseel-bg-panel aseel-text-soft",
    };
    return map[s] || "aseel-bg-panel aseel-text-ink";
  };

  const subtotal = formLines.reduce((s, l) => s + (Number(l.total) || 0), 0);
  const lineDiscountTotal = formLines.reduce((sum, line) => sum + (Number(line.discount) || 0), 0);
  const grossSubtotal = formLines.reduce(
    (sum, line) => sum + (Number(line.quantity) || 0) * (Number(line.unit_price) || 0),
    0,
  );
  const taxTotal = Math.max(0, subtotal - (grossSubtotal - lineDiscountTotal));
  const selectedQuotation = quotations.find((quotation) => quotation.id === selectedId);
  const toolbarActions: CommercialToolbarAction[] = [
    {
      key: "save",
      label: saving ? "جاري الحفظ…" : "تخزين (F12)",
      icon: saving ? <Loader2 className="animate-spin" /> : <Save />,
      onClick: saving ? undefined : () => void handleSave(),
      disabled: saving,
    },
    {
      key: "cancel",
      label: "إلغاء",
      icon: <X />,
      onClick: () => { setShowForm(false); setSelectedId(null); },
      danger: true,
      separatorBefore: true,
    },
    { key: "print", label: "طباعة", icon: <Printer />, onClick: () => window.print() },
  ];
  const headerFields: CommercialHeaderField[] = [
    {
      key: "number",
      label: "رقم العرض",
      control: <input className="aseel-input aseel-input--hl" readOnly
        value={selectedQuotation?.quotation_number || (selectedId ? `#${selectedId}` : "تلقائي")} />,
    },
    {
      key: "date",
      label: "التاريخ",
      control: <input className="aseel-input" type="date" value={formDate}
        onChange={(event) => setFormDate(event.target.value)} />,
    },
    {
      key: "validUntil",
      label: "صالح حتى",
      control: <input className="aseel-input" type="date" value={formValidUntil}
        onChange={(event) => setFormValidUntil(event.target.value)} />,
    },
    {
      key: "type",
      label: "نوع المستند",
      control: <input className="aseel-input" readOnly value="عرض سعر صادر للزبون" />,
    },
    {
      key: "customer",
      label: "الزبون / الحساب",
      control: (
        <select className="aseel-input" value={formCustomer}
          onChange={(event) => setFormCustomer(event.target.value)} data-aseel-key="1">
          <option value="">— اختر الزبون —</option>
          {partners.map((partner) => (
            <option key={partner.id} value={partner.id}>{partner.name}</option>
          ))}
        </select>
      ),
    },
    {
      key: "customerName",
      label: "الاسم",
      control: <input className="aseel-input" readOnly
        value={partners.find((partner) => String(partner.id) === formCustomer)?.name || ""} />,
    },
    {
      key: "address",
      label: "عنوان الزبون",
      control: <input className="aseel-input" value={formCustomerAddress}
        onChange={(event) => setFormCustomerAddress(event.target.value)} />,
    },
    {
      key: "taxNumber",
      label: "الرقم الضريبي",
      control: <input className="aseel-input font-mono" value={formCustomerTaxNumber}
        onChange={(event) => setFormCustomerTaxNumber(event.target.value)} />,
    },
    {
      key: "status",
      label: "الحالة",
      control: <input className="aseel-input" readOnly
        value={selectedQuotation ? statusLabel(selectedQuotation.status) : "مسودة"} />,
    },
  ];
  const editorColumns: CommercialLineColumn<LineState>[] = [
    { key: "seq", header: "مسلسل", width: "52px", align: "center", readOnly: true },
    {
      key: "name",
      header: "بيان الصنف",
      width: "35%",
      render: (line, index) => (
        <button type="button" className="flex w-full items-center justify-between gap-2 px-1 text-right"
          onClick={() => setProductPickerLineIdx(index)}>
          <span className={line.product_name ? "aseel-text-ink" : "aseel-text-soft"}>
            {line.product_name || "اختر صنفاً…"}
          </span>
          <span className="aseel-text-accent">…</span>
        </button>
      ),
    },
    { key: "quantity", header: "الكمية", width: "90px", align: "center", type: "number" },
    { key: "unit_price", header: "سعر الوحدة", width: "110px", align: "center", type: "number" },
    { key: "discount", header: "الخصم", width: "90px", align: "center", type: "number" },
    { key: "tax_rate", header: "الضريبة %", width: "90px", align: "center", type: "number" },
    { key: "total", header: "الإجمالي", width: "110px", align: "center", readOnly: true },
    {
      key: "del",
      header: "",
      width: "36px",
      align: "center",
      render: (_line, index) => (
        <button type="button" className="aseel-iconbtn aseel-iconbtn--danger"
          onClick={() => handleRemoveLine(index)} title="حذف السطر">
          <Trash2 className="h-3 w-3" />
        </button>
      ),
    },
  ];
  const listColumns: CommercialListColumn<SalesQuotationRow>[] = [
    {
      key: "quotation_number",
      header: "رقم العرض",
      width: "130px",
      render: (quotation) => (
        <button type="button" className="aseel-text-accent hover:underline"
          onClick={() => void toggleExpand(quotation.id)}>
          {expandedId === quotation.id ? "▾ " : "▸ "}{quotation.quotation_number}
        </button>
      ),
    },
    { key: "customer", header: "الزبون", render: (quotation) => <>{quotation.customer_name || "—"}</> },
    { key: "date", header: "التاريخ", width: "110px", render: (quotation) => <>{quotation.quotation_date}</> },
    { key: "valid", header: "صالحة حتى", width: "110px", render: (quotation) => <>{quotation.valid_until || "—"}</> },
    { key: "total", header: "الإجمالي", width: "120px", numeric: true,
      render: (quotation) => <>{Number(quotation.grand_total).toLocaleString()}</> },
    {
      key: "status",
      header: "الحالة",
      width: "110px",
      render: (quotation) => (
        <span className={`rounded px-2 py-0.5 text-xs ${statusColor(quotation.status)}`}>
          {statusLabel(quotation.status)}
        </span>
      ),
    },
    {
      key: "actions",
      header: "إجراءات",
      width: "210px",
      render: (quotation) => (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button onClick={() => void openQuotation(quotation.id)} className="aseel-text-accent hover:underline">تعديل</button>
          {quotation.status !== "converted" && quotation.status !== "cancelled" && (
            <>
              <button onClick={() => setConvertId(quotation.id)} className="text-green-600 hover:underline">تحويل</button>
              <button onClick={() => void handleCancel(quotation.id)} className="text-amber-600 hover:underline">إلغاء</button>
            </>
          )}
          {allowDelete && (
            <button onClick={() => void handleDelete(quotation.id)} className="aseel-text-state hover:underline">حذف</button>
          )}
        </div>
      ),
    },
  ];

  if (showForm) {
    return (
      <CommercialDocumentEditor<LineState>
        title="عرض سعر بيع"
        state={selectedQuotation ? `${statusLabel(selectedQuotation.status)} — ${selectedQuotation.quotation_number}` : "مسودة — عرض جديد"}
        nav={nav}
        actions={toolbarActions}
        headerFields={headerFields}
        lines={formLines}
        lineColumns={editorColumns}
        getLineCell={(line, key) => {
          const index = formLines.indexOf(line);
          if (key === "seq") return index + 1;
          if (key === "quantity") return line.quantity;
          if (key === "unit_price") return line.unit_price;
          if (key === "discount") return line.discount;
          if (key === "tax_rate") return line.tax_rate;
          if (key === "total") return Number(line.total).toLocaleString();
          return "";
        }}
        getLineKey={(line, index) => line.id ?? `new-${index}`}
        onLineChange={(index, key, value) => handleLineChange(index, key, value)}
        onAddLine={handleAddLine}
        banner={err ? <div className="aseel-banner aseel-banner--err">{err}</div> : undefined}
        tabs={[
          {
            key: "notes",
            label: "الملاحظات",
            content: <div className="px-1 py-2">
              <textarea className="aseel-input w-full" rows={4} value={formNotes}
                onChange={(event) => setFormNotes(event.target.value)} placeholder="ملاحظات العرض…" />
            </div>,
          },
          {
            key: "settings",
            label: "إعدادات العرض",
            content: <div className="flex flex-wrap gap-4 px-1 py-3">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={formIsActive}
                  onChange={(event) => setFormIsActive(event.target.checked)} />
                العرض فعّال
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={formPricesIncludeTax}
                  onChange={(event) => setFormPricesIncludeTax(event.target.checked)} />
                الأسعار تشمل ض.ق.م
              </label>
              {formValidUntil && new Date(formValidUntil) < new Date() && (
                <span className="text-xs font-semibold aseel-text-state">منتهي الصلاحية</span>
              )}
            </div>,
          },
        ]}
        totals={
          <>
            <div className="aseel-total-row"><span>مجموع البنود</span><span className="aseel-total-value">{grossSubtotal.toLocaleString()}</span></div>
            <div className="aseel-total-row"><span>الخصم</span><span className="aseel-total-value">{lineDiscountTotal.toLocaleString()}</span></div>
            <div className="aseel-total-row"><span>الضريبة</span><span className="aseel-total-value">{taxTotal.toLocaleString()}</span></div>
            <div className="aseel-total-row aseel-total-row--grand"><span>إجمالي العرض</span><span className="aseel-total-value">{subtotal.toLocaleString()}</span></div>
          </>
        }
        status={<>
          <span className="aseel-status-item">عدد الأصناف <b>{formLines.length}</b></span>
          <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
        </>}
        overlay={productPickerLineIdx !== null ? (
          <SalesProductPickerModal
            isOpen
            products={products}
            onSelect={(productId) => {
              const product = products.find((item) => item.id === productId);
              handleLineUpdate(productPickerLineIdx, {
                product_id: String(productId),
                ...(product ? {
                  product_name: formatProductPrimaryName(product),
                  unit_price: quotePriceFor(productId, product.unit_price),
                } : {}),
              });
              setProductPickerLineIdx(null);
            }}
            onClose={() => setProductPickerLineIdx(null)}
          />
        ) : undefined}
      />
    );
  }

  const detailPanel = expandedId != null ? (
    <div className="border-t aseel-border-soft p-3">
      {!expandedLines[expandedId] ? (
        <div className="text-xs aseel-text-soft">جارٍ تحميل البنود…</div>
      ) : expandedLines[expandedId].length === 0 ? (
        <div className="text-xs aseel-text-soft">لا بنود في هذا العرض.</div>
      ) : (
        <table className="aseel-grid text-xs" data-variant="list">
          <thead><tr><th>الصنف</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr></thead>
          <tbody>
            {expandedLines[expandedId].map((line, index) => (
              <tr key={index}>
                <td>{line.name}</td>
                <td>{formatQuantity(line.quantity)}</td>
                <td>{Number(line.unit_price).toLocaleString()}</td>
                <td>{Number(line.line_total).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  ) : undefined;

  return (
    <>
      <CommercialDocumentsList<SalesQuotationRow>
        title="عروض وطلبيات البيع"
        state="عروض الأسعار"
        rows={quotations}
        columns={listColumns}
        getRowKey={(quotation) => quotation.id}
        loading={loading}
        error={err}
        emptyHint="لا توجد عروض"
        countLabel={`${quotations.length} من ${totalQuotations} عرض`}
        onNew={() => { resetForm(); setShowForm(true); }}
        onReload={() => void loadQuotations()}
        newLabel="عرض جديد"
        nav={nav}
        onRowDoubleClick={(quotation) => void openQuotation(quotation.id)}
        pagination={totalQuotations > pageSize ? {
          page,
          pageSize,
          total: totalQuotations,
          onChange: setPage,
        } : undefined}
        detailPanel={detailPanel}
      />
      {convertId != null && (
        <ConvertTargetDialog
          title="تحويل عرض السعر"
          onPick={(target) => void handleConvert(convertId, target)}
          onClose={() => setConvertId(null)}
        />
      )}
    </>
  );
};

export const SalesDocumentsPage: React.FC<{
  initialTab?: "quotations" | "orders";
}> = ({ initialTab = "quotations" }) => {
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => setActiveTab(initialTab), [initialTab]);

  return (
    <div dir="rtl" className="flex h-full min-h-0 flex-col gap-3 p-3">
      <div className="flex w-fit items-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-1">
        <button
          type="button"
          onClick={() => setActiveTab("quotations")}
          className={`rounded-md px-4 py-2 text-sm font-semibold ${
            activeTab === "quotations"
              ? "bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
              : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
          }`}
        >
          عروض الأسعار
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("orders")}
          className={`rounded-md px-4 py-2 text-sm font-semibold ${
            activeTab === "orders"
              ? "bg-[var(--color-primary)] text-[var(--color-primary-foreground)]"
              : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
          }`}
        >
          طلبيات الزبائن
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {activeTab === "quotations" ? <SalesQuotationsPage /> : <SalesOrdersPage />}
      </div>
    </div>
  );
};
