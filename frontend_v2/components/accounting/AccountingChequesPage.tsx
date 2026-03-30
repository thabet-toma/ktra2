import React, { useEffect, useState, useCallback } from "react";
import { accountingApi } from "../../services/accountingApi";
import type { ChequeDto, AccountingPartner } from "../../types/accounting";
import { Banknote, Plus, Trash2, X, Save } from "lucide-react";

export const AccountingChequesPage: React.FC = () => {
  const [rows, setRows] = useState<ChequeDto[]>([]);
  const [partners, setPartners] = useState<AccountingPartner[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    cheque_number: "",
    bank_name: "",
    amount: "",
    due_date: "",
    issue_date: new Date().toISOString().split("T")[0],
    payee_name: "",
    direction: "Incoming",
    status: "Draft",
    partner: "",
    currency: "1",
    notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [ch, pr] = await Promise.all([
        accountingApi.getCheques(),
        accountingApi.getPartners().catch(() => []),
      ]);
      setRows(ch as ChequeDto[]);
      setPartners(pr as AccountingPartner[]);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    if (!form.cheque_number.trim()) {
      setErr("رقم الشيك مطلوب");
      return;
    }
    setErr(null);
    try {
      await accountingApi.createCheque({
        cheque_number: form.cheque_number.trim(),
        bank_name: form.bank_name || null,
        amount: form.amount || "0",
        due_date: form.due_date || null,
        issue_date: form.issue_date || null,
        payee_name: form.payee_name || null,
        direction: form.direction,
        status: form.status,
        partner: form.partner ? parseInt(form.partner, 10) : null,
        currency: parseInt(form.currency, 10) || 1,
        notes: form.notes || null,
      });
      setShowForm(false);
      setForm({
        cheque_number: "",
        bank_name: "",
        amount: "",
        due_date: "",
        issue_date: new Date().toISOString().split("T")[0],
        payee_name: "",
        direction: "Incoming",
        status: "Draft",
        partner: "",
        currency: "1",
        notes: "",
      });
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    }
  };

  const remove = async (id: number) => {
    if (!confirm("حذف الشيك؟")) return;
    try {
      await accountingApi.deleteCheque(id);
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-gradient-to-l from-emerald-900 to-slate-900 text-white rounded-xl">
        <div className="flex items-center gap-3">
          <Banknote className="w-8 h-8 text-emerald-300" />
          <div>
            <h1 className="text-lg font-bold">الشيكات</h1>
            <p className="text-xs text-emerald-200">وارد / صادر</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          شيك جديد
        </button>
      </div>

      {err && (
        <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 text-sm">
          {err}
        </div>
      )}

      {loading ? (
        <div className="py-16 text-center text-gray-500">جاري التحميل…</div>
      ) : (
        <div className="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <th className="text-right p-3">رقم</th>
                <th className="text-right p-3">البنك</th>
                <th className="text-right p-3">المبلغ</th>
                <th className="text-right p-3">الاستحقاق</th>
                <th className="text-right p-3">الاتجاه</th>
                <th className="text-right p-3">الحالة</th>
                <th className="text-right p-3 w-16" />
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr
                  key={c.id}
                  className="border-t border-gray-100 dark:border-gray-700"
                >
                  <td className="p-3 font-mono">{c.cheque_number}</td>
                  <td className="p-3">{c.bank_name || "—"}</td>
                  <td className="p-3">{c.amount}</td>
                  <td className="p-3">{c.due_date || "—"}</td>
                  <td className="p-3">{c.direction}</td>
                  <td className="p-3">{c.status}</td>
                  <td className="p-3">
                    <button
                      type="button"
                      onClick={() => remove(c.id)}
                      className="p-1 text-red-600 hover:bg-red-50 rounded"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && (
            <p className="p-8 text-center text-gray-500">لا شيكات</p>
          )}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-lg w-full p-6 border border-gray-200 dark:border-gray-700 max-h-[90vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold">شيك جديد</h3>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="grid grid-cols-1 gap-3 text-sm">
              <input
                placeholder="رقم الشيك *"
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.cheque_number}
                onChange={(e) =>
                  setForm((f) => ({ ...f, cheque_number: e.target.value }))
                }
              />
              <input
                placeholder="البنك"
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.bank_name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, bank_name: e.target.value }))
                }
              />
              <input
                placeholder="المبلغ"
                type="number"
                step="0.01"
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.amount}
                onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="date"
                  className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                  value={form.issue_date}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, issue_date: e.target.value }))
                  }
                />
                <input
                  type="date"
                  className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                  value={form.due_date}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, due_date: e.target.value }))
                  }
                />
              </div>
              <input
                placeholder="اسم المستفيد"
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.payee_name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, payee_name: e.target.value }))
                }
              />
              <select
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.direction}
                onChange={(e) =>
                  setForm((f) => ({ ...f, direction: e.target.value }))
                }
              >
                <option value="Incoming">وارد</option>
                <option value="Outgoing">صادر</option>
              </select>
              <select
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.status}
                onChange={(e) =>
                  setForm((f) => ({ ...f, status: e.target.value }))
                }
              >
                <option value="Draft">مسودة</option>
                <option value="Under_Collection">قيد التحصيل</option>
                <option value="Collected">محصّل</option>
                <option value="Bounced">مرتجع</option>
                <option value="Returned">معاد</option>
              </select>
              <select
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.partner}
                onChange={(e) =>
                  setForm((f) => ({ ...f, partner: e.target.value }))
                }
              >
                <option value="">— شريك (اختياري) —</option>
                {partners.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <textarea
                placeholder="ملاحظات"
                rows={2}
                className="border rounded-lg px-3 py-2 dark:bg-gray-900 dark:border-gray-600"
                value={form.notes}
                onChange={(e) =>
                  setForm((f) => ({ ...f, notes: e.target.value }))
                }
              />
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-4 py-2 rounded-lg border dark:border-gray-600"
              >
                إلغاء
              </button>
              <button
                type="button"
                onClick={submit}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white"
              >
                <Save className="w-4 h-4" />
                حفظ
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
