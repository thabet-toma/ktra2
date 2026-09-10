import assert from 'node:assert/strict';
import test from 'node:test';

import type { PlatformAnomaly } from './interventionAnomalies.ts';
import {
  ANOMALY_ABSENT_WITH_WORK,
  ANOMALY_CRITICAL_DELAY,
  ANOMALY_LOW_SCORE,
  ANOMALY_OVERLOADED,
  getAnomalyMeta,
  isSupportedAnomalyType,
  sortAnomaliesWorstFirst,
  SUPPORTED_ANOMALY_TYPES,
} from './interventionAnomalies.ts';

test('الشذوذات المدعومة هي الأربعة المتفق عليها فقط', () => {
  assert.equal(SUPPORTED_ANOMALY_TYPES.length, 4);
  assert.equal(isSupportedAnomalyType(ANOMALY_CRITICAL_DELAY), true);
  assert.equal(isSupportedAnomalyType(ANOMALY_ABSENT_WITH_WORK), true);
  assert.equal(isSupportedAnomalyType(ANOMALY_OVERLOADED), true);
  assert.equal(isSupportedAnomalyType(ANOMALY_LOW_SCORE), true);

  // أنواع دخيلة غير مدعومة
  assert.equal(isSupportedAnomalyType('unassigned_work_order'), false);
  assert.equal(isSupportedAnomalyType('idle_client'), false);
});

test('ترتيب الشذوذات: الأسوأ أولاً بحسب الوزن ومقياس الفرز', () => {
  const anomalies: PlatformAnomaly[] = [
    {
      type: ANOMALY_LOW_SCORE,
      severity: 'medium',
      severity_weight: 60,
      sort_metric: 15,
      message: 'درجة هابطة 55%',
    },
    {
      type: ANOMALY_CRITICAL_DELAY,
      severity: 'critical',
      severity_weight: 100,
      sort_metric: 7200, // ساعتان
      message: 'تأخر ساعتين',
    },
    {
      type: ANOMALY_CRITICAL_DELAY,
      severity: 'critical',
      severity_weight: 100,
      sort_metric: 14400, // 4 ساعات
      message: 'تأخر 4 ساعات',
    },
    {
      type: ANOMALY_OVERLOADED,
      severity: 'high',
      severity_weight: 80,
      sort_metric: 3,
      message: 'حمل زائد بـ 3 أوامر',
    },
    {
      type: ANOMALY_ABSENT_WITH_WORK,
      severity: 'high',
      severity_weight: 85,
      sort_metric: 45,
      message: 'غائب منذ 45 دقيقة',
    },
  ];

  const sorted = sortAnomaliesWorstFirst(anomalies);

  // التأخر 4 ساعات يسبق التأخر ساعتين، وكلاهما يسبق الغياب والحمل والدرجة
  assert.equal(sorted[0].message, 'تأخر 4 ساعات');
  assert.equal(sorted[1].message, 'تأخر ساعتين');
  assert.equal(sorted[2].type, ANOMALY_ABSENT_WITH_WORK);
  assert.equal(sorted[3].type, ANOMALY_OVERLOADED);
  assert.equal(sorted[4].type, ANOMALY_LOW_SCORE);
});

test('بيانات العرض (Metadata) صحيحة لكل نوع وخالية من inline styles', () => {
  const metaDelay = getAnomalyMeta(ANOMALY_CRITICAL_DELAY);
  assert.equal(metaDelay.label, 'تأخر حرج');
  assert.match(metaDelay.badgeClass, /rose/);

  const metaOverload = getAnomalyMeta(ANOMALY_OVERLOADED);
  assert.equal(metaOverload.label, 'حمل زائد');
  assert.match(metaOverload.badgeClass, /orange/);

  const metaAbsent = getAnomalyMeta(ANOMALY_ABSENT_WITH_WORK);
  assert.equal(metaAbsent.label, 'غائب وعليه عمل');
  assert.match(metaAbsent.badgeClass, /amber/);

  const metaScore = getAnomalyMeta(ANOMALY_LOW_SCORE);
  assert.equal(metaScore.label, 'درجة هابطة');
  assert.match(metaScore.badgeClass, /purple/);
});
