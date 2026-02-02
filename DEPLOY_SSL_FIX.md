# Быстрый деплой исправления SSL Auto-Renewal

## Что исправлено
✅ Автоматический перезапуск nginx после обновления сертификатов certbot

## 🚀 Рекомендуемый способ: Автоматический деплой через GitHub Actions

Ваш проект настроен на автоматический деплой. Просто закоммитьте изменения:

```bash
# 1. Проверьте изменения
git status

# 2. Добавьте изменённые файлы
git add docker-compose.yml scripts/ssl/certbot-renew-hook.sh docs/ *.md

# 3. Закоммитьте
git commit -m "fix: Add automatic nginx restart after SSL certificate renewal"

# 4. Отправьте в main
git push origin main
```

**GitHub Actions автоматически:**
- Соберёт новый Docker образ
- Задеплоит на Timeweb
- Обновит certbot с новой конфигурацией
- Применит все изменения

**Время выполнения:** ~5-10 минут

---

## 🔧 Альтернатива: Ручной деплой на сервере

Если нужно применить изменения немедленно:

```bash
# 1. Подключитесь к серверу
ssh user@your-server

# 2. Перейдите в директорию проекта
cd /opt/insflow-system

# 3. Загрузите обновления
git fetch origin main
git reset --hard origin/main

# 4. Перезапустите certbot с новой конфигурацией
docker compose --profile ssl stop certbot
docker compose --profile ssl rm -f certbot
docker compose --profile ssl up -d certbot

# 5. Проверьте статус
docker compose ps certbot
docker compose logs certbot --tail=20

# 6. Проверьте, что hook-скрипт доступен
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh

# 7. Тест: запустите dry-run обновления
docker compose exec certbot certbot renew --dry-run --deploy-hook /usr/local/bin/renew-hook.sh
```

## Проверка работы

```bash
# Проверьте текущий сертификат
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates

# Должно показать: notAfter=Apr  1 12:33:42 2026 GMT
```

## Что изменилось

### Файлы:
- ✅ `docker-compose.yml` - добавлен автоматический перезапуск nginx
- ✅ `scripts/ssl/certbot-renew-hook.sh` - новый hook-скрипт
- ✅ `docs/SSL_AUTO_RENEWAL_UPDATE.md` - полная документация

### Как это работает:
1. Certbot обновляет сертификаты каждые 12 часов (проверка)
2. При успешном обновлении запускается hook-скрипт
3. Hook-скрипт автоматически перезапускает nginx
4. Nginx загружает новые сертификаты

## Следующее обновление
Сертификаты действительны до **1 апреля 2026**  
Автоматическое обновление произойдёт примерно **1 марта 2026**

## Если что-то пошло не так

```bash
# Откат к предыдущей версии
cd /opt/insflow-system
git checkout HEAD~1 docker-compose.yml
docker compose --profile ssl restart certbot

# Ручной перезапуск nginx (как делали сегодня)
docker compose restart nginx
```

## Подробная документация
См. `docs/SSL_AUTO_RENEWAL_UPDATE.md`
