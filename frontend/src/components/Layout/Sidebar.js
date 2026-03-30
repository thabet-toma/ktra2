import React from 'react';
import {
    Box,
    List,
    ListItem,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Typography,
    Divider,
    Collapse
} from '@mui/material';
import {
    Dashboard as DashboardIcon,
    People as PeopleIcon,
    Inventory as InventoryIcon,
    ShoppingCart as ShoppingCartIcon,
    Receipt as ReceiptIcon,
    ExpandLess,
    ExpandMore,
    Business as BusinessIcon,
    Category as CategoryIcon,
    AddBox as AddBoxIcon,
    LocalShipping as ShipIcon
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';

const Sidebar = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const [openPurchases, setOpenPurchases] = React.useState(true);
    const [openAccounting, setOpenAccounting] = React.useState(true);
    const [openInventory, setOpenInventory] = React.useState(true);

    const handlePurchasesClick = () => {
        setOpenPurchases(!openPurchases);
    };

    const handleAccountingClick = () => {
        setOpenAccounting(!openAccounting);
    };

    const handleInventoryClick = () => {
        setOpenInventory(!openInventory);
    };

    return (
        <Box sx={{ width: 280, bgcolor: '#fff', height: '100vh', borderLeft: '1px solid #e0e0e0', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
            <Box sx={{ p: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
                <Typography variant="h5" fontWeight="bold" color="primary">K.T.R.A</Typography>
            </Box>
            <Divider />

            <List component="nav" sx={{ px: 2 }}>
                <ListItem disablePadding sx={{ mb: 1 }}>
                    <ListItemButton selected={location.pathname === '/'} onClick={() => navigate('/')} sx={{ borderRadius: 2 }}>
                        <ListItemIcon><DashboardIcon /></ListItemIcon>
                        <ListItemText primary="الرئيسية" />
                    </ListItemButton>
                </ListItem>



                {/* Purchases Section */}
                <ListItem disablePadding sx={{ mb: 1 }}>
                    <ListItemButton onClick={handlePurchasesClick} sx={{ borderRadius: 2, bgcolor: openPurchases ? '#e3f2fd' : 'transparent' }}>
                        <ListItemIcon><ShoppingCartIcon color={openPurchases ? 'primary' : 'inherit'} /></ListItemIcon>
                        <ListItemText primary="المشتريات" primaryTypographyProps={{ fontWeight: openPurchases ? 'bold' : 'medium', color: openPurchases ? 'primary' : 'inherit' }} />
                        {openPurchases ? <ExpandLess color="primary" /> : <ExpandMore />}
                    </ListItemButton>
                </ListItem>

                <Collapse in={openPurchases} timeout="auto" unmountOnExit>
                    <List component="div" disablePadding>
                        {/* Logistics Sub-menu */}
                        <ListItemButton onClick={() => navigate('/logistics/deals')} sx={{ pr: 4, borderRadius: 2, bgcolor: location.pathname === '/logistics/deals' ? '#e0f2f1' : 'transparent', mb: 0.5 }}>
                            <ListItemIcon><ShipIcon fontSize="small" color={location.pathname === '/logistics/deals' ? 'primary' : 'inherit'} /></ListItemIcon>
                            <ListItemText primary="الصفقات الاستيرادية" />
                        </ListItemButton>
                        <ListItemButton onClick={() => navigate('/logistics/shipments')} sx={{ pr: 4, borderRadius: 2, bgcolor: location.pathname === '/logistics/shipments' ? '#e0f2f1' : 'transparent', mb: 0.5 }}>
                            <ListItemIcon><ShipIcon fontSize="small" color={location.pathname === '/logistics/shipments' ? 'primary' : 'inherit'} /></ListItemIcon>
                            <ListItemText primary="إدارة الشحنات" />
                        </ListItemButton>
                        <ListItemButton onClick={() => navigate('/logistics/clearance')} sx={{ pr: 4, borderRadius: 2, bgcolor: location.pathname === '/logistics/clearance' ? '#e0f2f1' : 'transparent', mb: 0.5 }}>
                            <ListItemIcon><ShipIcon fontSize="small" color={location.pathname === '/logistics/clearance' ? 'primary' : 'inherit'} /></ListItemIcon>
                            <ListItemText primary="التخليص الجمركي" />
                        </ListItemButton>
                        <ListItemButton onClick={() => navigate('/logistics/expenses')} sx={{ pr: 4, borderRadius: 2, bgcolor: location.pathname === '/logistics/expenses' ? '#e8f5e9' : 'transparent', mb: 0.5 }}>
                            <ListItemIcon><ReceiptIcon fontSize="small" color={location.pathname === '/logistics/expenses' ? 'success' : 'inherit'} /></ListItemIcon>
                            <ListItemText primary="مصاريف الاستيراد" />
                        </ListItemButton>
                        <Divider sx={{ my: 1, mx: 2 }} />
                        <ListItemButton
                            selected={location.pathname === '/logistics/invoices'}
                            onClick={() => navigate('/logistics/invoices')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname === '/logistics/invoices' ? '#e0f2f1' : 'transparent' }}
                        >
                            <ListItemIcon><ReceiptIcon fontSize="small" color={location.pathname === '/logistics/invoices' ? 'primary' : 'inherit'} /></ListItemIcon>
                            <ListItemText primary="فواتير الشراء (Invoices)" />
                        </ListItemButton>
                        <ListItemButton
                            selected={location.pathname === '/partners'}
                            onClick={() => navigate('/partners')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname === '/partners' ? '#bbdefb' : 'transparent' }}
                        >
                            <ListItemIcon><PeopleIcon fontSize="small" color={location.pathname === '/partners' ? 'primary' : 'inherit'} /></ListItemIcon>
                            <ListItemText primary="الموردين والشركاء" />
                        </ListItemButton>
                    </List>
                </Collapse>

                {/* Accounting Section */}
                <ListItem disablePadding sx={{ mb: 1 }}>
                    <ListItemButton onClick={handleAccountingClick} sx={{ borderRadius: 2, bgcolor: openAccounting ? '#e8f5e9' : 'transparent' }}>
                        <ListItemIcon><ReceiptIcon color={openAccounting ? 'success' : 'inherit'} /></ListItemIcon>
                        <ListItemText primary="المحاسبة والمالية" primaryTypographyProps={{ fontWeight: openAccounting ? 'bold' : 'medium', color: openAccounting ? 'success' : 'inherit' }} />
                        {openAccounting ? <ExpandLess color="success" /> : <ExpandMore />}
                    </ListItemButton>
                </ListItem>

                <Collapse in={openAccounting} timeout="auto" unmountOnExit>
                    <List component="div" disablePadding>
                        <ListItemButton
                            selected={location.pathname === '/accounting/coa'}
                            onClick={() => navigate('/accounting/coa')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname === '/accounting/coa' ? '#c8e6c9' : 'transparent' }}
                        >
                            <ListItemIcon>
                                <InventoryIcon fontSize="small" color={location.pathname === '/accounting/coa' ? 'success' : 'inherit'} />
                            </ListItemIcon>
                            <ListItemText primary="شجرة الحسابات" />
                        </ListItemButton>
                        <ListItemButton
                            selected={location.pathname === '/accounting/journals'}
                            onClick={() => navigate('/accounting/journals')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname === '/accounting/journals' ? '#c8e6c9' : 'transparent' }}
                        >
                            <ListItemIcon>
                                <ReceiptIcon fontSize="small" color={location.pathname === '/accounting/journals' ? 'success' : 'inherit'} />
                            </ListItemIcon>
                            <ListItemText primary="دفتر اليومية" />
                        </ListItemButton>
                        <ListItemButton
                            selected={location.pathname === '/accounting/cheques'}
                            onClick={() => navigate('/accounting/cheques')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname === '/accounting/cheques' ? '#c8e6c9' : 'transparent' }}
                        >
                            <ListItemIcon>
                                <ReceiptIcon fontSize="small" color={location.pathname === '/accounting/cheques' ? 'success' : 'inherit'} />
                            </ListItemIcon>
                            <ListItemText primary="إدارة الشيكات" />
                        </ListItemButton>
                        <ListItemButton
                            selected={location.pathname === '/accounting/general-ledger'}
                            onClick={() => navigate('/accounting/general-ledger')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname === '/accounting/general-ledger' ? '#c8e6c9' : 'transparent' }}
                        >
                            <ListItemIcon>
                                <ReceiptIcon fontSize="small" color={location.pathname === '/accounting/general-ledger' ? 'success' : 'inherit'} />
                            </ListItemIcon>
                            <ListItemText primary="الأستاذ العام" />
                        </ListItemButton>
                        <ListItemButton
                            selected={location.pathname === '/accounting/trial-balance'}
                            onClick={() => navigate('/accounting/trial-balance')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname === '/accounting/trial-balance' ? '#c8e6c9' : 'transparent' }}
                        >
                            <ListItemIcon>
                                <ReceiptIcon fontSize="small" color={location.pathname === '/accounting/trial-balance' ? 'success' : 'inherit'} />
                            </ListItemIcon>
                            <ListItemText primary="ميزان المراجعة" />
                        </ListItemButton>
                    </List>
                </Collapse>

                {/* Inventory Section */}
                <ListItem disablePadding sx={{ mb: 1 }}>
                    <ListItemButton onClick={handleInventoryClick} sx={{ borderRadius: 2, bgcolor: openInventory ? '#fff3e0' : 'transparent' }}>
                        <ListItemIcon><InventoryIcon color={openInventory ? 'warning' : 'inherit'} /></ListItemIcon>
                        <ListItemText primary="المنتجات والمستودعات" primaryTypographyProps={{ fontWeight: openInventory ? 'bold' : 'medium', color: openInventory ? 'warning' : 'inherit' }} />
                        {openInventory ? <ExpandLess color="warning" /> : <ExpandMore />}
                    </ListItemButton>
                </ListItem>

                <Collapse in={openInventory} timeout="auto" unmountOnExit>
                    <List component="div" disablePadding>
                        <ListItemButton
                            selected={location.pathname.startsWith('/inventory')}
                            onClick={() => navigate('/inventory')}
                            sx={{ pr: 4, borderRadius: 2, mb: 0.5, bgcolor: location.pathname.startsWith('/inventory') ? '#ffe0b2' : 'transparent' }}
                        >
                            <ListItemIcon>
                                <InventoryIcon fontSize="small" color={location.pathname.startsWith('/inventory') ? 'warning' : 'inherit'} />
                            </ListItemIcon>
                            <ListItemText primary="إدارة المخزون" />
                        </ListItemButton>
                    </List>
                </Collapse>

                <ListItem disablePadding sx={{ mb: 1 }}>
                    <ListItemButton sx={{ borderRadius: 2 }}>
                        <ListItemIcon><BusinessIcon /></ListItemIcon>
                        <ListItemText primary="إدارة الموظفين" />
                    </ListItemButton>
                </ListItem>
            </List>
        </Box>
    );
};

export default Sidebar;
