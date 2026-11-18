// LEDG-02 parity: the JS canonicaliser reproduces every Python golden vector byte for byte.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CanonicalError, canonicalize, sha256Hex, validate } from "../src/lib/canonical.ts";

type AcceptVector = { name: string; value: unknown; canonical: string; sha256: string };
type RejectVector = { name: string; value: unknown; reason: string };

const raw = readFileSync(new URL("../../tests/fixtures/hash_vectors.json", import.meta.url));
const vectors = JSON.parse(raw.toString("ascii")) as {
  accept: AcceptVector[];
  reject: RejectVector[];
};

const RESEARCH_PROBE_SHA256 = "3274e09024a2561fb06caa533f7727a9e67ae6c7c5e3bfe8fe849233d2c5d99e";

test("vector file has at least 10 accept and 10 reject vectors", () => {
  assert.ok(vectors.accept.length >= 10);
  assert.ok(vectors.reject.length >= 10);
});

test("research probe hashes to the independently verified value", async () => {
  const probe = {
    prev_hash: "0".repeat(64),
    scheme: "calledit-ledger-v1",
    seq: "0",
    test: "researcher-probe-2026-11-18",
  };
  assert.equal(await sha256Hex(canonicalize(probe)), RESEARCH_PROBE_SHA256);
});

for (const vector of vectors.accept) {
  test(`accept: ${vector.name}`, async () => {
    const text = canonicalize(vector.value);
    assert.equal(text, vector.canonical);
    assert.equal(await sha256Hex(text), vector.sha256);
  });
}

for (const vector of vectors.reject) {
  test(`reject: ${vector.name}`, () => {
    assert.throws(() => validate(vector.value), CanonicalError);
    assert.throws(() => canonicalize(vector.value), CanonicalError);
  });
}

test("undefined and non-plain objects are rejected", () => {
  assert.throws(() => validate(undefined), CanonicalError);
  assert.throws(() => validate({ a: new Date(0) }), CanonicalError);
  assert.throws(() => validate({ a: 1n }), CanonicalError);
});
