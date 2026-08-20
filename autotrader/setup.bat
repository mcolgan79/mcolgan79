@echo off
REM ---------------------------------------------------------------------------
REM  autotrader first-time setup (Windows)
REM  Creates a virtual environment, installs the package, and stores your
REM  Alpaca paper credentials in %USERPROFILE%\.autotrader\
REM  Double-click this file, or run it from a Command Prompt.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

echo ==========================================
echo   autotrader setup
echo ==========================================
echo.

REM --- locate a Python 3.11+ interpreter ------------------------------------
REM  Point at a specific interpreter with:  set PYTHON=C:\Path\to\python.exe
set "PYCMD="
if defined PYTHON set "PYCMD=%PYTHON%"
if not defined PYCMD py -3.13 --version >nul 2>&1 && set "PYCMD=py -3.13"
if not defined PYCMD py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD py -3.11 --version >nul 2>&1 && set "PYCMD=py -3.11"
if not defined PYCMD py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD goto :nopython

%PYCMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :oldpython

for /f "delims=" %%v in ('%PYCMD% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%v"
echo [1/4] Using Python %PYVER%

REM --- virtual environment ---------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo [2/4] Reusing existing .venv
) else (
    echo [2/4] Creating .venv ...
    %PYCMD% -m venv .venv
    if errorlevel 1 goto :venvfailed
)

echo [3/4] Installing autotrader and its dependencies ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -e . --quiet
if errorlevel 1 goto :installfailed

REM --- credentials and config ------------------------------------------------
set "CFGDIR=%USERPROFILE%\.autotrader"
if not exist "%CFGDIR%" mkdir "%CFGDIR%"

if exist "%CFGDIR%\config.toml" (
    echo [4/4] Config already exists at %CFGDIR%\config.toml
) else (
    echo [4/4] Writing default config to %CFGDIR%\config.toml
    copy /y "config.example.toml" "%CFGDIR%\config.toml" >nul
)

if exist "%CFGDIR%\.env" goto :haveenv

echo.
echo Enter your Alpaca PAPER API credentials.
echo Get them at https://app.alpaca.markets/paper/dashboard/overview -^> API Keys
echo The key ID starts with PK. The secret is only shown once when you create it.
echo.
set /p "KEYID=  API Key ID    : "

REM Read the secret without echoing it to the screen.
set "SECRET="
for /f "delims=" %%s in ('powershell -NoProfile -Command "$s = Read-Host -AsSecureString '  Secret Key   '; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))" 2^>nul') do set "SECRET=%%s"
if not defined SECRET set /p "SECRET=  Secret Key    : "

if not defined KEYID goto :nokeys
if not defined SECRET goto :nokeys

> "%CFGDIR%\.env" echo APCA_API_KEY_ID=%KEYID%
>> "%CFGDIR%\.env" echo APCA_API_SECRET_KEY=%SECRET%
echo.
echo Credentials saved to %CFGDIR%\.env
goto :verify

:haveenv
echo.
echo Credentials already present at %CFGDIR%\.env
echo Delete that file and re-run this script to change them.

:verify
echo.
echo ==========================================
echo   Checking the connection
echo ==========================================
".venv\Scripts\trader.exe" doctor
if errorlevel 1 goto :doctorfailed

echo.
echo Setup complete. From now on use trader.bat, for example:
echo.
echo     trader.bat status
echo     trader.bat backtest
echo     trader.bat run --once --dry-run
echo.
goto :done

:nopython
echo ERROR: Python 3.11 or newer was not found on this machine.
echo Install it from https://www.python.org/downloads/windows/
echo and tick "Add python.exe to PATH" during installation.
goto :fail

:oldpython
echo ERROR: Python 3.11 or newer is required (this project uses tomllib).
echo Found:
%PYCMD% --version
echo.
echo Install a newer Python from https://www.python.org/downloads/windows/
echo and tick "Add python.exe to PATH", then re-run setup.bat.
echo.
echo Already have one somewhere unusual? Point at it directly:
echo     set PYTHON=C:\Path\to\python.exe
echo     setup.bat
goto :fail

:venvfailed
echo ERROR: could not create the virtual environment.
goto :fail

:installfailed
echo ERROR: dependency installation failed. Check your internet connection.
goto :fail

:nokeys
echo ERROR: both the key ID and the secret are required.
goto :fail

:doctorfailed
echo.
echo Setup finished, but the connection check failed -- see the errors above.
echo The most common causes are a mistyped secret key, or keys from the live
echo dashboard instead of the paper one.
goto :fail

:fail
echo.
pause
exit /b 1

:done
pause
exit /b 0
