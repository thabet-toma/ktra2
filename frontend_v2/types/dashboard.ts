export interface DashboardAlert {
  type: "info" | "warning" | "danger";
  title: string;
  message: string;
  link?: string;
}

export interface DashboardInvoice {
  id: number;
  invoice_number: string;
  status: string;
  grand_total: number;
  invoice_date: string | null;
  partner_name: string;
  currency_code: string;
}

export interface DashboardInvoiceSummary {
  total: number;
  posted: number;
  draft: number;
  recent: DashboardInvoice[];
}

export interface DashboardData {
  period: { from: string; to: string };
  financials: {
    revenue: number;
    expenses: number;
    net_profit: number;
  };
  sales_invoices: DashboardInvoiceSummary;
  purchase_invoices: DashboardInvoiceSummary;
  inventory: {
    total_products: number;
    in_stock: number;
    low_stock: number;
    out_of_stock: number;
    inventory_value: number;
    movements_this_month: number;
    low_stock_items: {
      id: number;
      sku: string;
      name_ar: string;
      quantity_on_hand: number;
      min_stock_level: number;
    }[];
  };
  accounting: { journals_this_month: number };
  alerts: DashboardAlert[];
  import_operations?: {
    deals: {
      open: number;
      active_value: number;
      status_distribution: { status: string; count: number }[];
    };
    shipments: { in_transit: number; clearing: number };
    payments: { paid_this_month: number };
  };
}
