# Azure VM Deployment Guide for Momentum Trading System

This guide walks you through deploying the Momentum Trading System on an Azure Virtual Machine.

## Prerequisites

1. **Azure Account** with an active subscription
2. **Azure CLI** installed locally (`az` command)
3. **SSH key pair** for VM access
4. **Zerodha Kite API credentials** (API Key, API Secret)

---

## Quick Start

```bash
# 1. Login to Azure
az login

# 2. Create resource group
az group create --name momentum-rg --location eastus

# 3. Create VM (Ubuntu 22.04 LTS)
az vm create \
  --resource-group momentum-rg \
  --name momentum-vm \
  --image Ubuntu2204 \
  --size Standard_B2s \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard

# 4. Open required ports
az vm open-port --resource-group momentum-rg --name momentum-vm --port 8000 --priority 1001
az vm open-port --resource-group momentum-rg --name momentum-vm --port 22 --priority 1000

# 5. Get public IP
az vm show -d -g momentum-rg -n momentum-vm --query publicIps -o tsv
```

---

## Detailed Setup Steps

### Step 1: Create Azure Resources

#### Option A: Using Azure CLI

```bash
# Set variables
RESOURCE_GROUP="momentum-rg"
VM_NAME="momentum-vm"
LOCATION="eastus"  # Choose: eastus, westus2, centralindia, etc.

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create VM with Ubuntu 22.04
az vm create \
  --resource-group $RESOURCE_GROUP \
  --name $VM_NAME \
  --image Ubuntu2204 \
  --size Standard_B2s \
  --admin-username azureuser \
  --generate-ssh-keys \
  --os-disk-size-gb 30 \
  --public-ip-sku Standard

# Open ports for application
az vm open-port --resource-group $RESOURCE_GROUP --name $VM_NAME --port 8000 --priority 1001
az vm open-port --resource-group $RESOURCE_GROUP --name $VM_NAME --port 80 --priority 1002
az vm open-port --resource-group $RESOURCE_GROUP --name $VM_NAME --port 443 --priority 1003
```

#### Option B: Using Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Click **Create a resource** → **Virtual Machine**
3. Configure:
   - **Resource Group**: Create new or select existing
   - **VM Name**: `momentum-vm`
   - **Region**: Select nearest to your location
   - **Image**: Ubuntu Server 22.04 LTS
   - **Size**: Standard_B2s (2 vCPUs, 4GB RAM) - minimum recommended
   - **Authentication**: SSH public key
   - **Inbound ports**: SSH (22)
4. Review and Create

### Step 2: Connect to VM

```bash
# Get public IP address
PUBLIC_IP=$(az vm show -d -g momentum-rg -n momentum-vm --query publicIps -o tsv)

# SSH into VM
ssh azureuser@$PUBLIC_IP
```

### Step 3: Install Docker & Docker Compose on VM

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group (logout/login required after)
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify installation
docker --version
docker-compose --version

# IMPORTANT: Logout and login again for group changes to take effect
exit
```

### Step 4: Clone and Configure Application

```bash
# SSH back into VM
ssh azureuser@<PUBLIC_IP>

# Clone repository
git clone https://github.com/<your-username>/Momentum.git
cd Momentum

# Create environment file
cat > .env << 'EOF'
# Zerodha Kite API Credentials
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_REDIRECT_URL=http://<your-vm-public-ip>:8000/callback
KITE_ACCESS_TOKEN=

# Database
DATABASE_URL=postgresql://appuser:secret@postgres:5432/appdb
REDIS_URL=redis://redis:6379/0

# Application
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF

# Edit with your actual credentials
nano .env
```

### Step 5: Deploy Application

```bash
# Build and start all services
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
```

### Step 6: Verify Deployment

```bash
# Check if services are running
docker-compose ps

# Test health endpoint
curl http://localhost:8000/health

# Check from outside (use your public IP)
curl http://<PUBLIC_IP>:8000/health
```

---

## Production Configuration

### docker-compose.prod.yml

Create a production-optimized compose file:

```yaml
version: "3.8"

services:
  redis:
    image: redis:7-alpine
    restart: always
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

  postgres:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-appdb}
      POSTGRES_USER: ${POSTGRES_USER:-appuser}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-secret}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pg-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser -d appdb"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
      target: production
    restart: always
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql://${POSTGRES_USER:-appuser}:${POSTGRES_PASSWORD:-secret}@postgres:5432/${POSTGRES_DB:-appdb}
      - KITE_API_KEY=${KITE_API_KEY}
      - KITE_API_SECRET=${KITE_API_SECRET}
      - KITE_REDIRECT_URL=${KITE_REDIRECT_URL}
      - KITE_ACCESS_TOKEN=${KITE_ACCESS_TOKEN}
      - ENVIRONMENT=production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  redis-data:
  pg-data:
```

### Deploy with Production Config

```bash
# Use production compose file
docker-compose -f docker-compose.prod.yml up -d --build
```

---

## Security Hardening

### 1. Configure Firewall (UFW)

```bash
# Enable UFW
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow application port
sudo ufw allow 8000/tcp

# Optional: Allow HTTPS if using SSL
sudo ufw allow 443/tcp

# Check status
sudo ufw status
```

### 2. Configure Azure Network Security Group

```bash
# Create NSG rules (more restrictive)
az network nsg rule create \
  --resource-group momentum-rg \
  --nsg-name momentum-vmNSG \
  --name AllowSSH \
  --priority 100 \
  --source-address-prefixes <YOUR-IP>/32 \
  --destination-port-ranges 22 \
  --access Allow \
  --protocol Tcp

az network nsg rule create \
  --resource-group momentum-rg \
  --nsg-name momentum-vmNSG \
  --name AllowApp \
  --priority 110 \
  --destination-port-ranges 8000 \
  --access Allow \
  --protocol Tcp
```

### 3. Set Up SSL with Nginx (Recommended)

```bash
# Install Nginx
sudo apt install nginx -y

# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Configure Nginx as reverse proxy
sudo nano /etc/nginx/sites-available/momentum
```

Add this Nginx config:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/momentum /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate (requires domain)
sudo certbot --nginx -d your-domain.com
```

---

## Systemd Service (Alternative to Docker Compose)

If you prefer running without Docker:

### /etc/systemd/system/momentum.service

```ini
[Unit]
Description=Momentum Trading System
After=network.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/Momentum
Environment=PATH=/home/azureuser/.pyenv/versions/3.13.0/bin:/usr/local/bin:/usr/bin
EnvironmentFile=/home/azureuser/Momentum/.env
ExecStart=/home/azureuser/.pyenv/versions/3.13.0/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable momentum
sudo systemctl start momentum

# Check status
sudo systemctl status momentum
```

---

## Monitoring & Maintenance

### Log Management

```bash
# View application logs
docker-compose logs -f backend

# View specific number of lines
docker-compose logs --tail=100 backend

# Save logs to file
docker-compose logs backend > backend.log
```

### Health Checks

```bash
# Create monitoring script
cat > ~/check_health.sh << 'EOF'
#!/bin/bash
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$HEALTH" != "200" ]; then
    echo "$(date): Health check failed with code $HEALTH" >> /var/log/momentum-health.log
    docker-compose -f /home/azureuser/Momentum/docker-compose.yml restart backend
fi
EOF

chmod +x ~/check_health.sh

# Add to crontab (every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * /home/azureuser/check_health.sh") | crontab -
```

### Backup Database

```bash
# Create backup script
cat > ~/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/azureuser/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

docker exec -t momentum_postgres_1 pg_dump -U appuser appdb > $BACKUP_DIR/db_backup_$TIMESTAMP.sql

# Keep only last 7 days of backups
find $BACKUP_DIR -name "db_backup_*.sql" -mtime +7 -delete
EOF

chmod +x ~/backup_db.sh

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /home/azureuser/backup_db.sh") | crontab -
```

---

## Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   sudo lsof -i :8000
   sudo kill -9 <PID>
   ```

2. **Docker permission denied**
   ```bash
   sudo usermod -aG docker $USER
   # Then logout and login again
   ```

3. **Cannot connect to application**
   - Check Azure NSG rules
   - Check UFW status: `sudo ufw status`
   - Verify application is running: `docker-compose ps`

4. **Database connection issues**
   ```bash
   docker-compose logs postgres
   docker exec -it momentum_postgres_1 psql -U appuser -d appdb
   ```

5. **Out of memory**
   ```bash
   # Check memory usage
   free -m
   docker stats
   
   # Consider upgrading VM size
   az vm resize --resource-group momentum-rg --name momentum-vm --size Standard_B2ms
   ```

---

## Cost Optimization

### VM Size Recommendations

| Size | vCPUs | RAM | Cost (approx) | Use Case |
|------|-------|-----|---------------|----------|
| Standard_B1s | 1 | 1GB | ~$7/month | Testing only |
| Standard_B2s | 2 | 4GB | ~$30/month | **Recommended** |
| Standard_B2ms | 2 | 8GB | ~$60/month | Heavy workloads |
| Standard_D2s_v3 | 2 | 8GB | ~$70/month | Production |

### Auto-shutdown (Dev/Test)

```bash
# Set auto-shutdown at 7 PM IST daily
az vm auto-shutdown \
  --resource-group momentum-rg \
  --name momentum-vm \
  --time 1330 \
  --timezone "UTC"
```

---

## Quick Reference Commands

```bash
# Start application
docker-compose up -d

# Stop application
docker-compose down

# Restart application
docker-compose restart

# View logs
docker-compose logs -f

# Update application
git pull
docker-compose up -d --build

# SSH tunnel for local access
ssh -L 8000:localhost:8000 azureuser@<PUBLIC_IP>
```

---

## Next Steps

1. Set up **Azure DNS** for custom domain
2. Configure **Azure Backup** for VM
3. Set up **Azure Monitor** alerts
4. Consider **Azure Container Apps** for managed containers
5. Implement **CI/CD with GitHub Actions** for automated deployments
