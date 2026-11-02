import { getJSON, postForm, postJSON } from "./api.js";
import { badge, button, buttonClass, dataTable, field, h, linkButton, metric, pageHeader, panel, panelHead, statusPanel, toast } from "./components.js";
import { formatDate } from "./adapters.js";
import { activateJob } from "./state.js";
import { sampleImportCard } from "./operational.js";

export function advancedNav(current = "advanced") {
  const links = [
    ["advanced", "Ferramentas"], ["analytics", "Explorar resultados"], ["compare", "Comparar execuções"],
    ["research", "Consultar mapeamentos"], ["contigs", "Comparar contigs"], ["settings", "Configuração"],
  ];
  return h("nav", { class: "gi-advanced__nav", "aria-label": "Ferramentas do Gene-In" }, links.map(([route, label]) => h("a", { href: `#/${route}`, "aria-current": current === route ? "page" : null, text: label })));
}

export function advancedShell(header, current) {
  const body = h("div", { class: "gi-advanced__body stack" });
  const zone = h("section", { class: "gi-advanced", "aria-label": "Ferramentas de análise" }, [
    advancedNav(current),
    body,
  ]);
  return { root: h("div", { class: "advanced-shell" }, [header, zone]), body };
}

function moduleRoute(title, description, href) {
  return h("a", { class: "gi-route", href }, [
    h("span", { class: "gi-route__title", text: title }),
    h("p", { text: description }),
  ]);
}

export async function renderAdvanced(store) {
  const { root, body } = advancedShell(
    pageHeader("Gene-In", "Ferramentas de análise", "Execute análises, explore resultados e compare arquivos identificados."),
    "advanced",
  );
  body.append(
    h("p", { text: "As conferências dos arquivos são controles de integridade e rastreabilidade. A interpretação dos resultados exige revisão humana." }),
    panel("Iniciar ou acompanhar uma análise", [
      h("p", { text: "O assistente reúne entradas, configuração e revisão antes da execução. Os resultados ficam disponíveis no histórico." }),
      h("div", { class: "gi-btnrow" }, [linkButton("Nova análise", "#/new"), linkButton("Histórico", "#/history", "secondary")]),
    ]),
    h("nav", { class: "gi-routes gi-routes--5", "aria-label": "Funções do programa" }, [
      moduleRoute("Explorar resultados", "Relatórios, arquivos, cobertura e suporte.", "#/analytics"),
      moduleRoute("Comparação de execuções", "Duas a quatro execuções, com compatibilidade explícita.", "#/compare"),
      moduleRoute("Consultar mapeamentos", "Consulta e download de resultados já produzidos.", "#/research"),
      moduleRoute("Comparação de contigs", "Homologia local sem remontagem.", "#/contigs"),
      moduleRoute("Configuração e lotes", "Ambiente, amostras e execução de manifestos.", "#/settings"),
    ]),
  );
  try {
    const [sampleData, configData, environment] = await Promise.all([getJSON("/api/samples"), getJSON("/api/config/env"), getJSON("/api/preflight")]);
    const config = configData.config || {};
    const present = new Set((environment.tools || []).filter((tool) => tool.present).map((tool) => tool.name));
    const tools = panel("Montagem isolada", [h("p", { text: "Monte uma amostra importada com o montador e o k-mer selecionados. Esta ação produz contigs; não executa a análise completa." })]);
    const sample = h("select", { id: "technical-sample" }, [h("option", { value: "", text: "Selecione a amostra" })]);
    (sampleData.samples || []).forEach((item) => {
      const id = typeof item === "string" ? item : item.name || item.id || item.sample;
      if (id) sample.append(h("option", { value: id, text: id }));
    });
    sample.value = store.get().wizard?.sample || "";
    const assembler = h("select", { id: "technical-assembler" }, [h("option", { value: "", text: "Selecione o montador" })]);
    for (const [value, executable] of [["velvet", "velveth"], ["spades", "spades.py"], ["metaspades", "metaspades.py"]]) {
      const option = h("option", { value, text: present.has(executable) ? value : `${value} — não instalado` });
      option.disabled = !present.has(executable);
      assembler.append(option);
    }
    assembler.value = ["velvet", "spades", "metaspades"].includes(config.ASSEMBLER) ? config.ASSEMBLER : "";
    const kmer = h("input", { id: "technical-kmer", type: "number", min: "1", value: config.VELVET_K || "31" });
    const threads = h("input", { id: "technical-threads", type: "number", min: "1", value: config.THREADS || "4" });
    const start = async () => {
      if (!sample.value) { toast("Selecione uma amostra importada."); return; }
      if (!/^[1-9][0-9]*$/.test(kmer.value)) { toast("Informe um k-mer inteiro positivo."); return; }
      if (!/^[1-9][0-9]*$/.test(threads.value)) { toast("Informe um número inteiro positivo de threads."); return; }
      if (!assembler.value || assembler.selectedOptions[0]?.disabled) { toast("Selecione um montador instalado."); return; }
      const params = { sample: sample.value, kmer: kmer.value, assembler: assembler.value, threads: threads.value };
      try {
        const response = await postJSON("/api/run", { action: "assembly_only", params });
        activateJob(store, response.job_id, "Execução iniciada");
      } catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
    };
    tools.append(field("Amostra", sample), field("Montador", assembler), field("K-mer (Velvet)", kmer), field("Threads (SPAdes/metaSPAdes)", threads),
      h("p", { text: "As entradas são procuradas em data/host_removed, data/cleaned e data/raw, nessa ordem. Os parâmetros adicionais salvos do montador também são utilizados." }),
      button("Montagem isolada", start, "secondary"));
    if (!(sampleData.samples || []).length) tools.append(linkButton("Importar amostra", "#/settings", "secondary"));
    body.append(tools);
  } catch (error) { body.append(statusPanel("unavailable", "Não foi possível carregar as opções de execução", error.payload?.error || error.message)); }
  body.append(statusPanel("unavailable", "Análise complementar fora da interface", "O comando existente depende de arquivos em pastas anteriores e de metadados das referências. A integração com resultados identificados por execução ainda precisa ser concluída e verificada antes de disponibilizar este lançamento no dashboard."));
  return root;
}

export async function renderResearch() {
  const { root, body } = advancedShell(pageHeader("Ferramentas", "Consultar mapeamentos", "Consulta de resultados de mapeamento já produzidos, com identidade e arquivos verificáveis."), "research");
  body.append(statusPanel("empty", "Consulta de resultados existentes", "A geração de novos mapeamentos não faz parte deste fluxo do painel. Resultados disponíveis mantêm sua origem, método e limites de interpretação."));
  try {
    const payload = await getJSON("/api/experimental/direct-map/runs");
    if (!payload.runs?.length) { body.append(statusPanel("empty", "Nenhum mapeamento disponível", "Não há resultados arquivados na pasta de mapeamentos configurada para esta instalação.")); return root; }
    payload.runs.forEach((run) => {
      const card = h("article", { class: "gi-panel" }, [panelHead(run.run_id), h("p", {}, [badge(run.contract_state, run.contract_state === "current" ? "done" : "invalid"), document.createTextNode(` · ${run.sample_id || "identidade não reinterpretada"}`)]), h("p", { text: `Concluída: ${formatDate(run.completed_at)} · Pipeline: ${run.pipeline_version || "não informado"}` })]);
      if (run.note) card.append(h("p", { text: run.note }));
      const actions = h("div", { class: "gi-btnrow" });
      (run.artifacts || []).forEach((type) => actions.append(linkButton(type, `/api/experimental/direct-map/artifact?run=${encodeURIComponent(run.run_id)}&type=${encodeURIComponent(type)}`, "secondary")));
      card.append(actions);
      body.append(card);
    });
  } catch (error) { body.append(statusPanel("error", "Consulta de mapeamentos indisponível", error.payload?.error || error.message)); }
  return root;
}

export async function renderContigs(store) {
  const { root, body } = advancedShell(pageHeader("Ferramentas", "Comparação de contigs", "Compara uma fonte imutável contra referência sem remontagem."), "contigs");
  try {
    const [sourcesPayload, comparisonsPayload, targetsPayload] = await Promise.all([
      getJSON("/api/experimental/contig-sources"), getJSON("/api/experimental/contig-comparisons"), getJSON("/api/targets"),
    ]);
    const sources = sourcesPayload.sources || [];
    const comparisons = comparisonsPayload.comparisons || [];
    const targets = targetsPayload.targets || targetsPayload || [];
    if (sources.length) {
      const form = h("form", { class: "gi-panel", onsubmit: async (event) => {
        event.preventDefault();
        const data = new FormData(form);
        try {
          const database = String(data.get("db") || "").trim();
          const query = String(data.get("db_query") || "").trim();
          if (database === "custom" && !query) {
            toast("Banco customizado exige query NCBI.");
            return;
          }
          const response = await postJSON("/api/run", { action: "compare_contigs", params: {
            sample: data.get("sample"), source_type: data.get("source_type"), source_id: data.get("source_id"),
            reference_kind: "database", db: database, db_query: query, blast_task: data.get("blast_task"),
            word_size: data.get("blast_task") === "blastn-short" ? 7 : 11, evalue: "1e-5", max_target_seqs: 50, threads: 4,
          } });
          activateJob(store, response.job_id, "Comparação iniciada");
        } catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
      } }, [panelHead("Nova comparação")]);
      const sourceSelect = h("select", { name: "source_id", id: "contig-source" });
      sources.forEach((source) => sourceSelect.append(h("option", { value: source.source_id || source.id, text: `${source.sample || "amostra"} · ${source.source_id || source.id}` })));
      const first = sources[0];
      const sample = h("input", { name: "sample", id: "contig-sample", value: first.sample || "", "data-kind": "id" });
      const sourceType = h("input", { name: "source_type", type: "hidden", value: first.source_type || "run" });
      sourceSelect.addEventListener("change", () => { const selected = sources[sourceSelect.selectedIndex]; sample.value = selected.sample || ""; sourceType.value = selected.source_type || "run"; });
      const db = h("select", { name: "db", id: "contig-db" });
      targets.forEach((target) => db.append(h("option", { value: typeof target === "string" ? target : (target.id || target.key), text: typeof target === "string" ? target : (target.label || target.name || target.id || target.key) })));
      if (!db.querySelector('option[value="custom"]')) {
        db.append(h("option", { value: "custom", text: "Outro vírus — query NCBI" }));
      }
      const dbQuery = h("input", { name: "db_query", id: "contig-db-query", type: "text", placeholder: '"Orthoflavivirus zikaense"[Organism]' });
      dbQuery.addEventListener("input", () => { if (dbQuery.value.trim()) db.value = "custom"; });
      const task = h("select", { name: "blast_task", id: "contig-task" }, [h("option", { value: "blastn", text: "blastn" }), h("option", { value: "blastn-short", text: "blastn-short" })]);
      form.append(field("Fonte de contigs", sourceSelect), field("Amostra", sample), sourceType, field("Banco", db), field("Outro vírus / query NCBI", dbQuery, "Obrigatório se o banco for customizado."), field("Tarefa BLAST", task), h("button", { class: buttonClass(), type: "submit", text: "Executar comparação" }));
      body.append(form);
    } else body.append(statusPanel("empty", "Nenhuma fonte de contigs", "Execute uma montagem ou importe uma fonte local pelo formulário abaixo."));
    const importForm = h("form", { class: "gi-panel", onsubmit: async (event) => {
      event.preventDefault();
      try { await postForm("/api/experimental/contig-sources/import", new FormData(importForm)); toast("Fonte de contigs importada."); location.reload(); }
      catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
    } }, [panelHead("Importar FASTA local")]);
    importForm.append(
      field("Amostra", h("input", { name: "sample", required: "required", type: "text", "data-kind": "id" })),
      field("Origem declarada", h("input", { name: "origin", required: "required", type: "text" })),
      field("Arquivo FASTA", h("input", { name: "fasta", required: "required", type: "file", accept: ".fa,.fasta,.fna" })),
      h("button", { class: buttonClass(), type: "submit", text: "Importar fonte" }),
    );
    body.append(importForm);
    if (comparisons.length) body.append(dataTable([
      { key: "comparison_id", label: "Comparação" }, { key: "sample", label: "Amostra" }, { key: "reference_database", label: "Banco" },
      { key: "completed_at", label: "Fim", render: (row) => formatDate(row.completed_at) },
      { key: "artifact", label: "Artefatos", render: (row) => linkButton("Manifesto", `/api/experimental/contig-comparison/artifact?comparison=${encodeURIComponent(row.comparison_id)}&type=manifest`, "secondary") },
    ], comparisons, "Comparações de contigs"));
  } catch (error) { body.append(statusPanel("error", "Comparação de contigs indisponível", error.payload?.error || error.message)); }
  return root;
}

const CONFIG_FIELDS = [
  ["ASSEMBLER", "Montador", "select", ["", "velvet", "spades", "metaspades"]],
  ["THREADS", "Threads", "number"], ["DB", "Banco", "text"],
  ["BLAST_EVALUE", "BLAST e-value", "text"], ["BLAST_MAX_TARGET_SEQS", "Máximo de alvos BLAST", "number"],
  ["HOST_FILTER_ENABLED", "Filtro de hospedeiro habilitado", "select", ["", "false", "true"]],
  ["HOST_NAME", "Hospedeiro", "text"], ["HOST_REF", "Referência do hospedeiro", "text"],
  ["HOST_INDEX_PREFIX", "Prefixo do índice Bowtie2", "text"],
  ["VELVET_K", "k-mer Velvet", "number"], ["MIN_CONTIG_LEN", "Comprimento mínimo do contig", "number"],
  ["SPADES_MEMORY", "Memória SPAdes", "number"], ["SPADES_PARAMS", "Parâmetros SPAdes", "text"],
  ["VELVET_PARAMS", "Parâmetros Velvet", "text"], ["READ_TRKG", "Rastreamento de leituras do Velvet", "select", ["", "yes", "no", "false", "true"]],
  ["BIND_HOST", "Host local do servidor", "text"], ["PORT", "Porta", "number"],
  ["SAMPLE_NAME", "Nome padrão da amostra", "text"], ["SAMPLE_ID", "ID padrão da amostra", "text"],
];

function configControl([key, label, type, options], values) {
  let control;
  if (type === "select") {
    control = h("select", { name: key });
    options.forEach((value) => control.append(h("option", { value, text: value || "Não definido" })));
  } else control = h("input", { name: key, type, min: type === "number" ? "1" : null });
  control.value = values[key] || "";
  return field(`${label} (${key})`, control);
}

function configEditor(store, values) {
  const form = h("form", { class: "gi-panel" }, [
    panelHead("Editar configuração operacional"),
    h("p", { text: "Configuração padrão global para as próximas análises pelo painel e linha de comando. O assistente define em cada análise banco, montador, k-mer, amostra e filtro de hospedeiro; adaptadores preenchidos nele substituem os globais. Valores vazios preservam a configuração atual. Salvar não altera execuções anteriores." }),
  ]);
  const basic = h("div", { class: "grid grid--2" });
  CONFIG_FIELDS.slice(0, 5).forEach((item) => basic.append(configControl(item, values)));
  const host = h("details", {}, [h("summary", { text: "Filtro de hospedeiro" })]);
  host.append(statusPanel("empty", "Filtro opcional", "A execução usa HOST_FILTER_ENABLED, HOST_NAME e HOST_INDEX_PREFIX. O assistente operacional envia host_filter_mode."));
  const hostGrid = h("div", { class: "grid grid--2", style: "margin-top: 16px" });
  CONFIG_FIELDS.slice(5, 9).forEach((item) => hostGrid.append(configControl(item, values)));
  const hostStatus = h("div", { role: "status", "aria-live": "polite" });
  const validateHost = async () => {
    const prefix = form.querySelector("[name='HOST_INDEX_PREFIX']").value.trim();
    hostStatus.replaceChildren(statusPanel("loading", "Validando índice", prefix || "Informe um prefixo."));
    try {
      const result = await postJSON("/api/host-index/validate", { prefix });
      if (!result.valid) { hostStatus.replaceChildren(statusPanel("error", "Índice inválido", result.reason || "Confira o prefixo.")); return false; }
      hostStatus.replaceChildren(statusPanel("success", "Índice válido", result.message || result.path || prefix));
      return true;
    } catch (error) {
      hostStatus.replaceChildren(statusPanel("error", "Índice inválido", error.payload?.reason || error.payload?.error || error.message));
      return false;
    }
  };
  host.append(hostGrid, button("Validar índice", validateHost, "secondary"), h("p", { text: "Validar apenas verifica o índice; use Salvar configuração para persistir o prefixo." }), hostStatus);
  const advanced = h("details", {}, [h("summary", { text: "Configuração avançada" })]);
  const advancedGrid = h("div", { class: "grid grid--2", style: "margin-top: 16px" });
  CONFIG_FIELDS.slice(9).forEach((item) => advancedGrid.append(configControl(item, values)));
  advanced.append(advancedGrid);
  const saveStatus = h("div", { role: "status", "aria-live": "polite" });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const config = Object.fromEntries([...new FormData(form)].filter(([, value]) => String(value).trim()).map(([key, value]) => [key, String(value).trim()]));
    const hostEnabled = String(config.HOST_FILTER_ENABLED || "").toLowerCase() === "true";
    if (hostEnabled && !(await validateHost())) return;
    try {
      const result = await postJSON("/api/config/env", { config });
      saveStatus.replaceChildren(statusPanel("success", "Configuração salva", result.message || "Configuração atualizada."));
      const current = await getJSON("/api/config/env");
      const table = document.getElementById("effective-config-table");
      if (table) table.replaceChildren(dataTable([{ key: "key", label: "Chave" }, { key: "value", label: "Valor" }], Object.entries(current.config || {}).map(([key, value]) => ({ key, value })), "Configuração salva"));
    } catch (error) { saveStatus.replaceChildren(statusPanel("error", "Falha ao salvar", error.payload?.error || error.message)); }
  });
  form.append(basic, host, advanced, h("div", { class: "gi-btnrow", style: "margin-top: 16px" }, h("button", { class: buttonClass(), type: "submit", text: "Salvar configuração" })), saveStatus);
  const rebuild = panel("Reconstruir ambiente", [
    h("p", { text: "Reexecuta o instalador do ambiente e acompanha a operação como job técnico." }),
  ]);
  rebuild.append(button("Reconstruir ambiente", async () => {
    if (!window.confirm("Reconstruir o ambiente local agora?")) return;
    try {
      const response = await postJSON("/api/config/environment/rebuild", {});
      activateJob(store, response.job_id, "Reconstruindo ambiente");
    } catch (error) { toast(error.payload?.error || error.message, "error"); }
  }, "danger"));
  return [form, rebuild];
}

export async function renderSettings(store) {
  const { root, body } = advancedShell(pageHeader("Gene-In", "Configuração e lotes", "Ambiente, amostras, política de análise e configuração operacional."), "settings");
  try {
    const [environment, evidence, config, targets, databases] = await Promise.all([
      getJSON("/api/config/environment"), getJSON("/api/evidence/config"), getJSON("/api/config/env"),
      getJSON("/api/targets"), getJSON("/api/dbs"),
    ]);
    body.append(environment.ok ? statusPanel("success", "Ambiente pronto", environment.preflight?.summary || "Ferramentas obrigatórias disponíveis.") : statusPanel("blocked", "Ambiente com pendências", environment.preflight?.summary || "Revise as dependências."));
    const activeProfile = metric("Perfil", evidence.profile_id || "Análise");
    activeProfile.append(badge("Ativo", "done"));
    body.append(h("section", { class: "gi-metrics", "aria-label": "Política de análise" }, [
      metric("Perfil de análise", evidence.profile_id), metric("Versão do perfil", evidence.profile_version), activeProfile,
    ]));
    const values = config.config || {};
    const rows = Object.entries(values).map(([key, value]) => ({ key, value }));
    body.append(...configEditor(store, values));
    body.append(panel("Configuração padrão global salva", [h("div", { id: "effective-config-table" }, dataTable([{ key: "key", label: "Chave" }, { key: "value", label: "Valor" }], rows, "Configuração salva"))]));
    body.append(sampleImportCard(store));
    const dbBuild = panel("Preparar banco viral", [
      h("p", { text: "Use um alvo do catálogo ou informe uma query NCBI para qualquer vírus fora da lista." }),
    ]);
    const dbName = h("select", { id: "build-db-name" });
    dbName.append(h("option", { value: "", text: "Nenhum — usar query NCBI" }));
    let dbGroup, dbGroupName;
    (databases.dbs?.length ? databases.dbs : (targets.targets || targets || [])).forEach((target) => {
      const value = typeof target === "string" ? target : (target.id || target.key || "");
      const label = typeof target === "string" ? target : (target.label || target.display_name || target.name || value);
      if (value) {
        const groupName = value.startsWith("picornaviridae_") ? "Família Picornaviridae" : "Alvos específicos";
        if (groupName !== dbGroupName) { dbGroup = h("optgroup", { label: groupName }); dbName.append(dbGroup); dbGroupName = groupName; }
        dbGroup.append(h("option", { value, text: label + (target.reference_size_bytes != null ? ` — referência local: ${target.reference_size_bytes} bytes` : " — tamanho local indisponível") }));
      }
    });
    const dbQuery = h("input", { id: "build-db-query", type: "text", placeholder: '"Orbivirus"[Organism] OR "Rotavirus A"[Organism] AND refseq[filter]' });
    const dbTaxid = h("input", { id: "build-db-taxid", type: "text", inputmode: "numeric", placeholder: "12087", "data-kind": "id" });
    dbBuild.append(
      field("Alvo pré-configurado (opcional)", dbName),
      field("Outro vírus / banco customizado — query NCBI", dbQuery, "Preencha para qualquer vírus fora da lista. Aceita qualquer query NCBI válida."),
      field("TaxID (opcional)", dbTaxid, "Usado somente se a query estiver vazia; vira txid<N>[Organism:exp]."),
      button("Preparar banco", async () => {
        const target = dbName.value.trim();
        const query = dbQuery.value.trim();
        const taxid = dbTaxid.value.trim();
        if (!target && !query && !taxid) {
          toast("Selecione um banco de referência ou informe uma query NCBI / TaxID.");
          return;
        }
        const params = {};
        if (query) params.query = query;
        else if (taxid) params.taxid = taxid;
        else params.db = target;
        try {
          const response = await postJSON("/api/run", { action: "build_db", params });
          store.set({ pendingDatabase: params.db || "custom", wizard: { dbQuery: params.query || (params.taxid ? `txid${params.taxid}[Organism:exp]` : "") } });
          activateJob(store, response.job_id, "Preparando banco");
        } catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
      }),
    );
    body.append(dbBuild);
    const evidenceRun = panel("Análise individual", [
      h("p", { text: "O assistente reúne a amostra, o banco e todas as escolhas da execução antes de iniciar. Os relatórios fazem parte da análise." }),
      linkButton("Abrir Nova análise", "#/new"),
    ]);
    body.append(evidenceRun);
    const manifests = await getJSON("/api/evidence/manifests");
    const batch = panel("Análise em lote", [h("p", { text: "O manifesto identifica as amostras e os controles. Confira o banco e o filtro desta execução antes de iniciar." })]);
    const manifestSelect = h("select", { id: "evidence-manifest" });
    (manifests.manifests || []).forEach((manifest) => manifestSelect.append(h("option", { value: manifest.manifest_id, text: `${manifest.manifest_id} · ${manifest.row_count || 0} linhas` })));
    const batchDb = h("input", { id: "evidence-batch-db", type: "text" });
    batchDb.value = values.DB || "";
    const batchQuery = h("input", { id: "batch-db-query", type: "text" });
    const hostMode = h("select", { id: "batch-host-mode" }, [
      h("option", { value: "none", text: "Sem filtro" }),
      h("option", { value: "sus_scrofa", text: "Sus scrofa" }),
      h("option", { value: "custom", text: "Outro hospedeiro" }),
    ]);
    const hostName = h("input", { id: "batch-host-name", type: "text", value: values.HOST_NAME || "" });
    const hostIndex = h("input", { id: "batch-host-index", type: "text", value: values.HOST_INDEX_PREFIX || "" });
    hostMode.value = String(values.HOST_FILTER_ENABLED).toLowerCase() === "true"
      ? (String(values.HOST_NAME).toLowerCase() === "sus scrofa" ? "sus_scrofa" : "custom") : "none";
    const manifestText = h("textarea", { id: "evidence-manifest-text", placeholder: "batch_id\tsample_id\trole\tlibrary_mode\tumi_mode\tr1\tr2\texpected_target" });
    const manifestExport = linkButton("Exportar TSV", "#", "secondary");
    const updateExport = () => {
      manifestExport.hidden = !manifestSelect.value;
      manifestExport.href = `/api/evidence/manifest/export?id=${encodeURIComponent(manifestSelect.value)}`;
    };
    manifestSelect.addEventListener("change", updateExport);
    updateExport();
    batch.append(field("Manifesto existente", manifestSelect), field("Banco", batchDb), h("div", { class: "gi-btnrow" }, [
      button("Executar lote", async () => {
        try {
          if (!manifestSelect.value || !(batchDb.value.trim() || batchQuery.value.trim())) { toast("Selecione um manifesto e informe o banco ou a query."); return; }
          const params = { manifest_id: manifestSelect.value, db: batchDb.value.trim(), host_filter_mode: hostMode.value };
          if (batchQuery.value.trim()) { params.db = "custom"; params.db_query = batchQuery.value.trim(); }
          if (hostMode.value !== "none") {
            if (!hostIndex.value.trim()) { toast("Informe o prefixo do índice do hospedeiro."); return; }
            params.host_index_prefix = hostIndex.value.trim();
            params.host_name = hostMode.value === "sus_scrofa" ? "Sus scrofa" : hostName.value.trim();
            if (!params.host_name) { toast("Informe o nome do hospedeiro."); return; }
          }
          const response = await postJSON("/api/evidence/run", { mode: "batch", params });
          activateJob(store, response.job_id, "Lote iniciado");
        } catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
      }),
      manifestExport,
    ]), field("Query do banco customizado (quando aplicável)", batchQuery), field("Filtro do lote", hostMode),
      field("Nome do hospedeiro", hostName), field("Prefixo do índice do hospedeiro", hostIndex),
      field("Importar manifesto TSV", manifestText), button("Validar e importar manifesto", async () => {
      try {
        const result = await postJSON("/api/evidence/manifests/import", { content: manifestText.value });
        const option = h("option", { value: result.manifest_id, text: result.manifest_id });
        manifestSelect.append(option); manifestSelect.value = result.manifest_id; updateExport();
        toast(`Manifesto importado: ${result.manifest_id}`);
      }
      catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
    }, "secondary"));
    body.append(batch);
  } catch (error) { body.append(statusPanel("error", "Configuração indisponível", error.payload?.error || error.message)); }
  return root;
}
