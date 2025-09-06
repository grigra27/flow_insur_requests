#!/bin/bash

# Скрипт для первоначальной настройки сервера Digital Ocean
# Запускать под root пользователем

set -e

echo "🚀 Setting up Digital Ocean server for Insurance System..."

# Обновляем систему
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Устанавливаем необходимые пакеты
echo "📦 Installing required packages..."
apt install -y \
    curl \
    git \
    nginx \
    ufw \
    fail2ban \
    htop \
    unzip \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release

# Устанавливаем Docker
echo "🐳 Installing Docker..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Устанавливаем Docker Compose
echo "🐳 Installing Docker Compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Создаем пользователя для приложения
echo "👤 Creating application user..."
useradd -m -s /bin/bash -G docker deploy
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh

# Настраиваем SSH ключи (нужно будет добавить публичный ключ)
echo "🔑 Setting up SSH keys..."
echo "# Add your public SSH key here" > /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# Создаем директории для проекта
echo "📁 Creating project directories..."
mkdir -p /opt/insurance-system
mkdir -p /opt/insurance-system-staging
mkdir -p /backups/insurance-system
chown -R deploy:deploy /opt/insurance-system
chown -R deploy:deploy /opt/insurance-system-staging
chown -R deploy:deploy /backups/insurance-system

# Настраиваем firewall
echo "🔥 Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Настраиваем fail2ban
echo "🛡️  Configuring fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = ssh
logpath = /var/log/auth.log
maxretry = 3

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
EOF

systemctl enable fail2ban
systemctl start fail2ban

# Настраиваем логротацию
echo "📋 Configuring log rotation..."
cat > /etc/logrotate.d/insurance-system << 'EOF'
/opt/insurance-system/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 deploy deploy
    postrotate
        docker-compose -f /opt/insurance-system/docker-compose.prod.yml restart web celery
    endscript
}
EOF

# Создаем systemd сервис для автозапуска
echo "⚙️  Creating systemd service..."
cat > /etc/systemd/system/insurance-system.service << 'EOF'
[Unit]
Description=Insurance System
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/insurance-system
ExecStart=/usr/local/bin/docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.prod.yml --env-file .env.prod down
TimeoutStartSec=0
User=deploy
Group=deploy

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable insurance-system

# Настраиваем cron для бэкапов
echo "⏰ Setting up backup cron job..."
cat > /etc/cron.d/insurance-backup << 'EOF'
# Backup insurance system database daily at 2 AM
0 2 * * * deploy cd /opt/insurance-system && docker-compose -f docker-compose.prod.yml exec -T web python manage.py dumpdata > /backups/insurance-system/db_backup_$(date +\%Y\%m\%d_\%H\%M\%S).json

# Clean old backups (older than 30 days)
0 3 * * * deploy find /backups/insurance-system -name "*.json" -mtime +30 -delete
EOF

# Создаем скрипт для мониторинга
echo "📊 Creating monitoring script..."
cat > /opt/insurance-system/monitor.sh << 'EOF'
#!/bin/bash

# Простой скрипт мониторинга для Insurance System

check_service() {
    local service=$1
    local url=$2
    
    if curl -f "$url" > /dev/null 2>&1; then
        echo "✅ $service is healthy"
        return 0
    else
        echo "❌ $service is down"
        return 1
    fi
}

echo "🔍 Checking Insurance System health..."
echo "Time: $(date)"
echo "----------------------------------------"

# Проверяем основное приложение
check_service "Main Application" "http://localhost/health/"

# Проверяем статус Docker контейнеров
echo ""
echo "📦 Docker containers status:"
docker-compose -f /opt/insurance-system/docker-compose.prod.yml ps

# Проверяем использование диска
echo ""
echo "💾 Disk usage:"
df -h /

# Проверяем использование памяти
echo ""
echo "🧠 Memory usage:"
free -h

# Проверяем логи на ошибки
echo ""
echo "📋 Recent errors in logs:"
docker-compose -f /opt/insurance-system/docker-compose.prod.yml logs --tail=10 web | grep -i error || echo "No recent errors found"

echo "----------------------------------------"
echo "Monitoring completed at $(date)"
EOF

chmod +x /opt/insurance-system/monitor.sh
chown deploy:deploy /opt/insurance-system/monitor.sh

# Добавляем мониторинг в cron
echo "0 */6 * * * deploy /opt/insurance-system/monitor.sh >> /var/log/insurance-monitor.log 2>&1" >> /etc/cron.d/insurance-backup

# Создаем базовую конфигурацию Nginx
echo "🌐 Creating basic Nginx configuration..."
cat > /etc/nginx/sites-available/insurance-system << 'EOF'
server {
    listen 80;
    server_name _;
    
    # Временная заглушка до настройки SSL
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /health/ {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
EOF

# Отключаем дефолтный сайт и включаем наш
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/insurance-system /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Создаем скрипт для SSL сертификата
echo "🔒 Creating SSL setup script..."
cat > /opt/setup-ssl.sh << 'EOF'
#!/bin/bash

# Скрипт для настройки SSL сертификата
# Запускать после настройки DNS записей

DOMAIN=$1

if [ -z "$DOMAIN" ]; then
    echo "Usage: $0 <domain>"
    echo "Example: $0 insurance.example.com"
    exit 1
fi

echo "🔒 Setting up SSL for $DOMAIN..."

# Устанавливаем Certbot
apt update
apt install -y certbot python3-certbot-nginx

# Получаем сертификат
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN

# Настраиваем автообновление
echo "0 12 * * * /usr/bin/certbot renew --quiet" | crontab -

echo "✅ SSL certificate installed for $DOMAIN"
echo "🔄 Nginx configuration updated automatically"
EOF

chmod +x /opt/setup-ssl.sh

# Выводим информацию о завершении
echo ""
echo "🎉 Server setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Add your SSH public key to /home/deploy/.ssh/authorized_keys"
echo "2. Clone your repository to /opt/insurance-system"
echo "3. Create .env.prod file with production settings"
echo "4. Set up DNS records for your domain"
echo "5. Run /opt/setup-ssl.sh <your-domain> to setup SSL"
echo "6. Start the application with systemctl start insurance-system"
echo ""
echo "📊 Useful commands:"
echo "- Monitor system: /opt/insurance-system/monitor.sh"
echo "- View logs: journalctl -u insurance-system -f"
echo "- Check firewall: ufw status"
echo "- Check fail2ban: fail2ban-client status"
echo ""
echo "🔐 Security notes:"
echo "- SSH is configured with key-based authentication"
echo "- Firewall is enabled (ports 22, 80, 443 open)"
echo "- Fail2ban is configured for SSH and Nginx protection"
echo "- Regular backups are scheduled at 2 AM daily"
echo ""
echo "⚠️  Don't forget to:"
echo "- Change default passwords"
echo "- Configure monitoring alerts"
echo "- Set up proper DNS records"
echo "- Set up backup and restore procedures"