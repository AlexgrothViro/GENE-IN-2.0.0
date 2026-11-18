# Caminhos e índices: contrato de armazenamento

O gerenciador cria componentes BLAST em diretório temporário sem espaços e
com basename físico `database`. BLAST+ v5 registra esse nome internamente;
renomear os componentes invalida a referência ao arquivo LMDB.

O prefixo lógico informado pela pessoa permanece inalterado. A promoção
recebe `--build-name database`, registra o campo opcional `index_basename`
no manifesto e guarda a geração em `.<SHA-256 do nome lógico>.generations/`.
O alias aponta ao basename físico dessa geração. Nome interno, diretório da
geração e nome temporário do alias não contêm espaços.

`promote_blast_database.py` produz esse registro;
`verify_blast_database_manifest.py` verifica alias, nomes, tamanhos e hashes.
Manifestos anteriores sem `index_basename` continuam usando o nome lógico
e o diretório histórico `.<nome lógico>.generations/`. Chamadas anteriores
ao promotor sem `--build-name` preservam esse formato. Uma versão antiga
do verificador não reconhece o novo armazenamento: mantenha gerenciador e
verificador da mesma entrega juntos. O contrato científico Evidence não muda.

O recibo de cache pode registrar os dois indexadores. Uma verificação BLAST
compara a referência e a identidade de makeblastdb; a verificação conjunta
exige também a identidade de bowtie2-build. Não descarta mudança na referência
ou na ferramenta necessária.

Regressões: `scripts/tests/test_db_manager_paths.py` usa oito letras arbitrárias
para criar, inspecionar e verificar índices, testar cache, detectar adulteração
e preservar a geração anterior quando um construtor controlado falha. Não
executa buscas, montagem ou alinhamento. Os testes reais exigem BLAST+ e
Bowtie2 disponíveis; ausência das ferramentas é registrada como skip.
