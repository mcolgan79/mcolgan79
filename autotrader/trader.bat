@echo off
REM ---------------------------------------------------------------------------
REM  autotrader launcher (Windows). Run setup.bat once first.
REM  Usage:  trader.bat status
REM          trader.bat backtest --start 2022-01-01
REM          trader.bat run --once --dry-run
REM ---------------------------------------------------------------------------
setlocal
if not exist "%~dp0.venv\Scripts\trader.exe" goto :nosetup
"%~dp0.venv\Scripts\trader.exe" %*
exit /b %errorlevel%

:nosetup
echo autotrader is not set up yet on this machine.
echo Run setup.bat first (double-click it, or run it from a Command Prompt).
pause
exit /b 1
