import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Grid, TextField, Table, TableBody,
    TableCell, TableContainer, TableHead, TableRow, CircularProgress, Divider, Checkbox, FormControlLabel
} from '@mui/material';
import { Search, AccountBalance, Print } from '@mui/icons-material';
import accountingService from '../../services/accountingService';

const TrialBalance = () => {
    // --- State ---
    const [loading, setLoading] = useState(false);
    const [reportData, setReportData] = useState([]);

    const [filters, setFilters] = useState({
        start_date: new Date(new Date().getFullYear(), 0, 1).toISOString().split('T')[0],
        end_date: new Date().toISOString().split('T')[0],
        include_unposted: false
    });

    // --- Actions ---
    const handleSearch = async () => {
        setLoading(true);
        try {
            const data = await accountingService.getTrialBalance(filters);
            setReportData(data);
        } catch (error) {
            console.error("Failed to fetch Trial Balance", error);
            alert("فشل في جلب ميزان المراجعة");
        } finally {
            setLoading(false);
        }
    };

    // Auto-load on mount
    useEffect(() => {
        handleSearch();
    }, []);

    // --- Helpers ---
    const formatCurrency = (val) => {
        if (val === null || val === undefined) return '-';
        return parseFloat(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    // Calculate Totals
    const totalDebit = reportData.reduce((sum, row) => sum + Number(row.total_debit), 0);
    const totalCredit = reportData.reduce((sum, row) => sum + Number(row.total_credit), 0);
    const balanceDiff = totalDebit - totalCredit;

    return (
        <Box dir="rtl" sx={{ height: '100vh', display: 'flex', flexDirection: 'column', bgcolor: '#f1f5f9', overflow: 'hidden' }}>

            {/* 1. Header & Filters */}
            <Paper elevation={0} sx={{ p: 2, borderBottom: '1px solid #e2e8f0', zIndex: 10 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                    <AccountBalance color="primary" sx={{ fontSize: 32 }} />
                    <Box>
                        <Typography variant="h6" fontWeight="bold" color="primary.main">ميزان المراجعة (Trial Balance)</Typography>
                        <Typography variant="caption" color="text.secondary">تقرير أرصدة الحسابات الإجمالي</Typography>
                    </Box>
                </Box>

                <Grid container spacing={2} alignItems="center">
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
                    <Grid item xs={12} md={3}>
                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={filters.include_unposted}
                                    onChange={(e) => setFilters({ ...filters, include_unposted: e.target.checked })}
                                />
                            }
                            label="عرض القيود غير المرحلة"
                        />
                    </Grid>
                    <Grid item xs={12} md={2}>
                        <Button
                            variant="contained" fullWidth startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <Search />}
                            onClick={handleSearch} disabled={loading}
                            sx={{ fontWeight: 'bold' }}
                        >
                            تحديث التقرير
                        </Button>
                    </Grid>
                </Grid>
            </Paper>

            {/* 2. Main Report Area */}
            <Box sx={{ flexGrow: 1, overflowY: 'auto', p: 2, display: 'flex', flexDirection: 'column' }}>
                <Paper sx={{ p: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', flexGrow: 1, border: '1px solid #e2e8f0' }}>

                    {/* Table Header */}
                    <TableContainer sx={{ flexGrow: 1 }}>
                        <Table stickyHeader size="small" sx={{
                            '& .MuiTableCell-root': { borderRight: '1px solid #e2e8f0', fontSize: '0.85rem', py: 0.75 },
                            '& .MuiTableRow-root:hover': { bgcolor: '#f8fafc' }
                        }}>
                            <TableHead>
                                <TableRow>
                                    <TableCell sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold', width: '100px' }}>الرمز</TableCell>
                                    <TableCell sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold' }}>اسم الحساب</TableCell>
                                    <TableCell align="center" sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold', width: '150px' }}>مجموع مدين</TableCell>
                                    <TableCell align="center" sx={{ bgcolor: '#1e293b', color: '#fff', fontWeight: 'bold', width: '150px' }}>مجموع دائن</TableCell>
                                    <TableCell align="center" sx={{ bgcolor: '#334155', color: '#fff', fontWeight: 'bold', width: '150px' }}>الرصيد</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {reportData.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={5} align="center" sx={{ py: 10, color: 'text.secondary' }}>
                                            لا توجد بيانات للعرض في هذه الفترة
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    reportData.map((row) => (
                                        <TableRow key={row.id}>
                                            <TableCell sx={{ fontFamily: 'monospace', fontWeight: 'bold', color: 'primary.main' }}>
                                                {row.code || '-'}
                                            </TableCell>
                                            <TableCell>{row.name}</TableCell>
                                            <TableCell align="center" sx={{ color: row.total_debit > 0 ? 'text.primary' : 'text.disabled' }}>
                                                {formatCurrency(row.total_debit)}
                                            </TableCell>
                                            <TableCell align="center" sx={{ color: row.total_credit > 0 ? 'text.primary' : 'text.disabled' }}>
                                                {formatCurrency(row.total_credit)}
                                            </TableCell>
                                            <TableCell align="center" sx={{
                                                fontWeight: 'bold',
                                                color: row.balance > 0 ? 'primary.main' : (row.balance < 0 ? 'error.main' : 'text.secondary'),
                                                bgcolor: '#f8fafc'
                                            }}>
                                                {formatCurrency(Math.abs(row.balance))} {row.balance > 0 ? '(Dr)' : (row.balance < 0 ? '(Cr)' : '-')}
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>

                    {/* Footer Totals */}
                    <Box sx={{ p: 1.5, bgcolor: '#1e293b', color: 'white', borderTop: '4px solid #475569' }}>
                        <Grid container spacing={2} alignItems="center">
                            <Grid item xs={12} md={3}>
                                <Typography variant="caption" sx={{ opacity: 0.7 }}>عدد الحسابات</Typography>
                                <Typography variant="h6" fontWeight="bold">{reportData.length}</Typography>
                            </Grid>
                            <Grid item xs={12} md={3}>
                                <Typography variant="caption" sx={{ opacity: 0.7 }}>إجمالي مدين</Typography>
                                <Typography variant="h6" fontWeight="bold" color="#4ade80">{formatCurrency(totalDebit)}</Typography>
                            </Grid>
                            <Grid item xs={12} md={3}>
                                <Typography variant="caption" sx={{ opacity: 0.7 }}>إجمالي دائن</Typography>
                                <Typography variant="h6" fontWeight="bold" color="#4ade80">{formatCurrency(totalCredit)}</Typography>
                            </Grid>
                            <Grid item xs={12} md={3} sx={{ textAlign: 'left' }}>
                                <Typography variant="caption" sx={{ opacity: 0.7 }}>الفرق (Balancing)</Typography>
                                <Typography variant="h6" fontWeight="bold" color={Math.abs(balanceDiff) < 0.01 ? '#4ade80' : 'error.main'}>
                                    {formatCurrency(balanceDiff)}
                                </Typography>
                            </Grid>
                        </Grid>
                    </Box>
                </Paper>
            </Box>
        </Box>
    );
};

export default TrialBalance;
