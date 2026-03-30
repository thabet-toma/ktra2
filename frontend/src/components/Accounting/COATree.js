import React, { useState, useEffect } from 'react';
import {
    Box,
    Typography,
    Paper,
    IconButton,
    Button,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    MenuItem,
    List,
    ListItem,
    ListItemText,
    Collapse,
    Tooltip,
} from '@mui/material';
import {
    Add as AddIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    ExpandLess,
    ExpandMore,
    Folder as FolderIcon,
    Description as FileIcon,
} from '@mui/icons-material';
import accountingService from '../../services/accountingService';

const COATree = () => {
    const [accounts, setAccounts] = useState([]);
    const [openNodes, setOpenNodes] = useState({});
    const [dialogOpen, setDialogOpen] = useState(false);
    const [currentAccount, setCurrentAccount] = useState({
        name: '',
        code: '',
        account_type: 'Asset',
        parent: null,
        is_active: true,
    });
    const [isEdit, setIsEdit] = useState(false);

    useEffect(() => {
        fetchAccounts();
    }, []);

    const fetchAccounts = async () => {
        try {
            const data = await accountingService.getAccounts();
            // Sort by code for consistent display
            const sortedData = [...data].sort((a, b) => (a.code || '').localeCompare(b.code || ''));
            setAccounts(sortedData);

            // Auto-open top level nodes
            const initialOpen = {};
            sortedData.forEach(acc => {
                if (!acc.parent) initialOpen[acc.id] = true;
            });
            setOpenNodes(initialOpen);
        } catch (error) {
            console.error('Error fetching accounts:', error);
        }
    };

    const handleToggle = (id) => {
        setOpenNodes((prev) => ({ ...prev, [id]: !prev[id] }));
    };

    const handleOpenDialog = (parent = null, account = null) => {
        if (account) {
            setCurrentAccount(account);
            setIsEdit(true);
        } else {
            setCurrentAccount({
                name: '',
                code: '',
                account_type: parent ? parent.account_type : 'Asset',
                parent: parent ? parent.id : null,
                is_active: true,
            });
            setIsEdit(false);
        }
        setDialogOpen(true);
    };

    const handleCloseDialog = () => {
        setDialogOpen(false);
        setCurrentAccount({
            name: '',
            code: '',
            account_type: 'Asset',
            parent: null,
            is_active: true,
        });
    };

    const handleSave = async () => {
        try {
            if (isEdit) {
                await accountingService.updateAccount(currentAccount.id, currentAccount);
            } else {
                await accountingService.createAccount(currentAccount);
            }
            fetchAccounts();
            handleCloseDialog();
        } catch (error) {
            console.error('Error saving account:', error.response?.data || error.message);
            alert('حدث خطأ أثناء حفظ الحساب: ' + JSON.stringify(error.response?.data || error.message));
        }
    };

    const handleDelete = async (id) => {
        if (window.confirm('هل أنت متأكد من حذف هذا الحساب؟')) {
            try {
                await accountingService.deleteAccount(id);
                fetchAccounts();
            } catch (error) {
                console.error('Error deleting account:', error);
            }
        }
    };

    const getTypeColor = (type) => {
        switch (type) {
            case 'Asset': return '#2e7d32';
            case 'Liability': return '#c62828';
            case 'Equity': return '#1565c0';
            case 'Revenue': return '#ef6c00';
            case 'Expense': return '#6a1b9a';
            default: return '#757575';
        }
    };

    const renderTree = (parentId = null, level = 0) => {
        const children = accounts.filter((acc) => acc.parent === parentId);
        if (children.length === 0) return null;

        return (
            <List disablePadding sx={{ pl: parentId ? 2 : 0 }}>
                {children.map((account) => {
                    const hasChildren = accounts.some((acc) => acc.parent === account.id);
                    const isOpen = openNodes[account.id];

                    return (
                        <React.Fragment key={account.id}>
                            <ListItem
                                sx={{
                                    borderLeft: level > 0 ? '1px dashed #ddd' : 'none',
                                    ml: level > 0 ? 2 : 0,
                                    py: 0.5,
                                    '&:hover': { bgcolor: '#f5f5f5' },
                                    borderRadius: 1,
                                    cursor: 'pointer'
                                }}
                            >
                                <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                                    <IconButton
                                        size="small"
                                        onClick={(e) => { e.stopPropagation(); handleToggle(account.id); }}
                                        sx={{ visibility: hasChildren ? 'visible' : 'hidden' }}
                                    >
                                        {isOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                                    </IconButton>

                                    {hasChildren ? (
                                        <FolderIcon sx={{ color: getTypeColor(account.account_type), mr: 1 }} fontSize="small" />
                                    ) : (
                                        <FileIcon color="action" sx={{ mr: 1, fontSize: '1rem' }} />
                                    )}

                                    <ListItemText
                                        primary={
                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#555' }}>
                                                    {account.code}
                                                </Typography>
                                                <Typography variant="body1" sx={{ fontWeight: level === 0 ? 700 : 500 }}>
                                                    {account.name}
                                                </Typography>
                                            </Box>
                                        }
                                        secondary={level === 0 ? account.account_type : null}
                                    />

                                    <Box className="actions" sx={{ opacity: 0.1, '&:hover': { opacity: 1 }, transition: '0.2s' }}>
                                        <Tooltip title="إضافة حساب فرعي">
                                            <IconButton size="small" color="primary" onClick={() => handleOpenDialog(account)}>
                                                <AddIcon fontSize="small" />
                                            </IconButton>
                                        </Tooltip>
                                        <Tooltip title="تعديل">
                                            <IconButton size="small" onClick={() => handleOpenDialog(null, account)}>
                                                <EditIcon fontSize="small" />
                                            </IconButton>
                                        </Tooltip>
                                        <Tooltip title="حذف">
                                            <IconButton size="small" color="error" onClick={() => handleDelete(account.id)}>
                                                <DeleteIcon fontSize="small" />
                                            </IconButton>
                                        </Tooltip>
                                    </Box>
                                </Box>
                            </ListItem>
                            <Collapse in={isOpen} timeout="auto" unmountOnExit>
                                {renderTree(account.id, level + 1)}
                            </Collapse>
                        </React.Fragment>
                    );
                })}
            </List>
        );
    };

    return (
        <Box sx={{ p: 4, bgcolor: '#f8f9fa', minHeight: '100vh' }}>
            <Paper elevation={0} sx={{ p: 3, mb: 4, borderRadius: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #e0e0e0' }}>
                <Box>
                    <Typography variant="h4" fontWeight="800" color="primary.main">دليل الحسابات</Typography>
                    <Typography variant="body2" color="text.secondary">إدارة الهيكل المالي والمحاسبي للمنشأة</Typography>
                </Box>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => handleOpenDialog()}
                    sx={{ borderRadius: 2, px: 3, py: 1, textTransform: 'none', fontWeight: 'bold' }}
                >
                    إضافة حساب جذر
                </Button>
            </Paper>

            <Paper sx={{ p: 4, borderRadius: 3, border: '1px solid #e0e0e0', boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}>
                {accounts.length > 0 ? renderTree() : (
                    <Box sx={{ textAlign: 'center', py: 8 }}>
                        <Typography color="text.secondary">لا توجد حسابات مضافة بعد.</Typography>
                    </Box>
                )}
            </Paper>

            <Dialog open={dialogOpen} onClose={handleCloseDialog} fullWidth maxWidth="sm" PaperProps={{ sx: { borderRadius: 3 } }}>
                <DialogTitle sx={{ fontWeight: 'bold', borderBottom: '1px solid #eee' }}>
                    {isEdit ? 'تعديل بيانات الحساب' : 'إضافة حساب جديد إلى الدليل'}
                </DialogTitle>
                <DialogContent sx={{ pt: 3 }}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
                        <Box sx={{ display: 'flex', gap: 2 }}>
                            <TextField
                                label="رمز الحساب"
                                fullWidth
                                variant="outlined"
                                value={currentAccount.code}
                                onChange={(e) => setCurrentAccount({ ...currentAccount, code: e.target.value })}
                            />
                            <TextField
                                select
                                label="نوع الحساب"
                                fullWidth
                                value={currentAccount.account_type}
                                onChange={(e) => setCurrentAccount({ ...currentAccount, account_type: e.target.value })}
                            >
                                <MenuItem value="Asset">أصول (Asset)</MenuItem>
                                <MenuItem value="Liability">خصوم (Liability)</MenuItem>
                                <MenuItem value="Equity">حقوق ملكية (Equity)</MenuItem>
                                <MenuItem value="Revenue">إيرادات (Revenue)</MenuItem>
                                <MenuItem value="Expense">مصروفات (Expense)</MenuItem>
                            </TextField>
                        </Box>

                        <TextField
                            label="اسم الحساب"
                            fullWidth
                            variant="outlined"
                            value={currentAccount.name}
                            onChange={(e) => setCurrentAccount({ ...currentAccount, name: e.target.value })}
                        />

                        {currentAccount.parent && (() => {
                            const parentAcc = accounts.find(a => a.id === currentAccount.parent);
                            return (
                                <TextField
                                    label="الحساب الرئيسي (يندرج تحت)"
                                    fullWidth
                                    value={parentAcc ? `${parentAcc.code} - ${parentAcc.name}` : ''}
                                    disabled
                                    variant="filled"
                                    size="small"
                                />
                            );
                        })()}
                    </Box>
                </DialogContent>
                <DialogActions sx={{ p: 4, borderTop: '1px solid #eee' }}>
                    <Button onClick={handleCloseDialog} sx={{ px: 3 }}>إلغاء</Button>
                    <Button variant="contained" onClick={handleSave} sx={{ px: 4, borderRadius: 2 }}>حفظ الحساب</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default COATree;
