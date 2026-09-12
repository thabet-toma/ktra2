/**
 * عميلُ واجهة برمجة تطبيقات مساحة موظّف الإدخال (التذكرة 210-E، §١).
 *
 * `GET /api/platform/ops/employees/` بلا مستدعٍ سلفاً — هي بوّابةُ تعريف الموظّف
 * بنفسه (تُرجِع صفَّه وحدَه لغير المدير، `get_queryset` في `PlatformEmployeeViewSet`)،
 * لا بابَ مديرٍ ميّت.
 */
import { apiGetObject } from "./restApi";

export type PlatformEmployeeStatus = "active" | "on_leave" | "offboarded";

export interface MyPlatformEmployeeProfile {
  id: number;
  user: number;
  username: string;
  email: string;
  specialty: string;
  capacity_target: string;
  status: PlatformEmployeeStatus;
  created_at: string;
  updated_at: string;
}

const unwrapRows = <T>(data: { results: T[]; count?: number } | T[]): T[] =>
  Array.isArray(data) ? data : data?.results || [];

/**
 * صفُّ الموظّفِ **المطابقُ للمستخدم الحاليّ** من `/employees/`.
 *
 * **ولا يُؤخذ `rows[0]` أبداً**: `PlatformEmployeeViewSet.get_queryset` يضيّق على
 * `user=request.user` لغيرِ المدير وحدَه — أمّا مديرُ العمليات فيعود له **كلُّ**
 * الموظفين مرتَّبين بـ`-created_at`. فلو أخذنا الأوّلَ لقرأ المديرُ محفظةَ زميلٍ
 * عشوائيٍّ تحت عنوان «محفظتي». العزلُ الخادميُّ سليم، والهويّةُ هي ما كان يَضيع.
 *
 * وحين لا صفَّ للمستخدم (مديرٌ بلا `PlatformEmployee`) تعود `null` فتعرض الشاشةُ
 * «لا يوجد ملفُّ موظّف منصّةٍ مرتبطٌ بحسابك» — وهو الجوابُ الصحيح لا محفظةُ غيرِه.
 */
export const getMyPlatformEmployeeProfile = async (
  currentUserId: string | number | undefined,
): Promise<MyPlatformEmployeeProfile | null> => {
  if (currentUserId === undefined || currentUserId === null || currentUserId === "") return null;
  const rows = unwrapRows(
    await apiGetObject<{ results: MyPlatformEmployeeProfile[]; count?: number } | MyPlatformEmployeeProfile[]>(
      "platform/ops/employees/",
    ),
  );
  return rows.find((row) => String(row.user) === String(currentUserId)) ?? null;
};
