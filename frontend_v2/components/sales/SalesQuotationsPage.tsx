import React, { useState, useEffect, useCallback } from "react";
import { useConfirm } from "../../contexts/ConfirmContext";
import {
  FileText,
  Plus,
  Trash2,
  Save,
  CheckCircle,
  Loader2,
  ChevronRight,
  ChevronLeft,
  ChevronsRight,
  ChevronsLeft,
  Printer,
  FileDown,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { AseelSpinner } from "../aseel/AseelStates";
import {
  listQuotations,
  getQuotation,
  createQuotation,
  updateQuotation,
  deleteQuotation,
  convertQuotationToInvoice,
  type SalesQuotationRow,
  type SalesQuotationDetail,
} from "../../services/salesApi";
import { accountingApi } from "../../services/accountingApi";
import { apiGetList } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { formatQuantity } from "../../utils/formatNumber";
import type { SqlProduct } from "../../types/inventory";
import {
  AseelDocumentShell,
  useRecordNavigation,
  useAseelKeymap,
  AseelAutocomplete,
} from "../aseel";
import { SalesProductPickerModal, type SalesProductPickerItem, formatProductPrimaryName } from "./SalesProductPickerModal";

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
  const [quotations, setQuotations] = useState<SalesQuotationRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

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

  // Aseel Navigation
  const [showPartnerPicker, setShowPartnerPicker] = useState(false);

  const nav = useRecordNavigation<SalesQuotationRow>({
    items: quotations,
    getId: (q) => q.id || 0,
    currentId: selectedId,
    onSelect: async (id) => {
      if (id === null) {
        resetForm();
        setShowForm(true);
      } else {
        try {
          const detail = await getQuotation(Number(id));
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
      }
    },
  });

  // M4-T5: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => window.print(),
    F5: () => loadAll(),
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

  const loadAll = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      // task16 E17: منتقي الصنف في عرض السعر كان يحمّل شجرة الحسابات
      // (getAccounts) بدل الأصناف — يُصحَّح إلى أصناف المخزون (inventory/products).
      const tenantId = resolveTenantId();
      const [qs, parts, prods] = await Promise.all([
        listQuotations(),
        accountingApi.getPartners() as Promise<Partner[]>,
        apiGetList<SqlProduct & { sale_price?: string; selling_price?: string }>(
          "inventory/products/",
          { tenantId }
        ),
      ]);
      setQuotations(qs || []);
      setPartners(parts || []);
      setProducts(
        (prods || []).map((p: any) => ({
          id: p.id,
          sku: p.sku || "",
          barcode: p.barcode,
          quantity_on_hand: String(p.quantity_on_hand || "0"),
          name_ar: p.name_ar || p.name || "",
          name_en: p.name_en || "",
          name: p.name_ar || p.name_en || p.name || p.sku || `#${p.id}`,
          unit_price: p.sale_price ?? p.selling_price ?? p.unit_price ?? "",
        }))
      );
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const resetForm = () => {
    setSelectedId(null);
    setFormCustomer("");
    setFormDate(new Date().toISOString().slice(0, 10));
    setFormValidUntil("");
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
        lines: formLines.map((l) => ({
          product: Number(l.product_id),
          quantity: l.quantity,
          unit_price: l.unit_price,
          line_discount: l.discount,
          tax_rate: Number(l.tax_rate),
        })),
      };
      if (selectedId) {
        await updateQuotation(selectedId, body);
      } else {
        await createQuotation(body);
      }
      resetForm();
      setShowForm(false);
      await loadAll();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const handleConvert = async (id: number) => {
    if (!window.confirm("هل تريد تحويل هذا العرض إلى فاتورة؟")) return;
    try {
      const result = await convertQuotationToInvoice(id);
      alert(`✅ تم التحويل — فاتورة رقم: ${result.invoice_number}`);
      await loadAll();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحويل");
    }
  };

  const handleDelete = async (id: number) => {
    if (!(await confirm({ title: "حذف عرض السعر", message: "هل أنت متأكد من حذف هذا العرض؟" }))) return;
    try {
      await deleteQuotation(id);
      await loadAll();
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
    };
    return map[s] || "aseel-bg-panel aseel-text-ink";
  };

  const productOptions = React.useMemo(
    () => products.map((p) => ({
      id: p.id,
      label: formatProductPrimaryName(p),
    })),
    [products]
  );

  const subtotal = formLines.reduce((s, l) => s + (Number(l.total) || 0), 0);

  return (
    <div
      data-skin="aseel"
      style={{ minHeight: 'calc(100vh - 5rem)', display: 'flex', flexDirection: 'column' }}
    >
    <AseelDocumentShell
      title="العروض والطلبيات"
      state={selectedId ? `عرض #${selectedId}` : 'عروض'}
      nav={nav}
      actions={[
        {
          key: 'new',
          label: 'عرض جديد',
          icon: <Plus />,
          onClick: () => { resetForm(); setShowForm(true); },
        },
        {
          key: 'reload',
          label: 'تحديث',
          icon: <RefreshCw />,
          onClick: () => loadAll(),
          separatorBefore: true,
        },
        {
          key: 'print',
          label: 'طباعة',
          icon: <Printer />,
          onClick: () => window.print(),
        },
      ]}
      header={<></>}
      status={
        <>
          <span className="aseel-status-item">السجل <b>{nav.position}/{nav.total}</b></span>
          <span className="aseel-status-item">{quotations.length} عرض</span>
        </>
      }
    >
    <div className="p-4 space-y-4" style={{ height: '100%', overflow: 'auto', background: '#ffffff' }}>
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">العروض والطلبيات</h2>
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center gap-2 px-4 py-2 aseel-btn-primary"
        >
          <Plus className="w-4 h-4" /> عرض جديد
        </button>
      </div>

      {err && <div className="p-3 aseel-bg-panel aseel-text-state rounded-lg">{err}</div>}

      {loading ? (
        <AseelSpinner />
      ) : (
        <div className="aseel-bg-field rounded-lg shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="aseel-bg-panel">
              <tr>
                <th className="text-right p-3">رقم العرض</th>
                <th className="text-right p-3">العميل</th>
                <th className="text-right p-3">التاريخ</th>
                <th className="text-right p-3">صالحة حتى</th>
                <th className="text-right p-3">الإجمالي</th>
                <th className="text-right p-3">الحالة</th>
                <th className="text-right p-3">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {quotations.length === 0 ? (
                <tr><td colSpan={7} className="p-6 text-center aseel-text-soft">لا توجد عروض</td></tr>
              ) : quotations.map((q) => (
                <tr key={q.id} className="border-t hover:aseel-bg-panel">
                  <td className="p-3 font-mono">{q.quotation_number}</td>
                  <td className="p-3">{q.customer_name || "-"}</td>
                  <td className="p-3">{q.quotation_date}</td>
                  <td className="p-3">{q.valid_until || "-"}</td>
                  <td className="p-3">{Number(q.grand_total).toLocaleString()}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${statusColor(q.status)}`}>
                      {statusLabel(q.status)}
                    </span>
                  </td>
                  <td className="p-3 flex gap-2">
                    <button onClick={() => { setSelectedId(q.id); }} className="aseel-text-accent hover:underline text-xs">تعديل</button>
                    {q.status !== "converted" && (
                      <button onClick={() => handleConvert(q.id)} className="text-green-600 hover:underline text-xs">تحويل</button>
                    )}
                    <button onClick={() => handleDelete(q.id)} className="aseel-text-state hover:underline text-xs">حذف</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="aseel-bg-field rounded-xl shadow-lg w-full max-w-4xl max-h-[90vh] overflow-y-auto p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">{selectedId ? "تعديل العرض" : "عرض جديد"}</h3>
              <button onClick={() => setShowForm(false)} className="p-1 hover:aseel-bg-panel rounded"><FileDown className="w-5 h-5" /></button>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium mb-1">العميل</label>
                <select
                  value={formCustomer}
                  onChange={(e) => setFormCustomer(e.target.value)}
                  className="w-full border rounded-lg p-2"
                  data-aseel-key="1"
                >
                  <option value="">-- اختر --</option>
                  {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">التاريخ</label>
                <input type="date" value={formDate} onChange={(e) => setFormDate(e.target.value)} className="w-full border rounded-lg p-2" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">فعال حتى تاريخ</label>
                <input type="date" value={formValidUntil} onChange={(e) => setFormValidUntil(e.target.value)} className="w-full border rounded-lg p-2" />
              </div>
              {/* N4-T6: فعال + الأسعار تشمل ض.ق.م + الاسم/العنوان/الضريبي */}
              <div className="col-span-2 flex flex-wrap gap-4 items-center aseel-bg-panel border aseel-border-soft rounded p-2">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={formIsActive} onChange={(e) => setFormIsActive(e.target.checked)} />
                  العرض فعّال
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={formPricesIncludeTax} onChange={(e) => setFormPricesIncludeTax(e.target.checked)} />
                  الأسعار تشمل ض.ق.م
                </label>
                {formValidUntil && new Date(formValidUntil) < new Date() && (
                  <span className="text-xs aseel-text-state font-semibold">⚠️ منتهي الصلاحية</span>
                )}
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">عنوان الزبون</label>
                <input type="text" value={formCustomerAddress} onChange={(e) => setFormCustomerAddress(e.target.value)} className="w-full border rounded-lg p-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">مشتغل مرخص (رقم ضريبي)</label>
                <input type="text" value={formCustomerTaxNumber} onChange={(e) => setFormCustomerTaxNumber(e.target.value)} className="w-full border rounded-lg p-2 text-sm font-mono" />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium mb-1">ملاحظات</label>
                <input type="text" value={formNotes} onChange={(e) => setFormNotes(e.target.value)} className="w-full border rounded-lg p-2" />
              </div>
            </div>

            <div className="mb-4">
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-medium">البنود</h4>
                <button onClick={handleAddLine} className="aseel-text-accent text-sm hover:underline">+ إضافة بند</button>
              </div>
              <table className="w-full text-sm border">
                <thead className="aseel-bg-panel">
                  <tr>
                    <th className="text-right p-2" style={{ minWidth: "250px" }}>المنتج</th>
                    <th className="text-right p-2">الكمية</th>
                    <th className="text-right p-2">السعر</th>
                    <th className="text-right p-2">الخصم</th>
                    <th className="text-right p-2">الضريبة %</th>
                    <th className="text-right p-2">الإجمالي</th>
                    <th className="text-right p-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {formLines.map((l, idx) => (
                    <tr key={idx} className="border-t">
                      <td className="p-2">
                        <div style={{ display: "flex", alignItems: "center", gap: 2, minWidth: "250px" }}>
                          <AseelAutocomplete
                            value={(() => {
                              const pr = products.find(p => String(p.id) === String(l.product_id));
                              return pr ? formatProductPrimaryName(pr) : l.product_name;
                            })()}
                            options={productOptions}
                            disabled={false}
                            placeholder="اكتب اسم الصنف…"
                            onPick={(id) => {
                              const prod = products.find(p => String(p.id) === String(id));
                              if (prod) {
                                handleLineUpdate(idx, {
                                  product_id: String(id),
                                  product_name: formatProductPrimaryName(prod),
                                  unit_price: prod.unit_price || "0"
                                });
                              } else {
                                handleLineUpdate(idx, { product_id: String(id) });
                              }
                            }}
                          />
                          <button
                            type="button"
                            className="px-2 border rounded aseel-bg-field hover:aseel-bg-panel text-sm"
                            onClick={() => setProductPickerLineIdx(idx)}
                            title="فهرس الأصناف الكامل (+)"
                          >…</button>
                        </div>
                      </td>
                      <td className="p-2"><input type="number" value={l.quantity} onChange={(e) => handleLineChange(idx, "quantity", e.target.value)} className="w-full border rounded p-1 text-sm" /></td>
                      <td className="p-2"><input type="number" value={l.unit_price} onChange={(e) => handleLineChange(idx, "unit_price", e.target.value)} className="w-full border rounded p-1 text-sm" /></td>
                      <td className="p-2"><input type="number" value={l.discount} onChange={(e) => handleLineChange(idx, "discount", e.target.value)} className="w-full border rounded p-1 text-sm" /></td>
                      <td className="p-2"><input type="number" value={l.tax_rate} onChange={(e) => handleLineChange(idx, "tax_rate", e.target.value)} className="w-full border rounded p-1 text-sm" /></td>
                      <td className="p-2 font-mono">{Number(l.total).toLocaleString()}</td>
                      <td className="p-2"><button onClick={() => handleRemoveLine(idx)} className="aseel-text-soft hover:aseel-text-state"><Trash2 className="w-4 h-4" /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="text-left mt-2 font-bold">الإجمالي: {subtotal.toLocaleString()}</div>
            </div>

            <div className="flex justify-end gap-3">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 aseel-bg-panel rounded-lg hover:aseel-bg-grid-head">إلغاء</button>
              <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 aseel-btn-primary disabled:opacity-50">
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {saving ? "جاري الحفظ..." : "حفظ"}
              </button>
            </div>
            
            {productPickerLineIdx !== null && (
              <SalesProductPickerModal
                isOpen={true}
                products={products}
                onSelect={(productId) => {
                  const prod = products.find(p => p.id === productId);
                  handleLineChange(productPickerLineIdx, "product_id", String(productId));
                  if (prod) {
                    handleLineChange(productPickerLineIdx, "product_name", formatProductPrimaryName(prod));
                    handleLineChange(productPickerLineIdx, "unit_price", prod.unit_price || "0");
                  }
                  setProductPickerLineIdx(null);
                }}
                onClose={() => setProductPickerLineIdx(null)}
              />
            )}
            
          </div>
        </div>
      )}
    </div>
    </AseelDocumentShell>
    </div>
  );
};
