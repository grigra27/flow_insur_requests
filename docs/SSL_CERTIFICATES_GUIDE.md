# Руководство по SSL сертификатам для insflow.ru

Данное руководство описывает процесс получения, настройки и обновления SSL сертификатов Let's Encrypt для доменов insflow.ru на хостинге Timeweb.

## 📋 Обзор

Система использует SSL сертификаты Let's Encrypt для обеспечения HTTPS соединений на всех четырех доменах:
- insflow.ru
- zs.insflow.ru  
- insflow.tw1.su
- zs.insflow.tw1.su

## 🔧 Предварительные требования

### 1. Установка Certbot

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Certbot и плагина для Nginx
sudo apt install certbot python3-certbot-nginx -y

# Проверка установки
certbot --version
```

### 2. Проверка DNS записей

Убедитесь, что DNS записи настроены и распространились:

```bash
# Проверка всех доменов
for domain in insflow.ru zs.insflow.ru insflow.tw1.su zs.insflow.tw1.su; do
    echo "Checking $domain:"
    dig +short $domain A
    echo "---"
done
```

### 3. Проверка доступности портов

```bash
# Проверка портов 80 и 443
sudo netstat -tlnp | grep -E ':80|:443'

# Убедитесь, что Nginx запущен
sudo systemctl status nginx
```

## 🚀 Получение SSL сертификатов

### Метод 1: Автоматическая настройка с Nginx

```bash
# Получение сертификата для основных доменов
sudo certbot --nginx \
  -d insflow.ru \
  -d zs.insflow.ru \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive \
  --redirect

# Получение сертификата для технических доменов
sudo certbot --nginx \
  -d insflow.tw1.su \
  -d zs.insflow.tw1.su \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive \
  --redirect
```

### Метод 2: Ручная настройка (только получение сертификата)

```bash
# Получение сертификата без автоматической настройки Nginx
sudo certbot certonly --nginx \
  -d insflow.ru \
  -d zs.insflow.ru \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive

sudo certbot certonly --nginx \
  -d insflow.tw1.su \
  -d zs.insflow.tw1.su \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive
```

### Метод 3: Webroot (для Docker окружения)

```bash
# Создание webroot директории
sudo mkdir -p /var/www/certbot

# Получение сертификата через webroot
sudo certbot certonly --webroot \
  -w /var/www/certbot \
  -d insflow.ru \
  -d zs.insflow.ru \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive

sudo certbot certonly --webroot \
  -w /var/www/certbot \
  -d insflow.tw1.su \
  -d zs.insflow.tw1.su \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive
```

## 📁 Структура сертификатов

После успешного получения сертификаты будут расположены в:

```
/etc/letsencrypt/live/
├── insflow.ru/
│   ├── fullchain.pem    # Полная цепочка сертификатов
│   ├── privkey.pem      # Приватный ключ
│   ├── cert.pem         # Сертификат домена
│   └── chain.pem        # Промежуточные сертификаты
└── insflow.tw1.su/
    ├── fullchain.pem
    ├── privkey.pem
    ├── cert.pem
    └── chain.pem
```

### Права доступа к сертификатам

```bash
# Проверка прав доступа
sudo ls -la /etc/letsencrypt/live/*/

# Установка правильных прав (если необходимо)
sudo chmod 644 /etc/letsencrypt/live/*/fullchain.pem
sudo chmod 600 /etc/letsencrypt/live/*/privkey.pem
```

## 🔄 Автоматическое обновление сертификатов

### Настройка Cron задачи

```bash
# Открытие crontab для редактирования
sudo crontab -e

# Добавление задачи обновления (каждый день в 2:00 AM)
0 2 * * * /usr/bin/certbot renew --quiet --post-hook "systemctl reload nginx"

# Альтернативный вариант с логированием
0 2 * * * /usr/bin/certbot renew --quiet --post-hook "systemctl reload nginx" >> /var/log/certbot-renew.log 2>&1
```

### Настройка Systemd Timer (альтернатива Cron)

```bash
# Создание service файла
sudo tee /etc/systemd/system/certbot-renew.service > /dev/null <<EOF
[Unit]
Description=Certbot Renewal
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --post-hook "systemctl reload nginx"
EOF

# Создание timer файла
sudo tee /etc/systemd/system/certbot-renew.timer > /dev/null <<EOF
[Unit]
Description=Run certbot renewal twice daily
Requires=certbot-renew.service

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Активация timer
sudo systemctl daemon-reload
sudo systemctl enable certbot-renew.timer
sudo systemctl start certbot-renew.timer

# Проверка статуса
sudo systemctl status certbot-renew.timer
```

### Тестирование автообновления

```bash
# Тестовый запуск обновления (dry-run)
sudo certbot renew --dry-run

# Принудительное обновление (для тестирования)
sudo certbot renew --force-renewal
```

## 🐳 Интеграция с Docker

### Обновление docker-compose.timeweb.yml

```yaml
version: '3.8'

services:
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx-timeweb/default-https.conf:/etc/nginx/conf.d/default.conf
      - /etc/letsencrypt:/etc/letsencrypt:ro  # SSL сертификаты
      - /var/www/certbot:/var/www/certbot:ro  # Webroot для обновления
    depends_on:
      - web
    restart: unless-stopped

  certbot:
    image: certbot/certbot
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt
      - /var/www/certbot:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

### Скрипт для получения сертификатов в Docker

```bash
#!/bin/bash
# scripts/ssl/obtain-certificates.sh

set -e

echo "🔐 Obtaining SSL certificates for insflow.ru domains..."

# Создание необходимых директорий
sudo mkdir -p /etc/letsencrypt
sudo mkdir -p /var/www/certbot

# Временная конфигурация Nginx для получения сертификатов
echo "📝 Creating temporary Nginx configuration..."
sudo tee /tmp/nginx-temp.conf > /dev/null <<EOF
server {
    listen 80;
    server_name insflow.ru zs.insflow.ru insflow.tw1.su zs.insflow.tw1.su;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}
EOF

# Запуск временного Nginx контейнера
echo "🚀 Starting temporary Nginx for certificate validation..."
docker run -d --name nginx-temp \
  -p 80:80 \
  -v /tmp/nginx-temp.conf:/etc/nginx/conf.d/default.conf \
  -v /var/www/certbot:/var/www/certbot \
  nginx:1.25-alpine

# Получение сертификатов
echo "📜 Obtaining certificates for insflow.ru and zs.insflow.ru..."
docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot \
  certbot/certbot certonly --webroot \
  -w /var/www/certbot \
  -d insflow.ru \
  -d zs.insflow.ru \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive

echo "📜 Obtaining certificates for insflow.tw1.su and zs.insflow.tw1.su..."
docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot \
  certbot/certbot certonly --webroot \
  -w /var/www/certbot \
  -d insflow.tw1.su \
  -d zs.insflow.tw1.su \
  --email admin@insflow.ru \
  --agree-tos \
  --non-interactive

# Остановка временного контейнера
echo "🛑 Stopping temporary Nginx..."
docker stop nginx-temp
docker rm nginx-temp

echo "✅ SSL certificates obtained successfully!"
echo "📁 Certificates location: /etc/letsencrypt/live/"
```

## 🔍 Проверка сертификатов

### Проверка статуса сертификатов

```bash
# Список всех сертификатов
sudo certbot certificates

# Детальная информация о сертификате
sudo openssl x509 -in /etc/letsencrypt/live/insflow.ru/cert.pem -text -noout

# Проверка срока действия
sudo openssl x509 -in /etc/letsencrypt/live/insflow.ru/cert.pem -noout -enddate
sudo openssl x509 -in /etc/letsencrypt/live/insflow.tw1.su/cert.pem -noout -enddate
```

### Проверка SSL через браузер

Откройте в браузере:
- https://insflow.ru
- https://zs.insflow.ru
- https://insflow.tw1.su
- https://zs.insflow.tw1.su

Проверьте:
- ✅ Зеленый замок в адресной строке
- ✅ Сертификат выдан Let's Encrypt
- ✅ Срок действия сертификата (90 дней)

### Проверка SSL через командную строку

```bash
# Проверка SSL соединения
for domain in insflow.ru zs.insflow.ru insflow.tw1.su zs.insflow.tw1.su; do
    echo "Checking SSL for $domain:"
    echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -dates
    echo "---"
done

# Проверка SSL Labs (онлайн)
echo "Check SSL Labs rating:"
echo "https://www.ssllabs.com/ssltest/analyze.html?d=insflow.ru"
echo "https://www.ssllabs.com/ssltest/analyze.html?d=zs.insflow.ru"
```

## 🚨 Мониторинг сертификатов

### Скрипт мониторинга

```bash
#!/bin/bash
# scripts/ssl/monitor-ssl-status.sh

set -e

LOG_FILE="/var/log/ssl-monitoring.log"
ALERT_DAYS=7

echo "$(date): Starting SSL certificate monitoring..." >> $LOG_FILE

for domain in insflow.ru insflow.tw1.su; do
    CERT_FILE="/etc/letsencrypt/live/$domain/cert.pem"
    
    if [ -f "$CERT_FILE" ]; then
        # Получение даты истечения
        EXPIRY_DATE=$(openssl x509 -in "$CERT_FILE" -noout -enddate | cut -d= -f2)
        EXPIRY_TIMESTAMP=$(date -d "$EXPIRY_DATE" +%s)
        CURRENT_TIMESTAMP=$(date +%s)
        DAYS_LEFT=$(( ($EXPIRY_TIMESTAMP - $CURRENT_TIMESTAMP) / 86400 ))
        
        echo "$(date): Certificate for $domain expires in $DAYS_LEFT days" >> $LOG_FILE
        
        if [ $DAYS_LEFT -le $ALERT_DAYS ]; then
            echo "$(date): WARNING: Certificate for $domain expires in $DAYS_LEFT days!" >> $LOG_FILE
            # Отправка уведомления (настройте по необходимости)
            # curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
            #   -d "chat_id=<CHAT_ID>&text=SSL certificate for $domain expires in $DAYS_LEFT days!"
        fi
    else
        echo "$(date): ERROR: Certificate file not found for $domain" >> $LOG_FILE
    fi
done

echo "$(date): SSL certificate monitoring completed." >> $LOG_FILE
```

### Настройка мониторинга в Cron

```bash
# Добавление в crontab (проверка каждый день в 9:00)
sudo crontab -e

# Добавить строку:
0 9 * * * /opt/insflow-system/scripts/ssl/monitor-ssl-status.sh
```

## 🛠️ Troubleshooting

### Частые проблемы и решения

#### 1. Ошибка "DNS problem: NXDOMAIN"

```bash
# Проверьте DNS записи
dig insflow.ru A
dig zs.insflow.ru A

# Подождите распространения DNS (до 48 часов)
# Используйте онлайн проверку: https://dnschecker.org/
```

#### 2. Ошибка "Connection refused"

```bash
# Проверьте, что порт 80 открыт
sudo netstat -tlnp | grep :80

# Проверьте firewall
sudo ufw status
sudo iptables -L

# Временно остановите другие веб-серверы
sudo systemctl stop apache2  # если установлен
```

#### 3. Ошибка "Rate limit exceeded"

```bash
# Let's Encrypt имеет лимиты:
# - 50 сертификатов на домен в неделю
# - 5 неудачных попыток в час

# Проверьте лимиты: https://crt.sh/?q=insflow.ru
# Подождите час перед повторной попыткой
```

#### 4. Проблемы с правами доступа

```bash
# Проверьте владельца файлов сертификатов
sudo ls -la /etc/letsencrypt/live/*/

# Исправьте права доступа
sudo chown -R root:root /etc/letsencrypt/
sudo chmod -R 755 /etc/letsencrypt/
sudo chmod 600 /etc/letsencrypt/live/*/privkey.pem
```

### Логи для диагностики

```bash
# Логи Certbot
sudo tail -f /var/log/letsencrypt/letsencrypt.log

# Логи Nginx
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Системные логи
sudo journalctl -u nginx -f
sudo journalctl -u certbot-renew -f
```

## 📝 Чек-лист SSL настройки

- [ ] DNS записи настроены и распространились
- [ ] Certbot установлен на сервере
- [ ] Порты 80 и 443 открыты
- [ ] Получены сертификаты для insflow.ru и zs.insflow.ru
- [ ] Получены сертификаты для insflow.tw1.su и zs.insflow.tw1.su
- [ ] Nginx настроен для HTTPS
- [ ] Настроено автоматическое обновление сертификатов
- [ ] Проверена работа HTTPS на всех доменах
- [ ] Настроен мониторинг сертификатов
- [ ] Проверены SSL Labs рейтинги

## 🔗 Полезные ссылки

- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Certbot User Guide](https://certbot.eff.org/docs/using.html)
- [SSL Labs SSL Test](https://www.ssllabs.com/ssltest/)
- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)
- [Certificate Transparency Logs](https://crt.sh/)