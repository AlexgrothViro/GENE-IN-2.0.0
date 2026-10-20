@echo off
setlocal EnableExtensions
title Gene-In - Remover plataforma

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo  =====================================================================
echo   Gene-In -- Desinstalador para Windows / WSL
echo  =====================================================================
echo.
echo   Este script remove o ambiente isolado do Gene-In no WSL:
echo     ~/.gene-in-bundle
echo.
echo   Ele nao remove nem desregistra distribuicoes WSL do usuario.
echo.

set /p CONFIRM="  Tem certeza que deseja remover o ambiente Gene-In? [S/N]: "
if /i not "%CONFIRM%"=="S" (
    echo [INFO] Remocao cancelada.
    pause
    exit /b 0
)

if not exist "%ROOT%\bundle\run.bat" (
    echo  [ERRO] bundle\run.bat nao foi encontrado.
    echo        Verifique se o repositorio foi extraido por completo.
    echo.
    pause
    exit /b 1
)

echo.
echo  [INFO] Removendo ambiente isolado do bundle no WSL...
echo.
call "%ROOT%\bundle\run.bat" uninstall-bundle
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" (
    echo.
    echo  =====================================================================
    echo   [ERRO] Nao foi possivel remover o ambiente isolado.
    echo  =====================================================================
    echo.
    pause
    exit /b %ERR%
)

echo.
set /p DEL_DATA="  Deseja tambem excluir a pasta de dados local (%USERPROFILE%\genein-dados)? [S/N]: "
if /i "%DEL_DATA%"=="S" (
    if exist "%USERPROFILE%\genein-dados" (
        echo [INFO] Removendo pasta de dados...
        rmdir /s /q "%USERPROFILE%\genein-dados"
        echo [OK] Pasta de dados excluida.
    ) else (
        echo [INFO] Pasta de dados local nao encontrada.
    )
)

echo.
echo  =====================================================================
echo   [OK] Remocao concluida.
echo  =====================================================================
echo.
pause
exit /b 0
