import { test } from 'node:test';
import assert from 'node:assert/strict';
import { claimOnceAndRun, singleFlight, type DedupeStore } from './reminderDedupe.ts';

function memoryStore(): DedupeStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => { data.set(k, v); },
    removeItem: (k) => { data.delete(k); },
  };
}

const tick = () => new Promise<void>((r) => setTimeout(r, 5));

/** نفس شكل خدمات التذكير الثلاث: جلبٌ ثمّ حلقةٌ تكتب إشعاراً لكلّ صفٍّ لم يُعلَن. */
function makeReminderRun(store: DedupeStore, addNotification: (key: string) => Promise<void>) {
  return async (_userId: string) => {
    await tick(); // الجلب من الخادم
    for (const key of ['dormant:1:10', 'dormant:1:11']) {
      await claimOnceAndRun(() => store, key, () => addNotification(key));
    }
  };
}

test('تشغيلان متزامنان (بلا حارس التشغيل) ⇒ إشعارٌ واحد لكلّ مفتاح — الحجزُ قبل الانتظار', async () => {
  const store = memoryStore();
  const written: string[] = [];
  const run = makeReminderRun(store, async (key) => { await tick(); written.push(key); });
  await Promise.all([run('u1'), run('u1')]);
  assert.deepEqual(written.sort(), ['dormant:1:10', 'dormant:1:11']);
});

test('تشغيلان متزامنان عبر singleFlight ⇒ الجلبُ مرّة وإشعارٌ واحد لكلّ مفتاح', async () => {
  const store = memoryStore();
  const written: string[] = [];
  let fetches = 0;
  const inner = makeReminderRun(store, async (key) => { await tick(); written.push(key); });
  const guarded = singleFlight(async (userId: string) => { fetches += 1; await inner(userId); });
  const first = guarded('u1');
  const second = guarded('u1');
  await Promise.all([first, second]);
  assert.deepEqual(written.sort(), ['dormant:1:10', 'dormant:1:11']);
  // الثاني وصل أثناء الأوّل ⇒ تشغيلٌ لاحقٌ واحد بعده (لا يضيع ما استجدّ)، لا تشغيلان متوازيان.
  assert.equal(fetches, 2);
});

test('singleFlight: لا يجري تشغيلان في آنٍ واحد، والنداءات المتراكمة تُطوى في تشغيلٍ لاحقٍ واحد', async () => {
  let running = 0;
  let maxRunning = 0;
  let calls = 0;
  const guarded = singleFlight(async () => {
    calls += 1;
    running += 1;
    maxRunning = Math.max(maxRunning, running);
    await tick();
    running -= 1;
  });
  await Promise.all([guarded(), guarded(), guarded(), guarded()]);
  assert.equal(maxRunning, 1);
  assert.equal(calls, 2);
  await guarded();
  assert.equal(calls, 3);
});

test('singleFlight: فشلُ تشغيلٍ لا يُبقي الحارسَ مقفلاً', async () => {
  let calls = 0;
  const guarded = singleFlight(async () => {
    calls += 1;
    if (calls === 1) throw new Error('network');
  });
  await assert.rejects(guarded(), /network/);
  await guarded();
  assert.equal(calls, 2);
});

test('فشلُ كتابة الإشعار لا يحرق المفتاح — المحاولةُ التالية تكتبه', async () => {
  const store = memoryStore();
  let attempts = 0;
  const write = async () => {
    attempts += 1;
    if (attempts === 1) throw new Error('write failed');
  };
  await assert.rejects(claimOnceAndRun(() => store, 'k', write), /write failed/);
  assert.equal(store.data.has('k'), false);
  assert.equal(await claimOnceAndRun(() => store, 'k', write), true);
  assert.equal(store.data.get('k'), '1');
  assert.equal(await claimOnceAndRun(() => store, 'k', write), false);
  assert.equal(attempts, 2);
});

test('تخزينٌ محجوب (تصفّحٌ خاص) ⇒ يُكتب الإشعار ولا يسقط', async () => {
  let written = 0;
  const blocked = () => { throw new Error('SecurityError'); };
  assert.equal(await claimOnceAndRun(blocked, 'k', async () => { written += 1; }), true);
  assert.equal(written, 1);
});
