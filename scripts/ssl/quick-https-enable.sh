#!/bin/bash

# Quick HTTPS Enable Script
# This script quickly enables HTTPS when certificates exist

set -e

PROJECT_PATH="/opt/insflow-system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Success message
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Info message
info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Quick HTTPS activation
quick_https_enable() {
    info "Быстрая активация HTTPS..."
    
    cd "$PROJECT_PATH"
    
    # Check if certificates exist (try both with and without sudo)
    if [[ -f "letsencrypt/live/insflow.ru/fullchain.pem" ]] || sudo test -f "letsencrypt/live/insflow.ru/fullchain.pem" 2>/dev/null; then
        success "SSL сертификаты найдены"
    else
        echo "❌ SSL сертификаты не найдены"
        echo "Запустите сначала: sudo bash scripts/ssl/obtain-certificates-docker.sh"
        exit 1
    fi
    
    # 1. Copy HTTPS nginx configuration
    cp nginx-timeweb/default-https.conf nginx-timeweb/default.conf
    success "HTTPS nginx конфигурация активирована"
    
    # 2. Update .env file
    sed -i 's/SSL_ENABLED=False/SSL_ENABLED=True/' .env
    sed -i 's/SESSION_COOKIE_SECURE=False/SESSION_COOKIE_SECURE=True/' .env
    sed -i 's/CSRF_COOKIE_SECURE=False/CSRF_COOKIE_SECURE=True/' .env
    sed -i 's/SECURE_SSL_REDIRECT=False/SECURE_SSL_REDIRECT=True/' .env
    sed -i 's/SECURE_HSTS_SECONDS=0/SECURE_HSTS_SECONDS=31536000/' .env
    sed -i 's/SECURE_HSTS_INCLUDE_SUBDOMAINS=False/SECURE_HSTS_INCLUDE_SUBDOMAINS=True/' .env
    sed -i 's/SECURE_HSTS_PRELOAD=False/SECURE_HSTS_PRELOAD=True/' .env
    success ".env обновлен для HTTPS"
    
    # 3. Restart with SSL profile
    docker-compose -f docker-compose.timeweb.yml down
    COMPOSE_PROFILES="ssl" docker-compose -f docker-compose.timeweb.yml up -d --force-recreate
    success "Сервисы перезапущены с HTTPS"
    
    # 4. Wait and test
    info "Ожидание запуска сервисов..."
    sleep 30
    
    # Test HTTPS
    local success_count=0
    local domains=("insflow.ru" "zs.insflow.ru" "insflow.tw1.su" "zs.insflow.tw1.su")
    
    for domain in "${domains[@]}"; do
        if curl -f -s -k "https://$domain/healthz/" > /dev/null 2>&1; then
            success "HTTPS работает для $domain"
            success_count=$((success_count + 1))
        else
            echo "❌ HTTPS не работает для $domain"
        fi
    done
    
    echo ""
    if [[ $success_count -eq 4 ]]; then
        success "🎉 HTTPS успешно активирован для всех доменов!"
        
        echo ""
        info "Доступные HTTPS endpoints:"
        echo "  - https://insflow.ru"
        echo "  - https://zs.insflow.ru"
        echo "  - https://insflow.tw1.su"
        echo "  - https://zs.insflow.tw1.su"
        
    else
        echo "⚠️ HTTPS активирован, но не все домены работают ($success_count/4)"
        info "Проверьте логи nginx: docker-compose -f docker-compose.timeweb.yml logs nginx"
    fi
}

# Main function
main() {
    echo "🚀 Быстрая активация HTTPS"
    echo "========================="
    
    quick_https_enable
}

# Run main function
main "$@"