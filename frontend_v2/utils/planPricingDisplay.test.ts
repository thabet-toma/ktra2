import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildLimitComparisonRows,
  buildModuleComparisonRows,
  buildPlanUsageBar,
  formatPlanLimitValue,
} from './planPricingDisplay.ts';
import type { PublicPlan } from '../services/pricingApi.ts';

test('formatPlanLimitValue: null بلا حدّ، صفر غير متاح، وعددٌ مُنسَّق', () => {
  assert.equal(formatPlanLimitValue(null), 'بلا حدّ');
  assert.equal(formatPlanLimitValue(0), 'غير متاح');
  assert.equal(formatPlanLimitValue(1500), '1,500');
});

const plan = (key: string, limitValue: number | null, moduleKeys: string[]): PublicPlan => ({
  key,
  label: key,
  price: 1,
  currency: 'ILS',
  currency_symbol: '₪',
  limits: [
    { key: 'sales.invoices', label: 'فواتير البيع', unit: 'فاتورة', period: 'month', period_label: 'شهرياً', value: limitValue },
  ],
  modules: moduleKeys.map((k) => ({ key: k, label: `وحدة ${k}` })),
});

test('buildLimitComparisonRows: صفٌّ واحدٌ يحمل قيمة كلّ خطّةٍ بمفتاحها', () => {
  const plans = [plan('Basic', 200, []), plan('Pro', null, []), plan('Enterprise', 0, [])];
  const rows = buildLimitComparisonRows(plans);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].valuesByPlan, { Basic: 200, Pro: null, Enterprise: 0 });
});

test('buildModuleComparisonRows: اتّحاد مفاتيح الوحدات عبر الخطط، وعلمُ التفعيل الصحيح لكلٍّ', () => {
  const plans = [
    plan('Basic', 1, []),
    plan('Pro', 1, ['hr_suite']),
    plan('Enterprise', 1, ['hr_suite', 'advanced_reports']),
  ];
  const rows = buildModuleComparisonRows(plans);
  const byKey = Object.fromEntries(rows.map((r) => [r.key, r]));
  assert.equal(rows.length, 2);
  assert.deepEqual(byKey.hr_suite.enabledByPlan, { Basic: false, Pro: true, Enterprise: true });
  assert.deepEqual(byKey.advanced_reports.enabledByPlan, { Basic: false, Pro: false, Enterprise: true });
});

test('buildPlanUsageBar: `null` بلا حدّ فلا شريطَ ولا قسمةَ على عدم', () => {
  const bar = buildPlanUsageBar(4200, null);
  assert.equal(bar.unbounded, true);
  assert.equal(bar.percent, 0);
  assert.equal(bar.remaining, null);
  assert.ok(Number.isFinite(bar.rawPercent));
});

test('buildPlanUsageBar: `0` غير متاح — لا صفرٌ يُقرأ «بلا استهلاك»', () => {
  const bar = buildPlanUsageBar(0, 0);
  assert.equal(bar.unavailable, true);
  assert.equal(bar.tone, 'over');
  assert.ok(!Number.isNaN(bar.rawPercent));
});

test('buildPlanUsageBar: الفائضُ يُقصّ في الشريط ويبقى في الرقم', () => {
  const bar = buildPlanUsageBar(320, 200);
  assert.equal(bar.percent, 100);
  assert.equal(bar.rawPercent, 160);
  assert.equal(bar.tone, 'over');
  assert.equal(bar.remaining, 0, 'بقي لك سالبٌ ليس رقماً يُقرأ');
});

test('buildPlanUsageBar: حدودُ النبرة عند ٨٠٪ و١٠٠٪ بالضبط', () => {
  assert.equal(buildPlanUsageBar(159, 200).tone, 'ok');
  assert.equal(buildPlanUsageBar(160, 200).tone, 'warning');
  assert.equal(buildPlanUsageBar(199, 200).tone, 'warning');
  assert.equal(buildPlanUsageBar(200, 200).tone, 'over');
});

test('buildPlanUsageBar: الباقي فرقٌ حقيقيّ لا نسبة', () => {
  const bar = buildPlanUsageBar(180, 200);
  assert.equal(bar.remaining, 20);
  assert.equal(bar.percent, 90);
});
