import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  addBrandChip,
  attachBrandToExisting,
  brandTargetOf,
  brandedNamesPreview,
  createProductWithBrands,
  createWithBrandsMessage,
} from './brandActions.ts';

// ── الهدف ────────────────────────────────────────────────────────────────────

test('الهدف: الأبُ أوّلاً متى وُجد', () => {
  assert.deepEqual(brandTargetOf({ family_id: 12, id: 7287 }), { family_id: 12 });
});

test('الهدف: منتجٌ قديمٌ بلا أب يُعرَّف بصفّه — هذا ما يفتح الكتالوج القديم', () => {
  assert.deepEqual(brandTargetOf({ family_id: null, id: 7290 }), { product_id: 7290 });
  assert.deepEqual(brandTargetOf({ family_id: null, product_id: '7290' }), { product_id: 7290 });
});

test('الهدف: لا معرّفَ صالح ⇒ null لا هدفٌ ملفَّق', () => {
  assert.equal(brandTargetOf({}), null);
  assert.equal(brandTargetOf({ family_id: 0, id: '' }), null);
  assert.equal(brandTargetOf({ id: 'abc' }), null);
});

// ── الشارات والمعاينة ───────────────────────────────────────────────────────

test('الشارات: الفارغُ والمكرَّرُ بعد التطبيع يُتجاهَلان', () => {
  let chips = addBrandChip([], '  ميشلان ');
  chips = addBrandChip(chips, 'ميشلان');
  chips = addBrandChip(chips, '   ');
  chips = addBrandChip(chips, 'Michelin');
  chips = addBrandChip(chips, 'michelin  ');
  assert.deepEqual(chips, ['ميشلان', 'Michelin']);
});

test('المعاينة: «الاسم (البراند)» لكلّ براند، والاسمُ وحدَه بلا براند', () => {
  assert.deepEqual(brandedNamesPreview('إطار 205/55/16', ['ميشلان', 'بريجستون']), [
    'إطار 205/55/16 (ميشلان)',
    'إطار 205/55/16 (بريجستون)',
  ]);
  assert.deepEqual(brandedNamesPreview('إطار 205/55/16', []), ['إطار 205/55/16']);
  assert.deepEqual(brandedNamesPreview('   ', ['ميشلان']), []);
});

test('المعاينة: براندٌ مذكورٌ في الاسم لا يُكرَّر — كصيغة الخادم', () => {
  assert.deepEqual(brandedNamesPreview('شاشة LG 55', ['LG']), ['شاشة LG 55']);
});

// ── الإنشاء بعدّة براندات ───────────────────────────────────────────────────

const recorder = () => {
  const calls: Array<{ kind: string; body: Record<string, unknown> }> = [];
  return {
    calls,
    createProduct: async (payload: Record<string, unknown>): Promise<Record<string, unknown>> => {
      calls.push({ kind: 'create', body: payload });
      return { id: 100, family_id: 9, sku: 'P-100' };
    },
    addBrand: async (body: Record<string, unknown>) => {
      calls.push({ kind: 'brand', body });
      if (body.brand === 'مرفوض') throw new Error('حدُّ الخطة');
      return { id: 100 + calls.length, created: true };
    },
  };
};

test('الإنشاء: البراندُ الأوّل في حمولة الإنشاء، والباقي بالتتابع تحت الأب نفسِه', async () => {
  const deps = recorder();
  const { steps } = await createProductWithBrands(deps as never, { name_ar: 'إطار' }, ['ميشلان', 'بريجستون', 'كونتيننتال']);
  assert.deepEqual(deps.calls.map((c) => c.kind), ['create', 'brand', 'brand']);
  assert.equal(deps.calls[0].body.brand, 'ميشلان');
  assert.equal(deps.calls[0].body.name_ar, 'إطار');
  assert.deepEqual(deps.calls[1].body, { family_id: 9, brand: 'بريجستون' });
  assert.deepEqual(deps.calls[2].body, { family_id: 9, brand: 'كونتيننتال' });
  assert.equal(steps.length, 2);
  assert.ok(steps.every((s) => s.ok));
});

test('الإنشاء: بلا براندات ⇒ براندٌ فارغ ولا نداءَ إضافة', async () => {
  const deps = recorder();
  const { steps } = await createProductWithBrands(deps as never, { name_ar: 'مسمار' }, []);
  assert.deepEqual(deps.calls.map((c) => c.kind), ['create']);
  assert.equal(deps.calls[0].body.brand, '');
  assert.deepEqual(steps, []);
});

test('الإنشاء: فشلُ الإنشاء يُرمى ولا يُضاف براندٌ واحد', async () => {
  const deps = recorder();
  deps.createProduct = async () => { throw new Error('رقم المنتج مستخدم'); };
  await assert.rejects(
    createProductWithBrands(deps as never, { name_ar: 'إطار' }, ['ميشلان', 'بريجستون']),
    /رقم المنتج مستخدم/,
  );
  assert.equal(deps.calls.filter((c) => c.kind === 'brand').length, 0);
});

test('الإنشاء: فشلُ براندٍ لا يوقف ما بعده ويُسجَّل باسمه وسببه', async () => {
  const deps = recorder();
  const { steps } = await createProductWithBrands(deps as never, { name_ar: 'إطار' }, ['ميشلان', 'مرفوض', 'بريجستون']);
  assert.equal(deps.calls.filter((c) => c.kind === 'brand').length, 2);
  assert.deepEqual(steps[0], { brand: 'مرفوض', ok: false, error: 'حدُّ الخطة' });
  assert.equal(steps[1].ok, true);
});

test('الإنشاء: ردٌّ بلا أب (خادمٌ أقدم) ⇒ الإضافةُ بصفّ المنتج لا بأبٍ ملفَّق', async () => {
  const deps = recorder();
  deps.createProduct = async (payload) => {
    deps.calls.push({ kind: 'create', body: payload });
    return { id: 55, family_id: null };
  };
  await createProductWithBrands(deps as never, { name_ar: 'إطار' }, ['أ', 'ب']);
  assert.deepEqual(deps.calls[1].body, { product_id: 55, brand: 'ب' });
});

test('الرسالة: تقول ما فشل وسببه، ولا «تمّ» على ما لم يتمّ', () => {
  const fmt = (n: number) => String(n);
  assert.deepEqual(createWithBrandsMessage('P-1', 1, [], fmt), { ok: true, text: 'تم إنشاء المنتج P-1.' });
  assert.equal(
    createWithBrandsMessage('P-1', 3, [
      { brand: 'ب', ok: true, productId: 2, created: true },
      { brand: 'ج', ok: true, productId: 3, created: true },
    ], fmt).text,
    'تم إنشاء المنتج P-1 بـ3 براندات.',
  );
  const partial = createWithBrandsMessage('P-1', 3, [
    { brand: 'ب', ok: false, error: 'حدُّ الخطة' },
    { brand: 'ج', ok: true, productId: 3, created: true },
  ], fmt);
  assert.equal(partial.ok, false);
  assert.match(partial.text, /2 من 3/);
  assert.match(partial.text, /«ب»: حدُّ الخطة/);
});

// ── الإنشاء السريع: الاسمُ موجود ⇒ براندٌ تحته ────────────────────────────────

test('الإنشاء السريع: اقتراحُ أبٍ ⇒ family_id، ثمّ الصفُّ الكامل للمستدعي', async () => {
  const calls: unknown[] = [];
  const full = await attachBrandToExisting(
    {
      addBrand: async (body) => { calls.push(body); return { id: 7291, created: true }; },
      getProduct: async (id) => { calls.push(['get', id]); return { id, sale_price: '300', quantity_on_hand: '0' }; },
    },
    { id: 1, family_id: 1, product_id: null },
    ' كونتيننتال ',
  );
  assert.deepEqual(calls, [{ family_id: 1, brand: 'كونتيننتال' }, ['get', 7291]]);
  assert.equal(full.sale_price, '300');
});

test('الإنشاء السريع: اقتراحُ منتجٍ قديم ⇒ product_id — لا يُقرأ id الأب الفارغ صفّاً', async () => {
  const calls: unknown[] = [];
  await attachBrandToExisting(
    {
      addBrand: async (body) => { calls.push(body); return { id: 7290, created: false }; },
      getProduct: async (id) => ({ id }),
    },
    { id: null, family_id: null, product_id: 7290 },
    'فارتا',
  );
  assert.deepEqual(calls[0], { product_id: 7290, brand: 'فارتا' });
});

test('الإنشاء السريع: براندٌ فارغ يُرفض قبل أيّ نداء', async () => {
  let called = false;
  await assert.rejects(
    attachBrandToExisting(
      { addBrand: async () => { called = true; return { id: 1 }; }, getProduct: async () => ({}) },
      { family_id: 1 },
      '   ',
    ),
    /اسم البراند/,
  );
  assert.equal(called, false);
});
