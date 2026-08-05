import type {
  AccountantEngagement,
  AccountantPermissionEntry,
  AccountantProfile,
  WorkspaceCompany,
} from '../types/accountant';
import { apiGetObject, apiPatchObject, apiPostForBlob, apiPostObject } from './restApi';

export type AccountantSignupInput = {
  fullName: string;
  email: string;
  password: string;
  professional_type: string;
  tax_registration_number: string;
  business_address: string;
  license_number?: string;
  license_authority?: string;
  phone?: string;
};

export const signupAccountant = (body: AccountantSignupInput) =>
  apiPostObject<{ accepted: boolean; email_verification_required: boolean }>(
    'accountant/signup/', body,
  );

export const verifyAccountantEmail = (token: string) =>
  apiPostObject<{ verified: boolean }>('accountant/verify-email/', { token });

export const resendAccountantVerification = (email: string) =>
  apiPostObject<{ accepted: boolean }>('accountant/resend-verification/', { email });

export const getAccountantProfile = () =>
  apiGetObject<{ profile: AccountantProfile }>('accountant/me/');

export const updateAccountantProfile = (body: Partial<AccountantProfile>) =>
  apiPatchObject<{ profile: AccountantProfile }>('accountant/me/', body);

export const submitAccountantProfile = () =>
  apiPostObject<{ status: string }>('accountant/me/submit-verification/', {});

/** بحث بالاسم المسجَّل تماماً — لا قائمة ولا بحث جزئي (منع تعداد الشركات). */
export const lookupCompanyForEngagement = (query: string) =>
  apiGetObject<{
    company: { tenant_id: number; company_name: string; engagement_status: string };
  }>(`accountant/companies/lookup/?q=${encodeURIComponent(query)}`);

export const requestAccountantEngagement = (tenantId: number, note: string) =>
  apiPostObject<{ engagement: AccountantEngagement }>('accountant/engagements/request/', {
    tenant_id: tenantId,
    note,
  });

export const acceptAccountantInvitation = (token: string) =>
  apiPostObject<{ engagement: AccountantEngagement }>('accountant/engagements/accept-invite/', { token });

export const listWorkspaceCompanies = (params: {
  search?: string;
  status?: string;
  page?: number;
  pageSize?: number;
} = {}) => {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  if (params.status) query.set('status', params.status);
  if (params.page) query.set('page', String(params.page));
  if (params.pageSize) query.set('page_size', String(params.pageSize));
  const suffix = query.toString();
  return apiGetObject<{
    results: WorkspaceCompany[];
    count: number;
    page: number;
    page_size: number;
  }>(`accountant/workspace/companies/${suffix ? `?${suffix}` : ''}`);
};

// ── مكتب المحاسبة: ملف الزبون (قراءة فقط) ───────────────────────────────────
export type ClientDocumentKind = 'sales' | 'purchases' | 'expenses';

export interface ClientInvoiceRow {
  id: number;
  invoice_number: string;
  invoice_date: string;
  kind: string;
  kind_label: string;
  partner_name: string;
  partner_tax_number: string;
  status: string;
  status_label: string;
  subtotal: string;
  tax_amount: string;
  grand_total: string;
}

export interface ClientExpenseRow {
  account_id: number;
  code: string;
  name: string;
  entries: number;
  amount: string;
}

export interface ClientSummary {
  period_from: string;
  period_to: string;
  assets: string;
  liabilities: string;
  equity: string;
  balance_gap: string;
  revenue: string;
  expenses: string;
  profit: string;
  output_vat: string;
  input_vat: string;
  vat_due: string;
}

export const listClientDocuments = <T = ClientInvoiceRow | ClientExpenseRow>(
  tenantId: number,
  kind: ClientDocumentKind,
  from: string,
  to: string,
) =>
  apiGetObject<{ kind: ClientDocumentKind; results: T[]; totals: Record<string, string>; count: number }>(
    `accountant/client/documents/?kind=${kind}&from=${from}&to=${to}`,
    { tenantId },
  );

export const getClientSummary = (tenantId: number, from: string, to: string) =>
  apiGetObject<{ company_name: string; summary: ClientSummary }>(
    `accountant/client/summary/?from=${from}&to=${to}`,
    { tenantId },
  );

export interface StatementRow {
  account_id: number;
  code: string;
  name: string;
  amount: string;
}

export interface ClientStatements {
  company_name: string;
  period_from: string;
  period_to: string;
  income: {
    revenue: StatementRow[];
    expenses: StatementRow[];
    revenue_total: string;
    expense_total: string;
    profit: string;
  };
  balance: {
    assets: StatementRow[];
    liabilities: StatementRow[];
    equity: StatementRow[];
    asset_total: string;
    liability_total: string;
    equity_total: string;
    gap: string;
  };
}

export const getClientStatements = (tenantId: number, from: string, to: string) =>
  apiGetObject<ClientStatements>(
    `accountant/client/statements/?from=${from}&to=${to}`, { tenantId },
  );

export interface TrendPoint {
  month: string;
  revenue: string;
  expenses: string;
  profit: string;
}

export const getClientTrend = (tenantId: number, months = 6) =>
  apiGetObject<{ months: number; series: TrendPoint[] }>(
    `accountant/client/trend/?months=${months}`, { tenantId },
  );

export interface PracticeClientRow {
  tenant_id: number;
  company_name: string;
  revenue: string;
  expenses: string;
  profit: string;
  vat_due: string;
  draft_documents: number;
  filing_due_date: string;
  days_to_filing: number;
  needs_attention: boolean;
}

export const getPracticeOverview = () =>
  apiGetObject<{
    period_from: string;
    period_to: string;
    clients: PracticeClientRow[];
    totals: {
      clients: number;
      vat_due: string;
      profit: string;
      draft_documents: number;
      needs_attention: number;
    };
  }>('accountant/practice/overview/');

export const downloadReviewPackageCsv = (
  tenantId: number,
  body: { period_from: string; period_to: string },
) => apiPostForBlob('accountant/review/export/', { ...body, format: 'csv' }, { tenantId });

export const listCompanyAccountantEngagements = (tenantId: number) =>
  apiGetObject<{ results: AccountantEngagement[]; count: number }>('accountant/company/engagements/', { tenantId });

export const getCompanyAccountantScopeCatalog = (tenantId: number) =>
  apiGetObject<{
    permissions: AccountantPermissionEntry[];
    defaults: string[];
    profiles: Record<string, string[]>;
    active_profile: string;
  }>('accountant/company/engagements/scope-catalog/', { tenantId });

export const inviteCompanyAccountant = (
  tenantId: number,
  body: { email: string; scope: string[]; note: string },
) => apiPostObject<{ engagement: AccountantEngagement }>(
  'accountant/company/engagements/invite/', body, { tenantId },
);

export const updateCompanyAccountantScope = (
  tenantId: number,
  id: number,
  scope: string[],
  reauthPassword: string,
) => apiPatchObject<{ engagement: AccountantEngagement }>(
  `accountant/company/engagements/${id}/scope/`,
  { scope, reauth_password: reauthPassword },
  { tenantId },
);

export const companyEngagementAction = (
  tenantId: number,
  id: number,
  action: 'approve' | 'decline' | 'suspend' | 'resume' | 'revoke',
  body: Record<string, unknown> = {},
) => apiPostObject<{ engagement: AccountantEngagement }>(
  `accountant/company/engagements/${id}/${action}/`, body, { tenantId },
);

