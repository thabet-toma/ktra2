import React, { useState, useEffect } from 'react';
import {
    Container,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Button,
    Typography,
    Box,
    Avatar,
    Chip,
    IconButton,
    TextField,
    InputAdornment,
    MenuItem,
    Menu,
    Grid,
    Divider
} from '@mui/material';
import {
    Add as AddIcon,
    Search as SearchIcon,
    FilterList as FilterListIcon,
    MoreHoriz as MoreHorizIcon,
    Edit as EditIcon,
    Visibility as ViewIcon,
    Delete as DeleteIcon
} from '@mui/icons-material';
import partnerService from '../../services/partnerService';
import PartnerForm from './PartnerForm';

const PartnersList = () => {
    const [partners, setPartners] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [filterType, setFilterType] = useState('all');
    const [openForm, setOpenForm] = useState(false);
    const [selectedPartner, setSelectedPartner] = useState(null);
    const [isReadOnly, setIsReadOnly] = useState(false);
    const [anchorEl, setAnchorEl] = useState(null);
    const [menuPartner, setMenuPartner] = useState(null);

    const fetchPartners = async () => {
        try {
            const data = await partnerService.getPartners();
            setPartners(data);
        } catch (error) {
            console.error("Failed to fetch partners", error);
        }
    };

    useEffect(() => {
        fetchPartners();
    }, []);

    const getTypeLabel = (type) => {
        const types = {
            'Customer': 'عميل',
            'Supplier': 'مورد',
            'FreightForwarder': 'شركة شحن',
            'CustomsBroker': 'مخلص جمركي',
            'LocalTransporter': 'ناقل محلي'
        };
        return types[type] || type;
    };

    const handleMenuOpen = (event, partner) => {
        setAnchorEl(event.currentTarget);
        setMenuPartner(partner);
    };

    const handleMenuClose = () => {
        setAnchorEl(null);
        setMenuPartner(null);
    };

    const handleEdit = () => {
        setSelectedPartner(menuPartner);
        setIsReadOnly(false);
        setOpenForm(true);
        handleMenuClose();
    };

    const handleView = () => {
        setSelectedPartner(menuPartner);
        setIsReadOnly(true);
        setOpenForm(true);
        handleMenuClose();
    };

    const handleAdd = () => {
        setSelectedPartner(null);
        setIsReadOnly(false);
        setOpenForm(true);
    };

    const filteredPartners = partners.filter(partner => {
        const matchesSearch = (partner.name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
            (partner.phone && partner.phone.includes(searchTerm));
        const matchesType = filterType === 'all' || partner.partner_type === filterType;
        return matchesSearch && matchesType;
    });

    return (
        <Container maxWidth="xl" sx={{ mt: 3, mb: 4 }}>
            {/* Header Area */}
            <Box sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                mb: 4,
                p: 3,
                bgcolor: '#fff',
                borderRadius: 4,
                boxShadow: '0 2px 12px rgba(0,0,0,0.03)',
                border: '1px solid #f0f2f5'
            }}>
                <Box>
                    <Typography variant="h4" sx={{ fontWeight: '800', color: '#1a237e', fontFamily: 'Cairo', mb: 0.5 }}>
                        إدارة الشركاء 🤝
                    </Typography>
                    <Typography variant="body1" color="text.secondary" sx={{ fontFamily: 'Cairo' }}>
                        عرض وتعديل الموردين، العملاء، ووكلاء الشحن في مكان واحد
                    </Typography>
                </Box>
                <Button
                    variant="contained"
                    startIcon={<AddIcon sx={{ ml: 1 }} />}
                    onClick={handleAdd}
                    sx={{
                        borderRadius: 3,
                        px: 4,
                        py: 1.5,
                        fontWeight: 'bold',
                        fontFamily: 'Cairo',
                        fontSize: '1rem',
                        boxShadow: '0 4px 14px rgba(26, 35, 126, 0.25)',
                        '&:hover': { boxShadow: '0 6px 20px rgba(26, 35, 126, 0.3)' }
                    }}
                >
                    إضافة شريك جديد
                </Button>
            </Box>

            {/* Filters Section */}
            <Paper sx={{ p: 2, mb: 4, borderRadius: 4, border: '1px solid #f0f2f5', boxShadow: 'none', bgcolor: '#fff' }}>
                <Grid container spacing={2} alignItems="center">
                    <Grid item xs={12} md={8}>
                        <TextField
                            fullWidth
                            placeholder="ابحث عن مورد (الاسم، الهاتف، الرقم الضريبي)..."
                            variant="outlined"
                            InputProps={{
                                startAdornment: (
                                    <InputAdornment position="start">
                                        <SearchIcon color="primary" />
                                    </InputAdornment>
                                ),
                                sx: { borderRadius: 3, fontFamily: 'Cairo', bgcolor: '#f8fafc' }
                            }}
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </Grid>
                    <Grid item xs={12} md={3}>
                        <TextField
                            select
                            fullWidth
                            variant="outlined"
                            value={filterType}
                            onChange={(e) => setFilterType(e.target.value)}
                            InputProps={{ sx: { borderRadius: 3, fontFamily: 'Cairo', bgcolor: '#f8fafc' } }}
                        >
                            <MenuItem value="all" sx={{ fontFamily: 'Cairo' }}>كل التصنيفات</MenuItem>
                            <MenuItem value="Customer" sx={{ fontFamily: 'Cairo' }}>العملاء</MenuItem>
                            <MenuItem value="Supplier" sx={{ fontFamily: 'Cairo' }}>الموردون</MenuItem>
                            <MenuItem value="FreightForwarder" sx={{ fontFamily: 'Cairo' }}>شركات الشحن</MenuItem>
                        </TextField>
                    </Grid>
                    <Grid item xs={12} md={1}>
                        <IconButton sx={{ bgcolor: '#f8fafc', borderRadius: 3, p: 1.5 }}>
                            <FilterListIcon color="primary" />
                        </IconButton>
                    </Grid>
                </Grid>
            </Paper>

            {/* Table Section */}
            <TableContainer component={Paper} sx={{ borderRadius: 4, border: '1px solid #f0f2f5', boxShadow: '0 4px 20px rgba(0,0,0,0.05)' }}>
                <Table sx={{ minWidth: 650 }} aria-label="partners table">
                    <TableHead sx={{ bgcolor: '#f8faff' }}>
                        <TableRow>
                            <TableCell align="right" sx={{ fontWeight: '800', fontFamily: 'Cairo', color: '#64748b' }}>#</TableCell>
                            <TableCell align="right" sx={{ fontWeight: '800', fontFamily: 'Cairo', color: '#64748b' }}>الاسم والبيانات</TableCell>
                            <TableCell align="right" sx={{ fontWeight: '800', fontFamily: 'Cairo', color: '#64748b' }}>التصنيف</TableCell>
                            <TableCell align="right" sx={{ fontWeight: '800', fontFamily: 'Cairo', color: '#64748b' }}>الاتصال</TableCell>
                            <TableCell align="right" sx={{ fontWeight: '800', fontFamily: 'Cairo', color: '#64748b' }}>الرصيد الحالي</TableCell>
                            <TableCell align="center" sx={{ fontWeight: '800', fontFamily: 'Cairo', color: '#64748b' }}>إجراءات</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {filteredPartners.map((partner, index) => (
                            <TableRow
                                key={partner.id}
                                sx={{
                                    '&:last-child td, &:last-child th': { border: 0 },
                                    transition: '0.2s',
                                    '&:hover': { bgcolor: '#f1f5f9', cursor: 'pointer' }
                                }}
                            >
                                <TableCell component="th" scope="row" align="right" sx={{ fontWeight: 'bold', color: '#94a3b8' }}>
                                    {index + 1}
                                </TableCell>
                                <TableCell align="right">
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                        <Avatar
                                            src={
                                                (partner.attachments && partner.attachments.find(a => a.file_type === 'Profile Image')?.file_path) ||
                                                (partner.image_path ? (partner.image_path.startsWith('http') ? partner.image_path : `http://localhost:8000/media/${partner.image_path}`) : undefined)
                                            }
                                            alt={partner.name}
                                            sx={{
                                                width: 48,
                                                height: 48,
                                                bgcolor: '#e0e7ff',
                                                color: '#4338ca',
                                                fontWeight: '800',
                                                border: '2px solid #fff',
                                                boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
                                            }}
                                        >
                                            {partner.name ? partner.name.charAt(0) : '?'}
                                        </Avatar>
                                        <Box>
                                            <Typography variant="subtitle1" fontWeight="800" sx={{ fontFamily: 'Cairo', color: '#1e293b' }}>
                                                {partner.name}
                                            </Typography>
                                            {partner.legal_name && (
                                                <Typography variant="caption" sx={{ fontFamily: 'Cairo', color: '#64748b', bgcolor: '#f1f5f9', px: 1, borderRadius: 1 }}>
                                                    {partner.legal_name}
                                                </Typography>
                                            )}
                                        </Box>
                                    </Box>
                                </TableCell>
                                <TableCell align="right">
                                    <Chip
                                        label={getTypeLabel(partner.partner_type)}
                                        size="small"
                                        sx={{
                                            bgcolor: partner.partner_type === 'Supplier' ? '#ecfdf5' : '#eff6ff',
                                            color: partner.partner_type === 'Supplier' ? '#059669' : '#2563eb',
                                            fontWeight: '800',
                                            fontFamily: 'Cairo',
                                            borderRadius: 1.5,
                                            border: '1px solid',
                                            borderColor: partner.partner_type === 'Supplier' ? '#10b981' : '#3b82f6'
                                        }}
                                    />
                                </TableCell>
                                <TableCell align="right">
                                    <Typography variant="body2" dir="ltr" sx={{ fontFamily: 'Cairo', color: '#1e293b', fontWeight: 'bold' }}>
                                        {partner.phone}
                                    </Typography>
                                    {partner.email && (
                                        <Typography variant="caption" sx={{ fontFamily: 'Cairo', color: '#64748b', display: 'block' }}>
                                            {partner.email}
                                        </Typography>
                                    )}
                                </TableCell>
                                <TableCell align="right">
                                    <Typography variant="subtitle2" sx={{ fontFamily: 'Cairo', color: '#1e293b', fontWeight: '#1e293b', fontWeight: '800' }}>
                                        {Number(partner.opening_balance || 0).toLocaleString()} {partner.currency || '₪'}
                                    </Typography>
                                </TableCell>
                                <TableCell align="center">
                                    <IconButton
                                        onClick={(e) => handleMenuOpen(e, partner)}
                                        sx={{ bgcolor: '#f8fafc', '&:hover': { bgcolor: '#e2e8f0' } }}
                                    >
                                        <MoreHorizIcon sx={{ color: '#64748b' }} />
                                    </IconButton>
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </TableContainer>


            {/* Row Actions Menu */}
            <Menu
                anchorEl={anchorEl}
                open={Boolean(anchorEl)}
                onClose={handleMenuClose}
                elevation={3}
                PaperProps={{
                    sx: {
                        minWidth: 180,
                        borderRadius: 3,
                        mt: 1,
                        p: 1,
                        boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)'
                    }
                }}
            >
                <MenuItem onClick={handleView} sx={{ fontFamily: 'Cairo', borderRadius: 2, gap: 1.5, py: 1 }}>
                    <ViewIcon fontSize="small" sx={{ color: '#6366f1' }} />
                    عرض التفاصيل
                </MenuItem>
                <MenuItem onClick={handleEdit} sx={{ fontFamily: 'Cairo', borderRadius: 2, gap: 1.5, py: 1 }}>
                    <EditIcon fontSize="small" sx={{ color: '#f59e0b' }} />
                    تعديل البيانات
                </MenuItem>
                <Divider sx={{ my: 1 }} />
                <MenuItem onClick={handleMenuClose} sx={{ fontFamily: 'Cairo', borderRadius: 2, gap: 1.5, py: 1, color: 'error.main' }}>
                    <DeleteIcon fontSize="small" />
                    حذف الشريك
                </MenuItem>
            </Menu>

            <PartnerForm
                open={openForm}
                handleClose={() => {
                    setOpenForm(false);
                    setSelectedPartner(null);
                }}
                onPartnerAdded={fetchPartners}
                partner={selectedPartner}
                readOnly={isReadOnly}
            />
        </Container>
    );
};

export default PartnersList;
