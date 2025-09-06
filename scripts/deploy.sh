#!/bin/bash

# Deployment script for insurance system enhancements
# This script handles the complete deployment of new features

set -e  # Exit on any error

# Configuration
PROJECT_DIR="/path/to/your/project"  # Update this path
VENV_DIR="/path/to/your/venv"        # Update this path
BACKUP_DIR="/backups/insurance_system"
LOG_FILE="/var/log/deploy_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS:${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    log "Проверка предварительных требований..."
    
    # Check if Python is available
    if ! command_exists python3; then
        error "Python3 не найден. Установите Python 3.8 или выше."
        exit 1
    fi
    
    # Check Python version
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log "Версия Python: $python_version"
    
    # Check if pip is available
    if ! command_exists pip3; then
        error "pip3 не найден. Установите pip."
        exit 1
    fi
    
    # Check if git is available
    if ! command_exists git; then
        error "Git не найден. Установите Git."
        exit 1
    fi
    
    # Check if virtual environment exists
    if [ ! -d "$VENV_DIR" ]; then
        warning "Виртуальное окружение не найдено по пути: $VENV_DIR"
        read -p "Создать новое виртуальное окружение? (y/N): " create_venv
        if [[ $create_venv =~ ^[Yy]$ ]]; then
            python3 -m venv "$VENV_DIR"
            log "Виртуальное окружение создано: $VENV_DIR"
        else
            error "Виртуальное окружение необходимо для развертывания"
            exit 1
        fi
    fi
    
    success "Предварительные требования выполнены"
}

# Function to create backup
create_backup() {
    log "Создание резервной копии..."
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Backup database
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    backup_file="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).json"
    python manage.py dumpdata > "$backup_file"
    
    if [ $? -eq 0 ]; then
        success "Резервная копия создана: $backup_file"
        echo "$backup_file" > "$BACKUP_DIR/latest_backup.txt"
    else
        error "Не удалось создать резервную копию"
        exit 1
    fi
}

# Function to update code
update_code() {
    log "Обновление кода..."
    
    cd "$PROJECT_DIR"
    
    # Stash any local changes
    git stash push -m "Auto-stash before deployment $(date)"
    
    # Pull latest changes
    git pull origin main
    
    if [ $? -eq 0 ]; then
        success "Код обновлен успешно"
    else
        error "Не удалось обновить код"
        exit 1
    fi
}

# Function to install dependencies
install_dependencies() {
    log "Установка зависимостей..."
    
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install requirements
    pip install -r requirements.txt
    
    if [ $? -eq 0 ]; then
        success "Зависимости установлены успешно"
    else
        error "Не удалось установить зависимости"
        exit 1
    fi
}

# Function to run database migrations
run_migrations() {
    log "Применение миграций базы данных..."
    
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Run the custom migration script
    python scripts/migrate_database.py
    
    if [ $? -eq 0 ]; then
        success "Миграции применены успешно"
    else
        error "Ошибка при применении миграций"
        exit 1
    fi
}

# Function to collect static files
collect_static() {
    log "Сбор статических файлов..."
    
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    python manage.py collectstatic --noinput
    
    if [ $? -eq 0 ]; then
        success "Статические файлы собраны успешно"
    else
        error "Не удалось собрать статические файлы"
        exit 1
    fi
}

# Function to run tests
run_tests() {
    log "Запуск тестов..."
    
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Run specific test suites for new features
    test_modules=(
        "insurance_requests.test_authentication_system"
        "insurance_requests.test_login_interface"
        "insurance_requests.test_form_enhancements"
        "insurance_requests.test_enhanced_email_templates"
        "insurance_requests.test_new_insurance_type"
        "insurance_requests.test_end_to_end_workflow"
    )
    
    for module in "${test_modules[@]}"; do
        log "Запуск тестов: $module"
        python manage.py test "$module" --verbosity=2
        
        if [ $? -ne 0 ]; then
            error "Тесты не прошли: $module"
            exit 1
        fi
    done
    
    success "Все тесты прошли успешно"
}

# Function to restart services
restart_services() {
    log "Перезапуск сервисов..."
    
    # Check if systemd services exist and restart them
    services=("gunicorn" "nginx" "celery")
    
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            log "Перезапуск $service..."
            sudo systemctl restart "$service"
            
            if [ $? -eq 0 ]; then
                success "$service перезапущен успешно"
            else
                warning "Не удалось перезапустить $service"
            fi
        else
            warning "Сервис $service не активен или не найден"
        fi
    done
}

# Function to verify deployment
verify_deployment() {
    log "Проверка развертывания..."
    
    cd "$PROJECT_DIR"
    source "$VENV_DIR/bin/activate"
    
    # Check if Django can start
    python manage.py check --deploy
    
    if [ $? -eq 0 ]; then
        success "Django проверка прошла успешно"
    else
        error "Django проверка не прошла"
        exit 1
    fi
    
    # Test database connection
    python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('Database connection OK')"
    
    if [ $? -eq 0 ]; then
        success "Подключение к базе данных работает"
    else
        error "Проблема с подключением к базе данных"
        exit 1
    fi
    
    # Check if authentication system is working
    python manage.py shell -c "
from django.contrib.auth.models import User, Group
admin_group = Group.objects.get(name='Администраторы')
user_group = Group.objects.get(name='Пользователи')
admin_user = User.objects.get(username='admin')
regular_user = User.objects.get(username='user')
print('Authentication system OK')
"
    
    if [ $? -eq 0 ]; then
        success "Система аутентификации работает"
    else
        error "Проблема с системой аутентификации"
        exit 1
    fi
}

# Function to rollback deployment
rollback_deployment() {
    error "Откат развертывания..."
    
    # Get latest backup
    if [ -f "$BACKUP_DIR/latest_backup.txt" ]; then
        backup_file=$(cat "$BACKUP_DIR/latest_backup.txt")
        
        if [ -f "$backup_file" ]; then
            log "Восстановление из резервной копии: $backup_file"
            
            cd "$PROJECT_DIR"
            source "$VENV_DIR/bin/activate"
            
            # Restore database
            python manage.py flush --noinput
            python manage.py loaddata "$backup_file"
            
            if [ $? -eq 0 ]; then
                success "База данных восстановлена из резервной копии"
            else
                error "Не удалось восстановить базу данных"
            fi
        else
            error "Файл резервной копии не найден: $backup_file"
        fi
    else
        error "Информация о резервной копии не найдена"
    fi
    
    # Restart services
    restart_services
}

# Function to show deployment summary
show_summary() {
    echo ""
    echo "=================================================================="
    echo "                    СВОДКА РАЗВЕРТЫВАНИЯ"
    echo "=================================================================="
    echo "Время развертывания: $(date)"
    echo "Лог файл: $LOG_FILE"
    echo ""
    echo "Новые функции развернуты:"
    echo "  ✓ Новый тип страхования 'страхование имущества'"
    echo "  ✓ Улучшенные шаблоны писем с расширенными описаниями"
    echo "  ✓ Отдельные поля дат страхования в формах"
    echo "  ✓ Система аутентификации с ролевой моделью"
    echo "  ✓ Современный интерфейс входа в систему"
    echo ""
    echo "Учетные записи для тестирования:"
    echo "  Администратор: admin / admin123"
    echo "  Пользователь:  user / user123"
    echo ""
    echo "Следующие шаги:"
    echo "  1. Проверьте работу системы в браузере"
    echo "  2. Протестируйте новые функции"
    echo "  3. Обновите документацию при необходимости"
    echo "=================================================================="
}

# Main deployment function
main() {
    echo "=================================================================="
    echo "        РАЗВЕРТЫВАНИЕ УЛУЧШЕНИЙ СТРАХОВОЙ СИСТЕМЫ"
    echo "=================================================================="
    echo ""
    
    # Check if running as root (not recommended)
    if [ "$EUID" -eq 0 ]; then
        warning "Запуск от имени root не рекомендуется"
        read -p "Продолжить? (y/N): " continue_as_root
        if [[ ! $continue_as_root =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Confirm deployment
    echo "Это развернет следующие новые функции:"
    echo "  • Новый тип страхования 'страхование имущества'"
    echo "  • Улучшенные шаблоны писем"
    echo "  • Отдельные поля дат страхования"
    echo "  • Система аутентификации"
    echo "  • Современный интерфейс входа"
    echo ""
    read -p "Продолжить развертывание? (y/N): " confirm
    
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        log "Развертывание отменено пользователем"
        exit 0
    fi
    
    # Set trap for cleanup on error
    trap rollback_deployment ERR
    
    # Run deployment steps
    check_prerequisites
    create_backup
    update_code
    install_dependencies
    run_migrations
    collect_static
    run_tests
    restart_services
    verify_deployment
    
    # Remove error trap
    trap - ERR
    
    success "Развертывание завершено успешно!"
    show_summary
}

# Run main function
main "$@"