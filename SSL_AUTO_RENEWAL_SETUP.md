# 🔒 Настройка автоматического перевыпуска SSL сертификатов

## 📋 Оглавление
1. [Текущая ситуация](#текущая-ситуация)
2. [Что было исправлено](#что-было-исправлено)
3. [Пошаговая инструкция](#пошаговая-инструкция)
4. [Проверка работы](#проверка-работы)
5. [Мониторинг](#мониторинг)
6. [Устранение проблем](#устранение-проблем)

---

## 🎯 Текущая ситуация

### Проблема
- ✅ Certbot успешно обновлял сертификаты (последнее обновление: 1 января 2026)
- ❌ Nginx не перезагружался после обновления и продолжал использовать старые сертификаты из памяти
- ❌ Пользователи видели истекший сертификат (31 января 2026) вместо нового (действителен до 1 апреля 2026)

### Решение
Добавлен автоматический перезапуск nginx после каждого успешного обновления сертификатов через deploy-hook в certbot.

---

## ✅ Что было исправлено

### Изменённые файлы:

1. **`docker-compose.yml`**
   - Добавлен Docker socket для управления контейнерами
   - Добавлен volume с hook-скриптом
   - Обновлена команда certbot с `--deploy-hook`
   - Добавлена установка docker-cli в контейнер certbot

2. **`scripts/ssl/certbot-renew-hook.sh`** (новый файл)
   - Автоматически находит nginx контейнер
   - Перезапускает nginx после обновления сертификатов
   - Проверяет успешность перезапуска
   - Логирует все операции

3. **Документация**
   - `docs/SSL_AUTO_RENEWAL_UPDATE.md` - подробная техническая документация
   - `SSL_AUTO_RENEWAL_SETUP.md` - эта инструкция

---

## 🚀 Пошаговая инструкция

### Вариант 1: Автоматический деплой через GitHub Actions (РЕКОМЕНДУЕТСЯ)

Ваш проект уже настроен на автоматический деплой через GitHub Actions. Просто закоммитьте изменения:

```bash
# 1. Проверьте изменения
git status

# 2. Добавьте все изменённые файлы
git add docker-compose.yml
git add scripts/ssl/certbot-renew-hook.sh
git add docs/SSL_AUTO_RENEWAL_UPDATE.md
git add SSL_AUTO_RENEWAL_SETUP.md

# 3. Закоммитьте с понятным сообщением
git commit -m "fix: Add automatic nginx restart after SSL certificate renewal

- Add deploy-hook to certbot for automatic nginx restart
- Add certbot-renew-hook.sh script for container management
- Mount Docker socket to certbot container
- Install docker-cli in certbot container for restart capability

This fixes the issue where nginx continued using old certificates
after certbot successfully renewed them."

# 4. Отправьте в main ветку
git push origin main
```

**Что произойдёт:**
1. GitHub Actions автоматически запустит workflow `deploy_timeweb.yml`
2. Соберёт новый Docker образ
3. Задеплоит на сервер Timeweb
4. Обновит docker-compose.yml на сервере
5. Перезапустит certbot с новой конфигурацией

**Время выполнения:** ~5-10 минут

---

### Вариант 2: Ручной деплой на сервере

Если нужно применить изменения немедленно без ожидания GitHub Actions:

```bash
# 1. Подключитесь к серверу
ssh user@your-server

# 2. Перейдите в директорию проекта
cd /opt/insflow-system

# 3. Загрузите последние изменения
git fetch origin main
git reset --hard origin/main

# 4. Проверьте, что файлы обновлены
ls -la scripts/ssl/certbot-renew-hook.sh
cat docker-compose.yml | grep -A10 "certbot:"

# 5. Остановите и удалите старый certbot контейнер
docker compose --profile ssl stop certbot
docker compose --profile ssl rm -f certbot

# 6. Запустите certbot с новой конфигурацией
docker compose --profile ssl up -d certbot

# 7. Проверьте статус
docker compose ps certbot
docker compose logs certbot --tail=30
```

---

## 🔍 Проверка работы

### 1. Проверка hook-скрипта в контейнере

```bash
# Проверьте, что скрипт доступен
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh

# Проверьте, что docker-cli установлен
docker compose exec certbot docker --version

# Проверьте, что Docker socket доступен
docker compose exec certbot ls -la /var/run/docker.sock
```

**Ожидаемый результат:**
```
-rw-r--r-- 1 root root 1234 Feb  2 10:00 /usr/local/bin/renew-hook.sh
Docker version 24.0.x, build xxxxx
srw-rw---- 1 root 999 0 Feb  2 10:00 /var/run/docker.sock
```

### 2. Тестирование hook-скрипта

```bash
# Запустите hook вручную для проверки
docker compose exec certbot /usr/local/bin/renew-hook.sh

# Проверьте логи hook
docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log
```

**Ожидаемый результат:**
```
2026-02-02 10:00:00 - Certificate renewal detected, restarting nginx container...
2026-02-02 10:00:00 - Found nginx container: insflow-system-nginx-1
2026-02-02 10:00:03 - SUCCESS: Nginx container restarted successfully
2026-02-02 10:00:06 - SUCCESS: Nginx is running and healthy
2026-02-02 10:00:06 - Certificate renewal hook completed successfully
```

### 3. Тест dry-run обновления

```bash
# Запустите тестовое обновление сертификатов
docker compose exec certbot certbot renew --dry-run --deploy-hook /usr/local/bin/renew-hook.sh
```

**Ожидаемый результат:**
```
Saving debug log to /var/log/letsencrypt/letsencrypt.log

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Processing /etc/letsencrypt/renewal/insflow.ru.conf
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Simulating renewal of an existing certificate for insflow.ru and zs.insflow.ru

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Congratulations, all simulated renewals succeeded:
  /etc/letsencrypt/live/insflow.ru/fullchain.pem (success)
  /etc/letsencrypt/live/insflow.tw1.su/fullchain.pem (success)
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
```

### 4. Проверка текущих сертификатов

```bash
# Проверьте срок действия сертификатов
docker compose exec certbot openssl x509 -in /etc/letsencrypt/live/insflow.ru/cert.pem -noout -dates

# Проверьте через HTTPS
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates

# Проверьте все домены
curl -I https://insflow.ru
curl -I https://zs.insflow.ru
curl -I https://insflow.tw1.su
curl -I https://zs.insflow.tw1.su
```

**Ожидаемый результат:**
```
notBefore=Jan  1 12:33:43 2026 GMT
notAfter=Apr  1 12:33:42 2026 GMT

HTTP/2 200
server: nginx/1.25.5
strict-transport-security: max-age=31536000; includeSubDomains; preload
```

---

## 📊 Мониторинг

### Автоматический мониторинг

Certbot проверяет обновления **каждые 12 часов** (43200 секунд):
- Сертификаты обновляются автоматически за **30 дней** до истечения
- После успешного обновления автоматически перезапускается nginx
- Все операции логируются

### Расписание обновлений

| Событие | Дата | Статус |
|---------|------|--------|
| Последнее обновление | 1 января 2026 | ✅ Выполнено |
| Текущий срок действия | до 1 апреля 2026 | ✅ Действителен |
| Следующее обновление | ~1 марта 2026 | ⏳ Запланировано |

### Команды для мониторинга

```bash
# 1. Проверка статуса контейнеров
docker compose ps

# 2. Логи certbot (последние обновления)
docker compose logs certbot --tail=100

# 3. Логи hook-скрипта
docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log

# 4. Логи nginx
docker compose logs nginx --tail=50

# 5. Проверка сертификатов через скрипт
./scripts/ssl/check-certificates.sh

# 6. Мониторинг SSL статуса
./scripts/ssl/monitor-ssl-status.sh
```

### Настройка алертов (опционально)

Добавьте в cron на сервере для ежедневной проверки:

```bash
# Откройте crontab
crontab -e

# Добавьте проверку сертификатов каждый день в 6:00
0 6 * * * cd /opt/insflow-system && ./scripts/ssl/check-certificates.sh --quiet || echo "SSL certificates need attention" | mail -s "SSL Alert" admin@insflow.ru
```

---

## 🔧 Устранение проблем

### Проблема 1: Hook-скрипт не выполняется

**Симптомы:**
- Certbot обновляет сертификаты
- Nginx не перезапускается
- Пользователи видят старые сертификаты

**Решение:**
```bash
# Проверьте права на скрипт
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh

# Сделайте скрипт исполняемым
docker compose exec certbot chmod +x /usr/local/bin/renew-hook.sh

# Проверьте логи
docker compose exec certbot cat /var/log/letsencrypt/renew-hook.log
```

### Проблема 2: Docker socket недоступен

**Симптомы:**
- Hook выполняется, но не может найти nginx контейнер
- Ошибка: "Cannot connect to Docker daemon"

**Решение:**
```bash
# Проверьте монтирование socket
docker compose exec certbot ls -la /var/run/docker.sock

# Если socket отсутствует, пересоздайте контейнер
docker compose --profile ssl stop certbot
docker compose --profile ssl rm -f certbot
docker compose --profile ssl up -d certbot
```

### Проблема 3: Docker CLI не установлен

**Симптомы:**
- Ошибка: "docker: command not found" в логах hook

**Решение:**
```bash
# Проверьте установку docker-cli
docker compose exec certbot docker --version

# Если не установлен, пересоздайте контейнер
docker compose --profile ssl down certbot
docker compose --profile ssl up -d certbot

# Проверьте логи установки
docker compose logs certbot | grep "docker-cli"
```

### Проблема 4: Nginx не перезапускается

**Симптомы:**
- Hook выполняется успешно
- Но nginx продолжает использовать старые сертификаты

**Решение:**
```bash
# Ручной перезапуск nginx
docker compose restart nginx

# Проверьте статус
docker compose ps nginx

# Проверьте, что новые сертификаты загружены
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates
```

### Проблема 5: Certbot не обновляет сертификаты

**Симптомы:**
- Сертификаты истекли или близки к истечению
- Certbot не запускает обновление

**Решение:**
```bash
# Принудительное обновление
docker compose exec certbot certbot renew --force-renewal --deploy-hook /usr/local/bin/renew-hook.sh

# Проверьте конфигурацию renewal
docker compose exec certbot cat /etc/letsencrypt/renewal/insflow.ru.conf

# Проверьте логи certbot
docker compose logs certbot --tail=100
```

---

## 📝 Дополнительная информация

### Как это работает

1. **Certbot контейнер** запускается с профилем `ssl`
2. Каждые **12 часов** certbot проверяет необходимость обновления
3. Если сертификат истекает через **30 дней или меньше**, certbot обновляет его
4. После успешного обновления запускается **deploy-hook** (`/usr/local/bin/renew-hook.sh`)
5. Hook-скрипт находит nginx контейнер и **перезапускает** его
6. Nginx загружает **новые сертификаты** из `/etc/letsencrypt/live/`
7. Все операции **логируются** для мониторинга

### Структура файлов

```
/opt/insflow-system/
├── docker-compose.yml                    # Обновлён: добавлен hook и Docker socket
├── scripts/ssl/
│   ├── certbot-renew-hook.sh            # НОВЫЙ: скрипт перезапуска nginx
│   ├── check-certificates.sh            # Проверка сертификатов
│   ├── monitor-ssl-status.sh            # Мониторинг SSL
│   └── renew-certificates.sh            # Ручное обновление
├── letsencrypt/                          # Volume с сертификатами
│   ├── live/
│   │   ├── insflow.ru/
│   │   │   ├── fullchain.pem
│   │   │   ├── privkey.pem
│   │   │   └── cert.pem
│   │   └── insflow.tw1.su/
│   │       ├── fullchain.pem
│   │       ├── privkey.pem
│   │       └── cert.pem
│   └── renewal/
│       ├── insflow.ru.conf
│       └── insflow.tw1.su.conf
└── docs/
    ├── SSL_AUTO_RENEWAL_UPDATE.md       # Техническая документация
    └── SSL_AUTO_RENEWAL_SETUP.md        # Эта инструкция
```

### Логи

| Лог | Расположение | Назначение |
|-----|--------------|------------|
| Certbot | `/var/log/letsencrypt/letsencrypt.log` | Основные операции certbot |
| Renewal hook | `/var/log/letsencrypt/renew-hook.log` | Операции перезапуска nginx |
| Nginx | Docker logs | Работа веб-сервера |

### Полезные ссылки

- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Certbot Documentation](https://eff-certbot.readthedocs.io/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

---

## ✅ Чеклист после установки

- [ ] Изменения закоммичены и запушены в GitHub
- [ ] GitHub Actions успешно задеплоил изменения
- [ ] Certbot контейнер запущен с новой конфигурацией
- [ ] Hook-скрипт доступен и исполняемый
- [ ] Docker CLI установлен в certbot контейнере
- [ ] Docker socket доступен в контейнере
- [ ] Dry-run тест прошёл успешно
- [ ] Текущие сертификаты действительны
- [ ] HTTPS работает на всех доменах
- [ ] Мониторинг настроен (опционально)

---

## 🎉 Готово!

После выполнения этой инструкции:
- ✅ Certbot будет автоматически обновлять сертификаты каждые 60 дней
- ✅ Nginx будет автоматически перезапускаться после обновления
- ✅ Пользователи всегда будут видеть актуальные сертификаты
- ✅ Никаких ручных действий не требуется

**Следующее автоматическое обновление:** ~1 марта 2026  
**Текущий срок действия сертификатов:** до 1 апреля 2026

---

## 📞 Поддержка

При возникновении проблем:
1. Проверьте раздел [Устранение проблем](#устранение-проблем)
2. Изучите логи: `docker compose logs certbot --tail=100`
3. Проверьте статус: `docker compose ps`
4. Запустите проверку: `./scripts/ssl/check-certificates.sh`

**Важно:** Сохраните эту инструкцию для будущих обновлений системы!
