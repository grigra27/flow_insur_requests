# Исправление маршрутизации доменов на Timeweb

## Проблема

При деплое на Timeweb все домены (`insflow.ru`, `zs.insflow.ru`, `insflow.tw1.su`, `zs.insflow.tw1.su`) показывали Django приложение вместо правильной маршрутизации:

- **Главные домены** (`insflow.ru`, `insflow.tw1.su`) должны показывать лендинг-страницу
- **Поддомены** (`zs.insflow.ru`, `zs.insflow.tw1.su`) должны показывать Django приложение

## Причина

В nginx конфигурации все домены были объединены в два server блока:
```nginx
server {
    server_name insflow.ru zs.insflow.ru;  # Все домены в одном блоке
    # ...
}
server {
    server_name insflow.tw1.su zs.insflow.tw1.su;  # Все домены в одном блоке
    # ...
}
```

Это приводило к тому, что nginx не мог различить домены и все запросы проксировались на Django.

## Решение

### 1. Разделение nginx server блоков

Создали отдельные server блоки для каждого домена:

```nginx
# Главный домен insflow.ru (лендинг)
server {
    listen 443 ssl http2;
    server_name insflow.ru;
    # ... проксирование на Django (который покажет лендинг)
}

# Поддомен zs.insflow.ru (Django приложение)
server {
    listen 443 ssl http2;
    server_name zs.insflow.ru;
    # ... проксирование на Django (который покажет приложение)
}

# Главный домен insflow.tw1.su (лендинг)
server {
    listen 443 ssl http2;
    server_name insflow.tw1.su;
    # ... проксирование на Django (который покажет лендинг)
}

# Поддомен zs.insflow.tw1.su (Django приложение)
server {
    listen 443 ssl http2;
    server_name zs.insflow.tw1.su;
    # ... проксирование на Django (который покажет приложение)
}
```

### 2. Добавление переменных окружения

В `docker-compose.timeweb.yml` добавили переменные для конфигурации доменов:

```yaml
environment:
  # Domain configuration
  - MAIN_DOMAINS=${MAIN_DOMAINS:-insflow.tw1.su,insflow.ru}
  - SUBDOMAINS=${SUBDOMAINS:-zs.insflow.tw1.su,zs.insflow.ru}
```

### 3. Django маршрутизация

Django уже был правильно настроен с `domain_aware_redirect` функцией в `onlineservice/urls.py`, которая:

- Для главных доменов показывает лендинг-страницу
- Для поддоменов показывает Django приложение

## Файлы изменены

1. **nginx-timeweb/default-https.conf** - разделены server блоки
2. **deployments/timeweb/nginx/default-https.conf** - разделены server блоки  
3. **docker-compose.timeweb.yml** - добавлены переменные MAIN_DOMAINS и SUBDOMAINS

## Тестирование

Создан скрипт `test_domain_routing.sh` для проверки правильности маршрутизации:

```bash
./test_domain_routing.sh
```

Скрипт проверяет:
- Доступность всех доменов
- Правильность контента (лендинг vs Django приложение)
- Работу health endpoints

## Деплой

После внесения изменений нужно:

1. Пересобрать и перезапустить контейнеры:
```bash
docker-compose -f docker-compose.timeweb.yml down
docker-compose -f docker-compose.timeweb.yml up -d
```

2. Проверить nginx конфигурацию:
```bash
docker-compose -f docker-compose.timeweb.yml exec nginx nginx -t
```

3. Запустить тест маршрутизации:
```bash
./test_domain_routing.sh
```

## Ожидаемый результат

После исправления:
- `https://insflow.ru` → лендинг-страница
- `https://zs.insflow.ru` → Django приложение
- `https://insflow.tw1.su` → лендинг-страница  
- `https://zs.insflow.tw1.su` → Django приложение