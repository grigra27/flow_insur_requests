#!/bin/bash

# Fix HTTPS Redirect Loops
# This script fixes the ERR_TOO_MANY_REDIRECTS issue

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

# Error message
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Fix redirect loops
fix_redirect_loops() {
    info "Исправляем проблему с бесконечными редиректами..."
    
    cd "$PROJECT_PATH"
    
    # 1. Stop services
    docker-compose -f docker-compose.timeweb.yml down
    
    # 2. Copy fixed HTTPS configuration
    cp nginx-timeweb/default-https.conf nginx-timeweb/default.conf
    success "Обновлена nginx конфигурация"
    
    # 3. Ensure .env is properly configured for HTTPS
    info "Проверяем .env конфигурацию..."
    
    # Make sure Django HTTPS settings are correct
    sed -i 's/SSL_ENABLED=False/SSL_ENABLED=True/' .env
    sed -i 's/SESSION_COOKIE_SECURE=False/SESSION_COOKIE_SECURE=True/' .env
    sed -i 's/CSRF_COOKIE_SECURE=False/CSRF_COOKIE_SECURE=True/' .env
    sed -i 's/SECURE_SSL_REDIRECT=False/SECURE_SSL_REDIRECT=True/' .env
    sed -i 's/SECURE_HSTS_SECONDS=0/SECURE_HSTS_SECONDS=31536000/' .env
    sed -i 's/SECURE_HSTS_INCLUDE_SUBDOMAINS=False/SECURE_HSTS_INCLUDE_SUBDOMAINS=True/' .env
    sed -i 's/SECURE_HSTS_PRELOAD=False/SECURE_HSTS_PRELOAD=True/' .env
    
    success ".env конфигурация обновлена"
    
    # 4. Start services with SSL profile
    info "Запускаем сервисы с исправленной конфигурацией..."
    COMPOSE_PROFILES="ssl" docker-compose -f docker-compose.timeweb.yml up -d
    
    # 5. Wait for services to start
    info "Ожидание запуска сервисов..."
    sleep 30
    
    success "Сервисы перезапущены"
}

# Test for redirect loops
test_redirect_loops() {
    info "Тестируем редиректы..."
    
    local domains=("insflow.ru" "zs.insflow.ru" "insflow.tw1.su" "zs.insflow.tw1.su")
    local success_count=0
    
    for domain in "${domains[@]}"; do
        # Test HTTP redirect (should be 301/302 to HTTPS)
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://$domain/" 2>/dev/null || echo "000")
        
        # Test HTTPS direct access
        local https_test=$(curl -f -s -k "https://$domain/healthz/" 2>/dev/null && echo "OK" || echo "FAIL")
        
        if [[ "$http_code" =~ ^30[12]$ ]] && [[ "$https_test" == "OK" ]]; then
            success "$domain: HTTP->HTTPS редирект работает, HTTPS доступен"
            success_count=$((success_count + 1))
        else
            error "$domain: Проблема с редиректами (HTTP: $http_code, HTTPS: $https_test)"
        fi
    done
    
    echo ""
    if [[ $success_count -eq 4 ]]; then
        success "🎉 Все домены работают корректно без бесконечных редиректов!"
        return 0
    else
        error "Некоторые домены все еще имеют проблемы ($success_count/4 работают)"
        return 1
    fi
}

# Show nginx configuration
show_nginx_config() {
    info "Текущая nginx конфигурация:"
    echo "================================"
    
    # Show which config is active
    if docker-compose -f "$PROJECT_PATH/docker-compose.timeweb.yml" exec -T nginx nginx -T 2>/dev/null | head -20; then
        success "Nginx конфигурация загружена успешно"
    else
        error "Не удалось получить nginx конфигурацию"
    fi
    
    echo "================================"
}

# Main function
main() {
    echo "🔧 Исправление бесконечных HTTPS редиректов"
    echo "=========================================="
    
    fix_redirect_loops
    
    if test_redirect_loops; then
        show_nginx_config
        
        echo ""
        success "🎉 Проблема с бесконечными редиректами исправлена!"
        
        info "Доступные endpoints:"
        echo "  - https://insflow.ru"
        echo "  - https://zs.insflow.ru"  
        echo "  - https://insflow.tw1.su"
        echo "  - https://zs.insflow.tw1.su"
        
    else
        error "Проблема с редиректами не полностью исправлена"
        
        info "Для диагностики проверьте:"
        echo "  - docker-compose -f docker-compose.timeweb.yml logs nginx"
        echo "  - docker-compose -f docker-compose.timeweb.yml logs web"
    fi
}

# Run main function
main "$@"