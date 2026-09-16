import assert from 'node:assert/strict';
import test from 'node:test';

import { PILOT_EXCLUSION_LABELS, REJECTION_CATEGORY_LABELS, pilotExclusionLabel } from './pilotExclusions.ts';

test('رموزُ الخادم التي كانت تظهر إنجليزيّةً صار لها اسمٌ عربيّ', () => {
  assert.equal(pilotExclusionLabel('onboarding'), 'تهيئة مؤقتة');
  assert.equal(pilotExclusionLabel('waiting_customer'), 'بانتظار العميل');
  assert.equal(pilotExclusionLabel('transferred_before_due'), 'نُقل قبل الاستحقاق');
  assert.equal(pilotExclusionLabel('customer_new_info'), 'معلومات جديدة من العميل');
  assert.equal(pilotExclusionLabel('other'), 'أخرى');
});

test('لا اسمَ إنجليزيٌّ في الخريطة', () => {
  for (const [code, label] of Object.entries(PILOT_EXCLUSION_LABELS)) {
    assert.equal(/[A-Za-z_]/.test(label), false, code);
  }
});

test('الرمزُ المجهولُ يُعرَض كما هو لا خانةً فارغة', () => {
  assert.equal(pilotExclusionLabel('future_code'), 'future_code');
  assert.equal(pilotExclusionLabel('toString'), 'toString');
});

test('تصنيفُ الردّ اسمٌ واحدٌ في القائمة وفي الجدول', () => {
  assert.equal(PILOT_EXCLUSION_LABELS.customer_new_info, REJECTION_CATEGORY_LABELS.customer_new_info);
  assert.equal(PILOT_EXCLUSION_LABELS.other, REJECTION_CATEGORY_LABELS.other);
});
