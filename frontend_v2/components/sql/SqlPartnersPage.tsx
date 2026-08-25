/**
 * N7-T8 — SqlPartnersPage — KitDenseTable للشركاء/الموردين
 */
import React, { useEffect, useState, useRef } from 'react';
import { apiGetPagedList } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { SqlDataPageShell } from './SqlDataPageShell';
import { Eye, Pencil, Plus, RefreshCw } from 'lucide-react';
import { KitDenseTable, type DenseColumn } from '../kit/KitDenseTable';
import { useKitIndexKeymap } from '../kit/useKitIndexKeymap';
import { useNavigate } from 'react-router-dom';
import { PartnerEditorModal, type PartnerType } from '../partners/PartnerEditorModal';

type PartnerRow = {
    id: number;
    name: string;
    partner_type?: string;
    phone?: string | null;
    email?: string | null;
    linked_account?: any;
};

export function SqlPartnersPage() {
    const navigate = useNavigate();
    const [rows, setRows] = useState<PartnerRow[]>([]);
    const [err, setErr] = useState<string | null>(null);
    const [q, setQ] = useState('');
    const [loading, setLoading] = useState(true);
    const [typeFilter, setTypeFilter] = useState<string>('all');
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [reloadToken, setReloadToken] = useState(0);
    const [editorOpen, setEditorOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const pageSize = 50;
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        let mounted = true;
        setLoading(true); setErr(null);
        const timer = window.setTimeout(() => {
        apiGetPagedList<PartnerRow>('partners/', {
            tenantId: resolveTenantId(),
            query: {
                page,
                page_size: pageSize,
                search: q.trim() || undefined,
                partner_type: typeFilter === 'all' ? undefined : typeFilter,
            },
        })
            .then(d => { if (mounted) { setRows(d.results); setTotal(d.count); } })
            .catch(e => mounted && setErr(e instanceof Error ? e.message : String(e)))
            .finally(() => mounted && setLoading(false));
        }, 250);
        return () => { mounted = false; window.clearTimeout(timer); };
    }, [page, q, reloadToken, typeFilter]);

    const partnerTypes = ['Customer', 'Supplier', 'FreightForwarder', 'CustomsBroker', 'LocalTransporter'];

    useKitIndexKeymap(
        {
            F6: () => searchInputRef.current?.focus(),
            CtrlIns: () => { setEditingId(null); setEditorOpen(true); },
            Escape: () => { setQ(''); setTypeFilter('all'); },
        }
    );

    const columns: DenseColumn<PartnerRow>[] = [
        { key: 'id', header: 'ID', width: '50px', align: 'center', render: r => <span style={{ fontFamily: 'monospace', color: 'var(--ktra-ink-soft)' }}>{r.id}</span> },
        { key: 'name', header: 'الاسم', width: '200px', render: r => <b>{r.name}</b> },
        { key: 'partner_type', header: 'النوع', width: '120px', render: r => <>{r.partner_type || '—'}</> },
        { key: 'phone', header: 'الهاتف', width: '120px', render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--ktra-fs-sm)' }}>{r.phone || '—'}</span> },
        { key: 'email', header: 'البريد', render: r => <span style={{ fontSize: 'var(--ktra-fs-sm)' }}>{r.email || '—'}</span> },
        {
            key: 'actions', header: '', width: '95px', align: 'center',
            render: r => (
                <div className="flex justify-center gap-1">
                    <button className="ktra-toolbtn" style={{ padding: '2px 4px' }} onClick={e => { e.stopPropagation(); setEditingId(r.id); setEditorOpen(true); }} title="تعديل بطاقة الطرف">
                        <Pencil style={{ width: 13, height: 13 }} />
                    </button>
                    <button className="ktra-toolbtn" style={{ padding: '2px 4px' }} onClick={e => { e.stopPropagation(); navigate(`/partners/${r.id}`); }} title="فتح ملف الطرف">
                        <Eye style={{ width: 13, height: 13 }} />
                    </button>
                </div>
            ),
        },
    ];

    return (
        <>
            <SqlDataPageShell
                title="الموردين والشركاء"
                subtitle="بيانات الموردين والشركاء من قاعدة البيانات."
                actions={
                    <div style={{ display: 'flex', gap: 6 }}>
                        <button className="ktra-toolbtn" onClick={() => { setEditingId(null); setEditorOpen(true); }} title="إضافة طرف جديد (Ctrl+Ins)">
                            <Plus style={{ width: 14, height: 14 }} /> طرف جديد
                        </button>
                        <input
                            ref={searchInputRef}
                            value={q}
                            onChange={e => { setQ(e.target.value); setPage(1); }}
                            placeholder="بحث بالاسم/النوع/الهاتف… (F6)"
                            className="ktra-input"
                            style={{ width: 220 }}
                        />
                        <select className="ktra-input" style={{ width: 130 }} value={typeFilter} onChange={e => { setTypeFilter(e.target.value); setPage(1); }}>
                            <option value="all">كل الأنواع</option>
                            {partnerTypes.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                        <button className="ktra-toolbtn" onClick={() => { setQ(''); setTypeFilter('all'); }} title="إعادة تعيين"><RefreshCw style={{ width: 14, height: 14 }} /></button>
                    </div>
                }
            >
                {err && <div style={{ padding: '6px 12px', fontSize: 'var(--ktra-fs-sm)', color: 'var(--ktra-danger, #c00)', borderBottom: '1px solid var(--ktra-border)' }}>{err}</div>}
                <div style={{ padding: '4px 0' }}>
                    <div style={{ padding: '4px 12px', display: 'flex', gap: 8 }}>
                        <span className="ktra-status-item">الإجمالي: <b>{total}</b></span>
                    </div>
                    <KitDenseTable<PartnerRow>
                        columns={columns}
                        rows={rows}
                        getRowKey={r => r.id}
                        loading={loading}
                        emptyHint="لا يوجد بيانات"
                        onRowDoubleClick={r => navigate(`/partners/${r.id}`)}
                        pagination={{ page, pageSize, total, onChange: setPage }}
                    />
                </div>
            </SqlDataPageShell>
            <PartnerEditorModal
                open={editorOpen}
                partnerId={editingId}
                initialType={typeFilter === 'all' ? 'Customer' : typeFilter as PartnerType}
                onClose={() => setEditorOpen(false)}
                onSaved={() => {
                    setEditorOpen(false);
                    setReloadToken((value) => value + 1);
                }}
            />
        </>
    );
}
