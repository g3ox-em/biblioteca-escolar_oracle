@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
if not exist .venv\Scripts\python.exe py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fallo
.venv\Scripts\python.exe app.py
:fallo
pause
