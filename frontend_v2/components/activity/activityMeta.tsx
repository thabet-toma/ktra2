import React from "react";
import {
  Plus, Pencil, Trash2, CheckCircle2, RotateCcw, Copy,
  DollarSign, Eye, LogIn, LogOut, Activity as ActivityIcon,
} from "lucide-react";
import { formatDateTimeValue } from "../../utils/formatDate";

/** بيانات عرض موحّدة لكل نوع إجراء — مشتركة بين سجل المستند والصفحة العامة. */
export interface ActionMeta {
  label: string;
  icon: React.ReactNode;
  /** classes للخلفية/النص للشارة */
  badge: string;
}

const cls = (c: string) => `w-4 h-4 ${c}`;

export const ACTION_META: Record<string, ActionMeta> = {
  create:    { label: "إنشاء",         icon: <Plus className={cls("text-green-600")} />,        badge: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300" },
  update:    { label: "تعديل",         icon: <Pencil className={cls("text-blue-600")} />,       badge: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300" },
  delete:    { label: "حذف",           icon: <Trash2 className={cls("text-red-600")} />,        badge: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300" },
  post:      { label: "ترحيل",         icon: <CheckCircle2 className={cls("text-emerald-600")} />, badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300" },
  unpost:    { label: "إلغاء ترحيل",   icon: <RotateCcw className={cls("text-amber-600")} />,   badge: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300" },
  duplicate: { label: "نسخ",           icon: <Copy className={cls("text-indigo-600")} />,       badge: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300" },
  payment:   { label: "دفعة",          icon: <DollarSign className={cls("text-teal-600")} />,   badge: "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300" },
  view:      { label: "عرض",           icon: <Eye className={cls("ktra-text-soft")} />,        badge: "ktra-bg-panel ktra-text-soft" },
  login:     { label: "تسجيل دخول",    icon: <LogIn className={cls("text-green-600")} />,       badge: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300" },
  logout:    { label: "تسجيل خروج",    icon: <LogOut className={cls("ktra-text-soft")} />,     badge: "ktra-bg-panel ktra-text-soft" },
};

export function actionMeta(action: string): ActionMeta {
  return ACTION_META[action] || {
    label: action,
    icon: <ActivityIcon className={cls("ktra-text-soft")} />,
    badge: "ktra-bg-panel ktra-text-soft",
  };
}

/** أسماء عربية لأنواع المستندات في سجل النشاط. */
export const ENTITY_LABELS: Record<string, string> = {
  sales_invoice: "فاتورة مبيعات",
  purchase_invoice: "فاتورة شراء",
  deal: "صفقة",
  shipment: "شحنة",
  clearance: "تخليص جمركي",
  local_shipment: "نقل محلي",
  customer_payment: "سند قبض",
  supplier_payment: "سند صرف",
  partner: "جهة",
  product: "منتج",
  session: "جلسة",
  // أفعال سوبر أدمن على الشركة نفسها — تظهر في «آخر الحركات» بلوحة المنصة،
  // وبلا اسمٍ عربي هنا كانت تُطبع بمفتاحها الإنجليزي داخل شاشة عربية.
  tenant: "الشركة",
  tenant_module: "وحدة مرخَّصة",
  tenant_limit: "حدّ خطة",
};

export function entityLabel(entityType: string): string {
  return ENTITY_LABELS[entityType] || entityType;
}

export function formatActivityTime(ts: string): string {
  return formatDateTimeValue(ts) || ts;
}
