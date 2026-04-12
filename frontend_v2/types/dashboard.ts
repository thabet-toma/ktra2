export interface DashboardAlert {
  type: "info" | "warning" | "danger";
  title: string;
  message: string;
  link?: string;
}

export interface DashboardData {
  deals: {
    total: number;
    open: number;
    shipped: number;
    cleared: number;
    closed: number;
    open_value: number;
    this_month: number;
    status_distribution: { status: string; count: number }[];
    recent: {
      id: number;
      ref_number: string;
      status: string;
      total_amount: number;
      order_date: string;
      partner_name: string;
    }[];
  };
  shipments: {
    total: number;
    in_transit: number;
    arrived: number;
    clearing: number;
    cleared: number;
    recent: {
      id: number;
      shipment_number: string;
      status: string;
      departure_date: string | null;
      arrival_date: string | null;
      total_shipping_cost_usd: number;
    }[];
  };
  payments: {
    total: number;
    posted: number;
    total_paid: number;
    paid_this_month: number;
  };
  invoices: {
    total: number;
    posted: number;
    draft: number;
    total_value: number;
    recent: {
      id: number;
      invoice_number: string;
      status: string;
      grand_total: number;
      invoice_date: string | null;
      partner_name: string;
    }[];
  };
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
  accounting: {
    journals_this_month: number;
  };
  alerts: DashboardAlert[];
}
