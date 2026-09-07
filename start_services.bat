@echo off
rem One-click wrapper for start_services.py (Windows).
set "PY=D:\tool\anaconda\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%~dp0start_services.py" %*
