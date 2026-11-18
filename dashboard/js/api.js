async function request(url, options = {}) {
  const response = await fetch(url, { ...options, cache: "no-store" });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message = typeof payload === "object" && payload?.error
      ? payload.error
      : (typeof payload === "string" && payload.trim() ? payload.trim() : `HTTP ${response.status}`);
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export function getJSON(url, options = {}) {
  return request(url, { ...options, method: "GET", headers: { Accept: "application/json" } });
}

export class ValidationPendingError extends Error {
  constructor() {
    super("A conferência dos arquivos continua em andamento. Você pode consultar novamente.");
    this.name = "ValidationPendingError";
  }
}

function assertActive(signal) {
  if (signal?.aborted) throw new DOMException("Consulta interrompida", "AbortError");
}

function validationDelay(milliseconds, signal) {
  assertActive(signal);
  return new Promise((resolve, reject) => {
    const cleanup = () => signal?.removeEventListener("abort", stop);
    const stop = () => { clearTimeout(timer); cleanup(); reject(new DOMException("Consulta interrompida", "AbortError")); };
    const timer = setTimeout(() => { cleanup(); resolve(); }, milliseconds);
    signal?.addEventListener("abort", stop, { once: true });
  });
}

export async function waitForValidation(load, {
  signal, onPending, isPending = (value) => value?.validation?.status === "VALIDATION_PENDING",
  maxAttempts = 30, intervalMs = 500,
} = {}) {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    assertActive(signal);
    const result = await load(signal);
    assertActive(signal);
    if (!isPending(result)) return result;
    onPending?.(result);
    if (attempt + 1 < maxAttempts) await validationDelay(intervalMs, signal);
  }
  throw new ValidationPendingError();
}

export function postJSON(url, body) {
  return request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
}

export function postForm(url, formData, onProgress) {
  if (onProgress) return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => onProgress(event.loaded, event.lengthComputable ? event.total : null);
    xhr.upload.onload = () => onProgress(null, null);
    xhr.onerror = () => reject(new Error("Falha de conexão ao enviar arquivos. Confira a conexão e tente novamente."));
    xhr.onabort = () => reject(new Error("Envio de arquivos interrompido."));
    xhr.onload = () => {
      let payload = xhr.responseText;
      if ((xhr.getResponseHeader("Content-Type") || "").includes("application/json")) {
        try { payload = JSON.parse(payload); } catch { reject(new Error("Resposta inválida do servidor.")); return; }
      }
      if (xhr.status >= 200 && xhr.status < 300) { resolve(payload); return; }
      const error = new Error(payload?.error || (typeof payload === "string" && payload.trim()) || `HTTP ${xhr.status}`);
      error.status = xhr.status;
      error.payload = payload;
      reject(error);
    };
    xhr.send(formData);
  });
  return request(url, { method: "POST", body: formData });
}

export { request };
