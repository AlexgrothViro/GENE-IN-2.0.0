# Citação e licença

[Início](../../README.md) / [Documentação](../README.md) / Citação

## Citar o software

Use os metadados de [CITATION.cff](../../CITATION.cff) e registre a versão e o commit da cópia efetivamente executada. O desenvolvedor identificado na licença é **Alexsander Groth**.

```bash
bash bundle/run.sh genein --version
git rev-parse HEAD
```

Em pacotes sem Git, consulte `SOURCE_COMMIT`, quando incluído pelo empacotador. A branch de distribuição com Builder não deve ser confundida com uma release anterior apenas por compartilhar o número de versão da base.

## Registrar o trabalho

Preserve as versões do programa e dos componentes, ambiente, entradas, bancos, configuração, montador escolhido e recibos da execução. Se usar Builder, inclua também sua versão e o commit reportado no manifesto.

O número do contrato Evidence é separado da versão do programa. Uma atualização de software não altera retrospectivamente resultados científicos. Cite também as ferramentas e os dados de terceiros utilizados.

## Licença

O Gene-In mantém a [Gene-In Limited Public Use License](../../LICENSE). O texto autoriza determinados usos acadêmicos, educacionais e não comerciais e estabelece restrições para outros usos. Consulte a licença integral; esta edição não modifica suas condições.

O Builder mantém sua licença MIT própria. Ele é obtido separadamente; seu código não foi incorporado à fonte do Gene-In. Os demais componentes conservam os termos descritos em [avisos de terceiros](../../THIRD_PARTY_NOTICES.md).
