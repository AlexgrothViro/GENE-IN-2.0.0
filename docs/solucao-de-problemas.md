# Solução de problemas

| Sintoma | Conferência e ação |
|---|---|
| `No module named genein` | Ative o ambiente correto e instale a fonte com `python -m pip install --no-build-isolation --no-deps -e .`. A instalação exige setuptools e as dependências Python disponíveis. |
| Comando usa outra cópia do projeto | Confira `python -c 'import genein; print(genein.__file__)'`. Reinstale o checkout atual nesse ambiente. O wrapper do bundle seleciona sua própria fonte. |
| Ambiente existente diverge do lock | Use `GENEIN_BUNDLE_DIR` com um diretório novo e repita a instalação. Consulte o diagnóstico antes de reutilizar um prefixo. |
| Erro de rede ao instalar | Confira acesso aos canais Conda e ao PyPI. Para pip offline, forneça `GENEIN_WHEELHOUSE` com os wheels correspondentes ao lock. |
| WSL ausente ou acesso negado | Confira a instalação do WSL/Ubuntu e as permissões Windows. Execute o instalador com uma conta autorizada para configurar os requisitos. |
| Banco BLAST rejeitado | Confira prefixo, arquivos do índice e manifesto `.db-manifest.json`. Use o gerenciador de bancos ou a preparação documentada. |
| Resultado já existe | Escolha um diretório de saída novo para a execução; os resultados são preservados. |
| Falta de espaço, erro de SQLite ou de escrita temporária no resgate | Confira espaço, cota e permissões no sistema de arquivos da saída e no diretório temporário efetivo, incluindo `TMPDIR` quando definido. Libere recursos ou escolha um caminho apropriado antes de repetir em uma saída nova. A deduplicação não recorre à tabela inteira em RAM quando SQLite falha. Preserve o log; falha técnica não é ausência de candidatos. |
| MULTI rejeita `--assembler` | Use `--analysis-profile assembly-consensus` sozinho. Para um montador individual, use `--analysis-profile default --assembler spades`. |
| Reads com adaptador não representam o comprimento da molécula | Informe os adaptadores reais da biblioteca em `QC_ADAPTER_R1` e `QC_ADAPTER_R2`, ou pelos ajustes da interface, e confira o FASTQ pós-QC. |
| Candidato alinhado ao hospedeiro ou atribuição ambígua | Confira competição, suporte e avisos. Revise as sequências com evidência independente adequada ao objetivo. |
| Porta da interface ocupada | O lançador pode escolher uma porta livre e registrar a URL. Veja [portas do dashboard](dashboard-portas.md). |

Ao relatar um problema, inclua versão/identificadores da entrega, comando ou opções selecionadas, versões das ferramentas, estado e erro da execução. Compartilhe dados de entrada somente quando estiverem autorizados; uma fixture sintética reproduzível costuma permitir depuração sem compartilhar a amostra.
