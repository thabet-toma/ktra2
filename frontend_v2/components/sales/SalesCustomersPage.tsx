import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiDelete, apiGetList, apiPatchObject, apiPostObject } from "../../services/restApi";
import { resolveTenantId } from "../../utils/tenantContext";
import { Loader2, Plus, Pencil, Trash2, RefreshCw, Users, Search } from "lucide-react";

type PartnerApi = {
  id: number;
  name: string;
  legal_name?: string | null;
  partner_type: string;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  country?: string | null;
  street_address?: string | null;
  state_or_province?: string | null;
  postal_code?: string | null;
  tax_number?: string | null;
  credit_limit?: string | null;
  currency?: number | null;
};

type CurrRow = { CurrencyID: number; Code: string; Name?: string | null };

const emptyForm = () => ({
  name: "",
  legal_name: "",
  phone: "",
  email: "",
  tax_number: "",
  street_address: "",
  city: "",
  state_or_province: "",
  postal_code: "",
  country: "",
  credit_limit: "",
  currency: "" as number | "",
});

export const SalesCustomersPage: React.FC = () => {
  const [rows, setRows] = useState<PartnerApi[]>([]);
  const [currencies, setCurrencies] = useState<CurrRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const tenantId = useMemo(() => resolveTenantId(), []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [all, cur] = await Promise.all([
        apiGetList<PartnerApi>("partners/", { tenantId }),
        apiGetList<CurrRow>("accounting/currencies/", { tenantId }),
      ]);
      setRows(all.filter((p) => p.partner_type === "Customer"));
      setCurrencies(cur);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل التحميل");
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => {
      const blob = [r.name, r.phone, r.email, r.city, r.tax_number]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }, [rows, search]);

  const openNew = () => {
    setEditingId(null);
    setForm(emptyForm());
    setModalOpen(true);
    setErr(null);
    setMsg(null);
  };

  const openEdit = (p: PartnerApi) => {
    setEditingId(p.id);
    setForm({
      name: p.name || "",
      legal_name: p.legal_name || "",
      phone: p.phone || "",
      email: p.email || "",
      tax_number: p.tax_number || "",
      street_address: p.street_address || "",
      city: p.city || "",
      state_or_province: p.state_or_province || "",
      postal_code: p.postal_code || "",
      country: p.country || "",
      credit_limit: p.credit_limit != null ? String(p.credit_limit) : "",
      currency: p.currency ?? "",
    });
    setModalOpen(true);
    setErr(null);
    setMsg(null);
  };

  const buildPayload = (): Record<string, unknown> => {
    const credit =
      form.credit_limit.trim() === "" ? null : Number(form.credit_limit);
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      partner_type: "Customer",
      legal_name: form.legal_name.trim() || null,
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
      tax_number: form.tax_number.trim() || null,
      street_address: form.street_address.trim() || null,
      city: form.city.trim() || null,
      state_or_province: form.state_or_province.trim() || null,
      postal_code: form.postal_code.trim() || null,
      country: form.country.trim() || null,
      credit_limit: credit != null && !Number.isNaN(credit) ? String(credit) : null,
      currency: form.currency === "" ? null : form.currency,
    };
    return payload;
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      setErr("اسم العميل مطلوب.");
      return;
    }
    setSaving(true);
    setErr(null);
    setMsg(null);
    try {
      const body = buildPayload();
      if (editingId) {
        await apiPatchObject(`partners/${editingId}/`, body, { tenantId });
        setMsg("تم تحديث بيانات العميل.");
      } else {
        await apiPostObject("partners/", body, { tenantId });
        setMsg("تم إضافة العميل.");
      }
      setModalOpen(false);
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحفظ");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (p: PartnerApi) => {
    if (!window.confirm(`حذف العميل «${p.name}»؟`)) return;
    setErr(null);
    setMsg(null);
    try {
      await apiDelete(`partners/${p.id}/`, { tenantId });
      setMsg("تم الحذف.");
      await load();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "فشل الحذف");
    }
  };

  const fmtMoney = (s: string | null | undefined) =>
    s != null && s !== ""
      ? Number(s).toLocaleString("en-US", { minimumFractionDigits: 2 })
      : "—";

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6" dir="rtl">
      <div className="flex flex-wrap items-center gap-3">
        <Users className="h-8 w-8 text-emerald-600" />
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">عملاء المبيعات</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm">
            إدارة العملاء (ذمم المبيعات) — نفس جدول الشركاء مع نوع «عميل»
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          تحديث
        </button>
        <button
          type="button"
          onClick={openNew}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 text-white hover:bg-emerald-700"
        >
          <Plus className="h-4 w-4" />
          عميل جديد
        </button>
      </div>

      {err && (
        <div className="p-4 rounded-lg bg-red-50 text-red-800 dark:bg-red-900/30 dark:text-red-200">{err}</div>
      )}
      {msg && (
        <div className="p-4 rounded-lg bg-emerald-50 text-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-200">
          {msg}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="بحث بالاسم، الهاتف، البريد، المدينة، الرقم الضريبي..."
            className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 pr-10"
          />
        </div>
      </div>

      <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden bg-white dark:bg-gray-900">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="text-right p-3">الاسم</th>
                <th className="text-right p-3">الهاتف</th>
                <th className="text-right p-3">البريد</th>
                <th className="text-right p-3">المدينة</th>
                <th className="text-right p-3">حد الائتمان</th>
                <th className="text-right p-3 w-48">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr
                  key={r.id}
                  className="border-t border-gray-100 dark:border-gray-800 hover:bg-gray-50/80 dark:hover:bg-gray-800/50"
                >
                  <td className="p-3 font-medium text-gray-900 dark:text-white">{r.name}</td>
                  <td className="p-3 font-mono text-xs">{r.phone || "—"}</td>
                  <td className="p-3 text-xs">{r.email || "—"}</td>
                  <td className="p-3">{r.city || "—"}</td>
                  <td className="p-3 font-mono">{fmtMoney(r.credit_limit)}</td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-2 justify-end">
                      <button
                        type="button"
                        onClick={() => openEdit(r)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-300 dark:border-gray-600 text-xs"
                      >
                        <Pencil className="h-3 w-3" />
                        تعديل
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(r)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded border border-red-300 text-red-700 dark:border-red-700 dark:text-red-300 text-xs"
                      >
                        <Trash2 className="h-3 w-3" />
                        حذف
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!filtered.length && !loading && (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-gray-500">
                    {rows.length ? "لا نتائج للبحث" : "لا يوجد عملاء بعد — أضف عميلاً جديداً"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
          <div
            className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-gray-900 shadow-xl border border-gray-200 dark:border-gray-700 p-6 space-y-4"
            dir="rtl"
          >
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              {editingId ? "تعديل عميل" : "عميل جديد"}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-sm md:col-span-2">
                <span>الاسم *</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm md:col-span-2">
                <span>الاسم القانوني</span>
                <input
                  value={form.legal_name}
                  onChange={(e) => setForm((f) => ({ ...f, legal_name: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>الهاتف</span>
                <input
                  value={form.phone}
                  onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>البريد</span>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm md:col-span-2">
                <span>الرقم الضريبي</span>
                <input
                  value={form.tax_number}
                  onChange={(e) => setForm((f) => ({ ...f, tax_number: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm md:col-span-2">
                <span>العنوان</span>
                <input
                  value={form.street_address}
                  onChange={(e) => setForm((f) => ({ ...f, street_address: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>المدينة</span>
                <input
                  value={form.city}
                  onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>المنطقة / الولاية</span>
                <input
                  value={form.state_or_province}
                  onChange={(e) => setForm((f) => ({ ...f, state_or_province: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>الرمز البريدي</span>
                <input
                  value={form.postal_code}
                  onChange={(e) => setForm((f) => ({ ...f, postal_code: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>الدولة</span>
                <input
                  value={form.country}
                  onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))}
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>حد الائتمان</span>
                <input
                  value={form.credit_limit}
                  onChange={(e) => setForm((f) => ({ ...f, credit_limit: e.target.value }))}
                  placeholder="0"
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2 font-mono"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span>عملة العميل (اختياري)</span>
                <select
                  value={form.currency === "" ? "" : String(form.currency)}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      currency: e.target.value ? Number(e.target.value) : "",
                    }))
                  }
                  className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 px-3 py-2"
                >
                  <option value="">—</option>
                  {currencies.map((c) => (
                    <option key={c.CurrencyID} value={c.CurrencyID}>
                      {c.Code} {c.Name ? `— ${c.Name}` : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex flex-wrap gap-2 justify-end pt-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600"
              >
                إلغاء
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={handleSave}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                حفظ
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
