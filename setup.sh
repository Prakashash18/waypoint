#!/bin/bash
# Waypoint Setup Script

set -e

echo "🛫 Waypoint Setup"
echo "================"
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3.12 &> /dev/null; then
    echo "❌ Python 3.12 not found. Please install Python 3.12 first."
    exit 1
fi
echo "✓ Python 3.12 found"

# Check if atlas-flight is installed
echo "Checking Atlas CLI..."
if ! command -v atlas-flight &> /dev/null; then
    echo "Installing Atlas CLI..."
    if command -v pipx &> /dev/null; then
        pipx install atlas-flight-booking --python python3.12
    else
        echo "❌ pipx not found. Install with: brew install pipx"
        exit 1
    fi
fi
echo "✓ Atlas CLI found"

# Create virtual environment
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3.12 -m venv venv
fi
echo "✓ Virtual environment ready"

# Install dependencies
echo "Installing Python dependencies..."
source venv/bin/activate
pip install -q flask flask-cors python-dotenv pydantic email-validator gunicorn
echo "✓ Dependencies installed"

# Configure environment
echo "Configuring environment..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ Created .env file (edit to add API keys)"
fi

# Switch to sandbox
echo "Switching to sandbox environment..."
export PATH="$HOME/.local/bin:$PATH"
atlas-flight environment use sandbox --json > /dev/null
echo "✓ Sandbox environment active"

echo ""
echo "================"
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Authenticate with Atlas:"
echo "   atlas-flight auth login"
echo "   atlas-flight auth poll"
echo ""
echo "2. (Optional) Add DASHSCOPE_API_KEY to .env for Qwen reasoning"
echo ""
echo "3. Run the web UI:"
echo "   source venv/bin/activate"
echo "   python run.py"
echo ""
echo "4. Or run the CLI demo:"
echo "   source venv/bin/activate"
echo "   python demo.py"
echo ""
