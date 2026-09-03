/**
 * task11 M2 — هوية الشركة النشطة (الاسم/الشعار/العنوان/التواصل).
 * يقرأ tenants/settings/current/ للشركة النشطة (X-Tenant-Id من resolveTenantId)
 * حتى تتغير معلومات الشركة ديناميكياً في كل الصفحات عند التبديل.
 */
import { useEffect, useState } from "react";
import { getTenantSettings } from "../services/tenantSettingsApi";
import { resolveTenantId } from "../utils/tenantContext";

export interface TenantIdentity {
  company_name_primary?: string | null;
  company_name_sub?: string | null;
  address?: string | null;
  po_box?: string | null;
  phone?: string | null;
  fax?: string | null;
  email?: string | null;
  logo_url?: string | null;
}

/**
 * تفضيلاتُ الشركة التي تقرأها شاشاتٌ غير شاشة الهوية. تُقرأ من **نفس** ردّ
 * `settings/current/` الذي يجلبه هذا الخطّاف أصلاً — لا نداء ثانٍ لحقلٍ واحد.
 */
export interface TenantPreferences {
  /** `free` | `linked` — انظر `utils/voucherAccountEntryMode.ts`. */
  voucher_account_entry_mode?: string | null;
}

export function useTenantSettings(): {
  identity: TenantIdentity | null;
  preferences: TenantPreferences | null;
  loading: boolean;
} {
  const [identity, setIdentity] = useState<TenantIdentity | null>(null);
  const [preferences, setPreferences] = useState<TenantPreferences | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    // P2-9: الشريط الجانبي ومبدّل الشركات يركّبان هذا الخطّاف معاً عند الإقلاع؛
    // المصدر المشترك يجعلهما طلباً واحداً بدل اثنين.
    getTenantSettings<TenantIdentity & TenantPreferences>(resolveTenantId())
      .then((s) => {
        if (!alive) return;
        setIdentity(s);
        setPreferences(s);
      })
      .catch(() => {
        if (!alive) return;
        setIdentity(null);
        setPreferences(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { identity, preferences, loading };
}
