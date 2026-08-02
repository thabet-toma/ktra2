/**
 * مصاريف شخصية — عميل REST رقيق حول restApi.
 * الـ backend: hr.PersonalExpenseViewSet — معزول بالمستخدم لا بالشركة، فلا
 * يُمرَّر tenantId هنا (المصاريف تتبع صاحبها عبر كل شركاته).
 *
 * الأوراق (تبويبات بأسلوب إكسل) والفئات كتالوجان لكل مستخدم، يزرعهما الخادم
 * عند أول قائمة — فلا نسخة افتراضية في الواجهة تتعارض معه.
 */
import { apiDelete, apiGetList, apiGetObject, apiPatchObject, apiPostObject } from './restApi';

/** مفتاح الفئة كما يخزنه الخادم — نصّ حر لأن الكتالوج صار قابلاً للتوسعة. */
export type PersonalExpenseCategoryKey = string;

export interface PersonalExpenseSheet {
  id: number;
  name: string;
  position: number;
  created_at: string;
}

export interface PersonalExpenseCategory {
  id: number;
  key: PersonalExpenseCategoryKey;
  label: string;
  position: number;
}

export interface PersonalExpense {
  id: number;
  sheet: number | null;
  date: string;
  title: string;
  category: PersonalExpenseCategoryKey;
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
  by_category: { category: PersonalExpenseCategoryKey; label: string; total: string }[];
}

export interface PersonalExpenseFilters {
  sheet?: number | null;
  month?: string;
  category?: PersonalExpenseCategoryKey | '';
  is_paid?: 'true' | 'false' | '';
}

function queryOf(filters: PersonalExpenseFilters): Record<string, string> {
  const q: Record<string, string> = {};
  if (filters.sheet) q.sheet = String(filters.sheet);
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
  sheet: number | null;
  date: string;
  title: string;
  category: PersonalExpenseCategoryKey;
  amount: string;
  is_paid: boolean;
  notes?: string;
}): Promise<PersonalExpense> {
  return apiPostObject<PersonalExpense>('hr/personal-expenses/', input);
}

export function updatePersonalExpense(
  id: number,
  patch: Partial<Pick<PersonalExpense, 'sheet' | 'date' | 'title' | 'category' | 'amount' | 'is_paid' | 'notes'>>,
): Promise<PersonalExpense> {
  return apiPatchObject<PersonalExpense>(`hr/personal-expenses/${id}/`, patch);
}

export function deletePersonalExpense(id: number): Promise<void> {
  return apiDelete(`hr/personal-expenses/${id}/`);
}

/* — الأوراق (تبويبات) — */

export function listPersonalExpenseSheets(): Promise<PersonalExpenseSheet[]> {
  return apiGetList<PersonalExpenseSheet>('hr/personal-expense-sheets/');
}

export function createPersonalExpenseSheet(name: string): Promise<PersonalExpenseSheet> {
  return apiPostObject<PersonalExpenseSheet>('hr/personal-expense-sheets/', { name });
}

export function renamePersonalExpenseSheet(id: number, name: string): Promise<PersonalExpenseSheet> {
  return apiPatchObject<PersonalExpenseSheet>(`hr/personal-expense-sheets/${id}/`, { name });
}

export function deletePersonalExpenseSheet(id: number): Promise<void> {
  return apiDelete(`hr/personal-expense-sheets/${id}/`);
}

/* — كتالوج الفئات — */

export function listPersonalExpenseCategories(): Promise<PersonalExpenseCategory[]> {
  return apiGetList<PersonalExpenseCategory>('hr/personal-expense-categories/');
}

export function createPersonalExpenseCategory(label: string): Promise<PersonalExpenseCategory> {
  return apiPostObject<PersonalExpenseCategory>('hr/personal-expense-categories/', { label });
}

export function renamePersonalExpenseCategory(
  id: number,
  label: string,
): Promise<PersonalExpenseCategory> {
  return apiPatchObject<PersonalExpenseCategory>(`hr/personal-expense-categories/${id}/`, { label });
}

export function deletePersonalExpenseCategory(id: number): Promise<void> {
  return apiDelete(`hr/personal-expense-categories/${id}/`);
}
