@echo off
setlocal

cd /d "%~dp0..\..\backend"
set "DJANGO_SETTINGS_MODULE=config.settings_ngrok"

"..\.venv\Scripts\python.exe" manage.py check
if errorlevel 1 exit /b 1

"..\.venv\Scripts\python.exe" manage.py collectstatic --noinput
if errorlevel 1 exit /b 1

"..\.venv\Scripts\waitress-serve.exe" --listen=127.0.0.1:8000 --threads=4 --url-scheme=https config.wsgi:application
