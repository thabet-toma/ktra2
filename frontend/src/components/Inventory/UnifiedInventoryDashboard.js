import React, { useState, useEffect } from 'react';
import {
    Box,
    Typography,
    Paper,
    Grid,
    Button,
    IconButton,
    InputAdornment,
    TextField,
    Divider,
    List,
    ListItem,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Collapse,
    Drawer,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    CircularProgress,
    Tooltip,
} from '@mui/material';
import {
    Inventory as InventoryIcon,
    Add as AddIcon,
    Search as SearchIcon,
    Folder as FolderIcon,
    FolderOpen as FolderOpenIcon,
    ExpandLess,
    ExpandMore,
    ChevronLeft,
    Edit as EditIcon,
    Delete as DeleteIcon,
    FilterList as FilterIcon,
    Close as CloseIcon,
    MoreVert as MoreVertIcon,
    Menu as MenuIcon,
} from '@mui/icons-material';
import inventoryService from '../../services/inventoryService';
import ProductList from './ProductList';
import AddProduct from './AddProduct';

const UnifiedInventoryDashboard = () => {
    const [categories, setCategories] = useState([]);
    const [loadingCats, setLoadingCats] = useState(true);
    const [expanded, setExpanded] = useState({});
    const [selectedCategoryId, setSelectedCategoryId] = useState(null);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [editProductId, setEditProductId] = useState(null);

    // Category Dialog State
    const [catDialogOpen, setCatDialogOpen] = useState(false);
    const [catEditMode, setCatEditMode] = useState(false);
    const [currentCategory, setCurrentCategory] = useState({ name: '', parent: null });

    useEffect(() => {
        fetchCategories();
    }, []);

    const fetchCategories = async () => {
        setLoadingCats(true);
        try {
            const data = await inventoryService.getCategories(true);
            setCategories(data);
            // Auto expand first level
            const initialExpanded = {};
            data.forEach(node => { initialExpanded[node.id] = true; });
            setExpanded(initialExpanded);
        } catch (error) {
            console.error("Error fetching categories:", error);
        } finally {
            setLoadingCats(false);
        }
    };

    const handleOpenAddProduct = () => {
        setEditProductId(null);
        setDrawerOpen(true);
    };

    const handleEditProduct = (id) => {
        setEditProductId(id);
        setDrawerOpen(true);
    };

    const handleProductActionComplete = () => {
        setDrawerOpen(false);
        // Refresh product list happens inside ProductList usually or by re-render
        // To force refresh, we can use a key or a signal
        setRefreshSignal(prev => prev + 1);
    };

    const [refreshSignal, setRefreshSignal] = useState(0);

    const toggleExpand = (id, e) => {
        e.stopPropagation();
        setExpanded(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const handleSaveCategory = async () => {
        if (!currentCategory.name?.trim()) {
            alert("يرجى إدخال اسم التصنيف");
            return;
        }
        try {
            if (catEditMode) {
                await inventoryService.updateCategory(currentCategory.id, currentCategory);
            } else {
                await inventoryService.createCategory(currentCategory);
            }
            setCatDialogOpen(false);
            fetchCategories();
        } catch (error) {
            alert("حدث خطأ أثناء حفظ التصنيف");
        }
    };

    const renderCategoryTree = (nodes, level = 0) => {
        return nodes.map((node) => {
            const hasChildren = node.children && node.children.length > 0;
            const isExpanded = expanded[node.id];
            const isSelected = selectedCategoryId === node.id;

            return (
                <Box key={node.id}>
                    <ListItem disablePadding>
                        <ListItemButton
                            selected={isSelected}
                            onClick={() => setSelectedCategoryId(node.id === selectedCategoryId ? null : node.id)}
                            sx={{
                                py: 0.5,
                                borderRadius: 1,
                                mb: 0.5,
                                '&.Mui-selected': { bgcolor: 'primary.light', color: 'primary.contrastText' }
                            }}
                        >
                            <ListItemIcon sx={{ minWidth: 32 }} onClick={(e) => hasChildren && toggleExpand(node.id, e)}>
                                {hasChildren ? (isExpanded ? <ExpandMore fontSize="small" /> : <ChevronLeft fontSize="small" />) : null}
                            </ListItemIcon>
                            <ListItemText
                                primary={node.name}
                                primaryTypographyProps={{ fontSize: '0.9rem', fontFamily: 'Cairo', fontWeight: isSelected ? 'bold' : 'normal' }}
                            />
                            <Box sx={{ display: 'flex' }}>
                                <Tooltip title="إضافة فرع">
                                    <IconButton
                                        size="small"
                                        color="primary"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setCatEditMode(false);
                                            setCurrentCategory({ name: '', parent: node.id });
                                            setCatDialogOpen(true);
                                        }}
                                    >
                                        <AddIcon sx={{ fontSize: 16 }} />
                                    </IconButton>
                                </Tooltip>
                                <IconButton
                                    size="small"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setCatEditMode(true);
                                        setCurrentCategory(node);
                                        setCatDialogOpen(true);
                                    }}
                                >
                                    <EditIcon sx={{ fontSize: 14 }} />
                                </IconButton>
                            </Box>
                        </ListItemButton>
                    </ListItem>
                    {hasChildren && (
                        <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                            <List component="div" disablePadding sx={{ pr: 2, borderRight: '1px solid #eee', mr: 1 }}>
                                {renderCategoryTree(node.children, level + 1)}
                            </List>
                        </Collapse>
                    )}
                </Box>
            );
        });
    };

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', bgcolor: '#f5f5f5' }} dir="rtl">
            {/* Header / Toolbar */}
            <Paper elevation={1} sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderRadius: 0, bgcolor: '#fff' }}>
                <Typography variant="h5" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1, fontFamily: 'Cairo', color: 'primary.main' }}>
                    <InventoryIcon color="primary" />
                    إدارة المخزون (Inventory Management)
                </Typography>
                <Box sx={{ display: 'flex', gap: 2 }}>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={handleOpenAddProduct}
                        sx={{ borderRadius: 2, fontWeight: 'bold' }}
                    >
                        منتج جديد
                    </Button>
                </Box>
            </Paper>

            <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
                {/* Unified Sidebar: Categories */}
                <Paper sx={{ width: 300, display: 'flex', flexDirection: 'column', borderRadius: 0, borderLeft: '1px solid #e0e0e0' }}>
                    <Box sx={{ p: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: '#fafafa' }}>
                        <Typography variant="subtitle1" fontWeight="bold" sx={{ fontFamily: 'Cairo' }}>التصنيفات</Typography>
                        <IconButton size="small" color="primary" onClick={() => {
                            setCatEditMode(false);
                            setCurrentCategory({ name: '', parent: null });
                            setCatDialogOpen(true);
                        }}>
                            <AddIcon />
                        </IconButton>
                    </Box>
                    <Divider />
                    <Box sx={{ p: 1, flex: 1, overflowY: 'auto' }}>
                        {loadingCats ? <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}><CircularProgress size={24} /></Box> : (
                            <List disablePadding>
                                <ListItem disablePadding>
                                    <ListItemButton
                                        selected={selectedCategoryId === null}
                                        onClick={() => setSelectedCategoryId(null)}
                                        sx={{ borderRadius: 1, mb: 0.5 }}
                                    >
                                        <ListItemIcon sx={{ minWidth: 32 }}><InventoryIcon fontSize="small" /></ListItemIcon>
                                        <ListItemText primary="كل المنتجات" primaryTypographyProps={{ fontFamily: 'Cairo' }} />
                                    </ListItemButton>
                                </ListItem>
                                {renderCategoryTree(categories)}
                            </List>
                        )}
                    </Box>
                </Paper>

                {/* Main Content: Product List */}
                <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
                    <ProductList
                        key={refreshSignal}
                        filterCategoryId={selectedCategoryId}
                        onEditProduct={handleEditProduct}
                        isEmbedded={true}
                    />
                </Box>
            </Box>

            {/* Side Drawer for Add/Edit Product */}
            <Drawer
                anchor="left"
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                PaperProps={{ sx: { width: { xs: '100%', md: 800 }, bgcolor: '#fcfcfc' } }}
            >
                <Box sx={{ p: 0, height: '100%', display: 'flex', flexDirection: 'column' }}>
                    <Box sx={{ p: 2, bgcolor: 'primary.main', color: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="h6" sx={{ fontFamily: 'Cairo', fontWeight: 'bold' }}>
                            {editProductId ? 'تعديل المنتج' : 'إضافة منتج جديد'}
                        </Typography>
                        <IconButton color="inherit" onClick={() => setDrawerOpen(false)}>
                            <CloseIcon />
                        </IconButton>
                    </Box>
                    <Box sx={{ flex: 1, overflowY: 'auto' }}>
                        <AddProduct
                            id={editProductId}
                            isEmbedded={true}
                            onSuccess={handleProductActionComplete}
                            onCancel={() => setDrawerOpen(false)}
                        />
                    </Box>
                </Box>
            </Drawer>

            {/* Category Dialog */}
            <Dialog open={catDialogOpen} onClose={() => setCatDialogOpen(false)} dir="rtl">
                <DialogTitle sx={{ fontFamily: 'Cairo' }}>{catEditMode ? 'تعديل التصنيف' : 'إضافة تصنيف'}</DialogTitle>
                <DialogContent>
                    <TextField
                        fullWidth
                        label="اسم التصنيف"
                        sx={{ mt: 2 }}
                        value={currentCategory.name}
                        onChange={(e) => setCurrentCategory({ ...currentCategory, name: e.target.value })}
                    />
                </DialogContent>
                <DialogActions sx={{ justifyContent: 'flex-start', p: 2 }}>
                    <Button variant="contained" onClick={handleSaveCategory}>حفظ</Button>
                    <Button onClick={() => setCatDialogOpen(false)}>إلغاء</Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default UnifiedInventoryDashboard;
