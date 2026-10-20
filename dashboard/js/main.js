import { createStore, loadActiveJob } from "./state.js";
import { startRouter } from "./router.js";
import { normalizeStatus } from "./adapters.js";
import { getJSON } from "./api.js";
import { loading, statusPanel } from "./components.js";
import { renderHome, renderHistory, renderNewAnalysis, renderResults, renderTrack } from "./operational.js";
import { renderAdvanced, renderContigs, renderResearch, renderSettings } from "./advanced.js";
import { renderAnalytics, renderComparison } from "./analytics.js";

export const appStore = createStore({
  route: "home",
  context: { environment: "Verificando", database: "Não selecionado", sample: "Não selecionada", job: "Aguardando" },
  activeJob: loadActiveJob(),
  wizard: {
    step: 0, loaded: false, environment: null, databases: [], samples: [],
    database: "", dbQuery: "", sample: "", assembler: "consensus", kmer: "31", hostMode: "none",
    qcAdapterR1: "", qcAdapterR2: "",
  },
});

let routeRequest = 0;
let currentRoute = { route: "home", params: new URLSearchParams() };
getJSON("/api/preflight").then((environment) => {
  appStore.set({ context: { environment: environment.ok ? "Pronto" : "Com pendências" }, wizard: { environment } });
}).catch(() => appStore.set({ context: { environment: "Indisponível" } }));

function contextStates(state) {
  const environment = state.context.environment;
  const job = normalizeStatus(state.activeJob?.status);
  return {
    environment: environment === "Pronto" ? "ok" : environment === "Verificando" ? "running" : "idle",
    database: state.context.database && state.context.database !== "Não selecionado" ? "ok" : "idle",
    sample: state.context.sample && state.context.sample !== "Não selecionada" ? "ok" : "idle",
    job: !state.activeJob?.id ? "idle" : job === "running" ? "running" : ["done", "partial"].includes(job) ? "ok" : "idle",
  };
}

function updateContext(state) {
  const states = contextStates(state);
  Object.entries(states).forEach(([key, value]) => {
    document.getElementById(`context-${key}`).textContent = state.context[key];
    document.getElementById(`context-${key}-cell`).dataset.state = value;
  });
}

function updateNavigation(route) {
  const operational = new Set(["home", "new", "track", "results", "history"]);
  document.querySelectorAll("[data-route]").forEach((link) => {
    if (operational.has(route) && link.dataset.route === route) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const nav = document.getElementById("primary-navigation");
  nav.dataset.open = "false";
  document.getElementById("menu-toggle").setAttribute("aria-expanded", "false");
}

async function viewFor(route, params) {
  const rerender = () => renderRoute(currentRoute);
  if (route === "home") return renderHome(appStore);
  if (route === "new") return renderNewAnalysis(appStore, rerender);
  if (route === "track") return renderTrack(appStore, rerender, params.get("job") || "");
  if (route === "results") return renderResults(appStore, params.get("run") || "");
  if (route === "history") return renderHistory(appStore);
  if (route === "advanced") return renderAdvanced(appStore);
  if (route === "analytics") return renderAnalytics(params.get("run") || "");
  if (route === "compare") return renderComparison(params.getAll("run"));
  if (route === "research") return renderResearch();
  if (route === "contigs") return renderContigs(appStore);
  if (route === "settings") return renderSettings(appStore);
  return statusPanel("unavailable", "Página não encontrada", "Use a navegação principal.");
}

export async function renderRoute(routeState) {
  currentRoute = routeState;
  const request = ++routeRequest;
  const root = document.getElementById("route-view");
  root.setAttribute("aria-busy", "true");
  root.replaceChildren(loading());
  updateNavigation(routeState.route);
  appStore.set({ route: routeState.route });
  try {
    const view = await viewFor(routeState.route, routeState.params);
    if (request !== routeRequest) return;
    root.replaceChildren(view);
    root.setAttribute("aria-busy", "false");
    document.title = `${view.querySelector("h1")?.textContent || "Gene-In"} · Gene-In`;
    document.getElementById("app-main").focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "instant" });
  } catch (error) {
    if (request !== routeRequest) return;
    root.replaceChildren(statusPanel("error", "Não foi possível abrir esta área", error.payload?.error || error.payload || error.message));
    root.setAttribute("aria-busy", "false");
  }
}

function initializeMenu() {
  const button = document.getElementById("menu-toggle");
  const nav = document.getElementById("primary-navigation");
  const close = () => {
    nav.dataset.open = "false";
    button.setAttribute("aria-expanded", "false");
  };
  button.addEventListener("click", () => {
    const open = nav.dataset.open !== "true";
    nav.dataset.open = String(open);
    button.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.dataset.open === "true") {
      close();
      button.focus();
    }
  });
}

initializeMenu();
appStore.subscribe(updateContext);
updateContext(appStore.get());
startRouter(renderRoute);
