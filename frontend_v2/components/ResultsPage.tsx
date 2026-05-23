/**
 * N7-T6 — ResultsPage (H8) — AseelDenseTable لنتائج تحليل AI
 */
import React, { useState, useMemo, useRef } from 'react';
import { Product } from '../types';
import { ProductPreviewModal } from './modals/ProductPreviewModal';
import { Eye, RefreshCw } from 'lucide-react';
import { AseelDenseTable, type DenseColumn } from './aseel/AseelDenseTable';
import { useAseelIndexKeymap } from './aseel/useAseelIndexKeymap';

interface ResultsPageProps {
    products: Product[];
    onBack: () => void;
    isTaskActive: boolean;
}

export const ResultsPage: React.FC<ResultsPageProps> = ({ products, onBack, isTaskActive }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [maxPrice] = useState(() => products.length === 0 ? 1000 : Math.ceil(Math.max(...products.map(p => p.price))));
    const [price, setPrice] = useState(maxPrice);
    const [sortBy, setSortBy] = useState('similarity');
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    const filteredProducts = useMemo(() => {
        return products
            .filter(p => p.name.toLowerCase().includes(searchTerm.toLowerCase()) && p.price <= price)
            .sort((a, b) => {
                if (sortBy === 'similarity') return b.similarity - a.similarity;
                if (sortBy === 'price_asc') return a.price - b.price;
                return b.price - a.price;
            });
    }, [products, searchTerm, price, sortBy]);

    useAseelIndexKeymap(
        { F6: () => searchInputRef.current?.focus(), Escape: () => { setSearchTerm(''); setPrice(maxPrice); setSortBy('similarity'); } },
        { enabled: !previewUrl },
    );

    const columns: DenseColumn<Product>[] = [
        {
            key: 'similarity',
            header: 'التطابق',
            width: '70px',
            align: 'center',
            sortable: true,
            render: (p) => (
                <span style={{ fontFamily: 'monospace', fontWeight: 700, color: p.similarity >= 0.8 ? 'var(--aseel-ok, #267346)' : p.similarity >= 0.5 ? 'var(--aseel-warn, #b8800a)' : 'var(--aseel-ink-soft)' }}>
                    {Math.round((p.similarity || 0) * 100)}%
                </span>
            ),
        },
        {
            key: 'name',
            header: 'المنتج',
            render: (p) => (
                <span>
                    <b style={{ color: 'var(--aseel-ink)' }}>{p.name}</b>
                    {p.description && <span style={{ marginRight: 6, fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>{p.description.slice(0, 60)}{p.description.length > 60 ? '…' : ''}</span>}
                </span>
            ),
        },
        {
            key: 'price',
            header: 'السعر',
            width: '90px',
            align: 'right',
            numeric: true,
            sortable: true,
            render: (p) => <span style={{ fontFamily: 'monospace' }}>${p.price.toLocaleString()}</span>,
        },
        {
            key: 'actions',
            header: '',
            width: '60px',
            align: 'center',
            render: (p) => (
                p.url ? (
                    <button className="aseel-toolbtn" style={{ padding: '2px 4px' }} onClick={(e) => { e.stopPropagation(); setPreviewUrl(p.url!); }} title="معاينة">
                        <Eye style={{ width: 13, height: 13 }} />
                    </button>
                ) : null
            ),
        },
    ];

    return (
        <>
            <div dir="rtl" data-skin="aseel" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 6, padding: '8px 12px' }}>
                {/* شريط العنوان */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                    <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>نتائج تحليل AI</strong>
                    <span className="aseel-status-item">المطابق: <b>{filteredProducts.length}</b> / {products.length}</span>
                    <div style={{ flex: 1 }} />
                    <input
                        ref={searchInputRef}
                        className="aseel-input"
                        style={{ width: 180 }}
                        placeholder="تصفية النتائج… (F6)"
                        value={searchTerm}
                        onChange={e => setSearchTerm(e.target.value)}
                    />
                    <select className="aseel-input" style={{ width: 150 }} value={sortBy} onChange={e => setSortBy(e.target.value)}>
                        <option value="similarity">الأفضل مطابقة (AI)</option>
                        <option value="price_asc">السعر: من الأقل</option>
                        <option value="price_desc">السعر: من الأعلى</option>
                    </select>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <label style={{ fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink)', whiteSpace: 'nowrap' }}>الحد الأقصى: ${price}</label>
                        <input
                            type="range"
                            min={0}
                            max={maxPrice}
                            value={price}
                            onChange={e => setPrice(Number(e.target.value))}
                            style={{ width: 100 }}
                        />
                    </div>
                    <button className="aseel-toolbtn" onClick={() => { setSearchTerm(''); setPrice(maxPrice); setSortBy('similarity'); }} title="إعادة تعيين">
                        <RefreshCw style={{ width: 14, height: 14 }} />
                    </button>
                    <button className="aseel-toolbtn" style={{ color: 'var(--aseel-accent, #1857a4)', fontWeight: 600 }} onClick={onBack}>
                        {isTaskActive ? 'بحث جديد' : 'إنهاء'}
                    </button>
                </div>

                <AseelDenseTable<Product>
                    columns={columns}
                    rows={filteredProducts}
                    getRowKey={(p) => `${p.name}-${p.price}-${p.similarity}`}
                    onRowDoubleClick={(p) => p.url && setPreviewUrl(p.url)}
                    emptyHint="لا توجد نتائج — جرب توسيع نطاق البحث"
                />
            </div>

            {previewUrl && (
                <ProductPreviewModal
                    isOpen={!!previewUrl}
                    onClose={() => setPreviewUrl(null)}
                    productUrl={previewUrl}
                />
            )}
        </>
    );
};
