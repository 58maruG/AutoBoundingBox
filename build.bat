@echo off
rem DCRsystem 自動アノテーションツール の .exe ビルド
cd /d "%~dp0"
uv run pyinstaller DCRsystem_AutoAnnotator.spec --noconfirm
echo.
echo ============================================================
echo ビルド完了:
echo   dist\DCRsystem_AutoAnnotator\DCRsystem_AutoAnnotator.exe
echo ============================================================
pause
