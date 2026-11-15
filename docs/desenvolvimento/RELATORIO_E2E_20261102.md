# Relatório do E2E real — 02/11/2026

## FATO

Código ensaiado: `6f7639f6f1c11f0505a5a91ae0ba8be8093de5f0`, na branch `codex/fechamento-engenharia-20261102`, PR #10, sem merge. Builder fora. `config/`, `src/`, VERSION, algoritmos, limiares e perfis científicos preservados. Este relatório descreve engenharia com entradas sem origem biológica; a validação científica não foi executada.

### Comando único

```bash
GENEIN_TEST_ARTIFACT_ROOT=/caminho/para/evidencias make e2e
```

Sem as ferramentas exigidas, o executor grava `status=SKIPPED`, imprime o motivo e retorna 77. O Make transforma a saída não zero do comando em código 2; nunca imprime PASSED nesse caso. Ferramenta presente que falha gera FAILED, não skip. A suíte tem testes para a ausência de ferramentas, para recusar saída sem recibo e para verificar a repetibilidade da entrada artificial.

### Dados e execução

- Gerador pseudoaleatório com semente `20261102`; duas strings independentes de 640 caracteres A/C/G/T, sem genomas ou acessos de organismos.
- Mesmos arquivos FASTQ nas quatro combinações: 632 pares, 79 por comprimento de 20, 25, 30, 40, 50, 65, 80 e 100 caracteres. Hashes reconferidos no final.
- Diretório de trabalho `work with spaces ...`; subdiretório `banks with spaces`; prefixos lógicos `primary bank`, `competition bank` e `mapping index`.
- Fluxo individual real, com QC e Velvet, perfil de análise `default`, uma thread. Nenhum limiar foi sobrescrito para fazer o exemplo passar.
- Banco BLAST v5 criado com nome físico estável `database`, entrada via stdin e promoção pelo mesmo helper usado pelo produto; isso preserva os nomes internos do banco e permite os prefixos lógicos com espaços.
- Perfil A executado em todas as combinações; A+B quando competição ligada. Pedir B com competição desligada continua sendo erro explícito.

| Execução | Competição | Remapeamento | Perfis | Código / resultado | Recibo |
|---|---|---|---|---|---|
| software-c0-r0 | desligada | desligado | A | 0 / PASSED | done_with_warning; 17 arquivos |
| software-c0-r1 | desligada | ligado | A | 0 / PASSED | done_with_warning; 21 arquivos |
| software-c1-r0 | ligada | desligado | A+B | 0 / PASSED | done_with_warning; 19 arquivos |
| software-c1-r1 | ligada | ligado | A+B | 0 / PASSED | done_with_warning; 23 arquivos |

`done_with_warning` é um estado final válido: as execuções individuais não têm controles de lote e os casos com remapeamento desligado registram a indisponibilidade dessa dimensão. O teste exige o recibo transacional e os artefatos íntegros; não exige uma conclusão científica positiva.

### Versões da instalação independente

| Ferramenta | Versão |
|---|---|
| Python | `3.11.15` |
| BLAST+ | `2.17.0` |
| Bowtie2 | `2.5.5` |
| samtools | `1.24` |
| fastp | `1.3.6` |
| Velvet | `1.2.10` |

SO: Ubuntu 24.04.3 LTS / WSL2 x86_64. [Sequência exata de instalação](../instalacao-do-zero.md); [recibo completo](instalacao-independente-e2e.json).

### O que o aceite verifica

Cada execução deve devolver 0, produzir `SUCCESS.json` com o run_id atual, ter hash do manifesto e de `sample_evidence.json` iguais aos do recibo, ter todos os arquivos do manifesto íntegros e deixar de ocupar staging. O teste também verifica configuração resolvida, perfis efetivos e conclusão do BLAST. Quando ligado, exige busca composta com registros e remapeamento concluído, log Bowtie2, identidade da referência e BAM/índice com registros mapeados. Quando desligado, exige ausência de BAM. Um exit 0, um recibo antigo ou uma etapa que não fez trabalho não bastam.

Registrados e reconferidos: **20 componentes nos dois bancos**, **seis componentes do índice Bowtie2**, hashes das entradas e de **15 arquivos de configuração**. O manifesto guarda comandos, ambiente explícito, versões, caminhos e hashes dos executáveis, configuração e recibos de cada caso. Não foram calculadas métricas de desempenho biológico.

### Comandos registrados pelo E2E

O [manifesto integral](e2e-manifest-20261102.json) contém os argv sem perda de espaços. Inclui os dois `makeblastdb` com entrada por stdin, `bowtie2-build` e as quatro chamadas do pipeline individual. Os logs e artefatos de cada execução ficam no diretório indicado por `[ARTIFACTS]`. SHA-256 do manifesto local: `7787d979fcd3aa84dec66dced567d0f2078507a4f448cd4ccb12b4f87a6d69eb`.

Execução local após instalação limpa: `2026-11-02T23:54:36.521790+00:00` até `2026-11-02T23:57:58.613243+00:00`. Todos os comandos do recibo de instalação retornaram 0; o painel respondeu HTTP 200 em três rotas e a fonte passou na conferência de 516 hashes antes e depois. O preflight e os executáveis das etapas foram conferidos no prefixo novo; não houve consulta ao bundle antigo.

### Suíte local completa

`make test` retornou 0, sem deselections:

```text
625 passed, 322 subtests passed in 133.70s (0:02:13)
138 passed in 68.11s (0:01:08)
# tests 31
# pass 31
# fail 0
```

Os três testes reais restaurados rodaram com as ferramentas presentes. Fronteiras shell, sintaxe Bash e compilação Python também passaram. O módulo de otimização fica fora do escopo declarado.

### CI com ferramentas reais

O job `optional-e2e` instala ferramentas reais e executa `make e2e`, sem mocks. Também preserva arquivos ocultos do armazenamento dos bancos. Execução do código ensaiado: [Engineering tests 41548793609](https://github.com/AlexgrothViro/GENE-IN-2.0.0/actions/runs/41548793609); jobs de engenharia, índices e E2E passaram. O [registro do CI](e2e-ci-20261102.json) contém IDs, saídas e metadados dos artefatos.

- Engenharia: `610 passed, 15 skipped, 320 subtests passed`; grupo separado `138 passed`; `31` testes JavaScript, zero falhas. Nenhum `deselected`. Skips têm motivos explícitos; esse job não instala os executáveis opcionais.
- Índices reais: `16 passed, 4 subtests passed`.
- E2E real: quatro linhas PASS e encerramento com código 0. [Baixar artefato do E2E](https://github.com/AlexgrothViro/GENE-IN-2.0.0/actions/runs/41548793609/artifacts/13188759780) — SHA-256 `7c68eda12fa671dae3f4a147d865c92d74e6e9b59dd13b950baddd3acee95ab7`.

O job de E2E usa as versões disponíveis no Ubuntu do CI, registradas no manifesto próprio; o ensaio local acima usa o lock distribuído. Os dois ambientes não são apresentados como idênticos.

### Falhas encontradas e corrigidas durante a preparação

1. O preparo inicial do novo teste entregava ao BLAST um nome de arquivo com espaços; o programa externo o dividiu. O teste passou a fornecer stdin, preservando os parâmetros existentes.
2. O novo exemplo tinha rótulo `VECTOR`, fora do enum aceito. Foi corrigido para `SYNTHETIC_SEQUENCE`; a checagem de produção o recusou antes de processar.
3. O primeiro CI do novo job faltava `dos2unix`. A preparação agora instala esse pré-requisito e o executor o inclui na lista de ferramentas necessárias. [Execução anterior com falha](https://github.com/AlexgrothViro/GENE-IN-2.0.0/actions/runs/41547170808) e artefato preservados.
4. A primeira suíte local após escrever o pré-registro recusou uma palavra reservada às notas internas nas regras de documentação do repositório. A redação pública foi ajustada, sem afrouxar o teste. O registro dessa primeira execução permanece preservado.
5. A conferência dos caminhos mostrou que o preflight consultava o bundle anterior, embora as etapas de análise já usassem o prefixo novo. O executor agora fixa a identidade do ambiente também no preflight, compara executáveis/hashes da proveniência e o ensaio foi repetido em novo bundle.

Os testes e ensaios repetidos são grupos sobrepostos: não somar os contadores como novas amostras ou provas independentes.

## OPINIÃO

O percurso mecânico e a instalação no ambiente registrado estão sustentados por recibos, logs e hashes. A proposta de [validação científica](../validacao/PROJETO_VALIDACAO_DECOY_REMAP.md) ainda depende de decisões de Alexsander e Orientador, piloto, margem/N congelados e recursos reais do Argon. O artigo deve continuar descrevendo funcionalidades, sem alegação de desempenho até terminar o estudo.
