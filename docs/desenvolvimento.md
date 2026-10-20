# Desenvolvimento e testes

Use Linux/WSL e Python 3.11 ou superior. Para desenvolver somente a CLI e os contratos, um venv é suficiente:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install setuptools wheel
python -m pip install --no-build-isolation -e '.[dev]'
make test
```

`make test` executa a suíte de engenharia: unittest, pytest, regressões shell, sintaxe Bash, compilação Python e testes JavaScript quando Node está disponível. Instale Node 18 ou superior para verificar também a interface. A integração contínua executa a instalação antes dos testes e inclui Node.

Os testes da CLI deliberadamente removem `PYTHONPATH` e lançam o comando fora da fonte. Rodar pytest numa cópia sem instalar o pacote pode produzir `No module named genein`. O lançador da suíte confere se o pacote instalado corresponde à árvore atual e instala essa árvore em modo editável se necessário. Execute-o num ambiente destinado a esse checkout.

Para testar módulos diretamente após instalar:

```bash
python -m pytest -q tests scripts/tests --ignore=scripts/tests/test_validation_tracks.py
node --test dashboard/tests/js_modules.test.mjs
```

Para as verificações com ferramentas reais, use o ambiente científico [registrado](installation-reproducibility.md):

Execute a suíte operacional numa cópia obtida por `git clone`. Ela também verifica o módulo experimental de mapeamento direto, cuja proveniência exige um commit Git resolvível e registra alterações locais. Um ZIP sem `.git` continua adequado ao processamento canônico e à recuperação de fragmentos, mas não satisfaz esse requisito do experimento de mapeamento direto.

```bash
export GENEIN_TEST_ARTIFACT_ROOT=/resultados/verificacao_genein
bash bundle/run.sh test-operational
python scripts/tests/verify_fragment_recovery_real.py \
  --artifact-root "$GENEIN_TEST_ARTIFACT_ROOT/fragmentos"
```

O segundo comando Python deve ser executado com o ambiente científico no PATH, incluindo o Python e os montadores desse ambiente. O wrapper `bundle/run.sh` aplica esse ambiente apenas ao comando que lança. Alternativamente, execute o Python pelo micromamba no prefixo instalado.

Código de saída 77 significa ferramenta operacional ausente e teste não executado. Falha de um teste realmente executado permanece `FAIL`, inclusive na trilha `all-safe`; ferramenta ausente não conta como teste aprovado. Guarde logs, versões e artefatos. Verificação funcional sintética e passagem de testes não estimam desempenho biológico ou superioridade.

Na preparação desta distribuição, use somente `all-safe` ou suas trilhas de engenharia, sintética, competitiva e operacional. O arquivo excluído importa módulos de otimização científica e não faz parte dessa verificação. Não execute essas trilhas experimentais como etapa de instalação ou lançamento.

Para gerar uma distribuição da fonte, registre as mudanças em commit e execute `python3 scripts/ops/build_release.py --output-dir /caminho/pasta_nova`. O comando usa somente arquivos rastreados, recusa sobrescrita e verifica cada membro de ZIP/tar.gz. Bancos, dados, configurações locais e caches não entram no pacote. Confira o arquivo fechado e os recibos da execução extraída conforme a [nota da versão 2.0.0](lancamento-20out.md).

Mudanças devem identificar produtores e consumidores dos contratos, preservar saídas anteriores e usar verificações que cubram os modos de falha envolvidos. Evite alterar parâmetros científicos para fazer os testes ou um benchmark produzir resultado favorável.
