#!/bin/bash
# ---------------------------------------------------
# Скрипт обновления Let's Encrypt сертификатов и перезапуска Docker-стека
# Автоматическое логирование и уведомления по email
# ---------------------------------------------------

# Путь к Docker Compose
DOCKER_COMPOSE_PATH="/opt/insurance-system/docker-compose.yml"

# Лог-файл
LOG_FILE="/var/log/renew_cert.log"

# Email для уведомлений
EMAIL="your-email@example.com"

echo "================ $(date '+%Y-%m-%d %H:%M:%S') ==================" >> "$LOG_FILE"
echo "Начало проверки сертификатов..." >> "$LOG_FILE"

# Проверяем и обновляем сертификаты
if sudo certbot renew --quiet --deploy-hook "docker-compose -f $DOCKER_COMPOSE_PATH exec nginx nginx -s reload"; then
    echo "Сертификаты обновлены успешно или не требовали обновления" >> "$LOG_FILE"
else
    echo "Ошибка при обновлении сертификатов!" >> "$LOG_FILE"
    echo "Ошибка при обновлении сертификатов на $(hostname) $(date)" | mail -s "Certbot Error" "$EMAIL"
    exit 1
fi

# Перезапуск всего Docker-стека
echo "Перезапуск Docker-стека..." >> "$LOG_FILE"
if docker-compose -f $DOCKER_COMPOSE_PATH down && docker-compose -f $DOCKER_COMPOSE_PATH up -d; then
    echo "Docker-стек успешно перезапущен" >> "$LOG_FILE"
else
    echo "Ошибка при перезапуске Docker-стека!" >> "$LOG_FILE"
    echo "Ошибка при перезапуске Docker-стека на $(hostname) $(date)" | mail -s "Docker Restart Error" "$EMAIL"
    exit 1
fi

echo "Проверка завершена" >> "$LOG_FILE"
echo "===================================================" >> "$LOG_FILE"
