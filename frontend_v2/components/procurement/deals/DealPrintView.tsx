import React, { useRef } from 'react';
import { Deal, User, Supplier } from '../../../types';
import { formatMoney } from '../../../utils/formatNumber';
import { Printer, X, MapPin, Phone, Mail, FileText, Building2, Truck, Hash, Calendar, DollarSign, CreditCard, Edit, ExternalLink } from 'lucide-react';
import { formatDateValue } from "../../../utils/formatDate";

interface DealPrintViewProps {
    deal: Deal;
    currentUser: User;
    supplier?: Supplier;
    onClose?: () => void;
    onEdit?: () => void;
}

export const DealPrintView: React.FC<DealPrintViewProps> = ({ deal, currentUser, supplier, onClose, onEdit }) => {
    const componentRef = useRef<HTMLDivElement>(null);

    const handlePrint = () => {
        window.print();
    };

    const totalPaid = Number(deal.postedPaidAmount) || 0;
    const unpostedAmount = Number(deal.unpostedRegisteredAmount) || 0;
    const subtotal = deal.subtotal || deal.items.reduce((sum, item) => sum + item.totalPrice, 0);

    // G1: عرض الأرقام عبر formatMoney — بلا أصفار عشرية زائدة
    const formatCurrency = (amount: number) => `$${formatMoney(Number(amount) || 0)}`;

    const formatDate = (dateString?: string) => {
        if (!dateString) return '-';
        return formatDateValue(dateString);
    };

    const getSupplierAddress = () => {
        if (!supplier) return 'العنوان غير مسجل';
        return [supplier.street, supplier.city, supplier.country].filter(Boolean).join('، ');
    };

    return (
        <div className="w-full min-h-screen ktra-bg-panel flex justify-center overflow-auto py-8 print:p-0 print:ktra-bg-field print:static print:block relative" dir="rtl">
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
            <div className="absolute top-4 right-4 flex gap-2 no-print z-[60]">
                <button onClick={handlePrint} className="flex items-center gap-2 ktra-bg-panel text-white px-4 py-2 rounded-full shadow-lg hover:ktra-bg-panel font-bold text-sm">
                    <Printer size={16} /> طباعة التقرير
                </button>

                {onEdit && (
                    <button onClick={onEdit} className="flex items-center gap-2 ktra-bg-panel text-white px-4 py-2 rounded-full shadow-lg hover:ktra-bg-panel font-bold text-sm">
                        <Edit size={16} /> تعديل البيانات
                    </button>
                )}

                {onClose && (
                    <button onClick={onClose} className="flex items-center gap-2 ktra-bg-field ktra-text-ink px-4 py-2 rounded-full shadow-lg hover:ktra-bg-panel border ktra-border-soft font-bold text-sm">
                        <X size={16} /> إغلاق
                    </button>
                )}
            </div>

            <div
                id="print-portal"
                ref={componentRef}
                className="w-[210mm] min-h-[297mm] ktra-bg-field shadow-2xl p-8 relative flex flex-col ktra-text-ink print:shadow-none print:w-full print:h-auto font-sans"
            >
                {/* 1. Header */}
                <div className="flex justify-between items-center border-b-2 ktra-border-soft pb-4 mb-4">
                    <div className="flex gap-4 items-center">
                        <div className="ktra-bg-panel text-white p-3 rounded-xl">
                            <FileText size={28} />
                        </div>
                        <div>
                            <h1 className="text-2xl font-black ktra-text-ink leading-none">تقرير صفقة شامل</h1>
                            <p className="text-xs font-bold ktra-text-soft mt-1">INTERNAL DEAL REPORT</p>
                        </div>
                    </div>

                    <div className="text-left text-xs space-y-1">
                        <div className="flex gap-2 justify-end"><span className="font-bold ktra-text-ink text-sm">{deal.dealNumber}</span> <span className="ktra-text-soft">REF:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium ktra-text-ink">{formatDate(new Date().toISOString())}</span> <span className="ktra-text-soft">PRINTED:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium ktra-text-ink">{currentUser.name}</span> <span className="ktra-text-soft">USER:</span></div>
                    </div>
                </div>

                {/* 2. Key Metrics Grid */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                    {[
                        { label: 'الحالة', value: deal.status, color: 'ktra-bg-accent-bg ktra-text-ink' },
                        { label: 'التاريخ', value: formatDate(deal.dealDate), mono: true },
                        { label: 'رقم العرض', value: deal.originalOfferNumber || '-', mono: true },
                        { label: 'الإجمالي', value: formatCurrency(deal.totalAmount), color: 'text-green-700', mono: true }
                    ].map((item, i) => (
                        <div key={i} className="border ktra-border-soft rounded-lg p-3 ktra-bg-panel">
                            <span className="text-[10px] ktra-text-soft font-bold uppercase block mb-1">{item.label}</span>
                            <span className={`text-sm font-bold ${item.color || ''} ${item.mono ? 'font-mono' : ''}`}>{item.value}</span>
                        </div>
                    ))}
                </div>

                {/* 3. Detailed Info Grid */}
                <div className="grid grid-cols-2 gap-4 mb-4 text-[11px]">
                    <div className="border ktra-border-soft rounded-lg overflow-hidden">
                        <div className="ktra-bg-panel px-3 py-2 border-b ktra-border-soft flex justify-between items-center">
                            <span className="font-bold flex items-center gap-1.5"><Building2 size={14} /> بيانات المورد</span>
                            <span className="font-mono text-[10px] ktra-text-soft">ID: {deal.supplierId}</span>
                        </div>
                        <div className="p-3 space-y-2">
                            <div className="flex justify-between"><span className="ktra-text-soft">الاسم:</span> <span className="font-bold text-sm">{deal.factoryName}</span></div>
                            <div className="flex justify-between"><span className="ktra-text-soft">العنوان:</span> <span className="text-left">{getSupplierAddress()}</span></div>
                            <div className="flex justify-between"><span className="ktra-text-soft">الهاتف:</span> <span className="dir-ltr font-medium">{supplier?.phone || supplier?.mobile || '-'}</span></div>
                            <div className="flex justify-between"><span className="ktra-text-soft">الايميل:</span> <span className="dir-ltr">{supplier?.email || '-'}</span></div>
                        </div>
                    </div>

                    <div className="border ktra-border-soft rounded-lg overflow-hidden">
                        <div className="ktra-bg-panel px-3 py-2 border-b ktra-border-soft flex justify-between items-center">
                            <span className="font-bold flex items-center gap-1.5"><Truck size={14} /> الشحن واللوجستيات</span>
                        </div>
                        <div className="p-3 grid grid-cols-2 gap-x-6 gap-y-2">
                            <div className="flex justify-between"><span className="ktra-text-soft">الشحن:</span> <span className="font-bold">{deal.shippingMethod || '-'}</span></div>
                            <div className="flex justify-between"><span className="ktra-text-soft">المدة:</span> <span className="font-bold">{deal.deliveryDays || '-'} يوم</span></div>
                            <div className="flex justify-between"><span className="ktra-text-soft">الوزن:</span> <span className="dir-ltr font-bold">{deal.totalWeight ? `${deal.totalWeight} KG` : '-'}</span></div>
                            <div className="flex justify-between"><span className="ktra-text-soft">الحجم:</span> <span className="dir-ltr font-bold">{deal.totalVolume ? `${deal.totalVolume} CBM` : '-'}</span></div>
                            <div className="col-span-2 flex justify-between border-t ktra-border-soft pt-2 mt-1">
                                <span className="ktra-text-soft">ملاحظات:</span>
                                <span className="italic font-medium">{deal.shipmentNotes || '-'}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 4. Items Table */}
                <div className="mb-4 border ktra-border-soft rounded-lg overflow-hidden shadow-sm">
                    <table className="w-full text-right border-collapse">
                        <thead className="ktra-bg-panel text-white text-[10px] font-bold">
                            <tr>
                                <th className="py-2 px-2 w-8 text-center border-r ktra-border-soft">#</th>
                                <th className="py-2 px-2 text-center w-12 border-r ktra-border-soft">صورة</th>
                                <th className="py-2 px-3 border-r ktra-border-soft">الصنف والمواصفات</th>
                                <th className="py-2 px-2 w-24 border-r ktra-border-soft">التصنيف</th>
                                <th className="py-2 px-2 w-14 text-center border-r ktra-border-soft">الكمية</th>
                                <th className="py-2 px-2 w-24 text-left border-r ktra-border-soft">سعر الوحدة</th>
                                <th className="py-2 px-2 w-24 text-left">الإجمالي</th>
                            </tr>
                        </thead>
                        <tbody className="text-[11px]">
                            {deal.items.map((item, index) => (
                                <tr key={item.id} className="border-b ktra-border-soft last:border-0 hover:ktra-bg-panel">
                                    <td className="py-2 px-2 text-center border-l ktra-border-soft ktra-text-soft">{index + 1}</td>
                                    <td className="py-2 px-2 text-center border-l ktra-border-soft">
                                        {item.imageUrls?.[0] && (
                                            <a href={item.imageUrls[0]} target="_blank" rel="noreferrer">
                                                <img src={item.imageUrls[0]} className="w-10 h-10 object-cover border ktra-border-soft rounded shadow-sm mx-auto hover:scale-110 transition-transform" alt="" />
                                            </a>
                                        )}
                                    </td>
                                    <td className="py-2 px-3 border-l ktra-border-soft">
                                        <p className="font-bold ktra-text-ink text-[12px]">{item.name}</p>
                                        <p className="text-[10px] ktra-text-soft leading-relaxed mt-1 line-clamp-2">{item.specifications}</p>
                                        <div className="flex gap-3 mt-1 text-[9px] ktra-text-soft font-mono">
                                            <span>HS: {item.hsCodePrimary || '-'}</span>
                                            {item.modelNumber && <span>MODEL: <span className="ktra-text-ink font-bold">{item.modelNumber}</span></span>}
                                        </div>
                                    </td>
                                    <td className="py-2 px-2 border-l ktra-border-soft ktra-text-soft">{item.categoryName}</td>
                                    <td className="py-2 px-2 text-center font-bold border-l ktra-border-soft text-sm">{item.quantity}</td>
                                    <td className="py-2 px-2 text-left font-mono border-l ktra-border-soft" dir="ltr">{formatCurrency(item.unitPrice)}</td>
                                    <td className="py-2 px-2 text-left font-bold font-mono ktra-bg-panel text-sm" dir="ltr">{formatCurrency(item.totalPrice)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* 5. Payments & Financials */}
                <div className="flex gap-4 text-[11px]">
                    <div className="flex-1 border ktra-border-soft rounded-lg overflow-hidden">
                        <div className="ktra-bg-panel px-3 py-2 border-b ktra-border-soft font-bold flex justify-between items-center">
                            <span className="flex items-center gap-1.5"><CreditCard size={14} /> سجل المدفوعات</span>
                            <span className="text-[10px] ktra-bg-field px-2 py-0.5 rounded border ktra-border-soft">{deal.payments?.length || 0} دفعة</span>
                        </div>
                        <table className="w-full text-[10px]">
                            <thead>
                                <tr className="border-b ktra-border-soft ktra-bg-panel ktra-text-soft uppercase">
                                    <th className="py-2 px-3 text-right">التاريخ</th>
                                    <th className="py-2 px-3 text-right">النوع</th>
                                    <th className="py-2 px-3 text-right">الحالة</th>
                                    <th className="py-2 px-3 text-right">الترحيل</th>
                                    <th className="py-2 px-3 text-right">القيد</th>
                                    <th className="py-2 px-3 text-left">المبلغ</th>
                                </tr>
                            </thead>
                            <tbody>
                                {deal.payments?.length ? (
                                    deal.payments.map((p, i) => (
                                        <tr key={i} className="border-b ktra-border-soft last:border-0 hover:ktra-bg-accent-bg/30">
                                            <td className="py-2 px-3">{formatDate(p.paymentDate)}</td>
                                            <td className="py-2 px-3 font-medium">{p.type === 'deposit' ? 'دفعة أولى' : 'دفعة متبقية'}</td>
                                            <td className="py-2 px-3">
                                                {p.confirmedBySupplier ? <span className="text-green-600 font-bold">● مؤكدة</span> : <span className="ktra-text-soft font-bold">○ قيد الانتظار</span>}
                                            </td>
                                            <td className="py-2 px-3">{p.isPosted ? "مرحّلة" : "غير مرحّلة"}</td>
                                            <td className="py-2 px-3">{p.journalId ? `#${p.journalId}` : "—"}</td>
                                            <td className="py-2 px-3 text-left font-mono font-bold" dir="ltr">{formatCurrency(p.amount)}</td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr><td colSpan={6} className="py-4 text-center ktra-text-soft italic">لا توجد سجلات دفع</td></tr>
                                )}
                            </tbody>
                            <tfoot className="ktra-bg-panel font-bold border-t-2 ktra-border-soft text-sm">
                                <tr>
                                    <td colSpan={5} className="py-2 px-3 text-left">إجمالي المدفوع والمرحّل:</td>
                                    <td className="py-2 px-3 text-left font-mono text-green-700" dir="ltr">{formatCurrency(totalPaid)}</td>
                                </tr>
                            </tfoot>
                        </table>
                    </div>

                    <div className="w-64 border ktra-border-soft rounded-lg overflow-hidden h-fit shadow-sm">
                        <div className="ktra-bg-panel text-white px-3 py-2 text-center font-bold">الملخص المالي النهائي</div>
                        <div className="p-3 space-y-2.5">
                            <div className="flex justify-between border-b ktra-border-soft pb-1.5">
                                <span className="ktra-text-soft">المجموع الفرعي:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatCurrency(subtotal)}</span>
                            </div>
                            {deal.discountAmount > 0 && (
                                <div className="flex justify-between border-b ktra-border-soft pb-1.5 text-green-600">
                                    <span>الخصم المكتسب:</span>
                                    <span className="font-mono font-bold" dir="ltr">- {formatCurrency(deal.discountAmount)}</span>
                                </div>
                            )}
                            {deal.taxAmount > 0 && (
                                <div className="flex justify-between border-b ktra-border-soft pb-1.5">
                                    <span>الضرائب:</span>
                                    <span className="font-mono font-bold" dir="ltr">{formatCurrency(deal.taxAmount)}</span>
                                </div>
                            )}
                            <div className="flex justify-between border-b ktra-border-soft pb-1.5">
                                <span className="ktra-text-soft">تكلفة الشحن:</span>
                                <span className="font-mono font-bold" dir="ltr">{deal.shippingIncluded ? '0.00' : formatCurrency(deal.shippingCost)}</span>
                            </div>
                            <div className="flex justify-between pt-2 font-black text-lg ktra-bg-panel -mx-3 px-3 border-t ktra-border-soft">
                                <span>الإجمالي:</span>
                                <span className="font-mono" dir="ltr">{formatCurrency(deal.totalAmount)}</span>
                            </div>
                            <div className="flex justify-between pt-1 ktra-text-state font-bold text-sm">
                                <span>المبلغ المتبقي:</span>
                                <span className="font-mono" dir="ltr">{formatCurrency(deal.amountOutstanding ?? deal.remainingAmount)}</span>
                            </div>
                            <div className="flex justify-between pt-1 text-sm">
                                <span>مسجّل بانتظار الترحيل:</span>
                                <span className="font-mono" dir="ltr">{formatCurrency(unpostedAmount)}</span>
                            </div>
                            <div className="flex justify-between pt-1 text-sm">
                                <span>رصيد المورد قبل دفعات الصفقة (بالعملة الأساسية):</span>
                                <span className="font-mono" dir="ltr">{formatMoney(deal.supplierBalanceBeforeDealPayments || 0)}</span>
                            </div>
                            <div className="flex justify-between pt-1 text-sm">
                                <span>رصيد المورد الحالي بعد الدفعات المرحّلة (بالعملة الأساسية):</span>
                                <span className="font-mono" dir="ltr">{formatMoney(deal.supplierBalanceAfterDealPayments || 0)}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* 6. Footer Notes */}
                <div className="mt-4 border ktra-border-soft rounded-lg p-3 ktra-bg-panel text-[11px]">
                    <span className="font-bold ktra-text-soft block mb-1">ملاحظات التقرير:</span>
                    <p className="font-bold ktra-text-ink leading-relaxed">{deal.internalNotes || "لا توجد ملاحظات إضافية مسجلة لهذه الصفقة."}</p>
                </div>

                {/* 7. Attachments Section - التعديل الكبير هنا */}
                <div className="mt-4 border ktra-border-soft rounded-lg p-3 ktra-bg-field no-print">
                    <div className="font-bold text-[11px] ktra-text-soft mb-2 flex items-center gap-1.5">
                        <FileText size={14} /> المرفقات والملفات الرقمية (انقر للفتح):
                    </div>

                    {(() => {
                        const d = deal as any;
                        const pdfs = d.quotePdfs || d.quote_pdfs || [];
                        const images = d.quoteImages || d.quote_images || [];
                        const hasAttachments = pdfs.length > 0 || images.length > 0;

                        if (!hasAttachments) return <span className="text-[10px] ktra-text-soft italic px-2">لا توجد مرفقات مرتبطة.</span>;

                        return (
                            <div className="flex flex-wrap gap-3">
                                {/* PDFs */}
                                {pdfs.map((pdf: any, idx: number) => (
                                    <a
                                        key={idx}
                                        href={pdf.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-2 ktra-bg-field border ktra-border-soft rounded-md px-3 py-2 hover:ktra-bg-panel hover:ktra-border-soft transition-all group"
                                    >
                                        <FileText size={18} className="ktra-text-soft" />
                                        <div className="flex flex-col">
                                            <span className="text-[10px] font-bold ktra-text-ink truncate max-w-[120px]">{pdf.name}</span>
                                            <span className="text-[8px] ktra-text-soft font-bold uppercase flex items-center gap-1">Open PDF <ExternalLink size={8} /></span>
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
                                        className="relative w-14 h-14 rounded-md border-2 ktra-border-soft overflow-hidden hover:ktra-border-soft transition-all shadow-sm group"
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

                <div className="mt-auto pt-4 border-t ktra-border-soft flex justify-between text-[10px] ktra-text-soft font-medium">
                    <p>Internal Secure Document - Unauthorized sharing is prohibited</p>
                    <p>Generated: {new Date().toLocaleString('en-GB')}</p>
                </div>
            </div>
        </div>
    );
};
