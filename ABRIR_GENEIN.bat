@echo off
setlocal EnableExtensions
title Gene-In - Abrir plataforma

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo  =====================================================================
echo   Gene-In -- Abrindo plataforma
echo  =====================================================================
echo.

if not exist "%ROOT%\start_platform.bat" (
    echo  [ERRO] start_platform.bat nao foi encontrado em:
    echo        "%ROOT%"
    echo.
    echo  Verifique se o pacote do Gene-In foi extraido por completo.
    echo.
    pause
    exit /b 1
)

call "%ROOT%\start_platform.bat"
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
    echo.
    echo  =====================================================================
    echo   [ERRO] Nao foi possivel abrir a plataforma Gene-In.
    echo  =====================================================================
    echo.
    pause
    exit /b %ERR%
)

exit /b 0
