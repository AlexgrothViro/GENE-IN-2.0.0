# Portas do dashboard

O atalho Windows cria um recibo exclusivo de abertura em `tmp/launcher-*.url`. O servidor escreve nele a URL da porta efetivamente selecionada; o atalho aguarda esse recibo e abre essa URL. Assim, uma porta padrão ocupada não faz o navegador abrir outro aplicativo. Recibos existentes são rejeitados, sem sobrescrita. A opção `--ready-file` também permite verificar essa ligação diretamente.

Execute `make ux` ou `make ux PORT=8765`. A porta solicitada é a primeira opção; se estiver ocupada ou se o sistema negar permissão de uso, o inicializador tenta as próximas 19 portas, sem ultrapassar 65535. Abra o endereço impresso em `Painel ativo em:`: ele contém a porta efetivamente usada.

No WSL, o inicializador consulta também os listeners TCP do Windows via PowerShell, pois uma porta disponível no Linux pode apontar para outro aplicativo no navegador do Windows. Se essa consulta não estiver disponível, um aviso informa que somente o WSL será verificado. A consulta é uma fotografia do momento da inicialização; não diagnostica bloqueios de firewall ou mudanças posteriores na rede.

Para exigir uma porta específica sem alternativas:

```bash
python3 scripts/ux_dashboard.py --host 127.0.0.1 --port 8000 --strict-port
```

A lógica fica em `scripts/dashboard/server.py`: `_windows_listener_ports` consulta o Windows e `_bind_server` faz as tentativas limitadas de abertura. Erros alheios à disponibilidade/permissão da porta continuam sendo propagados. Os testes ficam em `scripts/tests/test_dashboard_server.py`.

O servidor permanece restrito a loopback. Nenhum processo que ocupa outra porta é encerrado.
