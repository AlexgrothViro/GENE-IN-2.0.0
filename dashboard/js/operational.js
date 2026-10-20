import { getJSON, postForm, postJSON } from "./api.js";
import { jobLabel, elapsed, formatDate, normalizeStatus, runIdentity } from "./adapters.js";
import { analysisDimensions, badge, button, buttonClass, dataTable, field, h, linkButton, metric, openModal, outcomePanel, pageHeader, panel, panelHead, statusPanel, toast } from "./components.js";
import { activateJob, persistActiveJob } from "./state.js";

const WIZARD_STEPS = ["Ambiente", "Banco", "Amostra", "Configuração", "Revisão", "Execução"];
const CUSTOM_DATABASE = "custom";
const ROLE_LABELS = { sample: "Amostra", positive: "Controle positivo", negative_extraction: "Controle negativo — extração", negative_library: "Controle negativo — biblioteca", negative_sequencing: "Controle negativo — sequenciamento" };

function databaseValue(item) {
  return typeof item === "string" ? item : (item.id || item.key || item.name || "");
}

function databaseLabel(item) {
  return typeof item === "string" ? item : (item.label || item.display_name || item.name || item.id || item.key || "");
}

function databaseReady(wizard) {
  if (!wizard.database) return false;
  return wizard.database !== CUSTOM_DATABASE || Boolean(String(wizard.dbQuery || "").trim());
}

function databaseSummary(wizard) {
  if (wizard.database === CUSTOM_DATABASE) {
    const query = String(wizard.dbQuery || "").trim();
    if (!query) return "Customizado — query NCBI não informada";
    return query.length > 60 ? `Customizado: ${query.slice(0, 57)}…` : `Customizado: ${query}`;
  }
  return wizard.database || "Não selecionado";
}

const HISTORY_ARTIFACT_TYPES = {
  run_qc_html: ["Relatório QC", "qc_html"], run_qc_json: ["QC JSON", "qc_json"],
  run_cleaned_r1: ["Leituras limpas R1", "cleaned_r1"], run_cleaned_r2: ["Leituras limpas R2", "cleaned_r2"],
  run_report: ["Relatório", "report"], run_log: ["Log", "log"], run_blast_tsv: ["BLAST bruto", "blast"],
  run_labeled_hits_tsv: ["Hits classificados", "labeled"], run_adj_identity_tsv: ["Identidade ajustada", "adj_identity"],
  run_hit_contigs_fasta: ["FASTA de hits", "hit_contigs_fasta"], run_assembly_contigs_fasta: ["Contigs montados", "assembly_contigs_fasta"],
  run_advanced_alignment: ["Alinhamento avançado", "run_advanced_alignment"], run_advanced_tree: ["Árvore", "run_advanced_tree"],
  run_advanced_gate: ["Gate avançado", "run_advanced_gate"], run_advanced_hits: ["Hits avançados", "run_advanced_hits"],
  run_advanced_refs: ["Referências avançadas", "run_advanced_refs"], run_advanced_summary: ["Resumo avançado", "run_advanced_summary"],
};

function routeItem(title, description, href) {
  return h("a", { class: "gi-route", href }, [
    h("span", { class: "gi-route__key", text: href.replace(/^#/, "") }),
    h("span", { class: "gi-route__title", text: title }),
    h("p", { text: description }),
  ]);
}

export function renderHome() {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "gi-masthead" }, [
    h("div", { class: "gi-masthead__text" }, [
      h("h1", { text: "Recuperação de sequências candidatas para revisão" }),
      h("p", { text: "Hospedeiro e banco são escolhas da análise. Suíno e picornavírus são o caso-modelo de validação. Execução local." }),
      h("div", { class: "gi-btnrow" }, [linkButton("Iniciar nova análise", "#/new"), linkButton("Acompanhar execução", "#/track", "quiet")]),
      h("a", { href: "/help", text: "Ajuda, instalação, bancos e licenças" }),
    ]),
    h("div", { class: "gi-masthead__img", role: "presentation", style: "background-image: url('/hero-bg.png')" }),
  ]));
  root.append(h("nav", { class: "gi-routes", "aria-label": "Rotas operacionais" }, [
    routeItem("Nova análise", "Wizard operacional em seis etapas.", "#/new"),
    routeItem("Acompanhar", "Etapas, tempo real e log técnico.", "#/track"),
    routeItem("Resultados", "Relatórios e artefatos concluídos.", "#/results"),
    routeItem("Histórico", "Execuções anteriores e rastreabilidade.", "#/history"),
  ]));
  return root;
}

function wizardNav(wizard, onStep) {
  const step = wizard.step;
  const complete = [
    Boolean(wizard.environment?.ok), databaseReady(wizard), Boolean(wizard.sample),
    Boolean(wizard.assembler), Boolean(wizard.environment?.ok && databaseReady(wizard) && wizard.sample),
    false,
  ];
  const list = h("ol", { class: "gi-stepper", "aria-label": "Etapas da nova análise" });
  WIZARD_STEPS.forEach((label, index) => list.append(h("li", {}, h("button", {
    type: "button", "aria-current": index === step ? "step" : null,
    dataset: { complete: Boolean(complete[index] && wizard.visited?.[index]) }, onclick: () => onStep(index),
  }, [h("small", { text: String(index + 1).padStart(2, "0") }), h("span", { text: label })]))));
  return list;
}

function selectOptions(select, items, valueOf, labelOf) {
  select.append(h("option", { value: "", text: "Selecione" }));
  items.forEach((item) => select.append(h("option", { value: valueOf(item), text: labelOf(item) })));
}

export function sampleImportCard(store, { onImported, framed = true } = {}) {
  const heading = (text) => framed ? panelHead(text) : h("h3", { text });
  const wrap = (children) => framed ? h("section", { class: "gi-panel" }, children) : h("div", {}, children);
  const root = h("div", { class: "stack" });
  const filePicker = (name, id, accept) => {
    const input = h("input", { name, id, type: "file", accept, hidden: "hidden" });
    const selected = h("span", { role: "status", text: "Nenhum arquivo escolhido" });
    input.addEventListener("change", () => { selected.textContent = input.files?.[0]?.name || "Nenhum arquivo escolhido"; });
    return h("div", { class: "gi-btnrow" }, [input, button("Escolher arquivo", () => input.click(), "secondary"), selected]);
  };
  const upload = h("form", { onsubmit: async (event) => {
    event.preventDefault();
    if (upload.dataset.busy === "true") return;
    const data = new FormData(upload);
    const sample = String(data.get("sample") || "").trim();
    const r1 = upload.querySelector("[name='r1file']")?.files?.[0];
    const r2 = upload.querySelector("[name='r2file']")?.files?.[0];
    const zip = upload.querySelector("[name='zipfile']")?.files?.[0];
    if (!sample) { toast("Informe o identificador da amostra."); return; }
    if (!(zip || (r1 && r2))) { toast("Envie o par R1/R2 ou um arquivo .zip."); return; }
    try {
      upload.dataset.busy = "true";
      upload.setAttribute("aria-busy", "true");
      upload.querySelector("button[type='submit']").disabled = true;
      uploadStatus.textContent = "Enviando e validando arquivos… aguarde.";
      uploadProgress.hidden = false;
      uploadProgress.value = 0;
      const result = await postForm("/api/import-upload", data, (loaded, total) => {
        if (loaded === null) {
          uploadProgress.removeAttribute("value");
          uploadStatus.textContent = "Envio concluído. Validando os arquivos no servidor…";
        } else if (total) {
          uploadProgress.value = loaded / total * 100;
          uploadStatus.textContent = `Enviando arquivos: ${Math.floor(loaded / total * 100)}%.`;
        } else {
          uploadProgress.removeAttribute("value");
          uploadStatus.textContent = `Enviando arquivos: ${loaded.toLocaleString("pt-BR")} bytes enviados.`;
        }
      });
      const m = result.metadata || {};
      uploadStatus.textContent = `${result.sample_id || sample}: R1 ${m.r1_name || ""} (${m.r1_size_bytes ?? "?"} bytes); R2 ${m.r2_name || ""} (${m.r2_size_bytes ?? "?"} bytes); ${m.read_count_pairs ?? "?"} pares.`;
      toast(result.message || `Amostra importada: ${sample}`);
      if (typeof onImported === "function") await onImported(result.sample_id || sample);
    } catch (error) { uploadStatus.textContent = error.message; toast(error.payload?.error || error.payload || error.message, "error"); }
    finally { uploadProgress.hidden = true; upload.dataset.busy = "false"; upload.setAttribute("aria-busy", "false"); upload.querySelector("button[type='submit']").disabled = false; }
  } });
  const uploadStatus = h("p", { role: "status", "aria-live": "polite" });
  const uploadProgress = h("progress", { max: "100", value: "0", hidden: "hidden", "aria-label": "Progresso do envio" });
  upload.append(uploadProgress);
  upload.append(
    heading("Importar amostra"),
    h("p", { text: "Importe os arquivos FASTQ pareados R1/R2 ou um ZIP com esse par." }),
    field("Identificador da amostra", h("input", { name: "sample", id: "import-upload-sample", type: "text", required: "required", "data-kind": "id" })),
    field("FASTQ R1", filePicker("r1file", "import-upload-r1", ".fastq,.fq,.fastq.gz,.fq.gz")),
    field("FASTQ R2", filePicker("r2file", "import-upload-r2", ".fastq,.fq,.fastq.gz,.fq.gz")),
    field("Arquivo .zip (opcional)", filePicker("zipfile", "import-upload-zip", ".zip"), "Alternativa ao par R1/R2."),
    field("Substituir explicitamente uma amostra já importada", h("input", { name: "replace", id: "import-replace", type: "checkbox", value: "true" }), "Sobrescreve as entradas R1/R2 desse identificador. Confirme os arquivos; execuções em andamento bloqueiam a substituição."),
    h("button", { class: buttonClass(), type: "submit", text: "Importar upload" }),
    uploadStatus,
  );
  root.append(wrap(upload));
  const sampleName = h("input", { id: "import-path-sample", type: "text", "data-kind": "id" });
  const r1Path = h("input", { id: "import-path-r1", type: "text", "data-kind": "path", placeholder: "C:\\dados\\amostra_R1.fastq.gz" });
  const r2Path = h("input", { id: "import-path-r2", type: "text", "data-kind": "path", placeholder: "C:\\dados\\amostra_R2.fastq.gz" });
  const copy = h("input", { id: "import-path-copy", type: "checkbox" });
  const local = h("details", {}, [
    h("summary", { text: "Caminho local (avançado)" }),
    h("p", { text: "Aceita caminho Windows com normalização automática para o ambiente WSL." }),
    field("Nome da amostra", sampleName),
    field("Caminho R1", r1Path),
    field("Caminho R2", r2Path),
    h("label", { class: "gi-field gi-field--check" }, [h("span", {}, [copy, " Copiar arquivos (em vez de symlink)"])]),
    button("Importar por caminho", async () => {
      const sample = sampleName.value.trim();
      if (!sample || !r1Path.value.trim() || !r2Path.value.trim()) {
        toast("Informe o identificador e os caminhos R1 e R2.");
        return;
      }
      try {
        const response = await postJSON("/api/run", { action: "import_sample", params: { sample, r1: r1Path.value.trim(), r2: r2Path.value.trim(), copy: copy.checked } });
        activateJob(store, response.job_id, `Importando ${sample}`);
      } catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
    }),
  ]);
  root.append(wrap(local));
  root.append(h("div", { class: "gi-btnrow" }, [
    button("Gerar amostra DEMO", async () => {
      try {
        const response = await postJSON("/api/run", { action: "demo", params: {} });
        activateJob(store, response.job_id, "Gerando amostra DEMO");
      } catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
    }, "secondary"),
  ]));
  return root;
}

export async function renderNewAnalysis(store, rerender) {
  const state = store.get();
  const wizard = state.wizard;
  const root = h("div", {}, [pageHeader("Operação guiada", "Nova análise", "Ambiente → banco → amostra → configuração → revisão → execução.")]);
  root.append(wizardNav(wizard, (step) => { store.set({ wizard: { step, visited: { [wizard.step]: true } } }); rerender(); }));
  const card = h("section", { class: "gi-panel" });
  root.append(card);
  if (!wizard.loaded) {
    card.append(statusPanel("loading", "Verificando pré-requisitos", "Carregando ambiente, bancos e amostras locais."));
    try {
      const [environment, databases, samples, targets, config] = await Promise.all([
        getJSON("/api/preflight"), getJSON("/api/dbs"), getJSON("/api/samples"), getJSON("/api/targets"),
        getJSON("/api/config/env"),
      ]);
      const dbs = databases.dbs?.length ? databases.dbs : (targets.targets || targets || []);
      store.set({ wizard: { loaded: true, environment, databases: dbs, samples: samples.samples || [], savedConfig: config.config || {} }, context: { environment: environment.ok ? "Pronto" : "Com pendências" } });
      return renderNewAnalysis(store, rerender);
    } catch (error) {
      store.set({ wizard: { loaded: true, loadError: error.message }, context: { environment: "Indisponível" } });
      return renderNewAnalysis(store, rerender);
    }
  }
  const setStep = (step) => { store.set({ wizard: { step, visited: { [wizard.step]: true } } }); rerender(); };
  if (wizard.step === 0) {
    const environment = wizard.environment || {};
    card.append(panelHead("1. Ambiente"));
    card.append(environment.ok ? statusPanel("success", "Ambiente pronto", environment.summary || "Ferramentas obrigatórias disponíveis.") : statusPanel("blocked", "Ambiente com pendências", environment.summary || wizard.loadError || "Conclua a verificação de ferramentas antes de executar."));
  }
  if (wizard.step === 1) {
    card.append(panelHead("2. Banco viral"));
    const select = h("select", { id: "wizard-db" });
    select.append(h("option", { value: "", text: "Selecione" }));
    let group;
    let groupName;
    (wizard.databases || []).forEach((item) => {
      const value = databaseValue(item);
      const name = value.startsWith("picornaviridae_") ? "Família Picornaviridae" : "Alvos específicos";
      if (name !== groupName) { group = h("optgroup", { label: name }); select.append(group); groupName = name; }
      group.append(h("option", { value, text: databaseLabel(item) + (item.reference_size_bytes != null ? ` — referência local: ${item.reference_size_bytes} bytes` : " — tamanho local indisponível") }));
    });
    if (!(wizard.databases || []).some((item) => databaseValue(item) === CUSTOM_DATABASE)) {
      select.append(h("option", { value: CUSTOM_DATABASE, text: "Outro vírus — query NCBI" }));
    }
    select.value = wizard.database;
    const query = h("input", {
      id: "wizard-db-query", type: "text", value: wizard.dbQuery || "",
      placeholder: '"Orbivirus"[Organism] OR "Rotavirus A"[Organism] AND refseq[filter]',
    });
    const persistDatabase = () => {
      const custom = select.value === CUSTOM_DATABASE;
      store.set({
        wizard: { database: select.value, dbQuery: custom ? query.value.trim() : "" },
        context: { database: custom ? databaseSummary({ database: CUSTOM_DATABASE, dbQuery: query.value }) : (select.options[select.selectedIndex]?.text || "Não selecionado") },
      });
    };
    select.addEventListener("change", persistDatabase);
    query.addEventListener("input", () => {
      if (query.value.trim() && select.value !== CUSTOM_DATABASE) select.value = CUSTOM_DATABASE;
      persistDatabase();
    });
    card.append(field("Banco de referência", select, "A seleção delimita a busca por homologia; não altera limiares científicos."));
    card.append(field("Outro vírus / banco customizado — query NCBI", query, "Preencha para qualquer vírus fora da lista. Aceita qualquer query NCBI válida; obrigatório se escolher Outro vírus."));
    card.append(h("p", { text: "Query é a expressão de busca no NCBI: [Organism] indica o organismo; OR combina alternativas; AND exige ambas as condições; refseq[filter] limita às referências RefSeq. Evidence V2 é a camada de relatórios e rastreabilidade das sequências candidatas." }));
    card.append(h("p", { text: "Bancos não acompanham o pacote. Preparar baixa referências do NCBI e cria índices locais; requer internet, espaço e tempo. Selecionar um banco não o prepara automaticamente nesta tela." }));
    const dbStatus = h("p");
    const refreshStatus = () => {
      const selected = (wizard.databases || []).find((item) => databaseValue(item) === select.value);
      dbStatus.textContent = selected?.prepared ? "Manifesto local disponível; a integridade será conferida antes da busca." : "Banco ainda não preparado ou sem manifesto local. Prepare antes de executar.";
    };
    refreshStatus();
    select.addEventListener("change", refreshStatus);
    card.append(dbStatus, button("Preparar banco selecionado", async () => {
      if (!select.value) { toast("Selecione um banco.", "error"); return; }
      try {
        const response = await postJSON("/api/run", { action: "build_db", params: { db: select.value, query: query.value.trim() } });
        store.set({ pendingDatabase: select.value });
        activateJob(store, response.job_id, "Preparando banco");
      } catch (error) { toast(error.payload?.error || error.message, "error"); }
    }, "secondary"));
  }
  if (wizard.step === 2) {
    card.append(panelHead("3. Amostra"));
    const select = h("select", { id: "wizard-sample" });
    selectOptions(select, wizard.samples || [], (item) => item, (item) => item);
    select.value = wizard.sample;
    select.addEventListener("change", () => { store.set({ wizard: { sample: select.value }, context: { sample: select.value || "Não selecionada" } }); });
    card.append(field("Amostra pareada já importada", select, "Entradas locais já importadas, com arquivos R1 e R2 válidos."));
    const role = h("select", { id: "wizard-role" }, [
      ["sample", "Amostra"], ["positive", "Controle positivo"], ["negative_extraction", "Controle negativo — extração"],
      ["negative_library", "Controle negativo — biblioteca"], ["negative_sequencing", "Controle negativo — sequenciamento"],
    ].map(([value, text]) => h("option", { value, text })));
    role.value = wizard.role || "sample";
    role.addEventListener("change", () => store.set({ wizard: { role: role.value } }));
    const batch = h("input", { id: "wizard-batch", type: "text", value: wizard.batchId || "" });
    batch.addEventListener("change", () => store.set({ wizard: { batchId: batch.value.trim() } }));
    const expected = h("input", { id: "wizard-expected-target", type: "text", value: wizard.expectedTarget || "" });
    expected.addEventListener("change", () => store.set({ wizard: { expectedTarget: expected.value.trim() } }));
    expected.required = role.value === "positive";
    role.addEventListener("change", () => { expected.required = role.value === "positive"; });
    card.append(field("Papel da amostra", role), field("Lote (opcional)", batch, "Identifica a execução. A avaliação conjunta de controles exige executar o manifesto de lote na Área avançada."), field("Alvo esperado (obrigatório para controle positivo)", expected));
    if (!(wizard.samples || []).length) card.append(statusPanel("empty", "Nenhuma amostra importada ainda", "Use o upload, um caminho local ou a amostra DEMO abaixo."));
    card.append(sampleImportCard(store, {
      framed: false,
      onImported: async (sampleId) => {
        const samples = await getJSON("/api/samples");
        const selected = store.get().wizard.sample;
        store.set({ wizard: { samples: samples.samples || [], sample: selected || sampleId }, context: { sample: selected || sampleId } });
        if (selected && selected !== sampleId) toast(`Importada ${sampleId}. A seleção continua em ${selected}; selecione a nova amostra quando desejar.`);
        rerender();
      },
    }));
  }
  if (wizard.step === 3) {
    card.append(panelHead("4. Configuração"));
    const assembler = h("select", { id: "wizard-assembler" }, [h("option", { value: "consensus", text: "MULTI — SPAdes, metaSPAdes e Velvet" }), h("option", { value: "spades", text: "SPAdes" }), h("option", { value: "metaspades", text: "metaSPAdes" }), h("option", { value: "velvet", text: "Velvet" })]);
    assembler.value = wizard.assembler;
    assembler.addEventListener("change", () => store.set({ wizard: { assembler: assembler.value } }));
    card.append(field("Montagem", assembler, "MULTI preserva as sequências dos três montadores, inclusive as produzidas por apenas um deles."));
    const runLabel = h("input", { id: "wizard-label", type: "text", maxlength: "120", value: wizard.label || "" });
    runLabel.addEventListener("change", () => store.set({ wizard: { label: runLabel.value.trim() } }));
    card.append(field("Rótulo desta execução (opcional)", runLabel));
    const details = h("details", { open: "open" }, [h("summary", { text: "Limpeza das leituras e configurações técnicas" })]);
    const kmer = h("input", { id: "wizard-kmer", type: "number", min: "15", max: "127", value: wizard.kmer });
    kmer.addEventListener("change", () => store.set({ wizard: { kmer: kmer.value } }));
    const host = h("select", { id: "wizard-host" }, [h("option", { value: "none", text: "Sem filtro de hospedeiro" }), h("option", { value: "sus_scrofa", text: "Sus scrofa — exige índice preparado separadamente" }), h("option", { value: "custom", text: "Hospedeiro personalizado" })]);
    host.value = wizard.hostMode;
    host.addEventListener("change", () => {
      const saved = wizard.savedConfig || {};
      const prefix = host.value === "sus_scrofa" && saved.HOST_NAME === "Sus scrofa" ? saved.HOST_INDEX_PREFIX || "" : hostIndex.value.trim();
      hostIndex.value = prefix;
      store.set({ wizard: { hostMode: host.value, hostIndexPrefix: prefix } });
    });
    details.append(field("k-mer do Velvet", kmer, "Tamanho dos trechos usados pelo Velvet para montar sequências: número ímpar entre 15 e 127. SPAdes e metaSPAdes usam suas próprias configurações."), field("Filtro do hospedeiro", host, "Remove leituras alinhadas ao genoma do hospedeiro antes da montagem. Ative somente com um índice preparado para o hospedeiro da amostra."));
    const hostName = h("input", { id: "wizard-host-name", type: "text", value: wizard.hostName || "" });
    const hostIndex = h("input", { id: "wizard-host-index", type: "text", value: wizard.hostIndexPrefix || "" });
    hostName.addEventListener("change", () => store.set({ wizard: { hostName: hostName.value.trim() } }));
    hostIndex.addEventListener("change", () => store.set({ wizard: { hostIndexPrefix: hostIndex.value.trim() } }));
    details.append(field("Nome do hospedeiro personalizado", hostName, "Obrigatório para hospedeiro personalizado."), field("Prefixo do índice Bowtie2", hostIndex, "Informe o prefixo sem .1.bt2. O índice deve ser preparado previamente; não acompanha o pacote. Para Sus scrofa, vazio usa o prefixo salvo para esse hospedeiro."));
    details.append(button("Validar índice de hospedeiro", async () => {
      try {
        const response = await postJSON("/api/host-index/validate", { prefix: hostIndex.value.trim() });
        toast(response.valid ? "Índice completo disponível." : response.reason || "Índice indisponível.", response.valid ? "success" : "error");
      } catch (error) { toast(error.message, "error"); }
    }, "secondary"));
    const adapterR1 = h("input", { id: "wizard-adapter-r1", type: "text", value: wizard.qcAdapterR1 || "", maxlength: "500" });
    const adapterR2 = h("input", { id: "wizard-adapter-r2", type: "text", value: wizard.qcAdapterR2 || "", maxlength: "500" });
    adapterR1.addEventListener("change", () => store.set({ wizard: { qcAdapterR1: adapterR1.value.trim().toUpperCase() } }));
    adapterR2.addEventListener("change", () => store.set({ wizard: { qcAdapterR2: adapterR2.value.trim().toUpperCase() } }));
    adapterR1.setAttribute("pattern", "[ACGTNacgtn]*");
    adapterR2.setAttribute("pattern", "[ACGTNacgtn]*");
    details.append(field("Adaptador R1 (opcional)", adapterR1, "Cole Adapter do SampleSheet: adaptador 3′ que pode aparecer quando o fragmento é menor que a leitura (read-through). Use A/C/G/T/N. Vazio usa a configuração salva ou busca automática de adaptadores."), field("Adaptador R2 (opcional)", adapterR2, "Cole AdapterRead2 do SampleSheet; confirme a sequência da biblioteca. Vazio usa a configuração salva ou busca automática de adaptadores."));
    card.append(details);
  }
  if (wizard.step === 4) {
    card.append(panelHead("5. Revisão"));
    const rows = [
      ["Ambiente", wizard.environment?.ok ? "Pronto" : "Com pendências"], ["Banco", databaseSummary(wizard)],
      ["Amostra", wizard.sample || "Não selecionada"], ["Montador", wizard.assembler === "consensus" ? "MULTI — SPAdes, metaSPAdes e Velvet" : wizard.assembler], ["k-mer", wizard.kmer],
      ["Hospedeiro", wizard.hostMode === "custom" ? (wizard.hostName || "Nome não informado") : wizard.hostMode === "sus_scrofa" ? "Sus scrofa" : "Sem filtro"],
      ["Índice de hospedeiro", wizard.hostMode === "none" ? "Não utilizado" : wizard.hostIndexPrefix || "Prefixo configurado para Sus scrofa"],
      ["Papel da amostra", ROLE_LABELS[wizard.role || "sample"] || wizard.role], ["Lote", wizard.batchId || "Não informado"],
      ["Adaptador R1", wizard.qcAdapterR1 || "Configuração salva ou busca automática"],
      ["Adaptador R2", wizard.qcAdapterR2 || "Configuração salva ou busca automática"],
    ];
    card.append(dataTable([{ key: "label", label: "Item" }, { key: "value", label: "Seleção" }], rows.map(([label, value]) => ({ label, value })), "Revisão da análise"));
    if (wizard.hostMode === "none") card.append(statusPanel("warning", "Filtro de hospedeiro desligado", "Leituras e contigs do hospedeiro ou de outros organismos podem permanecer. Um contig longo não estabelece origem viral. Compare os comprimentos com as referências e revise os alinhamentos; use um índice apropriado se desejar filtrar o hospedeiro."));
    card.append(button("Revisar limites da execução", (event) => openModal(
      "Limites desta execução",
      h("div", {}, [
        statusPanel("info", "Conferência antes da execução", "Esta tela confere seleções; ainda não há resultados nem verificação de integridade dos artefatos."),
        h("p", { text: "Memória e tempo dependem da biblioteca, do banco e dos montadores. O índice do hospedeiro deve estar preparado; a integridade do banco será conferida antes da busca. A execução recupera candidatos para revisão pelo pesquisador." }),
      ]),
      event.currentTarget,
    ), "secondary"));
    const missing = [];
    if (!wizard.environment?.ok) missing.push("resolver o ambiente");
    if (!databaseReady(wizard)) missing.push(wizard.database === CUSTOM_DATABASE ? "informar a query NCBI do banco customizado" : "selecionar o banco");
    if (!wizard.sample) missing.push("selecionar a amostra");
    if (wizard.role === "positive" && !wizard.expectedTarget?.trim()) missing.push("informar o alvo esperado do controle positivo");
    if (missing.length) card.append(statusPanel("blocked", "Execução bloqueada", `Para continuar: ${missing.join("; ")}.`));
  }
  if (wizard.step === 5) {
    card.append(panelHead("6. Execução"));
    const missing = [];
    if (!wizard.environment?.ok) missing.push("ambiente pendente");
    if (!databaseReady(wizard)) missing.push(wizard.database === CUSTOM_DATABASE ? "query NCBI do banco customizado" : "banco não selecionado");
    if (!wizard.sample) missing.push("amostra não selecionada");
    if (wizard.role === "positive" && !wizard.expectedTarget?.trim()) missing.push("alvo esperado do controle positivo não informado");
    const execute = button("Executar análise", async () => {
      try {
        execute.disabled = true;
        const params = { sample: wizard.sample, db: wizard.database, assembler: wizard.assembler, kmer: wizard.kmer, host_filter_mode: wizard.hostMode, analysis_profile: wizard.assembler === "consensus" ? "assembly-consensus" : "default" };
        params.role = wizard.role || "sample";
        if (wizard.label) params.label = wizard.label;
        if (wizard.batchId) params.batch_id = wizard.batchId;
        if (wizard.expectedTarget) params.expected_target = wizard.expectedTarget;
        if (wizard.hostMode !== "none" && wizard.hostIndexPrefix) params.host_index_prefix = wizard.hostIndexPrefix;
        if (wizard.hostMode === "custom") params.host_name = wizard.hostName || "";
        if (wizard.database === CUSTOM_DATABASE && wizard.dbQuery) params.db_query = wizard.dbQuery.trim();
        if (wizard.qcAdapterR1) params.qc_adapter_r1 = wizard.qcAdapterR1;
        if (wizard.qcAdapterR2) params.qc_adapter_r2 = wizard.qcAdapterR2;
        const response = await postJSON("/api/run", { action: "evidence_pipeline", params });
        activateJob(store, response.job_id, "Iniciando");
      } catch (error) { execute.disabled = false; toast(error.payload?.error || error.payload || error.message, "error"); }
    }, "", { disabled: missing.length ? "disabled" : null, title: missing.length ? `Bloqueado: ${missing.join("; ")}` : null });
    card.append(missing.length ? statusPanel("blocked", "Não é possível executar", `Corrija: ${missing.join("; ")}.`) : statusPanel("success", "Pronto para executar", "A análise usará o perfil configurado e exibirá etapas e tempo decorrido real."), h("div", { class: "gi-btnrow", style: "margin-top: 16px" }, execute));
  }
  const controls = h("div", { class: "gi-btnrow", style: "margin-top: 16px" });
  if (wizard.step > 0) controls.append(button("Voltar", () => setStep(wizard.step - 1), "secondary"));
  if (wizard.step < 5) controls.append(button("Próximo", () => setStep(wizard.step + 1)));
  root.append(controls);
  return root;
}

function logCard(job) {
  const output = h("pre", { class: "gi-mono log-output", tabindex: "0", text: job.output || job.tail || "Aguardando saída…" });
  return panel("Log técnico", [output]);
}

export async function renderTrack(store, rerender, requestedJobId = "") {
  const root = h("div", { class: "stack" }, [pageHeader("Operação", "Acompanhar", "Etapas e tempo decorrido real. Nenhuma porcentagem ou previsão é inventada.")]);
  let active = store.get().activeJob;
  if (requestedJobId && active?.id !== requestedJobId) {
    active = persistActiveJob({ id: requestedJobId, status: "queued", startedAt: new Date().toISOString() });
    store.set({ activeJob: active });
  }
  if (!active?.id) { root.append(statusPanel("empty", "Nenhuma execução ativa", "Inicie uma nova análise ou escolha uma execução no histórico.")); return root; }
  try {
    const job = await getJSON(`/api/job/${encodeURIComponent(active.id)}`);
    const status = normalizeStatus(job.status);
    const updated = persistActiveJob({ ...active, ...job, status });
    store.set({ activeJob: updated, context: { job: jobLabel(status) } });
    root.append(statusPanel(status, `Status técnico: ${jobLabel(status)}`, `Tempo decorrido: ${elapsed(job.started_at || active.startedAt, job.finished_at || Date.now())}. Este painel descreve o job, não a evidência científica.`));
    if (job.evidence_v2_status || job.experimental_warning || job.experimental_analysis_outcome) {
      root.append(statusPanel(
        job.experimental_warning ? "not_evaluable" : "done",
        `Evidence V2: ${job.evidence_v2_status || "não informado"}`,
        job.experimental_warning || `analysis_outcome: ${job.experimental_analysis_outcome || "ainda não disponível"}.`,
      ));
    }
    if (Array.isArray(job.stage_status)) {
      const list = h("ol", { class: "gi-timeline" });
      job.stage_status.forEach((stage) => {
        const state = normalizeStatus(stage.status);
        const duration = stage.started_at ? elapsed(stage.started_at, stage.finished_at || Date.now()) : "";
        list.append(h("li", { dataset: { state } }, [
          h("span", {}, [h("strong", { text: stage.label || stage.id }), document.createTextNode(` — ${stage.status}`)]),
          duration ? h("time", { text: duration }) : null,
        ]));
      });
      root.append(panel("Etapas", [list]));
    }
    root.append(logCard(job));
    if (status === "failed" && job.run?.run_dir) root.append(panel("Saídas parciais — análise incompleta", [h("p", { text: "Arquivos das etapas concluídas, preservados para inspeção técnica. Não representam resultado final." }), artifactActions({ runDir: job.run.run_dir, paths: job.run.paths || {} })]));
    if (status === "failed") root.append(statusPanel("error", `Falha na etapa: ${job.failed_stage || "consulte o log"}`, `${job.failure_message || "Processo interrompido."} Código de saída: ${job.returncode ?? "não registrado"}. Tipo técnico: ${job.failure_type || "não informado"}. Preserve o log; confira o índice, o ambiente e a memória disponível antes de tentar novamente. Falha técnica não equivale a ausência de candidatos.`));
    if (["failed", "cancelled"].includes(status)) root.append(button("Revisar e reexecutar", async () => {
      try {
        const history = await getJSON("/api/history");
        const previous = (history.runs || []).map(runIdentity).find((run) => run.id === active.id);
        if (!previous?.sample) { toast("Execução sem amostra registrada. Escolha a entrada em Nova análise.", "error"); return; }
        reviewRerun(store, previous);
      } catch (error) { toast(error.message, "error"); }
    }, "secondary"));
    if (status === "running") {
      root.append(h("div", { class: "gi-btnrow" }, button("Cancelar execução", (event) => {
        let close;
        const confirm = button("Confirmar cancelamento", async () => {
          confirm.disabled = true;
          try { await postJSON(`/api/job/${encodeURIComponent(active.id)}/cancel`, {}); close(); rerender(); }
          catch (error) { confirm.disabled = false; toast(error.message, "error"); }
        }, "danger");
        close = openModal("Cancelar esta execução?", h("div", {}, [h("p", { text: "O processamento será interrompido. As saídas parciais não constituem resultado final." }), confirm]), event.currentTarget);
      }, "danger")));
      window.setTimeout(() => { if (location.hash.startsWith("#/track")) rerender(); }, 2000);
    }
    if (["done", "partial"].includes(status) && job.action === "build_db") {
      const selected = store.get().pendingDatabase || store.get().wizard.database;
      store.set({ wizard: { loaded: false, database: selected, step: 1 }, context: { database: selected || "Preparado" } });
      root.append(statusPanel("success", "Banco preparado", "Volte ao assistente para conferir o banco e continuar a análise."), linkButton("Continuar nova análise", "#/new"));
    } else if (["done", "partial"].includes(status)) root.append(h("div", { class: "gi-btnrow" }, linkButton("Abrir resultados", "#/results")));
  } catch (error) {
    if (error.status === 404) {
      persistActiveJob(null);
      store.set({ activeJob: null, context: { job: "Expirada" } });
      root.append(statusPanel("unavailable", "Execução expirada ou servidor reiniciado", "O job não está mais na memória do servidor. Consulte o histórico para localizar artefatos promovidos."), h("div", { class: "gi-btnrow" }, linkButton("Abrir histórico", "#/history", "secondary")));
    } else root.append(statusPanel("error", "Execução indisponível", error.payload?.error || error.message));
  }
  return root;
}

function artifactActions(run) {
  const actions = h("div", { class: "gi-btnrow" });
  Object.keys(run.paths || {}).forEach((key) => {
    const item = HISTORY_ARTIFACT_TYPES[key];
    if (item && run.runDir) actions.append(linkButton(item[0], `/api/history/file?run=${encodeURIComponent(run.runDir)}&type=${encodeURIComponent(item[1])}`, "secondary"));
  });
  return actions;
}

async function rerunOfficial(store, run) {
  try {
    const response = await postJSON("/api/history/rerun", { run_dir: run.runDir });
    activateJob(store, response.job_id, `Reexecutando ${run.sample}`);
  } catch (error) { toast(error.payload?.error || error.payload || error.message, "error"); }
}

function reviewRerun(store, run) {
  const p = run.params || {};
  store.set({ wizard: { loaded: false, step: 3, visited: {}, sample: p.sample || run.sample,
    database: p.db || "", dbQuery: p.db_query || "", assembler: p.assembler || store.get().wizard.assembler,
    kmer: p.kmer || store.get().wizard.kmer, hostMode: p.host_filter_mode || "none",
    hostName: p.host_name || "", hostIndexPrefix: p.host_index_prefix || "",
    qcAdapterR1: p.qc_adapter_r1 || "", qcAdapterR2: p.qc_adapter_r2 || "",
    role: p.role || "sample", expectedTarget: p.expected_target || "", batchId: p.batch_id || "", label: p.label || "" }, context: { sample: p.sample || run.sample } });
  toast("Confira banco e configuração antes de executar novamente.");
  location.hash = "#/new";
}

export async function renderResults(store, selectedRunId = "") {
  const root = h("div", { class: "stack" }, [pageHeader("Operação", "Resultados", "Conclusões e artefatos da análise com sua rastreabilidade técnica.")]);
  const history = await getJSON("/api/history").catch(() => ({ runs: [] }));
  const completed = (history.runs || []).map(runIdentity).filter((run) => ["done", "partial", "failed", "cancelled", "not_evaluable"].includes(run.status) || run.evidence);
  if (!completed.length) { root.append(statusPanel("empty", "Nenhum resultado concluído", "Execuções em andamento ou falhas permanecem disponíveis em Acompanhar e Histórico.")); return root; }
  const run = completed.find((item) => item.id === selectedRunId) || completed[0];
  const select = h("select", { id: "results-run" });
  completed.forEach((item) => select.append(h("option", { value: item.id, text: `${item.sample} · ${item.id}` })));
  select.value = run.id;
  select.addEventListener("change", () => { location.hash = `#/results?run=${encodeURIComponent(select.value)}`; });
  root.append(field("Execução", select, "A seleção permanece identificada na URL. Artefatos incompletos ou inválidos não são apresentados como resultados concluídos."));
  if (run.jobStatus && run.jobStatus !== run.status) {
    root.append(statusPanel("empty", `Status técnico do job: ${jobLabel(run.jobStatus)}`, "O estado do job não é evidência científica."));
  }
  if (["failed", "cancelled"].includes(run.status)) {
    root.append(statusPanel("error", `Execução: ${jobLabel(run.status)}`, "A análise não concluiu. Arquivos parciais servem para inspeção técnica; não constituem resultado final nem ausência de candidatos."));
    if (run.runDir) root.append(panel("Saídas parciais — análise incompleta", [artifactActions(run)]));
  } else if (run.status === "validation_pending") {
    root.append(statusPanel("empty", "Validando resultados", "Os arquivos estão sendo verificados em segundo plano. Atualize esta página em instantes."));
    root.append(button("Atualizar resultados", () => location.reload(), "secondary"));
  } else if (run.evidence) {
    root.append(button("Revalidar arquivos", async () => {
      try {
        await getJSON(`/api/evidence/result?run=${encodeURIComponent(run.id)}&refresh=1`);
        toast("Revalidação solicitada. Atualize os resultados em instantes.");
      } catch (error) { toast(error.message, "error"); }
    }, "secondary"));
    try {
      const summary = await getJSON(`/api/evidence/analytics?run=${encodeURIComponent(run.id)}`);
      if (!summary.validation.valid) {
        root.append(statusPanel("not_evaluable", "Execução incompleta ou inválida", summary.validation.message || "Artefatos não validados não são apresentados como resultado final."));
        root.append(outcomePanel("NOT_EVALUABLE"));
      } else {
        root.append(outcomePanel(summary.metadata.analysis_outcome));
        const result = await getJSON(`/api/evidence/result?run=${encodeURIComponent(run.id)}`);
        const available = new Set(result.artifacts || []);
        const recoveryActions = h("div", { class: "gi-btnrow" });
        [["candidate_fasta", "Sequências candidatas (FASTA)"], ["candidate_sequences", "Tabela de candidatos"], ["candidate_queries", "Origens e rastreabilidade"]].forEach(([type, label]) => {
          if (available.has(type)) recoveryActions.append(linkButton(label, `/api/evidence/artifact?run=${encodeURIComponent(run.id)}&type=${encodeURIComponent(type)}`, "secondary"));
        });
        if (recoveryActions.childNodes.length) root.append(panel("Sequências recuperadas para revisão", [h("p", { text: "Contigs e reads candidatos são preservados com seu comprimento e origem. A presença de um alinhamento exige avaliação posterior da especificidade e do suporte." }), recoveryActions]));
        root.append(panel("Dimensões da análise", [
          analysisDimensions({
            execution_status: summary.metadata.execution_status,
            analysis_outcome: summary.metadata.analysis_outcome,
            evidence_level: summary.metadata.evidence_level,
            promotion_status: summary.metadata.promotion_status || summary.promotion_summary?.status,
            control_status: summary.controls?.status,
            reported_conclusion: summary.metadata.reported_conclusion,
          }),
        ]));
      }
    } catch (error) {
      root.append(statusPanel("not_evaluable", "Evidence V2 não avaliável", error.payload?.error || error.message));
    }
  } else {
    root.append(statusPanel("empty", "Resultado operacional 1.1", "Este snapshot não contém artefatos Evidence V2."));
  }
  root.append(h("section", { class: "gi-metrics", "aria-label": "Identificação da execução" }, [
    metric("Execução", run.id), metric("Amostra", run.sample), metric(["failed", "cancelled"].includes(run.status) ? "Interrompida" : "Finalizada", formatDate(run.finished)),
  ]));
  const actions = h("div", { class: "gi-btnrow" });
  if (["failed", "cancelled"].includes(run.status) && run.sample) actions.append(button("Revisar e reexecutar", () => reviewRerun(store, run), "secondary"));
  if (run.evidence && run.valid) actions.append(linkButton("Abrir explorador avançado", `#/analytics?run=${encodeURIComponent(run.id)}`, "secondary"));
  if (run.runDir && run.valid !== false) actions.append(artifactActions(run));
  if (run.runDir && run.action && !run.evidence && !run.comparison) actions.append(button("Reexecutar", () => rerunOfficial(store, run), "secondary"));
  root.append(actions);
  return root;
}

export async function renderHistory(store) {
  const root = h("div", { class: "stack" }, [pageHeader("Rastreabilidade", "Histórico", "Execuções e seus artefatos são identificados por origem e estado técnico.")]);
  try {
    const payload = await getJSON("/api/history");
    const runs = (payload.runs || []).map(runIdentity);
    if (!runs.length) { root.append(statusPanel("empty", "Histórico vazio", "Nenhuma execução foi registrada.")); return root; }
    root.append(dataTable([
      { key: "id", label: "Execução", render: (run) => run.evidence ? h("a", { href: `#/analytics?run=${encodeURIComponent(run.id)}`, text: run.id }) : run.id },
      { key: "sample", label: "Amostra" }, { key: "status", label: "Estado técnico", render: (run) => badge(jobLabel(run.status), run.status) },
      { key: "label", label: "Rótulo" },
      { key: "params", label: "Configuração da execução", render: (run) => {
        const p = run.params || {};
        const c = run.effectiveConfig || {};
        if (Object.keys(c).length) return `Banco: ${c.db}; montagem: ${c.assembler === "consensus" ? "MULTI" : c.assembler}; hospedeiro: ${c.host_filter_enabled === "true" ? c.host_name || "filtro ativado" : "sem filtro"}; adaptadores R1/R2: ${c.qc_adapter_r1 || "busca automática"} / ${c.qc_adapter_r2 || "busca automática"}`;
        return Object.keys(p).length ? `Banco: ${p.db || "não registrado"}; montagem: ${p.assembler === "consensus" ? "MULTI" : p.assembler || "não registrada"}; hospedeiro: ${p.host_filter_mode || "não registrado"}; adaptadores R1/R2: ${p.qc_adapter_r1 || "não informado"} / ${p.qc_adapter_r2 || "não informado"}` : "Não registrada nesta execução antiga";
      } },
      { key: "started", label: "Início", render: (run) => formatDate(run.started) }, { key: "finished", label: "Fim", render: (run) => formatDate(run.finished) },
      { key: "evidence", label: "Camada", render: (run) => run.evidence ? badge(run.valid ? "Evidence V2 — relatórios" : "Evidence V2 — indisponível", run.valid ? "done" : "not_evaluable") : "Pipeline" },
      { key: "actions", label: "Ações", render: (run) => {
        const actions = h("div", { class: "gi-btnrow" });
        if (["failed", "cancelled"].includes(run.status) && run.sample) actions.append(button("Revisar e reexecutar", () => reviewRerun(store, run), "secondary"));
        if (run.evidence) actions.append(linkButton(run.valid ? "Abrir relatórios" : "Ver detalhes da falha ou pendência", `#/results?run=${encodeURIComponent(run.id)}`, "secondary"));
        else if (run.runDir) actions.append(linkButton("Abrir resultado", `#/results?run=${encodeURIComponent(run.id)}`, "secondary"), artifactActions(run));
        if (run.runDir && run.action && !run.evidence && !run.comparison) actions.append(button("Reexecutar", () => rerunOfficial(store, run), "secondary"));
        return actions;
      } },
    ], runs, "Histórico de execuções"));
  } catch (error) { root.append(statusPanel("error", "Histórico indisponível", error.payload?.error || error.message)); }
  return root;
}
