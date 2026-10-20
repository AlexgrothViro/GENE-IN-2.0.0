@echo off
setlocal EnableExtensions
title Gene-In - Atualizar plataforma

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo  =====================================================================
echo   Gene-In -- Atualizador para Windows / WSL
echo  =====================================================================
echo.
echo   Este atualizador sincroniza o ambiente isolado do bundle atual.
echo.

if not exist "%ROOT%\bundle\run.bat" (
    echo  [ERRO] bundle\run.bat nao foi encontrado.
    echo        Verifique se o repositorio foi extraido por completo.
    echo.
    pause
    exit /b 1
)

echo  [1/2] Atualizando ambiente Mamba isolado...
echo.
call "%ROOT%\bundle\run.bat" update-env
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" goto falha

echo.
echo  [2/2] Validando ambiente atualizado...
echo.
call "%ROOT%\bundle\run.bat" test-env
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" goto falha

echo.
echo  =====================================================================
echo   [OK] Gene-In atualizado com sucesso.
echo  =====================================================================
echo.
pause
exit /b 0

:falha
echo.
echo  =====================================================================
echo   [ERRO] A atualizacao do Gene-In falhou.
echo  =====================================================================
echo.
echo   Verifique as mensagens acima e tente novamente.
echo.
pause
exit /b %ERR%
