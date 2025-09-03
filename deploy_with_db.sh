#!/bin/bash

### ─── CONFIGURATION ─────────────────────────────────────────────────────
REMOTE_USER="root"
REMOTE_HOST="69.48.203.91"
REMOTE_PATH="/var/www/cannoli"
LOCAL_PATH="/mnt/c/Users/madha/OneDrive/Desktop/final-cannoli"
LOCAL_DB_PATH="$LOCAL_PATH/instance/quizbowl.db"
REMOTE_DB_PATH="$REMOTE_PATH/instance/quizbowl.db"
SSH_PASSWORD="DoaIe41q"

VENV_NAME="venv"
REQUIREMENTS_FILENAME="requirements.txt"
SYSTEMD_PATH="/etc/systemd/system/cannoli.service"

### ─── COLOR CONSTANTS ───────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

### ─── STATUS FUNCTIONS ──────────────────────────────────────────────────
status() {
    echo -e "${YELLOW}[*]${NC} $1"
}
success() {
    echo -e "${GREEN}[+]${NC} $1"
}
error() {
    echo -e "❌ Error: $1" >&2
    exit 1
}

### ─── CHECK ENVIRONMENT ─────────────────────────────────────────────────
if ! grep -qE "(Microsoft|WSL)" /proc/version &> /dev/null; then
    error "This script must be run from WSL (Windows Subsystem for Linux)"
fi

for cmd in rsync sshpass; do
    if ! command -v $cmd &> /dev/null; then
        status "Installing missing dependency: $cmd..."
        sudo apt-get update && sudo apt-get install -y $cmd || error "Failed to install $cmd"
    fi
done

export SSHPASS="$SSH_PASSWORD"

### ─── RSYNC SYNC ────────────────────────────────────────────────────────
EXCLUDES=(
    "--exclude=__pycache__"
    "--exclude=*.pyc"
    "--exclude=*.db"
    "--exclude=*.log"
    "--exclude=.coverage"
    "--exclude=.pytest_cache"
    "--exclude=logs"
    "--exclude=instance"
    "--exclude=node_modules"
    "--exclude=.git"
    "--exclude=.idea"
    "--exclude=$VENV_NAME"
    "--exclude=.env"
)

status "Syncing local files to remote server..."
rsync -avz --delete "${EXCLUDES[@]}" \
    -e "sshpass -e ssh -o StrictHostKeyChecking=no" \
    "$LOCAL_PATH/" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/" || error "File sync failed"

### ─── SEND DATABASE FILE ────────────────────────────────────────────────
if [ -f "$LOCAL_DB_PATH" ]; then
    status "Copying SQLite database to remote server..."
    sshpass -e ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_PATH/instance"
    sshpass -e scp -o StrictHostKeyChecking=no "$LOCAL_DB_PATH" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DB_PATH" || error "Failed to copy DB"
    success "Database file copied to $REMOTE_DB_PATH"
else
    error "Local DB file not found at $LOCAL_DB_PATH"
fi

### ─── REMOTE SETUP ──────────────────────────────────────────────────────
status "Setting up virtual environment and restarting Gunicorn..."

sshpass -e ssh -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_HOST" bash <<'EOF'
set -e

REMOTE_PATH="/var/www/cannoli"
VENV_PATH="$REMOTE_PATH/venv"
REQUIREMENTS_FILE="$REMOTE_PATH/requirements.txt"
SYSTEMD_FILE="/etc/systemd/system/cannoli.service"

cd "$REMOTE_PATH" || { echo "❌ Remote path not found"; exit 1; }

# Rebuild virtual environment
echo "⚙️ Recreating virtual environment..."
rm -rf "$VENV_PATH"
python3 -m venv "$VENV_PATH"
source "$VENV_PATH/bin/activate"
pip install --upgrade pip

# Install from requirements.txt
if [ -f "$REQUIREMENTS_FILE" ]; then
    echo "📦 Installing Python packages from $REQUIREMENTS_FILE"
    pip install -r "$REQUIREMENTS_FILE"
else
    echo "❌ requirements.txt not found at $REQUIREMENTS_FILE"
    exit 1
fi

# Ensure Gunicorn is installed in the venv
if ! command -v gunicorn &> /dev/null || [[ "$(which gunicorn)" != "$VENV_PATH/bin/gunicorn" ]]; then
    echo "🚀 Installing Gunicorn in virtualenv..."
    pip install gunicorn
fi

# Patch systemd service to use venv gunicorn
echo "📝 Ensuring systemd uses virtualenv Gunicorn..."
if ! grep -q "$VENV_PATH/bin/gunicorn" "$SYSTEMD_FILE"; then
    echo "🔄 Patching $SYSTEMD_FILE"

    cat <<UNITFILE > "$SYSTEMD_FILE"
[Unit]
Description=Gunicorn for Cannoli Flask App
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=$REMOTE_PATH
Environment="PATH=$VENV_PATH/bin"
ExecStart=$VENV_PATH/bin/gunicorn --workers 3 --bind unix:$REMOTE_PATH/cannoli.sock wsgi:app --timeout 120

[Install]
WantedBy=multi-user.target
UNITFILE

    systemctl daemon-reexec
    systemctl daemon-reload
fi

# Restart service
echo "🔁 Restarting Gunicorn service..."
sudo systemctl restart cannoli || echo "⚠️ Failed to restart Gunicorn"

# Status and logs
echo -e "\n==== Gunicorn Service Status ===="
sudo systemctl status cannoli --no-pager || echo "⚠️ Unable to get status"

echo -e "\n==== Last 100 Gunicorn Logs ===="
sudo journalctl -u cannoli -n 100 --no-pager --output=cat || echo "⚠️ Unable to get logs"

echo -e "\n==== Gunicorn Error Logs ===="
[ -f "$REMOTE_PATH/logs/error.log" ] && tail -n 100 "$REMOTE_PATH/logs/error.log" || echo "No error log"

echo -e "\n==== Gunicorn Access Logs ===="
[ -f "$REMOTE_PATH/logs/access.log" ] && tail -n 50 "$REMOTE_PATH/logs/access.log" || echo "No access log"

echo -e "\n==== Running Gunicorn Processes ===="
ps aux | grep -i gunicorn | grep -v grep || echo "No Gunicorn processes found"
EOF

### ─── DONE ──────────────────────────────────────────────────────────────
if [ $? -eq 0 ]; then
    success "Deployment completed successfully!"
    echo "🌐 Application should be available at: https://read.liqba.com"
else
    error "Deployment failed. Check output above."
fi
