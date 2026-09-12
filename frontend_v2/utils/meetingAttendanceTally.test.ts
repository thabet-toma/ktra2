import test from 'node:test';
import assert from 'node:assert/strict';

import { tallyAttendance } from './meetingAttendanceTally.ts';

test('صاحبُ العذر المقبول ليس غائباً — والفرقُ هو ما فُصلت لأجله الحالات الخمس', () => {
  const rows = [
    { status: 'attended' as const },
    { status: 'absent' as const },
    { status: 'excused_accepted' as const },
    { status: 'excused_pending' as const },
    { status: 'excused_rejected' as const },
  ];
  const tally = tallyAttendance(rows);
  assert.equal(tally.total, 5);
  assert.equal(tally.attended, 1);
  // لو كان العدُّ `total - attended` لعاد ٤ — وهي التهمةُ التي تُنزّل درجةَ ثلاثةٍ
  // اعتذروا، أحدُهم بعذرٍ **قَبِلَه المديرُ بنفسه**.
  assert.equal(tally.absent, 1);
  assert.equal(tally.excusedAccepted, 1);
  assert.equal(tally.excusedPending, 1);
  assert.equal(tally.excusedRejected, 1);
});

test('المعلَّقُ لا يُحسب غياباً ولا حضوراً — لا حكمَ قبل البتّ', () => {
  const tally = tallyAttendance([
    { status: 'excused_pending' as const },
    { status: 'excused_pending' as const },
  ]);
  assert.equal(tally.absent, 0);
  assert.equal(tally.attended, 0);
  assert.equal(tally.excusedPending, 2);
});

test('الفئاتُ الخمس تجمع المدعوّين كلَّهم بلا فقدٍ ولا تكرار', () => {
  const rows = [
    { status: 'attended' as const },
    { status: 'attended' as const },
    { status: 'absent' as const },
    { status: 'excused_rejected' as const },
  ];
  const t = tallyAttendance(rows);
  assert.equal(
    t.attended + t.absent + t.excusedPending + t.excusedAccepted + t.excusedRejected,
    t.total,
  );
});

test('دفترٌ فارغ أو غائب يعطي أصفاراً لا NaN', () => {
  for (const input of [null, undefined, []]) {
    const t = tallyAttendance(input);
    assert.equal(t.total, 0);
    assert.equal(t.absent, 0);
    assert.equal(t.attended, 0);
  }
});
