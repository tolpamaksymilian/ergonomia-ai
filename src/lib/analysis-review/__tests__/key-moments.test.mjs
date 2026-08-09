import assert from "node:assert/strict";
import test from "node:test";

import { rankAndDeduplicateKeyMoments } from "../key-moments.ts";

const moment = (id, time, rank, quality = 0.8) => ({ id, time, rank, quality, category: "posture", title: id, description: id, value: null, unit: null, bodyArea: null });

test("key moments use deterministic ranking and time deduplication", () => {
  const result = rankAndDeduplicateKeyMoments([
    moment("weaker-nearby", 1.2, 40),
    moment("strongest", 1, 90),
    moment("later", 4, 50),
  ], { minimumGapSeconds: 0.75, limit: 10 });
  assert.deepEqual(result.map((item) => item.id), ["strongest", "later"]);
});

test("key moment limit is enforced", () => {
  const result = rankAndDeduplicateKeyMoments(Array.from({ length: 20 }, (_, index) => moment(String(index), index * 2, 100 - index)), { limit: 6 });
  assert.equal(result.length, 6);
});
