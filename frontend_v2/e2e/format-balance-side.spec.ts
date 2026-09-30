import { test, expect } from "@playwright/test";
import { formatBalanceWithSide, formatMoney, formatPartyBalance } from "../utils/formatNumber";

/**
 * شكوى المالك الأولى: «مش واضح آخر رقم دائن ولا مدين» — والثانية (#33/#69): «لازم
 * ينكتب بحدو دائن ولا مدين والمدين سالب». الإشارة والكلمة معاً، والرقم في عزلٍ
 * اتّجاهيّ LTR كي لا يرسم RTL السالبَ في آخره («1,112-»). الحارس الأصليّ في
 * `utils/formatNumber.test.ts` (يعمل في `npm test`)؛ هذا مرآته في Playwright.
 */
const iso = (s: string) => `\u2066${s}\u2069`;

test.describe("formatBalanceWithSide", () => {
  test("المدين سالب ومسمّى، والدائن موجب ومسمّى", () => {
    expect(formatBalanceWithSide(1888)).toBe(`${iso("-1,888")} مدين`);
    expect(formatBalanceWithSide(-1112)).toBe(`${iso("1,112")} دائن`);
  });

  test("الصفر بلا جانب", () => {
    expect(formatBalanceWithSide(0)).toBe("0");
    expect(formatBalanceWithSide(-0)).toBe("0");
    expect(formatBalanceWithSide(0.001)).toBe("0");
  });

  test("المدخل غير الصالح يعيد الافتراضي", () => {
    expect(formatBalanceWithSide(null)).toBe("0");
    expect(formatBalanceWithSide("abc")).toBe("0");
    expect(formatMoney(1112)).toBe("1,112");
  });

  test("رصيد الطرف بإشارة الخادم يصل إلى القاعدة نفسها", () => {
    expect(formatPartyBalance("9000", false)).toBe(`${iso("-9,000")} مدين`);
    expect(formatPartyBalance("7551.5", true)).toBe(`${iso("7,551.5")} دائن`);
  });
});
