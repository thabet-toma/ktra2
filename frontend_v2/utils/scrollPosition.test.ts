import assert from "node:assert/strict";
import test from "node:test";

import { captureScrollPosition, restoreScrollPosition } from "./scrollPosition.ts";

test("restores the actual app scroll container after a data refresh", () => {
  const container = { scrollTop: 640 };
  const snapshot = captureScrollPosition(container, 15);
  container.scrollTop = 0;

  restoreScrollPosition(snapshot, () => {
    throw new Error("window fallback must not run for app-content");
  });

  assert.equal(container.scrollTop, 640);
});

test("falls back to the window position when there is no app scroll container", () => {
  const snapshot = captureScrollPosition(null, 90);
  let restoredWindowTop = 0;

  restoreScrollPosition(snapshot, (top) => { restoredWindowTop = top; });

  assert.equal(restoredWindowTop, 90);
});
