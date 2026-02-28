#!/bin/bash
# deploy.sh - Deploy MCProxy to remote server via SSH

set -e

# Configuration
REMOTE_HOST="${1:-server2-auto}"
REMOTE_PATH="/srv/containers/mcproxy"
SERVICE_NAME="mcproxy"

echo "📦 Deploying MCProxy to ${REMOTE_HOST}..."

# Step 1: Copy application files
echo "📄 Copying application files..."
ssh ${REMOTE_HOST} "mkdir -p ${REMOTE_PATH}"
scp *.py "${REMOTE_HOST}:${REMOTE_PATH}/"
scp requirements.txt "${REMOTE_HOST}:${REMOTE_PATH}/"
scp mcproxy.container "${REMOTE_HOST}:/tmp/"
scp .env.example "${REMOTE_HOST}:${REMOTE_PATH}/.env.example"
scp mcp-servers.example.json "${REMOTE_HOST}:${REMOTE_PATH}/config/mcp-servers.json.example"

# Step 2: Setup Python environment
echo "🐍 Setting up Python environment..."
ssh ${REMOTE_HOST} << 'ENDSSH'
cd /srv/containers/mcproxy
python3.11 -m venv venv || true
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ENDSSH

# Step 3: Setup systemd service
echo "🔧 Setting up systemd service..."
ssh ${REMOTE_HOST} << 'ENDSSH'
if [ -f /etc/systemd/system/${SERVICE_NAME}.service ]; then
    echo "⚠️  Service file already exists, skipping..."
else
    sudo cp /tmp/mcproxy.container /etc/containers/systemd/${SERVICE_NAME}.container
    sudo chmod 644 /etc/containers/systemd/${SERVICE_NAME}.container
    sudo chown root:root /etc/containers/systemd/${SERVICE_NAME}.container
    sudo systemctl daemon-reload
fi

# Create config directory
sudo mkdir -p ${REMOTE_PATH}/config
sudo chown -R server:server ${REMOTE_PATH}
ENDSSH

# Step 4: Copy example config
echo "📝 Creating example config..."
scp config/mcp-servers.example.json "${REMOTE_HOST}:${REMOTE_PATH}/config/mcp-servers.json.example"

# Step 5: Instructions
echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Configure MCP servers:"
echo "   ssh ${REMOTE_HOST} 'nano ${REMOTE_PATH}/config/mcp-servers.json'"
echo ""
echo "2. Set API keys:"
echo "   ssh ${REMOTE_HOST} 'nano ${REMOTE_PATH}/.env'"
echo ""
echo "3. Start service:"
echo "   ssh ${REMOTE_HOST} 'sudo systemctl start ${SERVICE_NAME}'"
echo ""
echo "4. View logs:"
echo "   ssh ${REMOTE_HOST} 'sudo journalctl -u ${SERVICE_NAME} -f'"
echo ""
echo "🚀 Ready to go!"
