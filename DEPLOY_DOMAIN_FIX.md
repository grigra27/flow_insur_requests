# Деплой исправления маршрутизации доменов

## Быстрая инструкция

### 1. Проверить изменения
```bash
# Проверить nginx конфигурацию
cat nginx-timeweb/default-https.conf | grep "server_name"

# Проверить docker-compose
grep -A2 -B2 "MAIN_DOMAINS\|SUBDOMAINS" docker-compose.timeweb.yml
```

### 2. Деплой через GitHub Actions
Просто сделайте push в main ветку - GitHub Actions автоматически задеплоит изменения.

### 3. Ручной деплой (если нужно)
```bash
# На сервере Timeweb
cd /path/to/project

# Остановить контейнеры
docker-compose -f docker-compose.timeweb.yml down

# Обновить код
git pull origin main

# Запустить с новой конфигурацией
docker-compose -f docker-compose.timeweb.yml up -d

# Проверить статус
docker-compose -f docker-compose.timeweb.yml ps
```

### 4. Проверить результат
```bash
# Локально (если есть доступ к серверу)
./test_domain_routing.sh

# Или вручную в браузере:
# https://insflow.ru - должен показать лендинг
# https://zs.insflow.ru - должен показать Django приложение
# https://insflow.tw1.su - должен показать лендинг
# https://zs.insflow.tw1.su - должен показать Django приложение
```

## Что изменилось

- ✅ Nginx конфигурация разделена на 4 отдельных server блока
- ✅ Добавлены переменные окружения MAIN_DOMAINS и SUBDOMAINS
- ✅ Django маршрутизация уже была настроена правильно

## Ожидаемый результат

После деплоя:
- **insflow.ru** и **insflow.tw1.su** → лендинг-страница
- **zs.insflow.ru** и **zs.insflow.tw1.su** → Django приложение