FROM nginx:1.25-alpine

# Удалим default-конфигурацию nginx (опционально)
RUN rm /etc/nginx/conf.d/default.conf || true

# Копируем наш конфиг в контейнер
COPY default.conf /etc/nginx/conf.d/default.conf

# Создать точки монтирования (необязательно — просто для ясности)
RUN mkdir -p /app/staticfiles /app/media

# expose только если нужно (docker-compose будет пробрасывать порты)
EXPOSE 80

# Используем стандартный CMD у nginx (не нужно заменять)
