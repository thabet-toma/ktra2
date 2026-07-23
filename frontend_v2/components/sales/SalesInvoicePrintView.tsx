import React, { useRef } from 'react';
import { useTenantSettings } from '../../hooks/useTenantSettings';
import { Printer, X, FileText, Building2 } from 'lucide-react';
import { formatMoney, formatQuantity } from '../../utils/formatNumber';
import type { PartnerRow, ProductRow, DraftLine } from './SalesInvoiceEditor';

export interface SalesPrintData {
  invoiceNumber: string;
  invoiceDate: string;
  dueDate: string;
  invoiceType: "cash" | "credit";
  customer?: PartnerRow;
  lines: DraftLine[];
  productsById: Map<number, ProductRow>;
  totals: {
    subtotalExclTax: number;
    discountAmount: number;
    taxAmount: number;
    grandTotal: number;
    perLine: Array<{ lineTotal: number }>;
  };
  currentUserName?: string;
  notes?: string;
  currencyCode?: string;
  amountPaid: number;
  remainingBalance: number;
  paymentStatusDisplay: string;
  customerBalanceBeforeInvoice: number;
  customerBalanceAfterInvoice: number;
  paymentDetails: NonNullable<import("../../services/salesApi").SalesInvoiceDetail["payment_details"]>;
}

interface Props {
  data: SalesPrintData;
  onClose: () => void;
}

export const SalesInvoicePrintView: React.FC<Props> = ({ data, onClose }) => {
    const componentRef = useRef<HTMLDivElement>(null);
    const { identity } = useTenantSettings();

    const handlePrint = () => {
        window.print();
    };

    const formatDate = (dateString?: string) => {
        if (!dateString) return '-';
        return new Date(dateString).toLocaleDateString('en-GB');
    };

    const curr = data.currencyCode || 'ILS';

    return (
        <div className="fixed inset-0 z-[100] aseel-bg-panel flex justify-center overflow-auto py-8 print:p-0 print:aseel-bg-field print:static print:block" dir="rtl">
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

            <div className="fixed top-4 right-4 flex gap-2 no-print z-[60]">
                <button onClick={handlePrint} className="flex items-center gap-2 aseel-bg-panel text-white px-4 py-2 rounded-full shadow-lg hover:aseel-bg-panel font-bold text-sm border aseel-border-soft">
                    <Printer size={16} /> طباعة الفاتورة
                </button>

                <button onClick={onClose} className="flex items-center gap-2 aseel-bg-field aseel-text-ink px-4 py-2 rounded-full shadow-lg hover:aseel-bg-panel border aseel-border-soft font-bold text-sm">
                    <X size={16} /> إغلاق
                </button>
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
                            <h1 className={`font-black aseel-text-ink leading-none ${identity?.company_name_primary ? 'text-base mt-1' : 'text-2xl'}`}>فاتورة مبيعات</h1>
                            <p className="text-xs font-bold aseel-text-soft mt-1">SALES INVOICE</p>
                        </div>
                    </div>

                    <div className="text-left text-xs space-y-1">
                        <div className="flex gap-2 justify-end"><span className="font-bold aseel-text-ink text-sm">{data.invoiceNumber || 'مسودة'}</span> <span className="aseel-text-soft">رقم الفاتورة:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium aseel-text-ink">{formatDate(data.invoiceDate)}</span> <span className="aseel-text-soft">التاريخ:</span></div>
                        <div className="flex gap-2 justify-end"><span className="font-medium aseel-text-ink">{data.currentUserName || '-'}</span> <span className="aseel-text-soft">المستخدم:</span></div>
                    </div>
                </div>

                {/* 2. Key Metrics & Customer */}
                <div className="grid grid-cols-2 gap-4 mb-4 text-[11px]">
                    <div className="border aseel-border-soft rounded-lg overflow-hidden">
                        <div className="aseel-bg-panel px-3 py-2 border-b aseel-border-soft flex justify-between items-center text-white">
                            <span className="font-bold flex items-center gap-1.5"><Building2 size={14} /> بيانات العميل</span>
                        </div>
                        <div className="p-3 space-y-2">
                            <div className="flex justify-between"><span className="aseel-text-soft">الاسم:</span> <span className="font-bold text-sm">{data.customer?.name || 'عميل نقدي'}</span></div>
                        </div>
                    </div>

                    <div className="border aseel-border-soft rounded-lg overflow-hidden">
                        <div className="aseel-bg-panel px-3 py-2 border-b aseel-border-soft flex justify-between items-center text-white">
                            <span className="font-bold flex items-center gap-1.5"><FileText size={14} /> تفاصيل إضافية</span>
                        </div>
                        <div className="p-3 space-y-2">
                            <div className="flex justify-between"><span className="aseel-text-soft">نوع الفاتورة:</span> <span className="font-bold">{data.invoiceType === 'cash' ? 'نقدي' : 'ذمم'}</span></div>
                            <div className="flex justify-between"><span className="aseel-text-soft">تاريخ الاستحقاق:</span> <span className="font-bold">{formatDate(data.dueDate)}</span></div>
                        </div>
                    </div>
                </div>

                {/* 3. Items Table */}
                <div className="mb-4 border aseel-border-soft rounded-lg overflow-hidden shadow-sm">
                    <table className="w-full text-right border-collapse">
                        <thead className="aseel-bg-panel text-white text-[10px] font-bold">
                            <tr>
                                <th className="py-2 px-2 w-8 text-center border-r aseel-border-soft border-l">#</th>
                                <th className="py-2 px-3 border-l aseel-border-soft">الصنف</th>
                                <th className="py-2 px-2 w-14 text-center border-l aseel-border-soft">الكمية</th>
                                <th className="py-2 px-2 w-24 text-left border-l aseel-border-soft">سعر الوحدة</th>
                                <th className="py-2 px-2 w-24 text-left border-l aseel-border-soft">الإجمالي</th>
                            </tr>
                        </thead>
                        <tbody className="text-[11px]">
                            {data.lines.map((item, index) => {
                                if (item.product === "") return null;
                                const pr = data.productsById.get(Number(item.product));
                                const pName = pr ? (pr.name_ar || pr.name_en || pr.sku) : '';
                                const lineTotal = data.totals.perLine[index]?.lineTotal || 0;
                                return (
                                    <tr key={index} className="border-b aseel-border-soft last:border-0 hover:aseel-bg-panel">
                                        <td className="py-2 px-2 text-center border-l aseel-border-soft aseel-text-soft">{index + 1}</td>
                                        <td className="py-2 px-3 border-l aseel-border-soft">
                                            <p className="font-bold aseel-text-ink text-[12px]">{pName}</p>
                                        </td>
                                        <td className="py-2 px-2 text-center font-bold border-l aseel-border-soft text-sm">{item.quantity}</td>
                                        <td className="py-2 px-2 text-left font-mono border-l aseel-border-soft" dir="ltr">{formatMoney(Number(item.unit_price))} {curr}</td>
                                        <td className="py-2 px-2 text-left font-bold font-mono aseel-bg-panel text-sm" dir="ltr">{formatMoney(lineTotal)} {curr}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                {/* 4. Financial Summary Row */}
                <div className="flex justify-end mb-4">
                    <div className="w-64 border aseel-border-soft rounded-lg overflow-hidden h-fit shadow-sm">
                        <div className="aseel-bg-panel text-white px-3 py-2 text-center font-bold">ملخص مالي</div>
                        <div className="p-3 space-y-2.5 text-[11px]">
                            <div className="flex justify-between border-b aseel-border-soft pb-1.5">
                                <span className="aseel-text-soft">المجموع الفرعي:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatMoney(data.totals.subtotalExclTax)} {curr}</span>
                            </div>
                            {data.totals.discountAmount > 0 && (
                                <div className="flex justify-between border-b aseel-border-soft pb-1.5 text-green-600">
                                    <span>الخصم:</span>
                                    <span className="font-mono font-bold" dir="ltr">- {formatMoney(data.totals.discountAmount)} {curr}</span>
                                </div>
                            )}
                            {data.totals.taxAmount > 0 && (
                                <div className="flex justify-between border-b aseel-border-soft pb-1.5">
                                    <span>الضرائب:</span>
                                    <span className="font-mono font-bold" dir="ltr">{formatMoney(data.totals.taxAmount)} {curr}</span>
                                </div>
                            )}
                            <div className="flex justify-between pt-2 font-black text-lg aseel-bg-panel -mx-3 px-3 border-t aseel-border-soft text-white">
                                <span>الإجمالي:</span>
                                <span className="font-mono" dir="ltr">{formatMoney(data.totals.grandTotal)} {curr}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">المدفوع المرحّل:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatMoney(data.amountPaid)} {curr}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">المتبقي:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatMoney(data.remainingBalance)} {curr}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">حالة الدفع:</span>
                                <span className="font-bold">{data.paymentStatusDisplay}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">رصيد العميل قبل احتساب المتبقي (بالعملة الأساسية):</span>
                                <span className="font-mono font-bold" dir="ltr">{formatMoney(data.customerBalanceBeforeInvoice)}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">الرصيد الحالي بعد احتسابه (بالعملة الأساسية):</span>
                                <span className="font-mono font-bold" dir="ltr">{formatMoney(data.customerBalanceAfterInvoice)}</span>
                            </div>
                            <div className="flex justify-between pt-1.5">
                                <span className="aseel-text-soft">إجمالي الكمية:</span>
                                <span className="font-mono font-bold" dir="ltr">{formatQuantity(data.lines.reduce((s, l) => l.product === "" ? s : s + (Number(l.quantity) || 0), 0))}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {data.paymentDetails.length > 0 && (
                    <div className="mb-4 border aseel-border-soft rounded-lg overflow-hidden">
                        <div className="aseel-bg-panel px-3 py-2 border-b aseel-border-soft font-bold">تفاصيل سندات القبض</div>
                        <table className="w-full text-[10px]">
                            <thead>
                                <tr className="border-b aseel-border-soft">
                                    <th className="p-2 text-right">السند</th>
                                    <th className="p-2 text-right">التاريخ</th>
                                    <th className="p-2 text-right">المبلغ المخصص</th>
                                    <th className="p-2 text-right">الحالة</th>
                                    <th className="p-2 text-right">القيد</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.paymentDetails.map((payment) => (
                                    <tr key={payment.id} className="border-b aseel-border-soft">
                                        <td className="p-2">سند قبض #{payment.id}</td>
                                        <td className="p-2">{formatDate(payment.payment_date)}</td>
                                        <td className="p-2">{formatMoney(Number(payment.allocated_amount))} {curr}</td>
                                        <td className="p-2">{payment.is_posted ? "مرحّل" : "غير مرحّل"}</td>
                                        <td className="p-2">{payment.journal ? `#${payment.journal}` : "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {data.notes && (
                    <div className="mt-4 border aseel-border-soft rounded-lg p-3 aseel-bg-field">
                        <div className="font-bold text-[11px] aseel-text-soft mb-1">ملاحظات:</div>
                        <p className="text-[11px]">{data.notes}</p>
                    </div>
                )}

                <div className="mt-auto pt-4 border-t aseel-border-soft flex justify-between text-[10px] aseel-text-soft font-medium">
                    <p>Generated: {new Date().toLocaleString('en-GB')}</p>
                </div>
            </div>
        </div>
    );
};
