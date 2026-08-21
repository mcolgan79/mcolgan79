@echo off
REM Start the autotrader dashboard and open it in your browser.
REM Run setup.bat once first.
setlocal
if not exist "%~dp0.venv\Scripts\trader.exe" goto :nosetup
"%~dp0.venv\Scripts\trader.exe" gui %*
exit /b %errorlevel%

:nosetup
echo autotrader is not set up yet on this machine. Run setup.bat first.
pause
exit /b 1
