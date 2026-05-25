import db from './db';

export async function cleanOldCache(maxAgeDays: number): Promise<number> {
  const cutoff = new Date(Date.now() - maxAgeDays * 86400_000).toISOString();
  let deleted = 0;

  const stores = ['products', 'partners', 'accounts', 'currencies', 'categories'] as const;
  for (const store of stores) {
    const old = await (db[store] as any)
      .where('updated_at')
      .below(cutoff)
      .toArray();
    for (const item of old) {
      await (db[store] as any).delete(item.id);
      deleted++;
    }
  }

  const oldLogs = await db.sync_log
    .where('timestamp')
    .below(cutoff)
    .toArray();
  for (const log of oldLogs) {
    await db.sync_log.delete(log.id!);
    deleted++;
  }

  return deleted;
}

export async function clearAllCache(): Promise<void> {
  const stores = ['products', 'partners', 'accounts', 'currencies', 'categories'] as const;
  for (const store of stores) {
    await (db[store] as any).clear();
  }
  await db.cache_meta.clear();
}
