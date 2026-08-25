/**
 * حارس «جزر الجلد»: لا مكوّن يفرض جلداً على نفسه.
 *
 * محدِّد التوكنات الكلاسيكية في `styles/index.css` مكتوب `[data-skin="aseel"]`
 * **بلا `:root`** — فوسمٌ محليّ على أي عنصر يُطابقه فعلاً، وتلبس شجرتُه اللوحة
 * الكلاسيكية داخل الجلد الحديث. وقع هذا مرّتين (نافذتا `PartnerProfilePage`
 * و`PaymentVoucherParts`): حدٌّ زيتوني `#9e9c7e` وسطحٌ أبيض `#ffffff` **بلا
 * مقابلٍ داكن** — لأن `.dark[data-skin="aseel"]` يلزمه `.dark` على العنصر نفسه
 * وهو على `<html>` ⇒ نافذتان بيضاوان في الوضع الداكن.
 *
 * القاعدة: الجلد يُضبط في مكان واحد — `styles/skin.ts` على `<html>`. لا يمسك
 * `tsc` ولا `eslint` مخالفةً كهذه (خاصيّةُ DOM سليمة نحوياً)، ولا يمسكها اختبار
 * e2e إلا إن صادف أن يفتح الشاشة المصابة — فالحارس **نصّي على المصدر**.
 *
 * الاستثناء الوحيد: `kit/KitStory.tsx` — صفحة معاينة الجلدين جنباً إلى جنب
 * (`ui-kit` في القائمة)، وفرضُ الجلد فيها هو **وظيفتها** لا عيبها.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const COMPONENTS = fileURLToPath(new URL('../components', import.meta.url));

/** يُسمح لها بفرض الجلد لأن عرضَ الجلود هو غرضها. */
const ALLOWED = new Set(['kit/KitStory.tsx']);

const walk = (dir: string): string[] =>
  readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full);
    return /\.(tsx|ts)$/.test(entry) ? [full] : [];
  });

test('لا مكوّن يفرض جلداً على نفسه بـdata-skin محليّ', () => {
  const offenders: string[] = [];

  for (const file of walk(COMPONENTS)) {
    const rel = relative(COMPONENTS, file).split('\\').join('/');
    if (ALLOWED.has(rel)) continue;
    const source = readFileSync(file, 'utf8');
    source.split('\n').forEach((line, i) => {
      /* التعليقات تشرح الفخّ ولا تقع فيه. */
      const code = line.replace(/^\s*(\/\/|\*|\/\*).*$/, '');
      if (/data-skin\s*=/.test(code)) offenders.push(`${rel}:${i + 1}`);
    });
  }

  assert.deepEqual(
    offenders,
    [],
    `جلدٌ مفروض محلياً — الشجرة ستلبس اللوحة الكلاسيكية داخل الجلد الحديث ` +
    `وبلا وضع داكن. اضبط الجلد من styles/skin.ts وحدها:\n${offenders.join('\n')}`,
  );
});
