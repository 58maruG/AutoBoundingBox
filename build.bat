@echo off
rem A2B 自動アノテーションツール の .exe ビルド
cd /d "%~dp0"
uv run pyinstaller A2B.spec --noconfirm
echo.
echo ============================================================
echo ビルド完了:
echo   dist\A2B\A2B.exe
echo ============================================================
pause
