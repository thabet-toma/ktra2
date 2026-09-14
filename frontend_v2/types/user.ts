
/**
 * مفردتان تلتقيان هنا:
 *  - أدوارُ التطبيق القديم التي يعيدها `hr/auth_api.py` للمستخدم الحالي
 *    (`manager` · `employee` · `procurement` · `legal_accountant` · `store_guest`).
 *  - أدوارُ عضوية الشركة كما هي في `tenants.models` (`ROLE_CHOICES`) — وهي
 *    ما تحمله صفوفُ «إدارة المستخدمين» منذ أن صارت تقرأ أعضاءَ الشركة.
 *
 * لا سحقَ بين المفردتين: `employee` لا وجودَ له في العضوية، وسحقُ
 * `accountant`/`sales`/`procurement`/`staff` إليه كان يُخفيها عن الفلاتر.
 * التصنيفُ في `utils/memberRoles.ts`، والتسميةُ في `utils/userRoleLabel.ts` وحدَه.
 */
export type UserRole =
    | 'manager' | 'employee' | 'procurement' | 'legal_accountant' | 'store_guest'
    | 'accountant' | 'sales' | 'staff' | 'ess' | 'field_staff' | 'viewer';

export interface PointsSystem {
    activityPointsPerClick: number;
    taskPointsFast: number;
    taskPointsNormal: number;
    maxActivityPointsPerDay: number;
}

export interface ActivityStatus {
    userId: string;
    lastCheckIn: string;
    activeMinutesToday: number;
    checkinClickCount: number;
    isCurrentlyActive: boolean;
    checkInButtonEnabled: boolean;
    lastActivityCheck: string;
    dailyDisableStartTime?: string;
    dailyDisableEndTime?: string;
    dailyDisableEnabled?: boolean;
    useGlobalSettings?: boolean;
}

export interface DailyPoints {
    date: string;
    userId: string;
    workMinutes: number;
    activityPoints: number;
    taskPoints: number;
    attendancePoints: number;
    totalPoints: number;
    checkinClicks: number;
    completedTasks: number;
    attended: boolean;
}

export interface PointsHistory {
    [date: string]: DailyPoints;
}

export interface User {
    id: string;
    name: string;
    role: UserRole;
    email: string;
    /** لا مصدرَ له في الخادم (`member_payload` لا يحمله) — يغيب عن أعضاء الشركة. */
    employmentStatus?: string;
    phone?: string;
    address?: string;
    isApproved: boolean;
    /** غيابُه «غير معروف» لا «غير مفعَّل» — لا تُظهر تحذيراً على المجهول. */
    isEmailVerified?: boolean;
    createdAt?: string;
    experienceDescription?: string;
    educationLevel?: string;
    resumeData?: {
        name: string;
        type: string;
        url: string;
    };
    notes?: string;
    pointsSystem?: PointsSystem;
    totalPoints?: number;
    currentDailyPoints?: DailyPoints;
    checkInButtonEnabled?: boolean;
    /** سوبر أدمن المنصة — يتحكم بتفعيل الاستيراد لكل شركة */
    isSuperAdmin?: boolean;
    /** صلاحية وحدة الاستيراد (إخفاء القائمة وقسم تكاليف الاستيراد) — الإنفاذ الموثوق على الخادم */
    canAccessImport?: boolean;
    /** نوع الهوية العامة؛ مستقل عن دور العضوية في الشركة النشطة. */
    accountType?: 'legal_accountant' | '';
}

export interface AttendanceSession {
    id: string;
    date: string;
    startTime: string;
    endTime?: string;
    isActive: boolean;
    createdBy: string;
    attendees: string[];
    autoEndTimeout?: NodeJS.Timeout;
}

export interface AttendanceRecord {
    id: string;
    userId: string;
    sessionId: string;
    date: string;
    attendedAt: string;
    points: number;
    status: 'present' | 'absent';
}

export interface GlobalDisableSettings {
    startTime: string;
    endTime: string;
    isEnabled: boolean;
    lastUpdatedBy?: string;
    lastUpdatedAt?: string;
}
