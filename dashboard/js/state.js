function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export const ACTIVE_JOB_STORAGE_KEY = "genein.activeJob.v1";

export const OPTIONAL_EVIDENCE_DEFAULTS = {
  competitionEnabled: null, competitionDb: null, competitionLabels: null,
  remappingEnabled: null, remappingReference: null, remappingIndex: null, libraryMode: null,
  optionalDefaults: {},
};

export function effectiveOptionalEvidence(wizard) {
  const saved = wizard.optionalDefaults || {};
  const value = (key, field, option) => (wizard[option] == null ? saved[field] : wizard[key] ?? saved[field]) ?? "";
  return {
    competitionEnabled: wizard.competitionEnabled ?? saved.competition_enabled ?? false,
    remappingEnabled: wizard.remappingEnabled ?? saved.remapping_enabled ?? false,
    competitionDb: value("competitionDb", "competition_db", "competitionEnabled"),
    competitionLabels: value("competitionLabels", "competition_labels", "competitionEnabled"),
    remappingReference: value("remappingReference", "remapping_reference", "remappingEnabled"),
    remappingIndex: value("remappingIndex", "remapping_index", "remappingEnabled"),
    libraryMode: value("libraryMode", "library_mode", "remappingEnabled") || "unknown",
  };
}

export function optionalEvidenceParams(wizard) {
  const params = {}, effective = effectiveOptionalEvidence(wizard);
  if (typeof wizard.competitionEnabled === "boolean") params.competition_enabled = wizard.competitionEnabled;
  if (typeof wizard.remappingEnabled === "boolean") params.remapping_enabled = wizard.remappingEnabled;
  if (params.competition_enabled) Object.assign(params, { competition_db: effective.competitionDb.trim(), competition_labels: effective.competitionLabels.trim() });
  if (params.remapping_enabled) Object.assign(params, { remapping_reference: effective.remappingReference.trim(), remapping_index: effective.remappingIndex.trim(), library_mode: effective.libraryMode });
  return params;
}

export function optionalEvidenceIssues(wizard) {
  const effective = effectiveOptionalEvidence(wizard), issues = [];
  if (effective.competitionEnabled && (!effective.competitionDb || !effective.competitionLabels)) issues.push("banco competitivo e tabela de rótulos");
  if (effective.remappingEnabled && (!effective.remappingReference || !effective.remappingIndex)) issues.push("referência e índice de remapeamento");
  return issues;
}

export function optionalEvidenceWizard(params = {}) {
  return { ...OPTIONAL_EVIDENCE_DEFAULTS,
    competitionEnabled: params.competition_enabled ?? null, competitionDb: params.competition_db ?? null, competitionLabels: params.competition_labels ?? null,
    remappingEnabled: params.remapping_enabled ?? null, remappingReference: params.remapping_reference ?? null, remappingIndex: params.remapping_index ?? null, libraryMode: params.library_mode ?? null };
}

export function loadActiveJob(storage = globalThis.sessionStorage) {
  try {
    const value = JSON.parse(storage?.getItem(ACTIVE_JOB_STORAGE_KEY) || "null");
    return value && typeof value.id === "string" && value.id ? value : null;
  } catch (_) { return null; }
}

export function persistActiveJob(job, storage = globalThis.sessionStorage) {
  try {
    if (job?.id) storage?.setItem(ACTIVE_JOB_STORAGE_KEY, JSON.stringify(job));
    else storage?.removeItem(ACTIVE_JOB_STORAGE_KEY);
  } catch (_) {}
  return job;
}

export function activateJob(store, jobId, contextLabel) {
  const activeJob = persistActiveJob({ id: jobId, status: "queued", startedAt: new Date().toISOString() });
  store.set({ activeJob, context: { job: contextLabel } });
  location.hash = `#/track?job=${encodeURIComponent(jobId)}`;
  return activeJob;
}

export function deepMerge(base, patch) {
  const result = { ...base };
  Object.entries(patch).forEach(([key, value]) => {
    result[key] = isPlainObject(value) && isPlainObject(result[key])
      ? deepMerge(result[key], value)
      : value;
  });
  return result;
}

export function createStore(initial = {}) {
  let state = { ...initial };
  const subscribers = new Set();
  return {
    get: () => state,
    set(patch) {
      state = deepMerge(state, patch);
      subscribers.forEach((subscriber) => subscriber(state));
      return state;
    },
    replace(next) {
      state = next;
      subscribers.forEach((subscriber) => subscriber(state));
      return state;
    },
    subscribe(subscriber) {
      subscribers.add(subscriber);
      return () => subscribers.delete(subscriber);
    },
  };
}
