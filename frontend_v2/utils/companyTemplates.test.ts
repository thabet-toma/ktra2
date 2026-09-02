import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  COMPANY_TEMPLATES,
  DEFAULT_COMPANY_TEMPLATE,
  companyTemplateByKey,
} from './companyTemplates.ts';

test('القالب الافتراضي general موجود في السِجلّ', () => {
  assert.equal(DEFAULT_COMPANY_TEMPLATE, 'general');
  assert.ok(companyTemplateByKey('general'));
});

test('كل قالب يحمل مفتاحاً واسماً وأيقونة ووصفاً غير فارغين', () => {
  for (const template of COMPANY_TEMPLATES) {
    assert.ok(template.key, 'key');
    assert.ok(template.name.trim().length > 0, 'name');
    assert.ok(template.icon.trim().length > 0, 'icon');
    assert.ok(template.description.trim().length > 0, 'description');
  }
});

test('قالب مكتب المحاسبة مُدرَج بمفتاحه المطابق لما يرسله الخادم', () => {
  const firm = companyTemplateByKey('accounting_firm');
  assert.ok(firm);
  assert.equal(firm?.name, 'مكتب محاسبة');
});

test('مفتاح غير معروف لا يعيد أي قالب', () => {
  assert.equal(companyTemplateByKey('not-a-real-template'), undefined);
});

test('لا مفاتيح مكررة في السِجلّ', () => {
  const keys = COMPANY_TEMPLATES.map((template) => template.key);
  assert.equal(new Set(keys).size, keys.length);
});
