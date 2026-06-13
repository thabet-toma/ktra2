import { resolveBranchId, resolveTenantId } from "../utils/tenantContext";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";
const INV = `${API_BASE}/inventory`;

const headers = (): HeadersInit => {
  const token = localStorage.getItem("token");
  // task11 R2: الشركة النشطة + الفرع النشط مع كل طلب مخزون
  const branchId = resolveBranchId();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Token ${token}` } : {}),
    "X-Tenant-Id": String(resolveTenantId()),
    ...(branchId ? { "X-Branch-Id": String(branchId) } : {}),
  };
};

async function handle(res: Response, ctx: string): Promise<void> {
  if (res.ok) return;
  let msg = `${ctx}: ${res.status}`;
  try {
    const j = await res.json();
    if (typeof j.error === "string") msg = j.error;
    else if (typeof j.detail === "string") msg = j.detail;
  } catch {
    const t = await res.text();
    if (t) msg = t.slice(0, 400);
  }
  throw new Error(msg);
}

async function asList(res: Response): Promise<any[]> {
  await handle(res, "inventory");
  const data = await res.json();
  return Array.isArray(data) ? data : (data.results ?? []);
}

export const inventoryApi = {
  // ─── Products ───

  getProducts: (params?: Record<string, string | number>) => {
    const q = params && Object.keys(params).length
      ? `?${new URLSearchParams(params as Record<string, string>)}`
      : "";
    return fetch(`${INV}/products/${q}`, { headers: headers() }).then(async (res) => {
      await handle(res, "inventory");
      const data = await res.json();
      return data; // Return full response (might be paginated: {results: [], count: ...})
    });
  },

  // ─── Categories ───

  getCategories: () =>
    fetch(`${INV}/categories/`, { headers: headers() }).then(asList),

  createCategory: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/categories/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createCategory");
    return res.json();
  },

  updateCategory: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/categories/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateCategory");
    return res.json();
  },

  deleteCategory: async (id: number) => {
    const res = await fetch(`${INV}/categories/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteCategory");
  },

  // ─── Warehouses (المستودعات) ───

  getWarehouses: (params?: Record<string, string>) => {
    const q = params && Object.keys(params).length
      ? `?${new URLSearchParams(params)}`
      : "";
    return fetch(`${INV}/warehouses/${q}`, { headers: headers() }).then(asList);
  },

  createWarehouse: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/warehouses/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createWarehouse");
    return res.json();
  },

  updateWarehouse: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/warehouses/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateWarehouse");
    return res.json();
  },

  deleteWarehouse: async (id: number) => {
    const res = await fetch(`${INV}/warehouses/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteWarehouse");
  },

  getProduct: async (id: number) => {
    const res = await fetch(`${INV}/products/${id}/`, { headers: headers() });
    await handle(res, "getProduct");
    return res.json();
  },

  getProductStockMovements: async (productId: number) => {
    const res = await fetch(`${INV}/products/${productId}/stock-movements/`, {
      headers: headers(),
    });
    await handle(res, "getProductStockMovements");
    return res.json();
  },

  // ─── Stock Movements ───

  getStockMovements: (params?: Record<string, string>) => {
    const q = params && Object.keys(params).length
      ? `?${new URLSearchParams(params)}`
      : "";
    return fetch(`${INV}/stock-movements/${q}`, { headers: headers() }).then(asList);
  },

  createStockMovement: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/stock-movements/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createStockMovement");
    return res.json();
  },

  getStockSummary: async () => {
    const res = await fetch(`${INV}/stock-movements/summary/`, {
      headers: headers(),
    });
    await handle(res, "getStockSummary");
    return res.json();
  },

  // ─── Product CRUD helpers (N5) ───

  createProduct: async (body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/products/`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "createProduct");
    return res.json();
  },

  updateProduct: async (id: number, body: Record<string, unknown>) => {
    const res = await fetch(`${INV}/products/${id}/`, {
      method: "PATCH",
      headers: headers(),
      body: JSON.stringify(body),
    });
    await handle(res, "updateProduct");
    return res.json();
  },

  deleteProduct: async (id: number) => {
    const res = await fetch(`${INV}/products/${id}/`, {
      method: "DELETE",
      headers: headers(),
    });
    await handle(res, "deleteProduct");
  },
};
