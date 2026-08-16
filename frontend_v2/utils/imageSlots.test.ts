import test from "node:test";
import assert from "node:assert/strict";
// الامتداد صريح: هذا الملف مُختبَر بـ`node --test` الذي لا يحلّ الاستيراد بلا امتداد.
import { fillFirstEmptySlots } from "./imageSlots.ts";

const EMPTY_THREE = ["", "", ""];

test("لصقة واحدة تملأ أول خانة فارغة", () => {
  assert.deepEqual(fillFirstEmptySlots(EMPTY_THREE, ["a"]), {
    assignments: [{ index: 0, file: "a" }],
    dropped: 0,
  });
});

test("أول خانة فارغة ليست بالضرورة الأولى", () => {
  assert.deepEqual(fillFirstEmptySlots(["u0", "", "u2"], ["a"]), {
    assignments: [{ index: 1, file: "a" }],
    dropped: 0,
  });
});

test("خانة بمسافات بيضاء تُعدّ فارغة — هكذا يُحفظ الصنف اليوم", () => {
  assert.deepEqual(fillFirstEmptySlots(["  ", "u1", "u2"], ["a"]), {
    assignments: [{ index: 0, file: "a" }],
    dropped: 0,
  });
});

test("N ملفات تملأ الخانات الفارغة التالية بالترتيب", () => {
  assert.deepEqual(fillFirstEmptySlots(["u0", "", ""], ["a", "b"]), {
    assignments: [
      { index: 1, file: "a" },
      { index: 2, file: "b" },
    ],
    dropped: 0,
  });
});

test("ما يتجاوز الخانات الثلاث يُهمَل ويُعاد عدده للرسالة", () => {
  assert.deepEqual(fillFirstEmptySlots(EMPTY_THREE, ["a", "b", "c", "d", "e"]), {
    assignments: [
      { index: 0, file: "a" },
      { index: 1, file: "b" },
      { index: 2, file: "c" },
    ],
    dropped: 2,
  });
});

test("لا خانة فارغة ← لا إسناد، وكل الملفات مُهمَلة", () => {
  assert.deepEqual(fillFirstEmptySlots(["u0", "u1", "u2"], ["a"]), {
    assignments: [],
    dropped: 1,
  });
});

test("قائمة خانات أقصر من ثلاث تبقى بطولها — لا تُخترع خانة رابعة", () => {
  assert.deepEqual(fillFirstEmptySlots(["", ""], ["a", "b", "c"]), {
    assignments: [
      { index: 0, file: "a" },
      { index: 1, file: "b" },
    ],
    dropped: 1,
  });
});

test("بلا ملفات ← لا شيء", () => {
  assert.deepEqual(fillFirstEmptySlots(EMPTY_THREE, []), { assignments: [], dropped: 0 });
});
