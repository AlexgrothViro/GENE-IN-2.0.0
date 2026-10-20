import { h, statusPanel } from "./components.js";

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function chartColors() {
  return {
    target: token("--chart-target"), competitor: token("--chart-competitor"), pass: token("--success"),
    blocked: token("--danger"), pending: token("--chart-pending"), depth: token("--chart-depth"),
  };
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function mountPlot(options, label, description) {
  const wrapper = h("div", { class: "chart" });
  if (!globalThis.Plot?.plot) {
    wrapper.append(statusPanel("unavailable", "Gráfico indisponível", "Observable Plot não foi carregado; use a tabela textual abaixo."));
    return wrapper;
  }
  const plot = globalThis.Plot.plot({
    width: 840,
    marginLeft: 72,
    marginBottom: 52,
    style: { background: "transparent", color: "var(--ink-muted)", fontFamily: "var(--font-mono)", fontSize: "11px" },
    ariaLabel: label,
    ariaDescription: description,
    ...options,
  });
  const graphics = plot.matches?.("svg") ? [plot] : [...plot.querySelectorAll("svg")];
  graphics.forEach((graphic) => {
    if (graphic.getAttribute("aria-label") || graphic === graphics.at(-1)) {
      graphic.setAttribute("role", "img");
      graphic.setAttribute("aria-label", label);
      graphic.setAttribute("aria-description", description);
    } else {
      graphic.setAttribute("aria-hidden", "true");
      graphic.setAttribute("focusable", "false");
    }
  });
  wrapper.append(plot);
  return wrapper;
}

export function stageTimelineChart(stages = []) {
  const COLORS = chartColors();
  const rows = stages.map((stage, index) => ({
    ...stage, index, duration: stage.started_at && stage.finished_at
      ? Math.max(0, (new Date(stage.finished_at) - new Date(stage.started_at)) / 1000)
      : null,
  }));
  if (!rows.some((row) => row.duration != null)) return statusPanel("unavailable", "Duração não medida", "As etapas continuam disponíveis na lista textual.");
  return mountPlot({
    x: { label: "Duração (segundos)", grid: true }, y: { label: null },
    marks: [globalThis.Plot.barX(rows, { x: "duration", y: "label", fill: COLORS.target, tip: true })],
  }, "Linha do tempo das etapas", "Duração real em segundos para cada etapa que registrou início e fim.");
}

export function gateMatrixChart(gates = []) {
  const COLORS = chartColors();
  if (!gates.length) return statusPanel("empty", "Nenhum gate informado", "Não há gates para representar nesta execução.");
  const rows = gates.map((gate) => ({ ...gate, value: String(gate.status).toUpperCase() === "PASS" ? 1 : 0 }));
  return mountPlot({
    height: Math.max(240, rows.length * 30 + 90),
    marginLeft: 200,
    x: { domain: [0, 1], ticks: 1, label: "0 bloqueado · 1 passou", grid: true }, y: { label: null },
    color: { domain: ["PASS", "BLOCKED", "NOT_EVALUABLE"], range: [COLORS.pass, COLORS.blocked, COLORS.pending], legend: true },
    marks: [globalThis.Plot.dot(rows, { x: "value", y: "gate_id", fill: "status", r: 8, tip: true })],
  }, "Matriz de gates", "Cada gate aparece como passou, bloqueado ou não avaliável; os motivos estão na tabela seguinte.");
}

export function coverageChart(rows = []) {
  const COLORS = chartColors();
  const data = rows.flatMap((row) => [
    { reference_id: row.reference_id || "não informado", measure: "Cobertura 1×", value: number(row.breadth_1x) },
    { reference_id: row.reference_id || "não informado", measure: "Cobertura 3×", value: number(row.breadth_3x) },
  ]).filter((row) => row.value != null);
  if (!data.length) return statusPanel("unavailable", "Cobertura não medida", "Nenhum valor numérico de cobertura está disponível.");
  return mountPlot({
    x: { label: "Fração da referência", domain: [0, 1], percent: true, grid: true }, y: { label: null },
    color: { domain: ["Cobertura 1×", "Cobertura 3×"], range: [COLORS.target, COLORS.depth], legend: true },
    marks: [globalThis.Plot.barX(data, { x: "value", y: "reference_id", fill: "measure", fx: "measure", tip: true })],
  }, "Cobertura por referência", "Pequenos múltiplos de cobertura 1× e 3×, expressos como fração da referência.");
}

export function supportChart(rows = []) {
  const COLORS = chartColors();
  const data = rows.flatMap((row) => [
    { locus: row.locus_id || row.reference_id || "não informado", measure: "Templates únicos", value: number(row.unique_templates) },
    { locus: row.locus_id || row.reference_id || "não informado", measure: "Inícios distintos", value: number(row.distinct_starts) },
    { locus: row.locus_id || row.reference_id || "não informado", measure: "Pares próprios", value: number(row.proper_pair_templates) },
  ]).filter((row) => row.value != null);
  if (!data.length) return statusPanel("unavailable", "Suporte não medido", "A tabela permanece disponível sem conversão de ausência em zero.");
  return mountPlot({
    x: { label: "Contagem absoluta", grid: true }, y: { label: null },
    color: { domain: ["Templates únicos", "Inícios distintos", "Pares próprios"], range: [COLORS.target, COLORS.depth, COLORS.competitor], legend: true },
    marks: [globalThis.Plot.barX(data, { x: "value", y: "locus", fill: "measure", fx: "measure", tip: true })],
  }, "Suporte por locus", "Contagens absolutas de templates únicos, inícios distintos e pares próprios para cada locus.");
}

export function competitiveChart(rows = []) {
  const COLORS = chartColors();
  const data = rows.flatMap((row) => [
    { query: row.qseqid || "não informado", series: "Alvo", value: number(row.target_bitscore) },
    { query: row.qseqid || "não informado", series: "Competidor", value: number(row.competitor_bitscore) },
  ]).filter((row) => row.value != null);
  if (!data.length) return statusPanel("unavailable", "Especificidade não avaliada", "Não há bitscores numéricos para alvo e competidor.");
  return mountPlot({
    x: { label: "Bitscore absoluto", grid: true }, y: { label: null },
    color: { domain: ["Alvo", "Competidor"], range: [COLORS.target, COLORS.competitor], legend: true },
    marks: [globalThis.Plot.barX(data, { x: "value", y: "query", fill: "series", fx: "series", tip: true })],
  }, "Especificidade competitiva", "Bitscores absolutos do alvo e do melhor competidor para cada sequência consultada.");
}

export function locusIntervalChart(rows = []) {
  const COLORS = chartColors();
  const data = rows.map((row) => ({
    reference: row.sseqid || row.reference_id || "não informado",
    locus: row.locus_id || row.hsp_id || "locus",
    start: number(row.reference_start ?? row.subject_start),
    end: number(row.reference_end ?? row.subject_end),
  })).filter((row) => row.start != null && row.end != null);
  if (!data.length) return statusPanel("empty", "Nenhum intervalo recuperado", "Não há coordenadas de loci ou HSPs para esta seleção.");
  return mountPlot({
    x: { label: "Coordenada na referência (pb)", grid: true }, y: { label: null },
    marks: [globalThis.Plot.rectX(data, { x1: "start", x2: "end", y: "reference", fill: COLORS.target, inset: 3, tip: true })],
  }, "Mapa intervalar de loci", "Intervalos em pares de bases por referência; valores exatos permanecem na tabela.");
}

export function comparisonMetricChart(runs = [], key, label) {
  const COLORS = chartColors();
  const data = runs.map((run) => ({ run: run.run_id, value: number(run.metrics?.[key]) })).filter((row) => row.value != null);
  if (!data.length) return statusPanel("unavailable", `${label} não medido`, "Nenhuma execução possui valor numérico para esta métrica.");
  return mountPlot({
    y: { label: label, grid: true, zero: true }, x: { label: "Execução" },
    marks: [globalThis.Plot.barY(data, { x: "run", y: "value", fill: COLORS.target, tip: true }), globalThis.Plot.ruleY([0])],
  }, `${label} por execução`, `Valores absolutos de ${label} para as execuções selecionadas.`);
}
