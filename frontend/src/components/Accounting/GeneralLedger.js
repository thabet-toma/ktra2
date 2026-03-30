import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Grid, TextField, Table, TableBody,
    TableCell, TableContainer, TableHead, TableRow, MenuItem, Autocomplete,
    CircularProgress, Divider, IconButton
} from '@mui/material';
import { Search, Print, AccountBalanceWallet } from '@mui/icons-material';
import accountingService from '../../services/accountingService';

const GeneralLedger = () => {
    // --- State ---
    const [accounts, setAccounts] = useState([]);
    const [loading, setLoading] = useState(false);
    const [reportData, setReportData] = useState(null);

    const [filters, setFilters] = useState({
        account_id: null,
        start_date: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0], // Start of year
        end_date: new Date().toISOString().split('T')[0]
    });

    // --- Init ---
    useEffect(() => {
        loadAccounts();
    }, []);

    const loadAccounts = async () => {
        try {
            const data = await accountingService.getAccounts();
            // Flatten if necessary, but assuming simple list
            setAccounts(data);
        } catch (error) {
            console.error("Failed to load accounts", error);
        }
    };

    // --- Actions ---
    const handleSearch = async () => {
        if (!filters.account_id) {
            alert("الرجاء اختيار الحساب أولاً");
            return;
        }

        setLoading(true);
        try {
            const data = await accountingService.getGeneralLedger({
                account_id: filters.account_id.id,
                start_date: filters.start_date,
                end_date: filters.end_date,
                include_unposted: filters.include_unposted
            });
            setReportData(data);
        } catch (error) {
            console.error("Failed to fetch GL", error);
            alert("فشل في جلب التقرير");
        } finally {
            setLoading(false);
        }
    };

    // --- Render Helpers ---
    const formatCurrency = (val) => {
        if (!val) return '0.00';
        return parseFloat(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    return (
        <Box dir="rtl" sx={{ height: '100vh', display: 'flex', flexDirection: 'column', bgcolor: '#f1f5f9', overflow: 'hidden' }}>

            {/* 1. Header & Filters */}
            <Paper elevation={0} sx={{ p: 2, borderBottom: '1px solid #e2e8f0', zIndex: 10 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                    <AccountBalanceWallet color="primary" />
                    <Typography variant="h6" fontWeight="bold" color="primary.main">الأستاذ العام (General Ledger)</Typography>
                </Box>

                <Grid container spacing={2} alignItems="center">
                    <Grid item xs={12} md={4}>
                        <Autocomplete
                            options={accounts}
                            getOptionLabel={(option) => `${option.code} - ${option.name}`}
                            value={filters.account_id}
                            onChange={(e, newVal) => setFilters({ ...filters, account_id: newVal })}
                            renderInput={(params) => <TextField {...params} label="اختر الحساب (Account)" size="small" variant="outlined" fullWidth />}
                            loading={accounts.length === 0}
                        />
                    </Grid>
                    <Grid item xs={6} md={2}>
                        <TextField
                            label="من تاريخ" type="date" size="small" fullWidth
                            value={filters.start_date} onChange={(e) => setFilters({ ...filters, start_date: e.target.value })}
                            InputLabelProps={{ shrink: true }}
                        />
                    </Grid>
                    <Grid item xs={6} md={2}>
                        <TextField
                            label="إلى تاريخ" type="date" size="small" fullWidth
                            value={filters.end_date} onChange={(e) => setFilters({ ...filters, end_date: e.target.value })}
                            InputLabelProps={{ shrink: true }}
                        />
                    </Grid>
                    <Grid item xs={12} md={2}>
                        <Button
                            variant="contained" fullWidth startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <Search />}
                            onClick={handleSearch} disabled={loading}
                            sx={{ fontWeight: 'bold' }}
                        >
                            عرض التقرير
                        </Button>
                        <Box sx={{ mt: 1 }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.85rem' }}>
                                <input
                                    type="checkbox"
                                    checked={filters.include_unposted || false}
                                    onChange={(e) => setFilters({ ...filters, include_unposted: e.target.checked })}
                                />
                                عرض القيود غير المرحلة (Draft)
                            </label>
                        </Box>
                    </Grid>
                </Grid>
            </Paper>

            {/* 2. Main Report Area */}
            <Box sx={{ flexGrow: 1, overflowY: 'auto', p: 2, display: 'flex', flexDirection: 'column' }}>
                {reportData ? (
                    <Paper sx={{ p: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', flexGrow: 1, border: '1px solid #e2e8f0' }}>

                        {/* Report Header */}
                        <Box sx={{ p: 2, bgcolor: '#f8fafc', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between' }}>
                            <Box>
                                <Typography variant="subtitle2" color="text.secondary">الحساب:</Typography>
                                <Typography variant="body1" fontWeight="bold">{reportData.account_code} - {reportData.account_name}</Typography>
                            </Box>
                            <Box sx={{ textAlign: 'left' }}>
                                <Typography variant="subtitle2" color="text.secondary">الرصيد الافتتاحي:</Typography>
                                <Typography variant="body1" fontWeight="bold" color={reportData.opening_balance >= 0 ? 'success.main' : 'error.main'}>
                                    {formatCurrency(reportData.opening_balance)}
                                </Typography>
                            </Box>
                        </Box>

                        {/* Report Table */}
                        <TableContainer sx={{ flexGrow: 1 }}>
                            <Table stickyHeader size="small" sx={{ '& .MuiTableCell-root': { borderRight: '1px solid #f1f5f9', fontSize: '0.85rem' } }}>
                                <TableHead>
                                    <TableRow>
                                        <TableCell sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold' }}>التاريخ</TableCell>
                                        <TableCell sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold' }}>رقم القيد</TableCell>
                                        <TableCell sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold', minWidth: 300 }}>البيان (Description)</TableCell>
                                        <TableCell align="center" sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold' }}>مدين (Debit)</TableCell>
                                        <TableCell align="center" sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold' }}>دائن (Credit)</TableCell>
                                        <TableCell align="center" sx={{ bgcolor: '#334155', color: '#fff', fontWeight: 'bold' }}>الرصيد (Balance)</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {/* Opening Balance Row */}
                                    <TableRow sx={{ bgcolor: '#fffbed' }}>
                                        <TableCell colSpan={3} sx={{ fontStyle: 'italic', color: 'text.secondary' }}>-- رصيد ما قبل الفترة --</TableCell>
                                        <TableCell align="center">-</TableCell>
                                        <TableCell align="center">-</TableCell>
                                        <TableCell align="center" sx={{ fontWeight: 'bold' }}>{formatCurrency(reportData.opening_balance)}</TableCell>
                                    </TableRow>

                                    {/* Transactions */}
                                    {reportData.transactions.map((row) => (
                                        <TableRow key={row.id} hover sx={{ '&:nth-of-type(even)': { bgcolor: '#f8fafc' } }}>
                                            <TableCell>{row.date}</TableCell>
                                            <TableCell>
                                                <Typography variant="caption" sx={{ bgcolor: '#e2e8f0', px: 0.5, borderRadius: 1 }}>
                                                    {row.ref_type} #{row.ref_id || row.journal_id}
                                                </Typography>
                                            </TableCell>
                                            <TableCell>{row.description}</TableCell>
                                            <TableCell align="center" sx={{ color: row.debit > 0 ? 'text.primary' : 'text.disabled' }}>{row.debit > 0 ? formatCurrency(row.debit) : '-'}</TableCell>
                                            <TableCell align="center" sx={{ color: row.credit > 0 ? 'text.primary' : 'text.disabled' }}>{row.credit > 0 ? formatCurrency(row.credit) : '-'}</TableCell>
                                            <TableCell align="center" sx={{ fontWeight: 'bold', color: row.balance >= 0 ? 'primary.main' : 'error.main', bgcolor: '#f8fafc' }}>
                                                {formatCurrency(row.balance)}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </TableContainer>

                        {/* Report Footer */}
                        <Box sx={{ p: 2, bgcolor: '#1e293b', color: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography variant="body2">عدد الحركات: {reportData.transactions.length}</Typography>
                            <Box sx={{ display: 'flex', gap: 4 }}>
                                <Box>
                                    <Typography variant="caption" display="block" sx={{ opacity: 0.7 }}>إجمالي مدين</Typography>
                                    <Typography variant="h6" fontWeight="bold">
                                        {formatCurrency(reportData.transactions.reduce((sum, r) => sum + Number(r.debit), 0))}
                                    </Typography>
                                </Box>
                                <Box>
                                    <Typography variant="caption" display="block" sx={{ opacity: 0.7 }}>إجمالي دائن</Typography>
                                    <Typography variant="h6" fontWeight="bold">
                                        {formatCurrency(reportData.transactions.reduce((sum, r) => sum + Number(r.credit), 0))}
                                    </Typography>
                                </Box>
                                <Divider orientation="vertical" flexItem sx={{ bgcolor: 'rgba(255,255,255,0.2)' }} />
                                <Box>
                                    <Typography variant="caption" display="block" sx={{ color: '#4ade80' }}>الرصيد الحالي</Typography>
                                    <Typography variant="h5" fontWeight="900" sx={{ color: '#4ade80' }}>
                                        {formatCurrency(reportData.closing_balance)}
                                    </Typography>
                                </Box>
                            </Box>
                        </Box>
                    </Paper>
                ) : (
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flexGrow: 1, opacity: 0.5 }}>
                        <AccountBalanceWallet sx={{ fontSize: 60, mb: 2, color: 'text.disabled' }} />
                        <Typography>قم باختيار حساب واضغط عرض التقرير</Typography>
                    </Box>
                )}
            </Box>
        </Box>
    );
};

export default GeneralLedger;
