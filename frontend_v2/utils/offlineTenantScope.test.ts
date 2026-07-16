import assert from "node:assert/strict";
import test from "node:test";

import {
  isOfflineRecordForTenant,
  tenantScopedOfflineKey,
} from "./offlineTenantScope.ts";

test("offline rows belong only to their explicit tenant", () => {
  assert.equal(isOfflineRecordForTenant({ tenant_id: 3 }, 3), true);
  assert.equal(isOfflineRecordForTenant({ tenant_id: 4 }, 3), false);
  assert.equal(isOfflineRecordForTenant({}, 3), false);
});

test("offline draft and metadata keys differ across tenants", () => {
  assert.equal(tenantScopedOfflineKey(3, "new"), "3:new");
  assert.notEqual(
    tenantScopedOfflineKey(3, "new"),
    tenantScopedOfflineKey(4, "new"),
  );
});
