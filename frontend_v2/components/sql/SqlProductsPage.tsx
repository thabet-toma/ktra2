/**
 * N7-T8 — SqlProductsPage — KitDenseTable للمنتجات
 */
import React, { useEffect, useMemo, useState, useRef } from 'react';
import { apiGetList } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { SqlDataPageShell } from './SqlDataPageShell';
import { Eye, RefreshCw } from 'lucide-react';
import { KitDenseTable, type DenseColumn } from '../kit/KitDenseTable';
import { useKitIndexKeymap } from '../kit/useKitIndexKeymap';

type ProductRow = {
    id: number;
    sku?: string;
    name_ar?: string;
    hs_code?: string | null;
    category?: any;
    is_active?: boolean;
};

export function SqlProductsPage() {
    const [rows, setRows] = useState<ProductRow[]>([]);
    const [err, setErr] = useState<string | null>(null);
    const [q, setQ] = useState('');
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<ProductRow | null>(null);
    const [detailsOpen, setDetailsOpen] = useState(false);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        let mounted = true;
        setLoading(true); setErr(null);
        apiGetList<ProductRow>('inventory/products/', { tenantId: resolveTenantId() })
            .then(d => mounted && setRows(d))
            .catch(e => mounted && setErr(e instanceof Error ? e.message : String(e)))
            .finally(() => mounted && setLoading(false));
        return () => { mounted = false; };
    }, []);

    const filtered = useMemo(() => {
        const s = q.trim().toLowerCase();
        if (!s) return rows;
        return rows.filter(r => `${r.sku || ''} ${r.name_ar || ''} ${r.hs_code || ''}`.toLowerCase().includes(s));
    }, [rows, q]);

    useKitIndexKeymap(
        { F6: () => searchInputRef.current?.focus(), Escape: () => setQ('') },
        { enabled: !detailsOpen },
    );

    const columns: DenseColumn<ProductRow>[] = [
        { key: 'id', header: 'ID', width: '50px', align: 'center', render: r => <span style={{ fontFamily: 'monospace', color: 'var(--ktra-ink-soft)' }}>{r.id}</span> },
        { key: 'sku', header: 'SKU', width: '110px', render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--ktra-fs-sm)' }}>{r.sku || '—'}</span> },
        { key: 'name_ar', header: 'الاسم', render: r => <b>{r.name_ar || '—'}</b> },
        { key: 'hs_code', header: 'HS Code', width: '110px', render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--ktra-fs-sm)' }}>{r.hs_code || '—'}</span> },
        {
            key: 'is_active', header: 'الحالة', width: '70px', align: 'center',
            render: r => <span style={{ fontSize: 'var(--ktra-fs-sm)', color: r.is_active === false ? 'var(--ktra-danger, #c00)' : 'var(--ktra-ok, #267346)', fontWeight: 600 }}>
                {r.is_active === false ? 'غير نشط' : 'نشط'}
            </span>,
        },
        {
            key: 'actions', header: '', width: '60px', align: 'center',
            render: r => (
                <button className="ktra-toolbtn" style={{ padding: '2px 4px' }} onClick={e => { e.stopPropagation(); setSelected(r); setDetailsOpen(true); }} title="عرض التفاصيل">
                    <Eye style={{ width: 13, height: 13 }} />
                </button>
            ),
        },
    ];

    return (
        <>
            <SqlDataPageShell
                title="المنتجات"
                subtitle="بيانات المنتجات من قاعدة البيانات."
                actions={
                    <div style={{ display: 'flex', gap: 6 }}>
                        <input
                            ref={searchInputRef}
                            value={q}
                            onChange={e => setQ(e.target.value)}
                            placeholder="بحث بالاسم/SKU/HS… (F6)"
                            className="ktra-input"
                            style={{ width: 220 }}
                        />
                        <button className="ktra-toolbtn" onClick={() => setQ('')} title="مسح"><RefreshCw style={{ width: 14, height: 14 }} /></button>
                    </div>
                }
            >
                {err && <div style={{ padding: '6px 12px', fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-danger, #c00)', borderBottom: '1px solid var(--ktra-border)' }}>{err}</div>}
                <div style={{ padding: '4px 0' }}>
                    <div style={{ padding: '4px 12px', display: 'flex', gap: 8 }}>
                        <span className="ktra-status-item">الإجمالي: <b>{rows.length}</b></span>
                        <span className="ktra-status-item">فعالة: <b style={{ color: 'var(--ktra-ok, #267346)' }}>{rows.filter(r => r.is_active !== false).length}</b></span>
                        {filtered.length !== rows.length && <span className="ktra-status-item">المفلتر: <b>{filtered.length}</b></span>}
                    </div>
                    <KitDenseTable<ProductRow>
                        columns={columns}
                        rows={filtered}
                        getRowKey={r => r.id}
                        loading={loading}
                        emptyHint="لا يوجد بيانات"
                        onRowDoubleClick={r => { setSelected(r); setDetailsOpen(true); }}
                    />
                </div>
            </SqlDataPageShell>

            {detailsOpen && selected && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 12 }} onClick={() => setDetailsOpen(false)}>
                    <div dir="rtl" style={{ background: 'var(--ktra-surface, #fff)', borderRadius: 8, width: '100%', maxWidth: 520, maxHeight: '90vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
                        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--ktra-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: 'var(--ktra-fs-title, 14px)', color: 'var(--ktra-ink)' }}>تفاصيل المنتج</strong>
                            <button className="ktra-toolbtn" onClick={() => setDetailsOpen(false)}>إغلاق</button>
                        </div>
                        <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 'var(--ktra-fs-sm)' }}>
                            {[['ID', selected.id], ['SKU', selected.sku || '—'], ['الاسم', selected.name_ar || '—'], ['HS Code', selected.hs_code || '—'], ['الحالة', selected.is_active === false ? 'غير نشط' : 'نشط']].map(([k, v]) => (
                                <div key={k as string}><span style={{ color: 'var(--ktra-ink-soft)' }}>{k}:</span> <b>{v as string}</b></div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
