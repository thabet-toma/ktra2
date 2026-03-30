import React, { useState, useEffect, useRef } from 'react';
import {
    Box, Typography, Paper, Button, TextField, Table, TableBody,
    TableCell, TableContainer, TableHead, TableRow, TableFooter,
    IconButton, MenuItem, Alert, Grid, Autocomplete, CircularProgress,
    Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle
} from '@mui/material';
import {
    Add as AddIcon, Delete as DeleteIcon, Save as SaveIcon,
    ArrowBack as BackIcon, CheckCircle as PostedIcon,
    Print as PrintIcon, Unpublished as DraftIcon
} from '@mui/icons-material';
import accountingService from '../../services/accountingService';
import { useNavigate, useParams } from 'react-router-dom';

const JournalEntry = () => {
    const { id } = useParams();
    const navigate = useNavigate();

    // --- Data Sources ---
    const [accounts, setAccounts] = useState([]);
    const [partners, setPartners] = useState([]);
    const [costCenters, setCostCenters] = useState([]);

    // --- UI State ---
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [confirmPostOpen, setConfirmPostOpen] = useState(false);

    // --- Form State ---
    const [header, setHeader] = useState({
        transaction_date: new Date().toISOString().split('T')[0],
        description: '',
        is_posted: false,
        reference_type: '',
        reference_id: ''
    });

    // Initial strict rows (Al-Aseel style usually starts with empty rows)
    const [lines, setLines] = useState([
        { account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' },
        { account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' },
        { account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' },
        { account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' },
        { account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' }
    ]);

    // --- Init ---
    useEffect(() => {
        loadInitialData();
    }, [id]);

    const loadInitialData = async () => {
        setLoading(true);
        try {
            // Load lookups safely
            const safeLoad = async (promise, fallback = []) => {
                try { return await promise; } catch (e) { console.warn(e); return fallback; }
            };

            const [accRes, partRes, costRes] = await Promise.all([
                safeLoad(accountingService.getAccounts()),
                safeLoad(accountingService.getPartners()),
                safeLoad(accountingService.getCostCenters())
            ]);

            setAccounts(accRes.filter(a => a.is_active));
            setPartners(partRes);
            setCostCenters(costRes);

            if (id) {
                const journal = await accountingService.getJournal(id);
                setHeader({
                    transaction_date: journal.transaction_date,
                    description: journal.description || '',
                    is_posted: journal.is_posted,
                    reference_type: journal.reference_type,
                    reference_id: journal.reference_id
                });

                // Map existing lines
                const mappedLines = journal.lines.map(line => ({
                    id: line.id,
                    account: accRes.find(a => a.id === line.account) || null,
                    description: line.description || '', // If individual line desc exists
                    cost_center: line.cost_center || '',
                    partner: partRes.find(p => p.id === line.partner) || null,
                    debit: parseFloat(line.debit) || '',
                    credit: parseFloat(line.credit) || ''
                }));

                // Ensure at least 5 rows for aesthetics
                while (mappedLines.length < 5) {
                    mappedLines.push({ account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' });
                }
                setLines(mappedLines);
            }
        } catch (err) {
            setError("فشل في تحميل البيانات. يرجى تحديث الصفحة.");
        } finally {
            setLoading(false);
        }
    };

    // --- Line Management ---
    const handleLineChange = (index, field, value) => {
        if (header.is_posted) return;
        const newLines = [...lines];

        // Auto-balance logic (Clear opposite field if value > 0)
        if (field === 'debit' && value > 0) newLines[index].credit = 0;
        if (field === 'credit' && value > 0) newLines[index].debit = 0;

        // If selecting account, auto-fill description if empty
        if (field === 'account' && value && !newLines[index].description) {
            newLines[index].description = header.description; // Default to header desc styling
        }

        newLines[index][field] = value;
        setLines(newLines);

        // Auto-add row if typing in last row
        if (index === lines.length - 1 && value) {
            setLines([...newLines, { account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' }]);
        }
    };

    const removeLine = (index) => {
        if (header.is_posted) return;
        const newLines = lines.filter((_, i) => i !== index);
        setLines(newLines.length ? newLines : [{ account: null, description: '', cost_center: '', partner: null, debit: '', credit: '' }]);
    };

    // --- Calculations ---
    const totalDebit = lines.reduce((sum, line) => sum + (parseFloat(line.debit) || 0), 0);
    const totalCredit = lines.reduce((sum, line) => sum + (parseFloat(line.credit) || 0), 0);
    const difference = totalDebit - totalCredit;
    const isBalanced = Math.abs(difference) < 0.01 && totalDebit > 0;

    // --- Actions ---
    const validate = () => {
        if (!header.transaction_date) return "التاريخ مطلوب";
        if (!header.description) return "شرح القيد (البيان) مطلوب";

        const validLines = lines.filter(l => l.account && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0));
        if (validLines.length < 2) return "يجب إدخال طرفين للقيد على الأقل";

        if (!isBalanced) return `القيد غير متوازن. الفرق: ${difference.toFixed(2)}`;
        return null;
    };

    const handleSave = async (shouldPost = false) => {
        const err = validate();
        if (err) { setError(err); return; }

        setSaving(true);
        setError(null);

        try {
            // Filter empty lines
            const activeLines = lines.filter(l => l.account && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0));

            const payload = {
                ...header,
                is_posted: header.is_posted, // Don't force post here, do it in separate call
                lines: activeLines.map(l => ({
                    account: l.account.id,
                    partner: l.partner ? l.partner.id : null,
                    cost_center: l.cost_center || null,
                    debit: parseFloat(l.debit) || 0,
                    credit: parseFloat(l.credit) || 0,
                    description: l.description || header.description
                }))
            };

            let savedId = id;
            if (id) {
                await accountingService.updateJournal(id, payload);
            } else {
                const res = await accountingService.createJournal(payload);
                savedId = res.id;
            }

            if (shouldPost) {
                try {
                    await accountingService.postJournal(savedId);
                    // Only navigate if both save AND post succeed
                    navigate('/accounting/journals');
                } catch (postErr) {
                    // If post fails, we stay on page and tell user
                    console.error("Post Error", postErr);
                    setSaving(false);
                    setError(postErr.response?.data?.error || "تم الحفظ، ولكن فشل الترحيل. يرجى المراجعة.");
                    // Update URL to the new ID so they don't create dupes if they click again
                    if (!id && savedId) {
                        navigate(`/accounting/journals/${savedId}`, { replace: true });
                    }
                }
            } else {
                navigate('/accounting/journals');
            }
        } catch (saveErr) {
            console.error("Save Error", saveErr);
            setError(saveErr.response?.data?.error || "حدث خطأ أثناء حفظ القيد");
            setSaving(false);
        }
    };

    // --- Render Helpers ---
    // Custom table cell for tight "Excel-like" feel
    const DenseCell = ({ children, width, align = 'left', bg = 'white' }) => (
        <TableCell
            sx={{
                p: '2px 4px',
                width,
                borderRight: '1px solid #e0e0e0',
                bgcolor: bg,
                '& .MuiInputBase-input': { fontSize: '0.85rem', p: 0.5 }
            }}
            align={align}
        >
            {children}
        </TableCell>
    );

    if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', mt: 10 }}><CircularProgress /></Box>;

    return (
        <Box dir="rtl" sx={{ p: 2, bgcolor: '#f1f5f9', minHeight: '100vh' }}>
            {/* Header / Toolbar */}
            <Paper elevation={0} sx={{ p: 1.5, mb: 1, border: '1px solid #cbd5e1', display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#1e293b', color: 'white' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <Typography variant="h6" fontWeight="bold">
                        {id ? `قيد يومية #${id}` : 'قيد يومية جديد'}
                    </Typography>
                    {header.is_posted ?
                        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', bgcolor: '#22c55e', color: 'white', px: 1, borderRadius: 1 }}>
                            <PostedIcon fontSize="small" /> <Typography variant="caption" fontWeight="bold">مرحّل</Typography>
                        </Box>
                        :
                        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', bgcolor: '#f59e0b', color: 'black', px: 1, borderRadius: 1 }}>
                            <DraftIcon fontSize="small" /> <Typography variant="caption" fontWeight="bold">مسودة</Typography>
                        </Box>
                    }
                </Box>

                <Box sx={{ display: 'flex', gap: 1 }}>
                    <Button size="small" variant="outlined" color="inherit" onClick={() => navigate('/accounting/journals')} startIcon={<BackIcon />}>خروج</Button>
                    {!header.is_posted && (
                        <>
                            <Button
                                size="small" variant="contained" color="info" startIcon={<SaveIcon />}
                                onClick={() => handleSave(false)} disabled={saving}
                            >
                                حفظ (F10)
                            </Button>
                            <Button
                                size="small" variant="contained" color="success" startIcon={<PostedIcon />}
                                onClick={() => setConfirmPostOpen(true)} disabled={saving || !isBalanced}
                            >
                                ترحيل (Post)
                            </Button>
                        </>
                    )}
                    <IconButton size="small" sx={{ color: 'white' }}><PrintIcon /></IconButton>
                </Box>
            </Paper>

            {/* Error Banner */}
            {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 1 }}>{error}</Alert>}

            {/* Master Data Inputs */}
            <Paper sx={{ p: 2, mb: 1, borderRadius: 1, bgcolor: '#fff' }}>
                <Grid container spacing={2}>
                    <Grid item xs={2}>
                        <TextField
                            label="التاريخ" type="date" fullWidth size="small" variant="outlined"
                            value={header.transaction_date} onChange={(e) => setHeader({ ...header, transaction_date: e.target.value })}
                            InputLabelProps={{ shrink: true }} disabled={header.is_posted}
                            sx={{ '& .MuiInputBase-input': { fontWeight: 'bold' } }}
                        />
                    </Grid>
                    <Grid item xs={1}>
                        <TextField
                            label="المرجع" fullWidth size="small" variant="outlined"
                            value={header.reference_id} onChange={(e) => setHeader({ ...header, reference_id: e.target.value })}
                            disabled={header.is_posted}
                        />
                    </Grid>
                    <Grid item xs={5}>
                        <TextField
                            label="شرح القيد (البيان العام)" fullWidth size="small" variant="outlined"
                            value={header.description} onChange={(e) => setHeader({ ...header, description: e.target.value })}
                            disabled={header.is_posted} placeholder="مثال: سداد دفعة للمورد..."
                        />
                    </Grid>
                    <Grid item xs={4}>
                        <Box sx={{ p: 1, bgcolor: isBalanced ? '#dcfce7' : '#fee2e2', borderRadius: 1, border: '1px solid', borderColor: isBalanced ? 'green' : 'red', textAlign: 'center' }}>
                            <Typography variant="body2" fontWeight="bold" color={isBalanced ? 'success.main' : 'error.main'}>
                                {isBalanced ? 'القيد متوازن' : `غير متوازن (الفرق: ${difference.toFixed(2)})`}
                            </Typography>
                        </Box>
                    </Grid>
                </Grid>
            </Paper>

            {/* High Density Grid Area */}
            <TableContainer component={Paper} sx={{ borderRadius: 1, border: '1px solid #cbd5e1', maxHeight: '65vh', overflowY: 'auto' }}>
                <Table stickyHeader size="small">
                    <TableHead>
                        <TableRow sx={{ height: 35 }}>
                            <TableCell sx={{ bgcolor: '#e2e8f0', fontWeight: 'bold', borderRight: '1px solid #cbd5e1', width: 40 }} align="center">#</TableCell>
                            <TableCell sx={{ bgcolor: '#e2e8f0', fontWeight: 'bold', borderRight: '1px solid #cbd5e1', color: '#0f172a' }} width="12%" align="center">مدين (Debit)</TableCell>
                            <TableCell sx={{ bgcolor: '#e2e8f0', fontWeight: 'bold', borderRight: '1px solid #cbd5e1', color: '#0f172a' }} width="12%" align="center">دائن (Credit)</TableCell>
                            <TableCell sx={{ bgcolor: '#e2e8f0', fontWeight: 'bold', borderRight: '1px solid #cbd5e1' }} width="25%">الحساب (Account)</TableCell>
                            <TableCell sx={{ bgcolor: '#e2e8f0', fontWeight: 'bold', borderRight: '1px solid #cbd5e1' }}>البيان (Description)</TableCell>
                            <TableCell sx={{ bgcolor: '#e2e8f0', fontWeight: 'bold', borderRight: '1px solid #cbd5e1' }} width="12%">م. تكلفة</TableCell>
                            <TableCell sx={{ bgcolor: '#e2e8f0', fontWeight: 'bold', borderRight: '1px solid #cbd5e1' }} width="15%">شريك (Partner)</TableCell>
                            <TableCell sx={{ bgcolor: '#e2e8f0', width: 40 }}></TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {lines.map((line, index) => (
                            <TableRow key={index} sx={{ height: 32, '&:hover': { bgcolor: '#f8fafc' } }}>
                                <TableCell align="center" sx={{ color: 'text.secondary', borderRight: '1px solid #e0e0e0' }}>{index + 1}</TableCell>

                                {/* 1. Debit */}
                                <DenseCell width="12%" bg="#f0fdf4">
                                    <TextField
                                        fullWidth variant="standard" type="number"
                                        InputProps={{ disableUnderline: true, style: { textAlign: 'center', fontWeight: 'bold' } }}
                                        value={line.debit} onChange={(e) => handleLineChange(index, 'debit', e.target.value)}
                                        disabled={header.is_posted} placeholder="0.00"
                                    />
                                </DenseCell>

                                {/* 2. Credit */}
                                <DenseCell width="12%" bg="#fef2f2">
                                    <TextField
                                        fullWidth variant="standard" type="number"
                                        InputProps={{ disableUnderline: true, style: { textAlign: 'center', fontWeight: 'bold' } }}
                                        value={line.credit} onChange={(e) => handleLineChange(index, 'credit', e.target.value)}
                                        disabled={header.is_posted} placeholder="0.00"
                                    />
                                </DenseCell>

                                {/* 3. Account */}
                                <DenseCell width="25%">
                                    <Autocomplete
                                        options={accounts}
                                        getOptionLabel={(opt) => `${opt.code} - ${opt.name}`}
                                        value={line.account}
                                        onChange={(_, val) => handleLineChange(index, 'account', val)}
                                        disabled={header.is_posted}
                                        renderInput={(params) => <TextField {...params} variant="standard" placeholder="ابحث عن حساب..." InputProps={{ ...params.InputProps, disableUnderline: true }} />}
                                        size="small"
                                        fullWidth
                                    />
                                </DenseCell>

                                {/* 4. Description */}
                                <DenseCell>
                                    <TextField
                                        fullWidth variant="standard"
                                        InputProps={{ disableUnderline: true }}
                                        value={line.description || header.description}
                                        // Usually line desc defaults to header desc if empty in display
                                        // But here we allow explicit override.
                                        // Simulating Al-Aseel: If user types, it overrides. 
                                        onChange={(e) => {
                                            const newLines = [...lines];
                                            newLines[index].description = e.target.value;
                                            setLines(newLines);
                                        }}
                                        disabled={header.is_posted}
                                    />
                                </DenseCell>

                                {/* 5. Cost Center */}
                                <DenseCell width="12%">
                                    <TextField
                                        select fullWidth variant="standard"
                                        InputProps={{ disableUnderline: true }}
                                        value={line.cost_center} onChange={(e) => handleLineChange(index, 'cost_center', e.target.value)}
                                        disabled={header.is_posted}
                                    >
                                        <MenuItem value=""><em>-</em></MenuItem>
                                        {costCenters.map(c => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}
                                    </TextField>
                                </DenseCell>

                                {/* 6. Partner */}
                                <DenseCell width="15%">
                                    <Autocomplete
                                        options={partners}
                                        getOptionLabel={(opt) => opt.name}
                                        value={line.partner}
                                        onChange={(_, val) => handleLineChange(index, 'partner', val)}
                                        disabled={header.is_posted}
                                        renderInput={(params) => <TextField {...params} variant="standard" placeholder="" InputProps={{ ...params.InputProps, disableUnderline: true }} />}
                                        size="small"
                                    />
                                </DenseCell>

                                <TableCell align="center" sx={{ borderRight: '1px solid #e0e0e0', p: 0 }}>
                                    {!header.is_posted && (
                                        <IconButton size="small" tabIndex={-1} color="error" onClick={() => removeLine(index)}>
                                            <DeleteIcon fontSize="small" />
                                        </IconButton>
                                    )}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>

                    {/* Totals Footer */}
                    <TableFooter sx={{ position: 'sticky', bottom: 0, bgcolor: '#1e293b', zIndex: 5 }}>
                        <TableRow>
                            <TableCell sx={{ color: 'white', fontWeight: 'bold', borderTop: '2px solid #334155' }} colSpan={1} align="center">الإجمالي</TableCell>
                            <TableCell sx={{ color: 'white', fontWeight: 'bold', borderTop: '2px solid #334155', bgcolor: '#334155' }} align="center">{totalDebit.toFixed(2)}</TableCell>
                            <TableCell sx={{ color: 'white', fontWeight: 'bold', borderTop: '2px solid #334155', bgcolor: '#334155' }} align="center">{totalCredit.toFixed(2)}</TableCell>
                            <TableCell colSpan={5} sx={{ color: '#94a3b8', borderTop: '2px solid #334155' }}>
                                {isBalanced ?
                                    <Typography variant="caption" sx={{ color: '#4ade80' }}>✔ القيد متوازن وجاهز للحفظ</Typography>
                                    :
                                    <Typography variant="caption" sx={{ color: '#f87171' }}>⚠ يوجد فرق: {Math.abs(difference).toFixed(2)}</Typography>
                                }
                            </TableCell>
                        </TableRow>
                    </TableFooter>
                </Table>
            </TableContainer>

            {/* Confirm Dialog */}
            <Dialog open={confirmPostOpen} onClose={() => setConfirmPostOpen(false)}>
                <DialogTitle>تأكيد ترحيل القيد</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        هل أنت متأكد من ترحيل القيد؟ <br />
                        <b>لا يمكن تعديل القيد أو حذفه بعد الترحيل.</b>
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setConfirmPostOpen(false)}>إلغاء</Button>
                    <Button onClick={() => { setConfirmPostOpen(false); handleSave(true); }} variant="contained" color="success" autoFocus>
                        تأكيد وترحيل
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default JournalEntry;
