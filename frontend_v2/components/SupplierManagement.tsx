// import React, { useEffect, useState } from 'react';
// import { Supplier } from '../types';
// import { suppliersService } from '../services/firestoreService';

// // هوك بسيط للكشف عن وضع الجهاز (Dark/Light)
// const useSystemTheme = () => {
//   const [isDark, setIsDark] = useState(
//     window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
//   );

//   useEffect(() => {
//     const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
//     const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
//     mediaQuery.addEventListener('change', handler);
//     return () => mediaQuery.removeEventListener('change', handler);
//   }, []);

//   return isDark;
// };

// const SupplierManagement: React.FC = () => {
//   const isDark = useSystemTheme();
//   const [suppliers, setSuppliers] = useState<Supplier[]>([]);
//   const [isAdding, setIsAdding] = useState(false);
//   const [editingId, setEditingId] = useState<string | null>(null);
//   const [error, setError] = useState<string | null>(null);

//   // إزالة supplierId من الحالة الأولية لأنه سيتم توليده في السيرفر عند الإضافة
//   // أو جلبه عند التعديل
//   const [form, setForm] = useState({
//     tradeName: '',
//     phone: '',
//     mobile: '',
//     street: '',
//     city: '',
//     region: '',
//     postalCode: '',
//     country: '',
//     supplierId: '', // للعرض فقط عند التعديل
//     currency: 'ILS',
//     openingBalance: 0,
//     balanceDate: new Date().toISOString().split('T')[0],
//     email: '',
//     notes: ''
//   });

//   // تعريف الألوان بناءً على الثيم
//   const theme = {
//     bg: isDark ? 'dark:bg-blue-900' : '#ffffff',
//     text: isDark ? '#e0e0e0' : '#333333',
//     cardBg: isDark ? '#2d2d2d' : '#f9f9f9',
//     border: isDark ? '#444' : '#ddd',
//     inputBg: isDark ? '#333' : '#fff',
//     inputText: isDark ? '#fff' : '#000',
//     thBg: isDark ? '#333' : '#f0f0f0',
//     hover: isDark ? '#3a3a3a' : '#f5f5f5'
//   };

//   const commonInputStyle = {
//     width: '100%',
//     padding: 8,
//     border: `1px solid ${theme.border}`,
//     borderRadius: 4,
//     backgroundColor: theme.inputBg,
//     color: theme.inputText,
//     outline: 'none'
//   };

//   useEffect(() => {
//     const unsubscribe = suppliersService.subscribeToSuppliers((data) => {
//       setSuppliers(data);
//     });
//     return () => unsubscribe && unsubscribe();
//   }, []);

//   const handleFormChange = (field: string, value: any) => {
//     setForm(prev => ({ ...prev, [field]: value }));
//   };

//   const handleAdd = () => {
//     setIsAdding(true);
//     setEditingId(null);
//     setForm({
//       tradeName: '',
//       phone: '',
//       mobile: '',
//       street: '',
//       city: '',
//       region: '',
//       postalCode: '',
//       country: '',
//       supplierId: '', // فارغ عند الإضافة الجديدة
//       currency: 'ILS',
//       openingBalance: 0,
//       balanceDate: new Date().toISOString().split('T')[0],
//       email: '',
//       notes: ''
//     });
//   };

//   const handleEdit = (supplier: Supplier) => {
//     setIsAdding(true);
//     setEditingId(supplier.id);
//     setForm({
//       tradeName: supplier.tradeName,
//       phone: supplier.phone || '',
//       mobile: supplier.mobile || '',
//       street: supplier.street || '',
//       city: supplier.city || '',
//       region: supplier.region || '',
//       postalCode: supplier.postalCode || '',
//       country: supplier.country || '',
//       supplierId: supplier.supplierId, // هنا نضع القيمة الموجودة
//       currency: supplier.currency || 'ILS',
//       openingBalance: supplier.openingBalance || 0,
//       balanceDate: supplier.balanceDate || new Date().toISOString().split('T')[0],
//       email: supplier.email || '',
//       notes: supplier.notes || ''
//     });
//   };

//   const handleSave = async () => {
//     if (!form.tradeName.trim()) {
//       setError('الاسم التجاري مطلوب');
//       return;
//     }
//     // لا نتحقق من supplierId عند الإضافة لأنه يتم توليده تلقائياً

//     try {
//       setError(null);
//       if (editingId) {
//         // تحديث مورد موجود
//         const existingSupplier = suppliers.find(s => s.id === editingId);
//         const supplier: Supplier = {
//           id: editingId,
//           ...form,
//           // نتأكد من عدم تغيير supplierId عند التعديل، نأخذ القديم
//           supplierId: existingSupplier?.supplierId || form.supplierId, 
//           createdAt: existingSupplier?.createdAt || new Date().toISOString(),
//           updatedAt: new Date().toISOString()
//         };
//         await suppliersService.updateSupplierInDb(supplier);
//       } else {
//         // إضافة مورد جديد (بدون إرسال supplierId، السيرفر يتكفل به)
//         // نقوم بإزالة supplierId من الـ form المرسل
//         const { supplierId, ...newSupplierData } = form;
//         await suppliersService.addSupplierToDb(newSupplierData);
//       }
//       setIsAdding(false);
//       setEditingId(null);
//     } catch (err: any) {
//       setError(err.message || 'حدث خطأ');
//     }
//   };

//   const handleDelete = async (id: string) => {
//     if (!confirm('هل تريد حذف هذا المورد؟')) return;
//     try {
//       setError(null);
//       await suppliersService.deleteSupplierFromDb(id);
//     } catch (err: any) {
//       setError(err.message || 'فشل الحذف');
//     }
//   };

//   const handleCancel = () => {
//     setIsAdding(false);
//     setEditingId(null);
//     setError(null);
//   };

//   return (
//     <div style={{ 
//       padding: 16, 
//       maxWidth: 1200, 
//       margin: '0 auto', 
//       fontFamily: 'Segoe UI, Tahoma, Geneva, Verdana, sans-serif',
//       backgroundColor: theme.bg,
//       color: theme.text,
//       minHeight: '100vh',
//       transition: 'background-color 0.3s, color 0.3s'
//     }}>
//       <h1 style={{ marginBottom: 40 }} className="text-2xl font-bold">إدارة الموردين</h1>


//       {error && <div style={{ color: '#ff4d4d', padding: 10, backgroundColor: 'rgba(255,0,0,0.1)', marginBottom: 16, borderRadius: 4, border: '1px solid #ff4d4d' }}>{error}</div>}

//       {!isAdding && (
//         <button onClick={handleAdd} style={{ padding: '10px 20px', marginBottom: 20, cursor: 'pointer', backgroundColor: '#4CAF50', color: 'white', border: 'none', borderRadius: 6, fontSize: '16px', fontWeight: 'bold' }}>
//           + إضافة مورد جديد
//         </button>
//       )}

//       {isAdding && (
//         <div style={{ border: `1px solid ${theme.border}`, padding: 24, marginBottom: 20, borderRadius: 8, backgroundColor: theme.cardBg }}>
//           <h3 style={{ marginTop: 0, marginBottom: 20 }}>{editingId ? 'تعديل بيانات المورد' : 'إضافة مورد جديد'}</h3>

//           <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 16, marginBottom: 16 }}>
//             {/* بيانات المورد */}
//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>الاسم التجاري *</label>
//               <input type="text" placeholder="الاسم التجاري" value={form.tradeName} onChange={(e) => handleFormChange('tradeName', e.target.value)} style={commonInputStyle} />
//             </div>

//             {/* عرض رقم المورد فقط في حالة التعديل */}
//             {editingId && (
//               <div>
//                 <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>رقم المورد</label>
//                 <input 
//                   type="text" 
//                   value={form.supplierId} 
//                   disabled 
//                   style={{ ...commonInputStyle, backgroundColor: isDark ? '#444' : '#e9e9e9', cursor: 'not-allowed', opacity: 0.8 }} 
//                   title="يتم توليد رقم المورد تلقائياً ولا يمكن تعديله"
//                 />
//               </div>
//             )}
            
//             {!editingId && (
//                <div style={{ display: 'flex', alignItems: 'center', color: isDark ? '#aaa' : '#666', fontSize: '0.9em' }}>
//                  <i>سيتم تعيين رقم المورد تلقائياً بعد الحفظ (مثل: 0001)</i>
//                </div>
//             )}

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>الهاتف</label>
//               <input type="text" placeholder="الهاتف" value={form.phone} onChange={(e) => handleFormChange('phone', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>جوال</label>
//               <input type="text" placeholder="جوال" value={form.mobile} onChange={(e) => handleFormChange('mobile', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>عنوان الشارع</label>
//               <input type="text" placeholder="عنوان الشارع" value={form.street} onChange={(e) => handleFormChange('street', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>المدينة</label>
//               <input type="text" placeholder="المدينة" value={form.city} onChange={(e) => handleFormChange('city', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>المنطقة</label>
//               <input type="text" placeholder="المنطقة" value={form.region} onChange={(e) => handleFormChange('region', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>الرمز البريدي</label>
//               <input type="text" placeholder="الرمز البريدي" value={form.postalCode} onChange={(e) => handleFormChange('postalCode', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>البلد</label>
//               <input type="text" placeholder="البلد" value={form.country} onChange={(e) => handleFormChange('country', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>العملة</label>
//               <select value={form.currency} onChange={(e) => handleFormChange('currency', e.target.value)} style={commonInputStyle}>
//                 <option value="ILS">ILS - شيكل إسرائيلي جديد</option>
//                 <option value="USD">USD - دولار أمريكي</option>
//                 <option value="EUR">EUR - يورو</option>
//                 <option value="AED">AED - درهم إماراتي</option>
//                 <option value="SAR">SAR - ريال سعودي</option>
//                 <option value="JOD">JOD - دينار أردني</option>
//               </select>
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>الرصيد الافتتاحي</label>
//               <input type="number" placeholder="0.00" value={form.openingBalance} onChange={(e) => handleFormChange('openingBalance', parseFloat(e.target.value) || 0)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>تاريخ الرصيد الافتتاحي</label>
//               <input type="date" value={form.balanceDate} onChange={(e) => handleFormChange('balanceDate', e.target.value)} style={commonInputStyle} />
//             </div>

//             <div>
//               <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>البريد الإلكتروني</label>
//               <input type="email" placeholder="example@domain.com" value={form.email} onChange={(e) => handleFormChange('email', e.target.value)} style={commonInputStyle} />
//             </div>
//           </div>

//           <div>
//             <label style={{ display: 'block', marginBottom: 6, fontWeight: 'bold', fontSize: '0.9em' }}>الملاحظات</label>
//             <textarea placeholder="أي ملاحظات إضافية..." value={form.notes} onChange={(e) => handleFormChange('notes', e.target.value)} style={{ ...commonInputStyle, minHeight: 80, resize: 'vertical' }} />
//           </div>

//           <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
//             <button onClick={handleSave} style={{ padding: '10px 24px', cursor: 'pointer', backgroundColor: '#2196F3', color: 'white', border: 'none', borderRadius: 4, fontWeight: 'bold' }}>
//               حفظ
//             </button>
//             <button onClick={handleCancel} style={{ padding: '10px 24px', cursor: 'pointer', backgroundColor: isDark ? '#555' : '#ccc', color: isDark ? '#fff' : '#333', border: 'none', borderRadius: 4 }}>
//               إلغاء
//             </button>
//           </div>
//         </div>
//       )}

//       {/* Suppliers List */}
//       {suppliers.length === 0 ? (
//         <div style={{ color: isDark ? '#aaa' : '#666', padding: 20, textAlign: 'center', border: `1px dashed ${theme.border}`, borderRadius: 8 }}>
//           لا توجد موردين بعد. قم بإضافة مورد جديد.
//         </div>
//       ) : (
//         <div style={{ overflowX: 'auto', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
//           <table style={{ width: '100%', borderCollapse: 'collapse', backgroundColor: theme.cardBg }}>
//             <thead>
//               <tr style={{ backgroundColor: theme.thBg, borderBottom: `2px solid ${theme.border}` }}>
//                 <th style={{ padding: 12, textAlign: 'right', color: theme.text }}>الاسم التجاري</th>
//                 <th style={{ padding: 12, textAlign: 'right', color: theme.text }}>رقم المورد</th>
//                 <th style={{ padding: 12, textAlign: 'right', color: theme.text }}>الهاتف</th>
//                 <th style={{ padding: 12, textAlign: 'right', color: theme.text }}>الجوال</th>
//                 <th style={{ padding: 12, textAlign: 'right', color: theme.text }}>البريد الإلكتروني</th>
//                 <th style={{ padding: 12, textAlign: 'right', color: theme.text }}>الرصيد</th>
//                 <th style={{ padding: 12, textAlign: 'center', color: theme.text }}>الإجراءات</th>
//               </tr>
//             </thead>
//             <tbody>
//               {suppliers.map(supplier => (
//                 <tr key={supplier.id} style={{ borderBottom: `1px solid ${theme.border}`, transition: 'background-color 0.2s' }}>
//                   <td style={{ padding: 12 }}>{supplier.tradeName}</td>
//                   <td style={{ padding: 12 }}>
//                     <span style={{ backgroundColor: isDark ? '#3a3a3a' : '#eef', padding: '2px 6px', borderRadius: 4, fontSize: '0.9em', fontFamily: 'monospace' }}>
//                       {supplier.supplierId}
//                     </span>
//                   </td>
//                   <td style={{ padding: 12 }}>{supplier.phone || '-'}</td>
//                   <td style={{ padding: 12 }}>{supplier.mobile || '-'}</td>
//                   <td style={{ padding: 12 }}>{supplier.email || '-'}</td>
//                   <td style={{ padding: 12, fontWeight: 'bold' }}>{supplier.openingBalance ? `${supplier.openingBalance} ${supplier.currency || 'ILS'}` : '-'}</td>
//                   <td style={{ padding: 12, textAlign: 'center', display: 'flex', gap: 8, justifyContent: 'center' }}>
//                     <button onClick={() => handleEdit(supplier)} style={{ padding: '6px 14px', cursor: 'pointer', backgroundColor: '#FF9800', color: 'white', border: 'none', borderRadius: 4, fontSize: '0.9em' }}>
//                       تعديل
//                     </button>
//                     <button onClick={() => handleDelete(supplier.id)} style={{ padding: '6px 14px', cursor: 'pointer', backgroundColor: '#f44336', color: 'white', border: 'none', borderRadius: 4, fontSize: '0.9em' }}>
//                       حذف
//                     </button>
//                   </td>
//                 </tr>
//               ))}
//             </tbody>
//           </table>
//         </div>
//       )}
//     </div>
//   );
// };

// export default SupplierManagement;