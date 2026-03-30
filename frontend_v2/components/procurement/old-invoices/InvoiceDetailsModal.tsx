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
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl w-full max-w-5xl my-8 flex flex-col relative animate-in fade-in zoom-in duration-200">
                {/* Header */}
                <div className="sticky top-0 bg-white dark:bg-gray-800 p-6 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center z-20 rounded-t-2xl">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                            <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                                تفاصيل الفاتورة
                            </h2>
                            <p className="text-sm text-gray-500 dark:text-gray-400 font-mono">
                                #{invoice.invoiceNumber}
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">
                        <X className="w-6 h-6 text-gray-500" />
                    </button>
                </div>

                {/* Body */}
                <div className="p-6 md:p-8 space-y-8 overflow-y-auto max-h-[calc(100vh-150px)]">

                    {/* Basic Info Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div className="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                            <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
                                <Calendar className="w-4 h-4" />
                                <span className="text-xs font-medium">تاريخ الفاتورة</span>
                            </div>
                            <div className="font-semibold text-gray-900 dark:text-white text-lg">
                                {invoice.invoiceDate}
                            </div>
                        </div>
                        <div className="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                            <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
                                <Building className="w-4 h-4" />
                                <span className="text-xs font-medium">المورد</span>
                            </div>
                            <div className="font-semibold text-gray-900 dark:text-white text-lg truncate">
                                {invoice.factoryName || '-'}
                            </div>
                        </div>
                        <div className="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700">
                            <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 mb-1">
                                <Tag className="w-4 h-4" />
                                <span className="text-xs font-medium">الحالة</span>
                            </div>
                            <div className="font-semibold text-gray-900 dark:text-white text-lg">
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
                            className="flex items-center justify-center gap-2 w-full p-4 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-xl border border-blue-200 dark:border-blue-800 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors font-semibold"
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
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                <FileText className="w-5 h-5 text-gray-500" />
                                الملفات المرفقة
                            </h3>

                            {/* PDF List */}
                            {invoice.pdfFiles && invoice.pdfFiles.length > 0 ? (
                                <div className="space-y-2">
                                    {invoice.pdfFiles.map((file, idx) => (
                                        <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700 transition-colors">
                                            <div className="flex items-center gap-3 overflow-hidden">
                                                <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-lg">
                                                    <FileText className="w-5 h-5 text-red-600 dark:text-red-400" />
                                                </div>
                                                <div className="min-w-0">
                                                    <div className="font-medium text-gray-900 dark:text-white truncate">{file.name}</div>
                                                    <div className="text-xs text-gray-500">{(file.size / 1024).toFixed(1)} KB</div>
                                                </div>
                                            </div>
                                            <button
                                                onClick={() => handleDownloadPdf(file)}
                                                className="p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded-lg transition-colors flex items-center gap-2 text-sm font-medium"
                                                title="تحميل الملف"
                                            >
                                                <Download className="w-4 h-4" />
                                                <span>تحميل</span>
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="p-4 text-center text-sm text-gray-500 bg-gray-50 dark:bg-gray-900/50 rounded-xl border border-dashed border-gray-200 dark:border-gray-700">
                                    لا توجد ملفات PDF مرفقة
                                </div>
                            )}

                            {/* Images Grid */}
                            {invoice.imageUrls && invoice.imageUrls.length > 0 && (
                                <div className="mt-4 grid grid-cols-4 gap-2">
                                    {invoice.imageUrls.map((url, idx) => (
                                        <a key={idx} href={url} target="_blank" rel="noopener noreferrer" className="block aspect-square rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 hover:ring-2 ring-blue-500 transition-all">
                                            <img src={url} alt={`Attachment ${idx}`} className="w-full h-full object-cover" />
                                        </a>
                                    ))}
                                </div>
                            )}
                        </div>

                    </div>

                    {/* Notes */}
                    {invoice.notes && (
                        <div className="bg-yellow-50 dark:bg-yellow-900/10 p-4 rounded-xl border border-yellow-200 dark:border-yellow-900/30">
                            <h4 className="font-bold text-yellow-800 dark:text-yellow-500 text-sm mb-2">ملاحظات:</h4>
                            <p className="text-gray-700 dark:text-gray-300 text-sm whitespace-pre-line">{invoice.notes}</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
