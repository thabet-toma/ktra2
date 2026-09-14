import assert from 'node:assert/strict';
import test from 'node:test';

import {
  arabicDayCount,
  contactRecencyLabel,
  leadAttentionBadge,
  leadAttentionLevel,
  STALL_ALERT_DAYS,
  STALL_WATCH_DAYS,
  type LeadAttentionInput,
} from './leadContactStats.ts';

const base: LeadAttentionInput = {
  contact_attempts: 3,
  days_since_last_contact: 1,
  days_in_status: 1,
  age_days: 3,
  follow_up_state: 'upcoming',
};

test('عددُ الأيّام يُنطَق مثنّىً وجمعَ قلّةٍ وتمييزاً منصوباً', () => {
  assert.equal(arabicDayCount(1), 'يوم واحد');
  assert.equal(arabicDayCount(2), 'يومين');
  assert.equal(arabicDayCount(5), '5 أيّام');
  assert.equal(arabicDayCount(15), '15 يوماً');
});

test('«لم يُسجَّل تواصلٌ بعد» ليست «اليوم» — والفرقُ هو كلُّ المعنى', () => {
  assert.equal(contactRecencyLabel(null), 'لم يُسجَّل تواصلٌ بعد');
  assert.equal(contactRecencyLabel(0), 'اليوم');
  assert.equal(contactRecencyLabel(1), 'أمس');
  assert.equal(contactRecencyLabel(4), 'منذ 4 أيّام');
});

test('متابعةٌ فات موعدُها إنذارٌ بذاتها ولو كُلِّم الرقمُ اليوم', () => {
  assert.equal(
    leadAttentionLevel({ ...base, days_since_last_contact: 0, follow_up_state: 'overdue' }),
    'stalled',
  );
});

test('الصمتُ يدقّ الجرس: أسبوعٌ نظرةٌ وأسبوعان إنذار', () => {
  assert.equal(leadAttentionLevel({ ...base, days_since_last_contact: STALL_WATCH_DAYS - 1 }), 'ok');
  assert.equal(leadAttentionLevel({ ...base, days_since_last_contact: STALL_WATCH_DAYS }), 'watch');
  assert.equal(leadAttentionLevel({ ...base, days_since_last_contact: STALL_ALERT_DAYS }), 'stalled');
});

test('طولُ المرحلة وحدَه لا يُنذر — صاحبُه يعمل عليه', () => {
  // رقمٌ كُلِّم أمسِ وهو في «مهتمّ» منذ شهرٍ يستحقّ نظرةً لا إنذاراً.
  assert.equal(leadAttentionLevel({ ...base, days_in_status: 30 }), 'watch');
});

test('رقمٌ لم يُكلَّم قطّ يُقاس صمتُه بعمره لا يُحسَب هادئاً', () => {
  const never = { ...base, days_since_last_contact: null, contact_attempts: 0 };
  assert.equal(leadAttentionLevel({ ...never, age_days: 1 }), 'ok');
  assert.equal(leadAttentionLevel({ ...never, age_days: STALL_ALERT_DAYS + 1 }), 'stalled');
});

test('الشارةُ تسمّي سببَ الإنذار: فواتُ الموعد غيرُ الركود', () => {
  const late = leadAttentionBadge({ ...base, follow_up_state: 'overdue' });
  const silent = leadAttentionBadge({ ...base, days_since_last_contact: 40 });
  assert.equal(late.level, 'stalled');
  assert.equal(silent.level, 'stalled');
  assert.notEqual(late.label, silent.label);
});

test('لكلّ درجةٍ طبقةُ لونٍ خاصّةٌ بها — ولا تكرار', () => {
  const classes = [
    leadAttentionBadge(base).className,
    leadAttentionBadge({ ...base, days_since_last_contact: STALL_WATCH_DAYS }).className,
    leadAttentionBadge({ ...base, days_since_last_contact: STALL_ALERT_DAYS }).className,
  ];
  assert.equal(new Set(classes).size, 3);
});
