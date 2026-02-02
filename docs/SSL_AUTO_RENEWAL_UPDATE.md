# SSL Auto-Renewal Update

## Проблема
Certbot успешно обновлял сертификаты, но nginx продолжал использовать старые сертификаты из памяти, так как не было автоматического перезапуска после обновления.

## Решение
Обновлена конфигурация Docker Compose для автоматического перезапуска nginx после обновления сертификатов.

## Изменения

### 1. docker-compose.yml
- Добавлен volume с Docker socket для управления контейнерами
- Добавлен volume с hook-скриптом для перезапуска nginx
- Обновлена команда certbot с использованием `--deploy-hook`
- Добавлена установка docker-cli в контейнер certbot

### 2. scripts/ssl/certbot-renew-hook.sh
Новый скрипт, который:
- Автоматически находит nginx контейнер
- Перезапускает nginx после обновления сертификатов
- Проверяет успешность перезапуска
- Логирует все операции

## Развертывание на сервере

### Шаг 1: Загрузка изменений
```bash
cd /opt/insflow-system
git pull origin main
```

### Шаг 2: Проверка изменений
```bash
# Проверьте, что файлы обновлены
cat docker-compose.yml | grep -A5 "certbot:"
ls -la scripts/ssl/certbot-renew-hook.sh
```

### Шаг 3: Перезапуск certbot с новой конфигурацией
```bash
# Остановите старый certbot
docker compose --profile ssl stop certbot

# Удалите старый контейнер
docker compose --profile ssl rm -f certbot

# Запустите с новой конфигурацией
docker compose --profile ssl up -d certbot

# Проверьте логи
docker compose logs certbot --tail=20
```

### Шаг 4: Проверка работы
```bash
# Проверьте, что certbot запущен
docker compose ps certbot

# Проверьте, что скрипт доступен в контейнере
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh

# Проверьте, что docker-cli установлен
docker compose exec certbot docker --version
```

## Тестирование

### Тест 1: Dry-run обновления
```bash
# Запустите тестовое обновление
docker compose exec certbot certbot renew --dry-run --deploy-hook /usr/local/bin/renew-hook.sh
```

### Тест 2: Проверка hook-скрипта
```bash
# Запустите hook вручную для проверки
docker compose exec certbot /usr/local/bin/renew-hook.sh
```

### Тест 3: Проверка логов
```bash
# Проверьте логи hook-скрипта
docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log
```

## Мониторинг

### Проверка статуса сертификатов
```bash
# Проверьте срок действия
docker compose exec certbot openssl x509 -in /etc/letsencrypt/live/insflow.ru/cert.pem -noout -dates

# Проверьте через HTTPS
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates
```

### Проверка логов обновления
```bash
# Логи certbot
docker compose logs certbot --tail=50

# Логи hook-скрипта
docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log

# Логи nginx
docker compose logs nginx --tail=30
```

## Расписание обновления

Certbot проверяет обновления каждые 12 часов (43200 секунд):
- Сертификаты обновляются автоматически за 30 дней до истечения
- После успешного обновления автоматически перезапускается nginx
- Все операции логируются

## Устранение проблем

### Проблема: Hook не выполняется
```bash
# Проверьте права на скрипт
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh

# Проверьте, что скрипт исполняемый
docker compose exec certbot chmod +x /usr/local/bin/renew-hook.sh
```

### Проблема: Docker socket недоступен
```bash
# Проверьте монтирование socket
docker compose exec certbot ls -la /var/run/docker.sock

# Проверьте, что docker-cli установлен
docker compose exec certbot docker ps
```

### Проблема: Nginx не перезапускается
```bash
# Проверьте логи hook
docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log

# Запустите hook вручную
docker compose exec certbot /usr/local/bin/renew-hook.sh

# Проверьте статус nginx
docker compose ps nginx
```

## Откат изменений

Если возникнут проблемы, можно вернуться к старой конфигурации:

```bash
# Остановите certbot
docker compose --profile ssl stop certbot

# Откатите изменения в git
git checkout HEAD~1 docker-compose.yml

# Перезапустите certbot
docker compose --profile ssl up -d certbot
```

## Дополнительная информация

- Certbot обновляет сертификаты за 30 дней до истечения
- Текущие сертификаты действительны до 1 апреля 2026
- Следующее обновление ожидается примерно 1 марта 2026
- Hook-скрипт логирует все операции в `/var/log/letsencrypt/renew-hook.log`

## Контакты

При возникновении проблем проверьте:
1. Логи certbot: `docker compose logs certbot`
2. Логи hook: `docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log`
3. Статус контейнеров: `docker compose ps`
4. Срок действия сертификатов: `scripts/ssl/check-certificates.sh`
