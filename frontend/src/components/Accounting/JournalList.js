import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Table, TableBody, TableCell,
    TableContainer, TableHead, TableRow, Chip, IconButton, TextField,
    InputAdornment, Tooltip, useTheme, CircularProgress
} from '@mui/material';
import {
    Add as AddIcon, Search, Visibility as ViewIcon,
    CheckCircle as PostIcon, Delete as DeleteIcon,
    AccountBalance, FilterList, HistoryEdu,
    Download as DownloadIcon, Print as PrintIcon
} from '@mui/icons-material';
import accountingService from '../../services/accountingService';
import { useNavigate } from 'react-router-dom';

const JournalList = () => {
    const theme = useTheme();
    const navigate = useNavigate();
    const [journals, setJournals] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        fetchJournals();
    }, []);

    const fetchJournals = async () => {
        try {
            const data = await accountingService.getJournals();
            // Sort by ID desc
            setJournals(data.sort((a, b) => b.id - a.id));
        } catch (error) {
            console.error('Error fetching journals:', error);
        }
    };

    const [loadingIds, setLoadingIds] = useState([]);

    const handlePost = async (id) => {
        if (!window.confirm('هل أنت متأكد من ترحيل القيد؟ لا يمكن التعديل بعد الترحيل.')) return;

        setLoadingIds(prev => [...prev, id]);
        try {
            await accountingService.postJournal(id);
            setJournals(prev => prev.map(j => j.id === id ? { ...j, is_posted: true } : j));
            alert("تم ترحيل القيد بنجاح");
        } catch (error) {
            console.error("Posting error", error);
            alert(error.response?.data?.error || 'حدث خطأ أثناء الترحيل. يرجى مراجعة الخادم.');
        } finally {
            setLoadingIds(prev => prev.filter(lid => lid !== id));
        }
    };

    const filteredJournals = journals.filter(j =>
        (j.description && j.description.toLowerCase().includes(searchTerm.toLowerCase())) ||
        j.id.toString().includes(searchTerm) ||
        (j.reference_id && j.reference_id.toString().includes(searchTerm))
    );

    return (
        <Box dir="rtl" sx={{ height: '100vh', display: 'flex', flexDirection: 'column', bgcolor: '#f1f5f9' }}>
            {/* 1. Header Bar (Dark Professional) */}
            <Paper elevation={0} sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#1e293b', color: 'white', borderRadius: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <AccountBalance sx={{ fontSize: 28, color: '#94a3b8' }} />
                    <Box>
                        <Typography variant="h6" fontWeight="bold" sx={{ color: '#fff' }}>دفتر اليومية العامة</Typography>
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>سجل القيود المحاسبية والعمليات المالية</Typography>
                    </Box>
                </Box>
                <Button variant="contained" color="secondary" startIcon={<AddIcon />} onClick={() => navigate('/accounting/journals/new')} sx={{ fontWeight: 'bold' }}>
                    قيد جديد (+New)
                </Button>
            </Paper>

            {/* 2. Filter Bar */}
            <Paper sx={{ p: 1.5, m: 2, mb: 1, display: 'flex', gap: 2, alignItems: 'center', borderRadius: 1 }}>
                <TextField
                    size="small" placeholder="بحث برقم القيد أو الوصف..."
                    value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
                    sx={{ width: 350 }}
                    InputProps={{
                        startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
                    }}
                />
                <Box sx={{ borderLeft: '1px solid #e0e0e0', height: 30, mx: 1 }} />
                <Button size="small" variant="text" startIcon={<FilterList />}>تصفية متقدمة</Button>
            </Paper>

            {/* 3. Table Area */}
            <Box sx={{ px: 2, flexGrow: 1, overflowY: 'auto', pb: 2 }}>
                <TableContainer component={Paper} sx={{ borderRadius: 1, border: '1px solid #e2e8f0' }}>
                    <Table size="small" stickyHeader sx={{ '& .MuiTableCell-root': { py: 1, borderColor: '#e2e8f0' } }}>
                        <TableHead>
                            <TableRow>
                                <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', width: '8%' }}>رقم القيد</TableCell>
                                <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', width: '10%' }}>التاريخ</TableCell>
                                <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold' }}>البيان (Description)</TableCell>
                                <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', width: '10%' }}>المرجع</TableCell>
                                <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', width: '12%' }} align="center">الإجمالي</TableCell>
                                <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', width: '10%' }} align="center">الحالة</TableCell>
                                <TableCell sx={{ bgcolor: '#f8fafc', fontWeight: 'bold', width: '12%' }} align="center">خيارات</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {filteredJournals.map((journal) => {
                                const totalAmount = journal.lines?.reduce((sum, line) => sum + parseFloat(line.debit || 0), 0) || 0;
                                const isPosting = loadingIds.includes(journal.id);
                                return (
                                    <TableRow key={journal.id} hover sx={{ '&:nth-of-type(even)': { bgcolor: '#f8fafc' } }}>
                                        <TableCell sx={{ fontWeight: 'bold', fontFamily: 'monospace' }}>#{journal.id}</TableCell>
                                        <TableCell>{journal.transaction_date}</TableCell>
                                        <TableCell>
                                            <Typography variant="body2" fontWeight={500} color="text.primary">{journal.description}</Typography>
                                            {journal.reference_type && <Typography variant="caption" color="text.secondary">Ref: {journal.reference_type} #{journal.reference_id}</Typography>}
                                        </TableCell>
                                        <TableCell>{journal.reference_id || '-'}</TableCell>
                                        <TableCell align="center" sx={{ fontWeight: 'bold' }}>{totalAmount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</TableCell>
                                        <TableCell align="center">
                                            <Chip
                                                label={journal.is_posted ? 'مرحّل' : 'مسودة'}
                                                color={journal.is_posted ? 'success' : 'default'}
                                                size="small"
                                                sx={{ height: 22, fontSize: '0.75rem', fontWeight: 'bold', minWidth: 60 }}
                                            />
                                        </TableCell>
                                        <TableCell align="center">
                                            <Tooltip title="عرض/تعديل">
                                                <IconButton size="small" color="primary" onClick={() => navigate(`/accounting/journals/${journal.id}`)}>
                                                    <ViewIcon fontSize="small" />
                                                </IconButton>
                                            </Tooltip>
                                            {!journal.is_posted && (
                                                <Tooltip title="ترحيل القيد">
                                                    <span>
                                                        <IconButton
                                                            size="small"
                                                            sx={{ color: '#059669' }}
                                                            onClick={() => handlePost(journal.id)}
                                                            disabled={isPosting}
                                                        >
                                                            {isPosting ? <CircularProgress size={16} /> : <PostIcon fontSize="small" />}
                                                        </IconButton>
                                                    </span>
                                                </Tooltip>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                </TableContainer>
            </Box>
        </Box>
    );
};

export default JournalList;
