/**
 * task11 M2 — هوية الشركة النشطة (الاسم/الشعار/العنوان/التواصل).
 * يقرأ tenants/settings/current/ للشركة النشطة (X-Tenant-Id من resolveTenantId)
 * حتى تتغير معلومات الشركة ديناميكياً في كل الصفحات عند التبديل.
 */
import { useEffect, useState } from "react";
import { apiGetObject } from "../services/restApi";
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

export function useTenantSettings(): {
  identity: TenantIdentity | null;
  loading: boolean;
} {
  const [identity, setIdentity] = useState<TenantIdentity | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    apiGetObject<TenantIdentity>("tenants/settings/current/", {
      tenantId: resolveTenantId(),
    })
      .then((s) => {
        if (alive) setIdentity(s);
      })
      .catch(() => {
        if (alive) setIdentity(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { identity, loading };
}
