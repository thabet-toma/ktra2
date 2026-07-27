/**
 * N7-T8 — SqlShipmentsPage — AseelDenseTable للشحنات (SQL)
 */
import React, { useEffect, useMemo, useState, useRef } from 'react';
import { apiGetList, apiGetObject } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { SqlDataPageShell } from './SqlDataPageShell';
import { Eye, RefreshCw } from 'lucide-react';
import { buildShipmentOptionLabel, ShipmentLabelInput } from '@/utils/shipmentLabel';
import { AseelDenseTable, type DenseColumn } from '../aseel/AseelDenseTable';
import { useAseelIndexKeymap } from '../aseel/useAseelIndexKeymap';
import { formatDateLocalized } from "../../utils/formatDate";

type ShipmentRow = ShipmentLabelInput & {
    status?: string;
    departure_date?: string | null;
    arrival_date?: string | null;
    shipping_agent?: any;
    bill_of_lading?: string | null;
    container_number?: string | null;
};

export function SqlShipmentsPage() {
    const [rows, setRows] = useState<ShipmentRow[]>([]);
    const [err, setErr] = useState<string | null>(null);
    const [q, setQ] = useState('');
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<ShipmentRow | null>(null);
    const [detailsOpen, setDetailsOpen] = useState(false);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        let mounted = true;
        setLoading(true); setErr(null);
        apiGetList<ShipmentRow>('logistics/shipments/', { tenantId: resolveTenantId() })
            .then(d => mounted && setRows(d))
            .catch(e => mounted && setErr(e instanceof Error ? e.message : String(e)))
            .finally(() => mounted && setLoading(false));
        return () => { mounted = false; };
    }, []);

    const filtered = useMemo(() => {
        const s = q.trim().toLowerCase();
        if (!s) return rows;
        return rows.filter(r => `${buildShipmentOptionLabel(r)} ${r.status || ''} ${r.shipping_agent?.name || ''} ${r.bill_of_lading || ''} ${r.container_number || ''}`.toLowerCase().includes(s));
    }, [rows, q]);

    const openShipment = async (row: ShipmentRow) => {
        setSelected(row); setDetailsOpen(true); setLoadingDetail(true);
        try { setSelected(await apiGetObject<ShipmentRow>(`logistics/shipments/${row.id}/`, { tenantId: resolveTenantId() })); }
        catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
        finally { setLoadingDetail(false); }
    };

    useAseelIndexKeymap(
        { F6: () => searchInputRef.current?.focus(), Escape: () => setQ('') },
        { enabled: !detailsOpen },
    );

    const columns: DenseColumn<ShipmentRow>[] = [
        {
            key: 'label', header: 'رقم الشحنة', width: '180px',
            render: r => {
                const isAir = (r.status || '').toLowerCase().includes('air');
                return <span><span style={{ marginLeft: 4 }}>{isAir ? '✈' : '🚢'}</span><b style={{ fontFamily: 'monospace' }}>{buildShipmentOptionLabel(r)}</b></span>;
            },
        },
        { key: 'agent', header: 'وكيل الشحن', width: '140px', render: r => <>{r.shipping_agent?.name || '—'}</> },
        {
            key: 'status', header: 'الحالة', width: '100px',
            render: r => <span style={{ fontSize: 'var(--aseel-fs-sm)', fontWeight: 500 }}>{r.status || '—'}</span>,
        },
        { key: 'departure_date', header: 'المغادرة', width: '90px', render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{formatDateLocalized(r.departure_date) || '—'}</span> },
        { key: 'arrival_date', header: 'الوصول', width: '90px', render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{formatDateLocalized(r.arrival_date) || '—'}</span> },
        {
            key: 'actions', header: '', width: '60px', align: 'center',
            render: r => (
                <button className="aseel-toolbtn" style={{ padding: '2px 4px' }} onClick={e => { e.stopPropagation(); void openShipment(r); }} title="عرض التفاصيل">
                    <Eye style={{ width: 13, height: 13 }} />
                </button>
            ),
        },
    ];

    return (
        <>
            <SqlDataPageShell
                title="إدارة الشحنات"
                subtitle="نفس أسلوب العرض الاحترافي مع تفاصيل عند الضغط."
                actions={
                    <div style={{ display: 'flex', gap: 6 }}>
                        <input
                            ref={searchInputRef}
                            value={q}
                            onChange={e => setQ(e.target.value)}
                            placeholder="بحث برقم/وكيل/حالة… (F6)"
                            className="aseel-input"
                            style={{ width: 220 }}
                        />
                        <button className="aseel-toolbtn" onClick={() => setQ('')} title="مسح"><RefreshCw style={{ width: 14, height: 14 }} /></button>
                    </div>
                }
            >
                {err && <div style={{ padding: '6px 12px', fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-danger, #c00)', borderBottom: '1px solid var(--aseel-border)' }}>{err}</div>}
                <div style={{ padding: '4px 0' }}>
                    <div style={{ padding: '4px 12px', display: 'flex', gap: 8 }}>
                        <span className="aseel-status-item">الإجمالي: <b>{rows.length}</b></span>
                        {filtered.length !== rows.length && <span className="aseel-status-item">المفلتر: <b>{filtered.length}</b></span>}
                    </div>
                    <AseelDenseTable<ShipmentRow>
                        columns={columns}
                        rows={filtered}
                        getRowKey={r => r.id}
                        loading={loading}
                        emptyHint="لا يوجد بيانات"
                        onRowDoubleClick={r => void openShipment(r)}
                    />
                </div>
            </SqlDataPageShell>

            {detailsOpen && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50, padding: 12 }} onClick={() => setDetailsOpen(false)}>
                    <div dir="rtl" style={{ background: 'var(--aseel-surface, #fff)', borderRadius: 8, width: '100%', maxWidth: 640, maxHeight: '90vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
                        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--aseel-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>تفاصيل الشحنة</strong>
                            <button className="aseel-toolbtn" onClick={() => setDetailsOpen(false)}>إغلاق</button>
                        </div>
                        <div style={{ padding: 14, fontSize: 'var(--aseel-fs-sm)' }}>
                            {loadingDetail ? (
                                <div style={{ color: 'var(--aseel-ink-soft)' }}>جار تحميل التفاصيل...</div>
                            ) : !selected ? (
                                <div style={{ color: 'var(--aseel-ink-soft)' }}>تعذر تحميل التفاصيل.</div>
                            ) : (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                    {[['رقم الشحنة', selected.shipment_number || '—'], ['الحالة', selected.status || '—'], ['وكيل الشحن', selected.shipping_agent?.name || '—'], ['Departure', selected.departure_date || '—'], ['Arrival', selected.arrival_date || '—'], ['B/L', selected.bill_of_lading || '—'], ['Container', selected.container_number || '—']].map(([k, v]) => (
                                        <div key={k as string}><span style={{ color: 'var(--aseel-ink-soft)' }}>{k}:</span> <b>{v as string}</b></div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
