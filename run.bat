@echo off
REM Quick start script for Windows

echo.
echo ========================================
echo   Faaya Product Preprocessor Launcher
echo ========================================
echo.

REM Check if venv exists
if not exist "venv\" (
    echo [1/3] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv. Make sure Python 3.8+ is installed.
        pause
        exit /b 1
    )
)

REM Activate venv
echo [2/3] Activating virtual environment...
call venv\Scripts\activate.bat

REM Install requirements
echo [3/3] Installing dependencies...
pip install -r requirements.txt --quiet

REM Check for .env file
if not exist ".env" (
    echo.
    echo ⚠️  .env file not found!
    echo Please add your API key to .env:
    echo   ANTHROPIC_API_KEY=sk-ant-your-key-here
    echo.
    echo Get your key at: https://console.anthropic.com
    echo.
    pause
)

REM Run the server
echo.
echo ✅ Starting server...
echo 🌐 Open your browser: http://localhost:8000
echo.
python main.py
