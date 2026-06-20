import React, { useState, useRef, useEffect } from "react";
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
  PlusCircle,
  ChevronDown
} from "lucide-react";
import { AppView, User } from "../../types";

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
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const go = (view: AppView, id?: string) => () => {
    onNavigate(view, id);
    setIsOpen(false);
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const groups: ActionItem[][] = [
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

  const visibleGroups = groups
    .map((g) => g.filter((a) => a.show))
    .filter((g) => g.length > 0);

  if (visibleGroups.length === 0) return null;

  return (
    <div className="relative flex items-center gap-1.5" ref={menuRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-[var(--color-primary)] text-white hover:opacity-90 shadow-sm"
        title="إجراءات سريعة"
      >
        <PlusCircle className="w-4 h-4" />
        <span className="hidden sm:inline">إجراءات سريعة</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Quick single-click icons for Print & Refresh */}
      <button
        type="button"
        onClick={() => window.print()}
        className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-primary)] hover:bg-[var(--color-surface-2)] rounded-lg transition-colors ml-1"
        title="طباعة"
      >
        <Printer className="w-4 h-4" />
      </button>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="p-1.5 text-[var(--color-text-muted)] hover:text-[var(--color-primary)] hover:bg-[var(--color-surface-2)] rounded-lg transition-colors"
        title="تحديث"
      >
        <RefreshCw className="w-4 h-4" />
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-56 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-xl shadow-lg z-50 py-2">
          {visibleGroups.map((group, gi) => (
            <React.Fragment key={gi}>
              {gi > 0 && <div className="h-px bg-[var(--color-border)] my-1.5 mx-3" />}
              <div className="px-1.5">
                {group.map((a) => (
                  <button
                    key={a.key}
                    type="button"
                    onClick={a.onClick}
                    className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-primary)] rounded-md transition-colors"
                  >
                    <span className="text-[var(--color-primary)] flex-shrink-0">{a.icon}</span>
                    <span className="truncate">{a.label}</span>
                  </button>
                ))}
              </div>
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
};
