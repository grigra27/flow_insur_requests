# Руководство по устранению проблем HTTPS

Данное руководство поможет диагностировать и решить проблемы, связанные с HTTPS на доменах insflow.ru в системе страховых заявок.

## 🚨 Быстрая диагностика

### Проверочный скрипт

```bash
#!/bin/bash
# Быстрая диагностика HTTPS проблем

echo "🔍 HTTPS Troubleshooting for insflow.ru domains"
echo "================================================"

DOMAINS=("insflow.ru" "zs.insflow.ru" "insflow.tw1.su" "zs.insflow.tw1.su")
SERVER_IP=$(curl -s -4 ifconfig.me)

echo "📍 Server IP: $SERVER_IP"
echo ""

# 1. DNS проверка
echo "🌐 DNS Resolution Check:"
for domain in "${DOMAINS[@]}"; do
    IP=$(dig +short $domain A | head -1)
    if [ "$IP" = "$SERVER_IP" ]; then
        echo "✅ $domain -> $IP (OK)"
    else
        echo "❌ $domain -> $IP (Expected: $SERVER_IP)"
    fi
done
echo ""

# 2. Проверка портов
echo "🔌 Port Connectivity Check:"
for port in 80 443; do
    if nc -z -w3 $SERVER_IP $port 2>/dev/null; then
        echo "✅ Port $port is open"
    else
        echo "❌ Port $port is closed or filtered"
    fi
done
echo ""

# 3. SSL сертификаты
echo "🔐 SSL Certificate Check:"
for domain in "${DOMAINS[@]}"; do
    if echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null; then
        EXPIRY=$(echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
        echo "✅ $domain: Certificate valid until $EXPIRY"
    else
        echo "❌ $domain: SSL certificate issue"
    fi
done
echo ""

# 4. HTTP/HTTPS ответы
echo "🌍 HTTP Response Check:"
for domain in "${DOMAINS[@]}"; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://$domain/ --max-time 10)
    HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://$domain/ --max-time 10)
    echo "$domain: HTTP=$HTTP_CODE, HTTPS=$HTTPS_CODE"
done
```

## 🔧 Категории проблем

### 1. DNS проблемы

#### Симптомы:
- Домен не разрешается в IP
- Неправильный IP адрес
- Intermittent connectivity

#### Диагностика:
```bash
# Проверка DNS записей
dig insflow.ru A
dig zs.insflow.ru A

# Проверка с разных DNS серверов
dig @8.8.8.8 insflow.ru A
dig @1.1.1.1 insflow.ru A
dig @208.67.222.222 insflow.ru A

# Проверка распространения DNS
nslookup insflow.ru
host insflow.ru

# Трассировка DNS запросов
dig +trace insflow.ru A
```

#### Решения:
```bash
# 1. Проверьте настройки DNS у провайдера
# 2. Очистите локальный DNS кэш
sudo systemctl flush-dns  # Linux
sudo dscacheutil -flushcache  # macOS
ipconfig /flushdns  # Windows

# 3. Проверьте TTL записей
dig insflow.ru A +noall +answer

# 4. Используйте альтернативные DNS серверы
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

### 2. SSL сертификат проблемы

#### Симптомы:
- "Certificate not trusted"
- "Certificate expired"
- "Certificate name mismatch"
- "SSL handshake failed"

#### Диагностика:
```bash
# Проверка сертификата
openssl s_client -servername insflow.ru -connect insflow.ru:443 -showcerts

# Проверка срока действия
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates

# Проверка цепочки сертификатов
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -issuer -subject

# Проверка локальных сертификатов
sudo certbot certificates
sudo ls -la /etc/letsencrypt/live/
```

#### Решения:

**Истекший сертификат:**
```bash
# Принудительное обновление
sudo certbot renew --force-renewal

# Проверка автообновления
sudo certbot renew --dry-run

# Перезапуск Nginx
sudo systemctl reload nginx
# или для Docker
docker-compose -f docker-compose.yml restart nginx
```

**Неправильный сертификат:**
```bash
# Удаление старого сертификата
sudo certbot delete --cert-name insflow.ru

# Получение нового сертификата
sudo certbot --nginx -d insflow.ru -d zs.insflow.ru
```

**Проблемы с цепочкой:**
```bash
# Проверка конфигурации Nginx
sudo nginx -t

# Проверка путей к сертификатам в конфигурации
grep -r "ssl_certificate" /etc/nginx/
grep -r "ssl_certificate" ./nginx-timeweb/
```

### 3. Nginx конфигурация

#### Симптомы:
- 502 Bad Gateway
- 504 Gateway Timeout
- Неправильные перенаправления
- Mixed content warnings

#### Диагностика:
```bash
# Проверка синтаксиса конфигурации
sudo nginx -t

# Проверка статуса Nginx
sudo systemctl status nginx

# Проверка логов
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Для Docker
docker-compose -f docker-compose.yml logs nginx
```

#### Решения:

**Исправление конфигурации:**
```nginx
# nginx-timeweb/default-https.conf
server {
    listen 80;
    server_name insflow.ru zs.insflow.ru insflow.tw1.su zs.insflow.tw1.su;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name insflow.ru zs.insflow.ru insflow.tw1.su zs.insflow.tw1.su;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/insflow.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/insflow.ru/privkey.pem;
    
    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Domain routing logic here...
}
```

**Перезапуск сервисов:**
```bash
# Обычная установка
sudo systemctl reload nginx

# Docker
docker-compose -f docker-compose.yml restart nginx
```

### 4. Django HTTPS настройки

#### Симптомы:
- Mixed content warnings
- Insecure cookies
- CSRF token errors
- Redirect loops

#### Диагностика:
```bash
# Проверка переменных окружения
env | grep -E "(SECURE_|SESSION_|CSRF_)"

# Проверка Django настроек
python manage.py shell
>>> from django.conf import settings
>>> print(settings.SECURE_SSL_REDIRECT)
>>> print(settings.SESSION_COOKIE_SECURE)
>>> print(settings.CSRF_COOKIE_SECURE)
```

#### Решения:

**Правильные настройки Django:**
```python
# settings.py
if os.getenv('HTTPS_ENABLED', 'False').lower() == 'true':
    # HTTPS settings
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'SAMEORIGIN'
```

**Переменные окружения:**
```bash
# .env или docker-compose.yml
HTTPS_ENABLED=True
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### 5. Firewall и сетевые проблемы

#### Симптомы:
- Connection timeout
- Connection refused
- Intermittent connectivity

#### Диагностика:
```bash
# Проверка открытых портов
sudo netstat -tlnp | grep -E ':80|:443'
sudo ss -tlnp | grep -E ':80|:443'

# Проверка firewall
sudo ufw status verbose
sudo iptables -L -n

# Проверка подключения
telnet insflow.ru 80
telnet insflow.ru 443
nc -zv insflow.ru 80
nc -zv insflow.ru 443
```

#### Решения:

**Настройка UFW:**
```bash
# Разрешить HTTP и HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

**Настройка iptables:**
```bash
# Разрешить входящие соединения
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4
```

### 6. Docker специфичные проблемы

#### Симптомы:
- Контейнеры не запускаются
- Volume mount errors
- Network connectivity issues

#### Диагностика:
```bash
# Проверка статуса контейнеров
docker-compose -f docker-compose.yml ps

# Проверка логов
docker-compose -f docker-compose.yml logs nginx
docker-compose -f docker-compose.yml logs web

# Проверка сетей
docker network ls
docker network inspect <network_name>

# Проверка volumes
docker volume ls
docker volume inspect <volume_name>
```

#### Решения:

**Перезапуск сервисов:**
```bash
# Полный перезапуск
docker-compose -f docker-compose.yml down
docker-compose -f docker-compose.yml up -d

# Пересборка образов
docker-compose -f docker-compose.yml build --no-cache
docker-compose -f docker-compose.yml up -d
```

**Проверка volumes:**
```bash
# Проверка монтирования SSL сертификатов
docker-compose -f docker-compose.yml exec nginx ls -la /etc/letsencrypt/live/

# Исправление прав доступа
sudo chown -R root:root /etc/letsencrypt/
sudo chmod -R 755 /etc/letsencrypt/
```

## 🔍 Специфичные сценарии

### Сценарий 1: "Сайт недоступен по HTTPS"

**Шаги диагностики:**
1. Проверьте DNS: `dig insflow.ru A`
2. Проверьте порт 443: `nc -zv insflow.ru 443`
3. Проверьте сертификат: `openssl s_client -connect insflow.ru:443`
4. Проверьте Nginx: `docker-compose logs nginx`

### Сценарий 2: "Mixed content warnings"

**Причины и решения:**
```html
<!-- Неправильно: -->
<script src="http://example.com/script.js"></script>
<img src="http://example.com/image.jpg">

<!-- Правильно: -->
<script src="https://example.com/script.js"></script>
<img src="https://example.com/image.jpg">
<!-- или protocol-relative: -->
<script src="//example.com/script.js"></script>
```

**Django настройки:**
```python
# settings.py
if HTTPS_ENABLED:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_TLS = True
```

### Сценарий 3: "Redirect loop"

**Причины:**
- Неправильная конфигурация Nginx
- Конфликт между Nginx и Django redirects
- Проблемы с proxy headers

**Решение:**
```nginx
# nginx конфигурация
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header Host $http_host;
```

### Сценарий 4: "Certificate chain issues"

**Диагностика:**
```bash
# Проверка цепочки сертификатов
echo | openssl s_client -connect insflow.ru:443 -showcerts

# Проверка с SSL Labs
curl -s "https://api.ssllabs.com/api/v3/analyze?host=insflow.ru"
```

**Решение:**
```bash
# Использование fullchain.pem вместо cert.pem
ssl_certificate /etc/letsencrypt/live/insflow.ru/fullchain.pem;
```

## 📊 Мониторинг и алерты

### Скрипт мониторинга HTTPS

```bash
#!/bin/bash
# scripts/monitor-https-health.sh

DOMAINS=("insflow.ru" "zs.insflow.ru" "insflow.tw1.su" "zs.insflow.tw1.su")
LOG_FILE="/var/log/https-monitoring.log"
ALERT_THRESHOLD=7  # дней до истечения сертификата

for domain in "${DOMAINS[@]}"; do
    echo "$(date): Checking $domain..." >> $LOG_FILE
    
    # Проверка доступности HTTPS
    if curl -s -f -m 10 https://$domain/ > /dev/null; then
        echo "$(date): ✅ $domain HTTPS OK" >> $LOG_FILE
    else
        echo "$(date): ❌ $domain HTTPS FAILED" >> $LOG_FILE
        # Отправка алерта
    fi
    
    # Проверка срока действия сертификата
    EXPIRY=$(echo | openssl s_client -servername $domain -connect $domain:443 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    if [ ! -z "$EXPIRY" ]; then
        EXPIRY_TIMESTAMP=$(date -d "$EXPIRY" +%s)
        CURRENT_TIMESTAMP=$(date +%s)
        DAYS_LEFT=$(( ($EXPIRY_TIMESTAMP - $CURRENT_TIMESTAMP) / 86400 ))
        
        if [ $DAYS_LEFT -le $ALERT_THRESHOLD ]; then
            echo "$(date): ⚠️ $domain certificate expires in $DAYS_LEFT days!" >> $LOG_FILE
        fi
    fi
done
```

### Настройка алертов

```bash
# Добавление в crontab (проверка каждые 15 минут)
*/15 * * * * /opt/insflow-system/scripts/monitor-https-health.sh

# Настройка email уведомлений
# Установка mailutils
sudo apt install mailutils

# Отправка алерта
echo "HTTPS issue detected on insflow.ru" | mail -s "HTTPS Alert" admin@insflow.ru
```

## 📝 Чек-лист устранения проблем

### Базовая проверка:
- [ ] DNS записи настроены правильно
- [ ] Порты 80 и 443 открыты
- [ ] SSL сертификаты действительны
- [ ] Nginx конфигурация корректна
- [ ] Django HTTPS настройки включены

### Продвинутая диагностика:
- [ ] SSL Labs тест пройден (A+ рейтинг)
- [ ] Нет mixed content warnings
- [ ] HSTS заголовки настроены
- [ ] Автообновление сертификатов работает
- [ ] Мониторинг настроен

### Производительность:
- [ ] SSL session caching включен
- [ ] HTTP/2 активирован
- [ ] Gzip сжатие работает через HTTPS
- [ ] Static files кэшируются правильно

## 🆘 Экстренное восстановление

### Быстрый откат к HTTP

```bash
# 1. Отключение SSL redirect в Django
export HTTPS_ENABLED=False

# 2. Временная HTTP конфигурация Nginx
cp nginx-timeweb/default.conf nginx-timeweb/default-https.conf.backup
cp nginx-timeweb/default-http-only.conf nginx-timeweb/default.conf

# 3. Перезапуск сервисов
docker-compose -f docker-compose.yml restart nginx web
```

### Контакты для поддержки

- **Timeweb Support:** https://timeweb.com/ru/help/
- **Let's Encrypt Community:** https://community.letsencrypt.org/
- **Nginx Documentation:** https://nginx.org/en/docs/

## 🔗 Полезные инструменты

- **SSL Labs Test:** https://www.ssllabs.com/ssltest/
- **Security Headers:** https://securityheaders.com/
- **Certificate Transparency:** https://crt.sh/
- **DNS Checker:** https://dnschecker.org/
- **HTTP Status Checker:** https://httpstatus.io/