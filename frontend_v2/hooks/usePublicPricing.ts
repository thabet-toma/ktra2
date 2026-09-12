/**
 * 211-N/O: تحميلٌ مشتركٌ لحمولة `/api/pricing/plans/` — تستهلكه صفحةُ الأسعار
 * وقسمُ الهبوط وكرتُ «خطّتي»، فلا يتكرّر منطقُ الجلب وحالتا التحميل والفشل
 * ثلاثَ مرّات. `data` تبقى `null` أثناء التحميل وبعد الفشل — لا صفراً يُعرض
 * سعراً كاذباً لحظةً واحدة.
 */
import { useEffect, useState } from 'react';
import { fetchPublicPricing, type PublicPricingResponse } from '../services/pricingApi.ts';

export interface UsePublicPricingResult {
  data: PublicPricingResponse | null;
  loading: boolean;
  error: string | null;
}

export function usePublicPricing(): UsePublicPricingResult {
  const [data, setData] = useState<PublicPricingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fetchPublicPricing()
      .then((res) => { if (alive) setData(res); })
      .catch(() => { if (alive) setError('تعذّر تحميل الأسعار. حاول مرّة أخرى.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  return { data, loading, error };
}
