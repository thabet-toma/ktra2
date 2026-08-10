/**
 * اختبارات وحدة الباركود — `node --test --experimental-strip-types "utils/*.test.ts"`.
 *
 * الترميز يُفحَص مقابل جداول EAN-13 المنشورة **مكتوبةً هنا حرفياً** لا مشتقّةً كما
 * في الوحدة: الوحدة تشتقّ R من L وG من R، فلو انقلبت الاشتقاقة أعطت رمزاً متّسقاً
 * مع نفسه ولا يقرؤه ماسح. الجداول المستقلّة هي ما يكشف ذلك.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  barcodeLabelsHtml,
  completeEan13,
  ean13CheckDigit,
  ean13Modules,
  ean13Svg,
  isValidEan13,
  onlyDigits,
} from "./barcode.ts";

// ── جداول EAN-13 المنشورة (مرجع مستقلّ عن الوحدة) ─────────────────────────
const L = [
  "0001101", "0011001", "0010011", "0111101", "0100011",
  "0110001", "0101111", "0111011", "0110111", "0001011",
];
const G = [
  "0100111", "0110011", "0011011", "0100001", "0011101",
  "0111001", "0000101", "0010001", "0001001", "0010111",
];
const R = [
  "1110010", "1100110", "1101100", "1000010", "1011100",
  "1001110", "1010000", "1000100", "1001000", "1110100",
];
const PARITY = [
  "LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
  "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL",
];

/** مرجع مباشر: حارس + 6 يسرى بنمط التعاقب + حارس أوسط + 6 يمنى + حارس. */
const referenceModules = (code: string): string => {
  const parity = PARITY[Number(code[0])];
  let bits = "101";
  for (let i = 0; i < 6; i++) {
    const d = Number(code[1 + i]);
    bits += parity[i] === "L" ? L[d] : G[d];
  }
  bits += "01010";
  for (let i = 0; i < 6; i++) bits += R[Number(code[7 + i])];
  return bits + "101";
};

// ── خانة التحقق ────────────────────────────────────────────────────────────

test("خانة التحقق تطابق باركوداً معروفاً (نفس مرجع الخادم)", () => {
  assert.equal(ean13CheckDigit("400638133393"), "1");
  assert.equal(ean13CheckDigit("590123412345"), "7");
  assert.equal(ean13CheckDigit("978020137962"), "4");
});

test("الباركود الصالح يُقبل والمعطوب يُرفض", () => {
  assert.equal(isValidEan13("4006381333931"), true);
  assert.equal(isValidEan13("5901234123457"), true);
  assert.equal(isValidEan13("4006381333930"), false); // خانة تحقق خاطئة
  assert.equal(isValidEan13("123"), false);           // أقصر
  assert.equal(isValidEan13("40063813339311"), false); // أطول
  assert.equal(isValidEan13("400638A333931"), false);  // حرف
  assert.equal(isValidEan13(""), false);
});

test("خانة التحقق ترفض دخلاً ليس 12 رقماً بدل أن تُنتج رمزاً لا يُمسَح", () => {
  assert.throws(() => ean13CheckDigit("12345"), /12/);
  assert.throws(() => ean13CheckDigit("40063813339a"), /12/);
});

test("مجموع صفري: خانة التحقق 0 لا 10", () => {
  // 000000000000 مجموعه 0 ⇒ (10 − 0) % 10 = 0
  assert.equal(ean13CheckDigit("000000000000"), "0");
  assert.equal(isValidEan13("0000000000000"), true);
});

// ── إكمال رقم كتبه المستخدم ────────────────────────────────────────────────

test("12 رقماً تُكمَّل بخانة التحقق", () => {
  const out = completeEan13("400638133393");
  assert.equal(out?.code, "4006381333931");
  assert.equal(out?.corrected, false);
  assert.equal(isValidEan13(out!.code), true);
});

test("رقم أقصر يُصفَّر من اليسار ثم يُكمَّل", () => {
  const out = completeEan13("55");
  assert.equal(out?.code.length, 13);
  assert.equal(out?.code.slice(0, 12), "000000000055");
  assert.equal(isValidEan13(out!.code), true);
});

test("13 رقماً بخانة تحقق سليمة تمرّ كما هي", () => {
  const out = completeEan13("5901234123457");
  assert.equal(out?.code, "5901234123457");
  assert.equal(out?.corrected, false);
});

test("13 رقماً بخانة تحقق خاطئة تُصحَّح والتصحيح يُقال لا يُبتلع", () => {
  const out = completeEan13("5901234123450");
  assert.equal(out?.code, "5901234123457");
  assert.equal(out?.corrected, true);
  assert.match(out!.note, /خانة التحقق/);
});

test("رقم أطول من 13 يُقتصّ على أول 12 خانة", () => {
  const out = completeEan13("59012341234509999");
  assert.equal(out?.code, "5901234123457");
  assert.equal(out?.corrected, true);
});

test("الفواصل والمسافات تسقط، والفراغ لا يُنتج باركوداً", () => {
  assert.equal(onlyDigits(" 400-638 133.393 "), "400638133393");
  assert.equal(completeEan13(" 400-638 133.393 ")?.code, "4006381333931");
  assert.equal(completeEan13("   "), null);
  assert.equal(completeEan13("abc"), null);
  assert.equal(completeEan13(""), null);
});

// ── الترميز والرسم ─────────────────────────────────────────────────────────

test("تسلسل الوحدات يطابق جداول EAN-13 المنشورة", () => {
  // «2…» هي بادئة الترقيم الداخلي التي يولّدها الخادم — تُغطّى صراحةً.
  for (const code of ["4006381333931", "5901234123457", "2000000000008", "0000000000000"]) {
    assert.equal(ean13Modules(code), referenceModules(code), code);
  }
});

test("بنية الرمز: 95 وحدة بحارسين جانبيين وحارس أوسط", () => {
  const bits = ean13Modules("5901234123457");
  assert.equal(bits.length, 95);
  assert.equal(bits.slice(0, 3), "101");
  assert.equal(bits.slice(45, 50), "01010");
  assert.equal(bits.slice(92), "101");
});

test("الرقم الأول يغيّر نمط التعاقب لا الأعمدة المرسومة لبقية الأرقام", () => {
  // 0 ⇒ LLLLLL و5 ⇒ LGGLLG: نفس الأرقام الستّ اليسرى، رمزان مختلفان.
  const zeroFirst = ean13Modules("0" + "123456" + "78901" + ean13CheckDigit("012345678901"));
  const fiveFirst = ean13Modules("5" + "123456" + "78901" + ean13CheckDigit("512345678901"));
  assert.notEqual(zeroFirst.slice(3, 45), fiveFirst.slice(3, 45));
  assert.equal(zeroFirst.slice(3, 10), L[1]);
  assert.equal(fiveFirst.slice(3, 10), L[1]); // أول خانة L في النمطين
  assert.equal(zeroFirst.slice(10, 17), L[2]);
  assert.equal(fiveFirst.slice(10, 17), G[2]); // الثانية G عند الرقم الأول 5
});

test("الترميز يرفض باركوداً غير صالح بدل رسم رمز كاذب", () => {
  assert.throws(() => ean13Modules("4006381333930"), /EAN-13/);
  assert.throws(() => ean13Modules("123"), /EAN-13/);
});

/**
 * «ماسح» بسيط: يقرأ هندسة الـSVG المرسوم (مواضع المستطيلات وعروضها) ويعيد بناء
 * الأرقام منها. هذا ما يعنيه «قابل للمسح» فعلياً — أن يعطي الرسمُ نفسُه الرقمَ
 * ذاته، لا أن تكون البتّات صحيحة في الذاكرة بينما الرسم أزاحها.
 */
const scanSvg = (svg: string, moduleWidth: number): string => {
  // الأعمدة السوداء وحدها — خلفية الرمز البيضاء fill="#fff" ليست بيانات.
  const rects = [...svg.matchAll(/<rect x="([\d.]+)" y="0" width="([\d.]+)" height="[\d.]+" fill="#000"\/>/g)];
  assert.notEqual(rects.length, 0, "لا أعمدة مرسومة");
  const filled = new Set<number>();
  for (const m of rects) {
    const start = Math.round(Number(m[1]) / moduleWidth);
    const span = Math.round(Number(m[2]) / moduleWidth);
    for (let i = 0; i < span; i++) filled.add(start + i);
  }
  // منطقة الهدوء اليسرى 11 وحدة ⇒ الرمز يبدأ عند الوحدة 11.
  let bits = "";
  for (let i = 11; i < 11 + 95; i++) bits += filled.has(i) ? "1" : "0";

  assert.equal(bits.slice(0, 3), "101", "حارس أيسر");
  assert.equal(bits.slice(45, 50), "01010", "حارس أوسط");
  assert.equal(bits.slice(92), "101", "حارس أيمن");

  const left = Array.from({ length: 6 }, (_, i) => bits.slice(3 + i * 7, 10 + i * 7));
  const right = Array.from({ length: 6 }, (_, i) => bits.slice(50 + i * 7, 57 + i * 7));

  // نمط التعاقب المقروء من الخانات اليسرى يعطي الرقم الأول.
  const parity = left.map((seg) => (L.includes(seg) ? "L" : G.includes(seg) ? "G" : "?")).join("");
  const first = PARITY.indexOf(parity);
  assert.notEqual(first, -1, `نمط تعاقب غير معروف: ${parity}`);

  const leftDigits = left.map((seg) => (L.includes(seg) ? L.indexOf(seg) : G.indexOf(seg)));
  const rightDigits = right.map((seg) => R.indexOf(seg));
  assert.equal(rightDigits.includes(-1), false, "خانة يمنى غير معروفة");

  return String(first) + leftDigits.join("") + rightDigits.join("");
};

test("مسح الرسم يُعيد الرقم نفسه — الرمز المرسوم قابل للقراءة فعلاً", () => {
  for (const code of ["4006381333931", "5901234123457", "2000000000008", "9780201379624"]) {
    for (const mw of [1.6, 2, 3]) {
      const svg = ean13Svg(code, { moduleWidth: mw, barHeight: 50, fontSize: 10 });
      assert.equal(scanSvg(svg, mw), code, `${code} @ ${mw}px`);
    }
  }
});

test("صفحة الملصقات تكرّر الملصق بعدد النسخ وتُسقط الباركود غير الصالح", () => {
  const html = barcodeLabelsHtml(
    [{ barcode: "4006381333931", name: "إطار 195/65/15", sku: "P-1", price: "250" }],
    3,
  );
  assert.equal((html.match(/class="label"/g) || []).length, 3);
  assert.match(html, /إطار 195\/65\/15/);
  assert.match(html, /250/);
  assert.equal(scanSvg(html, 2), "4006381333931");

  assert.equal(barcodeLabelsHtml([{ barcode: "4006381333930", name: "معطوب" }], 2), "");
  assert.equal(barcodeLabelsHtml([], 2), "");
  // عدد نسخ غير منطقي لا يُفجّر الطباعة
  assert.equal((barcodeLabelsHtml([{ barcode: "4006381333931", name: "x" }], 0).match(/class="label"/g) || []).length, 1);
  assert.equal((barcodeLabelsHtml([{ barcode: "4006381333931", name: "x" }], 9999).match(/class="label"/g) || []).length, 200);
});

test("اسم الصنف يُهرَّب فلا يكسر صفحة الطباعة", () => {
  const html = barcodeLabelsHtml([{ barcode: "4006381333931", name: '<script>x</script>&' }], 1);
  assert.equal(html.includes("<script>x</script>"), false);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&amp;/);
});

test("الرسم يُخرج SVG بعدد الأعمدة السوداء الصحيح ومناطق هدوء", () => {
  const code = "4006381333931";
  const svg = ean13Svg(code, { moduleWidth: 2, barHeight: 50, fontSize: 10 });
  const blackModules = ean13Modules(code).split("").filter((b) => b === "1").length;
  assert.equal((svg.match(/<rect /g) || []).length, blackModules + 1); // +1 خلفية بيضاء
  // العرض = (11 هدوء يسار + 95 + 7 هدوء يمين) × عرض الوحدة
  assert.match(svg, /width="226"/);
  assert.match(svg, /<svg /);
  assert.match(svg, new RegExp(`aria-label="باركود ${code}"`));
  // الأرقام المقروءة الثلاثة عشر تحت الرمز
  assert.equal((svg.match(/<text /g) || []).length, 13);
});
