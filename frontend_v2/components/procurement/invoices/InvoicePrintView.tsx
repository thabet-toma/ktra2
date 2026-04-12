import React, { useRef } from 'react';
import { Invoice, User, Supplier } from '../../../types';
import { formatTaxPercentLabel } from '../../../utils/sqlMoneyRound';
import { Printer, X, MapPin, Phone, Mail, FileText, Building2, Truck, Hash, Calendar, DollarSign, CreditCard, Edit, ExternalLink, Box } from 'lucide-react';

interface InvoicePrintViewProps {
    invoice: Invoice;
    currentUser: User;
    supplier?: Supplier;
    onClose?: () => void;
    onEdit?: () => void;
}

export const InvoicePrintView: React.FC<InvoicePrintViewProps> = ({ invoice, currentUser, supplier, onClose, onEdit }) => {
    const componentRef = useRef<HTMLDivElement>(null);

    const handlePrint = () => {
        window.print();
    };

    const formatCurrency = (amount: number) => {
        const symbol = invoice.currency === 'ILS' ? '₪' : '$';
        return `${symbol}${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    };

    const formatDate = (dateString?: string) => {
        if (!dateString) return '-';
        return new Date(dateString).toLocaleDateString('en-GB');
    };

    const printLanded = invoice.items.some(
        (it) =>
            (it.landedUnitPriceIls ?? 0) > 0 && (it.landedLineTotalIls ?? 0) > 0
    );

    const getSupplierAddress = () => {
        if (invoice.supplierSnapshot?.address) return invoice.supplierSnapshot.address;
        if (!supplier) return 'العنوان غير مسجل';
        return [supplier.street, supplier.city, supplier.country].filter(Boolean).join('، ');
    };

    const getSupplierName = () => {
        if (invoice.supplierSnapshot?.tradeName) {
            return invoice.supplierSnapshot.alias
                ? `${invoice.supplierSnapshot.tradeName} (${invoice.supplierSnapshot.alias})`
                : invoice.supplierSnapshot.tradeName;
        }
        if (!supplier) return invoice.factoryName || 'مورد غير محدد';
        return supplier.alias || supplier.tradeName || invoice.factoryName || 'مورد غير محدد';
    };

    // Calculate totals if not provided
    const calculateTotals = () => {
        const subtotal = invoice.subtotal || invoice.items.reduce((sum, item) => sum + item.totalPrice, 0);
        const discountAmount = invoice.discountAmount || 0;
        const netAfterDiscount = Math.max(0, subtotal - discountAmount);
        const taxAmount = invoice.taxAmount || 0;
        const shippingCost = invoice.shippingIncluded ? 0 : (invoice.shippingCost || 0);
        const grandTotal = invoice.grandTotal || (netAfterDiscount + taxAmount + shippingCost);

        return { subtotal, discountAmount, taxAmount, shippingCost, grandTotal };
    };

    const totals = calculateTotals();

    return (
        <div className="fixed inset-0 z-50 bg-gray-100 flex justify-center overflow-auto py-8 print:p-0 print:bg-white print:static print:block" dir="rtl">
            <style>
                {`
                    @media print {
                        @page { size: A4; margin: 10mm; }
                        body > * { display: none !important; }
                        #print-portal { display: block !important; }
                        #print-portal { 
                            position: absolute; left: 0; top: 0; width: 100%; margin: 0; padding: 0;
                            background: white; 
                        }
                        .no-print { display: none !important; }
                        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
                    }
                    .dir-ltr { direction: ltr; text-align: left; }
                `}
            </style>

            {/* Print Controls */}
            <div className="fixed top-4 right-4 flex gap-2 no-print z-[60]">
                <button onClick={handlePrint} className="flex items-center gap-2 bg-blue-900 text-white px-4 py-2 rounded-full shadow-lg hover:bg-blue-800 font-bold text-sm">
                    <Printer size={16} /> طباعة الفاتورة
                </button>

                {onEdit && (
                    <button onClick={onEdit} className="flex items-center gap-2 bg-amber-500 text-white px-4 py-2 rounded-full shadow-lg hover:bg-amber-600 font-bold text-sm">
                        <Edit size={16} /> تعديل البيانات
                    </button>
                )}

                {onClose && (
                    <button onClick={onClose} className="flex items-center gap-2 bg-white text-gray-700 px-4 py-2 rounded-full shadow-lg hover:bg-gray-100 border border-gray-200 font-bold text-sm">
                        <X size={16} /> إغلاق
                    </button>
                )}
            </div>

            <div
                id="print-portal"
                ref={componentRef}
                className="w-[210mm] min-h-[297mm] bg-white shadow-2xl p-8 relative flex flex-col text-gray-900 print:shadow-none print:w-full print:h-auto font-sans"
            >
                {/* 1. Header */}
                <div className="flex justify-between items-center border-b-2 border-gray-800 pb-4 mb-4">
                    <div className="flex gap-4 items-center">
                        <div className="bg-gray-900 text-white p-3 rounded-xl">
                            <FileText size={28} />
                        </div>
                        <div>
                            <h1 className="text-2xl font-black text-gray-900 leading-none">فاتورة مشتريات</h1>
                            <p className="text-xs font-bold text-gray-500 mt-1">PURCHASE INVOICE - {invoice.currency === 'ILS' ? 'NIS' : 'USD'}</p>
                        </div>
                    </div>

                    <div className="text-left text-xs space-y-1">
                        <div className="flex gap-2 justify-end"><span className="font-bold text-gray-900 text-sm">{invoice.invoiceNumber}</span> <span className="text-gray-500">REF:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium text-gray-800">{formatDate(invoice.invoiceDate || invoice.createdAt)}</span> <span className="text-gray-500">DATE:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium text-gray-800">{currentUser.name}</span> <span className="text-gray-500">USER:</span></div>
                    </div>
                </div>

                {/* 2. Key Metrics Grid */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                    {[
                        { label: 'الحالة', value: invoice.status === 'completed' ? 'مكتملة' : 'قيد المعالجة', color: invoice.status === 'completed' ? 'bg-green-100 text-green-800' : 'bg-blue-100 text-blue-800' },
                        { label: 'التاريخ', value: formatDate(invoice.invoiceDate), mono: true },
                        { label: 'رقم الصفقة', value: invoice.dealNumber || '-', mono: true },
                        { label: 'الإجمالي', value: formatCurrency(totals.grandTotal), color: 'text-green-700 font-black', mono: true }
                    ].map((item, i) => (
                        <div key={i} className="border border-gray-200 rounded-lg p-3 bg-gray-50">
                            <span className="text-[10px] text-gray-500 font-bold uppercase block mb-1">{item.label}</span>
                            <span className={`text-sm font-bold ${item.color || ''} ${item.mono ? 'font-mono' : ''}`}>{item.value}</span>
                        </div>
                    ))}
                </div>

                {/* 3. Detailed Info Grid */}
                <div className="grid grid-cols-2 gap-4 mb-4 text-[11px]">
                    <div className="border border-gray-300 rounded-lg overflow-hidden">
                        <div className="bg-gray-100 px-3 py-2 border-b border-gray-300 flex justify-between items-center">
                            <span className="font-bold flex items-center gap-1.5"><Building2 size={14} /> بيانات المورد</span>
                        </div>
                        <div className="p-3 space-y-2">
                            <div className="flex justify-between"><span className="text-gray-500">الاسم:</span> <span className="font-bold text-sm">{getSupplierName()}</span></div>
                            <div className="flex justify-between"><span className="text-gray-500">العنوان:</span> <span className="text-left">{getSupplierAddress()}</span></div>
                            <div className="flex justify-between"><span className="text-gray-500">مندوب المبيعات:</span> <span className="font-medium">{invoice.supplierSnapshot?.salesRepName || '-'}</span></div>
                            <div className="flex justify-between"><span className="text-gray-500">الهاتف:</span> <span className="dir-ltr font-medium">{invoice.supplierSnapshot?.salesRepPhone || supplier?.phone || '-'}</span></div>
                        </div>
                    </div>

                    <div className="border border-gray-300 rounded-lg overflow-hidden">
                        <div className="bg-gray-100 px-3 py-2 border-b border-gray-300 flex justify-between items-center">
                            <span className="font-bold flex items-center gap-1.5"><Truck size={14} /> الشحن واللوجستيات</span>
                        </div>
                        <div className="p-3 grid grid-cols-2 gap-x-6 gap-y-2">
                            <div className="flex justify-between"><span className="text-gray-500">طريقة الشحن:</span> <span className="font-bold">{invoice.dealInfo?.shippingMethod || '-'}</span></div>
                            <div className="flex justify-between"><span className="text-gray-500">الوزن الإجمالي:</span> <span className="dir-ltr font-bold">{invoice.totalWeight ? `${invoice.totalWeight} KG` : '-'}</span></div>
                            <div className="flex justify-between"><span className="text-gray-500">الحجم الإجمالي:</span> <span className="dir-ltr font-bold">{invoice.totalVolume ? `${invoice.totalVolume} CBM` : '-'}</span></div>
                            <div className="col-span-2 flex justify-between border-t border-gray-100 pt-2 mt-1">
                                <span className="text-gray-500">ملاحظات الصفقة:</span>
                                <span className="italic font-medium">{invoice.dealInfo?.internalNotes || '-'}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 4. Items Table */}
                <div className="mb-4 border border-gray-300 rounded-lg overflow-hidden shadow-sm">
                    <table className="w-full text-right border-collapse">
                        <thead className="bg-gray-800 text-white text-[10px] font-bold">
                            <tr>
                                <th className="py-2 px-2 w-8 text-center border-r border-gray-600">#</th>
                                <th className="py-2 px-2 text-center w-12 border-r border-gray-600">صورة</th>
                                <th className="py-2 px-3 border-r border-gray-600">الصنف والمواصفات</th>
                                <th className="py-2 px-2 w-24 border-r border-gray-600">التصنيف</th>
                                <th className="py-2 px-2 w-14 text-center border-r border-gray-600">الكمية</th>
                                <th className="py-2 px-2 w-24 text-left border-r border-gray-600">سعر الوحدة</th>
                                {printLanded && (
                                    <th className="py-2 px-2 w-28 text-left border-r border-gray-600 bg-amber-900/90">نهائي / وحدة</th>
                                )}
                                <th className="py-2 px-2 w-24 text-left border-r border-gray-600">الإجمالي</th>
                                {printLanded && (
                                    <th className="py-2 px-2 w-28 text-left bg-amber-900/90">إجمالي نهائي</th>
                                )}
                            </tr>
                        </thead>
                        <tbody className="text-[11px]">
                            {invoice.items.map((item, index) => (
                                <tr key={index} className="border-b border-gray-200 last:border-0 hover:bg-gray-50">
                                    <td className="py-2 px-2 text-center border-l border-gray-200 text-gray-500">{index + 1}</td>
                                    <td className="py-2 px-2 text-center border-l border-gray-200">
                                        {(item.imageUrls?.[0] || item.factoryImageUrl) && (
                                            <a href={item.imageUrls?.[0] || item.factoryImageUrl} target="_blank" rel="noreferrer">
                                                <img src={item.imageUrls?.[0] || item.factoryImageUrl} className="w-10 h-10 object-cover border border-gray-200 rounded shadow-sm mx-auto" alt="" />
                                            </a>
                                        )}
                                    </td>
                                    <td className="py-2 px-3 border-l border-gray-200">
                                        <p className="font-bold text-gray-900 text-[12px]">{item.name}</p>
                                        <p className="text-[10px] text-gray-500 leading-relaxed mt-1">{item.specifications}</p>
                                        {item.notes && (
                                            <div className="mt-1 p-1 bg-yellow-50 border border-yellow-100 rounded text-[9px] text-amber-700 italic">
                                                ملاحظة: {item.notes}
                                            </div>
                                        )}
                                        <div className="flex gap-3 mt-1 text-[9px] text-gray-400 font-mono">
                                            <span>HS: {item.hsCodePrimary || '-'}</span>
                                            {item.modelNumber && <span>MODEL: <span className="text-gray-700 font-bold">{item.modelNumber}</span></span>}
                                        </div>
                                    </td>
                                    <td className="py-2 px-2 border-l border-gray-200 text-gray-600">{item.categoryName}</td>
                                    <td className="py-2 px-2 text-center font-bold border-l border-gray-200 text-sm">{item.quantity}</td>
                                    <td className="py-2 px-2 text-left font-mono border-l border-gray-200" dir="ltr">{formatCurrency(item.unitPrice)}</td>
                                    {printLanded && (
                                        <td className="py-2 px-2 text-left font-mono border-l border-gray-200 bg-amber-50" dir="ltr">
                                            {item.landedUnitPriceIls != null ? formatCurrency(item.landedUnitPriceIls) : "—"}
                                        </td>
                                    )}
                                    <td className="py-2 px-2 text-left font-bold font-mono bg-gray-50 text-sm border-l border-gray-200" dir="ltr">{formatCurrency(item.totalPrice)}</td>
                                    {printLanded && (
                                        <td className="py-2 px-2 text-left font-bold font-mono bg-amber-50 text-sm" dir="ltr">
                                            {item.landedLineTotalIls != null ? formatCurrency(item.landedLineTotalIls) : "—"}
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* 5. Financial Summary Row */}
                <div className="flex justify-end mb-4">
                    <div className="w-64 border border-gray-300 rounded-lg overflow-hidden h-fit shadow-sm">
                        <div className="bg-gray-800 text-white px-3 py-2 text-center font-bold">ملخص مالي</div>
                        <div className="p-3 space-y-2.5 text-[11px]">
                            <div className="flex justify-between border-b border-gray-100 pb-1.5">
                                <span className="text-gray-500">المجموع الفرعي:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatCurrency(totals.subtotal)}</span>
                            </div>
                            {totals.discountAmount > 0 && (
                                <div className="flex justify-between border-b border-gray-100 pb-1.5 text-green-600">
                                    <span>الخصم:</span>
                                    <span className="font-mono font-bold" dir="ltr">- {formatCurrency(totals.discountAmount)}</span>
                                </div>
                            )}
                            {totals.taxAmount > 0 && (
                                <div className="flex justify-between border-b border-gray-100 pb-1.5">
                                    <span>الضرائب ({formatTaxPercentLabel(invoice.taxRate)}%):</span>
                                    <span className="font-mono font-bold" dir="ltr">{formatCurrency(totals.taxAmount)}</span>
                                </div>
                            )}
                            <div className="flex justify-between border-b border-gray-100 pb-1.5">
                                <span className="text-gray-500">تكلفة الشحن:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatCurrency(totals.shippingCost)}</span>
                            </div>
                            <div className="flex justify-between pt-2 font-black text-lg bg-gray-50 -mx-3 px-3 border-t border-gray-200">
                                <span>الإجمالي:</span>
                                <span className="font-mono" dir="ltr">{formatCurrency(totals.grandTotal)}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 6. Attachments Section */}
                <div className="mt-4 border border-gray-200 rounded-lg p-3 bg-white no-print">
                    <div className="font-bold text-[11px] text-gray-500 mb-2 flex items-center gap-1.5">
                        <FileText size={14} /> المرفقات والملفات الرقمية (انقر للفتح):
                    </div>

                    {(() => {
                        const pdfs = invoice.quotePdfs || invoice.dealInfo?.quotePdfs || [];
                        const images = invoice.quoteImages || invoice.dealInfo?.quoteImages || [];
                        const hasAttachments = pdfs.length > 0 || images.length > 0;

                        if (!hasAttachments) return <span className="text-[10px] text-gray-400 italic px-2">لا توجد مرفقات مرتبطة.</span>;

                        return (
                            <div className="flex flex-wrap gap-3">
                                {/* PDFs */}
                                {pdfs.map((pdf: any, idx: number) => (
                                    <a
                                        key={idx}
                                        href={pdf.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-2 bg-white border border-red-200 rounded-md px-3 py-2 hover:bg-red-50 hover:border-red-400 transition-all group"
                                    >
                                        <FileText size={18} className="text-red-500" />
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-bold text-gray-700 truncate max-w-[120px]">{pdf.name}</span>
                                            <span className="text-[8px] text-red-400 font-bold uppercase flex items-center gap-1">Open PDF <ExternalLink size={8} /></span>
                                        </div>
                                    </a>
                                ))}

                                {/* Images */}
                                {images.map((img: string, idx: number) => (
                                    <a
                                        key={idx}
                                        href={img}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="relative w-14 h-14 rounded-md border-2 border-gray-100 overflow-hidden hover:border-blue-400 transition-all shadow-sm group"
                                    >
                                        <img src={img} alt="" className="w-full h-full object-cover group-hover:scale-110 transition-transform" />
                                        <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                                            <ExternalLink size={12} className="text-white" />
                                        </div>
                                    </a>
                                ))}
                            </div>
                        );
                    })()}
                </div>

                <div className="mt-auto pt-4 border-t border-gray-200 flex justify-between text-[10px] text-gray-400 font-medium">
                    <p>Internal Secure Document - Unauthorized sharing is prohibited</p>
                    <p>Generated: {new Date().toLocaleString('en-GB')}</p>
                </div>
            </div>
        </div>
    );
};
