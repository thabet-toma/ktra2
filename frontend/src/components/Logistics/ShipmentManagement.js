import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Grid, Chip, Dialog,
    DialogTitle, DialogContent, TextField, DialogActions, Tabs, Tab,
    MenuItem, List, ListItem, ListItemText, Checkbox, Divider,
    Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
    IconButton, Tooltip, LinearProgress, Alert
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import {
    Add as AddIcon, Edit as EditIcon, LocalShipping as ShipIcon,
    Link as LinkIcon, DirectionsBoat, Warehouse, Receipt, Save,
    Close, Cloud, Flight, FlightTakeoff, Info, Payment,
    Delete as DeleteIcon, AttachFile
} from '@mui/icons-material';
import logisticsService from '../../services/logisticsService';
import accountingService from '../../services/accountingService';

// ===== Status Config =====
const SHIPMENT_STATUSES = [
    { value: 'draft', label: 'مسودة', color: '#6b7280', bg: '#f3f4f6' },
    { value: 'Pending', label: 'قيد الانتظار', color: '#d97706', bg: '#fffbeb' },
    { value: 'Loading', label: 'قيد التحميل', color: '#2563eb', bg: '#eff6ff' },
    { value: 'InTransit', label: 'في الطريق', color: '#0891b2', bg: '#ecfeff' },
    { value: 'Arrived', label: 'وصل الميناء', color: '#7c3aed', bg: '#f5f3ff' },
    { value: 'Clearance', label: 'تخليص جمركي', color: '#c026d3', bg: '#fdf4ff' },
    { value: 'Delivered', label: 'تم التسليم', color: '#059669', bg: '#ecfdf5' },
    { value: 'Cancelled', label: 'ملغاة', color: '#dc2626', bg: '#fef2f2' },
];

const SEA_STATUSES = ['agent_warehouse', 'loading', 'sailing', 'destination_port', 'clearance', 'domestic_delivery', 'delivered'];
const AIR_STATUSES = ['agent_warehouse', 'airport', 'flying', 'destination_airport', 'customs', 'domestic_delivery', 'delivered'];

// ===== StatusVisualizer Component =====
const StatusVisualizer = ({ type = 'sea', currentStatus }) => {
    const steps = type === 'sea' ? SEA_STATUSES : AIR_STATUSES;
    const labels = {
        agent_warehouse: 'مخزن الوكيل',
        loading: type === 'sea' ? 'تحميل الميناء' : 'المطار',
        sailing: 'إبحار',
        flying: 'طيران',
        destination_port: 'ميناء الوصول',
        destination_airport: 'مطار الوصول',
        clearance: 'تخليص',
        airport: 'المطار',
        customs: 'الجمارك',
        domestic_delivery: 'توصيل محلي',
        delivered: 'تم التسليم',
    };
    const idx = steps.indexOf(currentStatus);
    return (
        <Box sx={{ display: 'flex', gap: 0, overflowX: 'auto', py: 1 }}>
            {steps.map((s, i) => (
                <Box key={s} sx={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                    <Box sx={{
                        textAlign: 'center', px: 1.5, py: 1, borderRadius: 2, minWidth: 80,
                        bgcolor: i <= idx ? '#1d4ed8' : '#f1f5f9',
                        color: i <= idx ? '#fff' : '#94a3b8',
                        transition: 'all 0.2s'
                    }}>
                        <Typography fontSize="0.7rem" fontWeight={700}>{labels[s] || s}</Typography>
                    </Box>
                    {i < steps.length - 1 && (
                        <Box sx={{ width: 20, height: 2, bgcolor: i < idx ? '#1d4ed8' : '#e2e8f0' }} />
                    )}
                </Box>
            ))}
        </Box>
    );
};

// ===== CollapsibleSection =====
const CollapsibleSection = ({ title, icon: Icon, children, defaultOpen = true }) => {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <Paper sx={{ borderRadius: 2, overflow: 'hidden', mb: 2, border: '1px solid #e2e8f0' }}>
            <Box onClick={() => setOpen(!open)}
                sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 1.5, px: 2, bgcolor: '#f8fafc', cursor: 'pointer', '&:hover': { bgcolor: '#f1f5f9' }, borderBottom: open ? '1px solid #e2e8f0' : 'none' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {Icon && <Icon sx={{ fontSize: 18, color: '#3b82f6' }} />}
                    <Typography fontWeight={700} fontSize="0.9rem">{title}</Typography>
                </Box>
                <Typography color="text.secondary" fontSize="0.75rem">{open ? '▲' : '▼'}</Typography>
            </Box>
            {open && <Box sx={{ p: 2 }}>{children}</Box>}
        </Paper>
    );
};

// ===== MAIN COMPONENT =====
const ShipmentManagement = () => {
    const [shipments, setShipments] = useState([]);
    const [agents, setAgents] = useState([]);
    const [allDeals, setAllDeals] = useState([]);
    const [loading, setLoading] = useState(false);
    const [editDialogOpen, setEditDialogOpen] = useState(false);
    const [linkDialogOpen, setLinkDialogOpen] = useState(false);
    const [targetShipmentId, setTargetShipmentId] = useState(null);
    const [selectedDeals, setSelectedDeals] = useState([]);
    const [activeFormTab, setActiveFormTab] = useState(0);

    const emptyShipment = () => ({
        shipment_number: '',
        shipment_name: '',
        agent_shipment_number: '',
        shipping_agent: '',
        shipping_type: 'sea',
        status: 'Pending',
        pricing_method: 'total',
        unit_type: 'cbm',
        price_per_unit: 0,
        total_shipping_cost_usd: 0,
        total_volume: 0,
        total_weight_kg: 0,
        remaining_amount: 0,
        installment_plan_enabled: false,
        // sea fields
        ship_name: '',
        international_shipping_company: '',
        imo_number: '',
        mmsi_number: '',
        tracking_link: '',
        bill_of_lading_file: '',
        from_term: '',
        to_term: 'DDP',
        // air fields
        flight_number: '',
        airway_bill_number: '',
        airway_bill_file: '',
        // dates
        departure_date: new Date().toISOString().split('T')[0],
        arrival_date: '',
        // other
        notes: '',
        israeli_side_name: '',
        container_number: '',
        bill_of_lading: '',
    });

    const [currentShipment, setCurrentShipment] = useState(emptyShipment());

    useEffect(() => { loadData(); }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [shipData, partnersData, dealsData] = await Promise.all([
                logisticsService.getShipments(),
                accountingService.getPartners(),
                logisticsService.getDeals()
            ]);
            setShipments(shipData);
            setAgents(partnersData.filter(p => !p.is_customer));
            setAllDeals(dealsData);
        } catch (e) { console.error(e); }
        finally { setLoading(false); }
    };

    const handleOpenNew = () => { setCurrentShipment(emptyShipment()); setActiveFormTab(0); setEditDialogOpen(true); };
    const handleOpenEdit = (s) => { setCurrentShipment({ ...s }); setActiveFormTab(0); setEditDialogOpen(true); };

    const handleSave = async () => {
        try {
            if (currentShipment.id) {
                await logisticsService.updateShipment(currentShipment.id, currentShipment);
            } else {
                await logisticsService.createShipment(currentShipment);
            }
            setEditDialogOpen(false);
            loadData();
        } catch (e) { alert("❌ فشل الحفظ: " + (e.response?.data ? JSON.stringify(e.response.data) : e.message)); }
    };

    const handleOpenLinkDialog = async (shipment) => {
        setTargetShipmentId(shipment.id);
        setSelectedDeals([]);
        setLinkDialogOpen(true);
    };

    const handleLinkDeals = async () => {
        try {
            for (const dealId of selectedDeals) {
                await logisticsService.addDealToShipment(targetShipmentId, dealId);
            }
            setLinkDialogOpen(false);
            loadData();
        } catch (e) { alert("❌ خطأ في ربط الصفقات: " + e.message); }
    };

    const getStatusCfg = (val) => SHIPMENT_STATUSES.find(s => s.value === val) || SHIPMENT_STATUSES[1];

    const set = (field, val) => setCurrentShipment(p => ({ ...p, [field]: val }));

    return (
        <Box dir="rtl" sx={{ p: 3 }}>
            {/* Header */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                <Box>
                    <Typography variant="h5" fontWeight={800}>🚢 إدارة الشحنات</Typography>
                    <Typography variant="body2" color="text.secondary">{shipments.length} شحنة مسجلة</Typography>
                </Box>
                <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenNew} sx={{ borderRadius: 2, fontWeight: 700 }}>
                    شحنة جديدة
                </Button>
            </Box>

            {loading && <LinearProgress sx={{ mb: 2, borderRadius: 1 }} />}

            {/* Shipments Cards Grid */}
            <Grid container spacing={2}>
                {shipments.map(s => {
                    const cfg = getStatusCfg(s.status);
                    const linkedDeals = s.deals || [];
                    return (
                        <Grid item xs={12} md={6} lg={4} key={s.id}>
                            <Paper sx={{ p: 2.5, borderRadius: 3, border: '1px solid #e2e8f0', '&:hover': { boxShadow: 4 }, transition: 'box-shadow 0.2s', cursor: 'pointer' }}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1.5 }}>
                                    <Box>
                                        <Typography fontWeight={800} fontSize="1rem">
                                            {s.shipping_type === 'air' ? '✈️' : '🚢'} شحنة #{s.shipment_number}
                                        </Typography>
                                        {s.shipment_name && <Typography variant="caption" color="text.secondary">{s.shipment_name}</Typography>}
                                        {s.agent_shipment_number && <Typography variant="caption" display="block" color="text.secondary" fontFamily="monospace">Ref: {s.agent_shipment_number}</Typography>}
                                    </Box>
                                    <Box sx={{ px: 1.5, py: 0.4, bgcolor: cfg.bg, color: cfg.color, borderRadius: 2, fontSize: '0.78rem', fontWeight: 700, border: `1px solid ${cfg.color}30` }}>
                                        {cfg.label}
                                    </Box>
                                </Box>

                                <Divider sx={{ my: 1.5 }} />

                                <Grid container spacing={1} sx={{ fontSize: '0.82rem', mb: 1.5 }}>
                                    <Grid item xs={6}><Typography variant="caption" color="text.secondary">وكيل الشحن</Typography><Typography fontWeight={600} fontSize="0.82rem">{s.agent_name || s.shipping_agent || '-'}</Typography></Grid>
                                    <Grid item xs={6}><Typography variant="caption" color="text.secondary">تاريخ المغادرة</Typography><Typography fontWeight={600} fontSize="0.82rem">{s.departure_date || '-'}</Typography></Grid>
                                    <Grid item xs={6}><Typography variant="caption" color="text.secondary">تكلفة الشحن</Typography><Typography fontWeight={700} color="#1d4ed8" fontSize="0.88rem">${Number(s.total_shipping_cost_usd || 0).toLocaleString()}</Typography></Grid>
                                    <Grid item xs={6}><Typography variant="caption" color="text.secondary">الوزن / CBM</Typography><Typography fontWeight={600} fontSize="0.82rem">{s.total_weight_kg}kg / {s.total_volume}m³</Typography></Grid>
                                </Grid>

                                {linkedDeals.length > 0 && (
                                    <Box sx={{ bgcolor: '#f8fafc', borderRadius: 2, p: 1, mb: 1.5 }}>
                                        <Typography variant="caption" color="text.secondary" fontWeight={700}>الصفقات ({linkedDeals.length})</Typography>
                                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                                            {linkedDeals.map(d => <Chip key={d.id} label={`#${d.ref_number || d.id}`} size="small" sx={{ fontSize: '0.7rem' }} />)}
                                        </Box>
                                    </Box>
                                )}

                                <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                                    <Button size="small" variant="outlined" startIcon={<EditIcon />} onClick={() => handleOpenEdit(s)} sx={{ flex: 1, borderRadius: 2 }}>تعديل</Button>
                                    <Button size="small" variant="contained" startIcon={<LinkIcon />} onClick={() => handleOpenLinkDialog(s)} sx={{ flex: 1, borderRadius: 2 }}>ربط صفقات</Button>
                                </Box>
                            </Paper>
                        </Grid>
                    );
                })}
            </Grid>

            {shipments.length === 0 && !loading && (
                <Paper sx={{ p: 5, textAlign: 'center', borderRadius: 3, border: '2px dashed #e2e8f0' }}>
                    <ShipIcon sx={{ fontSize: 60, color: '#94a3b8', mb: 2 }} />
                    <Typography variant="h6" color="text.secondary">لا توجد شحنات</Typography>
                    <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenNew} sx={{ mt: 2, borderRadius: 2 }}>إضافة شحنة جديدة</Button>
                </Paper>
            )}

            {/* ===== SHIPMENT FORM DIALOG ===== */}
            <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="lg" fullWidth dir="rtl">
                <DialogTitle sx={{ bgcolor: '#0f172a', color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <ShipIcon />
                        <Box>
                            <Typography fontWeight={800}>{currentShipment.id ? `تعديل شحنة #${currentShipment.shipment_number}` : 'إنشاء شحنة جديدة'}</Typography>
                            {currentShipment.agent_shipment_number && <Typography variant="caption" sx={{ opacity: 0.7 }}>Ref: {currentShipment.agent_shipment_number}</Typography>}
                        </Box>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                        <Button variant="outlined" size="small" onClick={() => setEditDialogOpen(false)} sx={{ color: '#fff', borderColor: '#fff' }}>إلغاء</Button>
                        <Button variant="contained" size="small" startIcon={<Save />} onClick={handleSave} sx={{ bgcolor: '#1d4ed8', '&:hover': { bgcolor: '#1e40af' } }}>حفظ</Button>
                    </Box>
                </DialogTitle>

                {/* Status visualizer */}
                <Box sx={{ bgcolor: '#1e293b', px: 3, py: 1.5 }}>
                    <StatusVisualizer type={currentShipment.shipping_type || 'sea'} currentStatus="agent_warehouse" />
                </Box>

                {/* Form Tabs */}
                <Tabs value={activeFormTab} onChange={(_, v) => setActiveFormTab(v)} sx={{ bgcolor: '#f8fafc', borderBottom: '1px solid #e2e8f0', px: 2 }}>
                    <Tab icon={<Info sx={{ fontSize: 16 }} />} iconPosition="start" label="بيانات الشحنة" sx={{ fontWeight: 700, fontSize: '0.85rem' }} />
                    <Tab icon={<ShipIcon sx={{ fontSize: 16 }} />} iconPosition="start" label="تفاصيل الشحن" sx={{ fontWeight: 700, fontSize: '0.85rem' }} />
                    <Tab icon={<Payment sx={{ fontSize: 16 }} />} iconPosition="start" label="التكلفة والدفع" sx={{ fontWeight: 700, fontSize: '0.85rem' }} />
                </Tabs>

                <DialogContent sx={{ bgcolor: '#f8fafc', p: 3 }}>

                    {/* TAB 0: Basic Info */}
                    {activeFormTab === 0 && (
                        <Grid container spacing={2}>
                            <Grid item xs={12}>
                                <CollapsibleSection title="المعلومات الأساسية للشحنة" icon={Info}>
                                    <Grid container spacing={2}>
                                        <Grid item xs={6} sm={4}>
                                            <TextField select fullWidth size="small" label="نوع الشحن"
                                                value={currentShipment.shipping_type || 'sea'} onChange={e => set('shipping_type', e.target.value)}>
                                                <MenuItem value="sea">🚢 بحري (Sea)</MenuItem>
                                                <MenuItem value="air">✈️ جوي (Air)</MenuItem>
                                            </TextField>
                                        </Grid>
                                        <Grid item xs={6} sm={4}>
                                            <TextField fullWidth size="small" label="رقم الشحنة (Internal)"
                                                value={currentShipment.shipment_number || ''} onChange={e => set('shipment_number', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={6} sm={4}>
                                            <TextField fullWidth size="small" label="رقم الشحنة لدى الوكيل"
                                                value={currentShipment.agent_shipment_number || ''} onChange={e => set('agent_shipment_number', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={6} sm={6}>
                                            <TextField fullWidth size="small" label="اسم الشحنة"
                                                value={currentShipment.shipment_name || ''} onChange={e => set('shipment_name', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={6} sm={6}>
                                            <TextField fullWidth size="small" label="الجهة الإسرائيلية المستلمة"
                                                value={currentShipment.israeli_side_name || ''} onChange={e => set('israeli_side_name', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={6} sm={4}>
                                            <TextField select fullWidth size="small" label="وكيل الشحن"
                                                value={currentShipment.shipping_agent || ''} onChange={e => set('shipping_agent', e.target.value)}>
                                                {agents.map(a => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
                                            </TextField>
                                        </Grid>
                                        <Grid item xs={6} sm={4}>
                                            <TextField select fullWidth size="small" label="الحالة"
                                                value={currentShipment.status || 'Pending'} onChange={e => set('status', e.target.value)}>
                                                {SHIPMENT_STATUSES.map(s => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
                                            </TextField>
                                        </Grid>
                                        <Grid item xs={6} sm={4}>
                                            <TextField fullWidth size="small" label="رقم الحاوية (Container)"
                                                value={currentShipment.container_number || ''} onChange={e => set('container_number', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={6} sm={4}>
                                            <TextField type="date" fullWidth size="small" label="تاريخ المغادرة" InputLabelProps={{ shrink: true }}
                                                value={currentShipment.departure_date || ''} onChange={e => set('departure_date', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={6} sm={4}>
                                            <TextField type="date" fullWidth size="small" label="تاريخ الوصول" InputLabelProps={{ shrink: true }}
                                                value={currentShipment.arrival_date || ''} onChange={e => set('arrival_date', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={12}>
                                            <TextField fullWidth size="small" multiline rows={2} label="ملاحظات"
                                                value={currentShipment.notes || ''} onChange={e => set('notes', e.target.value)} />
                                        </Grid>
                                    </Grid>
                                </CollapsibleSection>
                            </Grid>
                        </Grid>
                    )}

                    {/* TAB 1: Shipping Details */}
                    {activeFormTab === 1 && (
                        <Grid container spacing={2}>
                            {currentShipment.shipping_type === 'sea' ? (
                                <Grid item xs={12}>
                                    <CollapsibleSection title="تفاصيل الشحن البحري" icon={DirectionsBoat}>
                                        <Grid container spacing={2}>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="اسم السفينة"
                                                    value={currentShipment.ship_name || ''} onChange={e => set('ship_name', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="شركة الشحن الدولية"
                                                    value={currentShipment.international_shipping_company || ''} onChange={e => set('international_shipping_company', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="رقم IMO"
                                                    value={currentShipment.imo_number || ''} onChange={e => set('imo_number', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="رقم MMSI"
                                                    value={currentShipment.mmsi_number || ''} onChange={e => set('mmsi_number', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="من (From Term)"
                                                    value={currentShipment.from_term || ''} onChange={e => set('from_term', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="إلى (To Term)"
                                                    value={currentShipment.to_term || 'DDP'} onChange={e => set('to_term', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="رقم بوليصة الشحن (B/L)"
                                                    value={currentShipment.bill_of_lading || ''} onChange={e => set('bill_of_lading', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={12}>
                                                <TextField fullWidth size="small" label="رابط تتبع الشحنة"
                                                    value={currentShipment.tracking_link || ''} onChange={e => set('tracking_link', e.target.value)} />
                                            </Grid>
                                        </Grid>
                                    </CollapsibleSection>
                                </Grid>
                            ) : (
                                <Grid item xs={12}>
                                    <CollapsibleSection title="تفاصيل الشحن الجوي" icon={FlightTakeoff}>
                                        <Grid container spacing={2}>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="رقم الرحلة"
                                                    value={currentShipment.flight_number || ''} onChange={e => set('flight_number', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="رقم بوليصة الشحن الجوي (AWB)"
                                                    value={currentShipment.airway_bill_number || ''} onChange={e => set('airway_bill_number', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="من (From Term)"
                                                    value={currentShipment.from_term || ''} onChange={e => set('from_term', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={6} sm={4}>
                                                <TextField fullWidth size="small" label="إلى (To Term)"
                                                    value={currentShipment.to_term || 'DDP'} onChange={e => set('to_term', e.target.value)} />
                                            </Grid>
                                            <Grid item xs={12}>
                                                <TextField fullWidth size="small" label="رابط تتبع الشحنة"
                                                    value={currentShipment.tracking_link || ''} onChange={e => set('tracking_link', e.target.value)} />
                                            </Grid>
                                        </Grid>
                                    </CollapsibleSection>
                                </Grid>
                            )}

                            {/* Dimensions */}
                            <Grid item xs={12}>
                                <CollapsibleSection title="الأبعاد والأوزان" icon={Warehouse}>
                                    <Grid container spacing={2}>
                                        <Grid item xs={6} sm={3}>
                                            <TextField type="number" fullWidth size="small" label="الحجم الكلي (CBM / m³)"
                                                value={currentShipment.total_volume || 0} onChange={e => set('total_volume', e.target.value)} />
                                        </Grid>
                                        <Grid item xs={6} sm={3}>
                                            <TextField type="number" fullWidth size="small" label="الوزن الكلي (Kg)"
                                                value={currentShipment.total_weight_kg || 0} onChange={e => set('total_weight_kg', e.target.value)} />
                                        </Grid>
                                    </Grid>
                                </CollapsibleSection>
                            </Grid>
                        </Grid>
                    )}

                    {/* TAB 2: Finance */}
                    {activeFormTab === 2 && (
                        <Grid container spacing={2}>
                            <Grid item xs={12}>
                                <CollapsibleSection title="تسعير الشحن" icon={Payment}>
                                    <Grid container spacing={2}>
                                        <Grid item xs={6} sm={3}>
                                            <TextField select fullWidth size="small" label="طريقة التسعير"
                                                value={currentShipment.pricing_method || 'total'} onChange={e => set('pricing_method', e.target.value)}>
                                                <MenuItem value="total">إجمالي</MenuItem>
                                                <MenuItem value="unit">بالوحدة</MenuItem>
                                            </TextField>
                                        </Grid>
                                        {currentShipment.pricing_method === 'unit' && (
                                            <>
                                                <Grid item xs={6} sm={3}>
                                                    <TextField select fullWidth size="small" label="نوع الوحدة"
                                                        value={currentShipment.unit_type || 'cbm'} onChange={e => set('unit_type', e.target.value)}>
                                                        <MenuItem value="cbm">CBM</MenuItem>
                                                        <MenuItem value="weight">وزن (Kg)</MenuItem>
                                                        <MenuItem value="container">حاوية</MenuItem>
                                                    </TextField>
                                                </Grid>
                                                <Grid item xs={6} sm={3}>
                                                    <TextField type="number" fullWidth size="small" label="السعر لكل وحدة ($)"
                                                        value={currentShipment.price_per_unit || 0} onChange={e => set('price_per_unit', e.target.value)} />
                                                </Grid>
                                            </>
                                        )}
                                        <Grid item xs={6} sm={3}>
                                            <TextField type="number" fullWidth size="small" label="إجمالي تكلفة الشحن ($)"
                                                value={currentShipment.total_shipping_cost_usd || 0} onChange={e => set('total_shipping_cost_usd', e.target.value)} />
                                        </Grid>
                                    </Grid>
                                </CollapsibleSection>
                            </Grid>
                        </Grid>
                    )}
                </DialogContent>
            </Dialog>

            {/* ===== LINK DEALS DIALOG ===== */}
            <Dialog open={linkDialogOpen} onClose={() => setLinkDialogOpen(false)} maxWidth="sm" fullWidth dir="rtl">
                <DialogTitle fontWeight={700}>🔗 ربط صفقات بالشحنة</DialogTitle>
                <DialogContent dividers>
                    <List dense>
                        {allDeals.map(d => (
                            <ListItem key={d.id} secondaryAction={
                                <Checkbox checked={selectedDeals.includes(d.id)} onChange={e => {
                                    setSelectedDeals(e.target.checked
                                        ? [...selectedDeals, d.id]
                                        : selectedDeals.filter(id => id !== d.id));
                                }} />
                            }>
                                <ListItemText
                                    primary={`صفقة #${d.ref_number || d.id}`}
                                    secondary={`${d.partner_name || ''} • $${Number(d.total_amount || 0).toLocaleString()}`}
                                />
                            </ListItem>
                        ))}
                    </List>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setLinkDialogOpen(false)}>إلغاء</Button>
                    <Button variant="contained" onClick={handleLinkDeals} disabled={selectedDeals.length === 0}>
                        ربط ({selectedDeals.length})
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ShipmentManagement;
