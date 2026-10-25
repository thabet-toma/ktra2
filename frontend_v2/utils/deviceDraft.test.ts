import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildDeviceBody } from './deviceDraft.ts';
import type { DeviceDraft } from '../services/devicesApi.ts';

/**
 * TKT-DEV-1 — جسم الجهاز يُبنى في مكانٍ واحد.
 *
 * نموذجان يكتبان السجل نفسه: الاستقبال (بلا `status`) والتعديل (معها). الاختبار
 * هنا يحرس ما يكسرانه معاً إن عاد البناء نسختين: التطبيع، ووجود `photo_url`
 * دائماً — `PATCH` بلا هذا المفتاح لا يمحو الصورة، لكن نسخةً تنساه تجعل
 * «إزالة الصورة» تبدو ناجحة وهي لم تصل.
 */

const draft = (overrides: Partial<DeviceDraft> = {}): DeviceDraft => ({
  customer_name: '  زبون تجريبي ',
  customer_phone: ' 0599-123 456 ',
  model_name: ' جهاز لوحي ',
  serial_number: ' SN-7 ',
  imei: '490-154 203/237518',
  technical_notes: 'ملاحظة فنية',
  photo_url: 'https://cdn.test/old.png',
  ...overrides,
});

test('الجسم يطبِّع الحقول كما يطبِّعها الخادم — تقليم وتطبيع هاتف وأرقام IMEI', () => {
  const body = buildDeviceBody(draft());
  assert.equal(body.customer_name, 'زبون تجريبي');
  assert.equal(body.customer_phone, '0599123456');
  assert.equal(body.model_name, 'جهاز لوحي');
  assert.equal(body.serial_number, 'SN-7');
  assert.equal(body.imei, '490154203237518');
});

test('photo_url يُرسَل دائماً — وقيمته الفارغة تصل كما هي لتمحو الصورة', () => {
  assert.equal(buildDeviceBody(draft()).photo_url, 'https://cdn.test/old.png');

  const cleared = buildDeviceBody(draft({ photo_url: '' }));
  assert.ok(Object.hasOwn(cleared, 'photo_url'));
  assert.equal(cleared.photo_url, '');
});

test('status لا يدخل جسم التسجيل، ويبقى في جسم التعديل', () => {
  const create = buildDeviceBody(draft());
  assert.equal(Object.hasOwn(create, 'status'), false);

  const edit = buildDeviceBody(draft({ status: 'in_check' }));
  assert.equal(edit.status, 'in_check');
});

test('الملاحظات الفنية تصل كما هي — لا تقليم ولا تحويل', () => {
  assert.equal(buildDeviceBody(draft({ technical_notes: '  سطر  ' })).technical_notes, '  سطر  ');
  assert.equal(buildDeviceBody(draft({ technical_notes: '' })).technical_notes, '');
});
