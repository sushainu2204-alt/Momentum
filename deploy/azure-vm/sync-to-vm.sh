#!/bin/bash
# =============================================================================
# Sync local code to Azure VM
# =============================================================================
# Usage:
#   ./sync-to-vm.sh              # One-time sync
#   ./sync-to-vm.sh --watch      # Watch and auto-sync
#   ./sync-to-vm.sh --deploy     # Sync and restart app
# =============================================================================

VM_USER="azureuser"
VM_IP="172.178.27.229"
LOCAL_PATH="/Users/sushmagollapudi/Momentum/"
REMOTE_PATH="~/Momentum/"

# Directories/files to exclude from sync
EXCLUDES=(
    '.git'
    '__pycache__'
    '*.pyc'
    '.env'
    'logs/'
    'data/orders/'
    '.DS_Store'
    '*.log'
    'node_modules'
    '.venv'
    'venv'
)

# Build exclude arguments
EXCLUDE_ARGS=""
for exclude in "${EXCLUDES[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude='$exclude'"
done

sync_once() {
    echo "🔄 Syncing to $VM_USER@$VM_IP..."
    eval rsync -avz --progress $EXCLUDE_ARGS "$LOCAL_PATH" "$VM_USER@$VM_IP:$REMOTE_PATH"
    echo "✅ Sync complete!"
}

sync_watch() {
    echo "👀 Watching for changes... (Ctrl+C to stop)"
    
    # Check if fswatch is installed
    if ! command -v fswatch &> /dev/null; then
        echo "❌ fswatch not installed. Install with: brew install fswatch"
        exit 1
    fi
    
    fswatch -o "$LOCAL_PATH" | while read; do
        echo "$(date '+%H:%M:%S') - Changes detected, syncing..."
        eval rsync -avz --quiet $EXCLUDE_ARGS "$LOCAL_PATH" "$VM_USER@$VM_IP:$REMOTE_PATH"
        echo "$(date '+%H:%M:%S') - ✅ Synced"
    done
}

sync_and_deploy() {
    sync_once
    echo ""
    echo "🚀 Restarting application on VM..."
    ssh "$VM_USER@$VM_IP" "cd ~/Momentum && docker-compose -f deploy/azure-vm/docker-compose.prod.yml up -d --build"
    echo "✅ Deployment complete!"
}

# Parse arguments
case "${1:-}" in
    --watch|-w)
        sync_watch
        ;;
    --deploy|-d)
        sync_and_deploy
        ;;
    --help|-h)
        echo "Usage: $0 [option]"
        echo ""
        echo "Options:"
        echo "  (none)      One-time sync"
        echo "  --watch     Watch and auto-sync on changes"
        echo "  --deploy    Sync and restart application"
        echo "  --help      Show this help"
        ;;
    *)
        sync_once
        ;;
esac
