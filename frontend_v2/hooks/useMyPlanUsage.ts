/**
 * حمولةُ «خطّتي» — حدودُ الشركة الفعّالة واستهلاكُها (`/api/my-plan/usage/`).
 *
 * **تُعاد القراءةُ عند تبديل الشركة**: المستخدمُ قد يكون عضواً في أكثرَ من
 * شركة، وبطاقةٌ تبقى على أرقام الشركة السابقة بعد التبديل هي أسوأُ من بطاقةٍ
 * فارغة — رقمٌ صحيحُ الشكل خاطئُ الصاحب لا يُشكّ فيه.
 *
 * و`data` تبقى `null` أثناء التحميل وبعد الفشل: لا صفراً يُعرض «لم تستهلك شيئاً»
 * لحظةً واحدة، والبطاقةُ تسقط عندها إلى حدود الخطّة العامّة بلا شريط.
 */
import { useEffect, useState } from 'react';
import { fetchMyPlanUsage, type MyPlanUsageResponse } from '../services/pricingApi.ts';

export interface UseMyPlanUsageResult {
  data: MyPlanUsageResponse | null;
  loading: boolean;
  error: string | null;
}

export function useMyPlanUsage(tenantId?: number | string | null): UseMyPlanUsageResult {
  const [data, setData] = useState<MyPlanUsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (tenantId === null || tenantId === undefined) {
      setData(null);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    setData(null);
    fetchMyPlanUsage()
      .then((res) => { if (alive) setData(res); })
      .catch(() => { if (alive) setError('تعذّر تحميل استهلاك خطّتك.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [tenantId]);

  return { data, loading, error };
}
