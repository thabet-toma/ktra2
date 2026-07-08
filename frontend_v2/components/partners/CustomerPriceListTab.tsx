/**
 * DEF-004 — تبويب «عرض السعر» في بطاقة العميل (مبيعات فقط).
 * يسرد كامل الكتالوج:
 *   - المنتجات التي اشتراها العميل → سعر آخر فاتورة (للقراءة فقط، نظامي) + شارة «آخر فاتورة».
 *   - المنتجات التي لم يشترها → حقل سعر قابل للتحرير يُحفظ كعرض سعر للعميل + شارة «عرض السعر / يدوي».
 * لا أثر محاسبي — مصدر تسعير احتياطي فقط.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Save, Search } from 'lucide-react';
import { getCustomerPriceList, saveCustomerQuotes, type CustomerPriceRow } from '../../services/salesApi';
import { formatMoney } from '../../utils/formatNumber';

interface Props {
  customerId: number | string;
}

export const CustomerPriceListTab: React.FC<Props> = ({ customerId }) => {
  const [rows, setRows] = useState<CustomerPriceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  // التعديلات اليدوية المعلّقة: product_id → القيمة المكتوبة.
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    getCustomerPriceList(customerId)
      .then((d) => { setRows(Array.isArray(d) ? d : []); setEdits({}); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [customerId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => (r.name || '').toLowerCase().includes(q) || (r.sku || '').toLowerCase().includes(q));
  }, [rows, query]);

  const onSave = () => {
    const entries = Object.entries(edits)
      .map(([pid, v]) => ({ product: Number(pid), unit_price: String(v).trim() }))
      .filter((e) => e.unit_price !== '');
    setSaving(true);
    setSavedMsg(null);
    saveCustomerQuotes(customerId, entries)
      .then(() => { setSavedMsg('حُفظت عروض الأسعار بنجاح'); load(); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setSaving(false));
  };

  const hasEdits = Object.values(edits).some((v) => String(v).trim() !== '');

  return (
    <div className="p-2" data-skin="aseel">
      <div className="flex items-center gap-2 mb-2">
        <div className="relative flex-1 max-w-xs">
          <input
            className="aseel-input w-full"
            style={{ paddingInlineStart: 26 }}
            placeholder="بحث عن منتج…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Search className="w-4 h-4 text-gray-400 absolute" style={{ insetInlineStart: 6, top: 7 }} />
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={saving || !hasEdits}
          title="حفظ عروض الأسعار"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-default transition-colors"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} حفظ
        </button>
        {savedMsg && <span role="status" className="text-xs" style={{ color: 'var(--aseel-ok,#2e7d32)' }}>{savedMsg}</span>}
      </div>

      {error && <div role="alert" className="m-1 p-2 text-sm text-[var(--aseel-danger,#c00)]">{error}</div>}

      {loading ? (
        <div className="p-4 text-center text-[var(--aseel-ink-soft)] flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> جاري التحميل…
        </div>
      ) : (
        <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
          <table className="aseel-grid" data-variant="items">
            <thead>
              <tr>
                <th>المنتج</th>
                <th style={{ width: '140px' }}>السعر</th>
                <th style={{ width: '150px' }}>المصدر</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={3} style={{ textAlign: 'center', padding: 14, color: 'var(--aseel-ink-soft)' }}>لا منتجات</td></tr>
              ) : filtered.map((r) => (
                <tr key={r.product_id}>
                  <td>{r.name}</td>
                  <td className="aseel-num">
                    {r.editable ? (
                      <input
                        className="aseel-input"
                        type="number"
                        min={0}
                        step={0.01}
                        placeholder="—"
                        value={edits[r.product_id] ?? (r.price ?? '')}
                        onChange={(e) => setEdits((prev) => ({ ...prev, [r.product_id]: e.target.value }))}
                      />
                    ) : (
                      <span>{formatMoney(r.price)}</span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`aseel-price-badge ${r.source === 'last_invoice' ? 'aseel-price-badge--last' : 'aseel-price-badge--quote'}`}
                      title={r.invoice_number ? `فاتورة ${r.invoice_number}` : undefined}
                    >{r.source_label}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default CustomerPriceListTab;
