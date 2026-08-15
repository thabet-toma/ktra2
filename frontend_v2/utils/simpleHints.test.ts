import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SIMPLE_HINTS, simpleHintFor, type SimpleHint } from '../constants/simpleHints.ts';
import { SIMPLE_VIEWS } from './uiMode.ts';

/**
 * THA-110 T5 — حراسة ملف النصوص نفسه. المكوّن يُفحَص في المتصفح
 * (`e2e/simple-ui-mode.spec.ts`)، وما يُفحَص هنا هو ما يخصّ الملف وحده:
 * أن كل بند قائمةٍ له شرحه، وأن المفاتيح لا تفترق عن الشاشات، وأن الغائب
 * يُعيد `null` بدل أن يكسر شاشة. تكتب T6 نصوصها فوق هذه الحراسة نفسها.
 */

test('لكل شاشةٍ في الوضع السهل مفتاحُ شرحٍ واحد، بلا زيادة ولا نقصان', () => {
  const navKeys = Object.keys(SIMPLE_HINTS).filter((k) => k.startsWith('nav.')).sort();
  assert.deepEqual(navKeys, SIMPLE_VIEWS.map((v) => `nav.${v}`).sort());
});

test('قائمة المفاتيح مجمَّدة — سبعة عشر مفتاحاً تكتب T6 نصوصها عليها', () => {
  assert.deepEqual(Object.keys(SIMPLE_HINTS).sort(), [
    'invoice.barcode',
    'invoice.currency',
    'invoice.customer',
    'invoice.date',
    'invoice.due-date',
    'invoice.lines',
    'invoice.notes',
    'invoice.paid',
    'invoice.total',
    'nav.dashboard',
    'nav.items-management',
    'nav.purchase-invoices',
    'nav.sales-customers',
    'nav.sales-invoices',
    'nav.settings',
    'nav.stock-levels',
    'nav.supplier-management',
  ]);
});

test('كل مفتاح له عنوان وسطران غير فارغين — لا ثالث لهما', () => {
  for (const [key, hint] of Object.entries(SIMPLE_HINTS)) {
    assert.ok(hint.title.trim().length > 0, `${key}: عنوان فارغ`);
    assert.equal(hint.lines.length, 2, `${key}: عدد الأسطر ليس اثنين`);
    for (const line of hint.lines) {
      assert.ok(line.trim().length > 0, `${key}: سطر فارغ`);
    }
  }
});

test('مفتاح غير معروف يُعيد null — لا أيقونة ولا انكسار', () => {
  assert.equal(simpleHintFor('nav.does-not-exist'), null);
  assert.equal(simpleHintFor(''), null);
  // `toString` موجودٌ على كل كائن: البحث لا يتسرّب إلى سلسلة النماذج.
  assert.equal(simpleHintFor('toString'), null);
});

test('نصٌّ فارغ كالمفقود تماماً — أيقونةٌ تفتح فراغاً أسوأ من لا أيقونة', () => {
  const bag = SIMPLE_HINTS as Record<string, SimpleHint | undefined>;
  const original = bag['nav.settings'];
  try {
    bag['nav.settings'] = { title: 'الإعدادات', lines: ['نصّ', '   '] };
    assert.equal(simpleHintFor('nav.settings'), null);
    bag['nav.settings'] = { title: '  ', lines: ['نصّ', 'نصّ'] };
    assert.equal(simpleHintFor('nav.settings'), null);
  } finally {
    bag['nav.settings'] = original;
  }
  assert.ok(simpleHintFor('nav.settings'));
});
