const DEFAULT_ROUTE = "home";
const KNOWN_ROUTES = new Set([
  "home", "new", "track", "results", "history", "advanced",
  "analytics", "compare", "research", "contigs", "settings",
]);

export function parseRoute(hash = "") {
  const raw = String(hash).replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?", 2);
  const route = KNOWN_ROUTES.has(path) ? path : DEFAULT_ROUTE;
  return { route, params: new URLSearchParams(query) };
}

export function routeHref(route, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value != null && String(value) !== "") query.set(key, String(value));
  });
  return `#/${route}${query.size ? `?${query}` : ""}`;
}

export function startRouter(onChange, win = window) {
  const notify = () => onChange(parseRoute(win.location.hash));
  win.addEventListener("hashchange", notify);
  if (!win.location.hash) win.location.hash = "#/home";
  else notify();
  return () => win.removeEventListener("hashchange", notify);
}
