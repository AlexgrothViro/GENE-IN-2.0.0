# Instalação e reprodução

Guia da **2.0.1**, correção de distribuição sobre a fonte 2.0.0. O [guia inicial](../README.md) apresenta o programa; o [histórico](../CHANGELOG.md) identifica o fechamento anterior. A instalação prepara a fonte e as ferramentas; bancos, índices de hospedeiro e dados de pesquisa são preparados separadamente.

## Plataformas e pré-requisitos

O ambiente científico fixado atende **Linux x86_64** e **Windows x86_64 com WSL2/Ubuntu**. O ambiente de referência das verificações anteriores é Ubuntu 24.04/WSL2. macOS, ARM e Windows sem WSL não são atendidos por esse lock.

A instalação precisa de internet na primeira preparação, salvo quando os artefatos já estão no cache local. O sistema Linux precisa de Bash, `make`, `python3`, `curl`, `tar`, `bzip2`, certificados e utilitários de `coreutils`/`findutils`. O instalador verifica esses requisitos e, em Debian/Ubuntu, tenta instalar os ausentes com `apt-get`, usando sudo quando necessário. Sem esses privilégios, informa o que pedir ao administrador.

Use a árvore completa de fonte, extraída do ZIP ou obtida pelo Git. Não execute de dentro do ZIP. **Mantenha a fonte no mesmo local depois de instalar**: o pacote Python é editável e chama adaptadores shell da mesma árvore. Um wheel isolado não contém o fluxo bioinformático completo.

## Windows com WSL2

1. Extraia o pacote inteiro em uma pasta permanente.
2. Se ainda não houver WSL2/Ubuntu, prepare-o com o administrador do computador. O comando de instalação usado para Ubuntu 24.04 é `wsl --install -d Ubuntu-24.04`, em PowerShell com os privilégios necessários. Abra Ubuntu e conclua a criação do usuário antes de instalar o Gene-In.
3. Execute `INSTALAR_GENEIN.bat` e acompanhe as mensagens. A senha de sudo, se solicitada, é a do usuário Linux.
4. Execute `ABRIR_GENEIN.bat` e abra o endereço indicado pelo lançador.

Os caminhos Linux usados na CLI são diferentes dos caminhos Windows: `C:\dados` corresponde normalmente a `/mnt/c/dados`. Cite caminhos com espaços. O gerenciador do Gene-In trata a construção BLAST em caminhos com espaços; chamadas diretas a `makeblastdb` e o teste sintético devem usar um diretório Linux sem espaços.

`Atualizar Gene-In.bat` verifica/reinstala dependências da **cópia atual**. Ele não busca novas versões da fonte no GitHub. Para trocar de versão, preserve a cópia anterior e instale a nova fonte em seu local definitivo.

## Linux ou terminal Ubuntu/WSL

Na raiz da fonte:

```bash
bash bundle/install_wsl.sh
bash bundle/run.sh test-env
bash bundle/run.sh genein --version
bash bundle/run.sh genein run --help
bash run_linux.sh
```

Para uma instalação separada, defina um prefixo novo **antes de todas as chamadas** de instalação, abertura e análise:

```bash
export GENEIN_BUNDLE_DIR="$HOME/.gene-in-2.0.1"
bash bundle/install_wsl.sh
bash bundle/run.sh test-env
bash run_linux.sh
```

Sem essa variável, o prefixo padrão é `~/.gene-in-bundle`. O lançador Windows usa o padrão. Não apague nem substitua um ambiente que esteja atendendo outra análise. O wrapper da CLI seleciona a fonte da própria cópia; em um ambiente compartilhado a instalação editável continua vinculada à última fonte instalada para comandos chamados diretamente, por isso prefira `bash bundle/run.sh genein ...`.

`GENEIN_WHEELHOUSE` pode apontar para wheels já disponíveis. O cache Conda/micromamba é separado da fonte. A disponibilidade de cache não representa uma instalação totalmente offline verificada.

`GENEIN_WORK_ROOT` é um diretório absoluto existente para o FASTA padrão, o banco BLAST e o índice Bowtie2. Sem essa variável, esses padrões continuam dentro da fonte. Um caminho passado em `REF_FASTA`, `BLAST_DB` ou `BOWTIE2_INDEX` não muda de lugar. A CLI continua exigindo `--output-root` novo e fora da fonte. `GENEIN_OUTPUT_ROOT`, exportado antes do painel, faz o histórico listar os `execution.json` dessa pasta. A configuração persistente do painel fica em `$GENEIN_WORK_ROOT/config/picornavirus.env` quando esse diretório existe, ou em `~/.gene-in/config/picornavirus.env`. Ela não é gravada dentro da fonte.

Na 2.0.0, Make, os scripts e o painel liam só o `config/picornavirus.env` da fonte (ou `config.env`) e o banco em `blastdb/<DB>` dentro da fonte. Na 2.0.1 os três usam a mesma procura:

1. `GENEIN_CONFIG_FILE`, mesmo que o arquivo ainda não exista;
2. `$GENEIN_WORK_ROOT/config/picornavirus.env`, quando o arquivo existe;
3. `~/.gene-in/config/picornavirus.env`, quando o arquivo existe;
4. `config/picornavirus.env` da fonte e, por último, `config.env`.

`BLAST_DB` no arquivo prevalece quando o nome do banco não veio de fora. O painel e um `DB` na linha de comando ignoram esse caminho e usam o prefixo do banco selecionado: o exemplo traz `BLAST_DB="blastdb/custom"`, e uma análise com `db=ptv` não pode cair nesse banco. Sem um caminho explícito, vale o primeiro banco já preparado (manifesto não vazio) em `$GENEIN_WORK_ROOT/blastdb/<DB>`, depois `~/.gene-in/blastdb/<DB>`, depois `blastdb/<DB>` na fonte. Se nenhum estiver preparado, o padrão é `$GENEIN_WORK_ROOT/blastdb/<DB>` quando o diretório de trabalho foi pedido, e `blastdb/<DB>` na fonte caso contrário. Um `picornavirus.env` do diretório de trabalho gravável pelo grupo ou por outros é recusado. Um perfil nomeado (`DB=ptv` e os demais) ignora `DB_QUERY`; só `DB=custom` usa a consulta e a grava no manifesto.

## Painel e hospedagem local

O comando `bash run_linux.sh` abre o servidor em loopback (`127.0.0.1`), com porta inicial 8000. Se estiver ocupada, tenta as próximas portas dentro do limite documentado. Use sempre o endereço impresso no terminal; veja [portas do painel](dashboard-portas.md).

Para solicitar outra porta:

```bash
bash run_linux.sh ux PORT=8765
```

O servidor usa arquivos e ferramentas do computador local. Não há implantação de serviço público ou configuração de acesso remoto neste procedimento. Mantenha o terminal aberto. Fechar a aba do navegador não encerra o servidor; use Ctrl+C no terminal depois de concluir os trabalhos.

## Ambiente fixado e reprodução

| Arquivo | Conteúdo |
|---|---|
| `environment.yml` | Dependências diretas fixadas |
| `environment.lock.yml` | Versões e builds Conda completos |
| `environment.linux-64.explicit.txt` | URLs e checksums dos pacotes Conda da plataforma |
| `requirements.lock.txt` | Versões e hashes das dependências Python adicionais |

O instalador obtém o micromamba **2.9.0** (linux-64). O tar.bz2 conferido, o mesmo arquivo que contém `bin/micromamba`, tem sha256 `8761c382127e6363bd9e0a2451aa3ef90d071a79133f736e2f759a3bf13040dd`. Um cache em `bundle/cache/` só é aceito com esse hash. Esse pin é do instalador; os pacotes do ambiente continuam em `environment.lock.yml`, `environment.linux-64.explicit.txt` e `requirements.lock.txt`.

O instalador usa o lock explícito, instala wheels com os hashes registrados e instala o Gene-In com `--no-build-isolation --no-deps`. Um ambiente existente é comparado aos registros Conda exigidos; divergências interrompem a preparação. A comparação lê `conda-meta`, não revalida byte a byte todos os binários, e admite pacotes adicionais. Para reproduzir o conjunto completo, use um prefixo novo.

Preserve a versão da fonte, o commit, os locks, os hashes das entradas e dos bancos, os manifestos e a configuração resolvida de cada análise. A [citação](citacao.md) lista o conjunto mínimo a relatar.

## Recursos e limites

Não há um requisito universal de RAM, tempo ou disco validado para toda biblioteca. Comece com uma amostra pequena e controles conhecidos. Escolha threads e memória conforme o montador e a capacidade disponível; os parâmetros não são ajustados automaticamente para garantir o término.

Uma amostra de 300.000 pares produziu cerca de 30 milhões de HSPs. O diagnóstico usa **45 GB livres no mesmo sistema de arquivos** como aviso para dados desse porte. As etapas pesadas também conferem suas estimativas de espaço antes de iniciar e durante a escrita. Esse valor vem de medições de engenharia guardadas em `docs/desenvolvimento/` no repositório Git; não é garantia de capacidade para qualquer amostra.

O metaSPAdes preserva o parâmetro `-m 64`; quando ele excede a memória disponível, o programa avisa. A redução automática não foi implementada. O BLAST convencional continua sem divisão em blocos; o bloco de 256 queries pertence à busca curta. O Velvet pode produzir montagens diferentes com as mesmas entradas e configuração. Os limites preservados estão em `docs/desenvolvimento/` no repositório Git.

Falhas de memória, espaço ou ferramentas precisam ser resolvidas antes de repetir a análise em uma pasta nova. SIGTERM permite tratamento e limpeza; SIGKILL e desligamento abrupto não podem ser tratados pelo próprio processo.

## Primeira análise e verificação opcional

Prepare um banco e use os exemplos de [uso e bancos](uso-e-bancos.md). `genein run` exige um diretório de saída novo, fora da fonte, e um banco BLAST com manifesto `.db-manifest.json` válido. `execution.json` registra lançamento e término, sem representar resultado científico.

Para repetir a verificação sintética de fragmentos com ferramentas reais, use a fonte instalada e uma pasta Linux sem espaços:

```bash
export GENEIN_BUNDLE_DIR="${GENEIN_BUNDLE_DIR:-$HOME/.gene-in-bundle}"
"$GENEIN_BUNDLE_DIR/bin/micromamba" run -p "$GENEIN_BUNDLE_DIR/env" \
  python scripts/tests/verify_fragment_recovery_real.py \
  --artifact-root "$HOME/genein-verificacao-2.0.0"
```

O teste cria seus próprios dados e conserva evidências, incluindo falhas. O sucesso esperado é `PASS functional fragment recovery`. Ele usa sequências sintéticas com origem conhecida; não estima sensibilidade, precisão ou utilidade em amostras reais. Veja [validação científica](validacao.md) e [desenvolvimento](guia-de-desenvolvimento.md) para outras verificações.

## Instalação global opcional

`install_linux.sh` prepara a árvore em `/opt/genein` e usa `/opt/genein/bundle`. Exige privilégios apropriados e `rsync`. O instalador preserva pastas de dados existentes e interrompe se precisar substituir um caminho com dados ou outro destino. A modalidade não é necessária para uso no WSL e não equivale à instalação de usuário verificada nos registros anteriores.

## Registros de instalação

Os testes de instalação anteriores estão nos registros de 06/10, b1 e b3, em `docs/desenvolvimento/` no repositório Git. Eles pertencem às versões e ambientes ali identificados. O [histórico de mudanças](../CHANGELOG.md) informa a verificação desta consolidação. Instalação editável num ambiente já disponível não demonstra preparação do WSL do zero, máquina nova sem cache ou reprodução independente.
