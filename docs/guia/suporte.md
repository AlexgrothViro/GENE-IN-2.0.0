# Suporte

[Início](../../README.md) / [Documentação](../README.md) / Suporte

## Problemas comuns

| Sintoma | Próximo passo |
|---|---|
| Instalação parou antes de criar o ambiente | Leia os pré-requisitos ausentes e a mensagem do gerenciador de pacotes; corrija o ambiente Linux e repita |
| O painel não abre | Use o endereço impresso no terminal; a porta pode ter mudado |
| Arquivo Windows não é encontrado no WSL | Confira o caminho Linux correspondente e as aspas em nomes com espaços |
| FASTQ corrompido ou inválido | Preserve o original e obtenha novamente uma cópia íntegra; a mensagem orienta a reimportação |
| Banco falha no diagnóstico | Confira a mensagem real; uma falha de leitura não equivale a banco pronto |
| Builder ausente ou incompatível | Execute `bash bundle/install_builder.sh` e a conferência do [guia de montadores](montadores.md) |
| Acesso negado ao Builder | Confira a conta autenticada no Git e a permissão para o repositório privado |
| Saída já existe | Use uma nova pasta de execução |
| Processo foi interrompido | Aguarde o registro de cancelamento e consulte os logs antes de iniciar outro trabalho |

## Relatar um erro

Use as [issues do Gene-In](https://github.com/AlexgrothViro/GENE-IN-2.0.0/issues). Inclua:

- versão e commit do programa;
- sistema operacional e uso de WSL;
- ação realizada e mensagem completa do erro;
- montador escolhido e, quando aplicável, versão do Builder;
- resultado esperado e observado.

Revise caminhos pessoais e credenciais antes de compartilhar logs. Não publique dados de amostras para relatar um problema de instalação.

## Referência técnica

A [documentação anterior de diagnóstico](https://github.com/AlexgrothViro/GENE-IN-2.0.0/blob/a61897fbce9c2fdff2a644ece59abaf82aeb8f51/docs/solucao-de-problemas.md) permanece disponível. Para a integração opcional, siga o guia atual de [montadores](montadores.md).
