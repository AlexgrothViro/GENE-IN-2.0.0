# Estado da validação científica

A entrega atual é uma ferramenta funcional de recuperação e apresentação de candidatos para triagem humana. Hospedeiro e banco são escolhas da análise. O caso-modelo de validação usa suíno e picornavírus; esse par não define o alcance do programa. O funcionamento com sequências de 20–100 pb foi verificado em cenários sintéticos controlados, incluindo adaptadores explicitamente informados e controle de hospedeiro.

Esses cenários usam referências exatas, uma semente, ausência de erros de sequenciamento e filtro de hospedeiro desligado. Não estimam sensibilidade ou precisão em material biológico degradado. Alinhamentos e bases alinhadas não demonstram origem viral. Candidatos espúrios continuam possíveis e devem permanecer identificáveis para revisão.

A campanha histórica de 27 bibliotecas sintéticas e 108 braços comparativos foi concluída. Ela pertence a uma configuração anterior, apresentou discordâncias de atribuição taxonômica e conserva G0.8 reprovado e validação integral não aprovada. Não foi reexecutada nem reclassificada com esta entrega. Seus resultados não comprovam o desempenho da nova recuperação de reads/candidatos de 20–100 pb.

As correções de 05/10 separaram disponibilidade e qualificação, corrigiram a redundância de posições alinhadas e explicitaram atribuição taxonômica e competição por referência/query/perfil. Qualificação científica permanece `NOT_EVALUATED`; preferência taxonômica é restrita aos hits rotulados reportados no painel.

Permanecem pendentes uma avaliação científica da recuperação por comprimento, carga, divergência, erros e fundo; a quantificação dos falsos candidatos e da carga de triagem; a comparação pareada dos componentes; e reprodução independente em ambiente novo. O desenho e os critérios devem ser definidos antes da avaliação final.

A [integração 2.0.2](integracao-memoria-22out.md) altera como determinadas etapas guardam e percorrem os dados. Equivalência de saídas, testes de falha, medições sintéticas de recursos e execução do pacote são verificações de engenharia. Não são uma repetição do piloto, não acrescentam métricas de sensibilidade/especificidade e não reclassificam G0.8 ou SAT4–6. O Gene-In Builder é um trabalho separado e seus resultados não são transferidos para esta distribuição.

Publicar esta fonte no GitHub registra a entrega de software. Esse ato não representa aprovação dos portões históricos, confirmação biológica ou aceitação acadêmica da dissertação.
