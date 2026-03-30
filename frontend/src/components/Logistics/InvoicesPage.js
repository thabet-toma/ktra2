import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Grid, Chip, Dialog,
    DialogTitle, DialogContent, TextField, DialogActions,
    MenuItem, LinearProgress, Avatar, TableContainer, Table,
    TableHead, TableRow, TableCell, TableBody, InputAdornment,
    IconButton, Tooltip
} from '@mui/material';
import {
    Receipt as ReceiptIcon, AccountBalanceWallet, Search,
    CheckCircle
} from '@mui/icons-material';
import axios from 'axios';
import logisticsService from '../../services/logisticsService';
import accountingService from '../../services/accountingService';

const InvoicesPage = () => {
    const [payments, setPayments] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');

    const [openDialog, setOpenDialog] = useState(false);
    const [selectedPayment, setSelectedPayment] = useState(null);
    const [selectedBank, setSelectedBank] = useState('');

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            // Fetch all payments (requires the new endpoint we added in urls.py)
            const paymentsRes = await axios.get('http://localhost:8000/api/logistics/payments/');
            const payData = Array.isArray(paymentsRes.data) ? paymentsRes.data : (paymentsRes.data.results || []);
            setPayments(payData);

            const accData = await accountingService.getChartOfAccounts();
            setAccounts(accData);
        } catch (error) {
            console.error("Error loading invoices data", error);
        } finally {
            setLoading(false);
        }
    };

    const handlePostPayment = async () => {
        if (!selectedPayment) return;
        try {
            await logisticsService.postPaymentToAccounting(selectedPayment.deal, selectedPayment.id, selectedBank);
            setOpenDialog(false);
            loadData();
            alert("تم ترحيل الدفعة بنجاح");
        } catch (error) {
            alert("خطأ في الترحيل: " + (error.response?.data?.error || error.message));
        }
    };

    const _filteredPayments = payments.filter(p =>
        (p.title || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (p.status || '').toLowerCase().includes(searchTerm.toLowerCase())
    );

    const totalInvoices = payments.length;
    const unpaidInvoices = payments.filter(p => !p.is_posted).length;
    const postedInvoices = payments.filter(p => p.is_posted).length;

    return (
        <Box sx={{ p: 4, bgcolor: '#f1f5f9', minHeight: '100vh', direction: 'rtl' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
                <Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Avatar sx={{ bgcolor: 'secondary.main', width: 56, height: 56 }}>
                            <ReceiptIcon fontSize="large" />
                        </Avatar>
                        <Box>
                            <Typography variant="h4" color="secondary.dark" fontWeight={800}>
                                فواتير الصفقات (Invoices)
                            </Typography>
                            <Typography variant="body1" color="text.secondary">
                                متابعة المطالبات المالية للشركات الموردة وترحيلها للحسابات
                            </Typography>
                        </Box>
                    </Box>
                </Box>
                <Box sx={{ display: 'flex', gap: 2 }}>
                    <Chip label={`إجمالي: ${totalInvoices}`} color="default" sx={{ fontWeight: 'bold' }} />
                    <Chip label={`مرحلة: ${postedInvoices}`} color="primary" sx={{ fontWeight: 'bold' }} />
                    <Chip label={`غير مرحلة: ${unpaidInvoices}`} color="warning" sx={{ fontWeight: 'bold' }} />
                </Box>
            </Box>

            <Paper elevation={0} sx={{ p: 2, mb: 3, borderRadius: 2, display: 'flex', gap: 2, alignItems: 'center' }}>
                <TextField
                    size="small" placeholder="بحث باسم الفاتورة أو الحالة..."
                    value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
                    sx={{ width: 400 }}
                    InputProps={{
                        startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
                    }}
                />
            </Paper>

            {loading ? <LinearProgress color="secondary" sx={{ mb: 3, borderRadius: 1 }} /> : null}

            <TableContainer component={Paper} elevation={0} sx={{ borderRadius: 2 }}>
                <Table>
                    <TableHead>
                        <TableRow sx={{ bgcolor: '#f8fafc' }}>
                            <TableCell sx={{ fontWeight: 'bold', color: '#334155' }}>الصفقة (المرجع)</TableCell>
                            <TableCell sx={{ fontWeight: 'bold', color: '#334155' }}>وصف الدفعة</TableCell>
                            <TableCell sx={{ fontWeight: 'bold', color: '#334155' }}>تاريخ الاستحقاق</TableCell>
                            <TableCell sx={{ fontWeight: 'bold', color: '#334155' }}>المبلغ</TableCell>
                            <TableCell sx={{ fontWeight: 'bold', color: '#334155' }} align="center">الحالة</TableCell>
                            <TableCell sx={{ fontWeight: 'bold', color: '#334155' }} align="center">الإجراءات</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {_filteredPayments.map((pay) => (
                            <TableRow key={pay.id} hover>
                                <TableCell>
                                    <Typography variant="body2" fontWeight="bold">صفقة #{pay.deal}</Typography>
                                </TableCell>
                                <TableCell>{pay.title}</TableCell>
                                <TableCell>
                                    <Chip label={pay.due_date} size="small" variant="outlined" />
                                </TableCell>
                                <TableCell sx={{ fontWeight: 'bold', color: '#0369a1' }}>
                                    $ {parseFloat(pay.amount || 0).toLocaleString()}
                                </TableCell>
                                <TableCell align="center">
                                    <Chip
                                        label={pay.is_posted ? 'مرحلة (Posted)' : pay.status}
                                        size="small"
                                        color={pay.is_posted ? 'primary' : pay.status === 'Paid' || pay.status === 'Confirmed' ? 'success' : pay.status === 'ClaimUploaded' ? 'warning' : 'default'}
                                        sx={{ fontWeight: 'bold' }}
                                    />
                                    {pay.is_posted && pay.journal_id_display && (
                                        <Typography variant="caption" display="block" color="text.secondary" mt={0.5}>
                                            قيد #{pay.journal_id_display}
                                        </Typography>
                                    )}
                                </TableCell>
                                <TableCell align="center">
                                    {pay.is_posted ? (
                                        <Tooltip title="تم الترحيل">
                                            <IconButton disabled color="primary"><CheckCircle /></IconButton>
                                        </Tooltip>
                                    ) : (pay.status === 'Paid' || pay.status === 'Confirmed') ? (
                                        <Button
                                            variant="contained" color="secondary" size="small"
                                            startIcon={<AccountBalanceWallet />}
                                            onClick={() => { setSelectedPayment(pay); setOpenDialog(true); }}
                                        >
                                            ترحيل واعتماد
                                        </Button>
                                    ) : (
                                        <Typography variant="caption" color="text.disabled">لم يتم الدفع</Typography>
                                    )}
                                </TableCell>
                            </TableRow>
                        ))}
                        {_filteredPayments.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                                    لا يوجد فواتير / دفعات مطابقة للبحث
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            {/* Posting Dialog */}
            <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
                <DialogTitle sx={{ bgcolor: 'secondary.main', color: 'white' }}>
                    ترحيل دفعة إلى المحاسبة
                </DialogTitle>
                <DialogContent sx={{ mt: 3, mb: 1 }}>
                    {selectedPayment && (
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                            <Box sx={{ p: 2, bgcolor: '#f0f9ff', borderRadius: 2, border: '1px solid #bae6fd' }}>
                                <Typography variant="subtitle2" color="primary.dark" gutterBottom>تفاصيل الدفعة</Typography>
                                <Typography variant="body2"><strong>البيان:</strong> {selectedPayment.title}</Typography>
                                <Typography variant="body2"><strong>المبلغ:</strong> $ {parseFloat(selectedPayment.amount).toLocaleString()}</Typography>
                                <Typography variant="body2" color="text.secondary" sx={{ mt: 1, fontSize: '0.8rem' }}>
                                    * الترحيل سيقوم بإنشاء قيد محاسبي يخصم هذا المبلغ من حساب البنك المُختار لتقليل رصيد المورد.
                                </Typography>
                            </Box>

                            <TextField
                                select
                                label="حساب البنك / الصندوق (دائن)"
                                fullWidth
                                value={selectedBank}
                                onChange={(e) => setSelectedBank(e.target.value)}
                                helperText="سيتم استخدام البنك الافتراضي إذا ترك فارغاً"
                            >
                                <MenuItem value="">-- البنك الافتراضي --</MenuItem>
                                {accounts.filter(a => a.account_type === 'Asset').map(a => (
                                    <MenuItem key={a.id} value={a.id}>{a.code} - {a.name}</MenuItem>
                                ))}
                            </TextField>
                        </Box>
                    )}
                </DialogContent>
                <DialogActions sx={{ p: 2, bgcolor: '#f8fafc' }}>
                    <Button onClick={() => setOpenDialog(false)}>إلغاء</Button>
                    <Button variant="contained" color="secondary" onClick={handlePostPayment}>
                        تأكيد الترحيل
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default InvoicesPage;
