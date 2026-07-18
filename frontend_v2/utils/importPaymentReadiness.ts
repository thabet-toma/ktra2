export interface UnpaidImportDeal {
  dealId: string;
  dealRef: string;
  unpaidUsd: number;
}

export function getUnpaidImportDeals(
  preview: Record<string, unknown> | null,
): UnpaidImportDeal[] {
  if (!preview || !Array.isArray(preview.deals)) return [];
  return preview.deals.flatMap((raw) => {
    if (!raw || typeof raw !== "object") return [];
    const row = raw as Record<string, unknown>;
    const unpaidUsd = Number(row.deal_unpaid_usd);
    if (!Number.isFinite(unpaidUsd) || unpaidUsd <= 0.02) return [];
    const dealId = String(row.deal_id ?? "");
    return [{
      dealId,
      dealRef: String(row.ref_number || (dealId ? `#${dealId}` : "—")),
      unpaidUsd,
    }];
  });
}
