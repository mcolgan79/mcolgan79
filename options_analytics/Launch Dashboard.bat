@echo off
title Options Portfolio Analytics
color 0A

echo ================================================
echo    Options Portfolio Analytics Dashboard
echo ================================================
echo.
echo Keep this window open while using the app.
echo Close it when you are done.
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    color 0C
    echo ERROR: Python is not installed.
    echo.
    echo Please go to https://www.python.org/downloads/
    echo Download and run the installer.
    echo.
    echo IMPORTANT: Check the box that says
    echo "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)

echo [1/2] Installing required packages...
echo       (This only takes a moment on first run)
echo.
pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo.
    echo ERROR: Failed to install packages.
    echo Make sure you are connected to the internet.
    echo.
    pause
    exit /b 1
)

echo [2/2] Starting dashboard...
echo.
echo Your browser will open automatically.
echo If it does not, go to: http://localhost:8501
echo.
echo ------------------------------------------------

python -m streamlit run "%~dp0app.py" --server.headless false

echo.
echo Dashboard stopped.
pause
