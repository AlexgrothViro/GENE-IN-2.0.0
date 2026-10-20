import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { elapsed, evidenceLabel, formatDate, jobLabel, normalizeStatus, runIdentity } from "../js/adapters.js";
import { createElement, replaceContent, setText } from "../js/dom.js";
import { analysisDimensions, outcomePanel } from "../js/components.js";
import { parseRoute, routeHref, startRouter } from "../js/router.js";
import { ACTIVE_JOB_STORAGE_KEY, createStore, loadActiveJob, persistActiveJob } from "../js/state.js";
import { postForm } from "../js/api.js";

test("upload preserves form bytes, reports progress and retains HTTP errors", async () => {
  const previous = globalThis.XMLHttpRequest;
  let instance;
  globalThis.XMLHttpRequest = class {
    constructor() { this.upload = {}; instance = this; }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader() {}
    getResponseHeader() { return "application/json"; }
    send(body) { this.body = body; }
  };
  try {
    const body = { original: "unchanged form" }, progress = [];
    const response = postForm("/api/import-upload", body, (...values) => progress.push(values));
    assert.equal(instance.body, body);
    instance.upload.onprogress({ loaded: 5, total: 10, lengthComputable: true });
    instance.upload.onload();
    instance.status = 200;
    instance.responseText = '{"sample_id":"sample"}';
    instance.onload();
    assert.deepEqual(await response, { sample_id: "sample" });
    assert.deepEqual(progress, [[5, 10], [null, null]]);
    const rejected = postForm("/api/import-upload", body, () => {});
    instance.status = 409;
    instance.responseText = '{"error":"Confirme a substituição"}';
    instance.onload();
    await assert.rejects(rejected, error => error.status === 409 && error.message === "Confirme a substituição");
  } finally { globalThis.XMLHttpRequest = previous; }
});

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const MODULE_DIR = path.join(TEST_DIR, "..", "js");

function fakeDocument() {
  return {
    createElement(tagName) {
      return {
        tagName: tagName.toUpperCase(), attributes: new Map(), children: [], dataset: {}, className: "", textContent: "",
        setAttribute(name, value) { this.attributes.set(name, String(value)); },
        getAttribute(name) { return this.attributes.get(name) || null; },
        addEventListener() {}, append(...children) { this.children.push(...children); },
      };
    },
    createTextNode(value) { return { nodeType: 3, textContent: String(value) }; },
  };
}

test("recovery labels never turn a candidate into confirmed viral detection", () => {
  assert.equal(evidenceLabel("DETECTED"), "Candidatos para revisão");
  assert.equal(evidenceLabel("EVIDENCE_RECOVERED"), "Candidatos para revisão");
  assert.equal(evidenceLabel("NO_SIGNAL"), "Sem candidatos para revisão");
  assert.equal(evidenceLabel("NOT_EVALUABLE"), "Não avaliável");
});

test("rendered dimensions explain recovery in both user flows", () => {
  const previous = globalThis.document;
  const previousNode = globalThis.Node;
  globalThis.document = fakeDocument();
  globalThis.Node = class {};
  const text = (node) => [node.textContent || "", ...(node.children || []).map(text)].join(" ");
  try {
    const dimensions = text(analysisDimensions({ evidence_level: "DETECTED" }));
    assert.match(dimensions, /Candidatos para revisão/);
    assert.doesNotMatch(dimensions, /CANDIDATOS_PARA_REVISAO/);
    assert.doesNotMatch(dimensions, /DETECTED/);
    assert.match(text(outcomePanel("EVIDENCE_RECOVERED")), /não confirma origem viral nem espécie/);
  } finally { globalThis.document = previous; globalThis.Node = previousNode; }
});

test("router defaults safely and preserves repeated comparison runs", () => {
  assert.equal(parseRoute("").route, "home");
  assert.equal(parseRoute("#/unknown").route, "home");
  const parsed = parseRoute("#/compare?run=a&run=b");
  assert.equal(parsed.route, "compare");
  assert.deepEqual(parsed.params.getAll("run"), ["a", "b"]);
  assert.equal(routeHref("analytics", { run: "run 1" }), "#/analytics?run=run+1");
});

test("router registers and removes one hash listener", () => {
  const listeners = [];
  const removed = [];
  const win = {
    location: { hash: "#/home" },
    addEventListener(type, callback) { listeners.push([type, callback]); },
    removeEventListener(type, callback) { removed.push([type, callback]); },
  };
  const stop = startRouter(() => {}, win);
  assert.equal(listeners.length, 1);
  stop();
  assert.deepEqual(removed, listeners);
});

test("single store owns nested route, context, job and analytical state", () => {
  const store = createStore({ route: "home", context: { sample: "" }, analytics: { rows: [] } });
  let notifications = 0;
  const unsubscribe = store.subscribe(() => { notifications += 1; });
  store.set({ route: "analytics", context: { sample: "A" } });
  assert.deepEqual(store.get(), { route: "analytics", context: { sample: "A" }, analytics: { rows: [] } });
  assert.equal(notifications, 1);
  unsubscribe();
});

test("status adapter covers active, terminal, partial and incompatible states", () => {
  assert.equal(normalizeStatus("queued"), "running");
  assert.equal(normalizeStatus("done_with_warning"), "partial");
  assert.equal(normalizeStatus("LEGACY_INCOMPATIBLE"), "failed");
  assert.equal(jobLabel("cancelled"), "Cancelada");
  assert.equal(jobLabel("not_started"), "Não iniciada");
  assert.equal(runIdentity({ run_id: "r", status: "done", evidence_v2: true }).evidence, true);
  const official = runIdentity({ run_id: "r2", action: "pipeline", run_dir: "run-r2", paths: { run_report: "report.md" } });
  assert.equal(official.action, "pipeline");
  assert.equal(official.runDir, "run-r2");
  assert.deepEqual(official.paths, { run_report: "report.md" });
});

test("active job survives route changes and reloads in session storage", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  const job = persistActiveJob({ id: "job-1", status: "queued", startedAt: "2026-08-24T10:00:00Z" }, storage);
  assert.equal(values.has(ACTIVE_JOB_STORAGE_KEY), true);
  assert.deepEqual(loadActiveJob(storage), job);
  persistActiveJob(null, storage);
  assert.equal(loadActiveJob(storage), null);
  values.set(ACTIVE_JOB_STORAGE_KEY, "not-json");
  assert.equal(loadActiveJob(storage), null);
});

test("elapsed time uses recorded timestamps and never invents an ETA", () => {
  assert.equal(elapsed("2026-08-24T10:00:00Z", "2026-08-24T11:02:03Z"), "1h 2min");
  assert.equal(elapsed(null), "Não medido");
  assert.match(formatDate("2026-08-24T10:00:00Z"), /24\/08\/2026/);
});

test("DOM helpers keep hostile backend text inert", () => {
  const doc = fakeDocument();
  const payload = "<img src=x onerror=alert(1)>";
  const node = createElement(doc, "div", { title: payload }, [payload]);
  assert.equal(node.attributes.get("title"), payload);
  assert.equal(node.children[0].textContent, payload);
  const container = { children: ["old"], replaceChildren() { this.children = []; }, append(...children) { this.children.push(...children); } };
  replaceContent(container, node);
  setText(node, payload);
  assert.deepEqual(container.children, [node]);
  assert.equal(node.textContent, payload);
});

test("application modules never assign innerHTML or use a CDN", () => {
  for (const name of fs.readdirSync(MODULE_DIR).filter((item) => item.endsWith(".js"))) {
    const source = fs.readFileSync(path.join(MODULE_DIR, name), "utf8");
    assert.equal(/\.innerHTML\s*=/.test(source), false, `${name} must not assign innerHTML`);
    assert.equal(/https?:\/\//.test(source), false, `${name} must stay offline`);
  }
  const html = fs.readFileSync(path.join(TEST_DIR, "..", "index.html"), "utf8");
  assert.match(html, /observable-plot-0\.6\.17\.min\.js/);
  assert.doesNotMatch(html, /https?:\/\//);
  assert.equal((html.match(/<script type="module"/g) || []).length, 1);
});

test("home uses the Gene-In masthead and route list instead of generic marketing copy", () => {
  const operational = fs.readFileSync(path.join(MODULE_DIR, "operational.js"), "utf8");
  const html = fs.readFileSync(path.join(TEST_DIR, "..", "index.html"), "utf8");
  assert.match(operational, /gi-masthead/);
  assert.match(operational, /hero-bg\.png/);
  assert.match(operational, /gi-routes/);
  assert.match(operational, /Recuperação de sequências candidatas para revisão/);
  assert.match(operational, /caso-modelo de validação/);
  assert.doesNotMatch(operational, /Da amostra ao resultado/);
  assert.doesNotMatch(operational, /Próxima ação/);
  assert.match(html, /gi-appbar__brand[\s\S]*gene-in-logo\.png/);
  assert.match(html, /<title>Gene-In · Candidatos para revisão<\/title>/);
  assert.doesNotMatch(html, /Análises virais/);
  assert.doesNotMatch(html, /width="40" height="40"/);
});

test("sample import remains available in the guided flow", () => {
  const operational = fs.readFileSync(path.join(MODULE_DIR, "operational.js"), "utf8");
  assert.match(operational, /\/api\/import-upload/);
  assert.match(operational, /import_sample/);
  assert.match(operational, /zipfile/);
  assert.match(operational, /Importar por caminho/);
  assert.match(operational, /Gerar amostra DEMO/);
});

test("custom NCBI database remains available outside the catalog", () => {
  const operational = fs.readFileSync(path.join(MODULE_DIR, "operational.js"), "utf8");
  const advanced = fs.readFileSync(path.join(MODULE_DIR, "advanced.js"), "utf8");
  assert.match(operational, /Outro vírus \/ banco customizado — query NCBI/);
  assert.match(operational, /db_query/);
  assert.match(operational, /CUSTOM_DATABASE/);
  assert.match(advanced, /Outro vírus \/ banco customizado — query NCBI/);
  assert.match(advanced, /build-db-query/);
  assert.match(advanced, /build-db-taxid/);
  assert.match(advanced, /contig-db-query/);
  assert.match(advanced, /db_query: query/);
});

test("analysis communication preserves dimensions and integrity status", () => {
  const components = fs.readFileSync(path.join(MODULE_DIR, "components.js"), "utf8");
  const operational = fs.readFileSync(path.join(MODULE_DIR, "operational.js"), "utf8");
  const analytics = fs.readFileSync(path.join(MODULE_DIR, "analytics.js"), "utf8");
  for (const dimension of [
    "execution_status", "analysis_outcome", "evidence_level",
    "promotion_status", "control_status", "reported_conclusion",
  ]) {
    assert.match(components, new RegExp(dimension));
  }
  assert.match(operational, /evidence_pipeline/);
  assert.match(analytics, /condições configuradas/);
  assert.match(analytics, /if \(!summary\.validation\.valid\) return root/);
  assert.match(analytics, /Caveats indisponíveis/);
  assert.match(analytics, /validador de integridade/);
  assert.doesNotMatch(`${components}\n${analytics}\n${operational}`, /SHADOW_ONLY|teto público|canonical-e1/);
  assert.doesNotMatch(operational, /action: "pipeline"/);
  assert.doesNotMatch(`${components}\n${analytics}\n${operational}`, /é um resultado negativo/);
  assert.doesNotMatch(`${components}\n${analytics}`, /ausência viral"/);
});

test("visual system exposes one token root and required semantic states", () => {
  const read = (name) => fs.readFileSync(path.join(TEST_DIR, "..", name), "utf8");
  const tokens = read("tokens.css");
  const components = read("gene-in.css");
  const css = read("styles.css");
  const all = `${tokens}\n${components}\n${css}`;
  assert.equal((tokens.match(/:root, \[data-theme="light"\]\s*\{/g) || []).length, 1);
  assert.equal((tokens.match(/^\[data-theme="dark"\]\s*\{/gm) || []).length, 1);
  assert.doesNotMatch(css, /:root\s*\{/);
  for (const state of ["loading", "empty", "unavailable", "blocked", "running", "done", "no_evidence", "not_evaluable", "failed", "cancelled", "partial", "shadow", "experimental", "not_applicable"]) {
    assert.match(all, new RegExp(`data-state=["']${state}["']`));
  }
  for (const outcome of ["EVIDENCE_RECOVERED", "NO_EVIDENCE_RECOVERED", "NOT_EVALUABLE"]) {
    assert.match(components, new RegExp(`data-outcome=["']${outcome}["']`));
  }
  assert.match(all, /prefers-reduced-motion/);
  assert.match(css, /advanced-entry--desktop/);
  assert.match(css, /primary-nav \.advanced-entry--mobile/);
  assert.match(css, /\.chart svg\[role="img"\]/);
  assert.doesNotMatch(css, /\.chart svg\s*\{/);
  assert.doesNotMatch(css, /Inter|box-shadow:\s*0/);
  assert.doesNotMatch(`${tokens}${components}${css}`, /https?:\/\//);
  assert.match(tokens, /url\("\/vendor\/fonts\//);
  const html = read("index.html");
  assert.match(html, /<html lang="pt-BR" data-theme="light">/);
  assert.match(html, /href="\/tokens\.css"[\s\S]*href="\/gene-in\.css"[\s\S]*href="\/styles\.css"/);
  assert.match(html, /<body class="gi-page">/);
  assert.match(html, /advanced-entry advanced-entry--mobile/);
  assert.match(html, /advanced-entry advanced-entry--desktop/);
  assert.match(html, /gene-in-logo\.png/);
  assert.match(html, /rel="icon" href="\/gene-in-symbol\.png"/);
  assert.doesNotMatch(html, /background:\s*#000/);
  for (const cell of ["environment", "database", "sample", "job"]) assert.match(html, new RegExp(`id="context-${cell}-cell"[^>]*data-state=`));
});

test("interface modules carry no emoji and read chart colors from tokens", () => {
  for (const name of fs.readdirSync(MODULE_DIR).filter((item) => item.endsWith(".js"))) {
    const source = fs.readFileSync(path.join(MODULE_DIR, name), "utf8");
    assert.doesNotMatch(source, /\p{Extended_Pictographic}(?<![✓✕×↻■◇△○—])/u, `${name} must not contain emoji`);
  }
  const charts = fs.readFileSync(path.join(MODULE_DIR, "charts.js"), "utf8");
  assert.doesNotMatch(charts, /#[0-9a-f]{6}/i);
  for (const name of ["--chart-target", "--chart-competitor", "--chart-depth", "--chart-pending", "--success", "--danger"]) {
    assert.match(charts, new RegExp(name));
  }
});
