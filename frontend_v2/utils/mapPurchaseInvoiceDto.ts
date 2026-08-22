import type { PurchaseInvoiceDto } from "@/types/purchaseInvoice";
import type { Invoice } from "@/types";
import { normalizeTaxRatePercent } from "@/utils/sqlMoneyRound";

/** Map SQL full DTO → frontend Invoice shape for InvoiceForm / القوائم */
export function mapPurchaseInvoiceDtoToInvoice(dto: PurchaseInvoiceDto): Invoice {
  return {
    id: String(dto.id),
    serialNumber: (dto.invoice_number || "").replace("INV-", ""),
    invoiceNumber: dto.invoice_number || "",
    invoiceName: dto.invoice_name || "",
    supplierId: String(dto.partner),
    factoryName: dto.factory_name || undefined,
    supplierInvoiceNumber: dto.supplier_invoice_number || undefined,
    notes: dto.notes || undefined,
    items: (dto.items || []).map((item, idx) => ({
      id: String(item.id || idx),
      serverId: Number(item.id) > 0 ? Number(item.id) : undefined,
      itemId: item.product ? String(item.product) : "",
      name: item.product_name || item.name,
      categoryId: "",
      categoryName: "",
      specifications: "",
      imageUrls: [],
      quantity: Number(item.quantity),
      // T-RECVIS: المستلَم والباقي يعبران المُطابِق — كان يُسقطهما فتبقى
      // الأرقام في الحمولة ولا تصل الشاشة أبداً.
      receivedQuantity: Number(item.received_quantity ?? 0),
      remainingQuantity: Number(item.remaining_quantity ?? 0),
      unitPrice: Number(item.unit_price),
      totalPrice: Number(item.total_price),
      hsCodePrimary: item.hs_code || undefined,
      notes: item.notes || undefined,
      landedUnitPriceIls: item.landed_unit_price_ils
        ? Number(item.landed_unit_price_ils)
        : undefined,
      landedLineTotalIls: item.landed_line_total_ils
        ? Number(item.landed_line_total_ils)
        : undefined,
      // T-SERIAL: الأرقام تعود مع البند فتبقى ظاهرة بعد الحفظ وإعادة الفتح.
      serials: Array.isArray(item.serials) ? item.serials.map(String) : [],
    })),
    status: dto.status as Invoice["status"],
    subtotal: dto.subtotal,
    discountAmount: dto.discount_amount || 0,
    taxRate: normalizeTaxRatePercent(dto.tax_rate ?? 0),
    taxAmount: dto.tax_amount || 0,
    taxType: dto.tax_type || "percentage",
    shippingCost: dto.shipping_cost || 0,
    shippingIncluded: dto.shipping_included || false,
    grandTotal: dto.grand_total,
    invoiceType: dto.invoice_type || (dto.clearance || dto.shipment ? "international" : "local"),
    fees: (dto.fees || []).map((fee) => ({
      id: fee.id != null ? String(fee.id) : undefined,
      description: fee.description,
      amount: Number(fee.amount || 0),
      calculationType: fee.calculation_type || "amount",
      calculationValue: Number(fee.calculation_value ?? fee.amount ?? 0),
      percentageBasis: fee.percentage_basis || "goods",
      expenseAccountId: Number(fee.expense_account) || null,
      expenseAccountCode: fee.expense_account_code || undefined,
      expenseAccountName: fee.expense_account_name || undefined,
      capitalizeToInventory: Boolean(fee.capitalize_to_inventory),
      isTaxable: Boolean(fee.is_taxable),
    })),
    feesTotal: Number(dto.fees_total || 0),
    payableTotal: Number(dto.payable_total || dto.grand_total || 0),
    amountPaid: Number(dto.amount_paid || 0),
    remainingBalance: Number(dto.remaining_balance || 0),
    paymentStatus: dto.payment_status || "unpaid",
    paymentStatusDisplay: dto.payment_status_display || "غير مدفوعة",
    receiptStatus: dto.receipt_status || "not_received",
    receiptStatusDisplay: dto.receipt_status_display || undefined,
    receiptProgress: dto.receipt_progress
      ? {
          ordered: Number(dto.receipt_progress.ordered),
          received: Number(dto.receipt_progress.received),
          remaining: Number(dto.receipt_progress.remaining),
          linesTotal: dto.receipt_progress.lines_total,
          linesRemaining: dto.receipt_progress.lines_remaining,
        }
      : undefined,
    partnerBalance: Number(dto.supplier_balance_current || 0),
    partnerBalanceBeforeInvoice: Number(dto.supplier_balance_before_invoice || 0),
    partnerBalanceAfterInvoice: Number(dto.supplier_balance_after_invoice || 0),
    paymentDetails: (dto.payment_details || []).map((payment) => ({
      source: payment.source,
      id: payment.id,
      paymentDate: payment.payment_date,
      amount: Number(payment.amount || 0),
      currencyCode: payment.currency_code,
      exchangeRate: Number(payment.exchange_rate || 1),
      cashOrBankAccountName: payment.cash_or_bank_account_name || undefined,
      isPosted: payment.is_posted,
      journalId: payment.journal || undefined,
      notes: payment.notes || undefined,
    })),
    localPayments: (dto.local_payments_json as Invoice["localPayments"]) || undefined,
    conversionMetadata:
      (dto.conversion_metadata_json as Invoice["conversionMetadata"]) || undefined,
    currency: dto.currency_code === "USD" ? "USD" : "ILS",
    invoiceDate: dto.invoice_date || undefined,
    createdAt: dto.created_at || new Date().toISOString(),
    updatedAt: dto.updated_at || new Date().toISOString(),
    createdBy: dto.created_by ? String(dto.created_by) : "",
    glPurchaseReceiptJournalId: dto.journal_id_display || undefined,
    dealId: dto.deal ? String(dto.deal) : undefined,
    dealNumber: dto.deal_ref || undefined,
    dealTitle: dto.deal_title || undefined,
    shipment: dto.shipment ? String(dto.shipment) : undefined,
    clearanceId: dto.clearance != null ? String(dto.clearance) : undefined,
    importLogistics: dto.shipment && dto.clearance != null ? {
      shipmentId: String(dto.shipment),
      shipmentNumber: dto.shipment_number || undefined,
      shipmentName: dto.shipment_name || undefined,
      clearanceId: dto.clearance,
    } : undefined,
    supplierSnapshot: { tradeName: dto.partner_name || "" },
    isPosted: Boolean(dto.is_posted),
    // W7a: هوية مستند المرجع (شارة + رابط الفاتورة الأصلية + لغة معكوسة).
    isReturn: Boolean(dto.is_return),
    originalInvoiceId: dto.original_invoice != null ? String(dto.original_invoice) : undefined,
    originalInvoiceNumber: dto.original_invoice_number || undefined,
    // T-PLINEAGE: من أين جاءت الفاتورة — عرض سعر أو طلبية، مع جدّها إن وُجد.
    sourceDocument: dto.source_document ? {
      kind: dto.source_document.kind,
      id: dto.source_document.id,
      number: dto.source_document.number,
      originKind: dto.source_document.origin_kind ?? null,
      originId: dto.source_document.origin_id ?? null,
      originNumber: dto.source_document.origin_number ?? null,
    } : undefined,
    // W7c: مرفقات الفاتورة (صور + PDF) — يستهلكها AttachmentsSection المشترك.
    quoteImages: dto.quote_images || [],
    quotePdfs: dto.quote_pdfs || [],
  } as Invoice;
}
