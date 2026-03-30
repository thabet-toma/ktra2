import React, { useState, useEffect } from 'react';
import {
    Box,
    Typography,
    Paper,
    Button,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Chip,
    IconButton,
    Dialog,
    DialogTitle,
    DialogContent,
    TextField,
    DialogActions,
    MenuItem
} from '@mui/material';
import {
    Add as AddIcon,
    Edit as EditIcon,
    CheckCircle as CollectIcon,
    Cancel as BounceIcon
} from '@mui/icons-material';
import accountingService from '../../services/accountingService';

const ChequeManagement = () => {
    const [cheques, setCheques] = useState([]);
    const [partners, setPartners] = useState([]);
    const [openDialog, setOpenDialog] = useState(false);
    const [currentCheque, setCurrentCheque] = useState(getEmptyCheque());

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const [chequeData, partnerData] = await Promise.all([
                accountingService.getCheques(),
                accountingService.getPartners()
            ]);
            setCheques(chequeData);
            setPartners(partnerData);
        } catch (error) {
            console.error("Failed to load cheques", error);
        }
    };

    function getEmptyCheque() {
        return {
            cheque_number: '',
            bank_name: '', // Added manually by user or from dropdown
            amount: '',
            due_date: '',
            payee_name: '',
            partner: '',
            direction: 'Incoming',
            status: 'Draft',
            notes: ''
        };
    }

    const handleSave = async () => {
        try {
            if (currentCheque.id) {
                await accountingService.updateCheque(currentCheque.id, currentCheque);
            } else {
                await accountingService.createCheque(currentCheque);
            }
            setOpenDialog(false);
            loadData();
        } catch (error) {
            alert('Error saving cheque: ' + error.message);
        }
    };

    const handleStatusChange = async (cheque, newStatus) => {
        if (!window.confirm(`Are you sure you want to mark this cheque as ${newStatus}?`)) return;
        try {
            await accountingService.updateCheque(cheque.id, { ...cheque, status: newStatus });
            loadData();
        } catch (error) {
            alert('Error updating status');
        }
    };

    return (
        <Box sx={{ p: 3, maxWidth: '1600px', margin: '0 auto' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                <Typography variant="h4" fontWeight="bold" color="primary">
                    إدارة الشيكات (Cheques)
                </Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => { setCurrentCheque(getEmptyCheque()); setOpenDialog(true); }}
                >
                    شيك جديد
                </Button>
            </Box>

            <TableContainer component={Paper}>
                <Table>
                    <TableHead sx={{ bgcolor: '#f5f5f5' }}>
                        <TableRow>
                            <TableCell>رقم الشيك</TableCell>
                            <TableCell>تاريخ الاستحقاق</TableCell>
                            <TableCell>المبلغ</TableCell>
                            <TableCell>البنك</TableCell>
                            <TableCell>الطرف (Partner)</TableCell>
                            <TableCell>الحالة</TableCell>
                            <TableCell>الاتجاه</TableCell>
                            <TableCell>إجراءات</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {cheques.map((cheque) => (
                            <TableRow key={cheque.id} hover>
                                <TableCell>{cheque.cheque_number}</TableCell>
                                <TableCell>{cheque.due_date}</TableCell>
                                <TableCell sx={{ fontWeight: 'bold' }}>{parseFloat(cheque.amount).toFixed(2)}</TableCell>
                                <TableCell>{cheque.bank_name}</TableCell>
                                <TableCell>
                                    {partners.find(p => p.id === cheque.partner)?.name || '-'}
                                </TableCell>
                                <TableCell>
                                    <Chip
                                        label={cheque.status}
                                        color={cheque.status === 'Collected' ? 'success' : cheque.status === 'Bounced' ? 'error' : 'warning'}
                                        size="small"
                                    />
                                </TableCell>
                                <TableCell>{cheque.direction === 'Incoming' ? 'قبض' : 'صرف'}</TableCell>
                                <TableCell>
                                    {cheque.status !== 'Collected' && cheque.status !== 'Bounced' && (
                                        <>
                                            <IconButton size="small" color="primary" onClick={() => { setCurrentCheque(cheque); setOpenDialog(true); }}>
                                                <EditIcon />
                                            </IconButton>
                                            <IconButton size="small" color="success" onClick={() => handleStatusChange(cheque, 'Collected')} title="تحصيل">
                                                <CollectIcon />
                                            </IconButton>
                                            <IconButton size="small" color="error" onClick={() => handleStatusChange(cheque, 'Bounced')} title="رتجع">
                                                <BounceIcon />
                                            </IconButton>
                                        </>
                                    )}
                                </TableCell>
                            </TableRow>
                        ))}
                        {cheques.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={8} align="center">لا توجد شيكات</TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            {/* Edit/Create Dialog */}
            <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
                <DialogTitle>{currentCheque.id ? 'تعديل شيك' : 'إضافة شيك جديد'}</DialogTitle>
                <DialogContent>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
                        <TextField
                            select
                            label="الاتجاه"
                            value={currentCheque.direction}
                            onChange={(e) => setCurrentCheque({ ...currentCheque, direction: e.target.value })}
                        >
                            <MenuItem value="Incoming">قبض (من عميل)</MenuItem>
                            <MenuItem value="Outgoing">صرف (لمورد)</MenuItem>
                        </TextField>

                        <TextField
                            label="رقم الشيك"
                            value={currentCheque.cheque_number}
                            onChange={(e) => setCurrentCheque({ ...currentCheque, cheque_number: e.target.value })}
                        />

                        <TextField
                            label="المبلغ"
                            type="number"
                            value={currentCheque.amount}
                            onChange={(e) => setCurrentCheque({ ...currentCheque, amount: e.target.value })}
                        />

                        <TextField
                            label="تاريخ الاستحقاق"
                            type="date"
                            InputLabelProps={{ shrink: true }}
                            value={currentCheque.due_date}
                            onChange={(e) => setCurrentCheque({ ...currentCheque, due_date: e.target.value })}
                        />

                        <TextField
                            select
                            label="الشريك (العميل/المورد)"
                            value={currentCheque.partner || ''}
                            onChange={(e) => setCurrentCheque({ ...currentCheque, partner: e.target.value })}
                        >
                            <MenuItem value=""><em>اختر...</em></MenuItem>
                            {partners.map(p => (
                                <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>
                            ))}
                        </TextField>

                        <TextField
                            label="اسم البنك"
                            value={currentCheque.bank_name}
                            onChange={(e) => setCurrentCheque({ ...currentCheque, bank_name: e.target.value })}
                        />

                        <TextField
                            label="البيان / ملاحظات"
                            multiline
                            rows={3}
                            value={currentCheque.notes}
                            onChange={(e) => setCurrentCheque({ ...currentCheque, notes: e.target.value })}
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenDialog(false)}>إلغاء</Button>
                    <Button variant="contained" onClick={handleSave}>حفظ</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ChequeManagement;
