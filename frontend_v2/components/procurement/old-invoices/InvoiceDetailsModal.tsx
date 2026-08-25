import React from 'react';
import { Invoice } from '../../../types';
import {
    X, Calendar, Building, Package, Tag, FileText,
    Calculator, Download, ExternalLink, ImageIcon
} from 'lucide-react';
import { ItemsTableSection } from '../../forms/shared/ItemsTableSection';

interface InvoiceDetailsModalProps {
    isOpen: boolean;
    onClose: () => void;
    invoice: Invoice | null;
    allDbItems: any[];
}

export const InvoiceDetailsModal: React.FC<InvoiceDetailsModalProps> = ({
    isOpen,
    onClose,
    invoice,
    allDbItems
}) => {
    if (!isOpen || !invoice) return null;

    const handleDownloadPdf = (file: { name: string; url: string }) => {
        const link = document.createElement('a');
        link.href = file.url;
        link.download = file.name || 'document.pdf';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4 overflow-y-auto">
            <div className="ktra-bg-field dark:ktra-bg-panel rounded-2xl shadow-2xl w-full max-w-5xl my-8 flex flex-col relative animate-in fade-in zoom-in duration-200">
                {/* Header */}
                <div className="sticky top-0 ktra-bg-field dark:ktra-bg-panel p-6 border-b ktra-border-soft dark:ktra-border-soft flex justify-between items-center z-20 rounded-t-2xl">
                    <div className="flex items-center gap-3">
                        <div className="p-2 ktra-bg-accent-bg dark:ktra-bg-panel/30 rounded-lg">
                            <FileText className="w-6 h-6 ktra-text-accent dark:ktra-text-soft" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold ktra-text-ink dark:text-white">
                                تفاصيل الفاتورة
                            </h2>
                            <p className="text-sm ktra-text-soft dark:ktra-text-soft font-mono">
                                #{invoice.invoiceNumber}
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:ktra-bg-panel dark:hover:ktra-bg-panel rounded-lg transition-colors">
                        <X className="w-6 h-6 ktra-text-soft" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 md:p-8 space-y-8 overflow-y-auto max-h-[calc(100vh-150px)]">

                    {/* Basic Info Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div className="p-4 ktra-bg-panel dark:ktra-bg-panel/50 rounded-xl border ktra-border-soft dark:ktra-border-soft">
                            <div className="flex items-center gap-2 ktra-text-soft dark:ktra-text-soft mb-1">
                                <Calendar className="w-4 h-4" />
                                <span className="text-xs font-medium">تاريخ الفاتورة</span>
                            </div>
                            <div className="font-semibold ktra-text-ink dark:text-white text-lg">
                                {invoice.invoiceDate}
                            </div>
                        </div>
                        <div className="p-4 ktra-bg-panel dark:ktra-bg-panel/50 rounded-xl border ktra-border-soft dark:ktra-border-soft">
                            <div className="flex items-center gap-2 ktra-text-soft dark:ktra-text-soft mb-1">
                                <Building className="w-4 h-4" />
                                <span className="text-xs font-medium">المورد</span>
                            </div>
                            <div className="font-semibold ktra-text-ink dark:text-white text-lg truncate">
                                {invoice.factoryName || '-'}
                            </div>
                        </div>
                        <div className="p-4 ktra-bg-panel dark:ktra-bg-panel/50 rounded-xl border ktra-border-soft dark:ktra-border-soft">
                            <div className="flex items-center gap-2 ktra-text-soft dark:ktra-text-soft mb-1">
                                <Tag className="w-4 h-4" />
                                <span className="text-xs font-medium">الحالة</span>
                            </div>
                            <div className="font-semibold ktra-text-ink dark:text-white text-lg">
                                {invoice.isHistorical ? 'أرشيف' : 'نشطة'}
                            </div>
                        </div>
                    </div>

                    {/* Invoice Link Button */}
                    {invoice.invoiceLink && (
                        <a
                            href={invoice.invoiceLink}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-center gap-2 w-full p-4 ktra-bg-accent-bg dark:ktra-bg-panel/20 ktra-text-accent dark:ktra-text-soft rounded-xl border ktra-border-accent dark:ktra-border-soft hover:ktra-bg-accent-bg dark:hover:ktra-bg-panel/30 transition-colors font-semibold"
                        >
                            <ExternalLink className="w-5 h-5" />
                            فتح رابط الفاتورة
                        </a>
                    )}

                    {/* Items Table */}
                    <ItemsTableSection
                        items={invoice.items || []}
                        onUpdateItem={() => { }}
                        onRemoveItem={() => { }}
                        onAddItem={() => { }}
                        onPreviewImage={() => { }}
                        readOnly={true}
                        allDbItems={allDbItems}
                        productionDays={invoice.dealInfo?.productionDays}
                        deliveryDays={invoice.dealInfo?.deliveryDays}
                        paymentMethod={invoice.dealInfo?.paymentMethod}
                        shippingMethod={invoice.dealInfo?.shippingMethod}
                        warrantyDuration={invoice.dealInfo?.warrantyDuration}
                        totalWeight={invoice.totalWeight}
                        totalVolume={invoice.totalVolume}
                        certificates={invoice.dealInfo?.certificates}
                        shipmentNotes={invoice.dealInfo?.shipmentNotes || invoice.notes}
                        shippingCost={invoice.shippingCost}
                        shippingIncluded={invoice.shippingIncluded}
                        taxRate={invoice.taxRate}
                        taxAmount={invoice.taxAmount}
                        taxType={invoice.taxType}
                    />

                    {/* Footer: Attachments & Totals */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
                        {/* Attachments */}
                        <div className="space-y-4">
                            <h3 className="text-lg font-bold ktra-text-ink dark:text-white flex items-center gap-2">
                                <FileText className="w-5 h-5 ktra-text-soft" />
                                الملفات المرفقة
                            </h3>

                            {/* PDF List */}
                            {invoice.pdfFiles && invoice.pdfFiles.length > 0 ? (
                                <div className="space-y-2">
                                    {invoice.pdfFiles.map((file, idx) => (
                                        <div key={idx} className="flex items-center justify-between p-3 ktra-bg-panel dark:ktra-bg-panel/50 rounded-xl border ktra-border-soft dark:ktra-border-soft hover:ktra-border-soft dark:hover:ktra-border-soft transition-colors">
                                            <div className="flex items-center gap-3 overflow-hidden">
                                                <div className="p-2 ktra-bg-panel dark:ktra-bg-panel/30 rounded-lg">
                                                    <FileText className="w-5 h-5 ktra-text-state dark:ktra-text-soft" />
                                                </div>
                                                <div className="min-w-0">
                                                    <div className="font-medium ktra-text-ink dark:text-white truncate">{file.name}</div>
                                                    <div className="text-xs ktra-text-soft">{(file.size / 1024).toFixed(1)} KB</div>
                                                </div>
                                            </div>
                                            <button
                                                onClick={() => handleDownloadPdf(file)}
                                                className="p-2 ktra-text-accent dark:ktra-text-soft hover:ktra-bg-accent-bg dark:hover:ktra-bg-panel/30 rounded-lg transition-colors flex items-center gap-2 text-sm font-medium"
                                                title="تحميل الملف"
                                            >
                                                <Download className="w-4 h-4" />
                                                <span>تحميل</span>
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="p-4 text-center text-sm ktra-text-soft ktra-bg-panel dark:ktra-bg-panel/50 rounded-xl border border-dashed ktra-border-soft dark:ktra-border-soft">
                                    لا توجد ملفات PDF مرفقة
                                </div>
                            )}

                            {/* Images Grid */}
                            {invoice.imageUrls && invoice.imageUrls.length > 0 && (
                                <div className="mt-4 grid grid-cols-4 gap-2">
                                    {invoice.imageUrls.map((url, idx) => (
                                        <a key={idx} href={url} target="_blank" rel="noopener noreferrer" className="block aspect-square rounded-lg overflow-hidden border ktra-border-soft dark:ktra-border-soft hover:ring-2 ring-blue-500 transition-all">
                                            <img src={url} alt={`Attachment ${idx}`} className="w-full h-full object-cover" />
                                        </a>
                                    ))}
                                </div>
                            )}
                        </div>

                    </div>

                    {/* Notes */}
                    {invoice.notes && (
                        <div className="ktra-bg-panel dark:ktra-bg-panel/10 p-4 rounded-xl border ktra-border-soft dark:ktra-border-soft/30">
                            <h4 className="font-bold ktra-text-ink dark:ktra-text-soft text-sm mb-2">ملاحظات:</h4>
                            <p className="ktra-text-ink dark:ktra-text-soft text-sm whitespace-pre-line">{invoice.notes}</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
