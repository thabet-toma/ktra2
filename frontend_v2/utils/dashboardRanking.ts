/**
 * خوارزمية فرز لوحة قيادة العمليات: الترتيب الأسوأ أولاً (م٦).
 *
 * للموظفين:
 * 1. عدد أوامر العمل المتأخرة تنازلياً (الأكثر تأخراً هو الأسوأ).
 * 2. عدد الشذوذات التشغيلية تنازلياً.
 * 3. مقدار الحمل الزائد فوق السعة المستهدفة تنازلياً.
 * 4. الدرجة المركبة للأداء تصاعدياً (الدرجة الأدنى هي الأسوأ).
 * 5. عدد أوامر العمل النشطة تنازلياً.
 *
 * للشركات:
 * 1. عدد أوامر العمل المتأخرة تنازلياً.
 * 2. عدد أوامر العمل النشطة تنازلياً.
 */

export interface PlatformDashboardEmployee {
  id: number;
  user_id?: number;
  name: string;
  username?: string;
  email?: string;
  specialty: string;
  /** رابطُ صورة الموظّف (211-Q) — فارغٌ يعني «أحرفٌ أولى» لا «لا موظّف». */
  photo_url?: string;
  /** عنوانُ العرض؛ منفصلٌ عن `specialty` المفتاحيّ عمداً. */
  job_title?: string;
  capacity_target: number;
  status: string;
  active_work_orders_count: number;
  overdue_work_orders_count: number;
  last_active_at: string | null;
  is_recently_active: boolean;
  is_active_now?: boolean;
  performance?: {
    status?: string;
    status_message?: string;
    composite_score?: number | null;
    sample_size?: number;
    min_sample_size?: number;
    rework_rate?: number;
    processed_sales_value?: number;
  } | null;
  anomalies_count?: number;
  anomalies?: any[];
  engaged_tenants_count?: number;
  companies?: { id: number; name: string }[];
}

export interface PlatformDashboardCompany {
  id: number;
  name: string;
  subscription_status: string;
  subscription_plan: string;
  active_work_orders_count: number;
  overdue_work_orders_count: number;
  assigned_employee?: {
    id: number;
    name: string;
    specialty: string;
  } | null;
}

export function sortEmployeesWorstFirst(
  employees: PlatformDashboardEmployee[]
): PlatformDashboardEmployee[] {
  // **نفسُ مفتاحِ الخادم بالترتيب نفسِه**: الخادمُ يرتّب بـ(الشذوذ، التأخّر، غيرُ
  // المرتَّبين، الدرجة)، وكان هذا يرتّب بـ(التأخّر، الشذوذ، …) فيقلب النتيجةَ التي
  // حسبها الخادم. قاعدةٌ واحدةٌ بتنفيذين متباعدين تعني أنّ ما يراه المستخدمُ يخالف
  // ما قرّره الخادمُ بلا أن يشتكيَ أحد. والخادمُ هو المرجع؛ وهذه لِما يُصفّى محلّياً.
  return [...employees].sort((a, b) => {
    // 1. عدد الشذوذات
    const anomaliesDiff = (b.anomalies_count || (b.anomalies ? b.anomalies.length : 0)) -
      (a.anomalies_count || (a.anomalies ? a.anomalies.length : 0));
    if (anomaliesDiff !== 0) {
      return anomaliesDiff;
    }

    // 2. الأوامر المتأخرة
    const overdueDiff = (b.overdue_work_orders_count || 0) - (a.overdue_work_orders_count || 0);
    if (overdueDiff !== 0) {
      return overdueDiff;
    }

    // 3. تجاوز السعة المستهدفة
    const overloadA = Math.max(0, (a.active_work_orders_count || 0) - (a.capacity_target || 0));
    const overloadB = Math.max(0, (b.active_work_orders_count || 0) - (b.capacity_target || 0));
    const overloadDiff = overloadB - overloadA;
    if (overloadDiff !== 0) {
      return overloadDiff;
    }

    // 4. الدرجة المركبة للأداء (الأدنى هو الأسوأ)
    const scoreA = a.performance?.composite_score;
    const scoreB = b.performance?.composite_score;
    if (typeof scoreA === 'number' && typeof scoreB === 'number') {
      if (scoreA !== scoreB) {
        return scoreA - scoreB;
      }
    } else if (typeof scoreA === 'number' && scoreB == null) {
      return -1; // الموظف ذو الدرجة المنخفضة أسوأ من الذي ليس له بيانات
    } else if (scoreA == null && typeof scoreB === 'number') {
      return 1;
    }

    // 5. الأوامر النشطة
    return (b.active_work_orders_count || 0) - (a.active_work_orders_count || 0);
  });
}

export function sortCompaniesWorstFirst(
  companies: PlatformDashboardCompany[]
): PlatformDashboardCompany[] {
  return [...companies].sort((a, b) => {
    // 1. الأوامر المتأخرة
    const overdueDiff = (b.overdue_work_orders_count || 0) - (a.overdue_work_orders_count || 0);
    if (overdueDiff !== 0) {
      return overdueDiff;
    }

    // 2. الأوامر النشطة
    return (b.active_work_orders_count || 0) - (a.active_work_orders_count || 0);
  });
}
