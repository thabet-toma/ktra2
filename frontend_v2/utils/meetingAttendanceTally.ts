/**
 * عدُّ دفتر حضور الاجتماع بحالاته الخمس (#211 م٢، 211-G).
 *
 * **الغائبُ من لم يحضر ولم يعتذر — لا «كلُّ من لم يحضر».** طرحُ الحاضرين من
 * المدعوّين (`total - attended`) يلصق صفةَ الغياب بصاحب العذر **المقبول** وبمن
 * لم يُبتَّ في عذره بعد، وهو بعينه الخلطُ الذي فُصلت لأجله الحالاتُ الخمس في
 * 211-E: عذرٌ بوليانيٌّ واحدٌ كان يُنزّل درجةَ من لم يُحكَم في عذره — عقوبةٌ قبل
 * الحكم. والحضورُ يرفع الدرجةَ ويُنزّلها بقرار المالك، فرقمٌ يجمع الفئاتِ ليس
 * تبسيطاً بل خطأٌ يدخل في تسعير راتب.
 *
 * ودالّةٌ خالصةٌ لا حسابٌ داخل المكوّن: `npm test` هنا لا يُصيّر مكوّناً، فمنطقٌ
 * يسكن `useMemo` لا يفحصه شيء.
 */

export type MeetingAttendanceStatusKey =
  | "attended"
  | "absent"
  | "excused_pending"
  | "excused_accepted"
  | "excused_rejected";

export interface AttendanceTally {
  /** مجموعُ المدعوّين — صفُّ حضورٍ لكلّ مدعوٍّ يُنشأ سلفاً (211-E). */
  total: number;
  attended: number;
  /** «غاب» الحقيقيّ: `absent` وحدَها، بلا أصحاب الأعذار. */
  absent: number;
  excusedPending: number;
  excusedAccepted: number;
  excusedRejected: number;
}

const EMPTY: AttendanceTally = {
  total: 0,
  attended: 0,
  absent: 0,
  excusedPending: 0,
  excusedAccepted: 0,
  excusedRejected: 0,
};

export function tallyAttendance(
  rows: readonly { status: MeetingAttendanceStatusKey }[] | null | undefined,
): AttendanceTally {
  if (!rows || rows.length === 0) return { ...EMPTY };
  const count = (status: MeetingAttendanceStatusKey) =>
    rows.filter((row) => row.status === status).length;
  return {
    total: rows.length,
    attended: count("attended"),
    absent: count("absent"),
    excusedPending: count("excused_pending"),
    excusedAccepted: count("excused_accepted"),
    excusedRejected: count("excused_rejected"),
  };
}
