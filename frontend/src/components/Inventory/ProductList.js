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
    IconButton,
    TextField,
    InputAdornment,
    Chip,
    Avatar,
} from '@mui/material';
import {
    Add as AddIcon,
    Search as SearchIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    Inventory as InventoryIcon,
} from '@mui/icons-material';
import inventoryService from '../../services/inventoryService';
import { useNavigate } from 'react-router-dom';

const ProductList = ({ filterCategoryId, onEditProduct, isEmbedded }) => {
    const navigate = useNavigate();
    const [products, setProducts] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        fetchProducts();
    }, []);

    const fetchProducts = async () => {
        try {
            const data = await inventoryService.getProducts();
            setProducts(data);
        } catch (error) {
            console.error('Error fetching products:', error);
        }
    };

    const handleDelete = async (id) => {
        if (window.confirm('هل أنت متأكد من حذف هذا المنتج؟')) {
            try {
                await inventoryService.deleteProduct(id);
                fetchProducts();
            } catch (error) {
                alert('حدث خطأ أثناء الحذف.');
            }
        }
    };

    const filteredProducts = products.filter(product => {
        const matchesSearch = (product.name_ar?.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (product.name_en?.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (product.sku?.toLowerCase().includes(searchTerm.toLowerCase()));

        const productCategoryId = product.category?.id || product.category;
        const matchesCategory = filterCategoryId ? (productCategoryId === filterCategoryId) : true;

        return matchesSearch && matchesCategory;
    });

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            {/* 1. Header with Search (Compact) */}
            <Paper elevation={0} sx={{ p: 1, mb: 1, display: 'flex', gap: 2, alignItems: 'center', border: '1px solid #e0e0e0', borderRadius: 2 }}>
                <TextField
                    sx={{ width: 400, bgcolor: '#f8fafc' }}
                    placeholder="بحث سريع (SKU، اسم المنتج...)"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    size="small"
                    InputProps={{
                        startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>,
                    }}
                />
                {!isEmbedded && (
                    <Button variant="contained" size="small" startIcon={<AddIcon />} onClick={() => navigate('/inventory/products/new')}>
                        إضافة منتج
                    </Button>
                )}
            </Paper>

            {/* 2. High-Density Table */}
            <TableContainer component={Paper} elevation={0} sx={{ flexGrow: 1, border: '1px solid #e0e0e0', borderRadius: 2, overflowY: 'auto' }}>
                <Table size="small" stickyHeader sx={{ '& .MuiTableCell-root': { py: 0.8, px: 1.2, textAlign: 'right' } }}>
                    <TableHead>
                        <TableRow>
                            <TableCell sx={{ bgcolor: '#f1f5f9', fontWeight: 'bold', width: '35%' }}>المنتج (Product)</TableCell>
                            <TableCell sx={{ bgcolor: '#f1f5f9', fontWeight: 'bold' }}>SKU</TableCell>
                            <TableCell sx={{ bgcolor: '#f1f5f9', fontWeight: 'bold' }}>التصنيف</TableCell>
                            <TableCell sx={{ bgcolor: '#f1f5f9', fontWeight: 'bold' }}>الوحدة</TableCell>
                            <TableCell sx={{ bgcolor: '#f1f5f9', fontWeight: 'bold' }} align="center">السعر</TableCell>
                            <TableCell sx={{ bgcolor: '#f1f5f9', fontWeight: 'bold' }} align="center">الحالة</TableCell>
                            <TableCell sx={{ bgcolor: '#f1f5f9', fontWeight: 'bold' }} align="center">خيارات</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {filteredProducts.map((product) => (
                            <TableRow key={product.id} hover sx={{ '&:nth-of-type(odd)': { bgcolor: '#fcfdfe' } }}>
                                <TableCell>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                        <Avatar
                                            variant="rounded"
                                            sx={{ width: 28, height: 28, fontSize: '0.75rem', bgcolor: 'primary.light' }}
                                        >
                                            {product.name_ar?.charAt(0) || 'P'}
                                        </Avatar>
                                        <Box>
                                            <Typography variant="body2" fontWeight="600" sx={{ lineHeight: 1.2 }}>{product.name_ar}</Typography>
                                            <Typography variant="caption" color="text.secondary">{product.name_en}</Typography>
                                        </Box>
                                    </Box>
                                </TableCell>
                                <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{product.sku}</TableCell>
                                <TableCell>
                                    <Chip label={product.category_name || 'عام'} size="small" variant="outlined" sx={{ height: 20, fontSize: '0.7rem' }} />
                                </TableCell>
                                <TableCell sx={{ fontSize: '0.8rem' }}>{product.uom_name || product.uom}</TableCell>
                                <TableCell align="center" sx={{ fontWeight: 'bold', color: 'success.dark' }}>
                                    {product.online_price ? `${product.online_price} $` : '-'}
                                </TableCell>
                                <TableCell align="center">
                                    <Chip
                                        label={product.is_for_sale_online ? 'أونلاين' : 'مخزني'}
                                        size="small"
                                        color={product.is_for_sale_online ? 'success' : 'default'}
                                        variant={product.is_for_sale_online ? 'filled' : 'outlined'}
                                        sx={{ height: 18, fontSize: '0.65rem' }}
                                    />
                                </TableCell>
                                <TableCell align="center">
                                    <IconButton size="small" color="primary" onClick={() => onEditProduct ? onEditProduct(product.id) : navigate(`/inventory/products/${product.id}/edit`)}>
                                        <EditIcon fontSize="small" />
                                    </IconButton>
                                    <IconButton size="small" color="error" onClick={() => handleDelete(product.id)}>
                                        <DeleteIcon fontSize="small" />
                                    </IconButton>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>
        </Box>
    );
};

export default ProductList;
