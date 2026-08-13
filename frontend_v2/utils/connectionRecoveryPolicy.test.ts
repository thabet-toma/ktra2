import assert from "node:assert/strict";
import test from "node:test";

import {
  isKtraCacheName,
  serviceWorkerScopeCoversPage,
} from "./connectionRecoveryPolicy.ts";

test("manual recovery selects only K.T.R.A cache names", () => {
  assert.equal(isKtraCacheName("ktra-static-build123"), true);
  assert.equal(isKtraCacheName("ktra-api-v1"), true);
  assert.equal(isKtraCacheName("workbox-precache-v2"), false);
  assert.equal(isKtraCacheName("another-app"), false);
});

test("manual recovery selects only a same-origin scope covering the page", () => {
  const page = "https://ktra-pro.tech/app/invoices/42";
  assert.equal(
    serviceWorkerScopeCoversPage("https://ktra-pro.tech/app/", page),
    true,
  );
  assert.equal(
    serviceWorkerScopeCoversPage("https://ktra-pro.tech/store/", page),
    false,
  );
  assert.equal(
    serviceWorkerScopeCoversPage("https://other.example/app/", page),
    false,
  );
  assert.equal(serviceWorkerScopeCoversPage("not-a-url", page), false);
});
