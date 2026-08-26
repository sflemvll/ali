#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../server"

if [ ! -d ".venv" ]; then
    echo "إنشاء بيئة بايثون…"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
    echo
    echo "تنبيه: ما موجود ملف .env"
    echo "انسخ .env.example باسم .env وحط بيه مفتاح ANTHROPIC_API_KEY"
    echo
fi

python app.py
