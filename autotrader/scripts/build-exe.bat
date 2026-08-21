@echo off
REM ---------------------------------------------------------------------------
REM  Build a standalone trader.exe that runs without Python installed.
REM  Run setup.bat first, then run this from the project root:
REM      scripts\build-exe.bat
REM  The result lands in dist\trader.exe -- copy it anywhere you like.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" goto :nosetup

echo Installing PyInstaller ...
".venv\Scripts\python.exe" -m pip install --quiet "pyinstaller>=6"
if errorlevel 1 goto :fail

echo Building dist\trader.exe (this takes a minute) ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile ^
    --name trader ^
    --collect-all alpaca ^
    --collect-submodules autotrader ^
    --add-data "src\autotrader\web\static;autotrader/web/static" ^
    scripts\trader_entry.py
if errorlevel 1 goto :fail

echo.
echo Built dist\trader.exe
echo.
echo It reads its config and credentials from %USERPROFILE%\.autotrader\,
echo so it works from any folder. Try:
echo.
echo     dist\trader.exe status
echo.
pause
exit /b 0

:nosetup
echo Run setup.bat first -- this build needs the project's virtual environment.
pause
exit /b 1

:fail
echo.
echo Build failed. See the errors above.
pause
exit /b 1
