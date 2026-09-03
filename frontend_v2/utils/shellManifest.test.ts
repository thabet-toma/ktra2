import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildShellSections,
  filterShellGroups,
  resolveManifestView,
  type ShellGroup,
  type ShellManifest,
} from './shellManifest.ts';

// بيان مصغّر بمجموعتين — يكفي لإثبات الفرعين بلا اعتماد على core/shell_manifest.py.
const SAMPLE_SHELL: ShellManifest = {
  start_view: 'dashboard',
  first_action: { view: 'sales-invoices', label_term: 'doc.sales_invoice' },
  groups: [
    { id: 'home', label_term: 'nav.home', views: ['dashboard'] },
    { id: 'fees', label_term: 'nav.fees', views: ['sales-invoices', 'stock-movements'] },
    { id: 'reports-only-managers', label_term: 'nav.reports', views: ['accounting-trial-balance'] },
  ],
  unbuilt_views: [],
};

// القاعدة الملزِمة للتذكرة #83: بيانٌ يذكر شاشةً يرفضها القناع الحيّ
// (`TEMPLATE_HIDDEN_VIEWS` لـ`accounting_firm`) لا يُظهرها — `stock-movements`
// حالةٌ حقيقية من `core/shell_manifest.py` (مجموعة «التقارير») لا مصطنعة.
test('يُقصي شاشةً مذكورة في البيان يرفضها قناع القالب', () => {
  const groups: ShellGroup[] = [
    { id: 'reports', label_term: 'nav.reports', views: ['reports', 'stock-movements'] },
  ];
  const filtered = filterShellGroups(groups, 'accounting_firm');
  assert.deepEqual(filtered[0].views, ['reports']);
});

test('general بلا قناعٍ يخصّه — لا شيء يُقصى', () => {
  const groups: ShellGroup[] = [
    { id: 'inv', label_term: 'nav.reports', views: ['stock-movements'] },
  ];
  assert.deepEqual(filterShellGroups(groups, 'general')[0].views, ['stock-movements']);
});

test('مجموعةٌ يُقصى كل ما فيها تُحذف كاملةً — لا رأسٌ بلا روابط', () => {
  const groups: ShellGroup[] = [
    { id: 'ghost', label_term: 'nav.reports', views: ['stock-movements', 'items-management'] },
    { id: 'kept', label_term: 'nav.home', views: ['dashboard'] },
  ];
  const filtered = filterShellGroups(groups, 'accounting_firm');
  assert.deepEqual(filtered.map((g) => g.id), ['kept']);
});

test('الوحدة المرخّصة المطفأة تُقصي شاشتها أيضاً', () => {
  const groups: ShellGroup[] = [
    { id: 'after-sales', label_term: 'nav.reports', views: ['after-sales', 'dashboard'] },
  ];
  const filtered = filterShellGroups(groups, 'general', [], { after_sales: false });
  assert.deepEqual(filtered[0].views, ['dashboard']);
});

test('الشاشة غير المبنيّة تسقط إلى dashboard', () => {
  assert.equal(resolveManifestView('office-desk', 'accounting_firm', ['office-desk']), 'dashboard');
  assert.equal(resolveManifestView('document-coding', 'client_book', ['document-coding']), 'dashboard');
});

test('شاشةٌ مبنيّة وغير مقنَّعة تبقى كما هي', () => {
  assert.equal(resolveManifestView('sales-invoices', 'accounting_firm', ['office-desk', 'document-coding']), 'sales-invoices');
});

// القاعدة الملزِمة للمراجعة: البيان يُرسَم فرعاً ثانياً في `Sidebar.tsx` عبر
// `buildShellSections` — دالّةٌ صرفة نختبرها هنا بلا رسمٍ ولا سياق React.

test('قالبٌ ذو بيان: الأقسام الناتجة = مجموعات البيان مصفّاةً بالقناع والصلاحية، بالترتيب، بلا مجموعةٍ فارغة', () => {
  const can = (key: string) => key !== 'accounting.report.view'; // يحجب «reports-only-managers» بالكامل
  const sections = buildShellSections(
    SAMPLE_SHELL,
    'accounting_firm', // يقنّع stock-movements في مجموعة «fees»
    {},
    can,
    'manager',
    ['dashboard'],
    true,
  );
  // الترتيب كما في البيان، والمجموعة الثالثة (صلاحيتها الوحيدة محجوبة) غابت كاملةً.
  assert.deepEqual(
    sections.map((g) => g.id),
    ['home', 'fees'],
  );
  assert.deepEqual(sections[0].views, ['dashboard']);
  // stock-movements سقطت بالقناع، فبقيت sales-invoices وحدها.
  assert.deepEqual(sections[1].views, ['sales-invoices']);
});

test('قالبٌ ذو بيان: مفتاحٌ مقصورٌ على المدير يسقط لغير المدير', () => {
  const can = () => true;
  const sections = buildShellSections(SAMPLE_SHELL, 'general', {}, can, 'employee', ['dashboard'], false);
  const home = sections.find((g) => g.id === 'home');
  assert.equal(home, undefined); // «home» كانت تحمل «dashboard» وحدها فغابت المجموعة كلّها معه
});

test('general: لا بيان ⇒ [] فوراً بلا معالجة — الفرع الجديد لا يُستدعى', () => {
  assert.deepEqual(buildShellSections(null, 'general', {}, () => true, 'manager', [], true), []);
  assert.deepEqual(buildShellSections(undefined, 'general', {}, () => true, 'manager', [], true), []);
});
