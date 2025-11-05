@echo off
REM Launcher for Protein-GUI
REM This makes it easy to start the application on any Windows machine

echo ========================================
echo  Sen Lab - Protein Analysis Suite
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.x from https://www.python.org/
    echo.
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import PyQt5" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] PyQt5 not found. Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)

echo Starting Protein Analysis GUI...
echo.
python protein_gui.py

if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with an error
    pause
)

