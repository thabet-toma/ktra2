import assert from "node:assert/strict";
import test from "node:test";

import {
  productInquiryMessage,
  storeHomePath,
  storeHomeUrl,
  storeProductPath,
  storeProductUrl,
  whatsappLink,
  whatsappNumber,
} from "./storeLinks.ts";

test("رابط المتجر الذي ينسخه صاحبه: مسار واحد ترمّزه دالة واحدة", () => {
  assert.equal(storeHomePath("alpha"), "/store/alpha");
  assert.equal(storeHomePath("متجر ألف"), `/store/${encodeURIComponent("متجر ألف")}`);
  assert.equal(storeHomeUrl("https://ktra-pro.tech/", "alpha"), "https://ktra-pro.tech/store/alpha");
  assert.equal(storeHomeUrl("https://ktra-pro.tech", "alpha"), "https://ktra-pro.tech/store/alpha");
});

test("مسار الصنف يرمّز المعرّف والـslug فلا يكسره حرف عربي أو مسافة", () => {
  assert.equal(storeProductPath("alpha", 12), "/store/alpha/p/12");
  assert.equal(storeProductPath("متجر ألف", 3), `/store/${encodeURIComponent("متجر ألف")}/p/3`);
});

test("الرابط المطلق لا يضاعف الشرطة المائلة عند أصلٍ منتهٍ بها", () => {
  assert.equal(storeProductUrl("https://ktra-pro.tech/", "alpha", 7), "https://ktra-pro.tech/store/alpha/p/7");
  assert.equal(storeProductUrl("https://ktra-pro.tech", "alpha", 7), "https://ktra-pro.tech/store/alpha/p/7");
});

test("الرقم الدولي يُنظَّف من الرموز، و`00` تُقصّ كما تُقصّ `+`", () => {
  assert.equal(whatsappNumber("+970 59 123 4567"), "970591234567");
  assert.equal(whatsappNumber("00970-59-1234567"), "970591234567");
});

test("الرقم المحلي يُرفض بدل تخمين مفتاح الدولة", () => {
  // «0591234567» بلا مفتاح دولة: أي تخمين يفتح محادثة مع شخص آخر في بلد آخر.
  assert.equal(whatsappNumber("0591234567"), null);
  assert.equal(whatsappNumber("١٢٣"), null);
  assert.equal(whatsappNumber(""), null);
  assert.equal(whatsappNumber(null), null);
  assert.equal(whatsappNumber("12345"), null);
});

test("رابط واتساب يحمل النص مرمّزاً، ويغيب كلياً حين يغيب رقم صالح", () => {
  const link = whatsappLink("+970591234567", "مرحباً");
  assert.equal(link, `https://wa.me/970591234567?text=${encodeURIComponent("مرحباً")}`);
  assert.equal(whatsappLink("0591234567", "مرحباً"), null);
  assert.equal(whatsappLink(null, "مرحباً"), null);
});

test("رسالة الاستفسار تحمل اسم الصنف ورابطه — البائع يعرف ما يُسأل عنه", () => {
  const message = productInquiryMessage("إطار ميشلان", "https://ktra-pro.tech/store/alpha/p/7");
  assert.match(message, /إطار ميشلان/);
  assert.match(message, /store\/alpha\/p\/7/);
});
