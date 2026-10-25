import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  arabicCount,
  buildStocktakeCreateBody,
  buildStocktakeLinesPayload,
  canCreateFromScope,
  countStocktakeProgress,
  filterStocktakeLines,
  groupStocktakeLines,
  isApplicableStocktakeDraft,
  isLocallyEdited,
  newSheetLineFromProduct,
  normalizeQuantity,
  partialCategoryIds,
  productLabel,
  pruneInactiveScopeProducts,
  quantityEquals,
  reapplyLocalEdits,
  rebaseDraftRestore,
  rebaseHeader,
  reconcileScopeProducts,
  setCategoryProducts,
  sheetLinesFromStocktake,
  stocktakeStampText,
  stocktakeVariance,
  summarizeScopeSelection,
  toggleScopeProduct,
  validateCountedQuantity,
  type ScopePickState,
  type ScopeProductPick,
  type StocktakeDraftIdentity,
  type StocktakeHeader,
  type StocktakeSheetLine,
} from './stocktake.ts';
import type { StocktakeLine, StocktakeScopeCounts } from '../types/inventory.ts';

const line = (overrides: Partial<StocktakeSheetLine> = {}): StocktakeSheetLine => ({
  product: 1,
  product_name: 'منتج أ',
  product_sku: 'SKU-1',
  product_category: 10,
  product_quantity_on_hand: '10',
  product_is_active: true,
  counted_quantity: '',
  counted_by_name: '',
  counted_at: null,
  system_quantity: null,
  variance: null,
  baseline: '',
  ...overrides,
});

const COUNTS: StocktakeScopeCounts = {
  categories: { '10': 3, '11': 4 },
  uncategorized: 2,
  all: 9,
};

const TREE = [
  { id: 10, name: 'قطع', parent: null },
  { id: 12, name: 'فرعية', parent: 10 },
  { id: 11, name: 'إطارات', parent: null },
];

test('تطبيع الكمية: 5.0000 يساوي 5، والفراغ يساوي null ومختلف عن 0', () => {
  assert.equal(quantityEquals('5.0000', '5'), true);
  assert.equal(quantityEquals(' 5 ', '5.0000'), true);
  assert.equal(quantityEquals('', null), true);
  assert.equal(quantityEquals('', '0'), false);
  assert.equal(quantityEquals('2.5', '2.5000'), true);
});

test('تطبيع الكمية للنصّ الرقميّ الخام: 4.0000 ⇒ 4 و2.5000 ⇒ 2.5 والغياب فارغ', () => {
  assert.equal(normalizeQuantity('4.0000'), '4');
  assert.equal(normalizeQuantity('2.5000'), '2.5');
  assert.equal(normalizeQuantity('0.0000'), '0');
  assert.equal(normalizeQuantity(null), '');
  assert.equal(normalizeQuantity(undefined), '');
});

test('التطبيع لا يخسر رقماً ولا يجمّع ولا يعرّب الأرقام', () => {
  // مُنسّق العرض يقصّ عند 4 منازل؛ خانة الإدخال لا تخسر رقماً ولا تجمّع.
  assert.equal(normalizeQuantity('0.00005'), '0.00005');
  assert.equal(normalizeQuantity('1000000.0000'), '1000000');
});

test('تحقّق الكمية المعدودة: الفراغ صالح، والسالب وغير الرقمي وما فوق 4 منازل مرفوض', () => {
  for (const valid of ['', '   ', '0', '7', '2.5', '2.5000', '.5']) {
    assert.equal(validateCountedQuantity(valid), true, `ينبغي أن تُقبل «${valid}»`);
  }
  for (const invalid of ['-3', 'abc', '1.23456', '1e3', '4,5', '-0.0001']) {
    assert.equal(validateCountedQuantity(invalid), false, `ينبغي أن تُرفض «${invalid}»`);
  }
});

test('التقدّم: الصفر كمية معدودة، والفراغ غير معدود', () => {
  const lines = [
    line({ counted_quantity: '0' }),
    line({ counted_quantity: '' }),
    line({ counted_quantity: '7.0000' }),
  ];
  assert.deepEqual(countStocktakeProgress(lines), {
    total: 3, counted: 2, uncounted: 1, ratio: 2 / 3,
  });
  assert.deepEqual(countStocktakeProgress([]), {
    total: 0, counted: 0, uncounted: 0, ratio: 0,
  });
});

test('الفلترة: بحثٌ في الاسم والرمز + «غير المعدود فقط» معاً', () => {
  const lines = [
    line({ product: 1, product_name: 'إطار ميشلان', product_sku: 'TY-1' }),
    line({ product: 2, product_name: 'بطارية فارتا', product_sku: 'BAT-9', counted_quantity: '4' }),
    line({ product: 3, product_name: 'زيت محرك', product_sku: 'OIL-3' }),
  ];
  assert.deepEqual(
    filterStocktakeLines(lines, { query: 'bat' }).map((l) => l.product),
    [2],
  );
  assert.deepEqual(
    filterStocktakeLines(lines, { query: 'بطارية' }).map((l) => l.product),
    [2],
  );
  assert.deepEqual(
    filterStocktakeLines(lines, { mode: 'uncounted' }).map((l) => l.product),
    [1, 3],
  );
  assert.deepEqual(
    filterStocktakeLines(lines, { mode: 'counted' }).map((l) => l.product),
    [2],
  );
  assert.deepEqual(
    filterStocktakeLines(lines, { query: 'TY', mode: 'uncounted' }).map((l) => l.product),
    [1],
  );
});

test('فلتر الفروقات: المسودّة تحسب حياً والمُرحَّل يقرأ اللقطة', () => {
  const lines = [
    line({ product: 1, counted_quantity: '', product_quantity_on_hand: '10' }),
    line({ product: 2, counted_quantity: '10', product_quantity_on_hand: '10' }),
    line({ product: 3, counted_quantity: '12', product_quantity_on_hand: '10' }),
    line({ product: 4, counted_quantity: '7', product_quantity_on_hand: '10' }),
  ];
  assert.equal(stocktakeVariance(lines[0]), null);
  assert.equal(stocktakeVariance(lines[2]), 2);
  assert.equal(stocktakeVariance(lines[3]), -3);
  assert.deepEqual(
    filterStocktakeLines(lines, { mode: 'variance' }).map((l) => l.product),
    [3, 4],
  );
  // المُرحَّل يقرأ `variance` المخزَّن لا الفرق الحي.
  const posted = [
    line({ product: 5, counted_quantity: '12', product_quantity_on_hand: '10', variance: '0.0000' }),
    line({ product: 6, counted_quantity: '10', product_quantity_on_hand: '10', variance: '1.5000' }),
  ];
  assert.deepEqual(
    filterStocktakeLines(posted, { mode: 'variance', posted: true }).map((l) => l.product),
    [6],
  );
});

test('التجميع: مسار التصنيف كاملاً، مرتّباً، و«بدون تصنيف» أخيراً', () => {
  const lines = [
    line({ product: 1, product_category: 12 }),
    line({ product: 2, product_category: null }),
    line({ product: 3, product_category: 11 }),
  ];
  const groups = groupStocktakeLines(lines, TREE);
  assert.deepEqual(groups.map((g) => g.label), ['إطارات', 'قطع ‹ فرعية', 'بدون تصنيف']);
  assert.deepEqual(groups.map((g) => g.categoryId), [11, 12, null]);
  assert.deepEqual(groups[0].lines.map((l) => l.product), [3]);
  assert.equal(groups[2].key, 'uncategorized');
  // التصنيفات بلا بنود لا تُرسم.
  assert.equal(groupStocktakeLines([line()], TREE).length, 1);
});

test('الحفظ: فرقُ ما تغيّر وحده، والسطر الممسوح يُرسل null', () => {
  const untouched = line({ product: 1, baseline: '5.0000', counted_quantity: '5' });
  const changed = line({ product: 2, baseline: '3', counted_quantity: '8' });
  const cleared = line({ product: 3, baseline: '4', counted_quantity: '' });
  const added = newSheetLineFromProduct({ id: 4, sku: 'N-4', name_ar: 'جديد', quantity_on_hand: '0' });
  const payload = buildStocktakeLinesPayload([untouched, changed, cleared, added]);
  assert.deepEqual(payload, {
    lines: [
      { product: 2, counted_quantity: '8' },
      { product: 3, counted_quantity: null },
      { product: 4, counted_quantity: null },
    ],
  });
  // لا تغيير ⇒ لا `lines` إطلاقاً.
  assert.deepEqual(buildStocktakeLinesPayload([untouched]), {});
});

test('الحفظ بعد حذف سطر: كلُّ الحالي مع replace_lines=true', () => {
  const payload = buildStocktakeLinesPayload(
    [
      line({ product: 1, baseline: '5', counted_quantity: '5' }),
      line({ product: 2, baseline: '3', counted_quantity: '6' }),
    ],
    1,
  );
  assert.deepEqual(payload, {
    replace_lines: true,
    lines: [
      { product: 1, counted_quantity: '5' },
      { product: 2, counted_quantity: '6' },
    ],
  });
});

test('إعادة التطبيق بعد 412: تعديلات المستخدم فوق النسخة الجديدة، والمضاف يبقى', () => {
  const fresh = sheetLinesFromStocktake([
    {
      id: 1, product: 1, product_name: 'أ', counted_quantity: '20',
      counted_by_name: 'أحمد', counted_at: '2026-10-22T08:00:00Z',
      product_sku: 'A', product_category: 10, product_quantity_on_hand: '20',
      product_is_active: true, system_quantity: null, variance: null,
    },
    {
      id: 2, product: 2, product_name: 'ب', counted_quantity: '5',
      counted_by_name: '', counted_at: null,
      product_sku: 'B', product_category: 10, product_quantity_on_hand: '5',
      product_is_active: true, system_quantity: null, variance: null,
    },
  ] as StocktakeLine[]);
  const local = [
    line({ product: 1, baseline: '10', counted_quantity: '12', counted_by_name: 'مدير' }),
    line({ product: 2, baseline: '5', counted_quantity: '5' }), // لم يمسّه محلياً
    newSheetLineFromProduct({ id: 3, sku: 'C', name_ar: 'ج', quantity_on_hand: '1' }),
  ];
  const { lines, reapplied } = reapplyLocalEdits(fresh, local);
  assert.equal(reapplied, 2);
  assert.deepEqual(lines.map((l) => [l.product, l.counted_quantity]), [
    [1, '12'], [2, '5'], [3, ''],
  ]);
  // القيمة المرجعية للسطر المعدَّل صارت الجديدة (20) — الحفظ القادم يرسل 12 وحده.
  assert.equal(lines[0].baseline, '20');
  // والخاتم المعروض لا يبقى خاتمَ قيمةٍ استُبدلت: الواجهة تقول «تعديلك — غير محفوظ».
  assert.equal(lines[0].counted_by_name, '');
  assert.equal(lines[0].counted_at, null);
  assert.equal(lines[2].baseline, undefined);
  assert.deepEqual(buildStocktakeLinesPayload(lines), {
    lines: [
      { product: 1, counted_quantity: '12' },
      { product: 3, counted_quantity: null },
    ],
  });
});

test('إعادة التطبيق: القيمة المحلية المساوية لقيمة الخادم تحفظ خاتم الخادم ولا تُحتسب', () => {
  const fresh = sheetLinesFromStocktake([
    {
      id: 1, product: 1, product_name: 'أ', counted_quantity: '20.0000',
      counted_by_name: 'أحمد', counted_at: '2026-10-22T08:00:00Z',
      product_sku: 'A', product_category: 10, product_quantity_on_hand: '20',
      product_is_active: true, system_quantity: null, variance: null,
    },
  ] as StocktakeLine[]);
  // كتب المستخدم 20 قبل وصول عدّ العامل 20 نفسه: القيمتان واحدة — لا تعديل.
  const local = [line({ product: 1, baseline: '10', counted_quantity: '20.0000' })];
  const { lines, reapplied } = reapplyLocalEdits(fresh, local);
  assert.equal(reapplied, 0);
  assert.equal(lines[0].counted_quantity, '20');
  assert.equal(lines[0].counted_by_name, 'أحمد');
  assert.equal(lines[0].counted_at, '2026-10-22T08:00:00Z');
});

test('«تعديلك غير محفوظ»: القيمة تختلف عن مرجعيتها أو سطرٌ أُضيف محلياً', () => {
  assert.equal(isLocallyEdited(line({ baseline: '5', counted_quantity: '5.0000' })), false);
  assert.equal(isLocallyEdited(line({ baseline: '5', counted_quantity: '6' })), true);
  assert.equal(isLocallyEdited(line({ baseline: '5', counted_quantity: '' })), true);
  assert.equal(isLocallyEdited(line({ baseline: undefined, counted_quantity: '4' })), true);
  assert.equal(isLocallyEdited(line({ baseline: undefined, counted_quantity: '' })), false);
});

test('سطرٌ أُضيف محلياً ولم يُعدّ لا يمحو عدّاً وصل من الخادم', () => {
  const fresh = sheetLinesFromStocktake([
    {
      id: 1, product: 4, product_name: 'د', counted_quantity: '6',
      counted_by_name: 'عامل', counted_at: '2026-10-22T09:00:00Z',
      product_sku: 'D', product_category: 10, product_quantity_on_hand: '6',
      product_is_active: true, system_quantity: null, variance: null,
    },
  ] as StocktakeLine[]);
  const local = [newSheetLineFromProduct({ id: 4, sku: 'D', name_ar: 'د' })];
  const { lines, reapplied } = reapplyLocalEdits(fresh, local);
  assert.equal(reapplied, 0);
  assert.equal(lines[0].counted_quantity, '6');
  assert.equal(lines[0].baseline, '6');
});

test('استعادة مسودّة قديمة تُعاد على بنود الخادم الحالية لا على مرجعيات المسودّة', () => {
  const server = sheetLinesFromStocktake([
    {
      id: 1, product: 1, product_name: 'أ', counted_quantity: '10',
      counted_by_name: 'أحمد', counted_at: '2026-10-22T08:00:00Z',
      product_sku: 'A', product_category: 10, product_quantity_on_hand: '10',
      product_is_active: true, system_quantity: null, variance: null,
    },
    {
      id: 2, product: 2, product_name: 'ب', counted_quantity: '9',
      counted_by_name: 'عاملٌ آخر', counted_at: '2026-10-22T09:00:00Z',
      product_sku: 'B', product_category: 10, product_quantity_on_hand: '9',
      product_is_active: true, system_quantity: null, variance: null,
    },
    {
      id: 3, product: 3, product_name: 'ج', counted_quantity: '4',
      counted_by_name: 'أحمد', counted_at: '2026-10-22T08:00:00Z',
      product_sku: 'C', product_category: 10, product_quantity_on_hand: '4',
      product_is_active: true, system_quantity: null, variance: null,
    },
  ] as StocktakeLine[]);
  // المسودّة: عدّلت أ (10 ⇒ 12) وحذفت ج، ومرجعياتها من وقت حفظها (ب كانت 5).
  const draft = [
    line({ product: 1, baseline: '10', counted_quantity: '12', counted_by_name: 'مدير' }),
    line({ product: 2, baseline: '5', counted_quantity: '5' }),
  ];

  const { lines, reapplied, removedIds } = rebaseDraftRestore(server, draft, [3, 99]);

  assert.equal(reapplied, 2); // تعديل أ + حذف ج
  assert.deepEqual(removedIds, [3]); // 99 لم يعد على الخادم فلا يُحذف شيء
  assert.deepEqual(lines.map((row) => [row.product, row.counted_quantity, row.baseline]), [
    [1, '12', '10'],
    [2, '9', '9'], // عدّ العامل الجديد فوق المسودّة القديمة
  ]);
  // الحفظ التالي (بحذفٍ ⇒ replace_lines) يحمل قيمة الخادم للبند ب لا قيمة المسودّة القديمة.
  assert.deepEqual(buildStocktakeLinesPayload(lines, removedIds.length), {
    replace_lines: true,
    lines: [
      { product: 1, counted_quantity: '12' },
      { product: 2, counted_quantity: '9' },
    ],
  });
});

test('هويّة المسودّة: تُطبَّق فقط على الجرد نفسه وبالإصدار 3', () => {
  assert.equal(isApplicableStocktakeDraft({ v: 3, docId: 900 }, 900), true);
  assert.equal(isApplicableStocktakeDraft({ v: 3, docId: 900 }, 950), false);
  // الإصدار الثاني (سابق رفع الإصدار) لم يُنشر يوماً، لكنه لا يُطبَّق الآن.
  assert.equal(isApplicableStocktakeDraft({ v: 2, docId: 900 }, 900), false);
  assert.equal(isApplicableStocktakeDraft({ v: 1, docId: 900 }, 900), false);
  // مسودّة الصفحة القديمة: بلا إصدار ولا رقم جرد.
  assert.equal(isApplicableStocktakeDraft(
    { date: '2026-10-20', lines: [] } as unknown as StocktakeDraftIdentity, 900,
  ), false);
  assert.equal(isApplicableStocktakeDraft({ v: 3, docId: 900 }, null), false);
  assert.equal(isApplicableStocktakeDraft(null, 900), false);
});

test('إعادة تأسيس الرأس: الحقول غير المعدَّلة تأخذ قيم الخادم الجديدة', () => {
  const server: StocktakeHeader = {
    date: '2026-10-23', warehouse: 2, notes: 'ملاحظات محدَّثة على الخادم',
  };
  const baseline: StocktakeHeader = {
    date: '2026-10-20', warehouse: '', notes: 'ملاحظات قديمة',
  };
  assert.deepEqual(rebaseHeader(server, baseline, baseline), {
    header: server,
    kept: 0,
  });
});

test('إعادة تأسيس الرأس: كل حقلٍ معدَّلٍ يبقى، والثلاثة مستقلّة', () => {
  const server: StocktakeHeader = {
    date: '2026-10-23', warehouse: 2, notes: 'ملاحظات الخادم',
  };
  const baseline: StocktakeHeader = {
    date: '2026-10-20', warehouse: '', notes: 'ملاحظات سابقة',
  };

  // التاريخ وحده معدَّل.
  assert.deepEqual(rebaseHeader(
    server,
    { ...baseline, date: '2026-10-22' },
    baseline,
  ), {
    header: { date: '2026-10-22', warehouse: 2, notes: 'ملاحظات الخادم' },
    kept: 1,
  });

  // الملاحظات وحدها معدَّلة.
  assert.deepEqual(rebaseHeader(
    server,
    { ...baseline, notes: 'ملاحظة المستخدم' },
    baseline,
  ), {
    header: { date: '2026-10-23', warehouse: 2, notes: 'ملاحظة المستخدم' },
    kept: 1,
  });

  // المستودع وحده معدَّل: من «كل المخزون» (مرجعية `null` من حمولة مسودّة) إلى 5.
  assert.deepEqual(rebaseHeader(
    server,
    { ...baseline, warehouse: 5 },
    { ...baseline, warehouse: null },
  ), {
    header: { date: '2026-10-23', warehouse: 5, notes: 'ملاحظات الخادم' },
    kept: 1,
  });

  // المستودع غير معدَّل: '' محلياً مقابل مرجعية `null` من حمولة مسودّة — «كل
  // المخزون» نفسه، فيأخذ قيمة الخادم ولا يُحتسب تعديلاً.
  assert.deepEqual(rebaseHeader(
    server,
    { ...baseline, warehouse: '' },
    { ...baseline, warehouse: null },
  ), {
    header: server,
    kept: 0,
  });

  // الثلاثة معدَّلة معاً — تبقى كلها.
  assert.deepEqual(rebaseHeader(server, {
    date: '2026-10-21', warehouse: 7, notes: 'كلها محلي',
  }, baseline), {
    header: { date: '2026-10-21', warehouse: 7, notes: 'كلها محلي' },
    kept: 3,
  });
});

test("إعادة تأسيس الرأس: '' وnull في المستودع قيمةٌ واحدة — ليسا تعديلاً", () => {
  const server: StocktakeHeader = {
    date: '2026-10-23', warehouse: 2, notes: 'ملاحظات الخادم',
  };
  const base = { date: '2026-10-20', notes: 'ملاحظات سابقة' };

  // الشاشة تحمل '' ومرجعية حمولة المسودّة null: كلاهما «كل المخزون» ⇒ لم يعدّله أحد
  // فيأخذ مستودع الخادم الجديد ولا يُحتسب بين «تعديلاتك».
  assert.deepEqual(rebaseHeader(
    server,
    { ...base, warehouse: '' },
    { ...base, warehouse: null },
  ), {
    header: { date: '2026-10-23', warehouse: 2, notes: 'ملاحظات الخادم' },
    kept: 0,
  });

  // والعكس: null محلياً و'' في المرجعية.
  assert.deepEqual(rebaseHeader(
    server,
    { ...base, warehouse: null },
    { ...base, warehouse: '' },
  ), {
    header: { date: '2026-10-23', warehouse: 2, notes: 'ملاحظات الخادم' },
    kept: 0,
  });
});

test('اسم المنتج المعروض: display_name ثم name_ar ثم name_en ثم sku ثم المعرّف', () => {
  assert.equal(productLabel({ id: 5, display_name: 'د', name_ar: 'أ', sku: 'S' }), 'د');
  assert.equal(productLabel({ id: 5, display_name: '', name_ar: 'أ', name_en: 'E', sku: 'S' }), 'أ');
  assert.equal(productLabel({ id: 5, name_en: 'E', sku: 'S' }), 'E');
  assert.equal(productLabel({ id: 5, sku: 'S' }), 'S');
  assert.equal(productLabel({ id: 5 }), 'منتج #5');
});

test('نصّ «عدّه»: الخاتم يتبع القيمة المعروضة', () => {
  assert.equal(stocktakeStampText(line({ counted_quantity: '' })), '');
  assert.equal(
    stocktakeStampText(line({ counted_quantity: '12', baseline: '10' })),
    'تعديلك — غير محفوظ',
  );
  const stamped = line({
    counted_quantity: '4',
    baseline: '4',
    counted_by_name: 'أحمد',
    counted_at: '2026-10-22T08:05:00',
  });
  assert.equal(stocktakeStampText(stamped), 'أحمد · 22/10/2026 08:05');
  // بلا اسمٍ وبختمٍ فقط: الوقت وحده — لا فاصلةٌ معلّقة.
  assert.equal(
    stocktakeStampText(line({
      counted_quantity: '4', baseline: '4', counted_at: '2026-10-22T08:05:00',
    })),
    '22/10/2026 08:05',
  );
});

test('صياغة العدد العربية: واحد واثنان و3–10 و11+', () => {
  const forms = { one: 'منتجٌ واحد', two: 'منتجان', few: 'منتجات', many: 'منتجاً' };
  assert.equal(arabicCount(1, forms), 'منتجٌ واحد');
  assert.equal(arabicCount(2, forms), 'منتجان');
  assert.equal(arabicCount(3, forms), '3 منتجات');
  assert.equal(arabicCount(10, forms), '10 منتجات');
  assert.equal(arabicCount(11, forms), '11 منتجاً');
  assert.equal(arabicCount(143, forms), '143 منتجاً');
  const withZero = { ...forms, zero: '0 منتج' };
  assert.equal(arabicCount(0, withZero), '0 منتج');
});

test('ملخّص النطاق: N من العدّادات وM من الاختيار، وكلا الوضعين', () => {
  assert.deepEqual(
    summarizeScopeSelection({ mode: 'categories', checkedIds: [10, 11, 10], uncategorized: true, counts: COUNTS }),
    { products: 3 + 4 + 2, categories: 3 },
  );
  assert.deepEqual(
    summarizeScopeSelection({ mode: 'categories', checkedIds: [], uncategorized: false, counts: COUNTS }),
    { products: 0, categories: 0 },
  );
  assert.deepEqual(
    summarizeScopeSelection({ mode: 'all', checkedIds: [], uncategorized: false, counts: COUNTS }),
    { products: 9, categories: 3 },
  );
  assert.deepEqual(
    summarizeScopeSelection({ mode: 'manual', checkedIds: [10], uncategorized: true, counts: COUNTS }),
    { products: 0, categories: 0 },
  );
});

test('«إنشاء» ممنوع عند صفر منتجات إلا في الوضع اليدوي', () => {
  assert.equal(canCreateFromScope('categories', { products: 0, categories: 0 }), false);
  assert.equal(canCreateFromScope('all', { products: 0, categories: 0 }), false);
  assert.equal(canCreateFromScope('manual', { products: 0, categories: 0 }), true);
  assert.equal(canCreateFromScope('categories', { products: 1, categories: 1 }), true);
});

test('جسم الإنشاء: مفاتيح K1 بالحرف، واليدوي بلا scope', () => {
  const manual = buildStocktakeCreateBody({
    mode: 'manual', stocktakeDate: '2026-10-22', warehouse: 5, notes: 'ملاحظة',
    checkedIds: [11, 10], uncategorized: true, includeInactive: true,
  });
  assert.equal('scope' in manual, false);
  assert.deepEqual(manual, {
    stocktake_date: '2026-10-22', warehouse: 5, notes: 'ملاحظة',
  });

  assert.deepEqual(buildStocktakeCreateBody({
    mode: 'categories', stocktakeDate: '2026-10-22', warehouse: null, notes: '',
    checkedIds: [11, 10, 10], uncategorized: true, includeInactive: false,
  }), {
    stocktake_date: '2026-10-22', warehouse: null, notes: '',
    scope: {
      all: false, categories: [10, 11], uncategorized: true, include_inactive: false,
    },
  });

  assert.deepEqual(buildStocktakeCreateBody({
    mode: 'all', stocktakeDate: '2026-10-22', warehouse: null, notes: '',
    checkedIds: [10], uncategorized: true, includeInactive: true,
  }), {
    stocktake_date: '2026-10-22', warehouse: null, notes: '',
    scope: {
      all: true, categories: [], uncategorized: false, include_inactive: true,
    },
  });
});

test('سطر الإضافة اليدوية يحمل الاسم والعشيرة ويُعلَن مضافاً محلياً', () => {
  const added = newSheetLineFromProduct({
    id: 9, sku: 'Z-9', name_ar: 'زيت', display_name: 'زيت — موبيل',
    quantity_on_hand: '12.0000', category: 10,
  });
  assert.equal(added.product_name, 'زيت — موبيل');
  assert.equal(added.product_quantity_on_hand, '12.0000');
  assert.equal(added.baseline, undefined);
  assert.equal(added.counted_quantity, '');
});

// ─── ST-2: اختيار منتجات النطاق (تصنيفٌ كامل · منتجاتٌ صريحة) ────────────────

const pick = (id: number, category: number | null = 10, isActive = true): ScopeProductPick =>
  ({ id, category, isActive });

const picks = (...items: ScopeProductPick[]): ReadonlyMap<number, ScopeProductPick> =>
  new Map(items.map((item) => [item.id, item]));

const pickState = (overrides: Partial<ScopePickState> = {}): ScopePickState => ({
  categories: [],
  products: new Map(),
  uncategorized: false,
  ...overrides,
});

const scopeKeys = (state: ScopePickState): number[] =>
  [...state.products.keys()].sort((a, b) => a - b);

test('تنقية الاختيار: ما يغطّيه تصنيفٌ مشمول أو «بدون تصنيف» يُسقط من الصريح', () => {
  assert.deepEqual(
    scopeKeys(reconcileScopeProducts(pickState({
      categories: [10], uncategorized: true,
      products: picks(pick(1, 10), pick(2, 11), pick(3, null)),
    }))),
    [2],
  );
  // علمُ «بدون تصنيف» مطفي: منتجُه الصريح يبقى — اختيارُه جزئيٌّ لا مغطّى.
  assert.deepEqual(
    scopeKeys(reconcileScopeProducts(pickState({
      categories: [10], uncategorized: false,
      products: picks(pick(1, 10), pick(3, null)),
    }))),
    [3],
  );
});

test('إلغاء منتجٍ من تصنيفٍ مشمولٍ بكامله: يُنزع التصنيف وتبقى بقية منتجاته صريحة', () => {
  const next = toggleScopeProduct(
    pickState({ categories: [10, 11] }),
    pick(5, 10),
    [pick(5, 10), pick(6, 10), pick(7, 10)],
  );
  assert.deepEqual(next.categories, [11]);
  assert.deepEqual(scopeKeys(next), [6, 7]);
  assert.equal(next.uncategorized, false);
});

test('منتجٌ من تصنيفٍ مشمولٍ غاب عن قائمته: لا يُنزع التصنيف بمعرفةٍ ناقصة', () => {
  const state = pickState({ categories: [10], products: picks(pick(9, 11)) });
  // قائمةٌ ناقصةٌ لا تحوي المنتج نفسه: نزعُ التصنيف هنا يُخرجه كلّه من النطاق.
  assert.equal(toggleScopeProduct(state, pick(5, 10), [pick(6, 10), pick(7, 10)]), state);
  // وبقائمةٍ كاملةٍ يُنزع ويُضاف الباقي — الفرق كلّه في المعرفة.
  const next = toggleScopeProduct(state, pick(5, 10), [pick(5, 10), pick(6, 10)]);
  assert.deepEqual(next.categories, []);
  assert.deepEqual(scopeKeys(next), [6, 9]);
});

test('بلا قائمةِ منتجاتٍ للتصنيف: يُضاف المنتج صريحاً ولا يُرقّى التصنيف', () => {
  const next = toggleScopeProduct(pickState(), pick(5, 10), []);
  // اكتمالُ قائمةٍ فارغةٍ ليس اكتمالاً: الترقية هنا تُدخل التصنيف كلّه بلا علم.
  assert.deepEqual(next.categories, []);
  assert.deepEqual(scopeKeys(next), [5]);
});

test('تأشير منتجٍ صريح: يُزاد وحده حتى يكتمل التصنيف فيُرقّى ويُفرغ الصريح', () => {
  const partial = toggleScopeProduct(
    pickState({ products: picks(pick(6, 10)) }),
    pick(5, 10),
    [pick(5, 10), pick(6, 10), pick(7, 10)],
  );
  assert.deepEqual(partial.categories, []);
  assert.deepEqual(scopeKeys(partial), [5, 6]);

  const promoted = toggleScopeProduct(
    pickState({ products: picks(pick(6, 10), pick(7, 10)) }),
    pick(5, 10),
    [pick(5, 10), pick(6, 10), pick(7, 10)],
  );
  assert.deepEqual(promoted.categories, [10]);
  assert.equal(promoted.products.size, 0);

  const removed = toggleScopeProduct(
    pickState({ products: picks(pick(5, 10), pick(6, 10)) }),
    pick(5, 10),
    [pick(5, 10), pick(6, 10)],
  );
  assert.deepEqual(removed.categories, []);
  assert.deepEqual(scopeKeys(removed), [6]);
});

test('«بدون تصنيف»: الإلغاء من الشمول الكامل يُصرّح الباقي، وتأشير الأخير يرقّي إلى العلم', () => {
  const unchecked = toggleScopeProduct(
    pickState({ uncategorized: true }),
    pick(3, null),
    [pick(3, null), pick(4, null)],
  );
  assert.equal(unchecked.uncategorized, false);
  assert.deepEqual(scopeKeys(unchecked), [4]);

  const promoted = toggleScopeProduct(
    pickState({ products: picks(pick(4, null)) }),
    pick(3, null),
    [pick(3, null), pick(4, null)],
  );
  assert.equal(promoted.uncategorized, true);
  assert.equal(promoted.products.size, 0);
  assert.deepEqual(promoted.categories, []);
});

test('تصنيفٌ كاملٌ أو ملغى بالجملة: يحسم التصنيف ويُسقط صريحَه', () => {
  const all = setCategoryProducts(
    pickState({ categories: [11], products: picks(pick(5, 10), pick(9, 11)) }),
    10,
    'all',
    [pick(5, 10), pick(6, 10)],
  );
  assert.deepEqual([...all.categories].sort((a, b) => a - b), [10, 11]);
  assert.deepEqual(scopeKeys(all), [9]);

  const none = setCategoryProducts(
    pickState({ categories: [10], products: picks(pick(5, 10), pick(9, 11)) }), 10, 'none', [],
  );
  assert.deepEqual(none.categories, []);
  assert.deepEqual(scopeKeys(none), [9]);

  const allUncategorized = setCategoryProducts(
    pickState({ products: picks(pick(3, null)) }), null, 'all', [pick(3, null)],
  );
  assert.equal(allUncategorized.uncategorized, true);
  assert.equal(allUncategorized.products.size, 0);

  const noneUncategorized = setCategoryProducts(
    pickState({ uncategorized: true }), null, 'none', [],
  );
  assert.equal(noneUncategorized.uncategorized, false);
});

test('كنس غير الصالح: المعطَّلُ في اللقطة والغائبُ عن تصنيفٍ أُعيدت قراءته', () => {
  // الخادم لا يردّ صفاً غير فعّالٍ حين يكون include_inactive مطفيّاً: المعطَّل
  // **يغيب**، فعلَمُ الاختيار نفسه هو القرينة الأولى على تعطّله.
  const staleFlag = pruneInactiveScopeProducts(
    pickState({ products: picks(pick(4, 12, false)) }),
    [pick(1, 10, true)],
  );
  assert.equal(staleFlag.removed, 1);
  assert.deepEqual(scopeKeys(staleFlag.state), []);

  // تصنيفُه (10) في المحمَّل ⇒ أُعيدت قراءته، ومعرّفه غاب ⇒ خرج من الأهلية.
  const gone = pruneInactiveScopeProducts(
    pickState({ products: picks(pick(1, 10, true), pick(2, 10, true), pick(5, 11, true)) }),
    [pick(1, 10, true), pick(6, 10, true)],
  );
  assert.equal(gone.removed, 1);
  assert.deepEqual(scopeKeys(gone.state), [1, 5]);

  // حاضرٌ نشطٌ في المحمَّل، وتصنيفٌ لم يُقرأ (11) ⇒ يُبقى الاثنان.
  const kept = pruneInactiveScopeProducts(
    pickState({ products: picks(pick(1, 10, true), pick(5, 11, true)) }),
    [pick(1, 10, true), pick(6, 10, true)],
  );
  assert.equal(kept.removed, 0);
  assert.deepEqual(scopeKeys(kept.state), [1, 5]);
});

test('التصنيفات الجزئية: فيها منتجٌ صريح وليست مشمولةً بكاملها', () => {
  assert.deepEqual(
    partialCategoryIds(pickState({
      categories: [11],
      products: picks(pick(1, 10), pick(2, 10), pick(3, 11), pick(4, null)),
    })),
    [10],
  );
  assert.deepEqual(partialCategoryIds(pickState()), []);
});

test('ملخّص النطاق مع منتجاتٍ صريحة: تُجمع بالنوعين ولا يتكرّر تصنيفُ المنتج الصريح', () => {
  assert.deepEqual(
    summarizeScopeSelection({
      mode: 'categories', checkedIds: [10], uncategorized: false, counts: COUNTS,
      products: picks(pick(1, 11), pick(2, 11)),
    }),
    { products: 3 + 2, categories: 2 },
  );
  // «بدون تصنيف» مرّةً واحدة، والتصنيف الجزئي يُحسب تصنيفاً.
  assert.deepEqual(
    summarizeScopeSelection({
      mode: 'categories', checkedIds: [], uncategorized: true, counts: COUNTS,
      products: picks(pick(3, 10)),
    }),
    { products: 2 + 1, categories: 1 + 1 },
  );
  // منتجٌ صريحٌ بلا تصنيف: «بدون تصنيف» اختيارٌ قائم يُحسب تصنيفاً واحداً.
  assert.deepEqual(
    summarizeScopeSelection({
      mode: 'categories', checkedIds: [], uncategorized: false, counts: COUNTS,
      products: picks(pick(4, null)),
    }),
    { products: 1, categories: 1 },
  );
  // والصريحُ المغطّى لا يُزاد مرّتين: نفسُ ما يُسقطه الخادم قبل الحفظ.
  assert.deepEqual(
    summarizeScopeSelection({
      mode: 'categories', checkedIds: [10], uncategorized: true, counts: COUNTS,
      products: picks(pick(1, 10), pick(4, null)),
    }),
    { products: 2 + 3, categories: 1 + 1 },
  );
});

test('جسم الإنشاء مع منتجاتٍ صريحة: مرتّبةٌ في وضع التصنيفات وحده وغير فارغةٍ فقط', () => {
  const categories = buildStocktakeCreateBody({
    mode: 'categories', stocktakeDate: '2026-10-22', warehouse: null, notes: '',
    checkedIds: [11, 10, 10], uncategorized: true, includeInactive: false,
    products: picks(pick(12, 10), pick(5, 10)),
  });
  assert.deepEqual(categories.scope, {
    all: false, categories: [10, 11], uncategorized: true, include_inactive: false,
    products: [5, 12],
  });

  const empty = buildStocktakeCreateBody({
    mode: 'categories', stocktakeDate: '2026-10-22', warehouse: null, notes: '',
    checkedIds: [10], uncategorized: false, includeInactive: false,
    products: new Map(),
  });
  assert.deepEqual(empty.scope, {
    all: false, categories: [10], uncategorized: false, include_inactive: false,
  });

  const all = buildStocktakeCreateBody({
    mode: 'all', stocktakeDate: '2026-10-22', warehouse: null, notes: '',
    checkedIds: [], uncategorized: false, includeInactive: true,
    products: picks(pick(5, 10)),
  });
  assert.deepEqual(all.scope, {
    all: true, categories: [], uncategorized: false, include_inactive: true,
  });

  const manual = buildStocktakeCreateBody({
    mode: 'manual', stocktakeDate: '2026-10-22', warehouse: null, notes: '',
    checkedIds: [], uncategorized: false, includeInactive: false,
    products: picks(pick(5, 10)),
  });
  assert.equal('scope' in manual, false);
});
