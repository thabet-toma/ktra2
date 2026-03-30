import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Grid, IconButton, useTheme,
    Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
    Chip, TextField, InputAdornment, Tooltip
} from '@mui/material';
import {
    Add as AddIcon, Edit as EditIcon,
    Search, AccountBalanceWallet, LocalShipping,
    Description, Assessment, PowerSettingsNew,
    PostAdd as PostIcon, CheckCircle
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import logisticsService from '../../services/logisticsService';

const DealsDashboard = () => {
    const theme = useTheme();
    const navigate = useNavigate();
    const [deals, setDeals] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const dealsData = await logisticsService.getDeals();
            setDeals(dealsData);
        } catch (error) {
            console.error("Error loading logistics data", error);
        } finally {
            setLoading(false);
        }
    };

    const handlePostToAccounting = async (id) => {
        if (!window.confirm("هل أنت متأكد من ترحيل هذه الصفقة إلى المحاسبة؟")) return;
        try {
            await logisticsService.postDealToAccounting(id);
            alert("تم الترحيل بنجاح");
            loadData();
        } catch (error) {
            alert("فشل الترحيل: " + (error.response?.data?.error || error.message));
        }
    };

    const filteredDeals = deals.filter(deal =>
        deal.ref_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        deal.partner_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        deal.description?.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const totalValue = deals.reduce((sum, d) => sum + parseFloat(d.total_amount || 0), 0);
    const postedCount = deals.filter(d => d.is_posted).length;

    return (
        <Box dir="rtl" sx={{ height: '100vh', display: 'flex', flexDirection: 'column', bgcolor: '#f1f5f9', fontFamily: 'Inter, sans-serif' }}>
            {/* 1. Slim Header Bar */}
            <Paper elevation={0} sx={{ p: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#0f172a', color: 'white', borderRadius: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <Assessment sx={{ fontSize: 24, color: '#fbbf24' }} />
                    <Box>
                        <Typography variant="subtitle1" fontWeight="800" sx={{ lineHeight: 1 }}>إدارة صفقات الاستيراد</Typography>
                        <Typography variant="caption" sx={{ opacity: 0.7, fontSize: '0.65rem' }}>إجمالي القيمة: {totalValue.toLocaleString()} $ | المؤرشفة: {postedCount}</Typography>
                    </Box>
                </Box>
                <Button
                    variant="contained" size="small"
                    onClick={() => navigate('/logistics/deals/new')}
                    sx={{ bgcolor: '#fbbf24', color: '#000', '&:hover': { bgcolor: '#f59e0b' }, fontWeight: 'bold', fontSize: '0.75rem' }}
                >
                    + صفقة جديدة
                </Button>
            </Paper>

            {/* 2. Search & Filter Bar */}
            <Box sx={{ p: 0.8, display: 'flex', gap: 1, alignItems: 'center', bgcolor: 'white', borderBottom: '1px solid #cbd5e1' }}>
                <TextField
                    size="small" placeholder="بحث..."
                    value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
                    sx={{ width: 300, '& .MuiInputBase-root': { fontSize: '0.8rem', height: 32 } }}
                    InputProps={{
                        startAdornment: <InputAdornment position="start"><Search sx={{ fontSize: 18 }} /></InputAdornment>,
                    }}
                />
                <Box sx={{ flexGrow: 1 }} />
                <Chip label={`الكل (${deals.length})`} size="small" onClick={() => { }} color="primary" sx={{ height: 24, fontSize: '0.7rem' }} />
                <Chip label={`مرحل (${postedCount})`} size="small" variant="outlined" sx={{ height: 24, fontSize: '0.7rem' }} />
                <Chip label={`قيد العمل (${deals.length - postedCount})`} size="small" variant="outlined" sx={{ height: 24, fontSize: '0.7rem' }} />
            </Box>

            {/* 3. Extreme-Density Table */}
            <TableContainer component={Paper} elevation={0} sx={{ flexGrow: 1, overflowY: 'auto', borderRadius: 0 }}>
                <Table size="small" stickyHeader sx={{
                    borderCollapse: 'collapse',
                    '& .MuiTableCell-root': {
                        py: 0.15,
                        px: 0.4,
                        textAlign: 'right',
                        fontSize: '0.68rem',
                        border: '1px solid #e2e8f0',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis'
                    }
                }}>
                    <TableHead>
                        <TableRow>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '30px', textAlign: 'center' }}>رقم</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '150px', whiteSpace: 'normal' }}>الوصف والبيان</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444' }}>المورد</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '80px', textAlign: 'center' }}>تاريخ الطلب</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '60px' }} align="center">حالة الصفقة</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '60px' }} align="center">حالة الدفع</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '80px' }} align="center">الإجمالي ($)</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '90px' }}>الشحن</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '50px' }} align="center">محاسبة</TableCell>
                            <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', color: '#444', width: '40px' }} align="center">تعديل</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {filteredDeals.map((deal) => (
                            <TableRow key={deal.id} hover sx={{ '&:nth-of-type(even)': { bgcolor: '#f1f5f9' } }}>
                                <TableCell sx={{ fontWeight: 'bold', color: '#0f172a', textAlign: 'center' }}>{deal.ref_number}</TableCell>
                                <TableCell sx={{ whiteSpace: 'normal' }}>{deal.description || '---'}</TableCell>
                                <TableCell>{deal.partner_name}</TableCell>
                                <TableCell sx={{ textAlign: 'center' }}>{deal.order_date}</TableCell>
                                <TableCell align="center">
                                    <Chip
                                        label={deal.status} size="small"
                                        color={deal.status === 'Open' ? 'info' : deal.status === 'Closed' ? 'success' : 'default'}
                                        sx={{ height: 16, fontSize: '0.6rem', borderRadius: '2px' }}
                                    />
                                </TableCell>
                                <TableCell align="center">
                                    <Chip
                                        label={deal.payment_status} size="small"
                                        color={deal.payment_status === 'Fully Paid' ? 'success' : deal.payment_status === 'Partially Paid' ? 'warning' : 'error'}
                                        sx={{ height: 16, fontSize: '0.6rem', borderRadius: '2px' }}
                                    />
                                </TableCell>
                                <TableCell align="center" sx={{ fontWeight: 'bold', color: '#0369a1' }}>
                                    {parseFloat(deal.total_amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                                </TableCell>
                                <TableCell>
                                    <Typography variant="caption" sx={{ fontSize: '0.65rem' }}>
                                        {deal.shipping_method} ({deal.incoterms})
                                    </Typography>
                                </TableCell>
                                <TableCell align="center">
                                    {deal.is_posted ? (
                                        <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
                                    ) : (
                                        <Button
                                            size="small" variant="contained"
                                            onClick={() => handlePostToAccounting(deal.id)}
                                            sx={{
                                                py: 0, px: 0.5, fontSize: '0.6rem', minWidth: 'unset',
                                                bgcolor: '#0f172a', color: '#fff', '&:hover': { bgcolor: '#334155' }
                                            }}
                                        >
                                            ترحيل
                                        </Button>
                                    )}
                                </TableCell>
                                <TableCell align="center">
                                    <IconButton size="small" sx={{ p: 0 }} color="primary" onClick={() => navigate(`/logistics/deals/edit/${deal.id}`)}>
                                        <EditIcon sx={{ fontSize: 14 }} />
                                    </IconButton>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Box>
    );
};

export default DealsDashboard;

