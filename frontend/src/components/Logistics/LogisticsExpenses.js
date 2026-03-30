import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Grid, Chip, Dialog,
    DialogTitle, DialogContent, TextField, DialogActions,
    MenuItem, LinearProgress, Avatar
} from '@mui/material';
import {
    Add as AddIcon, AttachMoney as MoneyIcon, Receipt as ReceiptIcon,
    AccountBalanceWallet, Description
} from '@mui/icons-material';
import logisticsService from '../../services/logisticsService';
import accountingService from '../../services/accountingService';

const LogisticsExpenses = () => {
    const [expenses, setExpenses] = useState([]);

    // Lookups
    const [partners, setPartners] = useState([]);
    const [accounts, setAccounts] = useState([]);
    const [deals, setDeals] = useState([]);
    const [shipments, setShipments] = useState([]);
    const [clearances, setClearances] = useState([]);

    const [openDialog, setOpenDialog] = useState(false);
    const [currentExpense, setCurrentExpense] = useState(getEmptyExpense());
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [expData, partData, accData, dealsData, shipData, clearData] = await Promise.all([
                logisticsService.getExpenses(),
                accountingService.getPartners(),
                accountingService.getChartOfAccounts(),
                logisticsService.getDeals(),
                logisticsService.getShipments(),
                logisticsService.getClearances()
            ]);
            setExpenses(expData);
            setPartners(partData);
            setAccounts(accData);
            setDeals(dealsData);
            setShipments(shipData);
            setClearances(clearData);
        } catch (error) {
            console.error("Error loading expense data", error);
        } finally {
            setLoading(false);
        }
    };

    function getEmptyExpense() {
        return {
            related_type: 'Shipment',
            related_id: '',
            expense_account: '',
            payable_account: '',
            description: '',
            amount: 0,
            currency: 1,
            invoice_number: '',
            invoice_date: new Date().toISOString().split('T')[0],
            is_posted: false
        };
    }

    const handleSave = async () => {
        try {
            const newExpense = await logisticsService.createExpense(currentExpense);
            if (newExpense.id) {
                await logisticsService.postExpenseToAccounting(newExpense.id);
            }
            setOpenDialog(false);
            loadData();
            // alert("Expense Saved & Posted to Journal Successfully!");
        } catch (error) {
            alert("Error saving/posting expense: " + error.message);
        }
    };

    const getRelatedOptions = () => {
        switch (currentExpense.related_type) {
            case 'Deal': return deals.map(d => ({ id: d.id, label: `صفقة #${d.ref_number}` }));
            case 'Shipment': return shipments.map(s => ({ id: s.id, label: `شحنة #${s.shipment_number}` }));
            case 'Clearance': return clearances.map(c => ({ id: c.id, label: `بيان #${c.declaration_number}` }));
            default: return [];
        }
    };

    return (
        <Box>
            {/* Header Section */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
                <Box>
                    <Typography variant="h4" color="success.main" gutterBottom>
                        المصاريف والقيود المالية
                    </Typography>
                    <Typography variant="body1" color="text.secondary">
                        متابعة المصاريف اللوجستية والتوجيه المحاسبي الآلي
                    </Typography>
                </Box>
                <Button
                    variant="contained"
                    color="success"
                    size="large"
                    startIcon={<AddIcon />}
                    onClick={() => { setCurrentExpense(getEmptyExpense()); setOpenDialog(true); }}
                >
                    تسجيل مصروف جديد
                </Button>
            </Box>

            {loading && <LinearProgress color="success" sx={{ mb: 3, borderRadius: 1 }} />}

            <Grid container spacing={3}>
                {expenses.map((expense) => (
                    <Grid item xs={12} key={expense.id}>
                        <Paper
                            sx={{
                                p: 2,
                                borderRadius: 3,
                                borderLeft: '6px solid',
                                borderLeftColor: 'success.main',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                transition: 'all 0.2s',
                                '&:hover': { boxShadow: 4, transform: 'translateX(-4px)' }
                            }}
                        >
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                <Avatar sx={{ bgcolor: 'success.light', color: 'success.dark' }}>
                                    <AccountBalanceWallet />
                                </Avatar>
                                <Box>
                                    <Typography variant="h6" fontWeight="bold">
                                        {expense.description}
                                    </Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        المرجع: {expense.related_type} #{expense.related_id} | فاتورة رقم: {expense.invoice_number}
                                    </Typography>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                                        <Chip label={`مدين: ${expense.expense_account_name}`} size="small" variant="outlined" />
                                        <Typography variant="caption">➔</Typography>
                                        <Chip label={`دائن: ${expense.payable_account_name}`} size="small" variant="outlined" />
                                    </Box>
                                </Box>
                            </Box>

                            <Box sx={{ textAlign: 'right', minWidth: 150 }}>
                                <Typography variant="h5" fontWeight="bold" color="success.dark">
                                    {parseFloat(expense.amount).toFixed(2)} <span style={{ fontSize: '0.6em' }}>₪</span>
                                </Typography>
                                {expense.is_posted ? (
                                    <Chip label="تم الترحيل (Posted)" color="success" size="small" icon={<ReceiptIcon />} sx={{ mt: 1 }} />
                                ) : (
                                    <Chip label="مسودة (Draft)" size="small" sx={{ mt: 1 }} />
                                )}
                            </Box>
                        </Paper>
                    </Grid>
                ))}
            </Grid>

            {/* Dialog */}
            <Dialog
                open={openDialog}
                onClose={() => setOpenDialog(false)}
                maxWidth="md"
                fullWidth
                PaperProps={{ sx: { borderRadius: 3 } }}
            >
                <DialogTitle sx={{ bgcolor: 'success.main', color: 'white', py: 2 }}>
                    تسجيل سند استحقاق (مصروف)
                </DialogTitle>
                <DialogContent sx={{ mt: 2 }}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, pt: 1 }}>
                        <Grid container spacing={3}>
                            <Grid item xs={12} md={6}>
                                <TextField
                                    select
                                    label="نوع المصروف مرتبط بـ"
                                    fullWidth
                                    value={currentExpense.related_type}
                                    onChange={(e) => setCurrentExpense({ ...currentExpense, related_type: e.target.value, related_id: '' })}
                                >
                                    <MenuItem value="Deal">صفقة (Deal)</MenuItem>
                                    <MenuItem value="Shipment">شحنة (Shipment)</MenuItem>
                                    <MenuItem value="Clearance">تخليص (Clearance)</MenuItem>
                                </TextField>
                            </Grid>
                            <Grid item xs={12} md={6}>
                                <TextField
                                    select
                                    label="اختار السجل المرتبط"
                                    fullWidth
                                    value={currentExpense.related_id}
                                    onChange={(e) => setCurrentExpense({ ...currentExpense, related_id: e.target.value })}
                                >
                                    {getRelatedOptions().map(opt => (
                                        <MenuItem key={opt.id} value={opt.id}>{opt.label}</MenuItem>
                                    ))}
                                </TextField>
                            </Grid>
                        </Grid>

                        <TextField
                            label="وصف المصروف (البيان)"
                            fullWidth
                            InputProps={{
                                startAdornment: <Description color="action" sx={{ mr: 1 }} />,
                            }}
                            value={currentExpense.description}
                            onChange={(e) => setCurrentExpense({ ...currentExpense, description: e.target.value })}
                        />

                        <Grid container spacing={3}>
                            <Grid item xs={6}>
                                <TextField
                                    type="number"
                                    label="المبلغ"
                                    fullWidth
                                    value={currentExpense.amount}
                                    onChange={(e) => setCurrentExpense({ ...currentExpense, amount: e.target.value })}
                                />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField
                                    label="رقم الفاتورة"
                                    fullWidth
                                    value={currentExpense.invoice_number}
                                    onChange={(e) => setCurrentExpense({ ...currentExpense, invoice_number: e.target.value })}
                                />
                            </Grid>
                        </Grid>

                        <Paper variant="outlined" sx={{ p: 2, bgcolor: 'success.50', borderColor: 'success.200' }}>
                            <Typography variant="subtitle2" color="success.dark" gutterBottom fontWeight="bold">التوجيه المحاسبي (GL Posting)</Typography>
                            <Grid container spacing={2}>
                                <Grid item xs={6}>
                                    <TextField
                                        select
                                        label="حساب المصروف (مدين)"
                                        fullWidth
                                        helperText="Debit Account"
                                        size="small"
                                        value={currentExpense.expense_account}
                                        onChange={(e) => setCurrentExpense({ ...currentExpense, expense_account: e.target.value })}
                                    >
                                        {accounts.filter(a => a.account_type === 'Expense' || a.account_type === 'Asset').map(a => (
                                            <MenuItem key={a.id} value={a.id}>{a.code} - {a.name}</MenuItem>
                                        ))}
                                    </TextField>
                                </Grid>
                                <Grid item xs={6}>
                                    <TextField
                                        select
                                        label="حساب الالتزام (دائن)"
                                        fullWidth
                                        helperText="Credit Account"
                                        size="small"
                                        value={currentExpense.payable_account}
                                        onChange={(e) => setCurrentExpense({ ...currentExpense, payable_account: e.target.value })}
                                    >
                                        {accounts.filter(a => a.account_type === 'Liability' || a.account_type === 'Asset').map(a => (
                                            <MenuItem key={a.id} value={a.id}>{a.code} - {a.name}</MenuItem>
                                        ))}
                                    </TextField>
                                </Grid>
                            </Grid>
                        </Paper>
                    </Box>
                </DialogContent>
                <DialogActions sx={{ p: 3, bgcolor: '#f5f5f5' }}>
                    <Button onClick={() => setOpenDialog(false)} size="large">إلغاء</Button>
                    <Button variant="contained" color="success" onClick={handleSave} size="large" sx={{ px: 4 }}>حفظ وترحيل</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default LogisticsExpenses;
