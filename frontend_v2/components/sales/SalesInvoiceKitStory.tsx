/**
 * M1 verification harness — mounts the REAL <SalesInvoiceEditor> (Kit shell)
 * with representative mock props so the screen can be eyeballed live without a
 * backend session. NOT a production screen — dev/QA only, mirrors KitStory.
 * Save/Post hit the same salesApi calls (will error offline — expected here).
 */
import React from "react";
import {
  SalesInvoiceEditor,
  type ProductRow,
  type PartnerRow,
  type CurrRow,
  type AccountRow,
  type TaxRow,
} from "./SalesInvoiceEditor";
import type { SalesInvoiceRow } from "../../services/salesApi";

const products: ProductRow[] = [
  { id: 1, sku: "PRD-001", barcode: "6291041500213", name_ar: "ورق تغليف", name_en: "Wrap Paper", quantity_on_hand: "240", online_price: "3.500", avg_cost: "2.10" },
  { id: 2, sku: "PRD-002", barcode: "6291041500220", name_ar: "صندوق كرتون", name_en: "Carton Box", quantity_on_hand: "85", online_price: "1.250", avg_cost: "0.80" },
  { id: 3, sku: "PRD-003", barcode: "6291041500237", name_ar: "شريط لاصق", name_en: "Tape Roll", quantity_on_hand: "500", online_price: "0.750", avg_cost: "0.40" },
];

const partners: PartnerRow[] = [
  { id: 11, name: "مؤسسة النور التجارية", partner_type: "Customer", credit_limit: "50000" },
  { id: 12, name: "شركة الفجر للتوزيع", partner_type: "Customer", credit_limit: "25000" },
  { id: 13, name: "متجر السلام", partner_type: "Customer", credit_limit: null },
  { id: 99, name: "مورد عام", partner_type: "Supplier", credit_limit: null },
];

const currencies: CurrRow[] = [
  { CurrencyID: 1, Code: "ILS", Name: "شيكل جديد" },
  { CurrencyID: 2, Code: "USD", Name: "دولار" },
  { CurrencyID: 3, Code: "JOD", Name: "دينار" },
];

const accounts: AccountRow[] = [
  { id: 101, code: "1101", name: "الصندوق الرئيسي", account_type: "Asset" },
  { id: 102, code: "1103", name: "بنك فلسطين", account_type: "Asset" },
  { id: 401, code: "4101", name: "إيرادات المبيعات", account_type: "Revenue" },
  { id: 402, code: "4102", name: "إيرادات الخدمات", account_type: "Revenue" },
  { id: 250, code: "2103", name: "ضريبة القيمة المضافة - مخرجات", account_type: "Liability" },
];

const taxRates: TaxRow[] = [
  { id: 7, name: "ض.ق.م", code: "VAT16", rate: "16", tax_account: 250, direction: "sales" },
  { id: 8, name: "معفى", code: "VAT0", rate: "0", tax_account: 250, direction: "both" },
];

const invoiceList: SalesInvoiceRow[] = [
  { id: 501, invoice_number: "SI-000501", customer: 11, customer_name: "مؤسسة النور التجارية", invoice_date: "2026-05-10", invoice_type: "credit", status: "posted", grand_total: "1740.00", currency: 1 },
  { id: 502, invoice_number: "SI-000502", customer: 12, customer_name: "شركة الفجر للتوزيع", invoice_date: "2026-05-14", invoice_type: "cash", status: "draft", grand_total: "986.00", currency: 1 },
  { id: 503, invoice_number: "SI-000503", customer: 13, customer_name: "متجر السلام", invoice_date: "2026-05-18", invoice_type: "credit", status: "draft", grand_total: "452.50", currency: 1 },
];

const salesSettings = {
  default_customer: null,
  default_currency: 1,
  default_payment_type: "credit" as const,
  default_cash_account: 101,
  default_revenue_account_product: 401,
  stock_on_post_default: true,
  default_vat_rate: 7,
  prices_include_tax: false,
  auto_post_invoices: false,
  show_journal_preview: true,
};

export const SalesInvoiceKitStory: React.FC = () => (
  <div style={{ height: "calc(100vh - 1rem)", padding: "0.5rem" }}>
    <SalesInvoiceEditor
      products={products}
      partners={partners}
      currencies={currencies}
      accounts={accounts}
      taxRates={taxRates}
      draftToEditId={null}
      onDraftEditConsumed={() => {}}
      onInvoiceSaved={() => {}}
      invoiceList={invoiceList}
      currentUserName="admin"
      salesSettings={salesSettings}
    />
  </div>
);
