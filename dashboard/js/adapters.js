export function normalizeStatus(value) {
  const raw = String(value || "").toLowerCase();
  if (["queued", "starting", "running", "cancelling"].includes(raw)) return "running";
  if (["done", "success"].includes(raw)) return "done";
  if (raw === "done_with_warning") return "partial";
  if (["error", "failed", "evidence_invalid", "legacy_incompatible", "incomplete"].includes(raw)) return "failed";
  if (raw === "not_evaluable") return "not_evaluable";
  if (raw === "not_started") return "not_started";
  if (raw === "blocked") return "blocked";
  if (raw === "cancelled") return "cancelled";
  return raw || "unavailable";
}

export function jobLabel(value) {
  if (value === "validation_pending") return "Validando resultados";
  return { running: "Em execução", done: "Concluída", partial: "Concluída com ressalvas técnicas", failed: "Falha", blocked: "Bloqueada", cancelled: "Cancelada", unavailable: "Aguardando", not_started: "Não iniciada", not_evaluable: "Não avaliável" }[normalizeStatus(value)] || value;
}

// Códigos contratuais DETECTED / EVIDENCE_RECOVERED permanecem no JSON.
// A interface mostra o rótulo neutro.
const PUBLIC_REVIEW_LABELS = {
  DETECTED: "CANDIDATOS_PARA_REVISAO",
  EVIDENCE_RECOVERED: "CANDIDATOS_PARA_REVISAO",
  NO_SIGNAL: "SEM_CANDIDATOS_PARA_REVISAO",
  NO_EVIDENCE_RECOVERED: "SEM_CANDIDATOS_PARA_REVISAO",
  NOT_EVALUABLE: "Não avaliável",
};

export function evidenceLabel(value) {
  return PUBLIC_REVIEW_LABELS[value] || value || "Não informado";
}

export function runIdentity(run = {}) {
  return {
    id: run.run_id || run.id || "",
    sample: run.sample || "—",
    status: normalizeStatus(run.execution_status || run.status),
    jobStatus: normalizeStatus(run.job_status || run.official_v1_status || ""),
    started: run.start || run.created_at || null,
    finished: run.end || run.finished_at || null,
    evidence: Boolean(run.evidence_v2),
    valid: run.valid_alpha2,
    shadow: run.shadow_mode,
    runDir: run.run_dir || "",
    action: run.action || "",
    paths: run.paths && typeof run.paths === "object" ? run.paths : {},
    comparison: Boolean(run.comparison || run.action === "compare_contigs"),
    params: run.params || {}, label: run.label || run.params?.label || "",
    effectiveConfig: run.effective_config || {},
    analysisOutcome: run.analysis_outcome || "",
    reportedConclusion: run.reported_conclusion || "",
  };
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" }).format(date);
}

export function elapsed(start, end = Date.now()) {
  if (!start) return "Não medido";
  const first = new Date(start).getTime();
  const last = typeof end === "number" ? end : new Date(end).getTime();
  if (!Number.isFinite(first) || !Number.isFinite(last) || last < first) return "Não medido";
  const seconds = Math.floor((last - first) / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}min` : `${minutes}min ${seconds % 60}s`;
}
