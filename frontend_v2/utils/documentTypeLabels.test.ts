import assert from 'node:assert/strict';
import test from 'node:test';

import {
  invoiceKindLabel,
  relatedInvoiceTypeLabel,
  stockLedgerMovementTypeLabel,
  stockMovementReferenceLabel,
} from './documentTypeLabels.ts';

test('يسمّي فاتورة البيع بيعاً', () => {
  assert.equal(relatedInvoiceTypeLabel({ document_type: 'SALES_INVOICE', invoice_kind: 'sale' }), 'بيع');
});

test('يسمّي مرتجع البيع مرتجع بيع', () => {
  assert.equal(relatedInvoiceTypeLabel({ document_type: 'SALES_INVOICE', invoice_kind: 'sale_return' }), 'مرتجع بيع');
});

test('يبقي فاتورة الشراء شراءً', () => {
  assert.equal(relatedInvoiceTypeLabel({ document_type: 'PURCHASE_INVOICE' }), 'شراء');
});

test('يسمّي مستحقّات المخلّص والوكيل والناقل بأسمائها لا «شراء»', () => {
  assert.equal(relatedInvoiceTypeLabel({ document_type: 'LOGISTICS_CLEARANCE' }), 'مستحق تخليص');
  assert.equal(relatedInvoiceTypeLabel({ document_type: 'SHIPMENT_FREIGHT_ACCRUAL' }), 'مستحق شحن');
  assert.equal(relatedInvoiceTypeLabel({ document_type: 'LOCAL_SHIPMENT' }), 'إرسالية');
});

test('يبقي حركة البيع مبيعاتٍ — الإصلاح لا يقلب السليم', () => {
  const movement = {
    reference_type: 'SALE',
    movement_type: 'OUT',
    movement_type_label: 'صرف',
  };
  assert.equal(stockLedgerMovementTypeLabel(movement), 'مبيعات');
  assert.equal(stockMovementReferenceLabel({ ...movement, reference_type_display: 'بيع' }), 'بيع');
});

test('يُبقي حركة المرتجع كما وصفها الخادم حتى لو كان مرجعها بيعاً', () => {
  const movement = {
    reference_type: 'SALE',
    movement_type: 'RETURN_IN',
    movement_type_label: 'مرتجع داخل',
  };
  assert.equal(stockLedgerMovementTypeLabel(movement), 'مرتجع داخل');
  assert.equal(stockMovementReferenceLabel({ ...movement, reference_type_display: 'بيع' }), 'مرتجع بيع');
});

// ‏#214-ب (بلاغُ المالك الثاني): «لما اضغط عليه بتبين كلمة فاتورة مبيعات
// بالعنوان». الوجهُ المالي: كشفُ الحساب وعنوانُ نافذة التفاصيل يشتقّان الاسمَ
// من `reference_type` — وقيدُ المرتجع يحمل `SALES_INVOICE` كالبيعة حرفاً.

test('يسمّي مرتجع البيع باسمه حين يُعرف نوعه', () => {
  assert.equal(invoiceKindLabel('sale_return'), 'مرتجع بيع');
  assert.equal(invoiceKindLabel('purchase_return'), 'مرتجع شراء');
});

test('يعيد null لِما ليس مرتجعاً فيتابع المستدعي تسميته المعتادة', () => {
  assert.equal(invoiceKindLabel('sale'), null);
  assert.equal(invoiceKindLabel(undefined), null);
  assert.equal(invoiceKindLabel(null), null);
});
