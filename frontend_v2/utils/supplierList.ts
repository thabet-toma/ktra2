type SupplierWithId = { id: string };

export function mergeSupplier<T extends SupplierWithId>(suppliers: T[], savedSupplier: T): T[] {
  const index = suppliers.findIndex((supplier) => supplier.id === savedSupplier.id);
  if (index < 0) return [...suppliers, savedSupplier];
  return suppliers.map((supplier, i) => i === index ? savedSupplier : supplier);
}
