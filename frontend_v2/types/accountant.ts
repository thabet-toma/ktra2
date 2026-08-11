export type AccountantVerificationStatus =
  | 'unverified'
  | 'pending_review'
  | 'verified'
  | 'rejected'
  | 'barred';

export type EngagementStatus =
  | 'pending'
  | 'active'
  | 'suspended'
  | 'revoked'
  | 'declined'
  | 'expired';

export interface AccountantProfile {
  id: number;
  user_id: number;
  full_name: string;
  email: string;
  account_type: string;
  professional_type: string;
  license_number: string;
  license_authority: string;
  tax_registration_number: string;
  business_address: string;
  phone: string;
  email_verified: boolean;
  verification_status: AccountantVerificationStatus;
  rejection_reason: string;
  barred_until: string | null;
}

export interface AccountantEngagement {
  id: number;
  accountant_id: number;
  accountant_name: string;
  accountant_email: string;
  tenant_id: number;
  company_name: string;
  status: EngagementStatus;
  initiated_by: 'accountant' | 'company';
  scope: string[];
  note: string;
  invitation_expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export type TaxPeriodStatus =
  | 'in_review'
  | 'needs_company_action'
  | 'ready'
  | 'approved'
  | 'submitted'
  | 'locked';

export interface WorkspaceCompany {
  engagement_id: number;
  tenant_id: number;
  company_name: string;
  status: EngagementStatus;
  accessible: boolean;
  open_queries: number;
  blockers: number;
  last_period: {
    id: number;
    period_from: string;
    period_to: string;
    status: TaxPeriodStatus;
  } | null;
}




export interface AccountantPermissionEntry {
  key: string;
  label: string;
  group: string;
}

