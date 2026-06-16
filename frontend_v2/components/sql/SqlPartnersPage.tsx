/**
 * N7-T8 — SqlPartnersPage — AseelDenseTable للشركاء/الموردين
/**
 * N7-T8 — SqlPartnersPage — AseelDenseTable للشركاء/الموردين
 */
import React, { useEffect, useMemo, useState, useRef } from 'react';
import { apiGetList } from '../../services/restApi';
import { resolveTenantId } from '../../utils/tenantContext';
import { SqlDataPageShell } from './SqlDataPageShell';
import { Eye, RefreshCw } from 'lucide-react';
import { AseelDenseTable, type DenseColumn } from '../aseel/AseelDenseTable';
import { useAseelIndexKeymap } from '../aseel/useAseelIndexKeymap';
import { useNavigate } from 'react-router-dom';

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
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        let mounted = true;
        setLoading(true); setErr(null);
        apiGetList<PartnerRow>('partners/', { tenantId: resolveTenantId() })
            .then(d => mounted && setRows(d))
            .catch(e => mounted && setErr(e instanceof Error ? e.message : String(e)))
            .finally(() => mounted && setLoading(false));
        return () => { mounted = false; };
    }, []);

    const filtered = useMemo(() => {
        const s = q.trim().toLowerCase();
        return rows.filter(r => {
            if (typeFilter !== 'all' && (r.partner_type || '') !== typeFilter) return false;
            if (!s) return true;
            return `${r.name} ${r.partner_type || ''} ${r.phone || ''} ${r.email || ''}`.toLowerCase().includes(s);
        });
    }, [rows, q, typeFilter]);

    const partnerTypes = useMemo(() => Array.from(new Set(rows.map(x => x.partner_type).filter(Boolean) as string[])), [rows]);

    useAseelIndexKeymap(
        { F6: () => searchInputRef.current?.focus(), Escape: () => { setQ(''); setTypeFilter('all'); } }
    );

    const columns: DenseColumn<PartnerRow>[] = [
        { key: 'id', header: 'ID', width: '50px', align: 'center', render: r => <span style={{ fontFamily: 'monospace', color: 'var(--aseel-ink-soft)' }}>{r.id}</span> },
        { key: 'name', header: 'الاسم', width: '200px', render: r => <b>{r.name}</b> },
        { key: 'partner_type', header: 'النوع', width: '120px', render: r => <>{r.partner_type || '—'}</> },
        { key: 'phone', header: 'الهاتف', width: '120px', render: r => <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>{r.phone || '—'}</span> },
        { key: 'email', header: 'البريد', render: r => <span style={{ fontSize: 'var(--aseel-fs-sm)' }}>{r.email || '—'}</span> },
        {
            key: 'actions', header: '', width: '60px', align: 'center',
            render: r => (
                <button className="aseel-toolbtn" style={{ padding: '2px 4px' }} onClick={e => { e.stopPropagation(); navigate(`/partners/${r.id}`); }} title="فتح ملف العميل/المورد">
                    <Eye style={{ width: 13, height: 13 }} />
                </button>
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
                        <input
                            ref={searchInputRef}
                            value={q}
                            onChange={e => setQ(e.target.value)}
                            placeholder="بحث بالاسم/النوع/الهاتف… (F6)"
                            className="aseel-input"
                            style={{ width: 220 }}
                        />
                        <select className="aseel-input" style={{ width: 130 }} value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
                            <option value="all">كل الأنواع</option>
                            {partnerTypes.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                        <button className="aseel-toolbtn" onClick={() => { setQ(''); setTypeFilter('all'); }} title="إعادة تعيين"><RefreshCw style={{ width: 14, height: 14 }} /></button>
                    </div>
                }
            >
                {err && <div style={{ padding: '6px 12px', fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-danger, #c00)', borderBottom: '1px solid var(--aseel-border)' }}>{err}</div>}
                <div style={{ padding: '4px 0' }}>
                    <div style={{ padding: '4px 12px', display: 'flex', gap: 8 }}>
                        <span className="aseel-status-item">الإجمالي: <b>{rows.length}</b></span>
                        {filtered.length !== rows.length && <span className="aseel-status-item">المفلتر: <b>{filtered.length}</b></span>}
                    </div>
                    <AseelDenseTable<PartnerRow>
                        columns={columns}
                        rows={filtered}
                        getRowKey={r => r.id}
                        loading={loading}
                        emptyHint="لا يوجد بيانات"
                        onRowDoubleClick={r => navigate(`/partners/${r.id}`)}
                    />
                </div>
            </SqlDataPageShell>
        </>
    );
}
