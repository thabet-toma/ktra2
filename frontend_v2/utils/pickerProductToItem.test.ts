import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mapPickerProductToItem } from './pickerProductToItem.ts';

// خيارات المستدعيَين الفعليَّين اليوم — لا تُغيَّر هنا بلا تغيير مقابل في
// firestoreService.ts و ItemSearchModal.tsx.
const fullScreenOpts = {
  fallbackName: (row: Record<string, unknown>) => `Item ${(row as any).id}`,
  extended: true,
};
const searchModalOpts = {
  fallbackName: (row: Record<string, unknown>) => `منتج ${(row as any).id ?? ""}`,
  categoryIdAcceptsZero: true,
  emptyModelNumberAsUndefined: true,
};

const fullProduct = {
  id: 42,
  name_ar: 'إطار',
  name_en: 'Tyre',
  sku: 'SKU-1',
  category: 7,
  category_name: 'إطارات',
  hs_code: '4011.10',
  min_stock_level: 5,
  online_description: 'وصف المتجر',
  is_for_sale_online: true,
  online_price: '199.900',
  barcode: '1234567890128',
  is_serialized: true,
  supplier_codes_text: 'A1 B2',
  attachments: [{ file_path: '/img/1.png' }, { file_path: '' }],
};

test('الشاشة الكاملة: الحقول الموسّعة كلّها كما كانت', () => {
  const item = mapPickerProductToItem(fullProduct, fullScreenOpts);
  assert.equal(item.id, '42');
  assert.equal(item.name, 'إطار');
  assert.equal(item.modelNumber, 'SKU-1');
  assert.equal(item.categoryId, '7');
  assert.equal(item.categoryName, 'إطارات');
  assert.equal(item.subCategoryId, '');
  assert.equal(item.subCategoryName, '');
  assert.equal(item.brandId, '');
  assert.equal(item.brandName, '');
  assert.deepEqual(item.imageUrls, ['/img/1.png']);
  assert.equal(item.hsCodePrimary, '4011.10');
  assert.equal(item.hsCodeAlternative, '');
  assert.equal(item.quantity, 5);
  assert.equal(item.specifications, 'وصف المتجر');
  assert.equal(item.notes, '');
  assert.equal(item.isActive, true);
  assert.equal(item.salePrice, 199.9);
  assert.equal(item.storeName, 'إطار');
  assert.equal(item.storeDescription, 'وصف المتجر');
  assert.equal(item.barcode, '1234567890128');
  assert.equal(item.isSerialized, true);
  assert.equal(item.supplierCodes, 'A1 B2');
});

test('الشاشة الكاملة: الاسم الاحتياطي بالإنجليزية والصور الفارغة تصير ["","",""]', () => {
  const item = mapPickerProductToItem(
    { id: 9, attachments: [] },
    fullScreenOpts,
  );
  assert.equal(item.name, 'Item 9');
  assert.deepEqual(item.imageUrls, ['', '', '']);
  assert.equal(item.modelNumber, '');
});

test('الشاشة الكاملة: category=0 تُعامَل كغير صالحة (truthy check)', () => {
  const item = mapPickerProductToItem({ id: 1, category: 0 }, fullScreenOpts);
  assert.equal(item.categoryId, '');
});

test('نافذة البحث: لا حقول موسّعة، ومودل نمبر الفارغ undefined لا ""', () => {
  const item = mapPickerProductToItem(fullProduct, searchModalOpts);
  assert.equal(item.specifications, '');
  assert.deepEqual(item.imageUrls, []);
  assert.equal(item.subCategoryId, undefined);
  assert.equal(item.hsCodePrimary, undefined);
  assert.equal(item.quantity, undefined);
  assert.equal(item.isActive, undefined);
  assert.equal(item.salePrice, undefined);
  assert.equal(item.storeName, undefined);
  assert.equal('subCategoryId' in item, false);
  assert.equal('quantity' in item, false);
});

test('نافذة البحث: modelNumber الفارغ يصير undefined لا نصاً فارغاً', () => {
  const item = mapPickerProductToItem({ id: 5 }, searchModalOpts);
  assert.equal(item.modelNumber, undefined);
});

test('نافذة البحث: الاسم الاحتياطي بالعربية، وcategory=0 صالحة (!= null)', () => {
  const item = mapPickerProductToItem({ id: 3, category: 0 }, searchModalOpts);
  assert.equal(item.name, 'منتج 3');
  assert.equal(item.categoryId, '0');
});

test('نافذة البحث: id غائب يجعل اسم الاحتياط يستعمل نصاً فارغاً', () => {
  const item = mapPickerProductToItem({}, searchModalOpts);
  assert.equal(item.name, 'منتج ');
});

test('كلا المستدعيين: barcode وisSerialized وsupplierCodes متطابقان', () => {
  const full = mapPickerProductToItem(fullProduct, fullScreenOpts);
  const modal = mapPickerProductToItem(fullProduct, searchModalOpts);
  assert.equal(full.barcode, modal.barcode);
  assert.equal(full.isSerialized, modal.isSerialized);
  assert.equal(full.supplierCodes, modal.supplierCodes);
  assert.equal(full.categoryName, modal.categoryName);
});
