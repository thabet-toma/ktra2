import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  COMPANY_TEMPLATES,
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

test('مفتاح غير معروف لا يعيد أي قالب', () => {
  assert.equal(companyTemplateByKey('not-a-real-template'), undefined);
});

test('قالب «إطارات» مُدرَج بمفتاحه المطابق لما يرسله الخادم', () => {
  const tyres = companyTemplateByKey('tyres');
  assert.ok(tyres);
  assert.equal(tyres?.name, 'إطارات');
});

test('قالبُ موديول المكتب الجديد مُدرَج — القالبُ الحيّ الوحيد للمكاتب بعد #291', () => {
  const office = companyTemplateByKey('accounting_office');
  assert.ok(office);
  assert.equal(office?.name, 'مكتب محاسبة (الجديد)');
});

test('لا مفاتيح مكررة في السِجلّ', () => {
  const keys = COMPANY_TEMPLATES.map((template) => template.key);
  assert.equal(new Set(keys).size, keys.length);
});

// ── #291: بابٌ واحد للإنشاء، والقالبان القديمان خارج السِجلّ ──────────────
//
// حُذف `accounting_firm` و`client_book` من الواجهة مع طبقة المكتب القديمة،
// ويبقيان في الخادم لهذه الموجة. فما تعرضه شاشة الإنشاء هو السِجلّ نفسه.

test('بابُ إنشاء شركة يعرض السِجلّ كلَّه بلا استثناء', () => {
  assert.deepEqual(
    SELF_SERVE_COMPANY_TEMPLATES.map((t) => t.key),
    COMPANY_TEMPLATES.map((t) => t.key),
  );
});

test('قالبُ المكتب القديم ودفتر العميل خارج سِجلّ الواجهة', () => {
  const keys = COMPANY_TEMPLATES.map((t) => t.key);
  assert.equal(keys.includes('accounting_firm' as never), false);
  assert.equal(keys.includes('client_book' as never), false);
});

test('الافتراضي العام من قوائم الإنشاء', () => {
  assert.ok(SELF_SERVE_COMPANY_TEMPLATES.some((t) => t.key === DEFAULT_COMPANY_TEMPLATE));
});
