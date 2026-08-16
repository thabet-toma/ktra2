import test from "node:test";
import assert from "node:assert/strict";
// الامتداد صريح: هذا الملف مُختبَر بـ`node --test` الذي لا يحلّ الاستيراد بلا امتداد.
import { resolvePasteZone, type PasteZoneState } from "./clipboardImage.ts";

/** منطقة افتراضية: النشاط = المعرّف، أي أن ترتيب المعرّفات هو ترتيب التركيب. */
const zone = (id: number, over: Partial<PasteZoneState> = {}): PasteZoneState => ({
  id,
  enabled: true,
  interactionRequired: false,
  activity: id,
  ...over,
});

const anywhere = { editable: false, containerIds: [] as number[] };

test("المنطقة الحاوية لهدف اللصق تفوز مهما كان ترتيب النشاط", () => {
  const zones = [zone(1, { activity: 9 }), zone(2, { activity: 1 })];
  assert.equal(resolvePasteZone(zones, { editable: false, containerIds: [2] }), 2);
});

test("المنطقة الأعمق تفوز حين تتداخل منطقتان", () => {
  const zones = [zone(1), zone(2)];
  // `containerIds` مرتّبة من الأعمق إلى الأسطح كما يبنيها المُوجِّه من شجرة DOM.
  assert.equal(resolvePasteZone(zones, { editable: false, containerIds: [2, 1] }), 2);
});

test("هدف نصّي (input/textarea/contenteditable) لا يذهب إلى أي منطقة", () => {
  const zones = [zone(1), zone(2)];
  assert.equal(resolvePasteZone(zones, { editable: true, containerIds: [] }), null);
});

test("هدف نصّي داخل منطقة يبقى للمنطقة — قاعدة الاحتواء تسبق قاعدة النصّ", () => {
  // لصق *صورة* داخل حقل نصّ تابع لمنطقة رفع لا يفعل شيئاً في الحقل، فتأخذه المنطقة.
  const zones = [zone(1)];
  assert.equal(resolvePasteZone(zones, { editable: true, containerIds: [1] }), 1);
});

test("منطقة واحدة تفوز باللصق من أي مكان في الشاشة", () => {
  assert.equal(resolvePasteZone([zone(1)], anywhere), 1);
});

test("منطقة النافذة المنبثقة (الأحدث تركيباً) تتقدّم على منطقة الصفحة", () => {
  const page = zone(1, { activity: 1 });
  const modal = zone(2, { activity: 2 });
  assert.equal(resolvePasteZone([page, modal], anywhere), 2);
});

test("التفاعل الأخير يتقدّم على ترتيب التركيب", () => {
  const page = zone(1, { activity: 7 }); // نُقر داخلها بعد تركيب الثانية
  const later = zone(2, { activity: 2 });
  assert.equal(resolvePasteZone([page, later], anywhere), 1);
});

test("منطقة تشترط تفاعلاً لا تفوز أبداً بترتيب التركيب", () => {
  const row = zone(2, { interactionRequired: true, activity: 0 });
  const page = zone(1, { activity: 1 });
  assert.equal(resolvePasteZone([page, row], anywhere), 1);
  // ووحدها بلا تفاعل: لا شيء بدل التخمين
  assert.equal(resolvePasteZone([row], anywhere), null);
});

test("منطقة تشترط تفاعلاً تفوز بعد النقر داخلها أو بالاحتواء", () => {
  const row = zone(2, { interactionRequired: true, activity: 5 });
  const page = zone(1, { activity: 1 });
  assert.equal(resolvePasteZone([page, row], anywhere), 2);

  const untouched = zone(2, { interactionRequired: true, activity: 0 });
  assert.equal(resolvePasteZone([page, untouched], { editable: false, containerIds: [2] }), 2);
});

test("منطقة معطّلة لا تفوز أبداً — لا بالاحتواء ولا بالنشاط", () => {
  const disabled = zone(2, { enabled: false, activity: 99 });
  const page = zone(1, { activity: 1 });
  assert.equal(resolvePasteZone([page, disabled], { editable: false, containerIds: [2] }), 1);
  assert.equal(resolvePasteZone([page, disabled], anywhere), 1);
  assert.equal(resolvePasteZone([disabled], anywhere), null);
});

test("لا مناطق مسجّلة ← لا شيء", () => {
  assert.equal(resolvePasteZone([], anywhere), null);
});
