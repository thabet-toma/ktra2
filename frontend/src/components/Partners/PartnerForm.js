import React, { useState } from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    Button,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Box,
    Typography,
    Tabs,
    Tab,
    Grid,
    InputAdornment,
    IconButton,
    Avatar,
    Paper,
    Divider
} from '@mui/material';
import {
    Person as PersonIcon,
    AttachMoney as MoneyIcon,
    AccountBalance as BankIcon,
    CloudUpload as CloudUploadIcon,
    Add as AddIcon,
    Delete as DeleteIcon
} from '@mui/icons-material';
import partnerService from '../../services/partnerService';
import cloudinaryService from '../../services/cloudinaryService';

const PartnerForm = ({ open, handleClose, onPartnerAdded, partner = null, readOnly = false }) => {
    const [tabValue, setTabValue] = useState(0);
    const [uploadingImage, setUploadingImage] = useState(false);
    const [uploadingDocument, setUploadingDocument] = useState(false);
    const [formData, setFormData] = useState({
        name: '',
        legal_name: '',
        street_address: '',
        city: '',
        state_or_province: '',
        postal_code: '',
        email: '',
        phone: '',
        tax_number: '',
        credit_limit: '',
        partner_type: 'Customer',
        image_path: null,
        country: '',
        opening_balance: 0,
        opening_balance_date: new Date().toISOString().split('T')[0],
        currency: '',
        group: ''
    });
    const [bankAccounts, setBankAccounts] = useState([]);

    React.useEffect(() => {
        if (partner && open) {
            // Find specific attachments
            const profileImg = partner.attachments?.find(a => a.file_type === 'Profile Image')?.file_path;
            const doc = partner.attachments?.find(a => a.file_type === 'Document')?.file_path;

            setFormData({
                name: partner.name || '',
                legal_name: partner.legal_name || '',
                street_address: partner.street_address || '',
                city: partner.city || '',
                state_or_province: partner.state_or_province || '',
                postal_code: partner.postal_code || '',
                email: partner.email || '',
                phone: partner.phone || '',
                tax_number: partner.tax_number || '',
                credit_limit: partner.credit_limit || '',
                partner_type: partner.partner_type || 'Customer',
                image_path: profileImg || partner.image_path || null,
                document_url: doc || null,
                country: partner.country || '',
                opening_balance: partner.opening_balance || 0,
                opening_balance_date: partner.opening_balance_date || new Date().toISOString().split('T')[0],
                currency: partner.currency || '',
                group: partner.group || ''
            });
            setBankAccounts(partner.bank_accounts || []);
        } else if (open) {
            setFormData({
                name: '',
                legal_name: '',
                street_address: '',
                city: '',
                state_or_province: '',
                postal_code: '',
                email: '',
                phone: '',
                tax_number: '',
                credit_limit: '',
                partner_type: 'Customer',
                image_path: null,
                country: '',
                opening_balance: 0,
                opening_balance_date: new Date().toISOString().split('T')[0],
                currency: '',
                group: ''
            });
            setBankAccounts([]);
        }
        setTabValue(0);
    }, [partner, open]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData({ ...formData, [name]: value });
    };

    const handleImageChange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploadingImage(true);
        try {
            const result = await cloudinaryService.uploadImage(file);
            setFormData(prev => ({
                ...prev,
                image_path: result.url,
                image_public_id: result.public_id
            }));
        } catch (err) {
            console.error("Cloudinary Upload Error:", err);
            alert("فشل رفع الصورة: " + err.message);
        } finally {
            setUploadingImage(false);
        }
    };

    const handleDocumentChange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploadingDocument(true);
        try {
            const result = await cloudinaryService.uploadFile(file);
            setFormData(prev => ({
                ...prev,
                document_url: result.url,
                document_public_id: result.public_id
            }));
        } catch (err) {
            console.error("Cloudinary File Upload Error:", err);
            alert("فشل رفع الملف: " + err.message);
        } finally {
            setUploadingDocument(false);
        }
    };
    const handleTabChange = (event, newValue) => {
        setTabValue(newValue);
    };

    const addBankAccount = () => {
        setBankAccounts([...bankAccounts, {
            bank_name: '',
            account_number: '',
            iban: '',
            swift_code: '',
            bank_address: '',
            beneficiary_name: '',
            currency: formData.currency,
            is_active: true
        }]);
    };

    const removeBankAccount = (index) => {
        setBankAccounts(bankAccounts.filter((_, i) => i !== index));
    };

    const updateBankAccount = (index, field, value) => {
        const updated = [...bankAccounts];
        updated[index][field] = value;
        setBankAccounts(updated);
    };

    const handleSubmit = async () => {
        // Validation
        for (let i = 0; i < bankAccounts.length; i++) {
            const acc = bankAccounts[i];
            if (!acc.bank_name || !acc.account_number || !acc.currency) {
                setTabValue(2);
                alert(`يرجى ملء كافة البيانات المطلوبة للحساب البنكي رقم ${i + 1}`);
                return;
            }
        }

        try {
            const partnerData = { ...formData, bank_accounts: bankAccounts };
            if (partner) {
                await partnerService.updatePartner(partner.id, partnerData);
            } else {
                await partnerService.createPartner(partnerData);
            }
            onPartnerAdded();
            handleClose();
        } catch (error) {
            let errorMessage = partner ? "فشل في تحديث بيانات الشريك." : "فشل في إضافة الشريك.";
            if (error.response?.data) {
                const data = error.response.data;
                if (typeof data === 'object' && !Array.isArray(data)) {
                    const fieldMap = {
                        'name': 'الاسم التجاري',
                        'email': 'البريد الإلكتروني',
                        'phone': 'رقم الهاتف',
                        'partner_type': 'نوع الشريك',
                        'currency': 'العملة',
                        'opening_balance': 'الرصيد الافتتاحي'
                    };
                    const errors = Object.entries(data).map(([f, m]) => `${fieldMap[f] || f}: ${m}`);
                    errorMessage = errors.join('\n');
                } else {
                    errorMessage = String(data);
                }
            }
            alert(`خطأ: ${errorMessage}`);
        }
    };

    const getTitle = () => {
        if (readOnly) return 'عرض تفاصيل الشريك 🔍';
        if (partner) return 'تعديل بيانات الشريك ✏️';
        return 'إضافة شريك جديد 🏢';
    };

    return (
        <Dialog
            open={open}
            onClose={handleClose}
            maxWidth="md"
            fullWidth
            dir="rtl"
            PaperProps={{ sx: { borderRadius: 3, boxShadow: '0 8px 32px rgba(0,0,0,0.1)' } }}
        >
            <DialogTitle sx={{ fontWeight: 'bold', fontFamily: 'Cairo', bgcolor: '#f8faff', color: '#1a237e', borderBottom: '1px solid #e0e6ed', py: 2 }}>
                {getTitle()}
            </DialogTitle>

            <Box sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: '#fff' }}>
                <Tabs value={tabValue} onChange={handleTabChange} variant="fullWidth" indicatorColor="primary" sx={{ '& .MuiTab-root': { fontFamily: 'Cairo', fontWeight: 'bold' } }}>
                    <Tab icon={<PersonIcon />} label="البيانات الأساسية" iconPosition="start" />
                    <Tab icon={<MoneyIcon />} label="البيانات المالية" iconPosition="start" />
                    <Tab icon={<BankIcon />} label="الحسابات البنكية" iconPosition="start" />
                </Tabs>
            </Box>

            <DialogContent dividers sx={{ maxHeight: '70vh', bgcolor: '#fcfdfe' }}>
                {tabValue === 0 && (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
                        <Grid container spacing={2.5}>
                            <Grid item xs={6}>
                                <TextField label="الاسم التجاري" name="name" value={formData.name} onChange={handleChange} fullWidth required disabled={readOnly} InputProps={{ sx: { fontFamily: 'Cairo' } }} />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField label="الاسم القانوني" name="legal_name" value={formData.legal_name} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={12}><Divider>العنوان والموقع</Divider></Grid>
                            <Grid item xs={12}>
                                <TextField label="عنوان الشارع" name="street_address" value={formData.street_address} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={4}>
                                <TextField label="المدينة" name="city" value={formData.city} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={4}>
                                <TextField label="المنطقة/المحافظة" name="state_or_province" value={formData.state_or_province} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={4}>
                                <TextField label="الرمز البريدي" name="postal_code" value={formData.postal_code} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField label="الدولة" name="country" value={formData.country} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField label="الرقم الضريبي" name="tax_number" value={formData.tax_number} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={12}><Divider>معلومات الاتصال</Divider></Grid>
                            <Grid item xs={6}>
                                <TextField label="الهاتف" name="phone" value={formData.phone} onChange={handleChange} fullWidth required disabled={readOnly} />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField label="البريد الإلكتروني" name="email" value={formData.email} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={6}>
                                <FormControl fullWidth disabled={readOnly}>
                                    <InputLabel>نوع الشريك</InputLabel>
                                    <Select name="partner_type" value={formData.partner_type} onChange={handleChange} label="نوع الشريك">
                                        <MenuItem value="Customer">عميل</MenuItem>
                                        <MenuItem value="Supplier">مورد</MenuItem>
                                        <MenuItem value="FreightForwarder">شركة شحن</MenuItem>
                                        <MenuItem value="CustomsBroker">مخلص جمركي</MenuItem>
                                        <MenuItem value="LocalTransporter">ناقل محلي</MenuItem>
                                    </Select>
                                </FormControl>
                            </Grid>
                        </Grid>
                        {!readOnly && (
                            <Button
                                variant="outlined"
                                component="label"
                                fullWidth
                                disabled={uploadingImage}
                                sx={{ borderStyle: 'dashed', py: 2, borderColor: '#cbd5e1', color: '#64748b' }}
                            >
                                {uploadingImage ? 'جاري الرفع...' : 'رفع صورة الشريك'}
                                <CloudUploadIcon sx={{ mr: 1 }} />
                                <input type="file" hidden accept="image/*" onChange={handleImageChange} />
                            </Button>
                        )}
                        {formData.image_path && typeof formData.image_path === 'string' && (
                            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
                                <Avatar
                                    src={formData.image_path.startsWith('http') ? formData.image_path : `http://localhost:8000/media/${formData.image_path}`}
                                    variant="rounded"
                                    sx={{ width: 100, height: 100, border: '2px solid #e0e6ed' }}
                                />
                            </Box>
                        )}
                        {!readOnly && (
                            <Button
                                variant="outlined"
                                component="label"
                                fullWidth
                                disabled={uploadingDocument}
                                sx={{ borderStyle: 'dashed', py: 2, borderColor: '#cbd5e1', color: '#64748b', mt: 1 }}
                            >
                                {uploadingDocument ? 'جاري رفع الملف...' : 'رفع مستند الشريك (PDF, Docs)'}
                                <CloudUploadIcon sx={{ mr: 1 }} />
                                <input type="file" hidden onChange={handleDocumentChange} />
                            </Button>
                        )}
                        {formData.document_url && (
                            <Typography variant="caption" align="center" sx={{ color: '#2ecc71', fontWeight: 'bold', display: 'block', mt: 1 }}>
                                ✅ تم رفع المستند: <a href={formData.document_url} target="_blank" rel="noopener noreferrer">عرض الملف</a>
                            </Typography>
                        )}
                    </Box>
                )}

                {tabValue === 1 && (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
                        <Grid container spacing={2.5}>
                            <Grid item xs={6}>
                                <TextField label="الحد الائتماني" name="credit_limit" type="number" value={formData.credit_limit} onChange={handleChange} fullWidth disabled={readOnly} InputProps={{ endAdornment: <InputAdornment position="end">ILS</InputAdornment> }} />
                            </Grid>
                            <Grid item xs={6}>
                                <FormControl fullWidth disabled={readOnly}>
                                    <InputLabel>العملة الافتراضية</InputLabel>
                                    <Select name="currency" value={formData.currency} onChange={handleChange} label="العملة الافتراضية">
                                        <MenuItem value="">اختر العملة</MenuItem>
                                        <MenuItem value="1">ILS - شيكل</MenuItem>
                                        <MenuItem value="2">USD - دولار</MenuItem>
                                        <MenuItem value="3">EUR - يورو</MenuItem>
                                        <MenuItem value="4">JOD - دينار</MenuItem>
                                    </Select>
                                </FormControl>
                            </Grid>
                            <Grid item xs={6}>
                                <TextField label="الرصيد الافتتاحي" name="opening_balance" type="number" value={formData.opening_balance} onChange={handleChange} fullWidth disabled={readOnly} />
                            </Grid>
                            <Grid item xs={6}>
                                <TextField label="تاريخ الرصيد" name="opening_balance_date" type="date" value={formData.opening_balance_date} onChange={handleChange} fullWidth disabled={readOnly} InputLabelProps={{ shrink: true }} />
                            </Grid>
                        </Grid>
                    </Box>
                )}

                {tabValue === 2 && (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography variant="subtitle2" fontWeight="bold" sx={{ fontFamily: 'Cairo', color: '#1a237e' }}>الحسابات البنكية</Typography>
                            {!readOnly && <Button variant="contained" size="small" startIcon={<AddIcon />} onClick={addBankAccount}>إضافة حساب</Button>}
                        </Box>
                        {bankAccounts.length === 0 && <Typography align="center" sx={{ py: 4, color: '#94a3b8' }}>لا توجد حسابات مسجلة</Typography>}
                        {bankAccounts.map((account, index) => (
                            <Paper key={index} sx={{ p: 2, border: '1px solid #e0e6ed', borderRadius: 2, mb: 1, position: 'relative' }}>
                                {!readOnly && <IconButton onClick={() => removeBankAccount(index)} sx={{ position: 'absolute', top: 5, left: 5, color: 'error.main' }} size="small"><DeleteIcon /></IconButton>}
                                <Grid container spacing={2}>
                                    <Grid item xs={12}><TextField label="اسم البنك" value={account.bank_name} onChange={(e) => updateBankAccount(index, 'bank_name', e.target.value)} fullWidth size="small" disabled={readOnly} /></Grid>
                                    <Grid item xs={6}><TextField label="رقم الحساب" value={account.account_number} onChange={(e) => updateBankAccount(index, 'account_number', e.target.value)} fullWidth size="small" disabled={readOnly} /></Grid>
                                    <Grid item xs={6}><TextField label="IBAN" value={account.iban} onChange={(e) => updateBankAccount(index, 'iban', e.target.value)} fullWidth size="small" disabled={readOnly} /></Grid>
                                    <Grid item xs={6}>
                                        <FormControl fullWidth size="small" disabled={readOnly}>
                                            <InputLabel>العملة</InputLabel>
                                            <Select value={account.currency} onChange={(e) => updateBankAccount(index, 'currency', e.target.value)} label="العملة">
                                                <MenuItem value="1">ILS</MenuItem>
                                                <MenuItem value="2">USD</MenuItem>
                                                <MenuItem value="3">EUR</MenuItem>
                                                <MenuItem value="4">JOD</MenuItem>
                                            </Select>
                                        </FormControl>
                                    </Grid>
                                </Grid>
                            </Paper>
                        ))}
                    </Box>
                )}
            </DialogContent>

            <DialogActions sx={{ p: 2, bgcolor: '#f8faff' }}>
                <Button onClick={handleClose}>{readOnly ? 'إغلاق' : 'إلغاء'}</Button>
                {!readOnly && <Button onClick={handleSubmit} variant="contained">حفظ البيانات</Button>}
            </DialogActions>
        </Dialog>
    );
};

export default PartnerForm;

