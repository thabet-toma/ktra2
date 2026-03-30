import React, { useState, useEffect } from 'react';
import {
    Box,
    Typography,
    Paper,
    CircularProgress,
    List,
    ListItem,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Collapse,
    Button,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    IconButton,
    Menu,
    MenuItem,
    Divider
} from '@mui/material';
import {
    ExpandLess,
    ExpandMore,
    Folder as FolderIcon,
    FolderOpen as FolderOpenIcon,
    Add as AddIcon,
    MoreVert as MoreVertIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    ChevronLeft
} from '@mui/icons-material';
import inventoryService from '../../services/inventoryService';

const CategoryTree = () => {
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(true);
    const [expanded, setExpanded] = useState({});

    // Dialog State
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editMode, setEditMode] = useState(false);
    const [currentCategory, setCurrentCategory] = useState({ name: '', parent: '' });

    // Menu State
    const [anchorEl, setAnchorEl] = useState(null);
    const [menuTargetId, setMenuTargetId] = useState(null);

    useEffect(() => {
        fetchCategories();
    }, []);

    const fetchCategories = async () => {
        setLoading(true);
        try {
            const data = await inventoryService.getCategories(true);
            setCategories(data);
            const initialExpanded = {};
            const autoExpand = (nodes) => {
                nodes.forEach(node => {
                    initialExpanded[node.id] = true;
                    if (node.children) autoExpand(node.children);
                });
            };
            autoExpand(data);
            setExpanded(prev => ({ ...prev, ...initialExpanded }));
        } catch (error) {
            console.error("Error fetching categories:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleOpenAddDialog = (parentId = null) => {
        setEditMode(false);
        setCurrentCategory({ name: '', parent: parentId || '' });
        setDialogOpen(true);
        handleCloseMenu();
    };

    const handleOpenEditDialog = (category) => {
        setEditMode(true);
        setCurrentCategory({ ...category });
        setDialogOpen(true);
        handleCloseMenu();
    };

    const handleDeleteCategory = async (id) => {
        if (window.confirm('هل أنت متأكد من حذف هذا التصنيف؟')) {
            try {
                await inventoryService.deleteCategory(id);
                fetchCategories();
            } catch (error) {
                console.error("Error deleting category", error);
            }
            handleCloseMenu();
        }
    };

    const handleSaveCategory = async () => {
        try {
            const data = {
                name: currentCategory.name,
                parent: currentCategory.parent || null
            };
            if (editMode) {
                await inventoryService.updateCategory(currentCategory.id, data);
            } else {
                await inventoryService.createCategory(data);
            }
            setDialogOpen(false);
            fetchCategories();
        } catch (error) {
            alert("فشل في حفظ التصنيف");
            console.error("Error saving category", error);
        }
    };

    const toggleExpand = (id) => {
        setExpanded(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const handleMenuClick = (event, id, category) => {
        event.stopPropagation();
        setAnchorEl(event.currentTarget);
        setMenuTargetId(id);
        setCurrentCategory(category);
    };

    const handleCloseMenu = () => {
        setAnchorEl(null);
        setMenuTargetId(null);
    };

    const renderTree = (nodes, level = 0) => {
        return nodes.map((node) => {
            const hasChildren = node.children && node.children.length > 0;
            const isExpanded = expanded[node.id];

            return (
                <div key={node.id} style={{ position: 'relative' }}>
                    {level > 0 && (
                        <Box
                            sx={{
                                position: 'absolute',
                                top: '24px',
                                right: -25,
                                width: '25px',
                                height: '1px',
                                bgcolor: '#bdbdbd',
                                zIndex: 1
                            }}
                        />
                    )}

                    <ListItem
                        secondaryAction={
                            <IconButton edge="end" onClick={(e) => handleMenuClick(e, node.id, node)} size="small">
                                <MoreVertIcon fontSize="small" />
                            </IconButton>
                        }
                        disablePadding
                    >
                        <ListItemButton
                            onClick={() => toggleExpand(node.id)}
                            sx={{
                                borderRadius: 2,
                                height: 48,
                                border: '1px solid transparent',
                                '&:hover': { bgcolor: '#f5f5f5', borderColor: '#e0e0e0' }
                            }}
                        >
                            <ListItemIcon sx={{ minWidth: 28 }}>
                                {hasChildren ? (
                                    isExpanded ? <ExpandMore fontSize="small" /> : <ChevronLeft fontSize="small" />
                                ) : (
                                    <Box sx={{ width: 24 }} />
                                )}
                            </ListItemIcon>

                            <ListItemIcon sx={{ minWidth: 36 }}>
                                {hasChildren ? (
                                    isExpanded ? <FolderOpenIcon color="primary" /> : <FolderIcon color="action" />
                                ) : (
                                    <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: '#9e9e9e', mx: 1 }} />
                                )}
                            </ListItemIcon>

                            <ListItemText
                                primary={node.name}
                                primaryTypographyProps={{ fontWeight: level === 0 ? 'bold' : '500', fontFamily: 'Cairo' }}
                            />
                        </ListItemButton>
                    </ListItem>

                    {hasChildren && (
                        <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                            <Box sx={{ mr: 2.5, pr: 3, borderRight: '1px solid #e0e0e0', position: 'relative' }}>
                                <List component="div" disablePadding>
                                    {renderTree(node.children, level + 1)}
                                </List>
                            </Box>
                        </Collapse>
                    )}
                </div>
            );
        });
    };

    return (
        <Paper elevation={0} sx={{ margin: 3, padding: 3, minHeight: '85vh', borderRadius: 3, border: '1px solid #e0e0e0' }} dir="rtl">
            <Box display="flex" justifyContent="flex-start" alignItems="center" mb={4} pb={2} borderBottom="1px solid #f0f0f0" gap={2}>
                <Typography variant="h5" color="primary" sx={{ fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 1, fontFamily: 'Cairo' }}>
                    <FolderIcon fontSize="large" sx={{ color: '#1976d2' }} />
                    شجرة الأصناف (Category Tree)
                </Typography>

                <Button
                    variant="contained"
                    startIcon={<AddIcon sx={{ ml: 1 }} />}
                    onClick={() => handleOpenAddDialog()}
                    sx={{ borderRadius: 2, fontFamily: 'Cairo', fontWeight: 'bold', px: 3 }}
                >
                    إضافة تصنيف جديد
                </Button>
            </Box>

            {loading ? (
                <Box display="flex" justifyContent="center" m={8}><CircularProgress /></Box>
            ) : (
                <Box>
                    <List sx={{ width: '100%', bgcolor: 'background.paper' }}>
                        {categories.length === 0 ? (
                            <Box textAlign="center" py={10} sx={{ opacity: 0.6 }}>
                                <FolderOpenIcon sx={{ fontSize: 80, color: '#e0e0e0', mb: 2 }} />
                                <Typography color="text.secondary" variant="h6" sx={{ fontFamily: 'Cairo' }}>لا توجد تصنيفات حالياً</Typography>
                                <Button onClick={() => handleOpenAddDialog()} sx={{ mt: 1, fontFamily: 'Cairo' }}>ابدأ بإضافة تصنيفاتك</Button>
                            </Box>
                        ) : (
                            renderTree(categories)
                        )}
                    </List>
                </Box>
            )}

            <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={handleCloseMenu} PaperProps={{ sx: { borderRadius: 2, mt: 1 } }}>
                <MenuItem onClick={() => handleOpenAddDialog(menuTargetId)} sx={{ fontFamily: 'Cairo' }}>
                    <ListItemIcon><AddIcon fontSize="small" color="primary" /></ListItemIcon>إضافة فرع
                </MenuItem>
                <MenuItem onClick={() => handleOpenEditDialog(currentCategory)} sx={{ fontFamily: 'Cairo' }}>
                    <ListItemIcon><EditIcon fontSize="small" /></ListItemIcon>تعديل
                </MenuItem>
                <Divider />
                <MenuItem onClick={() => handleDeleteCategory(menuTargetId)} sx={{ color: 'error.main', fontFamily: 'Cairo' }}>
                    <ListItemIcon><DeleteIcon fontSize="small" color="error" /></ListItemIcon>حذف
                </MenuItem>
            </Menu>

            <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="xs" dir="rtl">
                <DialogTitle sx={{ fontWeight: 'bold', fontFamily: 'Cairo' }}>{editMode ? 'تعديل التصنيف' : 'إضافة تصنيف جديد'}</DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        label="اسم التصنيف"
                        fullWidth
                        value={currentCategory.name}
                        onChange={(e) => setCurrentCategory({ ...currentCategory, name: e.target.value })}
                        sx={{ mt: 2 }}
                        InputProps={{ sx: { fontFamily: 'Cairo' } }}
                    />
                </DialogContent>
                <DialogActions sx={{ p: 2, justifyContent: 'flex-start' }}>
                    <Button onClick={handleSaveCategory} variant="contained" sx={{ fontFamily: 'Cairo' }}>{editMode ? 'حفظ' : 'إضافة'}</Button>
                    <Button onClick={() => setDialogOpen(false)} sx={{ fontFamily: 'Cairo' }}>إلغاء</Button>
                </DialogActions>
            </Dialog>
        </Paper>
    );
};

export default CategoryTree;

