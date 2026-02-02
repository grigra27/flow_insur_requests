# 🔒 SSL Auto-Renewal Fix - Исправление автоматического обновления сертификатов

## 🎯 Проблема и решение

**Проблема:** Certbot успешно обновлял SSL сертификаты, но nginx продолжал использовать старые сертификаты из памяти, так как не перезагружался после обновления.

**Решение:** Добавлен автоматический перезапуск nginx через deploy-hook в certbot после каждого успешного обновления сертификатов.

---

## 📦 Что изменилось

### Изменённые файлы:
- ✅ `docker-compose.yml` - добавлен hook и Docker socket для управления контейнерами
- ✅ `scripts/ssl/certbot-renew-hook.sh` - новый скрипт автоматического перезапуска nginx

### Новая документация:
- 📘 `SSL_AUTO_RENEWAL_SETUP.md` - **ГЛАВНАЯ ИНСТРУКЦИЯ** (читайте её!)
- 📗 `SSL_QUICK_REFERENCE.md` - быстрая справка по командам
- 📙 `DEPLOY_SSL_FIX.md` - инструкция по деплою
- 📕 `docs/SSL_AUTO_RENEWAL_UPDATE.md` - техническая документация

---

## 🚀 Что делать дальше?

### Вариант 1: Автоматический деплой (РЕКОМЕНДУЕТСЯ)

Ваш проект использует GitHub Actions для автоматического деплоя:

```bash
# 1. Закоммитьте изменения
git add .
git commit -m "fix: Add automatic nginx restart after SSL certificate renewal"
git push origin main

# 2. Дождитесь завершения GitHub Actions (~5-10 минут)
# 3. Готово! Изменения автоматически применены на сервере
```

### Вариант 2: Ручной деплой

Если нужно применить изменения немедленно:

```bash
# На сервере
cd /opt/insflow-system
git pull origin main
docker compose --profile ssl stop certbot
docker compose --profile ssl rm -f certbot
docker compose --profile ssl up -d certbot
```

---

## 📚 Документация

### Начните отсюда:
👉 **[SSL_AUTO_RENEWAL_SETUP.md](SSL_AUTO_RENEWAL_SETUP.md)** - полная пошаговая инструкция

### Дополнительно:
- **[SSL_QUICK_REFERENCE.md](SSL_QUICK_REFERENCE.md)** - быстрая справка по командам
- **[DEPLOY_SSL_FIX.md](DEPLOY_SSL_FIX.md)** - инструкция по деплою
- **[docs/SSL_AUTO_RENEWAL_UPDATE.md](docs/SSL_AUTO_RENEWAL_UPDATE.md)** - техническая документация

---

## ✅ Проверка после установки

```bash
# На сервере выполните:
docker compose ps certbot
docker compose exec certbot ls -la /usr/local/bin/renew-hook.sh
docker compose exec certbot docker --version
docker compose exec certbot certbot renew --dry-run --deploy-hook /usr/local/bin/renew-hook.sh
```

Если все команды выполнились успешно - всё работает! ✅

---

## 📊 Текущий статус сертификатов

- **Последнее обновление:** 1 января 2026
- **Срок действия:** до 1 апреля 2026 (ещё ~2 месяца)
- **Следующее обновление:** ~1 марта 2026 (автоматически)
- **Домены:** insflow.ru, zs.insflow.ru, insflow.tw1.su, zs.insflow.tw1.su

---

## 🔧 Быстрые команды

```bash
# Проверка сертификатов
echo | openssl s_client -servername insflow.ru -connect insflow.ru:443 2>/dev/null | openssl x509 -noout -dates

# Проверка HTTPS
curl -I https://insflow.ru

# Логи certbot
docker compose logs certbot --tail=50

# Перезапуск nginx (если нужно)
docker compose restart nginx
```

---

## 🎉 Результат

После применения этих изменений:
- ✅ Certbot автоматически обновляет сертификаты каждые 60 дней
- ✅ Nginx автоматически перезапускается после обновления
- ✅ Пользователи всегда видят актуальные сертификаты
- ✅ Никаких ручных действий не требуется

---

## 📞 Нужна помощь?

1. Прочитайте **[SSL_AUTO_RENEWAL_SETUP.md](SSL_AUTO_RENEWAL_SETUP.md)** - там есть раздел "Устранение проблем"
2. Проверьте логи: `docker compose logs certbot --tail=100`
3. Используйте **[SSL_QUICK_REFERENCE.md](SSL_QUICK_REFERENCE.md)** для быстрого доступа к командам

---

**Важно:** Сохраните эту документацию для будущих обновлений системы!
