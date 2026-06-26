#!/bin/bash

echo ""
echo "========================================"
echo "  Faaya Product Preprocessor Launcher"
echo "========================================"
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python 3 not found!"
    echo "Please install Python 3.8+ from https://www.python.org/downloads/"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[1/3] Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
echo "[2/3] Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "[3/3] Installing dependencies..."
echo "⏳ This may take 2-3 minutes on first run (rembg downloads ~170MB model)..."
pip install -r requirements.txt --quiet

# Check for .env file
if [ ! -f ".env" ]; then
    echo ""
    echo "⚠️  .env file not found!"
    echo "Please add your API key to .env:"
    echo "  ANTHROPIC_API_KEY=sk-ant-your-key-here"
    echo ""
    echo "Get your key at: https://console.anthropic.com"
    echo ""
    read -p "Press Enter to continue..."
fi

# Run the server
echo ""
echo "✅ Starting server..."
echo "🌐 Open your browser: http://localhost:8000"
echo ""
python3 main.py
