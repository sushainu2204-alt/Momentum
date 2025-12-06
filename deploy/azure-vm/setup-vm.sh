#!/bin/bash
# =============================================================================
# Azure VM Setup Script for Momentum Trading System
# =============================================================================
# Run this script on a fresh Ubuntu 22.04 VM to install all dependencies
# and configure the environment for running the Momentum Trading System.
#
# Usage:
#   chmod +x setup-vm.sh
#   ./setup-vm.sh
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# Step 1: System Updates
# =============================================================================
log_info "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# =============================================================================
# Step 2: Install Required Packages
# =============================================================================
log_info "Installing required system packages..."
sudo apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    htop \
    vim \
    ufw \
    fail2ban

# =============================================================================
# Step 3: Install Docker
# =============================================================================
log_info "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    log_info "Docker installed successfully"
else
    log_info "Docker already installed"
fi

# =============================================================================
# Step 4: Install Docker Compose
# =============================================================================
log_info "Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    log_info "Docker Compose installed successfully"
else
    log_info "Docker Compose already installed"
fi

# =============================================================================
# Step 5: Configure Firewall
# =============================================================================
log_info "Configuring firewall (UFW)..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 8000/tcp  # Application port
sudo ufw allow 80/tcp    # HTTP (for future Nginx)
sudo ufw allow 443/tcp   # HTTPS (for future SSL)
sudo ufw --force enable
log_info "Firewall configured"

# =============================================================================
# Step 6: Configure Fail2ban (SSH protection)
# =============================================================================
log_info "Configuring Fail2ban..."
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
log_info "Fail2ban configured"

# =============================================================================
# Step 7: Set Timezone
# =============================================================================
log_info "Setting timezone to Asia/Kolkata (IST)..."
sudo timedatectl set-timezone Asia/Kolkata

# =============================================================================
# Step 8: Create Application Directory
# =============================================================================
log_info "Creating application directory structure..."
mkdir -p ~/Momentum
mkdir -p ~/backups
mkdir -p ~/logs

# =============================================================================
# Step 9: Create Environment File Template
# =============================================================================
log_info "Creating environment file template..."
if [ ! -f ~/Momentum/.env ]; then
    cat > ~/Momentum/.env << 'EOF'
# =============================================================================
# Momentum Trading System - Environment Configuration
# =============================================================================
# IMPORTANT: Update these values with your actual credentials!
# =============================================================================

# Zerodha Kite API Credentials
KITE_API_KEY=aspi1lqnmd19lym0
KITE_API_SECRET=he4mwtbayabp60rya72jdtfxc658yvh7
KITE_REDIRECT_URL=https://172.178.27.229:8000/callback
KITE_ACCESS_TOKEN=

# Database Configuration
POSTGRES_DB=appdb
POSTGRES_USER=appuser
POSTGRES_PASSWORD=secret

# Redis Configuration
REDIS_URL=redis://redis:6379/0

# Application Settings
ENVIRONMENT=production
LOG_LEVEL=DEBUG
EOF
    log_warn "Environment file created at ~/Momentum/.env"
    log_warn "Please edit this file with your actual credentials!"
else
    log_info "Environment file already exists"
fi

# =============================================================================
# Step 10: Create Utility Scripts
# =============================================================================
log_info "Creating utility scripts..."

# Health check script
cat > ~/check_health.sh << 'EOF'
#!/bin/bash
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [ "$HEALTH" != "200" ]; then
    echo "$TIMESTAMP: Health check failed with code $HEALTH" >> ~/logs/health-check.log
    cd ~/Momentum && docker-compose -f deploy/azure-vm/docker-compose.prod.yml restart backend
    echo "$TIMESTAMP: Backend restarted" >> ~/logs/health-check.log
fi
EOF
chmod +x ~/check_health.sh

# Backup script
cat > ~/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="$HOME/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker exec momentum-postgres pg_dump -U appuser appdb > $BACKUP_DIR/db_backup_$TIMESTAMP.sql 2>/dev/null

if [ $? -eq 0 ]; then
    echo "$(date): Backup successful - db_backup_$TIMESTAMP.sql" >> ~/logs/backup.log
    # Compress backup
    gzip $BACKUP_DIR/db_backup_$TIMESTAMP.sql
    # Keep only last 7 days of backups
    find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +7 -delete
else
    echo "$(date): Backup failed" >> ~/logs/backup.log
fi
EOF
chmod +x ~/backup_db.sh

# Start application script
cat > ~/start_momentum.sh << 'EOF'
#!/bin/bash
cd ~/Momentum
docker-compose -f deploy/azure-vm/docker-compose.prod.yml up -d --build
echo "Momentum Trading System started!"
echo "Check status with: docker-compose -f deploy/azure-vm/docker-compose.prod.yml ps"
EOF
chmod +x ~/start_momentum.sh

# Stop application script
cat > ~/stop_momentum.sh << 'EOF'
#!/bin/bash
cd ~/Momentum
docker-compose -f deploy/azure-vm/docker-compose.prod.yml down
echo "Momentum Trading System stopped!"
EOF
chmod +x ~/stop_momentum.sh

# View logs script
cat > ~/view_logs.sh << 'EOF'
#!/bin/bash
cd ~/Momentum
docker-compose -f deploy/azure-vm/docker-compose.prod.yml logs -f --tail=100 backend
EOF
chmod +x ~/view_logs.sh

log_info "Utility scripts created in home directory"

# =============================================================================
# Step 11: Setup Cron Jobs
# =============================================================================
log_info "Setting up cron jobs..."
(crontab -l 2>/dev/null || echo "") | grep -v "check_health.sh" | grep -v "backup_db.sh" > /tmp/crontab.tmp
echo "*/5 * * * * $HOME/check_health.sh" >> /tmp/crontab.tmp
echo "0 2 * * * $HOME/backup_db.sh" >> /tmp/crontab.tmp
crontab /tmp/crontab.tmp
rm /tmp/crontab.tmp
log_info "Cron jobs configured"

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "============================================================================="
echo -e "${GREEN}Setup Complete!${NC}"
echo "============================================================================="
echo ""
echo "Next steps:"
echo "  1. Clone your repository:"
echo "     git clone https://github.com/YOUR_USERNAME/Momentum.git ~/Momentum"
echo ""
echo "  2. Edit the environment file with your credentials:"
echo "     nano ~/Momentum/.env"
echo ""
echo "  3. Start the application:"
echo "     ~/start_momentum.sh"
echo ""
echo "Utility scripts available:"
echo "  ~/start_momentum.sh  - Start the application"
echo "  ~/stop_momentum.sh   - Stop the application"
echo "  ~/view_logs.sh       - View application logs"
echo "  ~/backup_db.sh       - Manual database backup"
echo "  ~/check_health.sh    - Check application health"
echo ""
echo -e "${YELLOW}IMPORTANT: You need to logout and login again for Docker permissions!${NC}"
echo "============================================================================="
