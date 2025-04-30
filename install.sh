#!/bin/bash

# Остановка при ошибке
set -e

echo "🔧 Создание виртуального окружения..."
python3 -m venv venv

echo "✅ Виртуальное окружение создано."

echo "🚀 Активация виртуального окружения..."
source venv/bin/activate

echo "🔄 Обновление pip..."
pip install --upgrade pip

echo "📦 Установка зависимостей из requirements.txt..."
pip install -r requirements.txt

echo "✅ Установка завершена."
echo "📍 Для запуска окружения позже используйте:"
echo "    source venv/bin/activate"
