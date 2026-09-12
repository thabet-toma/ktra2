/**
 * عميلُ مستهدفَي موظّف المنصة (التذكرة 210-ز).
 *
 * `capacity_target` و`monthly_units_target` كانا بلا بابٍ في النظام كلِّه — لا
 * نقطةَ كتابةٍ ولا شاشةَ ولا `admin.py` — فيُضبطان من الـshell أو لا يُضبطان.
 * ومعنى ذلك أنّ مقامَ درجةِ كلّ موظّفٍ حقيقيٍّ صفرٌ، وأنّ حارسَ طاقة الإسناد
 * مُطفأٌ للجميع.
 *
 * **وهما سُلَّمان لا رقمٌ واحد**: الأوّلُ يُقاس بالشركات الموزونة (١/٢/٣ للشركة)
 * وبعدد أوامر العمل النشطة، والثاني بوحدات الكتالوج للمستندات في الشهر.
 */
import { apiGetObject, apiPatchObject } from "./restApi";

/** من أين جاءت المقاديرُ الثلاثة — «لا تاريخ» تعني ألّا أرقامَ تُقترح أصلاً. */
export type SuggestionBasis = "self" | "peers" | "no_history";

export interface MonthlyUnitsSuggestion {
  basis: SuggestionBasis;
  months: { year: number; month: number }[];
  /** `null` حين لا تاريخَ في المنصّة كلِّها — لا تُخترع أرقامٌ لمقامِ درجة. */
  targets: { low: number; medium: number; high: number } | null;
  sample_count?: number;
}

export interface EmployeeTargets {
  employee_id: number;
  employee_name: string;
  /** نصٌّ لأنّ النقطةَ تُصدِّره بـ`str()`: مُرمِّزُ DRF يحوّل `Decimal` إلى `float`. */
  capacity_target: string;
  monthly_units_target: string;
  /** `null` لغير مدير العمليات: بديلُ الزملاء يشتقّ الأرقامَ من إنتاج غيره. */
  monthly_units_suggestion: MonthlyUnitsSuggestion | null;
}

export const getEmployeeTargets = (employeeId: number) =>
  apiGetObject<EmployeeTargets>(`platform/ops/employees/${employeeId}/targets/`);

/**
 * يُمرَّر الحقلُ الذي تغيّر وحدَه: من لا يُمرَّر لا يُمَسّ، فلا يمحو ضبطُ أحدِ
 * السُلَّمين الآخرَ بصمت.
 */
export const setEmployeeTargets = (
  employeeId: number,
  input: { capacity_target?: string; monthly_units_target?: string },
) => apiPatchObject<EmployeeTargets>(`platform/ops/employees/${employeeId}/targets/`, input);
