export type TenantOwnedOfflineRecord = { tenant_id?: number | null };

export function isOfflineRecordForTenant(
  record: TenantOwnedOfflineRecord,
  tenantId: number,
): boolean {
  return Number(record.tenant_id) === tenantId;
}

export function tenantScopedOfflineKey(tenantId: number, key: string): string {
  return `${tenantId}:${key}`;
}
