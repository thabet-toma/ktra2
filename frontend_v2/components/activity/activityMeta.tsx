import React from "react";
import {
  Plus, Pencil, Trash2, CheckCircle2, RotateCcw, Copy,
  DollarSign, Eye, LogIn, LogOut, Activity as ActivityIcon,
} from "lucide-react";

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
  view:      { label: "عرض",           icon: <Eye className={cls("aseel-text-soft")} />,        badge: "aseel-bg-panel aseel-text-soft" },
  login:     { label: "تسجيل دخول",    icon: <LogIn className={cls("text-green-600")} />,       badge: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300" },
  logout:    { label: "تسجيل خروج",    icon: <LogOut className={cls("aseel-text-soft")} />,     badge: "aseel-bg-panel aseel-text-soft" },
};

export function actionMeta(action: string): ActionMeta {
  return ACTION_META[action] || {
    label: action,
    icon: <ActivityIcon className={cls("aseel-text-soft")} />,
    badge: "aseel-bg-panel aseel-text-soft",
  };
}

/** أسماء عربية لأنواع المستندات في سجل النشاط. */
export const ENTITY_LABELS: Record<string, string> = {
  sales_invoice: "فاتورة مبيعات",
  purchase_invoice: "فاتورة شراء",
  deal: "صفقة",
  customer_payment: "سند قبض",
  session: "جلسة",
};

export function entityLabel(entityType: string): string {
  return ENTITY_LABELS[entityType] || entityType;
}

export function formatActivityTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return ts;
  }
}
