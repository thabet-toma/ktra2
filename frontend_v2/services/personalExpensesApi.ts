/**
 * مصاريف شخصية — عميل REST رقيق حول restApi.
 * الـ backend: hr.PersonalExpenseViewSet — معزول بالمستخدم لا بالشركة، فلا
 * يُمرَّر tenantId هنا (المصاريف تتبع صاحبها عبر كل شركاته).
 */
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from './restApi';

export type PersonalExpenseCategory =
  | 'food' | 'transport' | 'bills' | 'health'
  | 'shopping' | 'family' | 'entertainment' | 'other';

export interface PersonalExpense {
  id: number;
  date: string;
  title: string;
  category: PersonalExpenseCategory;
  category_label: string;
  amount: string;
  is_paid: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface PersonalExpenseSummary {
  count: number;
  total: string;
  paid_total: string;
  unpaid_total: string;
  by_category: { category: PersonalExpenseCategory; label: string; total: string }[];
}

export interface PersonalExpenseFilters {
  month?: string;
  category?: PersonalExpenseCategory | '';
  is_paid?: 'true' | 'false' | '';
}

/** فئات العرض — نسخة الواجهة من كتالوج hr.PersonalExpense.CATEGORY_CHOICES. */
export const PERSONAL_EXPENSE_CATEGORIES: { value: PersonalExpenseCategory; label: string }[] = [
  { value: 'food', label: 'طعام وشراب' },
  { value: 'transport', label: 'مواصلات' },
  { value: 'bills', label: 'فواتير واشتراكات' },
  { value: 'health', label: 'صحة' },
  { value: 'shopping', label: 'تسوّق' },
  { value: 'family', label: 'أسرة وتعليم' },
  { value: 'entertainment', label: 'ترفيه' },
  { value: 'other', label: 'أخرى' },
];

function queryOf(filters: PersonalExpenseFilters): Record<string, string> {
  const q: Record<string, string> = {};
  if (filters.month) q.month = filters.month;
  if (filters.category) q.category = filters.category;
  if (filters.is_paid) q.is_paid = filters.is_paid;
  return q;
}

export function listPersonalExpenses(filters: PersonalExpenseFilters = {}): Promise<PersonalExpense[]> {
  return apiGetList<PersonalExpense>('hr/personal-expenses/', { query: queryOf(filters) });
}

export function fetchPersonalExpenseSummary(
  filters: PersonalExpenseFilters = {},
): Promise<PersonalExpenseSummary> {
  const q = new URLSearchParams(queryOf(filters)).toString();
  return apiGetObject<PersonalExpenseSummary>(`hr/personal-expenses/summary/${q ? `?${q}` : ''}`);
}

export function createPersonalExpense(input: {
  date: string;
  title: string;
  category: PersonalExpenseCategory;
  amount: string;
  is_paid: boolean;
  notes?: string;
}): Promise<PersonalExpense> {
  return apiPostObject<PersonalExpense>('hr/personal-expenses/', input);
}

export function updatePersonalExpense(
  id: number,
  patch: Partial<Pick<PersonalExpense, 'date' | 'title' | 'category' | 'amount' | 'is_paid' | 'notes'>>,
): Promise<PersonalExpense> {
  return apiPatchObject<PersonalExpense>(`hr/personal-expenses/${id}/`, patch);
}

export function deletePersonalExpense(id: number): Promise<void> {
  return apiDelete(`hr/personal-expenses/${id}/`);
}
