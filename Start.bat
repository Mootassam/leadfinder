@echo off
cd /d "%~dp0"
title Lead Finder
python -c "import flask, requests, dns, openpyxl" 2>nul || python -m pip install -r requirements.txt
python server.py
pause
