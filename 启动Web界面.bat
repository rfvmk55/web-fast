@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python webfast.py web
) else (
  py -3 webfast.py web
)
pause
