@echo off
setlocal EnableDelayedExpansion EnableExtensions

rem -------------------------
rem start_platform.bat - atalho Windows para iniciar a plataforma UX
rem Delega para bundle\run.bat ux (WSL + micromamba)
rem -------------------------

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PORT=8000"
set "READY_REL=tmp/launcher-%RANDOM%-%RANDOM%-%RANDOM%.url"
set "READY_FILE=%ROOT%\%READY_REL:/=\%"

if not exist "%ROOT%\bundle\run.bat" (
    echo [ERRO] bundle\run.bat nao encontrado em "%ROOT%\bundle\".
    echo        Verifique se o repositorio esta completo e tente novamente.
    pause
    exit /b 1
)

echo =====================================================
echo   Gene-In Platform - Iniciando...
echo =====================================================
echo.
echo [1/3] Iniciando servidor WSL em segundo plano...
echo       (esta janela ficara aberta ate o servidor encerrar)
echo.

rem Inicia o servidor WSL em uma nova janela separada (nao bloqueia)
start "Gene-In - Servidor WSL" cmd /c ""%ROOT%\bundle\run.bat" ux PORT=%PORT% UX_ARGS=--ready-file=%READY_REL% || (echo. & echo [ERRO] Servidor encerrou com erro. Verifique acima. & pause)"

rem Aguarda ate o servidor estar pronto (300 tentativas x 2 s = 600 s no total)
echo [2/3] Aguardando servidor em http://localhost:%PORT%/ ...
echo       (primeira execucao pode levar varios minutos para instalar o ambiente)
echo.
set "SERVER_URL="
for /f "tokens=*" %%U in ('powershell -ExecutionPolicy Bypass -NoProfile -NonInteractive -File "%ROOT%\bundle\wait_for_server.ps1" -ReadyFile "%READY_FILE%" -MaxTry 300') do (
    echo %%U | findstr /b "http://127.0.0.1:" >nul && set "SERVER_URL=%%U"
)

if not defined SERVER_URL (
    echo.
    echo [ERRO] O servidor nao respondeu dentro do tempo esperado.
    echo        Verifique a janela "Gene-In - Servidor WSL" para detalhes do erro.
    pause
    exit /b 1
)

echo.
echo [3/3] Abrindo !SERVER_URL! no navegador...
start "" "!SERVER_URL!"
exit /b 0
