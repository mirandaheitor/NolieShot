@echo off
title NolieShot
cd /d "%~dp0"

:: O jogo do servidor local roda como administrador (o launcher grava em HKLM).
:: Um programa comum nao consegue ler o teclado enquanto uma janela elevada esta
:: em foco, entao o overlay tambem precisa rodar como administrador.
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Pedindo permissao de administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

python -u main.py
pause
