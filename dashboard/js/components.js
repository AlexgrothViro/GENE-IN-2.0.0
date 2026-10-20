import { createElement } from "./dom.js";
import { evidenceLabel } from "./adapters.js";

export const h = (tag, props = {}, children = []) => createElement(document, tag, props, children);
export const text = (value) => document.createTextNode(value == null ? "" : String(value));

export function pageHeader(eyebrow, title, description, experimental = false) {
  return h("header", { class: "gi-pagehead" }, [
    h("div", { class: "gi-pagehead__over" }, [
      h("p", { class: "gi-label", text: eyebrow }),
      experimental ? badge("EXPERIMENTAL", "experimental") : null,
    ]),
    h("h1", { text: title }),
    h("p", { text: description }),
  ]);
}

export function panelHead(title, tag = "h2") {
  return h("header", { class: "gi-panel__head" }, h(tag, { text: title }));
}

export function panel(title, children = [], tag = "section", props = {}) {
  const { class: extra, ...rest } = props;
  return h(tag, { class: `gi-panel${extra ? ` ${extra}` : ""}`, ...rest }, [title ? panelHead(title) : null, ...(Array.isArray(children) ? children : [children])]);
}

export function metric(label, value, hint = "") {
  const missing = value == null || value === "" || value === "—";
  return h("div", { class: "gi-metric", dataset: missing ? { missing: "true" } : {} }, [
    h("small", { text: label }),
    h("strong", { text: missing ? "Não medido" : value }),
    hint ? h("small", { text: hint }) : null,
  ]);
}

export const DIMENSION_LABELS = {
  execution_status: "Status técnico (execution_status)",
  analysis_outcome: "Conclusão computacional (analysis_outcome)",
  evidence_level: "Recuperação de candidatos",
  promotion_status: "Disponibilidade",
  control_status: "Estado dos controles (control_status)",
  reported_conclusion: "Conclusão reportável (reported_conclusion)",
};

function outcomePlate(outcome, detail, label) {
  return h("div", { class: "gi-outcome", dataset: { outcome }, role: "status" }, [
    h("div", { class: "gi-outcome__reads", "aria-hidden": "true" }, [h("i"), h("i"), h("i"), h("i"), h("i"), h("i")]),
    h("div", {}, [
      h("strong", { class: "gi-outcome__code", text: label || outcome }),
      h("p", { class: "gi-outcome__text", text: detail }),
    ]),
  ]);
}

export function outcomePanel(outcome) {
  if (outcome === "NO_EVIDENCE_RECOVERED" || outcome === "SEM_CANDIDATOS_PARA_REVISAO" || outcome === "NO_SIGNAL") {
    return outcomePlate(
      "NO_EVIDENCE_RECOVERED",
      "A análise foi tecnicamente válida e não recuperou candidato classificável nas condições configuradas.",
      "Sem candidatos para revisão",
    );
  }
  if (outcome === "EVIDENCE_RECOVERED" || outcome === "CANDIDATOS_PARA_REVISAO" || outcome === "DETECTED") {
    return outcomePlate(
      "EVIDENCE_RECOVERED",
      "Há candidatos para revisão humana. A recuperação não confirma origem viral nem espécie.",
      "Candidatos para revisão",
    );
  }
  if (outcome === "NOT_EVALUABLE") {
    return outcomePlate(
      "NOT_EVALUABLE",
      "A execução não pôde ser avaliada cientificamente. O status técnico do job não substitui esta conclusão.",
    );
  }
  return null;
}

export function analysisDimensions(values = {}) {
  const rows = Object.entries(DIMENSION_LABELS).map(([key, dimension]) => {
    const value = values[key] == null || values[key] === "" ? "Não informado" : values[key];
    return { dimension, key, value: key === "execution_status" && value !== "Não informado" ? badge(value) : key === "evidence_level" ? evidenceLabel(value) : value };
  });
  return dataTable(
    [{ key: "dimension", label: "Dimensão" }, { key: "value", label: "Valor" }],
    rows,
    "Dimensões registradas no artefato da análise",
  );
}

const STATUS_ICONS = {
  loading: "↻", empty: "○", unavailable: "—", blocked: "■", running: "↻",
  done: "✓", no_evidence: "○", not_evaluable: "?", failed: "!", cancelled: "×",
  partial: "△", shadow: "◇", experimental: "◇", success: "✓", warning: "!", error: "!",
};

export function statusPanel(state, title, detail = "") {
  const line = h("div", { class: "gi-status", dataset: { state }, role: state === "error" ? "alert" : "status" });
  line.append(
    h("span", { class: "gi-status__icon", "aria-hidden": "true", text: STATUS_ICONS[state] || "i" }),
    h("strong", { text: title }),
    detail ? h("p", { text: detail }) : null,
  );
  return line;
}

export function badge(value, state = "") {
  const normalized = String(state || value || "").toLowerCase();
  return h("span", { class: "gi-tag", dataset: { state: normalized }, text: value || "Não informado" });
}

export const buttonClass = (variant = "") => `gi-btn gi-btn--${variant || "primary"}`;

export function button(label, onClick, variant = "", props = {}) {
  return h("button", {
    type: "button", class: buttonClass(variant),
    onclick: onClick, ...props, text: label,
  });
}

export function linkButton(label, href, variant = "") {
  return h("a", { class: buttonClass(variant), href, text: label });
}

export function field(label, control, hint = "") {
  const id = control.getAttribute("id") || `field-${Math.random().toString(36).slice(2)}`;
  control.setAttribute("id", id);
  const wrapper = h("div", { class: "gi-field" }, [h("label", { for: id, text: label }), control]);
  if (hint) wrapper.append(h("small", { text: hint }));
  return wrapper;
}

export function dataTable(columns, rows, caption = "Dados") {
  const table = h("table", { class: "gi-table" });
  table.append(h("caption", { class: "visually-hidden", text: caption }));
  const head = h("tr");
  columns.forEach((column) => head.append(h("th", { scope: "col", class: column.numeric ? "gi-num" : null, text: column.label || column.key })));
  table.append(h("thead", {}, head));
  const body = h("tbody");
  rows.forEach((row) => {
    const tr = h("tr");
    columns.forEach((column) => {
      const value = typeof column.render === "function" ? column.render(row) : row[column.key];
      tr.append(h("td", { class: column.numeric ? "gi-num" : null }, value instanceof Node ? value : text(value ?? "—")));
    });
    body.append(tr);
  });
  table.append(body);
  return h("div", { class: "gi-table-wrap" }, table);
}

export function loading(message = "Carregando dados…") {
  return h("div", { class: "gi-loader", role: "status" }, [
    h("div", { class: "gi-loader__glyph", "aria-hidden": "true" }, [h("b"), h("i"), h("i"), h("i"), h("i"), h("i"), h("b")]),
    h("span", { text: message }),
  ]);
}

export function toast(message, state = "") {
  const root = document.getElementById("notifications");
  const item = h("div", { class: "gi-toast", dataset: state ? { state } : {} });
  item.append(h("span", { text: message }), h("button", { type: "button", onclick: () => item.remove(), text: "Fechar" }));
  root.append(item);
  window.setTimeout(() => item.remove(), 5000);
}

export function openModal(title, content, opener = document.activeElement) {
  const root = document.getElementById("modal-root");
  const close = () => {
    document.removeEventListener("keydown", onKeydown);
    root.replaceChildren();
    if (opener && typeof opener.focus === "function") opener.focus();
  };
  const closeButton = button("Fechar", close, "quiet", { "aria-label": "Fechar janela" });
  const dialog = h("section", { class: "gi-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "modal-title" }, [
    h("header", { class: "gi-modal__head" }, [h("h2", { id: "modal-title", text: title }), closeButton]),
    h("div", { class: "gi-modal__body" }, content),
  ]);
  const backdrop = h("div", { class: "gi-modal-backdrop", onclick: (event) => { if (event.target === backdrop) close(); } }, dialog);
  const focusable = () => [...dialog.querySelectorAll("a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])")];
  const onKeydown = (event) => {
    if (event.key === "Escape") close();
    if (event.key !== "Tab") return;
    const nodes = focusable();
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  root.replaceChildren(backdrop);
  document.addEventListener("keydown", onKeydown);
  closeButton.focus();
  return close;
}
