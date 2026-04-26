# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости.
# postgresql-client пиним до 15, чтобы pg_dump писал формат, совместимый
# с pg_restore в db-контейнере (postgres:15). Без пина apt тянет последнюю
# доступную версию клиента, и формат дампа становится несовместим со старым
# сервером. Версия 15 ставится из официального PostgreSQL APT репозитория.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates gnupg lsb-release wget curl \
    && install -d /usr/share/keyrings \
    && wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg-keyring.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        postgresql-client-15 \
    && rm -rf /var/lib/apt/lists/*

# Создаем пользователя для приложения
RUN useradd --create-home --shell /bin/bash app

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn psycopg2-binary

# Копируем код приложения
COPY . .

# Создаем необходимые директории (включая backups — volume маунтится сюда,
# и без существующей в образе директории Docker создаст её под root)
RUN mkdir -p logs media staticfiles backups

# Копируем и делаем исполняемым entrypoint скрипт
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Копируем healthcheck скрипты
COPY healthcheck.py /app/healthcheck.py
COPY simple_healthcheck.py /app/simple_healthcheck.py
RUN chmod +x /app/healthcheck.py /app/simple_healthcheck.py

# Устанавливаем права на файлы
RUN chown -R app:app /app

# Переключаемся на пользователя app
USER app

# Открываем порт
EXPOSE 8000

# Устанавливаем entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Команда по умолчанию
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "onlineservice.wsgi:application"]