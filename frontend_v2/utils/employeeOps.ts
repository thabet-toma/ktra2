/**
 * دوال ومنطق وحدة متابعة الموظفين (employee_ops).
 * دوال خالصة لحراسة الترتيب والتصنيف والتسميات.
 */

export type DailyBucket = "overdue" | "today" | "later" | "undated";

/**
 * تصنيفُ المهمّة بالنسبة ليومٍ بعينه — تاريخٌ نصّيّ ISO أو فارغ.
 * حد التساوي (اليوم) يُصنّف "today" وليس "overdue".
 */
export function dailyBucket(
  dueDate: string | null | undefined,
  todayIso: string,
): DailyBucket {
  if (!dueDate) return "undated";
  const due = dueDate.trim().slice(0, 10);
  if (!due || due.length < 10) return "undated";
  const today = (todayIso || "").trim().slice(0, 10);
  if (!today || today.length < 10) return "undated";

  if (due < today) return "overdue";
  if (due === today) return "today";
  return "later";
}

const BUCKET_ORDER: Record<DailyBucket, number> = {
  overdue: 0,
  today: 1,
  later: 2,
  undated: 3,
};

/**
 * ترتيبُ شاشة «يومي»: **المتأخّرة أوّلاً · ثمّ ما يُستحقّ اليوم · ثمّ الباقي**،
 * وبلا موعدٍ في الآخر. وداخل كلّ مجموعة: الأقربُ موعداً أوّلاً، والمتساويةُ تبقى
 * على ترتيبها الوارد — ترتيبٌ **مستقرّ** لا يقلب المتساويات.
 */
export function sortDailyTasks<T extends { due_date?: string | null; id: number }>(
  tasks: T[],
  todayIso: string,
): T[] {
  return [...tasks].sort((a, b) => {
    const bucketA = dailyBucket(a.due_date, todayIso);
    const bucketB = dailyBucket(b.due_date, todayIso);

    const rankDiff = BUCKET_ORDER[bucketA] - BUCKET_ORDER[bucketB];
    if (rankDiff !== 0) {
      return rankDiff;
    }

    // داخل نفس المجموعة:
    if (bucketA === "undated" || bucketA === "today") {
      // متساويات الموعد — الترتيب مستقر
      return 0;
    }

    const dateA = (a.due_date ?? "").trim().slice(0, 10);
    const dateB = (b.due_date ?? "").trim().slice(0, 10);

    const dateDiff = dateA.localeCompare(dateB);
    if (dateDiff !== 0) {
      return dateDiff;
    }

    return 0;
  });
}

/** الحدُّ الأدنى الذي يلزم لفرز مهامّي — لا شكلَ `TaskDto` كاملاً. */
export interface DailySplitTask {
  id: number;
  due_date?: string | null;
  status?: string | null;
  my_assignment?: { status?: string | null } | null;
}

/**
 * فرزُ مهامّي في شاشة «يومي»: ما أعمل عليه، وما سلّمتُه وينتظر المدير.
 *
 * الحسمُ بحالة **إسنادي أنا** لا بحالة المهمّة: المهمّة متعدّدةُ الإسناد،
 * فحالتُها تصير `WAITING_FOR_REVIEW` بمجرّد أن يسلّم أيُّ زميل. ربطُ الدلو بها
 * كان يُخفي المهمّة من قائمتي ويسلبني زرَّ «سلّم» وأنا لم أبدأها.
 */
export function splitMyDailyTasks<T extends DailySplitTask>(
  tasks: T[],
  todayIso: string,
): { active: T[]; pending: T[] } {
  const active: T[] = [];
  const pending: T[] = [];
  for (const t of tasks) {
    const mine = t.my_assignment?.status;
    if (mine === "submitted") {
      pending.push(t);
    } else if (mine !== "completed" && t.status !== "COMPLETED") {
      active.push(t);
    }
  }
  return { active: sortDailyTasks(active, todayIso), pending };
}

/** تسميةُ بندِ الشريط تتبدّل بالصلاحية — لا تُكتب حرفياً في JSX. */
export function employeeOpsNavLabels(canManage: boolean): {
  daily: string;
  tasks: string; // "إدارة المهام" | "مهامي"
  people: string; // "الموظفون"
  points: string; // "إدارة النقاط" | "نقاطي"
} {
  return {
    daily: "يومي",
    tasks: canManage ? "إدارة المهام" : "مهامي",
    people: "الموظفون",
    points: canManage ? "إدارة النقاط" : "نقاطي",
  };
}

/** تسميات الأولويات */
export function taskPriorityLabel(priority: string | null | undefined): string {
  switch ((priority || "").toUpperCase()) {
    case "URGENT":
      return "حرجة";
    case "HIGH":
      return "عالية";
    case "LOW":
      return "منخفضة";
    case "MEDIUM":
    default:
      return "متوسطة";
  }
}

/** ألوان شارات الأولويات */
export function taskPriorityBadgeClass(priority: string | null | undefined): string {
  switch ((priority || "").toUpperCase()) {
    case "URGENT":
      return "bg-rose-100 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300 border-rose-200 dark:border-rose-900";
    case "HIGH":
      return "bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-900";
    case "LOW":
      return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200 dark:border-slate-700";
    case "MEDIUM":
    default:
      return "bg-blue-100 text-blue-800 dark:bg-blue-950/40 dark:text-blue-300 border-blue-200 dark:border-blue-900";
  }
}

/** تسميات قرارات المراجعة */
export function submissionDecisionLabel(decision: string | null | undefined): string {
  switch (decision) {
    case "approved_full":
      return "قبول كامل";
    case "approved_partial":
      return "قبول جزئي";
    case "rejected":
      return "مرفوض";
    case "pending":
    default:
      return "بانتظار المراجعة";
  }
}

/**
 * حالةُ **الإسناد** لا المهمّة: مفرداتُها صغيرةٌ (`not_started`…) ومختلفةٌ عن
 * مفردات `Task.status` الكبيرة. خلطُهما كان يطبع «not_started» للمستخدم.
 */
export function assignmentStatusLabel(status: string | null | undefined): string {
  switch ((status || "").toLowerCase()) {
    case "not_started":
      return "لم تبدأ";
    case "in_progress":
      return "قيد التنفيذ";
    case "submitted":
      return "سُلّمت — بانتظار المراجعة";
    case "completed":
      return "مكتملة";
    case "rejected":
      return "مرفوضة";
    default:
      return status || "غير محدد";
  }
}

/** تسميات حالات المهام */
export function taskStatusLabel(status: string | null | undefined): string {
  switch ((status || "").toUpperCase()) {
    case "NEW":
      return "جديدة";
    case "IN_PROGRESS":
      return "قيد التنفيذ";
    case "WAITING_FOR_REVIEW":
      return "بانتظار المراجعة";
    case "COMPLETED":
      return "مكتملة";
    case "REJECTED":
      return "مرفوضة";
    case "ACCEPTED":
      return "مقبولة";
    default:
      return status || "غير محدد";
  }
}
