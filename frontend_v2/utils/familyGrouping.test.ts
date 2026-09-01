import { test } from 'node:test';
import assert from 'node:assert/strict';
import { groupProductsByFamily, buildFamilyRow } from './familyGrouping.ts';
import type { SqlProduct } from '../types/inventory.ts';

const brand = (over: Partial<SqlProduct>): SqlProduct => ({
  id: 1, sku: 'SKU', quantity_on_hand: 0, avg_cost: 0,
  stock_status: 'in_stock', ...over,
});

test('منتج بثلاثة براندات: صفّ واحد، رصيده مجموع الثلاثة', () => {
  const rows = [
    brand({ id: 1, family_id: 5, family_name: 'هاتف ذكي', quantity_on_hand: 3, avg_cost: 100 }),
    brand({ id: 2, family_id: 5, family_name: 'هاتف ذكي', quantity_on_hand: 5, avg_cost: 120 }),
    brand({ id: 3, family_id: 5, family_name: 'هاتف ذكي', quantity_on_hand: 2, avg_cost: 90 }),
  ];
  const groups = groupProductsByFamily(rows);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].members.length, 3);
  const merged = buildFamilyRow(groups[0].members);
  assert.equal(merged.quantity_on_hand, 10);
  assert.equal(merged.display_name, 'هاتف ذكي');
});

test('منتجٌ بلا أبٍ (بيانات قديمة) يبقى صفّه الخاص بلا تجميع', () => {
  const rows = [
    brand({ id: 10, family_id: null, name_ar: 'زيت محرك' }),
    brand({ id: 11, family_id: null, name_ar: 'فلتر هواء' }),
  ];
  const groups = groupProductsByFamily(rows);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].members.length, 1);
  assert.equal(groups[0].members[0].id, 10);
  assert.equal(groups[1].members[0].id, 11);
});

test('عنصر الكشف: يظهر لمنتجٍ متعدّد البراندات ولا يظهر لبراندٍ واحد', () => {
  const multi = groupProductsByFamily([
    brand({ id: 1, family_id: 7 }), brand({ id: 2, family_id: 7 }),
  ]);
  assert.equal(multi[0].members.length > 1, true); // الشاشة تُظهر عنصر الكشف

  const single = groupProductsByFamily([brand({ id: 1, family_id: 8 })]);
  assert.equal(single[0].members.length > 1, false); // بلا عنصر — صفٌّ عادي

  const legacy = groupProductsByFamily([brand({ id: 1, family_id: null })]);
  assert.equal(legacy[0].members.length > 1, false);
});

test('ترتيب الأعضاء داخل المجموعة بالمعرّف — الأقدم (الضمنيّ المسمّى أوّلاً) يمثّل الصفّ', () => {
  const groups = groupProductsByFamily([
    brand({ id: 9, family_id: 3, name_ar: 'ثانٍ' }),
    brand({ id: 4, family_id: 3, name_ar: 'أوّل' }),
  ]);
  assert.deepEqual(groups[0].members.map((m) => m.id), [4, 9]);
});

test('التكلفة المجمَّعة متوسطٌ مرجَّح بالكمية لا متوسطاً بسيطاً', () => {
  const members = [
    brand({ id: 1, family_id: 1, quantity_on_hand: 2, avg_cost: 100 }),
    brand({ id: 2, family_id: 1, quantity_on_hand: 100, avg_cost: 10 }),
  ];
  const merged = buildFamilyRow(members);
  // (2*100 + 100*10) / 102 = 1200/102 ≈ 11.76 — قريبٌ من البراند الأكبر كمّاً
  // لا من المتوسط البسيط (55).
  assert.ok(Math.abs((merged.avg_cost as number) - 1200 / 102) < 1e-9);
});

test('حقولٌ لا تُجمَع (السعر ورقم المنتج) تأتي من العضو المرجعي (الأصغر معرّفاً)', () => {
  const members = [
    brand({ id: 5, family_id: 2, sku: 'ANCHOR-SKU', sale_price: '50' }),
    brand({ id: 6, family_id: 2, sku: 'OTHER-SKU', sale_price: '70' }),
  ];
  const merged = buildFamilyRow(members);
  assert.equal(merged.sku, 'ANCHOR-SKU');
  assert.equal(merged.sale_price, '50');
});

test('جمع الحقول النصّية-الرقمية (المشتراة/متوسط البيع الشهري) يتجاهل القيم الفارغة بلا كسر الجمع', () => {
  const members = [
    brand({ id: 1, family_id: 4, purchased_qty: '3', avg_monthly_sales: null }),
    brand({ id: 2, family_id: 4, purchased_qty: null, avg_monthly_sales: '1.5' }),
  ];
  const merged = buildFamilyRow(members);
  assert.equal(merged.purchased_qty, '3');
  assert.equal(merged.avg_monthly_sales, '1.5');
});

// #35: الحدّان يُفضّلان القيمة الحاكمة (`effective_*`) من الخادم على قيمة
// المرجعي الخام — وإلا عرض الصفّ رقماً غير الذي حَكَم على شارته.
test('الحدّ الأدنى المعروض يُفضَّل من effective_min_stock_level لا من قيمة المرجعي الخام', () => {
  const members = [
    brand({
      id: 5, family_id: 9, min_stock_level: 10, effective_min_stock_level: 99,
    }),
    brand({ id: 6, family_id: 9, min_stock_level: 30 }),
  ];
  const merged = buildFamilyRow(members);
  assert.equal(merged.min_stock_level, 99);
});

test('الحدّ الأقصى المعروض يُفضَّل من effective_max_stock_level لا من قيمة المرجعي الخام', () => {
  const members = [
    brand({
      id: 5, family_id: 9, max_stock_level: 10, effective_max_stock_level: 99,
    }),
    brand({ id: 6, family_id: 9, max_stock_level: 30 }),
  ];
  const merged = buildFamilyRow(members);
  assert.equal(merged.max_stock_level, 99);
});

test('غياب الحدّ الحاكم (بيانات ما قبل #35) يُبقي حدّ المرجعي الخام كما هو', () => {
  const members = [
    brand({ id: 5, family_id: 9, min_stock_level: 10, max_stock_level: 20 }),
    brand({ id: 6, family_id: 9, min_stock_level: 30, max_stock_level: 40 }),
  ];
  const merged = buildFamilyRow(members);
  assert.equal(merged.min_stock_level, 10);
  assert.equal(merged.max_stock_level, 20);
});

test('لا رقم مجمَّع يُخزَّن: `buildFamilyRow` نقيّةٌ — نفس المُدخل يُنتج نفس المُخرج، ولا يُعدَّل المُدخل', () => {
  const members = [
    brand({ id: 1, family_id: 6, quantity_on_hand: 4 }),
    brand({ id: 2, family_id: 6, quantity_on_hand: 6 }),
  ];
  const snapshot = JSON.parse(JSON.stringify(members));
  buildFamilyRow(members);
  assert.deepEqual(members, snapshot);
});
