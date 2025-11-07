#!/bin/bash

# Скрипт для тестирования конфигураций обоих хостингов

echo "🧪 Тестирование конфигураций для двух хостингов"
echo "================================================"

# Проверка файлов Digital Ocean
echo "📋 Проверка файлов Digital Ocean..."
if [ -f "docker-compose.yml" ]; then
    echo "✅ docker-compose.yml найден"
else
    echo "❌ docker-compose.yml не найден"
fi

if [ -f "nginx/default.conf" ]; then
    echo "✅ nginx/default.conf найден"
else
    echo "❌ nginx/default.conf не найден"
fi

if [ -f ".github/workflows/deploy_do.yml" ]; then
    echo "✅ .github/workflows/deploy_do.yml найден"
else
    echo "❌ .github/workflows/deploy_do.yml не найден"
fi

echo ""

# Проверка файлов Timeweb
echo "📋 Проверка файлов Timeweb..."
if [ -f "docker-compose.timeweb.yml" ]; then
    echo "✅ docker-compose.timeweb.yml найден"
else
    echo "❌ docker-compose.timeweb.yml не найден"
fi

if [ -f "nginx-timeweb/default.conf" ]; then
    echo "✅ nginx-timeweb/default.conf найден"
else
    echo "❌ nginx-timeweb/default.conf не найден"
fi

if [ -f ".github/workflows/deploy_timeweb.yml" ]; then
    echo "✅ .github/workflows/deploy_timeweb.yml найден"
else
    echo "❌ .github/workflows/deploy_timeweb.yml не найден"
fi

if [ -f ".env.timeweb.example" ]; then
    echo "✅ .env.timeweb.example найден"
else
    echo "❌ .env.timeweb.example не найден"
fi

echo ""

# Проверка синтаксиса docker-compose файлов
echo "🔍 Проверка синтаксиса docker-compose файлов..."

if command -v docker-compose &> /dev/null; then
    echo "Проверка docker-compose.yml..."
    if docker-compose config > /dev/null 2>&1; then
        echo "✅ docker-compose.yml синтаксис корректен"
    else
        echo "❌ docker-compose.yml содержит ошибки"
    fi
    
    echo "Проверка docker-compose.timeweb.yml..."
    if docker-compose -f docker-compose.timeweb.yml config > /dev/null 2>&1; then
        echo "✅ docker-compose.timeweb.yml синтаксис корректен"
    else
        echo "❌ docker-compose.timeweb.yml содержит ошибки"
    fi
else
    echo "⚠️ docker-compose не установлен, пропускаем проверку синтаксиса"
fi

echo ""

# Проверка доменов в nginx конфигах
echo "🌐 Проверка доменов в nginx конфигах..."

if grep -q "onbr.site" nginx/default.conf 2>/dev/null; then
    echo "✅ Домен onbr.site найден в nginx/default.conf"
else
    echo "❌ Домен onbr.site не найден в nginx/default.conf"
fi

if grep -q "zs.insflow.tw1.su" nginx-timeweb/default.conf 2>/dev/null; then
    echo "✅ Домен zs.insflow.tw1.su найден в nginx-timeweb/default.conf"
else
    echo "❌ Домен zs.insflow.tw1.su не найден в nginx-timeweb/default.conf"
fi

echo ""
echo "🎉 Проверка завершена!"
echo ""
echo "📚 Для деплоя:"
echo "   - Digital Ocean: git push origin main (автоматически)"
echo "   - Timeweb: git push origin main (автоматически)"
echo ""
echo "🔧 Не забудьте настроить GitHub Secrets для обоих хостингов!"