@echo off
echo ============================================
echo  TastyTrade Algo Trader - Windows Build
echo ============================================
echo.

:: Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause & exit /b 1
)

:: Kill any running instance and remove the old exe so Windows releases the lock
echo [2/3] Preparing build directory...
taskkill /f /im TastyTradeTrader.exe >nul 2>&1
timeout /t 2 /nobreak >nul
if exist dist\TastyTradeTrader.exe (
    del /f /q dist\TastyTradeTrader.exe
    if exist dist\TastyTradeTrader.exe (
        echo ERROR: Cannot delete dist\TastyTradeTrader.exe - close the app and try again.
        pause & exit /b 1
    )
)

:: Build the executable
echo.
echo [3/4] Building Windows executable...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "TastyTradeTrader" ^
    --add-data "config;config" ^
    --add-data "trading;trading" ^
    --add-data "ui;ui" ^
    --hidden-import "tastytrade" ^
    --hidden-import "PyQt6.QtCore" ^
    --hidden-import "PyQt6.QtWidgets" ^
    --hidden-import "PyQt6.QtGui" ^
    --hidden-import "keyring.backends.Windows" ^
    main.py

if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    pause & exit /b 1
)

echo.
echo [4/4] Done!
echo Executable: dist\TastyTradeTrader.exe
echo.
pause
