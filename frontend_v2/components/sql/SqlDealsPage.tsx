/**
 * N7-T8 — SqlDealsPage — AseelDenseTable للصفقات (SQL)
 */
import React, { useEffect, useMemo, useState, useRef } from 'react';
import { apiGetList, apiGetObject, apiPostObject } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { SqlDataPageShell } from './SqlDataPageShell';
import { Eye, RefreshCw, Plus } from 'lucide-react';
import { AseelDenseTable, type DenseColumn } from '../aseel/AseelDenseTable';
import { useAseelIndexKeymap } from '../aseel/useAseelIndexKeymap';

type DealRow = {
    id: number;
    ref_number?: string;
    order_date?: string;
    total_amount?: string | number;
    status?: string;
    partner?: any;
    partner_name?: string;
    description?: string | null;
    payment_status?: string;
    items?: Array<{ id: number; product_name?: string; quantity?: string | number; unit_price?: string | number; total_price?: string | number; notes?: string | null }>;
    payments?: Array<{ id: number; title?: string; amount?: string | number; status?: string; due_date?: string | null; transfer_date?: string | null }>;
};
type PartnerOption = { id: number; name?: string; partner_type?: string };

const statusLabel = (s?: string) => {
    const v = (s || '').toLowerCase();
    if (v.includes('open')) return 'نشطة';
    if (v.includes('close')) return 'مغلقة';
    if (v.includes('cancel')) return 'ملغاة';
    if (v.includes('ship')) return 'قيد الشحن';
    if (v.includes('complete')) return 'مكتملة';
    return s || '—';
};

const paymentStatusLabel = (s?: string) => {
    const v = (s || '').toLowerCase();
    if (v.includes('fully')) return 'مدفوعة كلياً';
    if (v.includes('part')) return 'مدفوعة جزئياً';
    if (v.includes('unpaid')) return 'غير مدفوعة';
    if (v.includes('paid')) return 'مدفوعة';
    if (v.includes('confirm')) return 'بانتظار التأكيد';
    return s || '—';
};

const statusColor = (s?: string) => {
    const v = (s || '').toLowerCase();
    if (v.includes('open')) return 'var(--aseel-warn, #b8800a)';
    if (v.includes('close') || v.includes('complete')) return 'var(--aseel-ok, #267346)';
    if (v.includes('cancel')) return 'var(--aseel-danger, #c00)';
    if (v.includes('ship')) return 'var(--aseel-accent, #1857a4)';
    return 'inherit';
};

const fmtDate = (d?: string | null) => (d ? formatDateValue(d) : '—');
import { formatMoney } from "@/utils/formatNumber";
import { formatDateValue } from "../../utils/formatDate";
const fmtMoney = (v: any) => formatMoney(v, String(v ?? '—'));

export function SqlDealsPage() {
    const [rows, setRows] = useState<DealRow[]>([]);
    const [partners, setPartners] = useState<PartnerOption[]>([]);
    const [err, setErr] = useState<string | null>(null);
    const [q, setQ] = useState('');
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<DealRow | null>(null);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [detailsOpen, setDetailsOpen] = useState(false);
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [createOpen, setCreateOpen] = useState(false);
    const [savingCreate, setSavingCreate] = useState(false);
    const [createForm, setCreateForm] = useState({ ref_number: '', partner: '', order_date: new Date().toISOString().slice(0, 10), status: 'Open', description: '' });
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        let mounted = true;
        setLoading(true); setErr(null);
        apiGetList<DealRow>('logistics/deals/', { tenantId: resolveTenantId() })
            .then(d => mounted && setRows(d))
            .catch(e => mounted && setErr(e instanceof Error ? e.message : String(e)))
            .finally(() => mounted && setLoading(false));
        return () => { mounted = false; };
    }, []);

    useEffect(() => {
        // T-PARTYPURE: طرف الصفقة مورد — القائمة كانت تعرض العملاء أيضاً.
        apiGetList<PartnerOption>('partners/lookup/?limit=500&partner_type=Supplier', { tenantId: resolveTenantId() }).then(setPartners).catch(() => setPartners([]));
    }, []);

    const filtered = useMemo(() => {
        const s = q.trim().toLowerCase();
        return rows.filter(r => {
            if (statusFilter !== 'all' && (r.status || '') !== statusFilter) return false;
            if (!s) return true;
            const pn = r.partner?.name || r.partner_name || '';
            return `${r.ref_number || ''} ${pn} ${r.status || ''} ${r.payment_status || ''} ${r.description || ''}`.toLowerCase().includes(s);
        });
    }, [rows, q, statusFilter]);

    const stats = useMemo(() => ({
        total: rows.length,
        totalAmount: rows.reduce((s, r) => s + Number(r.total_amount || 0), 0),
        active: rows.filter(r => !['closed', 'cancelled'].some(x => (r.status || '').toLowerCase().includes(x))).length,
    }), [rows]);

    const statuses = useMemo(() => Array.from(new Set(rows.map(r => r.status).filter(Boolean) as string[])), [rows]);

    const openDeal = async (row: DealRow) => {
        setSelected(row); setDetailsOpen(true); setLoadingDetail(true);
        try { setSelected(await apiGetObject<DealRow>(`logistics/deals/${row.id}/`, { tenantId: resolveTenantId() })); }
        catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
        finally { setLoadingDetail(false); }
    };

    const refreshDeals = async () => {
        setLoading(true);
        try { setRows(await apiGetList<DealRow>('logistics/deals/', { tenantId: resolveTenantId() })); }
        catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
        finally { setLoading(false); }
    };

    const handleCreateDeal = async () => {
        if (!createForm.ref_number.trim()) { setErr('رقم الصفقة مطلوب.'); return; }
        if (!createForm.partner) { setErr('اختر المورد أولاً.'); return; }
        setSavingCreate(true); setErr(null);
        try {
            await apiPostObject('logistics/deals/', { ref_number: createForm.ref_number.trim(), partner: Number(createForm.partner), order_date: createForm.order_date, status: createForm.status, description: createForm.description || null, currency: 1, items: [], payments: [] }, { tenantId: resolveTenantId() });
            setCreateOpen(false);
            setCreateForm({ ref_number: '', partner: '', order_date: new Date().toISOString().slice(0, 10), status: 'Open', description: '' });
            await refreshDeals();
        } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
        finally { setSavingCreate(false); }
    };

    useAseelIndexKeymap(
        { CtrlIns: () => setCreateOpen(true), F6: () => searchInputRef.current?.focus(), Escape: () => { setQ(''); setStatusFilter('all'); } },
        { enabled: !detailsOpen && !createOpen },
    );

    const columns: DenseColumn<DealRow>[] = [
        {
            key: 'ref_number', header: 'رقم الصفقة', width: '120px',
            render: r => <b style={{ fontFamily: 'monospace' }}>{r.ref_number || '—'}</b>,
        },
        {
            key: 'partner', header: 'المورد', width: '160px',
            render: r => <>{r.partner?.name || r.partner_name || '—'}</>,
        },
        {
            key: 'status', header: 'الحالة', width: '100px',
            render: r => <span style={{ color: statusColor(r.status), fontWeight: 500, fontSize: 'var(--aseel-fs-sm)' }}>{statusLabel(r.status)}</span>,
        },
        {
            key: 'payment_status', header: 'الدفع', width: '120px',
            render: r => <span style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>{paymentStatusLabel(r.payment_status)}</span>,
        },
        {
            key: 'order_date', header: 'التاريخ', width: '90px',
            render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{fmtDate(r.order_date)}</span>,
        },
        {
            key: 'total_amount', header: 'الإجمالي', width: '110px', align: 'right', numeric: true,
            render: r => <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{fmtMoney(r.total_amount)}</span>,
        },
        {
            key: 'actions', header: '', width: '60px', align: 'center',
            render: r => (
                <button className="aseel-toolbtn" style={{ padding: '2px 4px' }} onClick={e => { e.stopPropagation(); void openDeal(r); }} title="إدارة كاملة">
                    <Eye style={{ width: 13, height: 13 }} />
                </button>
            ),
        },
    ];

    return (
        <>
            <SqlDataPageShell
                title="إدارة الصفقات"
                subtitle="اضغط على أي صفقة لرؤية التفاصيل الكاملة."
                actions={
                    <div style={{ display: 'flex', gap: 6 }}>
                        <button className="aseel-toolbtn" style={{ padding: '4px 10px', color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }} onClick={() => setCreateOpen(true)} title="صفقة جديدة (Ctrl+Ins)">
                            <Plus style={{ width: 14, height: 14, display: 'inline', marginLeft: 4 }} />صفقة جديدة
                        </button>
                        <input ref={searchInputRef} value={q} onChange={e => setQ(e.target.value)} placeholder="بحث برقم/مورد/حالة… (F6)" className="aseel-input" style={{ width: 220 }} />
                        <select className="aseel-input" style={{ width: 130 }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
                            <option value="all">كل الحالات</option>
                            {statuses.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <button className="aseel-toolbtn" onClick={() => { setQ(''); setStatusFilter('all'); }} title="إعادة تعيين"><RefreshCw style={{ width: 14, height: 14 }} /></button>
                    </div>
                }
            >
                {err && <div style={{ padding: '6px 12px', fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-danger, #c00)', borderBottom: '1px solid var(--aseel-border)' }}>{err}</div>}
                <div style={{ padding: '4px 12px 4px', display: 'flex', gap: 8 }}>
                    <span className="aseel-status-item">الإجمالي: <b>{stats.total}</b></span>
                    <span className="aseel-status-item">نشطة: <b style={{ color: 'var(--aseel-warn, #b8800a)' }}>{stats.active}</b></span>
                    <span className="aseel-status-item">القيمة الكلية: <b style={{ fontFamily: 'monospace' }}>{stats.totalAmount.toLocaleString()}</b></span>
                    {filtered.length !== rows.length && <span className="aseel-status-item">المفلتر: <b>{filtered.length}</b></span>}
                </div>
                <AseelDenseTable<DealRow>
                    columns={columns}
                    rows={filtered}
                    getRowKey={r => r.id}
                    loading={loading}
                    emptyHint="لا يوجد بيانات"
                    onRowDoubleClick={r => void openDeal(r)}
                    footer={
                        filtered.length > 0 ? (
                            <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                                إجمالي: <b>{fmtMoney(filtered.reduce((s, r) => s + Number(r.total_amount || 0), 0))}</b>
                            </span>
                        ) : undefined
                    }
                />
            </SqlDataPageShell>

            {/* مودال التفاصيل الكاملة */}
            {detailsOpen && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 12 }} onClick={() => setDetailsOpen(false)}>
                    <div dir="rtl" style={{ background: '#f3f4f6', borderRadius: 12, width: '100%', maxWidth: '92vw', maxHeight: '92vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
                        <div style={{ position: 'sticky', top: 0, background: '#fff', borderBottom: '1px solid #e5e7eb', padding: '10px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 10 }}>
                            <strong style={{ fontSize: 14 }}>تفاصيل الصفقة</strong>
                            <button onClick={() => setDetailsOpen(false)} style={{ padding: '3px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, cursor: 'pointer' }}>إغلاق</button>
                        </div>
                        <div style={{ padding: 16 }}>
                            {loadingDetail ? (
                                <div style={{ color: '#6b7280', fontSize: 13 }}>جار تحميل تفاصيل الصفقة...</div>
                            ) : !selected ? (
                                <div style={{ color: '#6b7280', fontSize: 13 }}>تعذر تحميل التفاصيل.</div>
                            ) : (() => {
                                const paidTotal = (selected.payments || []).reduce((s, p) => s + Number(p.amount || 0), 0);
                                const total = Number(selected.total_amount || 0);
                                const remaining = Math.max(0, total - paidTotal);
                                return (
                                    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #1f2937', paddingBottom: 12 }}>
                                            <strong style={{ fontSize: 15 }}>تقرير صفقة شامل</strong>
                                            <div style={{ textAlign: 'left', fontSize: 12 }}>
                                                <div><span style={{ color: '#6b7280' }}>REF: </span><b>{selected.ref_number || '—'}</b></div>
                                                <div><span style={{ color: '#6b7280' }}>DATE: </span><b>{fmtDate(selected.order_date)}</b></div>
                                            </div>
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, fontSize: 12 }}>
                                            {[['الحالة', statusLabel(selected.status)], ['التاريخ', fmtDate(selected.order_date)], ['المورد', selected.partner_name || selected.partner?.name || '—'], ['الإجمالي', fmtMoney(selected.total_amount)]].map(([k, v]) => (
                                                <div key={k} style={{ border: '1px solid #e5e7eb', borderRadius: 6, padding: '8px 10px', background: '#f9fafb' }}>
                                                    <div style={{ color: '#9ca3af', fontSize: 10, marginBottom: 4 }}>{k}</div>
                                                    <b>{v}</b>
                                                </div>
                                            ))}
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                                            <div style={{ border: '1px solid #d1d5db', borderRadius: 8, overflow: 'hidden' }}>
                                                <div style={{ background: '#f3f4f6', padding: '6px 12px', borderBottom: '1px solid #d1d5db', fontWeight: 700, fontSize: 12 }}>بنود المنتجات</div>
                                                <div style={{ overflowX: 'auto' }}>
                                                    <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }} dir="rtl">
                                                        <thead style={{ background: '#1f2937', color: '#fff' }}>
                                                            <tr>{['الصنف', 'الكمية', 'سعر الوحدة', 'الإجمالي', 'ملاحظات'].map(h => <th key={h} style={{ padding: '6px 10px', textAlign: 'right', borderBottom: '1px solid #374151' }}>{h}</th>)}</tr>
                                                        </thead>
                                                        <tbody>
                                                            {(selected.items || []).length === 0 ? <tr><td colSpan={5} style={{ padding: '10px', color: '#9ca3af' }}>لا توجد بنود.</td></tr> :
                                                                (selected.items || []).map(it => (
                                                                    <tr key={it.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                                                                        <td style={{ padding: '6px 10px' }}>{it.product_name || '—'}</td>
                                                                        <td style={{ padding: '6px 10px' }}>{String(it.quantity ?? '—')}</td>
                                                                        <td style={{ padding: '6px 10px' }}>{fmtMoney(it.unit_price)}</td>
                                                                        <td style={{ padding: '6px 10px', fontWeight: 700 }}>{fmtMoney(it.total_price)}</td>
                                                                        <td style={{ padding: '6px 10px', color: '#6b7280' }}>{it.notes || '—'}</td>
                                                                    </tr>
                                                                ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                            <div style={{ border: '1px solid #d1d5db', borderRadius: 8, overflow: 'hidden', height: 'fit-content' }}>
                                                <div style={{ background: '#1f2937', color: '#fff', padding: '6px 12px', textAlign: 'center', fontWeight: 700, fontSize: 12 }}>الملخص المالي</div>
                                                <div style={{ padding: '10px 12px', fontSize: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
                                                    {[['إجمالي المدفوعات', fmtMoney(paidTotal), '#059669'], ['الإجمالي', fmtMoney(total), '#1f2937'], ['المتبقي', fmtMoney(remaining), '#dc2626']].map(([k, v, c]) => (
                                                        <div key={k} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #f3f4f6', paddingBottom: 6 }}>
                                                            <span style={{ color: '#6b7280' }}>{k}:</span>
                                                            <b style={{ fontFamily: 'monospace', color: c }}>{v}</b>
                                                        </div>
                                                    ))}
                                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}><span style={{ color: '#6b7280' }}>الدفع:</span><b>{paymentStatusLabel(selected.payment_status)}</b></div>
                                                </div>
                                            </div>
                                        </div>
                                        <div style={{ border: '1px solid #d1d5db', borderRadius: 8, overflow: 'hidden' }}>
                                            <div style={{ background: '#f3f4f6', padding: '6px 12px', borderBottom: '1px solid #d1d5db', fontWeight: 700, fontSize: 12, display: 'flex', justifyContent: 'space-between' }}>
                                                <span>الدفعات</span>
                                                <span style={{ fontSize: 11, background: '#fff', padding: '1px 6px', borderRadius: 4, border: '1px solid #e5e7eb' }}>{(selected.payments || []).length} دفعة</span>
                                            </div>
                                            <div style={{ overflowX: 'auto' }}>
                                                <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }} dir="rtl">
                                                    <thead style={{ background: '#f9fafb' }}>
                                                        <tr>{['العنوان', 'المبلغ', 'الحالة', 'الاستحقاق', 'تاريخ التحويل'].map(h => <th key={h} style={{ padding: '6px 10px', textAlign: 'right', borderBottom: '1px solid #e5e7eb', color: '#374151' }}>{h}</th>)}</tr>
                                                    </thead>
                                                    <tbody>
                                                        {(selected.payments || []).length === 0 ? <tr><td colSpan={5} style={{ padding: '10px', color: '#9ca3af' }}>لا توجد دفعات.</td></tr> :
                                                            (selected.payments || []).map(p => (
                                                                <tr key={p.id} style={{ borderBottom: '1px solid #f9fafb' }}>
                                                                    <td style={{ padding: '6px 10px' }}>{p.title || '—'}</td>
                                                                    <td style={{ padding: '6px 10px', fontWeight: 700, fontFamily: 'monospace' }}>{fmtMoney(p.amount)}</td>
                                                                    <td style={{ padding: '6px 10px' }}>{paymentStatusLabel(p.status)}</td>
                                                                    <td style={{ padding: '6px 10px', fontFamily: 'monospace' }}>{fmtDate(p.due_date)}</td>
                                                                    <td style={{ padding: '6px 10px', fontFamily: 'monospace' }}>{fmtDate(p.transfer_date)}</td>
                                                                </tr>
                                                            ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })()}
                        </div>
                    </div>
                </div>
            )}

            {/* مودال إضافة صفقة */}
            {createOpen && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 12 }} onClick={() => setCreateOpen(false)}>
                    <div dir="rtl" style={{ background: 'var(--aseel-surface, #fff)', borderRadius: 8, width: '100%', maxWidth: 480 }} onClick={e => e.stopPropagation()}>
                        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--aseel-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>إضافة صفقة جديدة</strong>
                            <button className="aseel-toolbtn" onClick={() => setCreateOpen(false)}>إغلاق</button>
                        </div>
                        <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                            {[['رقم الصفقة', 'text', 'ref_number', 'D-0104'], ['التاريخ', 'date', 'order_date', '']].map(([label, type, key, placeholder]) => (
                                <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                    <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>{label}</label>
                                    <input type={type} className="aseel-input" placeholder={placeholder} value={(createForm as any)[key]} onChange={e => setCreateForm(p => ({ ...p, [key]: e.target.value }))} />
                                </div>
                            ))}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>المورد</label>
                                <select className="aseel-input" value={createForm.partner} onChange={e => setCreateForm(p => ({ ...p, partner: e.target.value }))}>
                                    <option value="">اختر المورد</option>
                                    {partners.map(p => <option key={p.id} value={p.id}>{p.name || `#${p.id}`}</option>)}
                                </select>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>الحالة</label>
                                <select className="aseel-input" value={createForm.status} onChange={e => setCreateForm(p => ({ ...p, status: e.target.value }))}>
                                    <option value="Open">Open</option>
                                    <option value="Shipped">Shipped</option>
                                    <option value="Closed">Closed</option>
                                    <option value="Cancelled">Cancelled</option>
                                </select>
                            </div>
                            <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)' }}>الوصف</label>
                                <textarea className="aseel-input" rows={3} style={{ resize: 'vertical' }} placeholder="وصف مختصر للصفقة" value={createForm.description} onChange={e => setCreateForm(p => ({ ...p, description: e.target.value }))} />
                            </div>
                        </div>
                        <div style={{ padding: '10px 14px', borderTop: '1px solid var(--aseel-border)', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                            <button className="aseel-toolbtn" onClick={() => setCreateOpen(false)}>إلغاء</button>
                            <button className="aseel-toolbtn" style={{ color: 'var(--aseel-accent, #1857a4)', fontWeight: 700 }} onClick={handleCreateDeal} disabled={savingCreate}>
                                {savingCreate ? 'جارٍ الحفظ...' : 'حفظ الصفقة'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
