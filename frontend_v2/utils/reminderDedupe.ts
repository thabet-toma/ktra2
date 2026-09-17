/**
 * C2-4 — منعُ تكرار إشعارات التذكير المولَّدة في المتصفّح
 * (`services/customerDormancyAlerts.ts` · `services/shipmentArrivalReminders.ts`
 * · `services/customerNoteReminders.ts`).
 *
 * العطب: كانت الخدمات الثلاث تفحص مفتاح `localStorage` ثمّ **تنتظر**
 * `addNotification` ثمّ تكتب المفتاح — فتشغيلان متزامنان (`App.tsx` يطلقها عند
 * تغيّر المستخدم/اعتماده/دوره، و`CustomerNotesTab` بعد حفظ ملاحظة) يمرّان كلاهما
 * من الفحص قبل أن يكتب أيٌّ منهما، فيتكرّر الإشعار.
 *
 * العلاج طبقتان مستقلّتان، كلٌّ منهما تكفي وحدها للتكرار داخل التبويب:
 * 1. `claimOnceAndRun`: المفتاحُ يُحجَز **قبل** الانتظار (قراءةٌ وكتابةٌ
 *    متزامنتان بلا `await` بينهما)، ويُحرَّر إن فشلت الكتابة فلا يُحرَق.
 * 2. `singleFlight`: تشغيلٌ واحدٌ جارٍ لكلّ خدمة — لا جلبَين متوازيين من الخادم.
 *
 * التوليدُ الخادميّ (مصدرٌ واحد لكلّ الأجهزة) قرارٌ لاحقٌ خارج هذا الإصلاح.
 */

/** ما يلزم من `Storage` — `localStorage` في المتصفّح، وخريطةٌ في الاختبار. */
export interface DedupeStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/**
 * يكتب الإشعار مرّةً واحدة لكلّ مفتاح. `true` إن كُتب، `false` إن سبق إعلانُه.
 * التخزينُ المحجوب (تصفّحٌ خاص) لا يمنع الإشعار — نفس سلوك الخدمات قبل الإصلاح.
 * فشلُ الكتابة يُحرِّر المفتاح ثمّ يُعاد رميُه كما هو.
 */
export async function claimOnceAndRun(
  getStore: () => DedupeStore,
  key: string,
  write: () => Promise<unknown>,
): Promise<boolean> {
  try {
    if (getStore().getItem(key)) return false;
  } catch {
    /* تخزينٌ محجوب */
  }
  // الحجزُ قبل أيّ انتظار — تشغيلٌ متزامنٌ آخر يرى المفتاح محجوزاً.
  try {
    getStore().setItem(key, "1");
  } catch {
    /* ignore */
  }
  try {
    await write();
  } catch (error) {
    try {
      getStore().removeItem(key);
    } catch {
      /* ignore */
    }
    throw error;
  }
  return true;
}

/**
 * تشغيلٌ واحدٌ جارٍ في آنٍ واحد. نداءٌ يصل أثناء تشغيلٍ جارٍ **لا يُبتلَع**: تُطوى
 * كلُّ النداءات المتراكمة في تشغيلٍ لاحقٍ واحد بعد انتهائه (بآخر وسائط) — وإلّا
 * لفات ما استجدّ أثناءه (ملاحظةٌ حُفظت للتوّ بتذكيرٍ اليوم) حتى الدورة التالية
 * بعد ست ساعات. فشلُ تشغيلٍ لا يُبقي الحارس مقفلاً.
 */
export function singleFlight<A extends unknown[]>(
  fn: (...args: A) => Promise<void>,
): (...args: A) => Promise<void> {
  let running: Promise<void> | null = null;
  let queued: Promise<void> | null = null;
  let queuedArgs: A | null = null;

  const start = (args: A): Promise<void> => {
    const current: Promise<void> = Promise.resolve()
      .then(() => fn(...args))
      .finally(() => {
        if (running === current) running = null;
      });
    running = current;
    return current;
  };

  return (...args: A): Promise<void> => {
    if (!running) return start(args);
    queuedArgs = args;
    if (!queued) {
      queued = running
        .catch(() => undefined)
        .then(() => {
          queued = null;
          const nextArgs = queuedArgs as A;
          queuedArgs = null;
          return running ?? start(nextArgs);
        });
    }
    return queued;
  };
}
