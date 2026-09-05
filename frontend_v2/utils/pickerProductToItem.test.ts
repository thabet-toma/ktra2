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
  family_id: 11,
  family_name: 'مقاس إطار',
  stock_status: 'low_stock',
  is_service: false,
  available_quantity: '3',
  quantity_on_hand: '8',
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

// #22: family_id/family_name يمرّان عبر نقطة التحويل الموحّدة إلى مستدعيَيها
// معاً — لا نسخة ثانية (الحقلان يخصّان «المنتج» الأب، لا يُختاران بندًا).
test('كلا المستدعيين: family_id وfamily_name يمرّان كما هما', () => {
  const full = mapPickerProductToItem(fullProduct, fullScreenOpts);
  const modal = mapPickerProductToItem(fullProduct, searchModalOpts);
  assert.equal(full.familyId, '11');
  assert.equal(full.familyName, 'مقاس إطار');
  assert.equal(modal.familyId, '11');
  assert.equal(modal.familyName, 'مقاس إطار');
});

test('family_id/family_name غائبان أو null يصيران undefined لا نصاً "null"', () => {
  const item = mapPickerProductToItem({ id: 1 }, searchModalOpts);
  assert.equal(item.familyId, undefined);
  assert.equal(item.familyName, undefined);

  const nullish = mapPickerProductToItem(
    { id: 2, family_id: null, family_name: null }, fullScreenOpts,
  );
  assert.equal(nullish.familyId, undefined);
  assert.equal(nullish.familyName, undefined);
});

// ISSUE #133: شارة المخزون والمتاح بعد الحجز على جانب الشراء تحتاج هذه الحقول
// من نفس صفّ `?view=lookup` الذي تحمله `Item` أصلاً — لا تنزل عن نقطة التحويل
// الموحّدة إلى مطابقٍ ثانٍ. أساسية (`base`) لا حقلاً موسّعاً: نافذة البحث
// (`onItemCreated`/quick-create) تغذّي نفس مصفوفة `allDbItems` التي يبني منها
// المنتقي شارته، فحقلٌ يصل مستدعياً واحداً دون الآخر يُنتج بندَ شارةً صامتاً.
test('كلا المستدعيين: stock_status وis_service وavailable_quantity وquantity_on_hand يمرّان كما هما', () => {
  const full = mapPickerProductToItem(fullProduct, fullScreenOpts);
  const modal = mapPickerProductToItem(fullProduct, searchModalOpts);
  assert.equal(full.stock_status, 'low_stock');
  assert.equal(full.is_service, false);
  assert.equal(full.available_quantity, '3');
  assert.equal(full.quantity_on_hand, '8');
  assert.equal(modal.stock_status, 'low_stock');
  assert.equal(modal.is_service, false);
  assert.equal(modal.available_quantity, '3');
  assert.equal(modal.quantity_on_hand, '8');
});

test('stock_status/is_service/available_quantity/quantity_on_hand غائبون يصيرون undefined', () => {
  const item = mapPickerProductToItem({ id: 1 }, searchModalOpts);
  assert.equal(item.stock_status, undefined);
  assert.equal(item.is_service, undefined);
  assert.equal(item.available_quantity, undefined);
  assert.equal(item.quantity_on_hand, undefined);
});
