import assert from "node:assert/strict";
import test from "node:test";

import {
  assignmentStatusLabel,
  dailyBucket,
  splitMyDailyTasks,
  employeeOpsNavLabels,
  sortDailyTasks,
  taskPriorityBadgeClass,
  taskPriorityLabel,
  taskStatusLabel,
  submissionDecisionLabel,
} from "./employeeOps.ts";
import { moduleAllowsView } from "./viewPermissions.ts";

test("dailyBucket: تصنيف التواريخ بالنسبة لليوم", () => {
  const today = "2026-09-09";

  // حد التساوي: موعد اليوم ليس متأخراً بل today
  assert.equal(dailyBucket("2026-09-09", today), "today");
  assert.equal(dailyBucket("2026-09-09T14:30:00Z", today), "today");

  // المتأخرة
  assert.equal(dailyBucket("2026-09-08", today), "overdue");
  assert.equal(dailyBucket("2026-08-01", today), "overdue");

  // اللاحقة
  assert.equal(dailyBucket("2026-09-10", today), "later");
  assert.equal(dailyBucket("2026-10-01", today), "later");

  // بلا موعد
  assert.equal(dailyBucket(null, today), "undated");
  assert.equal(dailyBucket(undefined, today), "undated");
  assert.equal(dailyBucket("", today), "undated");
  assert.equal(dailyBucket("   ", today), "undated");
  assert.equal(dailyBucket("invalid", today), "undated");
});

test("sortDailyTasks: المتأخّرة قبل ما يُستحقّ اليوم قبل الباقي — الاختبار رقم ٥ في المواصفة", () => {
  const today = "2026-09-09";

  const taskLater = { id: 1, due_date: "2026-09-15", title: "لاحقة" };
  const taskToday = { id: 2, due_date: "2026-09-09", title: "اليوم" };
  const taskOverdue = { id: 3, due_date: "2026-09-05", title: "متأخرة" };

  const sorted = sortDailyTasks([taskLater, taskToday, taskOverdue], today);

  assert.deepEqual(
    sorted.map((t) => t.id),
    [3, 2, 1],
    "يجب أن تأتي المتأخرة أولاً ثم اليوم ثم الباقي",
  );
});

test("sortDailyTasks: المهمّةُ بلا موعدٍ في الآخر لا في الأوّل", () => {
  const today = "2026-09-09";

  const taskUndated = { id: 10, due_date: null, title: "بلا موعد" };
  const taskOverdue = { id: 11, due_date: "2026-09-01", title: "متأخرة" };
  const taskToday = { id: 12, due_date: "2026-09-09", title: "اليوم" };
  const taskLater = { id: 13, due_date: "2026-09-20", title: "لاحقة" };

  const sorted = sortDailyTasks(
    [taskUndated, taskLater, taskToday, taskOverdue],
    today,
  );

  assert.deepEqual(
    sorted.map((t) => t.id),
    [11, 12, 13, 10],
    "المهمة بلا موعد تأتي في آخر القائمة دائماً",
  );
});

test("sortDailyTasks: موعدُ اليوم ليس متأخّراً (حدُّ التساوي)", () => {
  const today = "2026-09-09";

  const taskToday = { id: 21, due_date: "2026-09-09" };
  const taskOverdue = { id: 22, due_date: "2026-09-08" };

  const sorted = sortDailyTasks([taskToday, taskOverdue], today);

  assert.equal(sorted[0].id, 22, "المتأخرة تسبق مهمة اليوم");
  assert.equal(sorted[1].id, 21, "مهمة اليوم تلي المتأخرة");
});

test("sortDailyTasks: الترتيبُ مستقرٌّ — مهمّتان بنفس الموعد تبقيان بترتيبهما", () => {
  const today = "2026-09-09";

  const taskA = { id: 101, due_date: "2026-09-09", title: "أولى" };
  const taskB = { id: 102, due_date: "2026-09-09", title: "ثانية" };
  const taskC = { id: 103, due_date: "2026-09-09", title: "ثالثة" };

  const sorted = sortDailyTasks([taskA, taskB, taskC], today);

  assert.deepEqual(
    sorted.map((t) => t.id),
    [101, 102, 103],
    "يجب أن يبقى الترتيب الأصلي مستقراً عند تساوي الموعد",
  );

  // وكذلك لبلا موعد
  const unA = { id: 201, due_date: null };
  const unB = { id: 202, due_date: null };
  const sortedUndated = sortDailyTasks([unA, unB], today);
  assert.deepEqual(sortedUndated.map((t) => t.id), [201, 202]);
});

test("sortDailyTasks: داخل مجموعة اللاحقة الأقرب موعداً أولاً", () => {
  const today = "2026-09-09";

  const taskLater1 = { id: 301, due_date: "2026-09-20" };
  const taskLater2 = { id: 302, due_date: "2026-09-11" };
  const taskLater3 = { id: 303, due_date: "2026-09-15" };

  const sorted = sortDailyTasks([taskLater1, taskLater2, taskLater3], today);

  assert.deepEqual(
    sorted.map((t) => t.id),
    [302, 303, 301],
    "في اللاحقة الأقرب تاريخاً يأتي أولاً",
  );
});

test("employeeOpsNavLabels: التسمياتُ تنقلب بالصلاحية", () => {
  const managerLabels = employeeOpsNavLabels(true);
  assert.equal(managerLabels.daily, "يومي");
  assert.equal(managerLabels.tasks, "إدارة المهام");
  assert.equal(managerLabels.people, "الموظفون");
  assert.equal(managerLabels.points, "إدارة النقاط");

  const selfLabels = employeeOpsNavLabels(false);
  assert.equal(selfLabels.daily, "يومي");
  assert.equal(selfLabels.tasks, "مهامي");
  assert.equal(selfLabels.people, "الموظفون");
  assert.equal(selfLabels.points, "نقاطي");
});

test("تسميات وألوان الأولويات والحالات", () => {
  assert.equal(taskPriorityLabel("URGENT"), "حرجة");
  assert.equal(taskPriorityLabel("high"), "عالية");
  assert.equal(taskPriorityLabel("medium"), "متوسطة");
  assert.equal(taskPriorityLabel("low"), "منخفضة");

  assert.ok(taskPriorityBadgeClass("URGENT").includes("rose"));

  assert.equal(taskStatusLabel("NEW"), "جديدة");
  assert.equal(taskStatusLabel("IN_PROGRESS"), "قيد التنفيذ");
  assert.equal(taskStatusLabel("WAITING_FOR_REVIEW"), "بانتظار المراجعة");
  assert.equal(taskStatusLabel("COMPLETED"), "مكتملة");
  assert.equal(taskStatusLabel("REJECTED"), "مرفوضة");

  assert.equal(submissionDecisionLabel("approved_full"), "قبول كامل");
  assert.equal(submissionDecisionLabel("approved_partial"), "قبول جزئي");
  assert.equal(submissionDecisionLabel("rejected"), "مرفوض");
  assert.equal(submissionDecisionLabel("pending"), "بانتظار المراجعة");
});

test("ترخيص شاشات employee_ops عبر moduleAllowsView", () => {
  const views = [
    "employee-ops-daily",
    "employee-ops-tasks",
    "employee-ops-people",
    "employee-ops-points",
  ];

  // شركة غير مرخصة
  for (const v of views) {
    assert.equal(moduleAllowsView(v, {}), false, `${v} يجب أن تُحجب لشركة غير مرخصة`);
    assert.equal(moduleAllowsView(v, { employee_ops: false }), false);
    assert.equal(moduleAllowsView(v, null), false);
  }

  // شركة مرخصة
  for (const v of views) {
    assert.equal(moduleAllowsView(v, { employee_ops: true }), true, `${v} يجب أن تُتاح لشركة مرخصة`);
  }
});


test("حالةُ الإسناد لها قاموسُها: مفرداتُها الصغيرةُ لا تُطبع بالإنجليزيّة", () => {
  // `taskStatusLabel` تُطابق مفرداتِ **المهمّة** الكبيرة، فتمرّ مفرداتُ الإسناد
  // الصغيرةُ من فرعِها الافتراضيّ حرفيّةً. هذا ما يحرسه هذا الاختبار.
  assert.equal(assignmentStatusLabel("not_started"), "لم تبدأ");
  assert.equal(assignmentStatusLabel("in_progress"), "قيد التنفيذ");
  assert.equal(assignmentStatusLabel("submitted"), "سُلّمت — بانتظار المراجعة");
  assert.equal(assignmentStatusLabel("completed"), "مكتملة");
  assert.equal(assignmentStatusLabel("rejected"), "مرفوضة");

  for (const raw of ["not_started", "in_progress", "submitted"]) {
    assert.notEqual(
      assignmentStatusLabel(raw),
      raw,
      `«${raw}» يجب ألّا تصل إلى المستخدم كما هي`,
    );
  }
});

test("تسليمُ زميلٍ لا يسحب المهمّة من قائمتي ولا يسلبني زرّ «سلّم»", () => {
  // المهمّةُ متعدّدةُ الإسناد: حالتُها تصير WAITING_FOR_REVIEW بمجرّد أن يسلّم
  // **أيُّ** مُسنَدٍ إليه. فإن رُبط الدلوُ بحالة المهمّة سقط هذا الاختبار.
  const colleagueSubmitted = {
    id: 1,
    due_date: "2026-09-09",
    status: "WAITING_FOR_REVIEW",
    my_assignment: { status: "not_started" },
  };
  const { active, pending } = splitMyDailyTasks([colleagueSubmitted], "2026-09-09");

  assert.equal(active.length, 1, "المهمّة يجب أن تبقى في قائمتي النشطة");
  assert.equal(pending.length, 0);
  assert.equal(active[0].id, 1);
});

test("ما سلّمتُه أنا ينتقل إلى «بانتظار موافقة المدير»", () => {
  const mineSubmitted = {
    id: 2,
    due_date: null,
    status: "WAITING_FOR_REVIEW",
    my_assignment: { status: "submitted" },
  };
  const { active, pending } = splitMyDailyTasks([mineSubmitted], "2026-09-09");

  assert.equal(pending.length, 1);
  assert.equal(active.length, 0);
});

test("المكتملُ يختفي من الدلوين، والفرزُ يبقى: المتأخّرُ قبل اليوم قبل الباقي", () => {
  const tasks = [
    { id: 1, due_date: "2026-09-20", status: "NEW", my_assignment: { status: "not_started" } },
    { id: 2, due_date: "2026-09-01", status: "NEW", my_assignment: { status: "in_progress" } },
    { id: 3, due_date: "2026-09-09", status: "NEW", my_assignment: { status: "not_started" } },
    { id: 4, due_date: "2026-09-02", status: "COMPLETED", my_assignment: { status: "completed" } },
  ];
  const { active, pending } = splitMyDailyTasks(tasks, "2026-09-09");

  assert.equal(pending.length, 0);
  assert.deepEqual(
    active.map((t) => t.id),
    [2, 3, 1],
    "المتأخّرة (2) ثمّ ما يُستحقّ اليوم (3) ثمّ الباقي (1)، والمكتملة (4) خارجَهما",
  );
});

test("المرفوضُ يبقى في قائمتي كي أُعيد التسليم، وبلا إسنادٍ لا يُعرض دلوٌ خاطئ", () => {
  // الرفضُ يُعيد الإسنادَ إلى الطابور: إخراجُه من القائمة يحرم صاحبَه من إصلاحه.
  const rejected = {
    id: 5,
    due_date: "2026-09-10",
    status: "WAITING_FOR_REVIEW",
    my_assignment: { status: "rejected" },
  };
  // مهمّةٌ ليست إسناداً لي (المدير يقرأ عبر listTasks فيأتي my_assignment فارغاً)
  const notMine = { id: 6, due_date: "2026-09-10", status: "NEW", my_assignment: null };

  const { active, pending } = splitMyDailyTasks([rejected, notMine], "2026-09-09");
  assert.equal(pending.length, 0);
  assert.deepEqual(
    active.map((t) => t.id).sort(),
    [5, 6],
    "المرفوضُ يبقى نشطاً، وما لا إسنادَ لي فيه لا يُصنَّف «بانتظار المدير»",
  );
});
