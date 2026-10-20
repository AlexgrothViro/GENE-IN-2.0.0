function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export const ACTIVE_JOB_STORAGE_KEY = "genein.activeJob.v1";

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
