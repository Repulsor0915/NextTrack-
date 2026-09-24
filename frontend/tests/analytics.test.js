import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const analyticsRoot = new URL("../static/frontend/analytics/", import.meta.url);

test("the published Analytics snapshot and figures match V2", async () => {
  const snapshot = JSON.parse(
    await readFile(new URL("snapshot.json", analyticsRoot), "utf8"),
  );

  assert.equal(snapshot.schema_version, "nexttrack-analytics-snapshot-v2");
  assert.equal(snapshot.catalogue.version, "spotify-merged-v2");
  assert.equal(snapshot.protocol.scenario_count, 12);
  assert.deepEqual(
    snapshot.methods.map((row) => row.method),
    ["random", "cbf", "context_no_mmr", "context_mmr"],
  );
  assert.equal(snapshot.figures.length, 5);

  for (const figure of snapshot.figures) {
    const contents = await readFile(new URL(figure.path, analyticsRoot));
    const checksum = createHash("sha256").update(contents).digest("hex");
    assert.equal(checksum, figure.sha256, figure.path);
  }
});
