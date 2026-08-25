/**
 * حارس قناع الأعمدة (T-SIMPL2): **كل مفتاحٍ مطويّ يجب أن يكون عموداً موجوداً**.
 *
 * `SIMPLE_HIDDEN_COLUMNS` قوائمُ سلاسل نصّية، و`visibleColumns` ترشّح بها. فلو
 * أُخطئ حرفٌ في مفتاح — أو أُعيدت تسمية عمودٍ في شاشته — **لا يشتكي شيء**: لا
 * `tsc` (النوع `string`) ولا `eslint` ولا اختبارُ e2e (الجدول يُرسم سليماً،
 * غايةُ ما يحدث أن العمود يبقى ظاهراً في الوضع السهل). أي أن الميزة تموت بصمت
 * وتبدو حيّةً — وهذا بالضبط ما حدث لقناع أعمدةٍ يُظنّ أنه يعمل.
 *
 * ولذلك الحارس **نصّي على المصدر**، كـ`skinIslands.test.ts`: يفتح ملفّ كل شاشة
 * ويتأكّد أن العمود مُعرَّف فيها فعلاً، وأن الشاشة **تستدعي القناع** أصلاً —
 * فسِجلٌّ لشاشةٍ لا تمرّ أعمدتُها منه سِجلٌّ ميت.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { SIMPLE_HIDDEN_COLUMNS } from './uiMode.ts';

/**
 * الشاشة ← ملفُّها. يُكتب هنا مرّةً، ونقصانُه يُخفق الاختبار — فبندٌ يُضاف إلى
 * السِّجل بلا ملفٍّ معروف لا يمرّ صامتاً.
 */
const SCREEN_SOURCES: Readonly<Record<string, string>> = {
  'sales-invoices': '../components/sales/SalesInvoicesPage.tsx',
  'stock-levels': '../components/inventory/StockLevelsPage.tsx',
  'items-management': '../components/items/ItemsManagement.tsx',
  'supplier-management': '../components/suppliers/SupplierManagement.tsx',
  'sales-customers': '../components/sales/SalesCustomersPage.tsx',
};

const sourceOf = (rel: string): string =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');

test('كل شاشةٍ في سِجلّ الأعمدة معروفٌ ملفُّها — لا بندَ يتيم', () => {
  for (const screen of Object.keys(SIMPLE_HIDDEN_COLUMNS)) {
    assert.ok(SCREEN_SOURCES[screen], `الشاشة ${screen} بلا ملفٍّ في SCREEN_SOURCES`);
  }
});

test('كل مفتاحٍ مطويّ هو عمودٌ مُعرَّفٌ فعلاً في شاشته', () => {
  const missing: string[] = [];

  for (const [screen, keys] of Object.entries(SIMPLE_HIDDEN_COLUMNS)) {
    const rel = SCREEN_SOURCES[screen];
    if (!rel) continue; // يمسكه الاختبار أعلاه
    const source = sourceOf(rel);
    for (const key of keys) {
      // تعريف العمود: `key: "x"` أو `key: 'x'`.
      // `String.raw` مقصود: في القالب العادي `\s` تُصبح `s` فتُطابق دائماً/أبداً
      // بلا أن يشتكي شيء — وهو الخطأ الذي وقع فيه هذا الحارس نفسه أول مرّة.
      const defined = new RegExp(String.raw`key:\s*["']` + key + String.raw`["']`).test(source);
      if (!defined) missing.push(`${screen} ← ${key}`);
    }
  }

  assert.deepEqual(missing, [], `مفاتيح مطويّة بلا عمودٍ يقابلها:\n${missing.join('\n')}`);
});

test('كل شاشةٍ مسجَّلة تُمرّر أعمدتها من القناع فعلاً — لا سِجلَّ ميتاً', () => {
  const unwired: string[] = [];

  for (const screen of Object.keys(SIMPLE_HIDDEN_COLUMNS)) {
    const rel = SCREEN_SOURCES[screen];
    if (!rel) continue;
    const source = sourceOf(rel);
    // اسمُ الشاشة يُمرَّر إلى `columns(...)` القادمة من `useSimpleUi`.
    const wired = source.includes('useSimpleUi') && source.includes(`"${screen}"`);
    if (!wired) unwired.push(screen);
  }

  assert.deepEqual(unwired, [], `شاشات مسجَّلة بلا استدعاء للقناع: ${unwired.join('، ')}`);
});
