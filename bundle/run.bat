@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM =====================================================================
REM  Gene-In -- Launcher Windows
REM  Diagnostico de pre-requisitos e instalacao assistida
REM =====================================================================

set "BUNDLE_DIR=%~dp0"
if "%BUNDLE_DIR:~-1%"=="\" set "BUNDLE_DIR=%BUNDLE_DIR:~0,-1%"

REM --------------------------------------------------------------------
REM  ETAPA 1: WSL existe no sistema?
REM --------------------------------------------------------------------
where wsl.exe >nul 2>nul
if errorlevel 1 (
    echo.
    echo =====================================================================
    echo  [ERRO] WSL nao foi encontrado neste computador.
    echo =====================================================================
    echo.
    echo  O Gene-In precisa do WSL ^(Windows Subsystem for Linux^) com Ubuntu.
    echo  Ele nao foi detectado neste computador.
    echo.
    echo  Para instalar, siga estes passos:
    echo    1. Abra o menu Iniciar e busque: PowerShell
    echo    2. Clique com o botao direito e escolha: Executar como Administrador
    echo    3. Cole o comando abaixo e pressione Enter:
    echo.
    echo         wsl --install -d Ubuntu-24.04
    echo.
    echo    4. Aguarde o download e reinicie o computador se solicitado.
    echo    5. Depois de reiniciar, abra o Ubuntu pelo menu Iniciar e crie
    echo       seu usuario Linux quando pedido.
    echo    6. Depois disso, clique novamente em run.bat para abrir o Gene-In.
    echo.
    echo  Se o comando acima nao funcionar, verifique distribuicoes disponiveis:
    echo.
    echo         wsl --list --online
    echo.
    echo  E instale a versao Ubuntu-24.04 que aparecer na lista.
    echo.
    echo  Se voce nao tiver permissao de administrador neste computador,
    echo  peca a uma pessoa com acesso de administrador para:
    echo    - Habilitar WSL no Windows;
    echo    - Instalar o Ubuntu 24.04 LTS pelo Microsoft Store;
    echo    - Liberar permissao de sudo para seu usuario.
    echo.
    echo =====================================================================
    pause
    exit /b 1
)

REM --------------------------------------------------------------------
REM  ETAPA 2: Existe alguma distribuicao WSL instalada e respondendo?
REM --------------------------------------------------------------------
set "USE_DISTRO="
set "DISTRO_NAME="

REM Tenta a distribuicao padrao primeiro
wsl.exe bash -c "echo ok" >nul 2>nul
if %errorlevel% equ 0 (
    set "USE_DISTRO=padrao"
    set "DISTRO_NAME=distribuicao padrao"
    goto check_make
)

REM Tenta nomes comuns em ordem
for %%D in (Ubuntu-24.04 Ubuntu Ubuntu-22.04 Ubuntu-20.04 Debian) do (
    wsl.exe -d "%%D" bash -c "echo ok" >nul 2>nul
    if !errorlevel! equ 0 (
        set "USE_DISTRO=-d %%D"
        set "DISTRO_NAME=%%D"
        goto check_make
    )
)

REM Nenhuma distro respondeu -- WSL existe mas sem Ubuntu/Debian acessivel
echo.
echo =====================================================================
echo  [ERRO] WSL encontrado, mas nenhuma distribuicao Ubuntu foi localizada.
echo =====================================================================
echo.
echo  O WSL esta instalado, mas nao foi possivel encontrar ou acessar
echo  uma distribuicao Linux compativel (Ubuntu 24.04 LTS, Debian ou similar).
echo.
echo  Para instalar o Ubuntu 24.04 LTS no WSL, siga estes passos:
echo    1. Abra o menu Iniciar e busque: PowerShell
echo    2. Clique com o botao direito e escolha: Executar como Administrador
echo    3. Cole o comando abaixo e pressione Enter:
echo.
echo         wsl --install -d Ubuntu-24.04
echo.
echo    4. Aguarde o download, abra o Ubuntu pelo menu Iniciar e crie
echo       seu usuario Linux quando pedido.
echo    5. Depois disso, clique novamente em run.bat para abrir o Gene-In.
echo.
echo  Se o comando acima nao funcionar, verifique distribuicoes disponiveis:
echo.
echo         wsl --list --online
echo.
echo  Depois instale a versao Ubuntu 24.04 LTS que aparecer na lista.
echo.
echo  Se voce nao tiver permissao de administrador neste computador,
echo  peca a uma pessoa com acesso de administrador para:
echo    - Instalar o Ubuntu 24.04 LTS pelo Microsoft Store;
echo    - Liberar permissao de sudo para seu usuario.
echo.
echo =====================================================================
pause
exit /b 1

REM --------------------------------------------------------------------
REM  ETAPA 3: make esta instalado dentro da distro?
REM --------------------------------------------------------------------
:check_make
set "WSL_RUN=wsl.exe"
if not "%USE_DISTRO%"=="padrao" set "WSL_RUN=wsl.exe %USE_DISTRO%"

%WSL_RUN% bash -lc "command -v make" >nul 2>nul
if %errorlevel% equ 0 goto check_python3

REM make ausente -- oferecer instalacao assistida
echo.
echo =====================================================================
echo  [ATENCAO] Ubuntu encontrado, mas "make" nao esta instalado.
echo =====================================================================
echo.
echo  O Gene-In precisa do "make" e outras ferramentas basicas que nao
echo  foram encontradas no Ubuntu/WSL deste computador.
echo.
echo  Deseja tentar instalar as dependencias automaticamente agora?
echo.
echo    S = Sim, instalar agora  ^(recomendado^)
echo    N = Nao, vou instalar manualmente depois
echo.
set /p RESP_MAKE="  Sua escolha [S/N]: "
if /i "!RESP_MAKE!"=="S" goto instalar_deps
if /i "!RESP_MAKE!"=="s" goto instalar_deps

REM Usuario recusou -- mostrar comandos manuais
echo.
echo =====================================================================
echo  Para instalar manualmente, abra o Ubuntu pelo menu Iniciar e rode:
echo =====================================================================
echo.
echo    sudo apt update
echo    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv
echo.
echo  Depois de instalar, feche o Ubuntu e clique novamente em run.bat.
echo.
echo  Se voce nao tiver permissao de administrador neste computador,
echo  peca a uma pessoa com acesso de administrador para:
echo    - Liberar permissao de sudo para seu usuario;
echo    - Instalar os pacotes acima via conta de administrador.
echo.
echo =====================================================================
pause
exit /b 1

REM --------------------------------------------------------------------
REM  ETAPA 4: python3 esta instalado dentro da distro?
REM --------------------------------------------------------------------
:check_python3
%WSL_RUN% bash -lc "command -v python3" >nul 2>nul
if %errorlevel% equ 0 goto executar

REM python3 ausente -- oferecer instalacao assistida
echo.
echo =====================================================================
echo  [ATENCAO] Ubuntu encontrado, mas "python3" nao esta instalado.
echo =====================================================================
echo.
echo  O Gene-In precisa do Python 3 para rodar o painel visual,
echo  mas ele nao foi encontrado no Ubuntu/WSL deste computador.
echo.
echo  Deseja tentar instalar as dependencias automaticamente agora?
echo.
echo    S = Sim, instalar agora  ^(recomendado^)
echo    N = Nao, vou instalar manualmente depois
echo.
set /p RESP_PY="  Sua escolha [S/N]: "
if /i "!RESP_PY!"=="S" goto instalar_deps
if /i "!RESP_PY!"=="s" goto instalar_deps

REM Usuario recusou -- mostrar comandos manuais
echo.
echo =====================================================================
echo  Para instalar manualmente, abra o Ubuntu pelo menu Iniciar e rode:
echo =====================================================================
echo.
echo    sudo apt update
echo    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv
echo.
echo  Depois de instalar, feche o Ubuntu e clique novamente em run.bat.
echo.
echo  Se voce nao tiver permissao de administrador neste computador,
echo  peca a uma pessoa com acesso de administrador para:
echo    - Liberar permissao de sudo para seu usuario;
echo    - Instalar os pacotes acima via conta de administrador.
echo.
echo =====================================================================
pause
exit /b 1

REM --------------------------------------------------------------------
REM  INSTALACAO ASSISTIDA -- chama install_wsl_dependencies.sh na distro
REM --------------------------------------------------------------------
:instalar_deps
echo.
echo [INFO] Iniciando instalacao de dependencias no Ubuntu/WSL...
echo [INFO] O Ubuntu pode pedir sua senha nesta etapa.
echo.

REM Converte o caminho do bundle para formato WSL
for /f "delims=" %%i in ('%WSL_RUN% wslpath -a "%BUNDLE_DIR%"') do set "WSL_BUNDLE_DIR=%%i"

%WSL_RUN% bash -lc "bash '!WSL_BUNDLE_DIR!/install_wsl_dependencies.sh'"
set "INST_ERR=%errorlevel%"

if "%INST_ERR%"=="0" (
    echo.
    echo [INFO] Instalacao concluida. Verificando ambiente novamente...
    echo.
) else (
    echo.
    echo =====================================================================
    echo  [ERRO] Nao foi possivel instalar automaticamente as dependencias.
    echo =====================================================================
    echo.
    echo  Verifique se WSL, Ubuntu, sudo e internet estao liberados,
    echo  ou rode os comandos abaixo manualmente:
    echo.
    echo    sudo apt update
    echo    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv
    echo.
    echo =====================================================================
    pause
    exit /b 1
)

REM --- Novo diagnostico apos instalacao -------------------------------
set "AINDA_FALTA="

%WSL_RUN% bash -lc "command -v make" >nul 2>nul
if errorlevel 1 set "AINDA_FALTA=make"

%WSL_RUN% bash -lc "command -v python3" >nul 2>nul
if errorlevel 1 (
    if defined AINDA_FALTA (
        set "AINDA_FALTA=!AINDA_FALTA!, python3"
    ) else (
        set "AINDA_FALTA=python3"
    )
)

if defined AINDA_FALTA (
    echo.
    echo =====================================================================
    echo  [ERRO] Apos a instalacao, ainda faltam: !AINDA_FALTA!
    echo =====================================================================
    echo.
    echo  A instalacao automatica nao conseguiu completar a configuracao.
    echo.
    echo  Para tentar instalar manualmente, abra o Ubuntu e rode:
    echo.
    echo    sudo apt update
    echo    sudo apt install -y make build-essential git curl wget unzip dos2unix tar bzip2 ca-certificates python3 python3-venv
    echo.
    echo  Verifique se WSL, Ubuntu e sudo estao liberados neste computador.
    echo.
    echo =====================================================================
    pause
    exit /b 1
)

echo [OK] Dependencias instaladas e verificadas com sucesso!
echo.

REM --------------------------------------------------------------------
REM  Tudo OK -- abrir o Gene-In
REM --------------------------------------------------------------------
:executar
echo.
echo [OK] Ambiente verificado: WSL + !DISTRO_NAME! + make + python3 encontrados.
echo [OK] Iniciando Gene-In...
echo.

if "%USE_DISTRO%"=="padrao" (
    for /f "delims=" %%i in ('wsl.exe wslpath -a "%BUNDLE_DIR%"') do set "WSL_BUNDLE_DIR=%%i"
    set "WSL_CMD=cd '!WSL_BUNDLE_DIR!/..' && bash bundle/run.sh %*"
    wsl.exe bash -lc "!WSL_CMD!"
) else (
    for /f "delims=" %%i in ('wsl.exe %USE_DISTRO% wslpath -a "%BUNDLE_DIR%"') do set "WSL_BUNDLE_DIR=%%i"
    set "WSL_CMD=cd '!WSL_BUNDLE_DIR!/..' && bash bundle/run.sh %*"
    wsl.exe %USE_DISTRO% bash -lc "!WSL_CMD!"
)

if errorlevel 1 (
    echo.
    echo =====================================================================
    echo  [ERRO] Servidor encerrou com erro. Verifique acima.
    echo =====================================================================
    pause
    exit /b 1
)
