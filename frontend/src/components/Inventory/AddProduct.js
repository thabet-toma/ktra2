import React, { useState, useEffect } from 'react';
import {
    Box,
    TextField,
    Button,
    Typography,
    Paper,
    Grid,
    MenuItem,
    FormControl,
    InputLabel,
    Select,
    FormControlLabel,
    Checkbox,
    Alert,
    CircularProgress,
    Accordion,
    AccordionSummary,
    AccordionDetails,
    Divider,
    InputAdornment,
    Tooltip,
    IconButton,
    Avatar,
    FormHelperText
} from '@mui/material';
import {
    ExpandMore as ExpandMoreIcon,
    Inventory as InventoryIcon,
    LocalShipping as ShippingIcon,
    Storefront as StoreIcon,
    Save as SaveIcon,
    Info as InfoIcon,
    QrCode as QrCodeIcon,
    Close as CloseIcon,
    PhotoCamera as PhotoCameraIcon,
    Delete as DeleteIcon
} from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import inventoryService from '../../services/inventoryService';
import cloudinaryService from '../../services/cloudinaryService';

const SmallTextField = (props) => (
    <TextField
        {...props}
        size="small"
        variant="outlined"
        fullWidth
        margin="none"
        InputLabelProps={{ shrink: true, style: { fontWeight: 'bold', transformOrigin: 'top right', right: 0, left: 'auto' } }}
        InputProps={{ ...props.InputProps, style: { padding: '4px 8px', fontSize: '0.9rem', textAlign: 'right', ...props.inputStyle } }}
        sx={{
            '& .MuiOutlinedInput-root': { padding: 0, bgcolor: 'white' },
            '& .MuiInputLabel-root': { right: 20, left: 'auto', transformOrigin: 'top right' },
            '& legend': { textAlign: 'right' },
            ...props.sx
        }}
    />
);

const AddProduct = ({ id: propId, isEmbedded, onSuccess, onCancel }) => {
    const params = useParams();
    const id = propId || params.id;
    const navigate = useNavigate();

    const [formData, setFormData] = useState({
        sku: '',
        barcode: '',
        name_ar: '',
        name_en: '',
        category: '',
        uom_id: '',
        weight_kg: '',
        volume_cbm: '',
        hs_code: '',
        min_stock_level: '',
        is_serialized: false,
        is_for_sale_online: false,
        online_price: '',
        online_description: '',
        image_url: '',
        image_public_id: ''
    });

    const [uploadingImage, setUploadingImage] = useState(false);

    const [categories, setCategories] = useState([]);
    const [uoms, setUoms] = useState([]);
    const [loadingCategories, setLoadingCategories] = useState(true);
    const [loadingUoms, setLoadingUoms] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [successMessage, setSuccessMessage] = useState('');
    const [errorMessage, setErrorMessage] = useState('');
    const [expanded, setExpanded] = useState('basic');
    const [errors, setErrors] = useState({});

    useEffect(() => {
        const loadData = async () => {
            try {
                const cats = await inventoryService.getCategories();
                setCategories(cats);
                setLoadingCategories(false);

                const units = await inventoryService.getUOMs();
                setUoms(units);
                setLoadingUoms(false);

                if (id) {
                    const productsList = await inventoryService.getProducts();
                    const existing = productsList.find(p => p.id === parseInt(id));
                    if (existing) {
                        const productImg = existing.attachments?.find(a => a.file_type === 'Product Image')?.file_path;
                        setFormData({
                            ...existing,
                            category: existing.category?.id || existing.category || '',
                            uom_id: existing.uom_id?.id || existing.uom_id || '',
                            image_url: productImg || existing.image_url || ''
                        });
                    }
                }
            } catch (err) {
                console.error("Error loading initial data", err);
                setLoadingCategories(false);
                setLoadingUoms(false);
            }
        };
        loadData();
    }, [id]);

    const handleChange = (e) => {
        const { name, value, type, checked } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: type === 'checkbox' ? checked : value
        }));
        if (errors[name]) {
            setErrors(prev => ({ ...prev, [name]: null }));
        }
    };

    const handleAccordionChange = (panel) => (event, isExpanded) => {
        setExpanded(isExpanded ? panel : false);
    };

    const handleImageUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploadingImage(true);
        try {
            const result = await cloudinaryService.uploadImage(file);
            setFormData(prev => ({
                ...prev,
                image_url: result.url,
                image_public_id: result.public_id
            }));
            setSuccessMessage('تم رفع الصورة بنجاح (Image uploaded successfully!)');
        } catch (err) {
            setErrorMessage('فشل رفع الصورة: ' + err.message);
        } finally {
            setUploadingImage(false);
        }
    };

    const handleRemoveImage = () => {
        setFormData(prev => ({
            ...prev,
            image_url: '',
            image_public_id: ''
        }));
    };

    const validate = () => {
        const newErrors = {};
        if (!formData.sku?.trim()) newErrors.sku = 'رمز المنتج مطلوب (SKU is required)';
        if (!formData.name_ar?.trim()) newErrors.name_ar = 'اسم المنتج بالعربي مطلوب';
        if (!formData.category) newErrors.category = 'يرجى اختيار التصنيف';
        if (!formData.uom_id) newErrors.uom_id = 'يرجى اختيار وحدة القياس';

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!validate()) {
            setErrorMessage('يرجى التحقق من الحقول المطلوبة (Please check required fields)');
            setExpanded('basic');
            return;
        }

        setSubmitting(true);
        setSuccessMessage('');
        setErrorMessage('');

        try {
            if (id) {
                await inventoryService.updateProduct(id, formData);
                setSuccessMessage('تم تحديث المنتج بنجاح! (Product updated successfully!)');
                if (isEmbedded) {
                    setTimeout(() => onSuccess(), 1500);
                } else {
                    setTimeout(() => navigate('/inventory/products'), 2000);
                }
            } else {
                await inventoryService.createProduct(formData);
                setSuccessMessage('تم إضافة المنتج بنجاح! (Product added successfully!)');
                if (isEmbedded) {
                    setTimeout(() => onSuccess(), 1500);
                } else {
                    setFormData({
                        sku: '', barcode: '', name_ar: '', name_en: '', category: '',
                        uom_id: '', weight_kg: '', volume_cbm: '', hs_code: '',
                        min_stock_level: '', is_serialized: false, is_for_sale_online: false,
                        online_price: '', online_description: '',
                        image_url: '', image_public_id: ''
                    });
                    setExpanded('basic');
                }
            }
        } catch (error) {
            setErrorMessage('فشل في العملية: ' + (error.response?.data ? JSON.stringify(error.response.data) : error.message));
        } finally {
            setSubmitting(false);
        }
    };

    if (isEmbedded) {
        return (
            <Box sx={{ p: 3, bgcolor: '#f8fafc', minHeight: '100%' }} dir="rtl">
                {successMessage && <Alert severity="success" sx={{ mb: 2 }}>{successMessage}</Alert>}
                {errorMessage && <Alert severity="error" sx={{ mb: 2 }}>{errorMessage}</Alert>}
                <form onSubmit={handleSubmit}>
                    <Grid container spacing={2}>
                        <Grid item xs={12} md={6}>
                            <SmallTextField
                                label="رمز المنتج (SKU)" name="sku"
                                value={formData.sku} onChange={handleChange}
                                required error={!!errors.sku} helperText={errors.sku}
                            />
                        </Grid>
                        <Grid item xs={12} md={6}>
                            <SmallTextField
                                label="اسم المنتج (بالعربي)" name="name_ar"
                                value={formData.name_ar} onChange={handleChange}
                                required error={!!errors.name_ar} helperText={errors.name_ar}
                            />
                        </Grid>
                        <Grid item xs={12} md={6}>
                            <FormControl fullWidth required size="small" error={!!errors.category}>
                                <Typography variant="caption" fontWeight="bold" sx={{ mb: 0.5 }}>التصنيف</Typography>
                                <Select
                                    name="category" value={formData.category} onChange={handleChange}
                                    sx={{ bgcolor: 'white', height: 40 }}
                                >
                                    {categories.map(cat => <MenuItem key={cat.id} value={cat.id}>{cat.name}</MenuItem>)}
                                </Select>
                                {errors.category && <FormHelperText>{errors.category}</FormHelperText>}
                            </FormControl>
                        </Grid>
                        <Grid item xs={12} md={6}>
                            <FormControl fullWidth required size="small" error={!!errors.uom_id}>
                                <Typography variant="caption" fontWeight="bold" sx={{ mb: 0.5 }}>وحدة القياس</Typography>
                                <Select
                                    name="uom_id" value={formData.uom_id} onChange={handleChange}
                                    sx={{ bgcolor: 'white', height: 40 }}
                                >
                                    {uoms.map(u => <MenuItem key={u.id} value={u.id}>{u.name_ar}</MenuItem>)}
                                </Select>
                                {errors.uom_id && <FormHelperText>{errors.uom_id}</FormHelperText>}
                            </FormControl>
                        </Grid>

                        <Grid item xs={6} md={3}>
                            <SmallTextField type="number" label="الوزن (KG)" name="weight_kg" value={formData.weight_kg} onChange={handleChange} />
                        </Grid>
                        <Grid item xs={6} md={3}>
                            <SmallTextField type="number" label="الحجم (CBM)" name="volume_cbm" value={formData.volume_cbm} onChange={handleChange} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                            <SmallTextField label="HS Code" name="hs_code" value={formData.hs_code} onChange={handleChange} />
                        </Grid>

                        <Grid item xs={12} md={6}>
                            <SmallTextField type="number" label="السعر أونلاين" name="online_price" value={formData.online_price} onChange={handleChange} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                            <FormControlLabel control={<Checkbox checked={formData.is_for_sale_online} onChange={handleChange} name="is_for_sale_online" />} label="متاح أونلاين" />
                        </Grid>
                    </Grid>
                    <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
                        <Button type="submit" variant="contained" disabled={submitting} fullWidth sx={{ py: 1.5, fontWeight: 'bold' }}>
                            {submitting ? <CircularProgress size={24} color="inherit" /> : 'حفظ البيانات'}
                        </Button>
                        <Button variant="outlined" onClick={onCancel} fullWidth>إلغاء</Button>
                    </Box>
                </form>
            </Box>
        );
    }

    return (
        <Box sx={{ maxWidth: 1000, mx: 'auto', mt: 4, mb: 6, px: 2 }} dir="rtl">
            <Paper elevation={4} sx={{ borderRadius: 3, overflow: 'hidden' }}>
                <Box sx={{ bgcolor: id ? 'secondary.main' : 'primary.main', color: 'white', p: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
                    <InventoryIcon fontSize="large" />
                    <Typography variant="h5" fontWeight="bold" sx={{ fontFamily: 'Cairo' }}>
                        {id ? `تعديل المنتج: ${formData.name_ar} (Edit Product)` : 'إضافة منتج جديد (Add New Product)'}
                    </Typography>
                </Box>

                <Box sx={{ p: 4 }}>
                    {successMessage && <Alert severity="success" variant="filled" sx={{ mb: 3, borderRadius: 2, fontFamily: 'Cairo' }}>{successMessage}</Alert>}
                    {errorMessage && <Alert severity="error" variant="filled" sx={{ mb: 3, borderRadius: 2, fontFamily: 'Cairo' }}>{errorMessage}</Alert>}

                    <form onSubmit={handleSubmit}>
                        <Accordion expanded={expanded === 'basic'} onChange={handleAccordionChange('basic')} sx={{ mb: 2, border: '1px solid #e0e0e0', borderRadius: '8px !important' }}>
                            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                    <InventoryIcon color="primary" />
                                    <Typography fontWeight="bold" sx={{ fontFamily: 'Cairo' }}>المعلومات الأساسية (Basic Info)</Typography>
                                </Box>
                            </AccordionSummary>
                            <AccordionDetails>
                                <Grid container spacing={3}>
                                    <Grid item xs={12} md={6}>
                                        <TextField
                                            fullWidth label="رمز المنتج (SKU)" name="sku"
                                            value={formData.sku} onChange={handleChange}
                                            required
                                            error={!!errors.sku}
                                            helperText={errors.sku}
                                            InputProps={{ startAdornment: <InputAdornment position="start"><QrCodeIcon fontSize="small" color="action" /></InputAdornment> }}
                                        />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <TextField fullWidth label="الباركود (Barcode)" name="barcode" value={formData.barcode} onChange={handleChange} />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <TextField
                                            fullWidth label="اسم المنتج (بالعربي)" name="name_ar"
                                            value={formData.name_ar} onChange={handleChange}
                                            required
                                            error={!!errors.name_ar}
                                            helperText={errors.name_ar}
                                        />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <TextField fullWidth label="Product Name (English)" name="name_en" value={formData.name_en} onChange={handleChange} />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <FormControl fullWidth required error={!!errors.category}>
                                            <InputLabel sx={{ fontFamily: 'Cairo' }}>التصنيف (Category)</InputLabel>
                                            <Select name="category" value={formData.category} onChange={handleChange} label="التصنيف (Category)">
                                                {loadingCategories ? <MenuItem disabled><CircularProgress size={20} sx={{ mr: 1 }} /> جاري التحميل...</MenuItem> :
                                                    categories.map(cat => <MenuItem key={cat.id} value={cat.id}>{cat.name}</MenuItem>)}
                                            </Select>
                                            {errors.category && <FormHelperText>{errors.category}</FormHelperText>}
                                        </FormControl>
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <FormControl fullWidth required error={!!errors.uom_id}>
                                            <InputLabel sx={{ fontFamily: 'Cairo' }}>وحدة القياس (UOM)</InputLabel>
                                            <Select name="uom_id" value={formData.uom_id} onChange={handleChange} label="وحدة القياس (UOM)">
                                                {loadingUoms ? <MenuItem disabled><CircularProgress size={20} sx={{ mr: 1 }} /> جاري التحميل...</MenuItem> :
                                                    uoms.map(u => <MenuItem key={u.id} value={u.id}>{u.name_ar} ({u.code})</MenuItem>)}
                                            </Select>
                                            {errors.uom_id && <FormHelperText>{errors.uom_id}</FormHelperText>}
                                        </FormControl>
                                    </Grid>

                                    {/* Image Upload Section */}
                                    <Grid item xs={12}>
                                        <Divider sx={{ my: 1 }} />
                                        <Typography variant="subtitle2" sx={{ mb: 1, fontFamily: 'Cairo', display: 'flex', alignItems: 'center', gap: 1 }}>
                                            <PhotoCameraIcon fontSize="small" /> صورة المنتج (Product Image)
                                        </Typography>
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                            {formData.image_url ? (
                                                <Box sx={{ position: 'relative' }}>
                                                    <Avatar
                                                        src={formData.image_url}
                                                        variant="rounded"
                                                        sx={{ width: 100, height: 100, border: '1px solid #ddd' }}
                                                    />
                                                    <IconButton
                                                        size="small"
                                                        color="error"
                                                        onClick={handleRemoveImage}
                                                        sx={{ position: 'absolute', top: -10, right: -10, bgcolor: 'white', '&:hover': { bgcolor: '#f5f5f5' } }}
                                                    >
                                                        <DeleteIcon fontSize="small" />
                                                    </IconButton>
                                                </Box>
                                            ) : (
                                                <Button
                                                    variant="outlined"
                                                    component="label"
                                                    startIcon={uploadingImage ? <CircularProgress size={20} /> : <PhotoCameraIcon />}
                                                    disabled={uploadingImage}
                                                    sx={{ height: 100, width: 100, borderStyle: 'dashed', fontFamily: 'Cairo' }}
                                                >
                                                    {uploadingImage ? 'جاري الرفع...' : 'رفع صورة'}
                                                    <input type="file" hidden accept="image/*" onChange={handleImageUpload} />
                                                </Button>
                                            )}
                                            {!formData.image_url && !uploadingImage && (
                                                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'Cairo' }}>
                                                    يمكنك رفع صورة للمنتج (PNG, JPG, JPEG)
                                                </Typography>
                                            )}
                                        </Box>
                                    </Grid>
                                </Grid>
                            </AccordionDetails>
                        </Accordion>

                        <Accordion expanded={expanded === 'logistics'} onChange={handleAccordionChange('logistics')} sx={{ mb: 2, border: '1px solid #e0e0e0', borderRadius: '8px !important' }}>
                            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                    <ShippingIcon color="primary" />
                                    <Typography fontWeight="bold" sx={{ fontFamily: 'Cairo' }}>البيانات اللوجستية والمخزن (Logistics & Inventory)</Typography>
                                </Box>
                            </AccordionSummary>
                            <AccordionDetails>
                                <Grid container spacing={3}>
                                    <Grid item xs={6} md={3}>
                                        <TextField fullWidth type="number" label="الوزن (KG)" name="weight_kg" value={formData.weight_kg} onChange={handleChange} inputProps={{ step: "0.0001" }} />
                                    </Grid>
                                    <Grid item xs={6} md={3}>
                                        <TextField fullWidth type="number" label="الحجم (CBM)" name="volume_cbm" value={formData.volume_cbm} onChange={handleChange} inputProps={{ step: "0.000001" }} />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <TextField fullWidth label="رمز النظام المنسق (HS Code)" name="hs_code" value={formData.hs_code} onChange={handleChange} />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <TextField fullWidth type="number" label="حد إعادة الطلب (Min Stock)" name="min_stock_level" value={formData.min_stock_level} onChange={handleChange} />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <FormControlLabel control={<Checkbox checked={formData.is_serialized} onChange={handleChange} name="is_serialized" color="primary" />} label={<Typography variant="body2" sx={{ fontFamily: 'Cairo' }}>المنتج يتطلب رقم تسلسلي (Serialized Product)</Typography>} />
                                    </Grid>
                                </Grid>
                            </AccordionDetails>
                        </Accordion>

                        <Accordion expanded={expanded === 'ecommerce'} onChange={handleAccordionChange('ecommerce')} sx={{ mb: 4, border: '1px solid #e0e0e0', borderRadius: '8px !important' }}>
                            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                    <StoreIcon color="primary" />
                                    <Typography fontWeight="bold" sx={{ fontFamily: 'Cairo' }}>المتجر الإلكتروني (E-Commerce)</Typography>
                                </Box>
                            </AccordionSummary>
                            <AccordionDetails>
                                <Grid container spacing={3}>
                                    <Grid item xs={12}>
                                        <FormControlLabel control={<Checkbox checked={formData.is_for_sale_online} onChange={handleChange} name="is_for_sale_online" color="secondary" />} label={<Typography fontWeight="medium" sx={{ fontFamily: 'Cairo' }}>تفعيل العرض في المتجر الإلكتروني (Show in Online Store)</Typography>} />
                                    </Grid>
                                    <Grid item xs={12} md={4}>
                                        <TextField fullWidth type="number" label="السعر أونلاين" name="online_price" value={formData.online_price} onChange={handleChange} disabled={!formData.is_for_sale_online} InputProps={{ endAdornment: <InputAdornment position="end">₪</InputAdornment> }} />
                                    </Grid>
                                    <Grid item xs={12}>
                                        <TextField fullWidth multiline rows={3} label="وصف المنتج للمتجر" name="online_description" value={formData.online_description} onChange={handleChange} disabled={!formData.is_for_sale_online} />
                                    </Grid>
                                </Grid>
                            </AccordionDetails>
                        </Accordion>

                        <Divider sx={{ mb: 3 }} />
                        <Button type="submit" variant="contained" color={id ? "secondary" : "primary"} size="large" fullWidth disabled={submitting} startIcon={submitting ? <CircularProgress size={20} color="inherit" /> : <SaveIcon />} sx={{ py: 1.5, fontSize: '1.1rem', fontWeight: 'bold', borderRadius: 2, fontFamily: 'Cairo' }}>
                            {submitting ? 'جاري الحفظ...' : id ? 'تحديث المنتج (Update Product)' : 'حفظ المنتج (Save Product)'}
                        </Button>
                    </form>
                </Box>
            </Paper>
        </Box>
    );
};

export default AddProduct;
