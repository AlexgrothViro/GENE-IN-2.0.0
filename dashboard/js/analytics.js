import { getJSON } from "./api.js";
import { analysisDimensions, badge, button, buttonClass, dataTable, field, h, linkButton, metric, outcomePanel, pageHeader, panel, statusPanel, toast } from "./components.js";
import { advancedShell } from "./advanced.js";
import { competitiveChart, comparisonMetricChart, coverageChart, gateMatrixChart, locusIntervalChart, stageTimelineChart, supportChart } from "./charts.js";
import { elapsed, evidenceLabel, formatDate } from "./adapters.js";

const DATASET_LABELS = {
  coverage: "Cobertura 1×/3× e profundidade", read_support: "Suporte por templates",
  fragment_evidence: "Fragmentos", hsp_evidence: "HSPs", locus_evidence: "Loci",
  competitive_hits: "Especificidade competitiva", template_lineage: "Linhagem e UMI",
};

function valueCard(label, value, hint = "") {
  return metric(label, value, hint);
}

function isNumericColumn(rows, key) {
  const values = rows.map((row) => row[key]).filter((value) => value != null && value !== "");
  return values.length > 0 && values.every((value) => typeof value === "number" || (typeof value === "string" && /^-?\d+(\.\d+)?(e-?\d+)?$/i.test(value.trim())));
}

function analyticsStatus(summary) {
  const block = h("div", { class: "stack" });
  if (!summary.validation.valid) {
    block.append(statusPanel("not_evaluable", "Execução não avaliável", summary.validation.message || "Os artefatos não passaram na validação integral."));
    block.append(outcomePanel("NOT_EVALUABLE"));
    return block;
  }
  const outcome = outcomePanel(summary.metadata.analysis_outcome);
  if (outcome) block.append(outcome);
  else block.append(statusPanel("success", "Artefatos validados", "Os dados abaixo são leituras dos artefatos verificados."));
  return block;
}

function gateTable(gates) {
  return dataTable([
    { key: "gate_id", label: "Gate" },
    { key: "status", label: "Estado", render: (row) => badge(row.status, row.status) },
    { key: "reason", label: "Motivo" },
  ], gates, "Gates e motivos");
}

function analysisSummary(summary) {
  const section = h("section", { class: "grid grid--2" });
  const decision = panel("Resumo da análise", [], "article");
  decision.append(analysisDimensions({
    execution_status: summary.metadata.execution_status,
    analysis_outcome: summary.metadata.analysis_outcome,
    evidence_level: summary.metadata.evidence_level,
    promotion_status: summary.metadata.promotion_status || summary.promotion_summary?.status,
    control_status: summary.controls?.status,
    reported_conclusion: summary.metadata.reported_conclusion,
  }));
  decision.append(statusPanel(
    summary.validation.valid ? "empty" : "not_evaluable",
    "Validação dos artefatos",
    summary.validation.valid
      ? `${summary.validation.status}: conjunto verificado pelo validador de integridade.`
      : `${summary.validation.status}: ${summary.validation.message || "apresentação fechada como não avaliável."}`,
  ));
  const caveats = panel("Caveats e controles", [], "article");
  if (!summary.validation.valid) {
    caveats.append(statusPanel(
      "not_evaluable",
      "Caveats indisponíveis",
      "Artefatos inválidos ou incompletos não são interpretados nem convertidos em ausência de achados.",
    ));
    section.append(decision, caveats);
    return section;
  }
  if (summary.controls?.status) {
    caveats.append(statusPanel(
      summary.controls.status === "CONTROL_ASSOCIATED_SIGNAL" ? "warning" : "empty",
      `control_status=${summary.controls.status}`,
      summary.controls.explanation || summary.explanations?.[summary.controls.status] || "Estado lido do artefato validado, sem inferência adicional.",
    ));
  }
  if (summary.caveats?.length) {
    const list = h("ul");
    summary.caveats.forEach((item) => list.append(h("li", { text: item })));
    caveats.append(list);
  } else caveats.append(statusPanel("empty", "Nenhum caveat registrado", "O artefato validado não forneceu caveats adicionais."));
  section.append(decision, caveats);
  return section;
}

function candidateSection(summary) {
  const section = panel("Candidatos");
  const promotion = summary.promotion_summary || {};
  const availability = summary.availability_summary || {};
  section.append(h("div", { class: "gi-metrics" }, [
    valueCard("Candidatos", promotion.total), valueCard("Disponíveis para revisão", availability.available ?? promotion.total),
  ]));
  section.append(h("p", { text: "Disponibilidade para revisão não confirma origem viral nem espécie. A qualificação científica não foi avaliada." }));
  if (summary.candidates?.length) section.append(dataTable([
    { key: "candidate_id", label: "Candidato" }, { key: "reference_id", label: "Referência" },
    { key: "candidate_class", label: "Classe" },
    { key: "promotion_status", label: "Disponibilidade", render: (row) => badge(row.promotion_status, row.promotion_status) },
    { key: "specificity_status", label: "Especificidade no painel" },
    { key: "taxonomic_status", label: "Atribuição taxonômica no painel" },
  ], summary.candidates, "Candidatos e disponibilidade"));
  else section.append(statusPanel("empty", "Nenhum candidato recuperado", "A execução não produziu candidatos nas condições configuradas."));
  return section;
}

function provenanceSection(summary) {
  const provenance = summary.provenance || {};
  const rows = Object.entries(provenance).map(([key, value]) => ({
    key, value: typeof value === "object" ? JSON.stringify(value) : value,
  }));
  const section = panel("Proveniência");
  if (rows.length) section.append(dataTable([{ key: "key", label: "Campo" }, { key: "value", label: "Valor" }], rows, "Proveniência da evidência"));
  else section.append(statusPanel("empty", "Proveniência não disponível", "A execução não expôs proveniência validada."));
  return section;
}

async function datasetSection(summary, dataset) {
  const card = panel(DATASET_LABELS[dataset]);
  const info = summary.datasets[dataset];
  if (!info || !["available", "empty"].includes(info.status)) {
    const state = info?.status === "not_measured" ? "unavailable" : info?.status === "not_applicable" ? "empty" : info?.status || "unavailable";
    const title = info?.status === "invalid" ? "Artefato inválido" : info?.status === "not_applicable" ? "Não aplicável" : info?.status === "empty" ? "Conjunto vazio" : "Dados indisponíveis";
    const detail = info?.status === "missing" ? "Artefato ausente." : info?.status === "not_applicable" ? "A mensuração não se aplica a esta execução." : info?.status === "empty" ? "O artefato é válido e não contém linhas de dados." : "Não medido para esta execução.";
    card.append(statusPanel(state === "invalid" ? "not_evaluable" : state, title, detail));
    return card;
  }
  const payload = await getJSON(`/api/evidence/analytics/dataset?run=${encodeURIComponent(summary.run_id)}&dataset=${encodeURIComponent(dataset)}&limit=500`);
  if (!payload.rows.length) {
    card.append(statusPanel("empty", "Conjunto vazio", "O artefato é válido e não contém linhas de dados."));
    return card;
  }
  if (dataset === "coverage") card.append(coverageChart(payload.rows));
  if (dataset === "read_support") card.append(supportChart(payload.rows));
  if (dataset === "competitive_hits") card.append(competitiveChart(payload.rows));
  if (["locus_evidence", "hsp_evidence"].includes(dataset)) card.append(locusIntervalChart(payload.rows));
  if (payload.truncated) card.append(statusPanel("warning", "Conteúdo truncado", "Use filtros de referência ou locus; nenhuma amostragem silenciosa foi aplicada."));
  card.append(dataTable(payload.columns.map((key) => ({ key, label: key, numeric: isNumericColumn(payload.rows, key) })), payload.rows, DATASET_LABELS[dataset]));
  card.append(h("div", { class: "gi-btnrow" }, linkButton("Abrir artefato original", payload.artifact, "secondary")));
  return card;
}

function lazyDatasetSection(summary, dataset) {
  const details = h("details", { class: "gi-analytics-data" }, [
    h("summary", { text: `${DATASET_LABELS[dataset]} · abrir gráfico e dados` }),
  ]);
  let loaded = false;
  details.addEventListener("toggle", async () => {
    if (!details.open || loaded) return;
    loaded = true;
    details.append(await datasetSection(summary, dataset));
  });
  if (["locus_evidence", "hsp_evidence"].includes(dataset)) details.open = true;
  return details;
}

function analyticsNavigation() {
  return h("nav", { class: "gi-analytics-nav", "aria-label": "Navegação do explorador" }, [
    button("Gráficos", () => document.getElementById("analytics-graphs")?.scrollIntoView({ behavior: "smooth", block: "start" }), "secondary"),
    button("Detalhes técnicos", () => document.getElementById("analytics-details")?.scrollIntoView({ behavior: "smooth", block: "start" }), "secondary"),
    button("Artefatos", () => document.getElementById("analytics-data")?.scrollIntoView({ behavior: "smooth", block: "start" }), "secondary"),
  ]);
}

export async function renderAnalytics(runId) {
  const { root, body } = advancedShell(
    pageHeader("Área avançada · Evidence V2", "Explorador analítico", "Execuções inválidas são fechadas como NOT_EVALUABLE; gráficos e tabelas usam apenas artefatos promovidos e validados.", true),
    "analytics",
  );
  if (!runId) {
    const input = h("input", { type: "text", placeholder: "ID da execução", autocomplete: "off", "data-kind": "id" });
    body.append(panel("", [
      field("Execução Evidence V2", input, "Informe um run_id promovido."),
      button("Carregar execução", () => { if (input.value.trim()) location.hash = `#/analytics?run=${encodeURIComponent(input.value.trim())}`; }),
    ]));
    return root;
  }
  try {
    const summary = await getJSON(`/api/evidence/analytics?run=${encodeURIComponent(runId)}`);
    body.append(analyticsStatus(summary));
    const identity = [
      valueCard("Execução", summary.run_id), valueCard("Amostra", summary.metadata.sample_id),
      valueCard("Status técnico", summary.metadata.execution_status),
      valueCard("Conclusão computacional", summary.metadata.analysis_outcome),
      valueCard("Recuperação", summary.metadata.evidence_label || evidenceLabel(summary.metadata.evidence_level)),
      valueCard("Finalizada", formatDate(summary.metadata.finished_at)),
    ];
    if (summary.validation.valid) identity.push(
      valueCard("Pipeline", summary.metadata.pipeline_version), valueCard("Política", summary.metadata.policy_version),
      valueCard("Candidatos", summary.metrics?.candidate_count),
    );
    body.append(h("section", { class: "gi-metrics", "aria-label": "Identificação da execução" }, identity));
    body.append(analysisSummary(summary));
    if (!summary.validation.valid) return root;
    body.append(analyticsNavigation());
    const graphs = panel("Gráficos e encaixes", [], "section", { class: "gi-analytics-visual" });
    graphs.id = "analytics-graphs";
    graphs.append(statusPanel("empty", "Visualização sob demanda", "Abra apenas os gráficos que quer inspecionar. As tabelas completas ficam recolhidas dentro de cada seção."));
    graphs.append(lazyDatasetSection(summary, "locus_evidence"));
    graphs.append(lazyDatasetSection(summary, "hsp_evidence"));
    body.append(graphs);

    const technical = h("details", { id: "analytics-details", class: "gi-analytics-data" }, [
      h("summary", { text: "Detalhes técnicos · candidatos, proveniência, etapas e gates" }),
    ]);
    let technicalLoaded = false;
    technical.addEventListener("toggle", async () => {
      if (!technical.open || technicalLoaded) return;
      technicalLoaded = true;
      technical.append(candidateSection(summary), provenanceSection(summary));
      const stages = panel("Linha do tempo dos estágios", [stageTimelineChart(summary.stages)]);
      const list = h("ol", { class: "gi-timeline" });
      summary.stages.forEach((stage) => {
        const duration = stage.started_at && stage.finished_at ? elapsed(stage.started_at, stage.finished_at) : "";
        list.append(h("li", { dataset: { state: String(stage.status || "pending").toLowerCase() } }, [
          h("span", {}, [h("strong", { text: stage.label }), document.createTextNode(` — ${stage.status || "não informado"}`)]),
          duration ? h("time", { text: duration }) : null,
        ]));
      });
      stages.append(list);
      technical.append(stages, panel("Gates e motivos", [gateMatrixChart(summary.gates), gateTable(summary.gates)]));
    });
    body.append(technical);

    const artifacts = h("details", { id: "analytics-data", class: "gi-analytics-data" }, [
      h("summary", { text: "Outros artefatos · abrir apenas se precisar" }),
    ]);
    ["fragment_evidence", "competitive_hits", "coverage", "read_support", "template_lineage"].forEach((dataset) => {
      artifacts.append(lazyDatasetSection(summary, dataset));
    });
    body.append(artifacts);
  } catch (error) {
    body.append(statusPanel("error", "Não foi possível carregar a execução", error.payload?.error || error.message));
  }
  return root;
}

export async function renderComparison(selected = []) {
  const { root, body } = advancedShell(pageHeader("Área avançada", "Comparar execuções", "Selecione de duas a quatro execuções. Políticas incompatíveis permanecem lado a lado, sem sobreposição.", true), "compare");
  const history = await getJSON("/api/history").catch(() => ({ runs: [] }));
  const candidates = (history.runs || []).filter((run) => run.evidence_v2 && run.valid_alpha2);
  const form = h("form", { class: "gi-panel", onsubmit: async (event) => {
    event.preventDefault();
    const runs = [...form.querySelectorAll("input:checked")].map((input) => input.value);
    if (runs.length < 2 || runs.length > 4) { toast("Selecione de duas a quatro execuções."); return; }
    location.hash = `#/compare?${runs.map((run) => `run=${encodeURIComponent(run)}`).join("&")}`;
  } }, [h("header", { class: "gi-panel__head" }, h("h2", { text: "Execuções validadas" }))]);
  candidates.forEach((run) => {
    const input = h("input", { type: "checkbox", name: "run", value: run.run_id, id: `compare-${run.run_id}` });
    input.checked = selected.includes(run.run_id);
    form.append(h("div", { class: "gi-field gi-field--check" }, [h("label", { for: input.id }, [input, document.createTextNode(` ${run.run_id} · ${run.sample || "sem amostra"}`)])]));
  });
  form.append(h("button", { class: buttonClass(), type: "submit", text: "Comparar seleção" }));
  body.append(form);
  if (selected.length >= 2) {
    try {
      const query = selected.map((run) => `run=${encodeURIComponent(run)}`).join("&");
      const payload = await getJSON(`/api/evidence/analytics/compare?${query}`);
      body.append(payload.compatibility.overlay_allowed
        ? statusPanel("success", "Execuções compatíveis", "Gráficos lado a lado e sobrepostos estão liberados.")
        : statusPanel("blocked", "Sobreposição bloqueada", payload.compatibility.reason));
      const identities = payload.runs.map((run) => ({ run_id: run.run_id, ...run.metadata, validation: run.validation.status }));
      body.append(dataTable([
        { key: "run_id", label: "Execução" }, { key: "sample_id", label: "Amostra" },
        { key: "pipeline_version", label: "Pipeline" }, { key: "policy_version", label: "Política" },
        { key: "schema_version", label: "Schema" }, { key: "validation", label: "Validação" },
      ], identities, "Identidade e compatibilidade"));
      const metricKeys = [...new Set(payload.runs.flatMap((run) => Object.keys(run.metrics || {})))].sort();
      const baseline = payload.runs[0];
      const metricRows = metricKeys.map((metric) => {
        const row = { metric };
        const baseValue = baseline.metrics?.[metric];
        payload.runs.forEach((run, index) => {
          const value = run.metrics?.[metric];
          row[`run_${index}`] = value ?? "Não medido";
          if (index > 0) row[`delta_${index}`] = typeof value === "number" && typeof baseValue === "number" ? value - baseValue : "Não avaliável";
        });
        return row;
      });
      const metricColumns = [{ key: "metric", label: "Métrica" }];
      payload.runs.forEach((run, index) => {
        metricColumns.push({ key: `run_${index}`, label: `${run.run_id} · absoluto`, numeric: true });
        if (index > 0) metricColumns.push({ key: `delta_${index}`, label: `Diferença vs ${baseline.run_id}`, numeric: true });
      });
      body.append(panel("Métricas lado a lado", [dataTable(metricColumns, metricRows, "Valores absolutos e diferenças")]));
      body.append(panel("Candidatos — valores absolutos", [comparisonMetricChart(payload.runs, "candidate_count", "Candidatos")]));
      const gates = payload.runs.flatMap((run) => run.gates.map((gate) => ({ run_id: run.run_id, ...gate })));
      body.append(panel("Matriz comparativa de gates", [dataTable([
        { key: "run_id", label: "Execução" }, { key: "gate_id", label: "Gate" }, { key: "status", label: "Estado" }, { key: "reason", label: "Motivo" },
      ], gates, "Gates comparados") ]));
      for (const [dataset, title, chart] of [
        ["coverage", "Cobertura por execução", coverageChart],
        ["read_support", "Suporte por execução", supportChart],
        ["locus_evidence", "Loci por execução", locusIntervalChart],
      ]) {
        const loaded = await Promise.all(payload.runs.map(async (run) => {
          if (!['available', 'empty'].includes(run.datasets?.[dataset]?.status)) return { run: run.run_id, rows: [], truncated: false, columns: [] };
          const data = await getJSON(`/api/evidence/analytics/dataset?run=${encodeURIComponent(run.run_id)}&dataset=${dataset}&limit=500`);
          return { run: run.run_id, ...data };
        }));
        const rows = loaded.flatMap((item) => item.rows.map((row) => ({
          ...row,
          run_id: item.run,
          reference_id: `${item.run} · ${row.reference_id || row.sseqid || "não informado"}`,
          sseqid: `${item.run} · ${row.sseqid || row.reference_id || "não informado"}`,
          locus_id: `${item.run} · ${row.locus_id || "não informado"}`,
        })));
        const section = panel(title);
        if (loaded.some((item) => item.truncated)) section.append(statusPanel("warning", "Conteúdo truncado", "Refine a execução no explorador analítico; nenhuma amostragem foi feita."));
        section.append(rows.length ? chart(rows) : statusPanel("empty", "Nenhum dado comparável", "Os artefatos estão vazios ou não foram medidos."));
        if (rows.length) {
          const columns = ["run_id", ...new Set(loaded.flatMap((item) => item.columns))];
          section.append(dataTable(columns.map((key) => ({ key, label: key, numeric: isNumericColumn(rows, key) })), rows, title));
        }
        body.append(section);
      }
    } catch (error) { body.append(statusPanel("error", "Comparação indisponível", error.payload?.error || error.message)); }
  }
  return root;
}
