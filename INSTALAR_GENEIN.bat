@echo off
setlocal EnableExtensions
title Gene-In - Instalador para Windows/WSL

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo  =====================================================================
echo   Gene-In -- Instalador para Windows / WSL
echo  =====================================================================
echo.
echo   Este instalador usa o bundle atual do Gene-In:
echo     - detecta WSL/Ubuntu
echo     - instala dependencias basicas quando necessario
echo     - cria ou atualiza o ambiente isolado em ~/.gene-in-bundle
echo     - valida as ferramentas do pipeline
echo.

if not exist "%ROOT%\bundle\run.bat" (
    echo  [ERRO] bundle\run.bat nao foi encontrado.
    echo        Verifique se o repositorio foi extraido por completo.
    echo.
    pause
    exit /b 1
)

echo  [1/2] Instalando ou atualizando o ambiente isolado...
echo.
call "%ROOT%\bundle\run.bat" install
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" goto falha

echo.
echo  [2/2] Validando ambiente do Gene-In...
echo.
call "%ROOT%\bundle\run.bat" test-env
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" goto falha

echo.
echo  =====================================================================
echo   [OK] Gene-In instalado e validado com sucesso.
echo  =====================================================================
echo.
echo   Para iniciar o painel, execute:
echo     ABRIR_GENEIN.bat
echo.
pause
exit /b 0

:falha
echo.
echo  =====================================================================
echo   [ERRO] A instalacao/validacao do Gene-In falhou.
echo  =====================================================================
echo.
echo   Verifique as mensagens acima. Em computadores institucionais, pode
echo   ser necessario liberar WSL, Ubuntu, sudo e acesso a internet.
echo.
pause
exit /b %ERR%
