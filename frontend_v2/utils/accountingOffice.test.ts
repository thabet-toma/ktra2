import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  AMOUNT_MASK,
  alertTargetPath,
  appointmentConfirmationView,
  appointmentSlotValue,
  appointmentStatusClass,
  applyPackageSummary,
  badgeLabelOf,
  canUndoReminderRow,
  clientTabFromSearch,
  commonTaxSystem,
  directionLabelOf,
  documentCellClass,
  documentCellGlyph,
  documentCellTone,
  documentDocsText,
  documentFileTag,
  documentGridRows,
  documentMissingBar,
  documentMonthColumns,
  documentMonthLabel,
  documentStatusChoicesFor,
  documentYearOptions,
  emptyDocumentCell,
  filterReadyToSendMessages,
  frequencyAfterSuggestion,
  availableServicesForClient,
  clientFilePath,
  clientIdFromSearch,
  clientServiceStatusClass,
  clientStatusBadgeClass,
  customizedSettingCount,
  deadlineRuleDescription,
  defaultExtensionDate,
  firstOfMonth,
  firstOfNextMonth,
  formatOfficeAmount,
  frequencyLabelFrom,
  groupAppointmentsByDay,
  groupDeadlinesByDay,
  isExpectedDeadline,
  isLockedOfficeSetting,
  isOpenAppointment,
  officeAppointmentAnchorId,
  missingFirstRunLabels,
  monthGrid,
  nextDayIso,
  nextMonthKey,
  obligationAmountText,
  obligationBadgeClass,
  obligationExtensionText,
  obligationOriginLabel,
  officeAssignableRoles,
  officeRoleLabel,
  officeSizeOf,
  officeWhatsappLink,
  officeWhatsappNumber,
  officeTaskAnchorId,
  overriddenRuleInput,
  periodLabel,
  platformOfficialText,
  previousMonthKey,
  readTodayFilter,
  readyToSendItemKeys,
  readyToSendMessageKey,
  readyToSendTypeChips,
  reminderLogKindClass,
  revertedReminderLogIds,
  shiftWeek,
  shortIsoDate,
  showsOfficeAssignment,
  settingsGroupFromSearch,
  statusLabelOf,
  taskIdFromSearch,
  todayFilterParams,
  uniqueDeadlineRules,
  visibleClientSettings,
  weekDays,
  weekRange,
  type CalendarDeadlineRow,
  type DeadlineRuleRow,
  type DocumentCell,
  type ObligationRow,
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

// ── #274: التقويم ────────────────────────────────────────────────────────
const CALENDAR_ROW = (
  overrides: Partial<CalendarDeadlineRow> &
    Pick<CalendarDeadlineRow, 'actual_deadline'>,
): CalendarDeadlineRow => ({
  client: { id: 1, name: 'زبون' },
  service: { code: 'vat', name: 'قيمة مضافة' },
  rule: { code: 'ps_vat_periodic', name: 'التقرير الدوري', needs_review: false },
  origin: 'official',
  origin_label: 'رسمي',
  period_start: '2026-01-01',
  period_end: '2026-01-31',
  period_label: 'كانون الثاني 2026',
  legal_date: overrides.actual_deadline,
  official_date: overrides.actual_deadline,
  internal_deadline: overrides.actual_deadline,
  platform_official_date: null,
  estimated: false,
  postponed: false,
  warnings: [],
  expected: true,
  ...overrides,
});

test('شبكة الشهر تبدأ بالأحد وتغطي أيامه كلها', () => {
  // كانون الثاني 2026: أوّلُه خميس، وفيه 31 يوماً ⇒ الأحد الأول 28/12/2025.
  const weeks = monthGrid('2026-01');
  assert.equal(weeks.length, 5);
  weeks.forEach((week) => assert.equal(week.length, 7));
  assert.equal(weeks[0][0].date, '2025-12-28');
  assert.equal(weeks[0][0].inMonth, false);
  assert.equal(weeks[0][4].date, '2026-01-01');
  assert.equal(weeks[0][4].inMonth, true);
  assert.equal(weeks[4][6].date, '2026-01-31');
  assert.equal(weeks[4][6].inMonth, true);
  const inMonth = weeks.flat().filter((day) => day.inMonth);
  assert.equal(inMonth.length, 31);
});

test('شبكة الشهر لا تنكسر على مفتاحٍ فاسد', () => {
  assert.deepEqual(monthGrid(''), []);
  assert.deepEqual(monthGrid('2026-13'), []);
  assert.deepEqual(monthGrid('غير شهر'), []);
});

test('مدى الأسبوع أحدٌ ← سبت', () => {
  assert.deepEqual(weekRange('2026-02-15'), {
    start: '2026-02-15',
    end: '2026-02-21',
  });
  // الجمعة داخل الأسبوع نفسه الذي بدأ بالأحد.
  assert.deepEqual(weekRange('2026-02-20'), {
    start: '2026-02-15',
    end: '2026-02-21',
  });
  assert.deepEqual(weekRange('غير تاريخ'), { start: '', end: '' });
});

test('التنقّل بين الشهور يعبر السنة', () => {
  assert.equal(nextMonthKey('2026-12'), '2027-01');
  assert.equal(previousMonthKey('2026-01'), '2025-12');
  assert.equal(nextMonthKey('2026-05'), '2026-06');
  assert.equal(nextMonthKey(''), '');
});

test('العناصر تُجمع على يوم موعدها الفعلي', () => {
  const grouped = groupDeadlinesByDay([
    CALENDAR_ROW({ actual_deadline: '2026-02-16' }),
    CALENDAR_ROW({ actual_deadline: '2026-02-16' }),
    CALENDAR_ROW({ actual_deadline: '2026-02-19' }),
  ]);
  assert.deepEqual(Object.keys(grouped).sort(), ['2026-02-16', '2026-02-19']);
  assert.equal(grouped['2026-02-16'].length, 2);
  assert.equal(grouped['2026-02-19'].length, 1);
});

test('تسمية الفترة احتياطاً تُطابق شكل الخادم', () => {
  assert.equal(periodLabel('2026-01-01', '2026-01-31'), 'كانون الثاني 2026');
  assert.equal(periodLabel('2026-01-01', '2026-03-31'), 'كانون الثاني–آذار 2026');
  assert.equal(periodLabel('2026-01-01', '2026-12-31'), '2026');
  assert.equal(
    periodLabel('2027-12-01', '2028-01-31'),
    'كانون الأول 2027–كانون الثاني 2028',
  );
  assert.equal(periodLabel('', ''), '');
});

test('السطر المحسوب «متوقَّع» ما لم يقل الخادم غير ذلك', () => {
  assert.equal(isExpectedDeadline(CALENDAR_ROW({ actual_deadline: '2026-02-16' })), true);
  assert.equal(
    isExpectedDeadline(CALENDAR_ROW({ actual_deadline: '2026-02-16', expected: false })),
    false,
  );
});

test('أيام الأسبوع سبعةٌ من الأحد، وتُزاح أسبوعاً بضغطة', () => {
  assert.deepEqual(weekDays('2026-02-18'), [
    '2026-02-15', '2026-02-16', '2026-02-17', '2026-02-18',
    '2026-02-19', '2026-02-20', '2026-02-21',
  ]);
  // الأحد نفسُه يبقى أوّلَ الأسبوع.
  assert.equal(weekDays('2026-02-15')[0], '2026-02-15');
  assert.deepEqual(weekDays('غير تاريخ'), []);

  assert.equal(shiftWeek('2026-02-18', 1), '2026-02-25');
  assert.equal(shiftWeek('2026-02-18', -1), '2026-02-11');
  // عبورُ السنة في الاتجاهين.
  assert.equal(shiftWeek('2026-12-30', 1), '2027-01-06');
  assert.equal(shiftWeek('2027-01-01', -1), '2026-12-25');
  assert.equal(shiftWeek('غير تاريخ', 1), '');
});

test('فلتر النوع بلا تكرارٍ بالكود — الأحدثُ سنةً يغلب، والترتيبُ بالاسم لا بالكود', () => {
  const PLATFORM = {
    rule_kind: 'day_of_next_month',
    rule_kind_label: '',
    rule_day: 15,
    rule_month: null,
    electronic_extension_days: 0,
  };
  const rules = [
    { code: 'ps_vat_periodic', rule_code: 'ps_vat_periodic', name: 'أ قديم', service_code: 'vat', is_generated: true, needs_review: false, year: 2026, version: 1, source_url: '', platform: PLATFORM, override: null, history: [], awaiting_decision: false },
    { code: 'ps_vat_periodic', rule_code: 'ps_vat_periodic', name: 'أ ضريبة', service_code: 'vat', is_generated: true, needs_review: false, year: 2027, version: 1, source_url: '', platform: PLATFORM, override: null, history: [], awaiting_decision: false },
    { code: 'ps_annual_return', rule_code: 'ps_annual_return', name: 'سنوي', service_code: 'annual_accounts', is_generated: true, needs_review: false, year: 2026, version: 1, source_url: '', platform: PLATFORM, override: null, history: [], awaiting_decision: false },
  ];
  const unique = uniqueDeadlineRules(rules);

  // «أ ضريبة» قبل «سنوي» بالاسم، وكودُها بعد `ps_annual_return` — الترتيبان مختلفان.
  assert.deepEqual(unique.map((rule) => rule.code), ['ps_vat_periodic', 'ps_annual_return']);
  assert.equal(unique.find((rule) => rule.code === 'ps_vat_periodic')!.name, 'أ ضريبة');
  assert.deepEqual(uniqueDeadlineRules([]), []);
});

// ── «اليوم» والالتزامات (#275) ─────────────────────────────────────────
function OBLIGATION(overrides: Partial<ObligationRow> = {}): ObligationRow {
  return {
    id: 1,
    client: { id: 7, name: 'أبو أحمد' },
    task: {
      id: 3,
      internal_deadline: '2026-02-10',
      assignee: { id: 5, name: 'سالم' },
    },
    name: 'דוח תקופתי למע"מ',
    rule_code: 'il_vat_periodic',
    origin: 'official',
    origin_label: 'رسمي',
    period_label: 'كانون الثاني 2026',
    official_date: '2026-02-15',
    actual_deadline: '2026-02-19',
    internal_deadline: '2026-02-10',
    due_date: '2026-02-19',
    extended_to: null,
    extension_note: '',
    platform_official_date: null,
    estimated: false,
    warnings: [],
    badges: [],
    amount: null,
    direction: '',
    direction_label: '',
    client_paid: false,
    status: 'pending',
    status_label: 'لسا ما انقدّم',
    // #278: لا صفوفَ أوراقٍ في هذا المُصنِّع — والاختبارُ يُمرّر `docs` عند الحاجة.
    docs: null,
    ...overrides,
  };
}

test('تسميات الحالة والاتجاه والشارة من الخادم — ولا نسخةً محليّة تنافسها', () => {
  const row = OBLIGATION({
    status: 'submitted',
    status_label: 'انقدّم',
    direction: 'due',
    direction_label: 'عليه',
    badges: [{ key: 'late', label: 'متأخّر رسمي' }],
  });

  assert.equal(statusLabelOf(row), 'انقدّم');
  assert.equal(directionLabelOf(row), 'عليه');
  assert.equal(badgeLabelOf(row.badges[0]), 'متأخّر رسمي');

  // نصٌّ غائبٌ من الخادم ⇒ القيمةُ الخام، لا تسميةٌ مخترعةٌ هنا.
  assert.equal(statusLabelOf({ status: 'unknown', status_label: '' }), 'unknown');
  assert.equal(directionLabelOf({ direction: 'due', direction_label: '   ' }), 'due');
  assert.equal(badgeLabelOf({ key: 'near', label: '' }), 'near');
});

test('نصّ المبلغ: الاتجاه والشيكل، والمخفيُّ «—» وحدها', () => {
  assert.equal(
    obligationAmountText({ amount: '620.00', direction_label: 'عليه' }),
    'عليه ₪ 620.00',
  );
  assert.equal(
    obligationAmountText({ amount: '50.00', direction_label: 'إله' }),
    'إله ₪ 50.00',
  );
  assert.equal(obligationAmountText({ amount: '620.00', direction_label: '' }), '₪ 620.00');
  // `null` = لا رؤية مبالغ: لا «0» ولا «عليه ₪ null».
  assert.equal(obligationAmountText({ amount: null, direction_label: 'عليه' }), AMOUNT_MASK);
  assert.equal(obligationAmountText({ amount: '', direction_label: '' }), AMOUNT_MASK);
});

test('فلتر اليوم يُقرأ من العنوان: المعروف يبقى والمجهول «الكل»', () => {
  assert.equal(readTodayFilter('?filter=mine'), 'mine');
  assert.equal(readTodayFilter('filter=week'), 'week');
  assert.equal(readTodayFilter('?filter=late&x=1'), 'late');
  assert.equal(readTodayFilter('?filter=someday'), '');
  assert.equal(readTodayFilter('?filter='), '');
  assert.equal(readTodayFilter(''), '');
  // #276: الدرجةُ الداخليّة فلترٌ رابعٌ معروف.
  assert.equal(readTodayFilter('?filter=late_internal'), 'late_internal');
  assert.equal(readTodayFilter('filter=late_internal&filter=late'), 'late_internal');
  assert.equal(readTodayFilter('?filter=Late'), '', 'المفتاحُ حسّاسٌ لحالة الأحرف');
  // الكتابةُ في العنوان: «الكل» بلا معامل.
  assert.deepEqual(todayFilterParams('mine'), { filter: 'mine' });
  assert.deepEqual(todayFilterParams('late_internal'), { filter: 'late_internal' });
  assert.deepEqual(todayFilterParams(''), {});
});

test('أصناف الشارة الثلاث: أحمرُ وأصفرُ ومحايد', () => {
  const late = obligationBadgeClass('late');
  const internal = obligationBadgeClass('late_internal');
  const near = obligationBadgeClass('near');

  assert.match(late, /border-rose-200 bg-rose-50 text-rose-700/);
  assert.match(late, /dark:/);
  assert.match(internal, /border-amber-200 bg-amber-50 text-amber-700/);
  assert.match(internal, /dark:/);
  // «قريب» لم يعد أصفر: لونُه محايدٌ لئلا يلتبس بالمتأخّر الداخلي.
  assert.match(near, /border-slate-200 bg-slate-50 text-slate-700/);
  assert.match(near, /dark:/);
  assert.doesNotMatch(near, /amber-/);
  assert.doesNotMatch(internal, /rose-/);
  // مفتاحٌ غير معروف يأخذ المحايد لا انفجاراً.
  assert.match(obligationBadgeClass('someday'), /border-slate-200/);
});

test('وجهةُ التنبيه: ملفّ الزبون على تبويب «الالتزامات والشغلات»', () => {
  assert.equal(
    alertTargetPath({ client: { id: 7 } }),
    '/accounting-office/clients?client=7&tab=obligations',
  );
  // وتنبيهُ شغلةٍ يضيف معرّفها فيُمرَّر إليها ويُبرز.
  assert.equal(
    alertTargetPath({ client: { id: 7 }, task_id: 12 }),
    '/accounting-office/clients?client=7&tab=obligations&task=12',
  );
  assert.equal(
    alertTargetPath({ client: { id: 7 }, task_id: null }),
    '/accounting-office/clients?client=7&tab=obligations',
  );
  // تنبيهٌ بلا زبون لا وجهةَ له — لا رابطَ يفتح العدم.
  assert.equal(alertTargetPath({ client: null }), '');

  // والتبويبُ يُقرأ من العنوان بالمعروف وحده.
  assert.equal(clientTabFromSearch('?client=7&tab=obligations'), 'obligations');
  assert.equal(clientTabFromSearch('tab=services'), 'services');
  assert.equal(clientTabFromSearch('?tab=someday'), null);
  assert.equal(clientTabFromSearch('?tab='), null);
  assert.equal(clientTabFromSearch(''), null);
});

test('شغلةُ التنبيه: تُقرأ من العنوان وتُمرَّر إلى عنصرها', () => {
  assert.equal(taskIdFromSearch('?client=7&tab=obligations&task=12'), 12);
  assert.equal(taskIdFromSearch('task=3'), 3);
  assert.equal(taskIdFromSearch('?task=0'), null);
  assert.equal(taskIdFromSearch('?task=-4'), null);
  assert.equal(taskIdFromSearch('?task=abc'), null);
  assert.equal(taskIdFromSearch('?tab=obligations'), null);
  assert.equal(taskIdFromSearch(''), null);
  // وعنصرُ الشغلة معرّفٌ واحدٌ يبنيه الرابط ويقرؤه التمرير.
  assert.equal(officeTaskAnchorId(12), 'office-task-12');
});

test('التاريخ القصير dd/MM من ISO بلا كائن Date', () => {
  assert.equal(shortIsoDate('2026-02-19'), '19/02');
  assert.equal(shortIsoDate('2026-04-30T23:00-05:00'), '30/04');
  assert.equal(shortIsoDate(''), '');
  assert.equal(shortIsoDate(null), '');
  assert.equal(shortIsoDate('غير تاريخ'), '');
});


// ── تعديل المكتب والتمديد والأحداث (#277) ────────────────────────────────

test('وصفُ قاعدة السطر — نصٌّ مقروءٌ من نوعها وأيامها', () => {
  assert.equal(
    deadlineRuleDescription({ rule_kind: 'day_of_next_month', rule_day: 15 }),
    'يوم 15 من الشهر التالي',
  );
  assert.equal(
    deadlineRuleDescription({ rule_kind: 'end_of_period' }),
    'آخر يوم في الفترة',
  );
  assert.equal(
    deadlineRuleDescription({
      rule_kind: 'month_day_next_year', rule_month: 4, rule_day: 30,
    }),
    'يوم 30 من الشهر 4 من السنة التالية',
  );
  assert.equal(
    deadlineRuleDescription({ rule_kind: 'days_after_event', rule_day: 30 }),
    'بعد 30 يوماً من الحدث',
  );
  // ونوعٌ لا وصفَ حسابيّاً له يعيد تسميةَ الخادم — لا فراغاً.
  assert.equal(
    deadlineRuleDescription({ rule_kind: 'brand_new', rule_kind_label: 'نوع جديد' }),
    'نوع جديد',
  );
  assert.equal(deadlineRuleDescription({ rule_kind: 'day_of_next_month' }), 'الشهر التالي');
});

test('وصفُ تعديلٍ جزئيّ — الحقلُ الفارغ يأخذ قيمةَ المنصة لا يُفرغ الوصف', () => {
  // `ps_annual_return`: يوم 30 من الشهر 4 من السنة التالية على المنصة.
  const platform = {
    rule_kind: 'month_day_next_year',
    rule_kind_label: 'يوم في السنة التالية',
    rule_day: 30,
    rule_month: 4,
  };

  // الشهرُ متروك ⇒ شهرُ المنصة.
  assert.equal(
    deadlineRuleDescription(overriddenRuleInput(platform, { rule_day: 15, rule_month: null })),
    'يوم 15 من الشهر 4 من السنة التالية',
  );
  // اليومُ متروك ⇒ يومُ المنصة.
  assert.equal(
    deadlineRuleDescription(overriddenRuleInput(platform, { rule_day: null, rule_month: 6 })),
    'يوم 30 من الشهر 6 من السنة التالية',
  );
  // الاثنان معاً ⇒ تعديلُ المكتب يغلب.
  assert.equal(
    deadlineRuleDescription(overriddenRuleInput(platform, { rule_day: 15, rule_month: 6 })),
    'يوم 15 من الشهر 6 من السنة التالية',
  );
});

test('تبويبُ الإعدادات يُقرأ من العنوان — والمعروفُ وحده', () => {
  assert.equal(settingsGroupFromSearch('?group=schedule'), 'schedule');
  assert.equal(settingsGroupFromSearch('group=alerts'), 'alerts');
  assert.equal(settingsGroupFromSearch('?group=someday'), null);
  assert.equal(settingsGroupFromSearch('?group='), null);
  assert.equal(settingsGroupFromSearch(''), null);
});

test('وجهةُ التنبيه تتبع opens — وشاشةُ اللائحة لمن تعدّى ملفَّ الزبون', () => {
  assert.equal(
    alertTargetPath({
      client: null, opens: 'deadline_rules',
    }),
    '/accounting-office/settings?group=schedule',
  );
  // ونوعُ الالتزام يبقى على ملفّ الزبون ولو حمل opens فارغاً.
  assert.equal(
    alertTargetPath({
      client: { id: 7 }, task_id: 12, opens: 'client',
    }),
    '/accounting-office/clients?client=7&tab=obligations&task=12',
  );
  assert.equal(alertTargetPath({ client: null, opens: 'client' }), '');
});

test('نصُّ التمديد وشارةُ الأصل — من حقول الخادم وحدها', () => {
  assert.equal(
    obligationExtensionText({ extended_to: '2026-04-15', extension_note: 'مدّدنا' }),
    'ممدَّد حتى 15/04 — مدّدنا',
  );
  assert.equal(
    obligationExtensionText({ extended_to: '2026-04-15', extension_note: '  ' }),
    'ممدَّد حتى 15/04',
  );
  assert.equal(obligationExtensionText({ extended_to: null, extension_note: '' }), '');
  // والرسميُّ بلا شارة: العلامةُ لما جاء من المكتب أو من حدث.
  assert.equal(obligationOriginLabel({ origin: 'official', origin_label: 'رسمي' }), '');
  assert.equal(
    obligationOriginLabel({ origin: 'office', origin_label: 'من المكتب' }), 'من المكتب',
  );
  assert.equal(obligationOriginLabel({ origin: 'event', origin_label: 'حدث' }), 'حدث');
  // والمنصة: تاريخها يظهر بجانب تاريخ المكتب حين يختلفان.
  assert.equal(platformOfficialText({ platform_official_date: '2026-02-16' }), 'المنصة: 16/02');
  assert.equal(platformOfficialText({ platform_official_date: null }), '');
});

test('تاريخُ التمديد المقترح بعد الموعد الساري بثلاثين يوماً', () => {
  assert.equal(defaultExtensionDate('2026-02-15'), '2026-03-17');
  // عبورُ السنة والشهر القصير لا يكسران الحساب (UTC بلا منطقةٍ زمنية).
  assert.equal(defaultExtensionDate('2026-12-20'), '2027-01-19');
  assert.equal(defaultExtensionDate('2026-01-31'), '2026-03-02');
  assert.equal(defaultExtensionDate('غير تاريخ'), '');
});

// ── قائمة الأوراق وشبكة الأشهر (#278) ───────────────────────────────────────

function cellOf(overrides: Partial<DocumentCell> & Pick<DocumentCell, 'month'>): DocumentCell {
  return {
    row_id: 1,
    status: 'required',
    status_label: 'مطلوبة',
    received_on: null,
    received_by_name: '',
    channel: '',
    channel_label: '',
    files_count: 0,
    ...overrides,
  };
}

test('كلُّ صفٍّ في شبكة الأوراق بعدد الأشهر نفسه — والفارغُ خانةٌ محايدة', () => {
  const payload = {
    months: ['2026-01-01', '2026-02-01'],
    items: [
      {
        item_code: 'a',
        name: 'فواتير المبيعات',
        cells: [cellOf({ month: '2026-01-01' }), cellOf({ month: '2026-02-01' })],
      },
      {
        // الخادمُ أرسل خانةً واحدة: الشبكةُ تُكمل الثانية ولا تُزيح الصفوف.
        item_code: 'b',
        name: 'كشف البنك',
        cells: [cellOf({ month: '2026-01-01' })],
      },
    ],
  };

  const rows = documentGridRows(payload);

  assert.deepEqual(rows.map((row) => row.cells.length), [2, 2]);
  assert.equal(rows[1].cells[1].month, '2026-02-01');
  assert.equal(rows[1].cells[1].row_id, null);
  assert.equal(documentCellTone(rows[1].cells[1]), 'empty');
});

test('الخاناتُ بأشهرها لا بترتيبها — ترتيبٌ مبدَّلٌ لا يخلط الأعمدة', () => {
  const payload = {
    months: ['2026-01-01', '2026-02-01'],
    items: [
      {
        item_code: 'a',
        name: 'بند',
        cells: [cellOf({ month: '2026-02-01', row_id: 9 }), cellOf({ month: '2026-01-01', row_id: 8 })],
      },
    ],
  };

  const [row] = documentGridRows(payload);

  assert.deepEqual(row.cells.map((cell) => cell.row_id), [8, 9]);
});

test('أسماءُ الأشهر في رأس الشبكة بلا سنة — من جدول monthKey وحده', () => {
  assert.equal(documentMonthLabel('2026-01-01'), 'كانون الثاني');
  assert.deepEqual(documentMonthColumns(['2026-10-01']), [
    { iso: '2026-10-01', label: 'تشرين الأول' },
  ]);
});

test('ألوانُ الحالات الخمس ورمزُها كما في النموذج المرئي', () => {
  assert.equal(documentCellTone(cellOf({ month: '2026-01-01', status: 'received' })), 'received');
  assert.equal(documentCellTone(cellOf({ month: '2026-01-01', status: 'partial' })), 'partial');
  assert.equal(documentCellTone(cellOf({ month: '2026-01-01', status: 'not_needed' })), 'skipped');
  assert.equal(documentCellTone(cellOf({ month: '2026-01-01', status: 'required' })), 'required');
  assert.equal(documentCellTone(emptyDocumentCell('2026-01-01')), 'empty');

  assert.equal(documentCellGlyph(cellOf({ month: '2026-01-01', status: 'received' })), '✓');
  assert.equal(documentCellGlyph(cellOf({ month: '2026-01-01', status: 'partial' })), '!');
  assert.equal(documentCellGlyph(cellOf({ month: '2026-01-01', status: 'not_needed' })), '–');
  assert.equal(documentCellGlyph(emptyDocumentCell('2026-01-01')), '');

  // «وصلت» خضراء و«ناقصة» كهرمانية و«مطلوبة» حمراء الإطار — لا نصَّ هنا.
  assert.match(documentCellClass(cellOf({ month: '2026-01-01', status: 'received' })), /emerald/);
  assert.match(documentCellClass(cellOf({ month: '2026-01-01', status: 'partial' })), /amber/);
  assert.match(documentCellClass(cellOf({ month: '2026-01-01', status: 'required' })), /rose/);
});

test('عدّادُ «وصل 3/5» يقف حيث لا صفوفَ محسوبة', () => {
  assert.equal(documentDocsText(null), '');
  assert.equal(documentDocsText({ received: 0, required: 0 }), '');
  assert.equal(documentDocsText({ received: 3, required: 5 }), 'وصل 3/5');
  assert.equal(documentDocsText({ received: 5, required: 5 }), 'وصل 5/5');
});

test('شريطُ «ناقص لشهر…» يعدّ آخر شهرٍ ويسمّي بنودَه', () => {
  const payload = {
    months: ['2026-01-01', '2026-02-01'],
    items: [
      {
        item_code: 'a',
        name: 'كشف البنك',
        cells: [
          cellOf({ month: '2026-01-01', status: 'received' }),
          cellOf({ month: '2026-02-01', status: 'required' }),
        ],
      },
      {
        item_code: 'b',
        name: 'فواتير المشتريات',
        cells: [
          cellOf({ month: '2026-01-01', status: 'received' }),
          cellOf({ month: '2026-02-01', status: 'partial' }),
        ],
      },
    ],
  };

  const bar = documentMissingBar(payload);

  assert.equal(bar?.monthLabel, 'شباط');
  assert.deepEqual(bar?.names, ['كشف البنك', 'فواتير المشتريات']);
  assert.equal(bar?.counts, '1 مطلوبة · 1 ناقصة');
});

test('شريطُ الناقص يغيب حين لا ينقص شيء', () => {
  const payload = {
    months: ['2026-02-01'],
    items: [
      {
        item_code: 'a',
        name: 'كشف البنك',
        cells: [cellOf({ month: '2026-02-01', status: 'received' })],
      },
      {
        item_code: 'b',
        name: 'ورقة',
        cells: [cellOf({ month: '2026-02-01', status: 'not_needed' })],
      },
    ],
  };

  assert.equal(documentMissingBar(payload), null);
  assert.equal(documentMissingBar({ months: [], items: [] }), null);
});

test('تسميةُ «مش لازمة» في القائمة السنوية سنةٌ لا شهر', () => {
  const choices = [
    { value: 'required', label: 'مطلوبة' },
    { value: 'not_needed', label: 'مش لازمة هالشهر', annual_label: 'مش لازمة هالسنة' },
  ];

  assert.deepEqual(documentStatusChoicesFor(choices, true).map((entry) => entry.label), [
    'مطلوبة',
    'مش لازمة هالسنة',
  ]);
  assert.deepEqual(documentStatusChoicesFor(choices, false).map((entry) => entry.label), [
    'مطلوبة',
    'مش لازمة هالشهر',
  ]);
});

test('وسمُ الملف والسنوات المتاحة من الخادم', () => {
  assert.equal(documentFileTag({ copy_label: '  صورة — الأصل عند الزبون ' }), 'صورة — الأصل عند الزبون');
  assert.equal(documentFileTag({ copy_label: '' }), '');
  assert.deepEqual(documentYearOptions({ available_years: [2026, 2025] }), [2026, 2025]);
});

test('فلترُ «ناقصه أوراق» يُقرأ ويُكتب في العنوان', () => {
  assert.equal(readTodayFilter('?filter=missing_docs'), 'missing_docs');
  assert.deepEqual(todayFilterParams('missing_docs'), { filter: 'missing_docs' });
});

test('رقمُ واتساب المكتب من رقمٍ محلّي فلسطيني', () => {
  // 059/056 جوالٌ فلسطينيّ — مفتاحُ الدولة 970 والباقي بعد الصفر.
  assert.equal(officeWhatsappNumber('0599123456', 'PS'), '970599123456');
  assert.equal(officeWhatsappNumber('0569123456', 'PS'), '970569123456');
  // بلا نظامٍ ضريبي: البادئة نفسها تحكم، فلا حاجةَ إلى مفتاح الدولة.
  assert.equal(officeWhatsappNumber('0599123456', null), '970599123456');
});

test('جوالٌ إسرائيليّ (05 بغير 059/056) يأخذ 972', () => {
  assert.equal(officeWhatsappNumber('0501234567', 'IL'), '972501234567');
  assert.equal(officeWhatsappNumber('0521234567', 'PS'), '972521234567');
});

test('أرضيٌّ محلّي بأيّ نظامٍ ضريبيّ يأخذ مفتاح دولته', () => {
  assert.equal(officeWhatsappNumber('022345678', 'PS'), '97022345678');
  assert.equal(officeWhatsappNumber('022345678', 'IL'), '97222345678');
  assert.equal(officeWhatsappNumber('042345678', 'IL'), '97242345678');
  // نظامٌ مجهول: أرضيٌّ بلا مفتاحِ دولةٍ معلوم ⇒ لا رابط، لا تخمين.
  assert.equal(officeWhatsappNumber('022345678', null), null);
  assert.equal(officeWhatsappNumber('022345678', 'JO'), null);
});

test('الرقمُ الدوليّ يمرّ كما هو بلا إعادة بناء', () => {
  assert.equal(officeWhatsappNumber('+970599123456', 'PS'), '970599123456');
  assert.equal(officeWhatsappNumber('+972 50-123-4567', 'IL'), '972501234567');
  assert.equal(officeWhatsappNumber('00972599123456', 'PS'), '972599123456');
  assert.equal(officeWhatsappNumber('00970 59 912 3456', null), '970599123456');
});

test('رقمٌ غير صالح أو قصيرٌ جداً يعطي null لا رابطاً يبدو صالحاً', () => {
  assert.equal(officeWhatsappNumber('', 'PS'), null);
  assert.equal(officeWhatsappNumber(null, 'PS'), null);
  assert.equal(officeWhatsappNumber(undefined, 'PS'), null);
  assert.equal(officeWhatsappNumber('abc', 'PS'), null);
  assert.equal(officeWhatsappNumber('12', 'PS'), null);
  assert.equal(officeWhatsappNumber('0599', 'PS'), null);
  assert.equal(officeWhatsappNumber('+0599123456', 'PS'), null);
  assert.equal(officeWhatsappNumber('1234567890123456', 'PS'), null);
});

test('رابطُ المحادثة يرمّز النصَّ ويعطي null مع رقمٍ غير صالح', () => {
  const text = 'أهلاً أبو أحمد، ناقصنا فاتورة مشتريات.';
  assert.equal(
    officeWhatsappLink('0599123456', 'PS', text),
    `https://wa.me/970599123456?text=${encodeURIComponent(text)}`,
  );
  assert.equal(officeWhatsappLink('12', 'PS', text), null);
  assert.equal(officeWhatsappLink('abc', 'PS', text), null);
  assert.equal(officeWhatsappLink('', 'IL', text), null);
});

// ── #280/ب: «جاهز للإرسال» وسجلّ التذكيرات ───────────────────────────────────
//
// الرسالةُ وحدةُ العرض: بندٌ لكل (زبون، نوع، فترة)، وشخصٌ واحدٌ يأخذ رسالةً
// واحدةً فيها بنودُه. والبنودُ هنا مختصرةٌ بالحقول التي تقرؤها الدوالّ وحدها —
// والباقي (النصُّ والشارة والهاتف) يعرضه المكوّنُ كما وصل من الخادم.

const DOCUMENT_ITEM = {
  client_id: 3,
  reminder_type: 'documents',
  reminder_type_label: 'أوراق ناقصة',
  period_start: '2026-10-01',
  period_end: '2026-10-31',
};

const DEADLINE_ITEM = {
  client_id: 3,
  reminder_type: 'deadline',
  reminder_type_label: 'موعد رسمي قريب',
  period_start: '2026-11-01',
  period_end: '2026-11-30',
};

const MESSAGE_ONE = { recipient: { contact_id: 11 }, items: [DOCUMENT_ITEM] };
const MESSAGE_TWO = { recipient: { contact_id: 11 }, items: [DEADLINE_ITEM] };
const MESSAGE_MERGED = {
  recipient: { contact_id: 11 },
  items: [DOCUMENT_ITEM, DEADLINE_ITEM],
};

test('مفاتيحُ الفعل أربعةٌ فقط: الزبون والنوع وطرفا الفترة', () => {
  const keys = readyToSendItemKeys(MESSAGE_MERGED);
  assert.deepEqual(keys, [
    {
      client_id: 3,
      reminder_type: 'documents',
      period_start: '2026-10-01',
      period_end: '2026-10-31',
    },
    {
      client_id: 3,
      reminder_type: 'deadline',
      period_start: '2026-11-01',
      period_end: '2026-11-30',
    },
  ]);
  // لا تُرسَل تسميةٌ ولا نصُّ بند: الخادم يعرف بندَه من الأربعة وحدها.
  assert.deepEqual(
    Object.keys(keys[0]),
    ['client_id', 'reminder_type', 'period_start', 'period_end'],
  );
});

test('رقائقُ النوع: «الكل» أوّلاً ثم ما له رسائلُ اليوم بتسمية الخادم', () => {
  assert.deepEqual(
    readyToSendTypeChips([MESSAGE_ONE, MESSAGE_TWO, MESSAGE_MERGED]),
    [
      { value: '', label: 'الكل', count: 3 },
      { value: 'documents', label: 'أوراق ناقصة', count: 2 },
      { value: 'deadline', label: 'موعد رسمي قريب', count: 2 },
    ],
  );
  // يومٌ بلا رسائلَ لا رقاقةَ فيه — ولا رقاقةَ «الكل» وحدها.
  assert.deepEqual(readyToSendTypeChips([]), []);
});

test('ترشيحُ النوع يُبقي الرسالة كاملةً إذا حملت بنداً من نوعه', () => {
  const messages = [MESSAGE_ONE, MESSAGE_MERGED];
  assert.equal(filterReadyToSendMessages(messages, '').length, 2);
  assert.equal(filterReadyToSendMessages(messages, 'deadline').length, 1);
  // النوعُ المختار يبقى رسالةً واحدةً كاملةً — لا تُقصّ بنودُها الأخرى.
  assert.equal(filterReadyToSendMessages(messages, 'deadline')[0].items.length, 2);
  assert.deepEqual(filterReadyToSendMessages(messages, 'appointment'), []);
});

test('مفتاحُ الرسالة يميّز رسالتَي شخصٍ واحدٍ ولا يتغيّر بترتيب البنود', () => {
  assert.notEqual(readyToSendMessageKey(MESSAGE_ONE), readyToSendMessageKey(MESSAGE_TWO));
  assert.equal(
    readyToSendMessageKey({ recipient: { contact_id: 11 }, items: [DOCUMENT_ITEM, DEADLINE_ITEM] }),
    readyToSendMessageKey({ recipient: { contact_id: 11 }, items: [DEADLINE_ITEM, DOCUMENT_ITEM] }),
  );
});

test('صفوفُ undo تُعلَّم مُبطَلةً بمعرّف ما تُبطله', () => {
  const rows = [
    { id: 9, kind: 'undo', reverts_id: 4 },
    { id: 4, kind: 'sent', reverts_id: null },
  ];
  assert.deepEqual([...revertedReminderLogIds(rows)], [4]);
  assert.deepEqual([...revertedReminderLogIds([])], []);
});

test('«ما انبعتت» على إرسالٍ أو مكالمةٍ لم يُبطَل أحدُهما', () => {
  const rows = [
    { id: 4, kind: 'sent', reverts_id: null },
    { id: 9, kind: 'undo', reverts_id: 4 },
  ];
  const reverted = revertedReminderLogIds(rows);
  assert.equal(canUndoReminderRow({ id: 4, kind: 'sent' }, reverted), false);
  assert.equal(canUndoReminderRow({ id: 5, kind: 'sent' }, reverted), true);
  assert.equal(canUndoReminderRow({ id: 6, kind: 'manual' }, reverted), true);
  // التنحيةُ وصفُّ التصحيح ليسا إرسالاً فلا يُبطلان.
  assert.equal(canUndoReminderRow({ id: 7, kind: 'dismissed' }, reverted), false);
  assert.equal(canUndoReminderRow({ id: 9, kind: 'undo' }, reverted), false);
});
test('شارةُ نوع الصفّ: أربعةُ ألوانٍ ونوعٌ مجهولٌ محايد', () => {
  assert.match(reminderLogKindClass('sent'), /emerald/);
  assert.match(reminderLogKindClass('manual'), /teal/);
  assert.match(reminderLogKindClass('dismissed'), /amber/);
  assert.match(reminderLogKindClass('undo'), /slate/);
  assert.match(reminderLogKindClass('anything_else'), /slate/);
});

test('الغدُ من تاريخ ISO بلا كائن Date — ويعبر الشهر والسنة', () => {
  assert.equal(nextDayIso('2026-11-05'), '2026-11-06');
  assert.equal(nextDayIso('2026-11-30'), '2026-12-01');
  assert.equal(nextDayIso('2026-12-31'), '2027-01-01');
  assert.equal(nextDayIso('2028-02-28'), '2028-02-29');
  // الفاسدُ لا يصير تاريخاً مخترعاً: أدنى تاريخٍ للتأجيل يبقى فارغاً فيُرفض الحفظ.
  assert.equal(nextDayIso(''), '');
  assert.equal(nextDayIso('غير تاريخ'), '');
});

test('الإرسالُ التلقائي مقفلٌ للعرض — والخادم يردّ 400 على فتحه', () => {
  assert.equal(isLockedOfficeSetting('reminder_auto_send'), true);
  assert.equal(isLockedOfficeSetting('reminder_merge_daily'), false);
  assert.equal(isLockedOfficeSetting('documents_reminder_max'), false);
});
test('نظامُ الرسالة المشترك: يُعاد حين تتفق بنودها، وnull حين تختلف أو تغيب', () => {
  assert.equal(commonTaxSystem([{ tax_system: 'PS' }, { tax_system: 'PS' }]), 'PS');
  assert.equal(commonTaxSystem([{ tax_system: ' PS ' }]), 'PS');
  // رسالةُ مستلِمٍ لزبونين بنظامين مختلفين: لا نظامَ واحدٌ لها.
  assert.equal(commonTaxSystem([{ tax_system: 'PS' }, { tax_system: 'IL' }]), null);
  // بندٌ غاب نظامُ زبونه (أو لم يصل بعد) يُسقط النظامَ كلَّه — لا تخمين.
  assert.equal(commonTaxSystem([{ tax_system: 'PS' }, { tax_system: null }]), null);
  assert.equal(commonTaxSystem([{ tax_system: 'PS' }, {}]), null);
  assert.equal(commonTaxSystem([{ tax_system: '' }]), null);
  assert.equal(commonTaxSystem([]), null);
});

test('تبويبُ سجلّ التذكيرات يُقرأ من العنوان كأخواته', () => {
  assert.equal(clientTabFromSearch('?client=7&tab=reminder-log'), 'reminder-log');
});

test('وقتُ الموعد يُقصّ من نصّه ISO — لا كائن Date ولا انزياحَ منطقةٍ زمنية', () => {
  // ما يقبله `input[type=datetime-local]` وحده: تاريخٌ ووقتٌ بلا ثوانٍ ولا منطقة.
  assert.equal(
    appointmentSlotValue('2026-02-01T10:30:00+02:00'),
    '2026-02-01T10:30',
  );
  assert.equal(appointmentSlotValue('2026-02-01 10:30:00'), '2026-02-01T10:30');
  // الفاسدُ يعيد فراغاً فلا يُملأ حقلُ الوقت بقيمةٍ مخترعة.
  assert.equal(appointmentSlotValue(''), '');
  assert.equal(appointmentSlotValue(null), '');
  assert.equal(appointmentSlotValue('غداً'), '');
});


test('المواعيدُ مجموعةً بأيامها، والمحجوزُ وحده ذو أفعال', () => {
  const rows = [
    { id: 1, day: '2026-02-01', status: 'scheduled' },
    { id: 2, day: '2026-02-01', status: 'cancelled' },
    { id: 3, day: '2026-02-02', status: 'scheduled' },
  ];
  const byDay = groupAppointmentsByDay(rows as never);
  assert.deepEqual(Object.keys(byDay).sort(), ['2026-02-01', '2026-02-02']);
  assert.equal(byDay['2026-02-01'].length, 2);

  assert.equal(isOpenAppointment({ status: 'scheduled' }), true);
  assert.equal(isOpenAppointment({ status: 'cancelled' }), false);
  assert.equal(isOpenAppointment({ status: 'done' }), false);

  // اللونُ عرضٌ لا نصّ: المحجوزُ والمنتهي والملغى ثلاثُ طبقاتٍ مختلفة.
  assert.notEqual(appointmentStatusClass('scheduled'), appointmentStatusClass('cancelled'));
  assert.notEqual(appointmentStatusClass('done'), appointmentStatusClass('cancelled'));
  assert.equal(officeAppointmentAnchorId(7), 'office-appointment-7');
});

test('تأكيدُ الموعد: النصُّ كما بناه الخادم، والرابطُ من نظام زبونه', () => {
  const result = {
    appointment: { tax_system: 'IL' },
    log: { id: 3 },
    body: 'بذكّرك بموعدك يوم 04/02/2026.',
    phone: '0599123456',
  };
  const view = appointmentConfirmationView(result as never);

  assert.equal(view.body, result.body);
  assert.ok(view.link?.startsWith('https://wa.me/'));
  assert.ok(view.link?.includes(encodeURIComponent(result.body)));

  // نظامُ السطر العائد يغلب الاحتياط، والغيابُ في الاثنين لا يخترع مفتاحَ دولة:
  // رقمٌ أرضيٌّ بلا نظامٍ لا يُبنى له رابط، فيبقى النصُّ بلا زرّ محادثة.
  assert.equal(
    appointmentConfirmationView({ ...result, appointment: { tax_system: null } } as never, 'IL')
      .link,
    view.link,
  );
  assert.equal(
    appointmentConfirmationView(
      { ...result, appointment: { tax_system: null }, phone: '022345678' } as never,
    ).link,
    null,
  );
});
