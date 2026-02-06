#!/bin/bash
# setup.sh - Quick setup script for local development

set -e

echo "🚀 MCProxy Setup Script"
echo ""

# Check Python version
if ! command -v python3.11 &> /dev/null; then
    echo "❌ Python 3.11+ not found. Please install Python 3.11 or later."
    exit 1
fi

echo "✅ Python 3.11+ found"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "🐍 Creating virtual environment..."
    python3.11 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Create config directory
mkdir -p config

# Create .env from example if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚠️  Created .env from example. Please add your API keys:"
    echo "   nano .env"
    exit 0
fi

# Create config from example if not exists
if [ ! -f "config/mcp-servers.json" ]; then
    cp mcp-servers.example.json config/mcp-servers.json
    echo "✅ Created config/mcp-servers.json from example"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Start MCProxy:"
echo "  source venv/bin/activate"
echo "  python main.py --log"
echo ""
echo "Or with custom config:"
echo "  python main.py --log --config config/mcp-servers.json --port 12010"
