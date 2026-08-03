import React, { useRef } from 'react';
import { Invoice, User, Supplier } from '../../../types';
import { formatTaxPercentLabel } from '../../../utils/sqlMoneyRound';
import { formatMoney, formatQuantity } from '../../../utils/formatNumber';
import { useTenantSettings } from '../../../hooks/useTenantSettings';
import { Printer, X, MapPin, Phone, Mail, FileText, Building2, Truck, Hash, Calendar, DollarSign, CreditCard, Edit, ExternalLink, Box } from 'lucide-react';
import { formatDateValue } from "../../../utils/formatDate";

interface InvoicePrintViewProps {
    invoice: Invoice;
    currentUser: User;
    supplier?: Supplier;
    onClose?: () => void;
    onEdit?: () => void;
}

export const InvoicePrintView: React.FC<InvoicePrintViewProps> = ({ invoice, currentUser, supplier, onClose, onEdit }) => {
    const componentRef = useRef<HTMLDivElement>(null);
    // M2: هوية الشركة النشطة في ترويسة الطباعة
    const { identity } = useTenantSettings();

    const handlePrint = () => {
        window.print();
    };

    const formatCurrency = (amount: number) => {
        const symbol = invoice.currency === 'ILS' ? '₪' : '$';
        return `${symbol}${formatMoney(amount)}`;
    };

    const formatDate = (dateString?: string) => {
        if (!dateString) return '-';
        return formatDateValue(dateString);
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
        <div className="fixed inset-0 z-50 aseel-bg-panel flex justify-center overflow-auto py-8 print:p-0 print:aseel-bg-field print:static print:block" dir="rtl">
            <style>
                {`
                    @media print {
                        @page { size: A4; margin: 10mm; }
                        body * { visibility: hidden; }
                        #print-portal, #print-portal * { visibility: visible; }
                        #print-portal { 
                            position: absolute; left: 0; top: 0; width: 100%; margin: 0; padding: 0;
                            background: white; 
                        }
                        .no-print, .no-print * { display: none !important; visibility: hidden !important; }
                        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
                    }
                    .dir-ltr { direction: ltr; text-align: left; }
                `}
            </style>

            {/* Print Controls */}
            <div className="fixed top-4 right-4 flex gap-2 no-print z-[60]">
                <button onClick={handlePrint} className="flex items-center gap-2 aseel-bg-panel text-white px-4 py-2 rounded-full shadow-lg hover:aseel-bg-panel font-bold text-sm">
                    <Printer size={16} /> طباعة الفاتورة
                </button>

                {onEdit && (
                    <button onClick={onEdit} className="flex items-center gap-2 aseel-bg-panel text-white px-4 py-2 rounded-full shadow-lg hover:aseel-bg-panel font-bold text-sm">
                        <Edit size={16} /> تعديل البيانات
                    </button>
                )}

                {onClose && (
                    <button onClick={onClose} className="flex items-center gap-2 aseel-bg-field aseel-text-ink px-4 py-2 rounded-full shadow-lg hover:aseel-bg-panel border aseel-border-soft font-bold text-sm">
                        <X size={16} /> إغلاق
                    </button>
                )}
            </div>

            <div
                id="print-portal"
                ref={componentRef}
                className="w-[210mm] min-h-[297mm] aseel-bg-field shadow-2xl p-8 relative flex flex-col aseel-text-ink print:shadow-none print:w-full print:h-auto font-sans"
            >
                {/* 1. Header */}
                <div className="flex justify-between items-center border-b-2 aseel-border-soft pb-4 mb-4">
                    <div className="flex gap-4 items-center">
                        {identity?.logo_url ? (
                            <img src={identity.logo_url} alt="شعار الشركة" className="w-14 h-14 rounded-xl object-cover border aseel-border-soft" />
                        ) : (
                            <div className="aseel-bg-panel text-white p-3 rounded-xl">
                                <FileText size={28} />
                            </div>
                        )}
                        <div>
                            {identity?.company_name_primary && (
                                <div className="text-lg font-black aseel-text-ink leading-tight">{identity.company_name_primary}</div>
                            )}
                            {(identity?.address || identity?.phone) && (
                                <div className="text-[10px] aseel-text-soft">
                                    {[identity?.address, identity?.phone && `هاتف: ${identity.phone}`].filter(Boolean).join(' — ')}
                                </div>
                            )}
                            <h1 className={`font-black aseel-text-ink leading-none ${identity?.company_name_primary ? 'text-base mt-1' : 'text-2xl'}`}>فاتورة مشتريات</h1>
                            <p className="text-xs font-bold aseel-text-soft mt-1">PURCHASE INVOICE - {invoice.currency === 'ILS' ? 'NIS' : 'USD'}</p>
                        </div>
                    </div>

                    <div className="text-left text-xs space-y-1">
                        <div className="flex gap-2 justify-end"><span className="font-bold aseel-text-ink text-sm">{invoice.invoiceNumber}</span> <span className="aseel-text-soft">REF:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium aseel-text-ink">{formatDate(invoice.invoiceDate || invoice.createdAt)}</span> <span className="aseel-text-soft">DATE:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium aseel-text-ink">{currentUser.name}</span> <span className="aseel-text-soft">USER:</span></div>
                    </div>
                </div>

                {/* 2. Key Metrics Grid */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                    {[
                        { label: 'الحالة', value: invoice.status === 'completed' ? 'مكتملة' : 'قيد المعالجة', color: invoice.status === 'completed' ? 'bg-green-100 text-green-800' : 'aseel-bg-accent-bg aseel-text-ink' },
                        { label: 'التاريخ', value: formatDate(invoice.invoiceDate), mono: true },
                        { label: 'رقم الصفقة', value: invoice.dealNumber || '-', mono: true },
                        { label: 'الإجمالي', value: formatCurrency(totals.grandTotal), color: 'text-green-700 font-black', mono: true }
                    ].map((item, i) => (
                        <div key={i} className="border aseel-border-soft rounded-lg p-3 aseel-bg-panel">
                            <span className="text-[10px] aseel-text-soft font-bold uppercase block mb-1">{item.label}</span>
                            <span className={`text-sm font-bold ${item.color || ''} ${item.mono ? 'font-mono' : ''}`}>{item.value}</span>
                        </div>
                    ))}
                </div>

                {/* 3. Detailed Info Grid */}
                <div className="grid grid-cols-2 gap-4 mb-4 text-[11px]">
                    <div className="border aseel-border-soft rounded-lg overflow-hidden">
                        <div className="aseel-bg-panel px-3 py-2 border-b aseel-border-soft flex justify-between items-center">
                            <span className="font-bold flex items-center gap-1.5"><Building2 size={14} /> بيانات المورد</span>
                        </div>
                        <div className="p-3 space-y-2">
                            <div className="flex justify-between"><span className="aseel-text-soft">الاسم:</span> <span className="font-bold text-sm">{getSupplierName()}</span></div>
                            <div className="flex justify-between"><span className="aseel-text-soft">العنوان:</span> <span className="text-left">{getSupplierAddress()}</span></div>
                            <div className="flex justify-between"><span className="aseel-text-soft">مندوب المبيعات:</span> <span className="font-medium">{invoice.supplierSnapshot?.salesRepName || '-'}</span></div>
                            <div className="flex justify-between"><span className="aseel-text-soft">الهاتف:</span> <span className="dir-ltr font-medium">{invoice.supplierSnapshot?.salesRepPhone || supplier?.phone || '-'}</span></div>
                        </div>
                    </div>

                    <div className="border aseel-border-soft rounded-lg overflow-hidden">
                        <div className="aseel-bg-panel px-3 py-2 border-b aseel-border-soft flex justify-between items-center">
                            <span className="font-bold flex items-center gap-1.5"><Truck size={14} /> الشحن واللوجستيات</span>
                        </div>
                        <div className="p-3 grid grid-cols-2 gap-x-6 gap-y-2">
                            <div className="flex justify-between"><span className="aseel-text-soft">طريقة الشحن:</span> <span className="font-bold">{invoice.dealInfo?.shippingMethod || '-'}</span></div>
                            <div className="flex justify-between"><span className="aseel-text-soft">الوزن الإجمالي:</span> <span className="dir-ltr font-bold">{invoice.totalWeight ? `${invoice.totalWeight} KG` : '-'}</span></div>
                            <div className="flex justify-between"><span className="aseel-text-soft">الحجم الإجمالي:</span> <span className="dir-ltr font-bold">{invoice.totalVolume ? `${invoice.totalVolume} CBM` : '-'}</span></div>
                            <div className="col-span-2 flex justify-between border-t aseel-border-soft pt-2 mt-1">
                                <span className="aseel-text-soft">ملاحظات الصفقة:</span>
                                <span className="italic font-medium">{invoice.dealInfo?.internalNotes || '-'}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 4. Items Table */}
                <div className="mb-4 border aseel-border-soft rounded-lg overflow-hidden shadow-sm">
                    <table className="w-full text-right border-collapse">
                        <thead className="aseel-bg-panel text-white text-[10px] font-bold">
                            <tr>
                                <th className="py-2 px-2 w-8 text-center border-r aseel-border-soft">#</th>
                                <th className="py-2 px-2 text-center w-12 border-r aseel-border-soft">صورة</th>
                                <th className="py-2 px-3 border-r aseel-border-soft">الصنف والمواصفات</th>
                                <th className="py-2 px-2 w-24 border-r aseel-border-soft">التصنيف</th>
                                <th className="py-2 px-2 w-14 text-center border-r aseel-border-soft">الكمية</th>
                                <th className="py-2 px-2 w-24 text-left border-r aseel-border-soft">سعر الوحدة</th>
                                {printLanded && (
                                    <th className="py-2 px-2 w-28 text-left border-r aseel-border-soft aseel-bg-panel/90">نهائي / وحدة</th>
                                )}
                                <th className="py-2 px-2 w-24 text-left border-r aseel-border-soft">الإجمالي</th>
                                {printLanded && (
                                    <th className="py-2 px-2 w-28 text-left aseel-bg-panel/90">إجمالي نهائي</th>
                                )}
                            </tr>
                        </thead>
                        <tbody className="text-[11px]">
                            {invoice.items.map((item, index) => (
                                <tr key={index} className="border-b aseel-border-soft last:border-0 hover:aseel-bg-panel">
                                    <td className="py-2 px-2 text-center border-l aseel-border-soft aseel-text-soft">{index + 1}</td>
                                    <td className="py-2 px-2 text-center border-l aseel-border-soft">
                                        {(item.imageUrls?.[0] || item.factoryImageUrl) && (
                                            <a href={item.imageUrls?.[0] || item.factoryImageUrl} target="_blank" rel="noreferrer">
                                                <img src={item.imageUrls?.[0] || item.factoryImageUrl} className="w-10 h-10 object-cover border aseel-border-soft rounded shadow-sm mx-auto" alt="" />
                                            </a>
                                        )}
                                    </td>
                                    <td className="py-2 px-3 border-l aseel-border-soft">
                                        <p className="font-bold aseel-text-ink text-[12px]">{item.name}</p>
                                        <p className="text-[10px] aseel-text-soft leading-relaxed mt-1">{item.specifications}</p>
                                        {item.notes && (
                                            <div className="mt-1 p-1 aseel-bg-panel border aseel-border-soft rounded text-[9px] aseel-text-ink italic">
                                                ملاحظة: {item.notes}
                                            </div>
                                        )}
                                        <div className="flex gap-3 mt-1 text-[9px] aseel-text-soft font-mono">
                                            <span>HS: {item.hsCodePrimary || '-'}</span>
                                            {item.modelNumber && <span>MODEL: <span className="aseel-text-ink font-bold">{item.modelNumber}</span></span>}
                                        </div>
                                    </td>
                                    <td className="py-2 px-2 border-l aseel-border-soft aseel-text-soft">{item.categoryName}</td>
                                    <td className="py-2 px-2 text-center font-bold border-l aseel-border-soft text-sm">{item.quantity}</td>
                                    <td className="py-2 px-2 text-left font-mono border-l aseel-border-soft" dir="ltr">{formatCurrency(item.unitPrice)}</td>
                                    {printLanded && (
                                        <td className="py-2 px-2 text-left font-mono border-l aseel-border-soft aseel-bg-panel" dir="ltr">
                                            {item.landedUnitPriceIls != null ? formatCurrency(item.landedUnitPriceIls) : "—"}
                                        </td>
                                    )}
                                    <td className="py-2 px-2 text-left font-bold font-mono aseel-bg-panel text-sm border-l aseel-border-soft" dir="ltr">{formatCurrency(item.totalPrice)}</td>
                                    {printLanded && (
                                        <td className="py-2 px-2 text-left font-bold font-mono aseel-bg-panel text-sm" dir="ltr">
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
                    <div className="w-64 border aseel-border-soft rounded-lg overflow-hidden h-fit shadow-sm">
                        <div className="aseel-bg-panel text-white px-3 py-2 text-center font-bold">ملخص مالي</div>
                        <div className="p-3 space-y-2.5 text-[11px]">
                            <div className="flex justify-between border-b aseel-border-soft pb-1.5">
                                <span className="aseel-text-soft">المجموع الفرعي:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatCurrency(totals.subtotal)}</span>
                            </div>
                            {totals.discountAmount > 0 && (
                                <div className="flex justify-between border-b aseel-border-soft pb-1.5 text-green-600">
                                    <span>الخصم:</span>
                                    <span className="font-mono font-bold" dir="ltr">- {formatCurrency(totals.discountAmount)}</span>
                                </div>
                            )}
                            {totals.taxAmount > 0 && (
                                <div className="flex justify-between border-b aseel-border-soft pb-1.5">
                                    <span>الضرائب ({formatTaxPercentLabel(invoice.taxRate)}%):</span>
                                    <span className="font-mono font-bold" dir="ltr">{formatCurrency(totals.taxAmount)}</span>
                                </div>
                            )}
                            <div className="flex justify-between border-b aseel-border-soft pb-1.5">
                                <span className="aseel-text-soft">تكلفة الشحن:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatCurrency(totals.shippingCost)}</span>
                            </div>
                            <div className="flex justify-between pt-2 font-black text-lg aseel-bg-panel -mx-3 px-3 border-t aseel-border-soft">
                                <span>الإجمالي:</span>
                                <span className="font-mono" dir="ltr">{formatCurrency(totals.grandTotal)}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">المدفوع المرحّل:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatCurrency(invoice.amountPaid || 0)}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">المتبقي:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatCurrency(invoice.remainingBalance || 0)}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">حالة الدفع:</span>
                                <span className="font-bold">{invoice.paymentStatusDisplay || "غير مدفوعة"}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">رصيد المورد قبل احتساب المتبقي (بالعملة الأساسية):</span>
                                <span className="font-mono font-bold" dir="ltr">{formatMoney(invoice.partnerBalanceBeforeInvoice || 0)}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">الرصيد الحالي بعد احتسابه (بالعملة الأساسية):</span>
                                <span className="font-mono font-bold" dir="ltr">{formatMoney(invoice.partnerBalanceAfterInvoice || 0)}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">إجمالي الكمية:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatQuantity((invoice.items || []).reduce((s, it) => s + (Number(it.quantity) || 0), 0))}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {!!invoice.paymentDetails?.length && (
                    <div className="mb-4 border aseel-border-soft rounded-lg overflow-hidden">
                        <div className="aseel-bg-panel px-3 py-2 border-b aseel-border-soft font-bold">تفاصيل دفعات المورد</div>
                        <table className="w-full text-[10px]">
                            <thead>
                                <tr className="border-b aseel-border-soft">
                                    <th className="p-2 text-right">السند</th>
                                    <th className="p-2 text-right">التاريخ</th>
                                    <th className="p-2 text-right">الصندوق/البنك</th>
                                    <th className="p-2 text-right">المبلغ</th>
                                    <th className="p-2 text-right">الحالة</th>
                                    <th className="p-2 text-right">القيد</th>
                                </tr>
                            </thead>
                            <tbody>
                                {invoice.paymentDetails.map((payment) => (
                                    <tr key={`${payment.source}-${payment.id}`} className="border-b aseel-border-soft">
                                        <td className="p-2">{payment.source === "supplier_payment" ? "سند صرف" : "دفعة فاتورة"} #{payment.id}</td>
                                        <td className="p-2">{formatDate(payment.paymentDate)}</td>
                                        <td className="p-2">{payment.cashOrBankAccountName || "—"}</td>
                                        <td className="p-2">{formatMoney(payment.amount)} {payment.currencyCode}</td>
                                        <td className="p-2">{payment.isPosted ? "مرحّل" : "غير مرحّل"}</td>
                                        <td className="p-2">{payment.journalId ? `#${payment.journalId}` : "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* 6. Attachments Section */}
                <div className="mt-4 border aseel-border-soft rounded-lg p-3 aseel-bg-field no-print">
                    <div className="font-bold text-[11px] aseel-text-soft mb-2 flex items-center gap-1.5">
                        <FileText size={14} /> المرفقات والملفات الرقمية (انقر للفتح):
                    </div>

                    {(() => {
                        const pdfs = invoice.quotePdfs || invoice.dealInfo?.quotePdfs || [];
                        const images = invoice.quoteImages || invoice.dealInfo?.quoteImages || [];
                        const hasAttachments = pdfs.length > 0 || images.length > 0;

                        if (!hasAttachments) return <span className="text-[10px] aseel-text-soft italic px-2">لا توجد مرفقات مرتبطة.</span>;

                        return (
                            <div className="flex flex-wrap gap-3">
                                {/* PDFs */}
                                {pdfs.map((pdf: any, idx: number) => (
                                    <a
                                        key={idx}
                                        href={pdf.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-2 aseel-bg-field border aseel-border-soft rounded-md px-3 py-2 hover:aseel-bg-panel hover:aseel-border-soft transition-all group"
                                    >
                                        <FileText size={18} className="aseel-text-soft" />
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-bold aseel-text-ink truncate max-w-[120px]">{pdf.name}</span>
                                            <span className="text-[8px] aseel-text-soft font-bold uppercase flex items-center gap-1">Open PDF <ExternalLink size={8} /></span>
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
                                        className="relative w-14 h-14 rounded-md border-2 aseel-border-soft overflow-hidden hover:aseel-border-soft transition-all shadow-sm group"
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

                <div className="mt-auto pt-4 border-t aseel-border-soft flex justify-between text-[10px] aseel-text-soft font-medium">
                    <p>Internal Secure Document - Unauthorized sharing is prohibited</p>
                    <p>Generated: {new Date().toLocaleString('en-GB')}</p>
                </div>
            </div>
        </div>
    );
};
