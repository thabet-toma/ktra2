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
      itemId: item.product ? String(item.product) : "",
      name: item.product_name || item.name,
      categoryId: "",
      categoryName: "",
      specifications: "",
      imageUrls: [],
      quantity: Number(item.quantity),
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
    shipment: dto.shipment ? String(dto.shipment) : undefined,
    clearanceId: dto.clearance != null ? String(dto.clearance) : undefined,
    supplierSnapshot: { tradeName: dto.partner_name || "" },
    isPosted: Boolean(dto.is_posted),
  } as Invoice;
}
