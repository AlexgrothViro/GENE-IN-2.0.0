# Instalação independente: registro de ensaio

## FATO

A aplicação foi instalada a partir do pacote identificado abaixo em um venv
novo, sem herança de site-packages e com user site desabilitado. Antes da
instalação, somente `pip 24.0` estava presente. O carregamento de `genein` e
`jsonschema` estava indisponível nesse ambiente inicial.

- Sistema: Ubuntu 24.04.3 LTS, WSL2, x86_64.
- Kernel/plataforma registrada: `Linux-6.6.87.2-microsoft-standard-WSL2-x86_64-with-glibc2.39`.
- Python: `3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]`.
- Origem: pacote ZIP extraído em diretório com espaços; instalação editável
  pelo pip do venv, com dependências obtidas do registro oficial PyPI.
- Commit do código ensaiado: `a0d70f67d881c13cdf6bf03de7586f7f351bd9a0` (quarto commit da revisão).
- Abertura do painel e leitura de `/`, `/api/evidence/options` e `/js/state.js`:
  HTTP 200 nas três rotas. Nenhuma análise foi iniciada.
- Identidade da CLI igual ao commit do pacote; módulo Gene-In Builder ausente.

### Versões das ferramentas externas

| Ferramenta | Saída de versão |
|---|---|
| blastn | `blastn: 2.12.0+` |
| bowtie2 | `/usr/bin/bowtie2-align-s version 2.5.2` |
| samtools | `samtools 1.19.2` |
| fastp | `fastp 0.23.4` |

Essas ferramentas já estavam disponíveis no host e foram apenas consultadas.
O venv não herdou bibliotecas Python do host. Este ensaio não representa a
provisão de um sistema operacional novo com todas as ferramentas externas.

### Dependências Python após a instalação

| Pacote | Versão |
|---|---|
| attrs | 26.1.0 |
| genein | 2.0.2 |
| jsonschema | 4.26.0 |
| jsonschema-specifications | 2025.9.1 |
| pip | 24.0 |
| referencing | 0.37.0 |
| rpds-py | 2026.9.1 |
| typing_extensions | 4.16.0 |

### Hashes dos pacotes de ensaio

- `Gene-In-2.0.2-fechamento-ensaio.zip`: `034ee5d734c2dd0bf863867763b38146bf45c740725446192c3a1dfa6f16b257`
- `Gene-In-2.0.2-fechamento-ensaio.tar.gz`: `3d2268c156c54302c38563e176839be68a0421aa05d9337467a3150e102d4f09`

Os hashes foram lidos do manifesto externo e reconferidos após a instalação.
Este documento registra o pacote do quarto commit. O quinto commit acrescenta
este registro, a proteção de ambiente para `make test` e sua entrada no CI;
os hashes acima não se referem a um pacote posterior contendo este próprio
documento. Nenhuma tag ou Release foi criada nesta revisão.

### Entrada de testes e Python gerenciado

`make test` passou no ambiente de engenharia: 619 testes em `scripts/tests`,
138 em `tests`, 322 subtestes e 31 JavaScript. Três testes operacionais foram
explicitamente excluídos do escopo de engenharia, além do módulo de otimização.
As fronteiras shell com executáveis controlados, sintaxe Bash e compilação
Python também passaram.

No Python de sistema com marcador `EXTERNALLY-MANAGED`, a tentativa sem a fonte
instalada retornou o código esperado 2 e a mensagem `make test precisa de um
venv`. Não houve chamada ao pip de sistema. A entrada só tenta instalar a fonte
quando estiver em venv; no CI a fonte já é instalada antes de `make test`.

### Pendências de aceite

O ensaio completo de (c) não foi executado. A parte de (e) que exige repetir
esse percurso após a instalação permanece pendente. Os testes reais de índices
registram somente metadados e hashes; não são o recibo final de uma análise.
O item (e) é, portanto, parcial. Não houve execução de validação científica.

Saídas e recibo resumido: [saídas](desenvolvimento/fechamento-saidas.txt) e
[registro de instalação](desenvolvimento/instalacao-independente.json).

## OPINIÃO

O venv sem bibliotecas herdadas reduz a dúvida sobre dependências Python da
aplicação. Para o aceite integral solicitado, ainda falta o percurso completo
de (c) e, se desejada, a provisão independente das ferramentas externas.
