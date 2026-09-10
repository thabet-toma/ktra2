import assert from 'node:assert/strict';
import test from 'node:test';

import type {
  PlatformDashboardCompany,
  PlatformDashboardEmployee,
} from './dashboardRanking.ts';
import {
  sortCompaniesWorstFirst,
  sortEmployeesWorstFirst,
} from './dashboardRanking.ts';

test('ترتيب الموظفين: الأسوأ أولاً (الأكثر تأخراً ثم الأكثر حملاً ثم الأقل أداءً)', () => {
  const empList: PlatformDashboardEmployee[] = [
    {
      id: 1,
      name: 'موظف ممتاز',
      specialty: 'data_entry',
      capacity_target: 10,
      status: 'active',
      active_work_orders_count: 5,
      overdue_work_orders_count: 0,
      last_active_at: null,
      is_recently_active: true,
      performance: { composite_score: 95 },
    },
    {
      id: 2,
      name: 'موظف متأخر',
      specialty: 'data_entry',
      capacity_target: 5,
      status: 'active',
      active_work_orders_count: 5,
      overdue_work_orders_count: 3, // أكثر تأخراً!
      last_active_at: null,
      is_recently_active: true,
      performance: { composite_score: 70 },
    },
    {
      id: 3,
      name: 'موظف محمل زيادة',
      specialty: 'review',
      capacity_target: 3,
      status: 'active',
      active_work_orders_count: 6, // زائد بـ 3
      overdue_work_orders_count: 0,
      last_active_at: null,
      is_recently_active: true,
      performance: { composite_score: 80 },
    },
    {
      id: 4,
      name: 'موظف بدرجة منخفضة',
      specialty: 'review',
      capacity_target: 5,
      status: 'active',
      active_work_orders_count: 4,
      overdue_work_orders_count: 0,
      last_active_at: null,
      is_recently_active: true,
      performance: { composite_score: 45 }, // درجة هابطة!
    },
  ];

  const sorted = sortEmployeesWorstFirst(empList);

  // المتأخر هو الأول (الأسوأ)
  assert.equal(sorted[0].id, 2);
  // ثم المحمل زيادة (حمل زائد 3 فوق السعة)
  assert.equal(sorted[1].id, 3);
  // ثم صاحب الدرجة المنخفضة 45
  assert.equal(sorted[2].id, 4);
  // وأخيراً الممتاز
  assert.equal(sorted[3].id, 1);
});

test('ترتيب الشركات: الأسوأ أولاً (الأكثر تأخراً ثم الأكثر نشاطاً)', () => {
  const companies: PlatformDashboardCompany[] = [
    {
      id: 101,
      name: 'شركة مستقرة',
      subscription_status: 'active',
      subscription_plan: 'standard',
      active_work_orders_count: 2,
      overdue_work_orders_count: 0,
    },
    {
      id: 102,
      name: 'شركة متأخرة جداً',
      subscription_status: 'active',
      subscription_plan: 'enterprise',
      active_work_orders_count: 10,
      overdue_work_orders_count: 5,
    },
    {
      id: 103,
      name: 'شركة متأخرة قليلاً',
      subscription_status: 'active',
      subscription_plan: 'standard',
      active_work_orders_count: 4,
      overdue_work_orders_count: 1,
    },
  ];

  const sorted = sortCompaniesWorstFirst(companies);
  assert.equal(sorted[0].id, 102); // 5 متأخر
  assert.equal(sorted[1].id, 103); // 1 متأخر
  assert.equal(sorted[2].id, 101); // 0 متأخر
});
