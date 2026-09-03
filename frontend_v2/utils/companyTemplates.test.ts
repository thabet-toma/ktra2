import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  COMPANY_TEMPLATES,
  DEFAULT_CLIENT_BOOK_TEMPLATE,
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

test('ISSUE #81: قالب دفتر العميل مُدرَج، وهو افتراضي `ClientBooksPanel` لا الافتراضي العام', () => {
  const clientBook = companyTemplateByKey('client_book');
  assert.ok(clientBook);
  assert.equal(clientBook?.name, 'دفتر عميل');
  assert.equal(DEFAULT_CLIENT_BOOK_TEMPLATE, 'client_book');
  assert.notEqual(DEFAULT_CLIENT_BOOK_TEMPLATE, DEFAULT_COMPANY_TEMPLATE);
});

test('مفتاح غير معروف لا يعيد أي قالب', () => {
  assert.equal(companyTemplateByKey('not-a-real-template'), undefined);
});

test('لا مفاتيح مكررة في السِجلّ', () => {
  const keys = COMPANY_TEMPLATES.map((template) => template.key);
  assert.equal(new Set(keys).size, keys.length);
});
