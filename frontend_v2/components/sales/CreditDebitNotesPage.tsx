import React, { useState, useEffect, useCallback } from "react";
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
} from "lucide-react";
import { apiGetList, apiPostObject, apiPatchObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { accountingApi } from "../../services/accountingApi";
import {
  AseelDocumentShell,
  useRecordNavigation,
  useAseelKeymap,
} from "../aseel";
import { RefreshCw } from "lucide-react";

const tid = () => resolveTenantId();
const BASE = "sales/credit-debit-notes";

type NoteRow = {
  id: number;
  note_number: string;
  note_date: string;
  note_type: "credit" | "debit";
  customer: number;
  customer_name?: string;
  related_invoice?: number | null;
  related_invoice_number?: string | null;
  amount: string;
  reason?: string;
  status: string;
  journal?: number | null;
};

type Partner = { id: number; name: string };

export const CreditDebitNotesPage: React.FC = () => {
  const [notes, setNotes] = useState<NoteRow[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [formType, setFormType] = useState<"credit" | "debit">("credit");
  const [formCustomer, setFormCustomer] = useState("");
  const [formDate, setFormDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [formAmount, setFormAmount] = useState("");
  const [formReason, setFormReason] = useState("");
  // N4-T5: حقول إضافية per spec
  const [formIncludesTax, setFormIncludesTax] = useState(false);
  const [formTaxRate, setFormTaxRate] = useState("17");
  const [formRelatedInvoice, setFormRelatedInvoice] = useState("");
  const [formVatStatementNo, setFormVatStatementNo] = useState("");
  const [activeTab, setActiveTab] = useState<"main" | "notes" | "accounts">("main");

  // N4-T5: حساب المبلغ بدون ضريبة / مبلغ الضريبة / الإجمالي
  const amt = Number(formAmount) || 0;
  const taxPct = Number(formTaxRate) || 0;
  const { amountExcl, taxAmount, totalAmount } = (() => {
    if (formIncludesTax) {
      // formAmount includes tax → extract
      const excl = amt / (1 + taxPct / 100);
      return { amountExcl: excl, taxAmount: amt - excl, totalAmount: amt };
    } else {
      // formAmount excludes tax → add
      const tax = amt * (taxPct / 100);
      return { amountExcl: amt, taxAmount: tax, totalAmount: amt + tax };
    }
  })();

  const nav = useRecordNavigation<NoteRow>({
    items: notes,
    getId: (n) => n.id || 0,
    currentId: selectedId,
    onSelect: async (id) => {
      if (id === null) {
        resetForm();
        setShowForm(true);
      } else {
        const found = notes.find(n => n.id === id);
        if (found) {
          setSelectedId(found.id);
          setFormType(found.note_type);
          setFormCustomer(String(found.customer));
          setFormDate(found.note_date?.slice(0, 10) || "");
          setFormAmount(found.amount);
          setFormReason(found.reason || "");
          setShowForm(true);
        }
      }
    },
  });

  // M4-T4: Aseel keyboard shortcuts — real handlers.
  useAseelKeymap({
    F2: () => window.print(),
    F5: () => loadAll(),
    F6: () => {
      const el = document.querySelector<HTMLInputElement>('[data-aseel-field="search"]');
      el?.focus();
    },
    F12: () => handleSave(),
    Escape: () => {
      setShowForm(false);
      setSelectedId(null);
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
      const [ns, parts] = await Promise.all([
        apiGetList<NoteRow>(BASE, { tenantId: tid() }),
        accountingApi.getPartners() as Promise<Partner[]>,
      ]);
      setNotes(ns || []);
      setPartners(parts || []);
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
    setFormType("credit");
    setFormCustomer("");
    setFormDate(new Date().toISOString().slice(0, 10));
    setFormAmount("");
    setFormReason("");
  };

  const handleSave = async () => {
    if (!formCustomer || !formAmount) {
      setErr("يرجى ملء جميع الحقول المطلوبة");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const body = {
        note_type: formType,
        customer: Number(formCustomer),
        note_date: formDate,
        amount: String(totalAmount.toFixed(2)),
        amount_excl_tax: String(amountExcl.toFixed(2)),
        tax_amount: String(taxAmount.toFixed(2)),
        tax_rate: String(taxPct),
        includes_tax: formIncludesTax,
        related_invoice: formRelatedInvoice ? Number(formRelatedInvoice) : null,
        vat_statement_no: formVatStatementNo || null,
        reason: formReason,
      };
      if (selectedId) {
        await apiPatchObject(`${BASE}/${selectedId}/`, body, { tenantId: tid() });
      } else {
        await apiPostObject(BASE, body, { tenantId: tid() });
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

  const handlePost = async (id: number) => {
    if (!window.confirm("هل تريد ترحيل هذا الإشعار؟")) return;
    try {
      await apiPostObject(`${BASE}/${id}/post/`, {}, { tenantId: tid() });
      await loadAll();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الترحيل");
    }
  };

  const statusLabel = (s: string) => {
    const map: Record<string, string> = { draft: "مسودة", posted: "مرحّل", cancelled: "ملغي" };
    return map[s] || s;
  };

  const statusColor = (s: string) => {
    const map: Record<string, string> = {
      draft: "bg-gray-100 text-gray-700",
      posted: "bg-green-100 text-green-700",
      cancelled: "bg-red-100 text-red-700",
    };
    return map[s] || "bg-gray-100 text-gray-700";
  };

  return (
    <div
      data-skin="aseel"
      style={{ height: 'calc(100vh - 5rem)', display: 'flex', flexDirection: 'column' }}
    >
    <AseelDocumentShell
      title="الإشعارات المدينة/الدائنة"
      state={selectedId ? `إشعار #${selectedId}` : 'إشعارات'}
      nav={nav}
      actions={[
        {
          key: 'new',
          label: 'إشعار جديد',
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
          <span className="aseel-status-item">{notes.length} إشعار</span>
        </>
      }
    >
    <div className="p-4 space-y-4" style={{ height: '100%', overflow: 'auto', background: '#ffffff' }}>
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">الإشعارات المدينة/الدائنة</h2>
        <button
          onClick={() => { resetForm(); setShowForm(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="w-4 h-4" /> إشعار جديد
        </button>
      </div>

      {err && <div className="p-3 bg-red-50 text-red-700 rounded-lg">{err}</div>}

      {loading ? (
        <div className="flex items-center gap-2 text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> جاري التحميل...</div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-right p-3">رقم الإشعار</th>
                <th className="text-right p-3">النوع</th>
                <th className="text-right p-3">العميل</th>
                <th className="text-right p-3">التاريخ</th>
                <th className="text-right p-3">المبلغ</th>
                <th className="text-right p-3">الحالة</th>
                <th className="text-right p-3">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {notes.length === 0 ? (
                <tr><td colSpan={7} className="p-6 text-center text-gray-400">لا توجد إشعارات</td></tr>
              ) : notes.map((n) => (
                <tr key={n.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 font-mono">{n.note_number}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${n.note_type === "credit" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {n.note_type === "credit" ? "دائن" : "مدين"}
                    </span>
                  </td>
                  <td className="p-3">{n.customer_name || "-"}</td>
                  <td className="p-3">{n.note_date}</td>
                  <td className="p-3">{Number(n.amount).toLocaleString()}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${statusColor(n.status)}`}>
                      {statusLabel(n.status)}
                    </span>
                  </td>
                  <td className="p-3 flex gap-2">
                    {n.status === "draft" && (
                      <>
                        <button onClick={() => { setSelectedId(n.id); }} className="text-blue-600 hover:underline text-xs">تعديل</button>
                        <button onClick={() => handlePost(n.id)} className="text-green-600 hover:underline text-xs">ترحيل</button>
                      </>
                    )}
                    {n.journal && <span className="text-gray-400 text-xs">قيد #{n.journal}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-lg w-full max-w-lg p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">{selectedId ? "تعديل الإشعار" : "إشعار جديد"}</h3>
              <button onClick={() => setShowForm(false)} className="p-1 hover:bg-gray-100 rounded"><FileDown className="w-5 h-5" /></button>
            </div>

            {/* N4-T5 tabs */}
            <div className="flex gap-1 border-b border-gray-200 mb-3">
              {[
                { k: "main", l: "الرئيسية" },
                { k: "notes", l: "الملاحظات" },
                { k: "accounts", l: "الحسابات" },
              ].map((t) => (
                <button key={t.k} type="button"
                  onClick={() => setActiveTab(t.k as "main" | "notes" | "accounts")}
                  className={`px-3 py-1.5 text-xs font-medium border-b-2 ${activeTab === t.k ? "border-blue-600 text-blue-700" : "border-transparent text-gray-500"}`}>
                  {t.l}
                </button>
              ))}
            </div>

            {activeTab === "main" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium mb-1">النوع</label>
                  <select value={formType} onChange={(e) => setFormType(e.target.value as "credit" | "debit")} className="w-full border rounded p-1.5 text-sm" data-aseel-key="1">
                    <option value="credit">إشعار دائن</option>
                    <option value="debit">إشعار مدين</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">التاريخ</label>
                  <input type="date" value={formDate} onChange={(e) => setFormDate(e.target.value)} className="w-full border rounded p-1.5 text-sm" />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs font-medium mb-1">الحساب (العميل/المورد)</label>
                  <select value={formCustomer} onChange={(e) => setFormCustomer(e.target.value)} className="w-full border rounded p-1.5 text-sm" data-aseel-key="1">
                    <option value="">-- اختر (+) --</option>
                    {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">رقم فاتورة المقاصة</label>
                  <input type="text" value={formRelatedInvoice} onChange={(e) => setFormRelatedInvoice(e.target.value)} className="w-full border rounded p-1.5 text-sm font-mono" placeholder="رقم الفاتورة المرتبطة" />
                </div>
                <div>
                  <label className="block text-xs font-medium mb-1">كشف الضريبة</label>
                  <input type="text" value={formVatStatementNo} onChange={(e) => setFormVatStatementNo(e.target.value)} className="w-full border rounded p-1.5 text-sm" placeholder="رقم كشف الضريبة" />
                </div>

                {/* المبلغ + ضريبة */}
                <div className="col-span-2 bg-amber-50 border border-amber-200 rounded p-2 mt-2">
                  <label className="flex items-center gap-2 text-xs mb-2">
                    <input type="checkbox" checked={formIncludesTax} onChange={(e) => setFormIncludesTax(e.target.checked)} />
                    المبلغ يشمل قيمة الضريبة المضافة
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] mb-0.5">المبلغ (Space=رصيد)</label>
                      <input
                        type="number" step="0.01"
                        data-aseel-field="remaining-amount"
                        value={formAmount}
                        onChange={(e) => setFormAmount(e.target.value)}
                        className="w-full border rounded p-1 text-sm font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] mb-0.5">نسبة ض.ق.م %</label>
                      <input type="number" step="0.01" value={formTaxRate} onChange={(e) => setFormTaxRate(e.target.value)} className="w-full border rounded p-1 text-sm font-mono" />
                    </div>
                    <div>
                      <label className="block text-[11px] mb-0.5">المبلغ بدون ضريبة</label>
                      <input type="text" readOnly value={amountExcl.toFixed(2)} className="w-full border rounded p-1 text-sm font-mono bg-gray-100" />
                    </div>
                    <div>
                      <label className="block text-[11px] mb-0.5">مبلغ الضريبة</label>
                      <input type="text" readOnly value={taxAmount.toFixed(2)} className="w-full border rounded p-1 text-sm font-mono bg-gray-100" />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-[11px] mb-0.5">مبلغ الإشعار الإجمالي</label>
                      <input type="text" readOnly value={totalAmount.toFixed(2)} className="w-full border rounded p-1 text-sm font-mono font-bold bg-emerald-50" />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === "notes" && (
              <div>
                <label className="block text-xs font-medium mb-1">السبب / الملاحظات</label>
                <textarea value={formReason} onChange={(e) => setFormReason(e.target.value)} className="w-full border rounded p-2" rows={6} />
              </div>
            )}

            {activeTab === "accounts" && (
              <div className="text-xs text-gray-600 p-3 bg-gray-50 rounded">
                معاينة القيد المحاسبي: {formType === "credit" ? "Dr إيراد مرتجعات / Cr ذمم" : "Dr ذمم / Cr إيراد إضافي"} —
                المبلغ: {totalAmount.toFixed(2)} (ضمنه ض.ق.م {taxAmount.toFixed(2)}).
              </div>
            )}

            <div className="flex justify-end gap-3 mt-4">
              <button onClick={() => setShowForm(false)} className="px-4 py-2 bg-gray-100 rounded-lg hover:bg-gray-200">إلغاء</button>
              <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {saving ? "جاري الحفظ..." : "حفظ"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </AseelDocumentShell>
    </div>
  );
};
