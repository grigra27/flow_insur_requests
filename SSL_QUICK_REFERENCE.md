# 🔒 SSL Quick Reference - Быстрая справка

## 📋 Основные команды

### Проверка сертификатов
```bash
# Срок действия сертификата
docker compose exec certbot openssl x509 -in /etc/letsencrypt/live/insflow.ru/cert.pem -noout -dates

# Проверка через HTTPS
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates

# Полная проверка всех сертификатов
./scripts/ssl/check-certificates.sh
```

### Статус контейнеров
```bash
# Все контейнеры
docker compose ps

# Только certbot
docker compose ps certbot

# Только nginx
docker compose ps nginx
```

### Логи
```bash
# Логи certbot
docker compose logs certbot --tail=50

# Логи hook-скрипта
docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log

# Логи nginx
docker compose logs nginx --tail=30
```

### Тестирование
```bash
# Dry-run обновления
docker compose exec certbot certbot renew --dry-run --deploy-hook /usr/local/bin/renew-hook.sh

# Ручной запуск hook
docker compose exec certbot /usr/local/bin/renew-hook.sh

# Проверка HTTPS
curl -I https://insflow.ru
```

### Перезапуск
```bash
# Перезапуск nginx
docker compose restart nginx

# Перезапуск certbot
docker compose --profile ssl restart certbot

# Полный перезапуск
docker compose --profile ssl down
docker compose --profile ssl up -d
```

## 🚨 Экстренные действия

### Сертификат истёк
```bash
# 1. Принудительное обновление
docker compose exec certbot certbot renew --force-renewal --deploy-hook /usr/local/bin/renew-hook.sh

# 2. Перезапуск nginx
docker compose restart nginx

# 3. Проверка
curl -I https://insflow.ru
```

### Nginx показывает старый сертификат
```bash
# Просто перезапустите nginx
docker compose restart nginx

# Проверьте, что новый сертификат загружен
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates
```

### Hook не работает
```bash
# 1. Проверьте скрипт
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh

# 2. Сделайте исполняемым
docker compose exec certbot chmod +x /usr/local/bin/renew-hook.sh

# 3. Проверьте Docker socket
docker compose exec certbot ls -la /var/run/docker.sock

# 4. Пересоздайте контейнер
docker compose --profile ssl stop certbot
docker compose --profile ssl rm -f certbot
docker compose --profile ssl up -d certbot
```

## 📊 Текущий статус

| Параметр | Значение |
|----------|----------|
| Последнее обновление | 1 января 2026 |
| Срок действия | до 1 апреля 2026 |
| Следующее обновление | ~1 марта 2026 |
| Частота проверки | каждые 12 часов |
| Домены | insflow.ru, zs.insflow.ru, insflow.tw1.su, zs.insflow.tw1.su |

## 📚 Документация

- **Полная инструкция:** `SSL_AUTO_RENEWAL_SETUP.md`
- **Техническая документация:** `docs/SSL_AUTO_RENEWAL_UPDATE.md`
- **Быстрый деплой:** `DEPLOY_SSL_FIX.md`

## ✅ Чеклист здоровья системы

```bash
# Запустите эти команды для полной проверки
docker compose ps                                    # Все контейнеры работают?
docker compose logs certbot --tail=20                # Нет ошибок?
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh  # Hook на месте?
docker compose exec certbot docker --version         # Docker CLI установлен?
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates  # Сертификат актуален?
curl -I https://insflow.ru                          # HTTPS работает?
```

Если все команды выполнились успешно - система работает корректно! ✅
