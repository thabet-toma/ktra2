import test from "node:test";
import assert from "node:assert/strict";
import { ccInitials } from "./ccInitials.ts";

test("أداةُ التعريف لا تُقرأ حرفاً من الاسم", () => {
  assert.equal(ccInitials("عمر الشريف"), "عش");
  assert.equal(ccInitials("رنا الخطيب"), "رخ");
  assert.equal(ccInitials("سامي درويش"), "سد");
});

test("«عبد» تُدمج مع ما بعدها فتبقى حرفَ الاسم", () => {
  assert.equal(ccInitials("لينا عبد الله"), "لع");
  assert.equal(ccInitials("عبد الرحمن ياسين"), "عي");
  assert.equal(ccInitials("محمد أبو زيد"), "مأ");
});

test("«الله» لا يُنزع منها فتصير «له»", () => {
  assert.equal(ccInitials("الله"), "ال");
  assert.equal(ccInitials("عبد الله"), "عب");
});

test("اسمٌ واحدٌ يُعطي حرفين منه", () => {
  assert.equal(ccInitials("لينا"), "لي");
  assert.equal(ccInitials("الخطيب"), "خط");
});

test("الأسماءُ اللاتينيّة تبقى كما كانت", () => {
  assert.equal(ccInitials("John Smith"), "JS");
  assert.equal(ccInitials("  Ada  "), "Ad");
});

test("الفراغُ يُعطي البديلَ لا سلسلةً فارغةً تُفرغ الدائرة", () => {
  assert.equal(ccInitials(""), "؟");
  assert.equal(ccInitials("   "), "؟");
  assert.equal(ccInitials(null as unknown as string), "؟");
  assert.equal(ccInitials("", "ك"), "ك");
});

test("«ال» وحدَها أقصرُ من أن يُنزع منها شيء", () => {
  assert.equal(ccInitials("ال"), "ال");
});
