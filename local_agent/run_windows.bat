@echo off
cd /d %~dp0
py -3 -m venv .venv
call .venv\\Scripts\\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chrome
if exist ..\\.env copy ..\\.env .env
python agent.py
pause
