import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  blankSimpleFields,
  dirtySimplePayload,
  hasSimpleChanges,
  simpleFieldsFromProduct,
  simplePayload,
  validateSimpleFields,
  type ItemSimpleFields,
} from './itemSimpleFields.ts';

const withFields = (over: Partial<ItemSimpleFields> = {}): ItemSimpleFields => ({
  ...blankSimpleFields(),
  name_ar: 'إطار',
  ...over,
});

test('صفّ الخادم يُقرأ بأنواعه لا بنصوصه', () => {
  const fields = simpleFieldsFromProduct({
    name_ar: 'إطار', name_en: 'Tyre', category: '7', uom_id: 3,
    sale_price: '150.5000', barcode: '1234567890128',
    is_service: false, is_serialized: true,
  });
  assert.equal(fields.category, 7);
  assert.equal(fields.uom_id, 3);
  assert.equal(fields.sale_price, '150.5000');
  assert.equal(fields.is_serialized, true);
});

test('التصنيف ووحدة القياس الغائبان يصيران null لا NaN', () => {
  const fields = simpleFieldsFromProduct({ name_ar: 'صنف' });
  assert.equal(fields.category, null);
  assert.equal(fields.uom_id, null);
  assert.equal(fields.sale_price, '');
});

test('الفراغ يُرسَل null لا نصّاً فارغاً', () => {
  const payload = simplePayload(withFields({ barcode: '  ', sale_price: '  ', name_en: '' }));
  assert.equal(payload.barcode, null);
  assert.equal(payload.sale_price, null);
  assert.equal(payload.name_en, null);
  assert.equal(payload.name_ar, 'إطار');
});

test('سعر البيع يُرسَل رقماً', () => {
  assert.equal(simplePayload(withFields({ sale_price: '150.5' })).sale_price, 150.5);
});

test('الخدمة لا تحمل تتبّعاً تسلسلياً مهما كان المربّع', () => {
  const payload = simplePayload(withFields({ is_service: true, is_serialized: true }));
  assert.equal(payload.is_serialized, false);
});

test('تغيير الاسم وحده يرسل الاسم وحده', () => {
  const before = withFields({ category: 3, sale_price: '100' });
  const after = { ...before, name_ar: 'إطار جديد' };
  assert.deepEqual(dirtySimplePayload(before, after), { name_ar: 'إطار جديد' });
});

test('بلا تغيير: حمولة فارغة ولا حفظ', () => {
  const before = withFields({ category: 3 });
  assert.deepEqual(dirtySimplePayload(before, { ...before }), {});
  assert.equal(hasSimpleChanges(before, { ...before }), false);
});

test('مسحُ سعر البيع تغييرٌ يُرسَل null صراحةً', () => {
  const before = withFields({ sale_price: '100' });
  const after = { ...before, sale_price: '' };
  assert.deepEqual(dirtySimplePayload(before, after), { sale_price: null });
  assert.equal(hasSimpleChanges(before, after), true);
});

test('مسافة زائدة حول الاسم ليست تغييراً', () => {
  const before = withFields({ name_ar: 'إطار' });
  assert.equal(hasSimpleChanges(before, { ...before, name_ar: '  إطار  ' }), false);
});

test('تحويل الصنف إلى خدمة يطفئ التتبّع في نفس الحمولة', () => {
  const before = withFields({ is_serialized: true });
  const after = { ...before, is_service: true };
  assert.deepEqual(dirtySimplePayload(before, after), { is_service: true, is_serialized: false });
});

test('الاسم مطلوب بأحد اللسانين', () => {
  assert.ok(validateSimpleFields(blankSimpleFields()));
  assert.equal(validateSimpleFields(withFields()), null);
  assert.equal(validateSimpleFields(withFields({ name_ar: '', name_en: 'Tyre' })), null);
  assert.ok(validateSimpleFields(withFields({ name_ar: '   ' })));
});
