import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the IndiaAQBench product preview", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>IndiaAQBench/i);
  assert.match(html, /illustrative data only/i);
  assert.match(html, /Four days of air-quality context/i);
  assert.match(html, /Experimental research/i);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape/i);
});

test("keeps public claims and demo boundaries in source", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /illustrative data only/i);
  assert.match(page, /not official health guidance/i);
  assert.match(page, /Awaiting full benchmark/i);
  assert.match(page, /Delhi is not the target/i);
  assert.match(page, /CAMS \(planned\)/i);
  assert.match(page, /"corrected" \| "raw_aurora" \| "cams_forecast"/);
  assert.match(page, /limited-data or method-unavailable state/i);
  assert.match(page, /POD · FAR · CSI/);
  assert.match(layout, /underserved Indian cities/i);
  assert.match(packageJson, /"name": "indiaaqbench-web"/);
  assert.doesNotMatch(page, /_sites-preview|SkeletonPreview/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});
