import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  STORAGE_CODE_MAX,
  STORAGE_COLUMN_MAX,
  STORAGE_ROW_MAX,
  blankStorageLocationDraft,
  nextStorageWarehouse,
  storageDraftsFromRows,
  storageLocationIssues,
  storageLocationLabel,
  storageLocationsChanged,
  storageLocationsPayload,
  storageWarehouseChoices,
  type StorageLocationDraft,
  type StorageLocationRow,
  type WarehouseOption,
} from './storageLocations.ts';

/**
 * TASK-2b — منطقُ موقع التخزين لكل مخزن، بلا React ولا fetch.
 *
 * كلُّ رسالةٍ هنا هي رسالةُ الخادم **حرفاً** (`inventory/serializers.py`:
 * `ProductStorageLocationWriteSerializer` و`ProductStorageLocationListSerializer`)
 * — رسالةٌ محلّية بصياغةٍ ثانية تُنتج نصّين لنفس الرفض، فيرى المستخدم هذا مرّةً
 * وذاك مرّة.
 */

const draft = (over: Partial<StorageLocationDraft> = {}): StorageLocationDraft => ({
  ...blankStorageLocationDraft(),
  warehouse: 13,
  warehouse_name: 'مخزن أ',
  ...over,
});

const row = (over: Partial<StorageLocationRow> = {}): StorageLocationRow => ({
  id: 3,
  warehouse: 13,
  warehouse_name: 'مخزن أ',
  kind: 'grid',
  column: 'B',
  row: '7',
  code: '',
  label: 'عمود B · صف 7',
  ...over,
});

const messages = (drafts: StorageLocationDraft[]) =>
  storageLocationIssues(drafts).map((issue) => `${issue.index}:${issue.field}:${issue.message}`);

test('«عمود وصف» بلا عمود يُرفض برسالة الخادم نفسها', () => {
  assert.deepEqual(messages([draft({ kind: 'grid', column: '   ', row: '7' })]),
    ['0:column:عمود الموقع مطلوب لنوع «عمود وصف»']);
});

test('«عمود وصف» بلا صفّ يُرفض برسالة الخادم نفسها', () => {
  assert.deepEqual(messages([draft({ kind: 'grid', column: 'B', row: '' })]),
    ['0:row:صفّ الموقع مطلوب لنوع «عمود وصف»']);
});

test('«رمز القسم» بلا رمزٍ يُرفض برسالة الخادم نفسها', () => {
  assert.deepEqual(messages([draft({ kind: 'code', column: 'B', row: '7', code: '  ' })]),
    ['0:code:رمز القسم مطلوب لنوع «رمز القسم»']);
});

test('القصّ قبل الفحص: « B » و« 7 » عمودٌ وصفٌّ صالحان', () => {
  assert.deepEqual(messages([draft({ kind: 'grid', column: ' B ', row: ' 7 ' })]), []);
  assert.deepEqual(messages([draft({ kind: 'code', code: ' A86 ' })]), []);
});

test('الحدود على المقصوص: 20 للعمود والصف و50 للرمز', () => {
  assert.deepEqual(messages([draft({ column: 'x'.repeat(STORAGE_COLUMN_MAX), row: '7' })]), []);
  assert.deepEqual(messages([draft({ column: 'x'.repeat(STORAGE_COLUMN_MAX + 1), row: '7' })]),
    [`0:column:العمود لا يزيد على ${STORAGE_COLUMN_MAX} حرفاً`]);
  assert.deepEqual(messages([draft({ column: 'B', row: 'x'.repeat(STORAGE_ROW_MAX + 1) })]),
    [`0:row:الصف لا يزيد على ${STORAGE_ROW_MAX} حرفاً`]);
  assert.deepEqual(messages([draft({ kind: 'code', code: 'x'.repeat(STORAGE_CODE_MAX) })]), []);
  assert.deepEqual(messages([draft({ kind: 'code', code: 'x'.repeat(STORAGE_CODE_MAX + 1) })]),
    [`0:code:رمز القسم لا يزيد على ${STORAGE_CODE_MAX} حرفاً`]);
});

test('الحقل الذي لا يخصّ النوع لا يُفحص ولا يُرسل', () => {
  // grid برمزٍ طويل: الرمز يُفرَّغ فليس خطأً.
  assert.deepEqual(messages([draft({ kind: 'grid', column: 'B', row: '7', code: 'x'.repeat(80) })]), []);
  // code بعمودٍ طويل وصفٍّ فارغ: الحقلان يُفرَّغان فليسا خطأين.
  assert.deepEqual(messages([draft({ kind: 'code', column: 'x'.repeat(80), row: '', code: 'A86' })]), []);
});

test('المخزن المكرَّر يُرفض برسالة الخادم نفسها وتسمّي المخزن — على السطر الثاني', () => {
  assert.deepEqual(messages([
    draft({ warehouse: 13, warehouse_name: 'مخزن أ', column: 'B', row: '7' }),
    draft({ warehouse: 13, warehouse_name: 'مخزن أ', column: 'C', row: '8' }),
  ]), ['1:warehouse:المخزن «مخزن أ» مكرَّر في القائمة — موقعٌ واحد لكل منتجٍ في المخزن']);
});

test('سطرٌ بلا مخزن يُرفض قبل فحص حقوله', () => {
  assert.deepEqual(messages([draft({ warehouse: null, warehouse_name: '', column: 'B', row: '7' })]),
    ['0:warehouse:المخزن مطلوب لكل موقع']);
});

test('جسم PUT: قصُّ القيم وتفريغ حقول النوع الآخر — الحقول الخمسة وحدها', () => {
  assert.deepEqual(storageLocationsPayload([
    draft({ warehouse: 13, kind: 'grid', column: ' B ', row: ' 7 ', code: 'A86' }),
    draft({ warehouse: 14, warehouse_name: 'مخزن ب', kind: 'code', column: 'C', row: '8', code: ' A86 ' }),
  ]), [
    { warehouse: 13, kind: 'grid', column: 'B', row: '7', code: '' },
    { warehouse: 14, kind: 'code', column: '', row: '', code: 'A86' },
  ]);
});

test('جسم PUT يستبعد السطر الذي لم يُختر له مخزن — لا `null` في القائمة', () => {
  assert.deepEqual(storageLocationsPayload([draft({ warehouse: null, column: 'B', row: '7' })]), []);
});

test('label يطابق صياغة الخادم حرفاً: «عمود {column} · صف {row}» أو الرمز', () => {
  assert.equal(storageLocationLabel('grid', 'B', '7', ''), 'عمود B · صف 7');
  assert.equal(storageLocationLabel('grid', ' B ', ' 7 ', 'A86'), 'عمود B · صف 7');
  assert.equal(storageLocationLabel('code', 'B', '7', 'A86'), 'A86');
  assert.equal(storageLocationLabel('code', '', '', ' A86 '), 'A86');
});

test('المحمَّل ← المحرَّر: لا تغيير يعني لا PUT', () => {
  const before = storageDraftsFromRows([row(), row({ id: 4, warehouse: 14, warehouse_name: 'مخزن ب', kind: 'code', column: '', row: '', code: 'A86', label: 'A86' })]);
  assert.equal(storageLocationsChanged(before, storageDraftsFromRows([row(), row({ id: 4, warehouse: 14, warehouse_name: 'مخزن ب', kind: 'code', column: '', row: '', code: 'A86', label: 'A86' })])), false);
});

test('ترتيب السطور وحده ليس تغييراً — المقارنة بمخزنٍ لا بفهرس', () => {
  const grid = draft({ warehouse: 13, column: 'B', row: '7' });
  const code = draft({ warehouse: 14, warehouse_name: 'مخزن ب', kind: 'code', code: 'A86' });
  assert.equal(storageLocationsChanged([grid, code], [code, grid]), false);
});

test('تغيير قيمةٍ أو نوعٍ أو إضافةُ سطرٍ أو حذفُه تغييرٌ يُرسَل', () => {
  const before = [draft({ warehouse: 13, column: 'B', row: '7' })];
  assert.equal(storageLocationsChanged(before, [draft({ warehouse: 13, column: 'B', row: '8' })]), true);
  assert.equal(storageLocationsChanged(before, [draft({ warehouse: 13, kind: 'code', code: 'A86' })]), true);
  assert.equal(storageLocationsChanged(before, []), true);
  assert.equal(storageLocationsChanged([], before), true);
});

test('صفُّ الخادم يُقرأ إلى سطر محرّر كما هو', () => {
  const [grid, code] = storageDraftsFromRows([
    row(),
    row({ id: 4, warehouse: 14, warehouse_name: 'مخزن ب', kind: 'code', column: '', row: '', code: 'A86', label: 'A86' }),
  ]);
  assert.deepEqual(grid, {
    warehouse: 13, warehouse_name: 'مخزن أ', kind: 'grid', column: 'B', row: '7', code: '',
  });
  assert.deepEqual(code, {
    warehouse: 14, warehouse_name: 'مخزن ب', kind: 'code', column: '', row: '', code: 'A86',
  });
});

const WAREHOUSES: WarehouseOption[] = [
  { id: 13, name: 'مخزن أ', is_active: true, is_default: true },
  { id: 14, name: 'مخزن ب', is_active: true, is_default: false },
  { id: 15, name: 'مخزن ج', is_active: false, is_default: false },
];

test('خيارات السطر: الفعّالة وحدها + المخزن المحفوظ ولو صار معطَّلاً', () => {
  const drafts = [draft({ warehouse: 15, warehouse_name: 'مخزن ج' })];
  // 13 و14 فعّالان فيبقى الانتقال إليهما ممكناً، و15 معطَّلٌ لكنه المحفوظ فلا يختفي.
  assert.deepEqual(storageWarehouseChoices(WAREHOUSES, drafts, 0).map((w) => w.id), [13, 14, 15]);
  assert.deepEqual(storageWarehouseChoices(WAREHOUSES, [], 0).map((w) => w.id), [13, 14]);
});

test('المخزن المختار في سطرٍ لا يظهر خياراً في سطرٍ آخر', () => {
  const drafts = [draft({ warehouse: 13 })];
  assert.deepEqual(storageWarehouseChoices(WAREHOUSES, drafts, -1).map((w) => w.id), [14]);
  assert.deepEqual(storageWarehouseChoices(WAREHOUSES, drafts, 0).map((w) => w.id), [13, 14]);
});

test('أول سطر يُقترح فيه المخزن الافتراضي، ثم أوّل مخزنٍ حرّ', () => {
  assert.equal(nextStorageWarehouse(WAREHOUSES, [])?.id, 13);
  assert.equal(nextStorageWarehouse(WAREHOUSES, [draft({ warehouse: 13 })])?.id, 14);
  assert.equal(nextStorageWarehouse(WAREHOUSES, [draft({ warehouse: 13 }), draft({ warehouse: 14, warehouse_name: 'مخزن ب' })]), null);
});
