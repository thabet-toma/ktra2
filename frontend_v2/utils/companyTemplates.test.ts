import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  CLIENT_BOOK_TEMPLATES,
  COMPANY_TEMPLATES,
  DEFAULT_CLIENT_BOOK_TEMPLATE,
  DEFAULT_COMPANY_TEMPLATE,
  SELF_SERVE_COMPANY_TEMPLATES,
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

// ── بلاغ المالك: قالبٌ لكل باب ────────────────────────────────────────
//
// «لما أنشئ شركة بيجي دفتر زبون — قيّمه» و«لما أسجّل عميل بيجيني ٣ خيارات».
// السِجلّ يبقى واحداً (الخادم يعرف الثلاثة ويسمّيها في كل مكان)، والمعروض
// ينقسم بابين. الخادم يفرض القاعدة نفسها بـ`assert_self_serve_template` و
// `assert_book_template` — وهذه القوائم عرضٌ لها لا مصدرُها.

test('بابُ إنشاء شركة لا يعرض «دفتر عميل»', () => {
  const keys = SELF_SERVE_COMPANY_TEMPLATES.map((t) => t.key);
  assert.equal(keys.includes('client_book'), false);
  assert.deepEqual(keys, ['general', 'accounting_firm']);
});

test('بابُ دفاتر العملاء يعرض «دفتر عميل» وحده', () => {
  assert.deepEqual(CLIENT_BOOK_TEMPLATES.map((t) => t.key), ['client_book']);
});

test('البابان معاً يغطّيان السِجلّ كلَّه بلا تقاطع', () => {
  const shown = [...SELF_SERVE_COMPANY_TEMPLATES, ...CLIENT_BOOK_TEMPLATES].map((t) => t.key);
  assert.equal(new Set(shown).size, shown.length);
  assert.deepEqual([...shown].sort(), COMPANY_TEMPLATES.map((t) => t.key).sort());
});

test('الافتراضي العام من قوائم الإنشاء، وافتراضي الدفتر من قائمة الدفاتر', () => {
  assert.ok(SELF_SERVE_COMPANY_TEMPLATES.some((t) => t.key === DEFAULT_COMPANY_TEMPLATE));
  assert.ok(CLIENT_BOOK_TEMPLATES.some((t) => t.key === DEFAULT_CLIENT_BOOK_TEMPLATE));
});
