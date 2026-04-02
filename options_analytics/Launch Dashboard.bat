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
echo Checking for Python...
python --version
if errorlevel 1 (
    color 0C
    echo.
    echo ERROR: Python is not installed or not in PATH.
    echo.
    echo Please go to https://www.python.org/downloads/
    echo Download and run the installer.
    echo IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)

echo.
echo [1/2] Installing required packages...
echo       (You will see output - this is normal)
echo.
python -m pip install -r "%~dp0requirements.txt" --disable-pip-version-check
if errorlevel 1 (
    color 0C
    echo.
    echo ERROR: Failed to install packages.
    echo Check the output above for details.
    echo Make sure you are connected to the internet.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/2] Starting dashboard...
echo Your browser will open automatically.
echo If it does not, go to: http://localhost:8501
echo.
echo ------------------------------------------------

python -m streamlit run "%~dp0app.py"

echo.
echo Dashboard stopped.
pause
