import assert from "node:assert/strict";
import test from "node:test";
import { mergeSupplier } from "./supplierList.ts";

test("adds a supplier created during the current deal session to the searchable list", () => {
  const suppliers = [{ id: "1", tradeName: "المورد القديم", type: "factory" }];
  const created = { id: "2", tradeName: "Chengdu Sunrise Electric", type: "factory" };

  const merged = mergeSupplier(suppliers, created);
  const searchResults = merged.filter((supplier) =>
    supplier.type === "factory" && supplier.tradeName.toLowerCase().includes("chengdu"));

  assert.deepEqual(merged, [suppliers[0], created]);
  assert.deepEqual(searchResults, [created]);
});

test("replaces a matching supplier instead of duplicating it", () => {
  const suppliers = [{ id: "1", tradeName: "اسم قديم", type: "factory" }];
  const saved = { id: "1", tradeName: "اسم محدّث", type: "factory" };

  assert.deepEqual(mergeSupplier(suppliers, saved), [saved]);
});
