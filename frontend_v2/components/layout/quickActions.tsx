import React from "react";
import {
  FilePlus2,
  ShoppingCart,
  ReceiptText,
  HandCoins,
  ArrowLeftRight,
  Search,
  Network,
  Wallet,
  CreditCard,
  Coins,
} from "lucide-react";
import { AppView, User } from "../../types";

/**
 * تعريف موحّد للإجراءات السريعة (مصدر واحد) — يستهلكه شريط الإجراءات السريعة
 * ({@link GlobalActionBar}) وقائمة زر الفأرة اليمنى العامّة ({@link GlobalContextMenu})
 * معاً، فلا يتكرّر تعريف الأزرار ولا صلاحياتها في مكانين.
 */
export type QuickAction = {
  key: string;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  show: boolean;
  danger?: boolean;
};

/**
 * يبني مجموعات الإجراءات السريعة حسب دور المستخدم.
 * @param go مصنع onClick: يتلقّى (view, id?) ويعيد المعالج (يتيح للمستهلك إغلاق
 *           قائمته بعد التنقّل).
 */
export function buildQuickActionGroups(
  user: User,
  go: (view: AppView, id?: string) => () => void,
): QuickAction[][] {
  const isManager = user.role === "manager";
  const canInvoice = user.role === "manager" || user.role === "procurement";

  return [
    [
      {
        key: "new-sales",
        label: "فاتورة مبيعات",
        icon: <FilePlus2 className="w-4 h-4" />,
        onClick: go("sales-invoices", "new"),
        show: canInvoice,
      },
      {
        key: "new-purchase",
        label: "فاتورة شراء",
        icon: <ShoppingCart className="w-4 h-4" />,
        onClick: go("purchase-invoices", "new"),
        show: canInvoice,
      },
      {
        key: "receipt",
        label: "سند قبض",
        icon: <ReceiptText className="w-4 h-4" />,
        onClick: go("sales-customer-payments"),
        show: canInvoice,
      },
      {
        key: "payment",
        label: "سند صرف",
        icon: <HandCoins className="w-4 h-4" />,
        onClick: go("supplier-payments"),
        show: canInvoice,
      },
    ],
    [
      {
        key: "transfer",
        label: "قيد تحويل",
        icon: <ArrowLeftRight className="w-4 h-4" />,
        onClick: go("accounting-journal-entry"),
        show: isManager,
      },
      {
        key: "search-entry",
        label: "البحث عن قيد",
        icon: <Search className="w-4 h-4" />,
        onClick: go("accounting-journals"),
        show: isManager,
      },
      {
        key: "coa",
        label: "شجرة الحسابات",
        icon: <Network className="w-4 h-4" />,
        onClick: go("accounting-coa"),
        show: isManager,
      },
      {
        key: "cash-statement",
        label: "كشف الصندوق",
        icon: <Wallet className="w-4 h-4" />,
        onClick: go("cash-boxes"),
        show: isManager,
      },
      {
        key: "cheques",
        label: "الشيكات",
        icon: <CreditCard className="w-4 h-4" />,
        onClick: go("accounting-cheques"),
        show: isManager,
      },
      {
        key: "fx",
        label: "صرف العملات",
        icon: <Coins className="w-4 h-4" />,
        onClick: go("accounting-exchange-rates"),
        show: isManager,
      },
    ],
  ];
}

/** يُرشّح المجموعات على `show` ويحذف الفارغة — سلوك عرض مشترك. */
export function visibleQuickActionGroups(groups: QuickAction[][]): QuickAction[][] {
  return groups.map((g) => g.filter((a) => a.show)).filter((g) => g.length > 0);
}
