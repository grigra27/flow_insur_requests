# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    wget \
    curl \
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

# Создаем необходимые директории
RUN mkdir -p logs media staticfiles

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