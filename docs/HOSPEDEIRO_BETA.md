# Índice do hospedeiro

O pacote não inclui genomas nem índices do hospedeiro. Obtenha o FASTA de uma fonte documentada, adequada ao organismo da amostra, e registre a versão e a origem. No ambiente instalado, prepare um índice com:

```bash
bowtie2-build /caminho/genoma.fasta /caminho/indice_hospedeiro
bowtie2-inspect -s /caminho/indice_hospedeiro
```

No assistente, escolha hospedeiro personalizado, informe o nome e `/caminho/indice_hospedeiro`, sem o sufixo `.1.bt2`, e valide o índice. Para Sus scrofa, o prefixo salvo na configuração técnica para esse hospedeiro também pode ser usado. O filtro remove leituras alinhadas ao hospedeiro antes da montagem; com o filtro desligado essas leituras podem permanecer. Nenhum banco ou índice é baixado automaticamente por esse formulário.

## Filtro desligado e comprimento dos contigs

O assistente e o log avisam quando o filtro está desligado: leituras do hospedeiro e de outros organismos podem permanecer. Um contig longo, inclusive maior que as referências do banco escolhido, não estabelece origem viral. Confira o QC, os comprimentos, a referência alinhada e o suporte antes de interpretar candidatos. O aviso não remove contigs nem aplica um novo limite de comprimento; qualquer regra quantitativa adicional depende da decisão científica do autor.
