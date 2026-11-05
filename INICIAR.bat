@echo off
setlocal
cd /d "%~dp0"
title Sincronizador de canciones v5
py -3.12-64 --version >nul 2>nul
if errorlevel 1 (
    py -3.12 --version >nul 2>nul
    if errorlevel 1 (
        echo ERROR: No encuentro Python 3.12 de 64 bits.
        echo Instala Python 3.12 desde https://www.python.org/downloads/release/python-31210/
        pause
        exit /b 1
    )
    set PY=py -3.12
) else (
    set PY=py -3.12-64
)
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 goto error
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto error
python -m pip install -r requirements.txt
if errorlevel 1 goto error
python -m streamlit run app.py
if errorlevel 1 goto error
goto end
:error
echo.
echo ERROR durante la instalacion o el arranque. Copia el mensaje anterior.
pause
exit /b 1
:end
pause
