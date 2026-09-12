import assert from 'node:assert/strict';
import test from 'node:test';

import { BAR_WIDTH_STEPS, barWidthClass } from './barWidth.ts';

test('barWidthClass: كلّ خطوةٍ صنفٌ حرفيٌّ يراه ماسحُ Tailwind', () => {
  // صنفٌ مبنيٌّ وقتَ التشغيل لا يولّد قاعدةً، فالشريطُ يبقى صفراً بلا خطأ.
  assert.equal(BAR_WIDTH_STEPS.length, 21);
  for (const step of BAR_WIDTH_STEPS) {
    assert.ok(/^w-(0|full|\[\d{1,3}%\])$/.test(step), `خطوةٌ ليست صنفاً حرفيّاً: ${step}`);
  }
});

test('barWidthClass: الطرفان والقصّ خارجهما', () => {
  assert.equal(barWidthClass(0), 'w-0');
  assert.equal(barWidthClass(100), 'w-full');
  assert.equal(barWidthClass(-40), 'w-0', 'نسبةٌ سالبةٌ لا تخرج من السُلَّم');
  assert.equal(barWidthClass(160), 'w-full', 'الفائضُ يُقصّ في الشريط لا يُسقط الفهرسة');
});

test('barWidthClass: التقريبُ إلى أقرب خطوةِ ٥٪', () => {
  assert.equal(barWidthClass(47), 'w-[45%]');
  assert.equal(barWidthClass(48), 'w-[50%]');
  assert.equal(barWidthClass(90), 'w-[90%]');
});

test('barWidthClass: `NaN` صفرٌ لا `undefined` يُطبع في الصنف', () => {
  assert.equal(barWidthClass(Number.NaN), 'w-0');
  assert.equal(barWidthClass(Number.POSITIVE_INFINITY), 'w-0');
});
