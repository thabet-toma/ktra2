import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  AMOUNT_MASK,
  applyPackageSummary,
  frequencyAfterSuggestion,
  availableServicesForClient,
  clientFilePath,
  clientIdFromSearch,
  clientServiceStatusClass,
  clientStatusBadgeClass,
  customizedSettingCount,
  firstOfMonth,
  firstOfNextMonth,
  formatOfficeAmount,
  frequencyLabelFrom,
  missingFirstRunLabels,
  officeAssignableRoles,
  officeRoleLabel,
  officeSizeOf,
  showsOfficeAssignment,
  visibleClientSettings,
  type OfficeServiceRow,
  type SettingRow,
} from './accountingOffice.ts';

function row(overrides: Partial<SettingRow> & Pick<SettingRow, 'key' | 'label' | 'kind'>): SettingRow {
  return { levels: ['office'], choices: [], has_default: true, default: null, value: null, ...overrides };
}

const TAX_SYSTEM = row({
  key: 'tax_system',
  label: 'النظام الضريبي',
  kind: 'choice',
  levels: ['office', 'client'],
  choices: [{ value: 'PS', label: 'فلسطيني' }, { value: 'IL', label: 'إسرائيلي' }],
  has_default: false,
  value: 'IL',
  value_label: 'إسرائيلي',
});

const REST_DAYS = row({
  key: 'rest_days',
  label: 'يوم راحة الزبون',
  kind: 'weekdays',
  levels: ['office', 'client'],
  choices: [
    { value: 'sun', label: 'الأحد' },
    { value: 'fri', label: 'الجمعة' },
  ],
  default: ['fri'],
  value: ['fri'],
  value_label: 'الجمعة',
});

const FILING_METHOD = row({
  key: 'filing_method',
  label: 'طريقة التقديم',
  kind: 'choice',
  levels: ['office', 'client'],
  choices: [{ value: 'electronic', label: 'إلكتروني' }, { value: 'manual', label: 'يدوي' }],
  value: 'electronic',
  value_label: 'إلكتروني',
});

test('طريقة التقديم تظهر لزبونٍ إسرائيليّ وحده', () => {
  const settings = [TAX_SYSTEM, REST_DAYS, FILING_METHOD];
  assert.deepEqual(
    visibleClientSettings(settings, 'IL').map((s) => s.key),
    ['tax_system', 'rest_days', 'filing_method'],
  );
  assert.deepEqual(
    visibleClientSettings(settings, 'PS').map((s) => s.key),
    ['tax_system', 'rest_days'],
  );
  // النظام غير مختارٍ بعد: لا ادّعاء إسرائيليّ، فلا تُعرض.
  assert.deepEqual(
    visibleClientSettings(settings, null).map((s) => s.key),
    ['tax_system', 'rest_days'],
  );
});

test('«مخصَّص» يُشتقّ من قيمة الخادم وحدها، ويُعدّ صحيحاً', () => {
  const settings = [
    { ...TAX_SYSTEM, is_customized: true },
    { ...REST_DAYS, is_customized: false },
    { ...FILING_METHOD, is_customized: true },
  ];
  assert.equal(customizedSettingCount(settings), 2);
  assert.equal(customizedSettingCount(settings.map((s) => ({ ...s, is_customized: false }))), 0);
  assert.equal(customizedSettingCount([]), 0);
});

test('شارة الحالة: النشط أخضر والمنتهي رماديّ — والنصّ من الخادم', () => {
  assert.match(clientStatusBadgeClass('active'), /emerald/);
  assert.match(clientStatusBadgeClass('ended'), /slate/);
});

test('خطوة أول تشغيل تسمّي المفاتيح الناقصة بأسمائها', () => {
  assert.deepEqual(
    missingFirstRunLabels(['tax_system', 'office_size'], [TAX_SYSTEM, REST_DAYS]),
    ['النظام الضريبي', 'office_size'],
  );
  assert.deepEqual(missingFirstRunLabels([], [TAX_SYSTEM]), []);
});

test('معرّف الزبون يُقرأ من العنوان حين يكون صالحاً', () => {
  assert.equal(clientIdFromSearch('?client=12'), 12);
  assert.equal(clientIdFromSearch('client=7'), 7);
  assert.equal(clientIdFromSearch('?status=active&client=3'), 3);
});

test('عنوانٌ بلا معرّف أو بمعرّف فاسد يعود للقائمة لا للخطأ', () => {
  assert.equal(clientIdFromSearch(''), null);
  assert.equal(clientIdFromSearch('?status=active'), null);
  assert.equal(clientIdFromSearch('?client=abc'), null);
  assert.equal(clientIdFromSearch('?client=0'), null);
  assert.equal(clientIdFromSearch('?client=-4'), null);
});

const OFFICE_SIZE = row({
  key: 'office_size',
  label: 'حجم المكتب',
  kind: 'choice',
  choices: [
    { value: 'solo', label: 'شخص واحد' },
    { value: 'small', label: 'صغير' },
    { value: 'large', label: 'كبير' },
  ],
  has_default: false,
  value: 'solo',
  value_label: 'شخص واحد',
});

test('«شخص واحد» يُخفي عمود المسؤول والإسناد', () => {
  assert.equal(showsOfficeAssignment('solo'), false);
  assert.equal(showsOfficeAssignment('small'), true);
  assert.equal(showsOfficeAssignment('large'), true);
  // حجمٌ غائب لا يُخفي شيئاً: الخادم هو الحكم، والإخفاء عرضٌ فقط.
  assert.equal(showsOfficeAssignment(null), true);
});

test('حجم المكتب يُقرأ من سطر الإعداد وحده', () => {
  assert.equal(officeSizeOf([TAX_SYSTEM, OFFICE_SIZE]), 'solo');
  assert.equal(
    officeSizeOf([{ ...OFFICE_SIZE, value: 'large' }]),
    'large',
  );
  assert.equal(officeSizeOf([TAX_SYSTEM]), null);
});

test('المبلغ المخفيّ يُعرض «—»', () => {
  assert.equal(formatOfficeAmount(null), AMOUNT_MASK);
  assert.equal(formatOfficeAmount(undefined), AMOUNT_MASK);
  assert.equal(formatOfficeAmount(''), AMOUNT_MASK);
  assert.equal(formatOfficeAmount('1200.00'), '1200.00');
  assert.equal(formatOfficeAmount(0), '0');
});

test('«مالك» تسميةُ دور المدير في قسم أدوار المكتب وحده', () => {
  assert.equal(officeRoleLabel('manager', 'مدير'), 'مالك');
  assert.equal(officeRoleLabel('accountant', 'محاسب'), 'محاسب');
  assert.equal(officeRoleLabel('office_manager', 'مدير مكتب'), 'مدير مكتب');
});

const SERVER_ROLES = [
  { key: 'manager', label: 'مدير' },
  { key: 'office_manager', label: 'مدير مكتب' },
  { key: 'accountant', label: 'محاسب' },
  { key: 'viewer', label: 'مستعرض' },
  { key: 'sales', label: 'موظف مبيعات' },
];

test('أدوار المكتب أربعة، والقارئ في المكتب الكبير وحده', () => {
  assert.deepEqual(
    officeAssignableRoles(SERVER_ROLES, 'small').map((role) => role.key),
    ['manager', 'office_manager', 'accountant'],
  );
  assert.deepEqual(
    officeAssignableRoles(SERVER_ROLES, 'large').map((role) => role.key),
    ['manager', 'office_manager', 'accountant', 'viewer'],
  );
  // «شخص واحد» لا قسمَ أدوارٍ أصلاً.
  assert.deepEqual(officeAssignableRoles(SERVER_ROLES, 'solo'), []);
  // الدور الحاليّ خارج الأربعة يُعرض كما هو — وإلا كذب المنتقي على صاحبه.
  const withSales = officeAssignableRoles(SERVER_ROLES, 'small', 'sales');
  assert.equal(withSales[0].key, 'sales');
  assert.equal(withSales[0].label, 'موظف مبيعات');
});

test('الرابط يُبنى ويُقرأ بالدالة نفسها — لا نسختان تفترقان', () => {
  assert.equal(clientFilePath(), '/accounting-office/clients');
  assert.equal(clientFilePath(null), '/accounting-office/clients');
  assert.equal(clientFilePath(9), '/accounting-office/clients?client=9');
  const search = clientFilePath(9).slice('/accounting-office/clients'.length);
  assert.equal(clientIdFromSearch(search), 9);
});

// ── #273: الخدمات والباقات ──────────────────────────────────────────────
const SERVICE = (overrides: Partial<OfficeServiceRow> & Pick<OfficeServiceRow, 'id' | 'code'>): OfficeServiceRow => ({
  name: overrides.code,
  is_active: true,
  is_builtin: true,
  position: 0,
  ...overrides,
});

test('«من أيّ فترةٍ المكتب مسؤول» افتراضُها أولُ الشهر الحالي', () => {
  assert.equal(firstOfMonth('2026-04-17'), '2026-04-01');
  assert.equal(firstOfMonth('2026-04-01'), '2026-04-01');
  assert.equal(firstOfMonth('2026-12-31T23:10:00+02:00'), '2026-12-01');
  // سطرٌ فارغ أو غير مؤرَّخ لا يخترع تاريخاً — الحقلُ يبقى فارغاً.
  assert.equal(firstOfMonth(''), '');
  assert.equal(firstOfMonth('غير تاريخ'), '');
});

test('«سارية من» في تغيير الدورية = أولُ الشهر القادم', () => {
  assert.equal(firstOfNextMonth('2026-04-17'), '2026-05-01');
  assert.equal(firstOfNextMonth('2026-04-01'), '2026-05-01');
  // كانون الأول يعبر السنة — لا `2026-13-01`.
  assert.equal(firstOfNextMonth('2026-12-31'), '2027-01-01');
  assert.equal(firstOfNextMonth('2026-12-01T10:00:00'), '2027-01-01');
  assert.equal(firstOfNextMonth(''), '');
  assert.equal(firstOfNextMonth('غير تاريخ'), '');
});

test('منتقي «أضف خدمة» يُخفي المعطَّلة والمضافة نشطةً ويُبقي الموقوفة', () => {
  const bookkeeping = SERVICE({ id: 1, code: 'bookkeeping', name: 'مسك دفاتر' });
  const vat = SERVICE({ id: 2, code: 'vat', name: 'قيمة مضافة' });
  const payroll = SERVICE({ id: 3, code: 'payroll', name: 'رواتب' });
  const stoppedCatalog = SERVICE({ id: 4, code: 'custom-a', name: 'معطَّلة', is_active: false });
  const services = [
    { service: { id: 2 }, is_active: true },
    { service: { id: 3 }, is_active: false },
  ];
  assert.deepEqual(
    availableServicesForClient([bookkeeping, vat, payroll, stoppedCatalog], services).map((row) => row.code),
    ['bookkeeping', 'payroll'],
  );
  // زبونٌ بلا خدمات: كلُّ المفعّلة متاحة.
  assert.deepEqual(
    availableServicesForClient([bookkeeping, vat, stoppedCatalog], []).map((row) => row.code),
    ['bookkeeping', 'vat'],
  );
});

test('شارة حالة خدمة الزبون: النشطة أخضر والموقوفة رماديّ — والنصّ من الخادم', () => {
  assert.match(clientServiceStatusClass('active'), /emerald/);
  assert.match(clientServiceStatusClass('stopped'), /slate/);
});

test('تسميةُ الدورية تُقرأ من اختيارات الخادم وحدها', () => {
  const choices = [
    { value: 'monthly', label: 'شهري' },
    { value: 'bimonthly', label: 'كل شهرين' },
  ];
  assert.equal(frequencyLabelFrom(choices, 'bimonthly'), 'كل شهرين');
  assert.equal(frequencyLabelFrom(choices, ''), '');
  assert.equal(frequencyLabelFrom(choices, null), '');
  // قيمةٌ لا يعرفها الخادم تُعرض كما هي — لا تُطوى إلى تسميةٍ كاذبة.
  assert.equal(frequencyLabelFrom(choices, 'weekly'), 'weekly');
});

test('المقترحُ الجديد لا يكتب فوق دوريةٍ اختارها الموظف بيده', () => {
  assert.equal(
    frequencyAfterSuggestion({ frequency: 'annual', frequencyTouched: true }, 'monthly'),
    'annual',
  );
  assert.equal(
    frequencyAfterSuggestion({ frequency: 'annual', frequencyTouched: false }, 'monthly'),
    'monthly',
  );
  // بلا مقترحٍ ولم يلمس الموظف شيئاً ⇒ فراغٌ يطلب اختياراً صريحاً.
  assert.equal(
    frequencyAfterSuggestion({ frequency: 'annual', frequencyTouched: false }, null),
    '',
  );
});

test('ملخّص تطبيق الباقة يُسمّي ما أُضيف وما تُخطّي بأسماء الخادم', () => {
  const result = {
    added: [
      { service_id: 2, service_name: 'قيمة مضافة', client_service_id: 9, frequency: 'monthly' },
    ],
    skipped: [
      { service_id: 3, service_name: 'رواتب', reason: 'فترةٌ متداخلةٌ عند الزبون — لم تُمسّ دوريتُها' },
      { service_id: 4, service_name: 'استشارات ومعاملات', reason: 'معطَّلة في كتالوج المكتب' },
    ],
  };
  const summary = applyPackageSummary(result);
  assert.match(summary, /أُضيفت 1/);
  assert.match(summary, /قيمة مضافة/);
  // سببُ التخطّي يصل من الخادم فيظهر بجانب اسم كل خدمةٍ متخطّاة.
  assert.match(summary, /تُخطّي 2: رواتب \(فترةٌ متداخلةٌ عند الزبون — لم تُمسّ دوريتُها\)/);
  assert.match(summary, /استشارات ومعاملات \(معطَّلة في كتالوج المكتب\)/);
  // باقةٌ فارغة لا تقول «أُضيفت 0» بلا سبب — تقول إنها لم تُضف شيئاً.
  assert.match(applyPackageSummary({ added: [], skipped: [] }), /لم تُضف شيئاً/);
});
