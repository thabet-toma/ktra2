import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  COGS_COST_METHOD_OPTIONS,
  computeCogsExampleRows,
  formatCogsVariance,
  isFixedSnapshotMethod,
  normalizeCogsCostMethod,
} from './cogsCostMethod.ts';

test('COGS_COST_METHOD_OPTIONS has fifo, standard, last_purchase in order and hides avco until M5', () => {
  assert.deepEqual(
    COGS_COST_METHOD_OPTIONS.map((o) => o.value),
    ['fifo', 'standard', 'last_purchase'],
  );
  assert.equal(
    COGS_COST_METHOD_OPTIONS.some((o) => (o.value as string) === 'avco'),
    false,
  );
  assert.equal(COGS_COST_METHOD_OPTIONS[0].label, 'الوارد أولاً يصرف أولاً (FIFO)');
  assert.equal(COGS_COST_METHOD_OPTIONS[1].label, 'السعر الثابت (التكلفة المعيارية)');
  assert.equal(COGS_COST_METHOD_OPTIONS[2].label, 'آخر سعر شراء');
});

test('normalizeCogsCostMethod treats missing or unknown (including avco) as fifo', () => {
  assert.equal(normalizeCogsCostMethod('fifo'), 'fifo');
  assert.equal(normalizeCogsCostMethod('standard'), 'standard');
  assert.equal(normalizeCogsCostMethod('last_purchase'), 'last_purchase');
  assert.equal(normalizeCogsCostMethod('avco'), 'fifo');
  assert.equal(normalizeCogsCostMethod('unknown'), 'fifo');
  assert.equal(normalizeCogsCostMethod(null), 'fifo');
  assert.equal(normalizeCogsCostMethod(undefined), 'fifo');
});

test('isFixedSnapshotMethod is true for standard and last_purchase only', () => {
  assert.equal(isFixedSnapshotMethod('standard'), true);
  assert.equal(isFixedSnapshotMethod('last_purchase'), true);
  assert.equal(isFixedSnapshotMethod('fifo'), false);
  assert.equal(isFixedSnapshotMethod('avco'), false);
  assert.equal(isFixedSnapshotMethod('unknown'), false);
  assert.equal(isFixedSnapshotMethod(null), false);
  assert.equal(isFixedSnapshotMethod(undefined), false);
});

test('computeCogsExampleRows computes §4 scenario (8@10, 4@16, sell 10, standard 11) from layers', () => {
  const rows = computeCogsExampleRows();
  assert.equal(rows.length, 3);

  assert.deepEqual(
    rows.map((r) => ({
      method: r.method,
      cogs: r.cogs,
      varianceSide: r.varianceSide,
      varianceAmount: r.varianceAmount,
      varianceText: formatCogsVariance(r.varianceSide, r.varianceAmount),
      inventoryCredit: r.inventoryCredit,
      remainingInventory: r.remainingInventory,
    })),
    [
      {
        method: 'fifo',
        cogs: 112,
        varianceSide: 'none',
        varianceAmount: 0,
        varianceText: '—',
        inventoryCredit: 112,
        remainingInventory: 32,
      },
      {
        method: 'standard',
        cogs: 110,
        varianceSide: 'debit',
        varianceAmount: 2,
        varianceText: 'مدين 2',
        inventoryCredit: 112,
        remainingInventory: 32,
      },
      {
        method: 'last_purchase',
        cogs: 160,
        varianceSide: 'credit',
        varianceAmount: 48,
        varianceText: 'دائن 48',
        inventoryCredit: 112,
        remainingInventory: 32,
      },
    ],
  );
});

test('computeCogsExampleRows computes a non-default multi-layer scenario without hard-coded constants', () => {
  // Hand calculation for layers [5@20, 10@30, 6@35], sellQty=12, standardUnitCost=24:
  // - FIFO consumption of 12: 5*20 + 7*30 = 100 + 210 = 310 (inventoryCredit = 310)
  // - Remaining stock: 3*30 + 6*35 = 90 + 210 = 300
  // - fifo: cogs = 310, diff = 310 - 310 = 0 -> none 0
  // - standard: cogs = 12 * 24 = 288, diff = 310 - 288 = +22 -> debit 22
  // - last_purchase (last layer unitCost = 35): cogs = 12 * 35 = 420, diff = 310 - 420 = -110 -> credit 110
  const rows = computeCogsExampleRows({
    layers: [
      { qty: 5, unitCost: 20 },
      { qty: 10, unitCost: 30 },
      { qty: 6, unitCost: 35 },
    ],
    sellQty: 12,
    standardUnitCost: 24,
  });

  assert.deepEqual(
    rows.map((r) => ({
      method: r.method,
      cogs: r.cogs,
      varianceSide: r.varianceSide,
      varianceAmount: r.varianceAmount,
      varianceText: formatCogsVariance(r.varianceSide, r.varianceAmount),
      inventoryCredit: r.inventoryCredit,
      remainingInventory: r.remainingInventory,
    })),
    [
      {
        method: 'fifo',
        cogs: 310,
        varianceSide: 'none',
        varianceAmount: 0,
        varianceText: '—',
        inventoryCredit: 310,
        remainingInventory: 300,
      },
      {
        method: 'standard',
        cogs: 288,
        varianceSide: 'debit',
        varianceAmount: 22,
        varianceText: 'مدين 22',
        inventoryCredit: 310,
        remainingInventory: 300,
      },
      {
        method: 'last_purchase',
        cogs: 420,
        varianceSide: 'credit',
        varianceAmount: 110,
        varianceText: 'دائن 110',
        inventoryCredit: 310,
        remainingInventory: 300,
      },
    ],
  );
});
