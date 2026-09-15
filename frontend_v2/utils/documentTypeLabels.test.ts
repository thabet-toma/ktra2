import assert from 'node:assert/strict';
import test from 'node:test';

import {
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
