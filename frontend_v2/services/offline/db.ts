import Dexie, { type EntityTable } from 'dexie';

export interface ProductCache {
  id: number;
  tenant_id: number;
  sku: string;
  name_ar: string;
  data: string;
  updated_at: string;
}

export interface PartnerCache {
  id: number;
  tenant_id: number;
  name: string;
  partner_type: string;
  data: string;
  updated_at: string;
}

export interface AccountCache {
  id: number;
  tenant_id: number;
  code: string;
  account_type: string;
  data: string;
  updated_at: string;
}

export interface CurrencyCache {
  id: number;
  Code: string;
  data: string;
  updated_at: string;
}

export interface CategoryCache {
  id: number;
  tenant_id: number;
  name: string;
  data: string;
  updated_at: string;
}

export interface CacheMeta {
  key: string;
  updated_at: string;
}

/**
 * كاش عام لقوائم الـ API (قراءة فقط) — يملؤه `apiGetList` عند كل نجاح شبكة،
 * ويُقرأ عند فشل الشبكة (أوفلاين) لعرض آخر بيانات محفوظة. المفتاح = URL كامل +
 * المستأجر + الفرع (لمنع تداخل الشركات/الفروع على نفس المسار).
 */
export interface ApiListCache {
  url: string;
  data: string;
  updated_at: string;
}

export interface MutationEntry {
  id?: number;
  status: 'pending' | 'syncing' | 'failed' | 'synced';
  created_at: string;
  endpoint: string;
  method: 'POST' | 'PATCH' | 'DELETE';
  body: string;
  tenant_id?: number;
  temp_id?: string;
  error?: string;
}

export interface SyncLogEntry {
  id?: number;
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  message: string;
  payload?: string;
}

export interface IdMapping {
  temp_id: string;
  real_id: number;
  model: string;
  synced_at: string;
}

export interface InvoiceDraft {
  draft_id: string;
  tenant_id: number;
  data: string;
  updated_at: string;
}

const db = new Dexie('ktra_offline') as Dexie & {
  products: EntityTable<ProductCache, 'id'>;
  partners: EntityTable<PartnerCache, 'id'>;
  accounts: EntityTable<AccountCache, 'id'>;
  currencies: EntityTable<CurrencyCache, 'id'>;
  categories: EntityTable<CategoryCache, 'id'>;
  cache_meta: EntityTable<CacheMeta, 'key'>;
  mutation_queue: EntityTable<MutationEntry, 'id'>;
  sync_log: EntityTable<SyncLogEntry, 'id'>;
  id_mappings: EntityTable<IdMapping, 'temp_id'>;
  invoice_drafts: EntityTable<InvoiceDraft, 'draft_id'>;
  api_list_cache: EntityTable<ApiListCache, 'url'>;
};

db.version(1).stores({
  products: 'id, tenant_id, sku, name_ar, [tenant_id+sku]',
  partners: 'id, tenant_id, name, partner_type, [tenant_id+partner_type]',
  accounts: 'id, tenant_id, code, account_type',
  currencies: 'id, Code',
  categories: 'id, tenant_id, name',
  cache_meta: 'key, updated_at',
  mutation_queue: '++id, status, created_at, endpoint, method',
  sync_log: '++id, timestamp, level, message',
  id_mappings: 'temp_id, real_id, model, synced_at',
});

db.version(2).stores({
  invoice_drafts: 'draft_id, tenant_id, updated_at',
});

db.version(3).stores({
  api_list_cache: 'url, updated_at',
});

export default db;
