# Instalação do zero: sequência executada

## FATO — ensaio de 02/11/2026

Instalação a partir do pacote do commit `6f7639f6f1c11f0505a5a91ae0ba8be8093de5f0`, em bundle novo: `/tmp/genein-pr10-package-clean-vjmjuo_q/bundle`. O diretório do bundle e o prefixo não existiam antes. O instalador do pacote baixou o micromamba e provisionou as ferramentas externas e dependências Python fixadas; não reutilizou ferramentas ou bibliotecas do ambiente Gene-In anterior. O SO e seus utilitários básicos já existiam: este ensaio não representa a instalação de um SO novo.

- SO: Ubuntu 24.04.3 LTS, WSL2, Linux x86_64.
- Plataforma registrada: `Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.39`.
- User site Python desabilitado; identidade do prefixo verificada; módulo Gene-In Builder ausente.
- Lock Conda: `environment.linux-64.explicit.txt`, SHA-256 `9b9f528479b493c8f1cc024e455ddd710ae87ccb59f1cf1731370781bff5d60d`.
- Lock Python: `requirements.lock.txt`, SHA-256 `99b784404e6bb614589ab62c02802b492a0760c2024bb83fadd2b0b8fef23d3e`.
- Instalação, `pip check`, painel HTTP e **quatro execuções de `make e2e` passaram**. Não houve validação científica.

| Ferramenta | Versão instalada no prefixo novo |
|---|---|
| Python | `3.11.15` |
| BLAST+ | `2.17.0` |
| Bowtie2 | `2.5.5` |
| samtools | `1.24` |
| fastp | `1.3.6` |
| Velvet | `1.2.10` |

As saídas brutas de versão, caminhos e hashes dos executáveis estão no [manifesto E2E](desenvolvimento/e2e-manifest-20261102.json). Os builds Conda e pacotes Python estão no [recibo de instalação](desenvolvimento/instalacao-independente-e2e.json).

### Pacote efetivamente instalado

- `Gene-In-2.0.2-PR10-e2e-isolado.zip`: `6e8f3918e629872d0ffb598e855e4f9e59804d756420b9a804fa46a7afa9187f`
- `Gene-In-2.0.2-PR10-e2e-isolado.tar.gz`: `0d4cb876c20f40cdc282f0b3fd239fb1cff49256e15d7f2f30d6725dbdee2bf2`

ZIP e TAR tiveram todos os membros conferidos por hash; o ZIP também teve CRC conferido. O manifesto de fonte foi verificado antes da instalação e novamente depois do E2E: **516 arquivos passaram nas duas verificações**. Os relatórios deste ensaio entraram em commit posterior; os hashes acima identificam o pacote ensaiado, não um arquivo contendo seu próprio hash. Nenhuma tag ou Release foi criada.

### Pré-requisitos do SO usados neste ensaio

Já presentes no host: `bash`, `make`, `python3`, `curl`, `tar`, `bzip2`, `install`, `find`, `chmod`, `unzip`, `sha256sum`, compilador e Git. A lista e os caminhos estão no recibo. O teste começou sem bundle ou prefixo de ferramentas no diretório escolhido. O instalador verificou os arquivos de lock existentes no pacote; nenhum parâmetro científico foi editado.

### Comandos efetivamente executados, na ordem

Ambiente do instalador: `PATH=/usr/bin:/bin`, `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1` e `GENEIN_BUNDLE_DIR=/tmp/genein-pr10-package-clean-vjmjuo_q/bundle`. Os diretórios abaixo identificam o ensaio encerrado; para repetir, use diretórios novos e preserve as evidências anteriores.

```bash
# cwd: /mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/pacote-6f7639f
sha256sum -c SHA256SUMS

# cwd: /mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO
unzip -q '/mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/pacote-6f7639f/Gene-In-2.0.2-PR10-e2e-isolado.zip' -d '/mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0'

# cwd: /mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0/Gene-In-2.0.2-PR10-e2e-isolado
sha256sum -c SOURCE_MANIFEST.sha256

# cwd: /mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0/Gene-In-2.0.2-PR10-e2e-isolado
bash bundle/install_wsl.sh

# cwd: /mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0/Gene-In-2.0.2-PR10-e2e-isolado
/tmp/genein-pr10-package-clean-vjmjuo_q/bundle/env/bin/python -m pip check

# cwd: /mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0/Gene-In-2.0.2-PR10-e2e-isolado
/tmp/genein-pr10-package-clean-vjmjuo_q/bundle/env/bin/genein --version
```

Depois da instalação, o PATH passou a ser `/tmp/genein-pr10-package-clean-vjmjuo_q/bundle/env/bin:/usr/bin:/bin`. Todos os comandos acima retornaram 0. O instalador usou micromamba 2.9.0 e conferiu o SHA-256 do arquivo de bootstrap antes de extrair, conforme o script distribuído.

### Abertura real do painel

No diretório `/mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0/Gene-In-2.0.2-PR10-e2e-isolado`, o processo dedicado foi iniciado com:

```bash
/tmp/genein-pr10-package-clean-vjmjuo_q/bundle/env/bin/python scripts/ux_dashboard.py --host 127.0.0.1 --port 39965 --ready-file '/mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0/dashboard.url'
```

Ambiente adicional: `GENEIN_WORK_ROOT=/mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/package installation with spaces dc1fr0f0/panel work with spaces` e `GENEIN_CONFIG_FILE` apontando para `not-present.env` nesse diretório. A prontidão foi lida de `dashboard.url`. As requisições HTTP foram feitas com `urllib.request.urlopen` no mesmo ensaio:

| Rota | HTTP | Bytes |
|---|---|---|
| `/` | 200 | 2822 |
| `/api/evidence/options` | 200 | 443 |
| `/js/state.js` | 200 | 4540 |

O processo do painel usado no teste foi encerrado após essas leituras. A instância habitual do usuário não foi alterada. O E2E abaixo usa a entrada individual canônica da CLI; esta etapa do painel verifica instalação e rotas, não um disparo de análise pelo navegador.

### E2E após a instalação

Com o Python e as ferramentas do prefixo novo, no diretório do pacote extraído:

```bash
GENEIN_TEST_ARTIFACT_ROOT='/mnt/c/Users/Admin/Desktop/Nova pasta/FECHAMENTO_E2E_PR10_20261102/ISOLADO/E2E_INSTALACAO_LIMPA' make e2e
sha256sum -c SOURCE_MANIFEST.sha256
```

Resultado: código 0; quatro combinações PASSED. Cada uma percorreu FASTQ → QC → montagem → BLAST → Evidence → recibo final, com busca competitiva e/ou Bowtie2 executados quando ligados. O executor fixa `GENEIN_ENV_DIR` no ambiente ativo, impedindo a consulta automática de um bundle anterior. Os caminhos e hashes dos executáveis no manifesto e na proveniência de cada caso precisam ser iguais. Os dados são strings aleatórias sem origem em organismos. Os detalhes e as saídas estão no [relatório E2E](desenvolvimento/RELATORIO_E2E_20261102.md).

### Entrada de testes e Python gerenciado

`make test` exige a fonte instalada ou prepara a instalação somente dentro de um venv. Em Python de sistema sem a fonte instalada, a mensagem orienta criar um venv e retorna 2, sem chamar o pip de sistema. Os três testes reais antes excluídos foram reintegrados; as ausências de ferramentas aparecem com motivo em `pytest -rs`. O módulo de otimização `test_validation_tracks.py` permanece fora da suíte de engenharia, sem execução da validação científica.

O [registro inicial de venv](desenvolvimento/instalacao-independente.json) é histórico e era parcial. O recibo atual, com ferramentas externas provisionadas e E2E, é [instalacao-independente-e2e.json](desenvolvimento/instalacao-independente-e2e.json).

## OPINIÃO

O ensaio fecha o aceite de instalação e do percurso mecânico no ambiente registrado. Compatibilidade com outros SOs e o resultado científico precisam de evidências próprias; não decorrem deste teste.
