import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { documentLineProductName, formatProductPrimaryName } from './productDisplayName.ts';

test('display_name القادم من الخادم يُقدَّم على كل شيء', () => {
  assert.equal(
    formatProductPrimaryName({ id: 1, display_name: '215/65/16 (دانتير ايكو جرين)' }),
    '215/65/16 (دانتير ايكو جرين)',
  );
});

test('بلا display_name: عربي وإنكليزي معاً يُدمجان بشرطة', () => {
  assert.equal(
    formatProductPrimaryName({ id: 2, name_ar: 'مضخة', name_en: 'Pump' }),
    'مضخة — Pump',
  );
});

test('بلا display_name: عربي وحده', () => {
  assert.equal(formatProductPrimaryName({ id: 3, name_ar: 'مضخة' }), 'مضخة');
});

test('بلا display_name ولا اسم عربي: إنكليزي', () => {
  assert.equal(formatProductPrimaryName({ id: 4, name_en: 'Pump' }), 'Pump');
});

test('بلا أي اسم: SKU', () => {
  assert.equal(formatProductPrimaryName({ id: 5, sku: 'SKU-9' }), 'SKU-9');
});

test('بلا اسم ولا SKU: رقم المنتج احتياطاً أخيراً', () => {
  assert.equal(formatProductPrimaryName({ id: 6 }), 'منتج #6');
});

test('حقول فارغة (سلاسل بيضاء) تُعامَل كغائبة', () => {
  assert.equal(
    formatProductPrimaryName({ id: 7, name_ar: '   ', name_en: '', sku: 'SKU-7' }),
    'SKU-7',
  );
});

// ── اسمُ الصنف على سطر المستند ──────────────────────────────────────────────
// بلاغ المالك: «أفتح فاتورة… قبل التحرير جايبلي المنتج بس مش محدد البراند،
// أحياناً آه وأحياناً لا». الـ«أحياناً» كانت **حالةَ الفاتورة**: المرحَّلة تعرض
// لقطتها المجمَّدة (`product_display_name` على الخادم = الاسم + البراند)، والمسودّة
// بلا لقطة فكان وجهُ المستند يسقط إلى `name_ar` الخامّ — والبراند ليس فيه.
// بينما خليّةُ المحرِّر نفسِه تعرضه. قاعدةٌ واحدة لكلّ من يسمّي السطر.

test('سطر المستند: اللقطة المجمَّدة تسبق الاسم الحيّ', () => {
  assert.equal(
    documentLineProductName('إطار 205/55/16 (ميشلان)', { id: 1, display_name: 'إطار 205/55/16 (بريجستون)' }),
    'إطار 205/55/16 (ميشلان)',
  );
});

test('سطر المستند: مسودّةٌ بلا لقطة تعرض البراند كما يعرضه المحرِّر', () => {
  assert.equal(
    documentLineProductName('', { id: 2, name_ar: 'إطار 205/55/16', display_name: 'إطار 205/55/16 (ميشلان)' }),
    'إطار 205/55/16 (ميشلان)',
  );
});

test('سطر المستند: لقطةٌ من مسافاتٍ بيضاء تُعامَل كغائبة', () => {
  assert.equal(documentLineProductName('   ', { id: 3, display_name: 'مضخة (غروندفوس)' }), 'مضخة (غروندفوس)');
});

test('سطر المستند: لا لقطة ولا صنفٌ محمَّل ⇒ فراغٌ يقرّر المستدعي بديلَه', () => {
  assert.equal(documentLineProductName(undefined, undefined), '');
});

/** مواضعُ تسمّي صنفَ سطرٍ في مستندات البيع (فاتورة · طلبيّة · عرض سعر · سند تسليم). السقوطُ إلى `name_ar || name_en || sku`
 *  فيها هو العطبُ نفسُه: يُسقط البراند. التعليقاتُ تُجرَّد — حارسٌ يسقط على تعليقٍ
 *  معطوب، وبدون التجريد «تُصلَح» المخالفةُ بنقلها إلى تعليق. */
const SALES_LINE_NAMING_SOURCES = [
  '../components/sales/SalesInvoiceEditor.tsx',
  '../components/sales/SalesInvoicePrintView.tsx',
  '../components/sales/SalesOrdersPage.tsx',
  '../components/sales/SalesQuotationsPage.tsx',
  '../components/sales/DeliveryNotesPage.tsx',
];

test('مستندات البيع لا تسمّي صنفاً بالاسم الخامّ الذي يُسقط البراند', () => {
  // أيُّ سقوطٍ يبدأ بـ`name_ar ||` — بصيغه كلِّها (`p.name_ar || p.name_en || p.sku`،
  // `pr?.name_ar || productId`…): كلُّها تُسمّي البراند باسم منتجه الأب.
  // المستثنى وحده ملءُ الحقل نفسِه (`name_ar: p.name_ar || p.name`) — ذاك حقلُ
  // الاسم العربيّ لا لافتة.
  const rawFallback = /(?<!\bname_ar:\s*[^\n,]*)\bname_ar\s*\|\|[^\n;,)]*/g;
  const offenders: string[] = [];
  for (const rel of SALES_LINE_NAMING_SOURCES) {
    const source = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/\/\/[^\n]*/g, ' ');
    for (const hit of source.match(rawFallback) || []) offenders.push(`${rel}: ${hit}`);
  }
  assert.deepEqual(offenders, [], 'استعمل formatProductPrimaryName / documentLineProductName');
});

test('مُطابِقا الطلبيّة وعرض السعر لا يُسقطان display_name', () => {
  // بغيابه يسمّي `formatProductPrimaryName` الصنفَ بلا براند وإن مرّ الاسمُ بها.
  for (const rel of ['../components/sales/SalesOrdersPage.tsx', '../components/sales/SalesQuotationsPage.tsx']) {
    const source = readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');
    assert.match(source, /display_name: p\.display_name \?\? null/, `${rel}: مُطابِقُ القائمة`);
    assert.match(source, /display_name: created\.display_name \?\? null/, `${rel}: مُطابِقُ الإنشاء السريع`);
  }
});
