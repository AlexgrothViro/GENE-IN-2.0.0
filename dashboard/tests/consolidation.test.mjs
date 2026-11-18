import assert from "node:assert/strict";
import test from "node:test";
import { comparisonMetricValue } from "../js/adapters.js";
import { ValidationPendingError, waitForValidation } from "../js/api.js";

test("comparison preserves measured zero and does not alter source metrics", () => {
  const run = { metrics: { breadth_1x: 0, candidate_count: 0 }, datasets: { coverage: { status: "empty" } } };
  const original = JSON.stringify(run);
  assert.equal(comparisonMetricValue(run, "breadth_1x"), 0);
  assert.equal(comparisonMetricValue(run, "candidate_count"), 0);
  assert.equal(JSON.stringify(run), original);
});

test("comparison distinguishes absent, unmeasured, inapplicable and invalid coverage", () => {
  for (const [status, expected] of Object.entries({ not_measured: "Não medido", missing: "Não medido", not_applicable: "Não aplicável", invalid: "Inválido" })) {
    const run = { metrics: { breadth_1x: 0 }, datasets: { coverage: { status } } };
    assert.equal(comparisonMetricValue(run, "breadth_1x"), expected);
    assert.equal(run.metrics.breadth_1x, 0);
  }
  assert.equal(comparisonMetricValue({ metrics: {} }, "breadth_1x"), "Não medido");
  assert.equal(comparisonMetricValue({ metrics: { qualification_status: "NOT_EVALUATED" } }, "qualification_status"), "Não avaliado");
});

test("pending inspection becomes its valid result without manual reload", async () => {
  let calls = 0, pending = 0;
  const final = { validation: { status: "EVIDENCE_VALID", valid: true } };
  const result = await waitForValidation(async () => ++calls === 1 ? { validation: { status: "VALIDATION_PENDING" } } : final,
    { intervalMs: 0, onPending: () => pending++ });
  assert.equal(result, final);
  assert.equal(calls, 2);
  assert.equal(pending, 1);
});

test("invalid inspection is terminal and is not retried into success", async () => {
  let calls = 0;
  const invalid = { validation: { status: "EVIDENCE_INVALID", valid: false } };
  assert.equal(await waitForValidation(async () => { calls++; return invalid; }), invalid);
  assert.equal(calls, 1);
});

test("inspection polling has a finite limit and keeps pending distinct from invalid", async () => {
  let calls = 0;
  await assert.rejects(waitForValidation(async () => { calls++; return { validation: { status: "VALIDATION_PENDING" } }; },
    { maxAttempts: 2, intervalMs: 0 }), ValidationPendingError);
  assert.equal(calls, 2);
});

test("leaving a page aborts pending inspection without another request", async () => {
  let calls = 0;
  const controller = new AbortController();
  const result = waitForValidation(async () => { calls++; return { validation: { status: "VALIDATION_PENDING" } }; },
    { signal: controller.signal, intervalMs: 5000, onPending: () => setTimeout(() => controller.abort(), 0) });
  await assert.rejects(result, { name: "AbortError" });
  assert.equal(calls, 1);
});

test("aborted page and network failure do not produce a successful inspection", async () => {
  const controller = new AbortController();
  controller.abort();
  let called = false;
  await assert.rejects(waitForValidation(async () => { called = true; }, { signal: controller.signal }), { name: "AbortError" });
  assert.equal(called, false);
  await assert.rejects(waitForValidation(async () => { throw new Error("network unavailable"); }), /network unavailable/);
});
