@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 清理旧的构建产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo 开始打包...
python -m PyInstaller --noconfirm --onedir --windowed --name WebFast ^
  --icon "web\\icon.ico" ^
  --add-data "web;web" ^
  --add-data "tools;tools" ^
  --add-data "settings.toml;." ^
  --collect-all webview ^
  --hidden-import clr ^
  webfast_app.py
echo.
if exist "dist\\WebFast\\WebFast.exe" (
  echo 打包完成: dist\\WebFast\\WebFast.exe
) else (
  echo 打包失败，看上面的报错
)
pause
