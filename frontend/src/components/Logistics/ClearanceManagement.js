import React, { useState, useEffect } from 'react';
import {
    Box, Typography, Paper, Button, Grid, Chip, Dialog,
    DialogTitle, DialogContent, TextField, DialogActions,
    MenuItem
} from '@mui/material';
import {
    Add as AddIcon, Edit as EditIcon, Policy as PolicyIcon
} from '@mui/icons-material';
import logisticsService from '../../services/logisticsService';
import accountingService from '../../services/accountingService';

const ClearanceManagement = () => {
    const [clearances, setClearances] = useState([]);
    const [shipments, setShipments] = useState([]); // Shipments available for clearance
    const [brokers, setBrokers] = useState([]); // Partners (Brokers)
    const [openDialog, setOpenDialog] = useState(false);
    const [currentClearance, setCurrentClearance] = useState(getEmptyClearance());

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const [clearData, shipData, partnersData] = await Promise.all([
                logisticsService.getClearances(),
                logisticsService.getShipments(),
                accountingService.getPartners()
            ]);
            setClearances(clearData);
            setShipments(shipData);
            setBrokers(partnersData.filter(p => !p.is_customer)); // Ideally filter by Broker type
        } catch (error) {
            console.error("Error loading clearance data", error);
        }
    };

    function getEmptyClearance() {
        return {
            shipment: '',
            customs_broker: '',
            declaration_number: '',
            clearance_date: new Date().toISOString().split('T')[0],
            status: 'Processing',
            notes: ''
        };
    }

    const handleSave = async () => {
        try {
            if (currentClearance.id) {
                // Update
                // Note: Usually we patch here.
                // Assuming update endpoint exists or we use create if logic allows
                alert("Update logic to be implemented fully in backend ViewSet updates.");
            } else {
                await logisticsService.createClearance(currentClearance);
            }
            setOpenDialog(false);
            loadData();
        } catch (error) {
            alert("Error saving clearance: " + error.message);
        }
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'Processing': return 'warning';
            case 'Cleared': return 'success';
            case 'Hold': return 'error';
            default: return 'default';
        }
    };

    return (
        <Box sx={{ p: 3 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                <Typography variant="h4" fontWeight="bold" color="primary">
                    التخليص الجمركي (Customs Clearance)
                </Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => { setCurrentClearance(getEmptyClearance()); setOpenDialog(true); }}
                    sx={{ px: 4, py: 1.5, borderRadius: 2 }}
                >
                    ملف تخليص جديد
                </Button>
            </Box>

            <Grid container spacing={3}>
                {clearances.map((item) => (
                    <Grid item xs={12} md={6} lg={4} key={item.id}>
                        <Paper sx={{ p: 2, borderRadius: 3, border: '1px solid #e0e0e0', '&:hover': { boxShadow: 6 } }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                                <Typography variant="h6" fontWeight="bold">البيان: {item.declaration_number || '---'}</Typography>
                                <Chip label={item.status} color={getStatusColor(item.status)} size="small" />
                            </Box>

                            <Typography variant="body2" sx={{ mt: 1 }}>
                                📦 الشحنة: #{item.shipment}
                            </Typography>
                            <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>
                                👮 المخلص: {item.broker_name || 'غير محدد'}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                📅 التاريخ: {item.clearance_date}
                            </Typography>

                            <Box sx={{ mt: 2 }}>
                                <Button
                                    variant="outlined"
                                    size="small"
                                    startIcon={<EditIcon />}
                                    onClick={() => { setCurrentClearance(item); setOpenDialog(true); }}
                                    fullWidth
                                >
                                    تعديل بيانات البيان
                                </Button>
                            </Box>
                        </Paper>
                    </Grid>
                ))}
            </Grid>

            {/* Dialog */}
            <Dialog open={openDialog} onClose={() => setOpenDialog(false)} maxWidth="sm" fullWidth>
                <DialogTitle>{currentClearance.id ? 'تعديل ملف التخليص' : 'بدء تخليص جديد'}</DialogTitle>
                <DialogContent>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
                        <TextField
                            select
                            label="الشحنة"
                            fullWidth
                            value={currentClearance.shipment}
                            onChange={(e) => setCurrentClearance({ ...currentClearance, shipment: e.target.value })}
                            disabled={!!currentClearance.id} // Cannot change shipment once started usually
                        >
                            {shipments.map(s => (
                                <MenuItem key={s.id} value={s.id}>#{s.shipment_number} ({s.status})</MenuItem>
                            ))}
                        </TextField>

                        <TextField
                            select
                            label="المخلص الجمركي (Customs Broker)"
                            fullWidth
                            value={currentClearance.customs_broker || ''}
                            onChange={(e) => setCurrentClearance({ ...currentClearance, customs_broker: e.target.value })}
                        >
                            {brokers.map(b => (
                                <MenuItem key={b.id} value={b.id}>{b.name}</MenuItem>
                            ))}
                        </TextField>

                        <TextField
                            label="رقم البيان الجمركي (Declaration No)"
                            fullWidth
                            value={currentClearance.declaration_number}
                            onChange={(e) => setCurrentClearance({ ...currentClearance, declaration_number: e.target.value })}
                        />

                        <TextField
                            type="date"
                            label="تاريخ التخليص"
                            fullWidth
                            InputLabelProps={{ shrink: true }}
                            value={currentClearance.clearance_date}
                            onChange={(e) => setCurrentClearance({ ...currentClearance, clearance_date: e.target.value })}
                        />

                        <TextField
                            select
                            label="الحالة"
                            fullWidth
                            value={currentClearance.status}
                            onChange={(e) => setCurrentClearance({ ...currentClearance, status: e.target.value })}
                        >
                            <MenuItem value="Processing">تحت الإجراء (Processing)</MenuItem>
                            <MenuItem value="Cleared">خالص (Cleared)</MenuItem>
                            <MenuItem value="Hold">معلق (Hold)</MenuItem>
                        </TextField>
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

export default ClearanceManagement;
