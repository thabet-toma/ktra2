/**
 * ISSUE #57 — الفترات الضريبية تعمل على دفتر العميل، مُداراً كان أو مربوطاً.
 *
 * أيّ دفتر تُرسَل إليه شاشة الفترات الضريبية؟ الدفتر المُدار يفوز عند التعارض
 * (`hybrid`): مديره يحمل صلاحية `manager` كاملة عليه منذ إنشائه
 * (`tenants.services.create_company`)، بينما الارتباط قد يمنح نطاقاً جزئياً
 * فقط ولا يعمل أصلاً إلا وهو نشط (`accessible`). دفترٌ مربوطٌ بارتباطٍ معلَّق أو
 * مرفوض لا يفتح شيئاً — تماماً كزرّ «افتح دفاتر الشركة» في ملف الزبون.
 */

export interface ClientBookAccessInput {
  managedTenantId: number | null | undefined;
  linkedTenantId: number | null | undefined;
  linkedAccessible: boolean;
}

export function resolveClientBookTenantId(input: ClientBookAccessInput): number | null {
  if (input.managedTenantId != null) return input.managedTenantId;
  if (input.linkedTenantId != null && input.linkedAccessible) return input.linkedTenantId;
  return null;
}
