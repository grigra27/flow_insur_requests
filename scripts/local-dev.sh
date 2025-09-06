#!/bin/bash

# Скрипт для быстрого запуска локальной разработки
# Использование: ./scripts/local-dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting local development environment..."

# Переходим в директорию проекта
cd "$PROJECT_DIR"

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your local settings"
fi

# Проверяем наличие виртуального окружения
if [ ! -d "venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Обновляем pip
echo "📦 Updating pip..."
pip install --upgrade pip

# Устанавливаем зависимости
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Проверяем наличие базы данных
if [ ! -f "db.sqlite3" ]; then
    echo "🗄️  Setting up database..."
    python manage.py migrate
    python manage.py setup_user_groups
    
    # Предлагаем создать суперпользователя
    echo "👤 Would you like to create a superuser? (y/n)"
    read -r create_superuser
    if [ "$create_superuser" = "y" ] || [ "$create_superuser" = "Y" ]; then
        python manage.py createsuperuser
    fi
    
    # Предлагаем загрузить демо-данные
    echo "📊 Would you like to load demo data? (y/n)"
    read -r load_demo
    if [ "$load_demo" = "y" ] || [ "$load_demo" = "Y" ]; then
        python manage.py loaddata insurance_requests/fixtures/sample_data.json
        echo "✅ Demo data loaded!"
        echo "Demo users:"
        echo "  - Admin: admin / admin123"
        echo "  - User: user / user123"
    fi
else
    echo "🔄 Running migrations..."
    python manage.py migrate
fi

# Собираем статические файлы
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Проверяем конфигурацию
echo "🔍 Checking configuration..."
python manage.py check

echo ""
echo "✅ Local development environment is ready!"
echo ""
echo "🚀 To start the development server:"
echo "   source venv/bin/activate"
echo "   python manage.py runserver"
echo ""
echo "🌐 Application will be available at: http://127.0.0.1:8000/"
echo ""
echo "📊 Useful commands:"
echo "   python manage.py shell          # Django shell"
echo "   python manage.py migrate        # Apply migrations"
echo "   python manage.py createsuperuser # Create admin user"
echo ""
echo "🐳 To use Docker instead:"
echo "   docker-compose up -d"
echo "   # Application will be available at: http://localhost:8000/"