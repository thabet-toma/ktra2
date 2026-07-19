import { test, expect } from "@playwright/test";
import { formatBalanceWithSide, formatMoney } from "../utils/formatNumber";

/**
 * شكوى المالك: «مش واضح آخر رقم دائن ولا مدين» — الأستاذ العام كان يعرض
 * «1,112-» والإشارة تُرسم في نهاية الرقم بصرياً في RTL فتلتبس.
 */
test.describe("formatBalanceWithSide", () => {
  test("يسمّي الجانب صراحةً بدل الإشارة", () => {
    expect(formatBalanceWithSide(1888)).toBe("1,888 مدين");
    expect(formatBalanceWithSide(-1112)).toBe("1,112 دائن");
  });

  test("لا يُبقي أي إشارة سالبة في المخرجات", () => {
    expect(formatBalanceWithSide(-1112)).not.toContain("-");
    expect(formatBalanceWithSide(-0.5)).not.toContain("-");
  });

  test("الصفر بلا جانب", () => {
    expect(formatBalanceWithSide(0)).toBe("0");
    expect(formatBalanceWithSide(-0)).toBe("0");
    expect(formatBalanceWithSide(0.001)).toBe("0");
  });

  test("يحافظ على تنسيق G1 (بلا أصفار عشرية غير دالّة)", () => {
    expect(formatBalanceWithSide(2000)).toBe("2,000 مدين");
    expect(formatBalanceWithSide(-187.5)).toBe("187.5 دائن");
    expect(formatBalanceWithSide(1234.56)).toBe("1,234.56 مدين");
  });

  test("المدخل غير الصالح يعيد الافتراضي", () => {
    expect(formatBalanceWithSide(null)).toBe("0");
    expect(formatBalanceWithSide(undefined)).toBe("0");
    expect(formatBalanceWithSide("")).toBe("0");
    expect(formatBalanceWithSide("abc")).toBe("0");
  });

  test("يقبل النص الرقمي كما يفعل formatMoney", () => {
    expect(formatBalanceWithSide("-1112")).toBe("1,112 دائن");
    expect(formatMoney(1112)).toBe("1,112");
  });
});
