/**
 * N6-T2 — ShipmentManagement (L2) — AseelDenseTable لإدارة الشحنات
 * المرجع: task5.md:796 + الإرساليات.txt:6-155
 */
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shipment, User } from '../../../types';
import { shipmentsService } from '../../../services/shipmentsService';
import { Plus, Eye, Edit, Trash2, RefreshCw } from 'lucide-react';
import { LoadingSpinner } from '../../LoadingSpinner';
import { ShipmentDetailView } from './ShipmentDetailView';
import { AseelDenseTable, type DenseColumn } from '../../aseel/AseelDenseTable';
import { CreateShipmentFromDealsModal } from '../../import-flow/CreateShipmentFromDealsModal';
import { useAseelIndexKeymap } from '../../aseel/useAseelIndexKeymap';
import { openInNewTab } from '@/utils/openInNewTab';
import { useConfirm } from '../../../contexts/ConfirmContext';
import { useToast } from '../../../contexts/ToastContext';
import { AseelErrorState } from '../../aseel';
import { formatDateValue } from "../../../utils/formatDate";

interface ShipmentManagementProps {
    currentUser: User;
    onOpenAccountingJournal?: (
        journalId: number | null,
        dealRef?: { dealId: string; dealNumber: string; displayName: string }
    ) => void;
}

const STATUS_LABELS: Record<string, string> = {
    draft:            'مسودة',
    payment_pending:  'بانتظار الدفع',
    partially_paid:   'مدفوع جزئياً',
    paid:             'مدفوع بالكامل',
    shipped:          'تم الشحن',
    delivered:        'تم التسليم',
    cancelled:        'ملغاة',
};

const STATUS_COLORS: Record<string, string> = {
    draft:           'var(--aseel-ink-soft)',
    payment_pending: 'var(--aseel-warn, #b8800a)',
    partially_paid:  'var(--aseel-warn, #b8800a)',
    paid:            'var(--aseel-ok, #267346)',
    shipped:         'var(--aseel-accent, #1857a4)',
    delivered:       'var(--aseel-ok, #267346)',
    cancelled:       'var(--aseel-danger, #c00)',
};

const fmtAmt = (n: number | undefined) =>
    (n ?? 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

const fmtDate = (s: string | undefined) => {
    if (!s) return '—';
    return formatDateValue(s);
};

export const ShipmentManagement: React.FC<ShipmentManagementProps> = ({
    currentUser,
    onOpenAccountingJournal,
}) => {
    const navigate = useNavigate();

    const confirm = useConfirm();
    const toast = useToast();
    const [shipments, setShipments] = useState<Shipment[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [reloadKey, setReloadKey] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [currentPage, setCurrentPage] = useState(1);
    const [hasNextPage, setHasNextPage] = useState(false);
    const [search, setSearch] = useState('');
    const [typeFilter, setTypeFilter] = useState<'all' | 'sea' | 'air'>('all');
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [viewingShipment, setViewingShipment] = useState<Shipment | null>(null);
    const [isCreateFromDealsOpen, setIsCreateFromDealsOpen] = useState(false);
    const searchInputRef = useRef<HTMLInputElement | null>(null);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        const timer = window.setTimeout(() => {
            void shipmentsService.listShipmentsPage({
                page: 1, pageSize: 50, search, status: statusFilter, shippingType: typeFilter,
            }).then((result) => {
                if (cancelled) return;
                setShipments(result.shipments);
                setTotalCount(result.count);
                setHasNextPage(result.hasNext);
                setCurrentPage(1);
                setLoadError(null);
            }).catch((error) => {
                if (!cancelled) {
                    setLoadError(error instanceof Error ? error.message : 'تعذّر تحميل الشحنات.');
                }
            }).finally(() => {
                if (!cancelled) setLoading(false);
            });
        }, 250);
        return () => { cancelled = true; window.clearTimeout(timer); };
    }, [reloadKey, search, statusFilter, typeFilter]);

    const filteredShipments = useMemo(() => {
        return shipments;
    }, [shipments]);

    const stats = useMemo(() => ({
        total: totalCount,
        inTransit: shipments.filter(s => ['shipped'].includes(s.status)).length,
        delivered: shipments.filter(s => s.status === 'delivered').length,
        totalCost: shipments.reduce((sum, s) => sum + (s.totalShippingCostUsd || 0), 0),
    }), [shipments, totalCount]);

    const openShipmentDetails = async (shipment: Shipment) => {
        setLoading(true);
        try {
            const detail = await shipmentsService.getShipment(String(shipment.id));
            setViewingShipment(detail);
            setLoadError(null);
        } catch (error) {
            setLoadError(error instanceof Error ? error.message : 'تعذّر فتح تفاصيل الشحنة.');
        } finally {
            setLoading(false);
        }
    };

    const loadMoreShipments = async () => {
        if (!hasNextPage || loading) return;
        setLoading(true);
        try {
            const nextPage = currentPage + 1;
            const result = await shipmentsService.listShipmentsPage({
                page: nextPage, pageSize: 50, search, status: statusFilter,
                shippingType: typeFilter,
            });
            setShipments((rows) => [...rows, ...result.shipments]);
            setCurrentPage(nextPage);
            setHasNextPage(result.hasNext);
            setTotalCount(result.count);
        } catch (error) {
            setLoadError(error instanceof Error ? error.message : 'تعذّر تحميل المزيد.');
        } finally {
            setLoading(false);
        }
    };

    // «شحنة جديدة» تفتح فاتح اختيار الصفقات الجاهزة (المسار الصحيح: اختر صفقات →
    // أنشئ شحنة)، بدل الشحنة الفارغة القديمة. «إنشاء بلا صفقات» يبقى متاحاً من الفاتح.
    const handleCreateNew = () => {
        setIsCreateFromDealsOpen(true);
    };

    const handleEdit = (shipment: Shipment) => {
        openInNewTab(`/import-flow/${encodeURIComponent(String(shipment.id))}`);
    };

    const handleDelete = async (shipmentId: string) => {
        if (!(await confirm({ title: 'حذف الشحنة', message: 'هل أنت متأكد من حذف هذه الشحنة؟' }))) return;
        try {
            await shipmentsService.deleteShipment(shipmentId);
        } catch (error) {
            // console suppressed
            toast('حدث خطأ أثناء حذف الشحنة', 'error');
        }
    };

    const columns: DenseColumn<Shipment>[] = [
        {
            key: 'shipmentNumber',
            header: 'رقم الشحنة',
            width: '130px',
            sortable: true,
            render: (s) => (
                <span>
                    <span style={{ marginLeft: 4 }}>{s.shippingInfo?.shippingType === 'air' ? '✈' : '🚢'}</span>
                    <b style={{ fontFamily: 'monospace' }}>{s.shipmentNumber}</b>
                    {(s.dealsCount ?? s.deals?.length ?? 0) > 0 && (
                        <span style={{ marginRight: 4, fontSize: 'var(--aseel-fs-sm)', color: 'var(--aseel-ink-soft)' }}>
                            ({s.dealsCount ?? s.deals?.length ?? 0} صفقة)
                        </span>
                    )}
                </span>
            ),
        },
        {
            key: 'shipmentName',
            header: 'اسم الشحنة',
            sortable: true,
            render: (s) => (
                <span title={s.shipmentName || undefined}>
                    {(s.shipmentName || '').trim() || '—'}
                </span>
            ),
        },
        {
            key: 'shippingAgentName',
            header: 'وكيل الشحن',
            width: '150px',
            render: (s) => <>{s.shippingAgentName || '—'}</>,
        },
        {
            key: 'type',
            header: 'النوع',
            width: '70px',
            align: 'center',
            render: (s) => <>{s.shippingInfo?.shippingType === 'air' ? 'جوي' : 'بحري'}</>,
        },
        {
            key: 'status',
            header: 'الحالة',
            width: '130px',
            render: (s) => (
                <span style={{ color: STATUS_COLORS[s.status] || 'inherit', fontWeight: 500 }}>
                    {STATUS_LABELS[s.status] || s.status}
                </span>
            ),
        },
        {
            key: 'departureDate',
            header: 'المغادرة',
            width: '90px',
            sortable: true,
            render: (s) => <>{fmtDate(s.shippingInfo?.departureDate)}</>,
        },
        {
            key: 'arrivalDate',
            header: 'الوصول',
            width: '90px',
            sortable: true,
            render: (s) => <>{fmtDate(s.shippingInfo?.arrivalDate)}</>,
        },
        {
            key: 'totalShippingCostUsd',
            header: 'التكلفة',
            width: '100px',
            align: 'right',
            numeric: true,
            sortable: true,
            render: (s) => (
                <span style={{ fontFamily: 'monospace' }}>
                    ${fmtAmt(s.totalShippingCostUsd)}
                </span>
            ),
        },
        {
            key: 'actions',
            header: '',
            width: '80px',
            align: 'center',
            render: (s) => (
                <span style={{ display: 'inline-flex', gap: 2 }}>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px' }}
                        onClick={(e) => { e.stopPropagation(); void openShipmentDetails(s); }}
                        title="عرض التفاصيل"
                    >
                        <Eye style={{ width: 13, height: 13 }} />
                    </button>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px' }}
                        onClick={(e) => { e.stopPropagation(); handleEdit(s); }}
                        title="تعديل (رحلة الاستيراد)"
                    >
                        <Edit style={{ width: 13, height: 13 }} />
                    </button>
                    <button
                        className="aseel-toolbtn"
                        style={{ padding: '2px 4px', color: 'var(--aseel-danger, #c00)' }}
                        onClick={(e) => { e.stopPropagation(); void handleDelete(String(s.id)); }}
                        title="حذف"
                    >
                        <Trash2 style={{ width: 13, height: 13 }} />
                    </button>
                </span>
            ),
        },
    ];

    // N0-T7 — keymap على قائمة الشحنات
    useAseelIndexKeymap({
        CtrlIns: handleCreateNew,
        F6: () => searchInputRef.current?.focus(),
        Escape: () => { setSearch(''); setTypeFilter('all'); setStatusFilter('all'); },
    },
    { enabled: !viewingShipment },
    );

    if (loading) return <LoadingSpinner />;
    if (loadError && shipments.length === 0) {
        return <AseelErrorState message={loadError} onRetry={() => {
            setLoading(true);
            setReloadKey((key) => key + 1);
        }} />;
    }

    return (
        <div dir="rtl" style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 6, padding: '8px 12px' }}>
            {/* شريط العنوان */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingBottom: 4, borderBottom: '1px solid var(--aseel-border)' }}>
                <strong style={{ fontSize: 'var(--aseel-fs-title, 14px)', color: 'var(--aseel-ink)' }}>
                    إدارة الشحنات
                </strong>
                <span className="aseel-status-item">الإجمالي: <b>{stats.total}</b></span>
                <span className="aseel-status-item">في الشحن: <b>{stats.inTransit}</b></span>
                <span className="aseel-status-item">تم التسليم: <b>{stats.delivered}</b></span>
                <span className="aseel-status-item">إجمالي التكلفة: <b>${fmtAmt(stats.totalCost)}</b></span>
                <div style={{ flex: 1 }} />
                <input
                    ref={searchInputRef}
                    className="aseel-input"
                    style={{ width: 190 }}
                    placeholder="بحث بالاسم، رقم الشحنة، الوكيل… (F6)"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                <select
                    className="aseel-input"
                    style={{ width: 120 }}
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value as 'all' | 'sea' | 'air')}
                >
                    <option value="all">كل الأنواع</option>
                    <option value="sea">🚢 بحري</option>
                    <option value="air">✈️ جوي</option>
                </select>
                <select
                    className="aseel-input"
                    style={{ width: 150 }}
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                >
                    <option value="all">كل الحالات</option>
                    {Object.entries(STATUS_LABELS).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                    ))}
                </select>
                <button
                    className="aseel-toolbtn"
                    onClick={() => { setSearch(''); setTypeFilter('all'); setStatusFilter('all'); }}
                    title="إعادة تعيين الفلاتر"
                >
                    <RefreshCw style={{ width: 14, height: 14 }} />
                </button>
                <button
                    className="aseel-toolbtn"
                    onClick={handleCreateNew}
                    title="تفتح «رحلة الاستيراد» لشحنة جديدة: بيانات ← صفقات ← دفع شحن ← تخليص ← فواتير (Ctrl+Ins)"
                >
                    <Plus style={{ width: 14, height: 14 }} /> شحنة جديدة
                </button>
            </div>

            {/* عقد موحّد مع صفحات التخليص والنقل المحلي: التحرير داخل رحلة الاستيراد */}
            <p style={{ fontSize: 'var(--aseel-fs-sm, 12px)', color: 'var(--aseel-ink-soft)', margin: 0 }}>
                نقرة مزدوجة تفتح <b>ملخص الشحنة</b> · زر التعديل ✎ يفتح <b>«رحلة الاستيراد»</b>
                (الصفقات، دفع الشحن، التخليص، النقل المحلي، الفواتير).
            </p>

            {/* جدول الشحنات */}
            <AseelDenseTable<Shipment>
                columns={columns}
                rows={filteredShipments}
                getRowKey={(s) => s.id}
                loading={loading}
                emptyHint="لا توجد شحنات — اضغط «شحنة جديدة»"
                // فتح الشحنة = ملخصها الواضح؛ «رحلة الاستيراد» من زر التعديل فقط
                onRowDoubleClick={(s) => { void openShipmentDetails(s); }}
                footer={
                    filteredShipments.length > 0 ? (
                        <span style={{ fontFamily: 'monospace', fontSize: 'var(--aseel-fs-sm)' }}>
                            إجمالي التكلفة: <b>${fmtAmt(filteredShipments.reduce((s, r) => s + (r.totalShippingCostUsd || 0), 0))}</b>
                        </span>
                    ) : undefined
                }
            />
            {hasNextPage && (
                <button className="aseel-toolbtn" onClick={() => void loadMoreShipments()}>
                    تحميل المزيد ({shipments.length} من {totalCount})
                </button>
            )}

            {viewingShipment && (
                <ShipmentDetailView
                    shipment={viewingShipment}
                    onClose={() => setViewingShipment(null)}
                />
            )}

            {/* «شحنة جديدة» = اختَر صفقات جاهزة → أنشئ شحنة (المسار الصحيح). زر
                «إنشاء شحنة فارغة» داخل الفاتح يبقي مسار الترويسة-أولاً متاحاً. */}
            <CreateShipmentFromDealsModal
                isOpen={isCreateFromDealsOpen}
                onClose={() => setIsCreateFromDealsOpen(false)}
                onCreated={(shipmentId) => {
                    setIsCreateFromDealsOpen(false);
                    openInNewTab(`/import-flow/${encodeURIComponent(String(shipmentId))}`);
                }}
                onCreateEmpty={() => {
                    setIsCreateFromDealsOpen(false);
                    openInNewTab('/import-flow/new');
                }}
            />
        </div>
    );
};
