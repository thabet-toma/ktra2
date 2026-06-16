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
  Printer,
  RefreshCw,
} from "lucide-react";
import { AppView, User } from "../../types";

/**
 * task18 DEF-A2: شريط الإجراءات العام الدائم (يحاكي شريط الأدوات السفلي في
 * تطبيق سطح المكتب). كل إجراء ملاحي يفتح شاشته بمساره الخاص عبر `onNavigate`
 * (المساره يتزامن مع الـ URL في App.setViewAndSyncPath). الطباعة/التحديث
 * إجراءات عامة فورية. التصدير إلى إكسل يبقى سياقياً لكل صفحة قائمة (لكلٍّ زر
 * تصدير خاص) فلا نضع زراً عاماً معطّلاً هنا.
 */
type ActionItem = {
  key: string;
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  show: boolean;
  danger?: boolean;
};

interface Props {
  user: User;
  onNavigate: (view: AppView, targetId?: string) => void;
}

export const GlobalActionBar: React.FC<Props> = ({ user, onNavigate }) => {
  const isManager = user.role === "manager";
  const canInvoice = user.role === "manager" || user.role === "procurement";

  const go = (view: AppView, id?: string) => () => onNavigate(view, id);

  // مجموعات الإجراءات مفصولة بفواصل بصرية — بترتيب شريط الأصيل السفلي.
  const groups: ActionItem[][] = [
    [
      {
        key: "new-sales",
        label: "فاتورة مبيعات",
        icon: <FilePlus2 />,
        onClick: go("sales-invoices", "new"),
        show: canInvoice,
      },
      {
        key: "new-purchase",
        label: "فاتورة شراء",
        icon: <ShoppingCart />,
        onClick: go("purchase-invoices", "new"),
        show: canInvoice,
      },
    ],
    [
      {
        key: "receipt",
        label: "سند قبض",
        icon: <ReceiptText />,
        onClick: go("sales-customer-payments"),
        show: canInvoice,
      },
      {
        key: "payment",
        label: "سند صرف",
        icon: <HandCoins />,
        onClick: go("supplier-payments"),
        show: canInvoice,
      },
      {
        key: "transfer",
        label: "قيد تحويل",
        icon: <ArrowLeftRight />,
        onClick: go("accounting-journal-entry"),
        show: isManager,
      },
    ],
    [
      {
        key: "search-entry",
        label: "البحث عن قيد",
        icon: <Search />,
        onClick: go("accounting-journals"),
        show: isManager,
      },
      {
        key: "coa",
        label: "شجرة الحسابات",
        icon: <Network />,
        onClick: go("accounting-coa"),
        show: isManager,
      },
      {
        key: "cash-statement",
        label: "كشف الصندوق",
        icon: <Wallet />,
        onClick: go("cash-boxes"),
        show: isManager,
      },
      {
        key: "cheques",
        label: "الشيكات",
        icon: <CreditCard />,
        onClick: go("accounting-cheques"),
        show: isManager,
      },
      {
        key: "fx",
        label: "صرف العملات",
        icon: <Coins />,
        onClick: go("accounting-exchange-rates"),
        show: isManager,
      },
    ],
    [
      {
        key: "print",
        label: "طباعة",
        icon: <Printer />,
        onClick: () => window.print(),
        show: true,
      },
      {
        key: "refresh",
        label: "تحديث",
        icon: <RefreshCw />,
        onClick: () => window.location.reload(),
        show: true,
      },
    ],
  ];

  const visibleGroups = groups
    .map((g) => g.filter((a) => a.show))
    .filter((g) => g.length > 0);

  return (
    <nav
      className="aseel-toolbar aseel-actionbar flex-shrink-0"
      aria-label="شريط الإجراءات العام"
    >
      {visibleGroups.map((group, gi) => (
        <React.Fragment key={gi}>
          {gi > 0 && <span className="aseel-toolsep" aria-hidden="true" />}
          <div className="aseel-toolgrp">
            {group.map((a) => (
              <button
                key={a.key}
                type="button"
                className={`aseel-toolbtn${a.danger ? " aseel-toolbtn--danger" : ""}`}
                onClick={a.onClick}
                title={a.label}
              >
                {a.icon}
                <span>{a.label}</span>
              </button>
            ))}
          </div>
        </React.Fragment>
      ))}
    </nav>
  );
};
