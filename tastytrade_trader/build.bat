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

:: Build the executable
echo.
echo [2/3] Building Windows executable...
pyinstaller ^
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
echo [3/3] Done!
echo Executable: dist\TastyTradeTrader.exe
echo.
pause
