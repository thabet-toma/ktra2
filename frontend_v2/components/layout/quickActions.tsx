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
 * @param salesInvoiceLabel ISSUE #82: اسم فاتورة المبيعات من المعجم
 *        (`usePermissions().term('doc.sales_invoice')`) — يتبدّل باسمه البديل
 *        في مكتب المحاسبة.
 * @param firstAction ISSUE #83: إجراء البيان الأول (`shell.first_action`)،
 *        محلولاً عبر `resolveManifestView` — يستبدل الافتراض الأعمى «فاتورة
 *        مبيعات» حين يعرّف قالب الشركة إجراءه الخاص (مثل «ترميز مستندات» في
 *        دفتر عميل). غيابه (`general` وما بلا بيان) يبقي السلوك القديم حرفياً.
 */
export function buildQuickActionGroups(
  user: User,
  go: (view: AppView, id?: string) => () => void,
  salesInvoiceLabel: string,
  firstAction?: { view: string; label: string } | null,
): QuickAction[][] {
  const isManager = user.role === "manager";
  const canInvoice = user.role === "manager" || user.role === "procurement";
  // البيان (#83) يعيد شاشةً مُحلولة (تسقط إلى `dashboard` عند اللزوم) بمفتاحٍ
  // نصّي عام؛ التوكيد آمنٌ لأن `resolveManifestView` تضمن قيمة `AppView` صالحة.
  const primaryAction = firstAction ?? { view: "sales-invoices" as AppView, label: salesInvoiceLabel };

  return [
    [
      {
        key: "new-sales",
        label: primaryAction.label,
        icon: <FilePlus2 className="w-4 h-4" />,
        onClick: go(primaryAction.view as AppView, "new"),
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
  return applySavedOrder(groups.map((g) => g.filter((a) => a.show)).filter((g) => g.length > 0));
}

/**
 * ترتيب أيقونات الإجراءات السريعة القابل للسحب — محفوظ محلياً (لكل متصفح)
 * ومصدر واحد يخدم شريط الإجراءات ({@link GlobalActionBar}) وقائمة زر الفأرة
 * اليمنى ({@link GlobalContextMenu}) معاً عبر {@link visibleQuickActionGroups}.
 */
const ORDER_KEY = "ktra:quickActionsOrder";

export function getQuickActionsOrder(): string[] {
  try {
    const raw = localStorage.getItem(ORDER_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((k): k is string => typeof k === "string") : [];
  } catch {
    return [];
  }
}

export function setQuickActionsOrder(order: string[]): void {
  try {
    localStorage.setItem(ORDER_KEY, JSON.stringify(order));
  } catch {
    /* تجاهل أخطاء التخزين */
  }
}

/** يرتّب كل مجموعة حسب ترتيب المستخدم المحفوظ؛ المفاتيح غير المحفوظة تبقى بترتيبها الأصلي في النهاية. */
function applySavedOrder(groups: QuickAction[][]): QuickAction[][] {
  const order = getQuickActionsOrder();
  if (order.length === 0) return groups;
  const rank = new Map(order.map((k, i) => [k, i]));
  return groups.map((g) =>
    [...g].sort((a, b) => (rank.get(a.key) ?? Number.MAX_SAFE_INTEGER) - (rank.get(b.key) ?? Number.MAX_SAFE_INTEGER)),
  );
}
