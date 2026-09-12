import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildLimitComparisonRows,
  buildModuleComparisonRows,
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
