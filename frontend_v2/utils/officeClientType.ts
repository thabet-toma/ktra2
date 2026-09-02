/**
 * ISSUE #52 — نوع زبون المكتب: مشتقٌّ من حقلين اختياريين لا حقل حالة ثالث.
 *
 * مرآة `accountant_portal.models.PracticeClient.client_type`: الزبون قد يُربَط
 * بدفتر مُدار يفتحه المكتب له (`managed_tenant`) و/أو بارتباط شركة قائمة على
 * المنصة بإذنها (`engagement`) — والقيمتان مستقلتان فلا نخزّن نوعاً ثالثاً
 * يمكن أن يناقضهما، بل نشتقّه هنا كما يُشتقّ في الخادم.
 */

export type OfficeClientType = 'managed' | 'engaged' | 'hybrid' | 'unlinked';

export function deriveOfficeClientType(
  managedTenantId: number | null | undefined,
  engagementId: number | null | undefined,
): OfficeClientType {
  const hasManaged = managedTenantId != null;
  const hasEngagement = engagementId != null;
  if (hasManaged && hasEngagement) return 'hybrid';
  if (hasManaged) return 'managed';
  if (hasEngagement) return 'engaged';
  return 'unlinked';
}
