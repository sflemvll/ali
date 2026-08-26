@echo off
chcp 65001 >nul
cd /d "%~dp0..\server"

if not exist ".venv" (
    echo إنشاء بيئة بايثون…
    python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

if not exist ".env" (
    echo.
    echo تنبيه: ما موجود ملف .env
    echo انسخ .env.example باسم .env وحط بيه مفتاح ANTHROPIC_API_KEY
    echo.
)

python app.py
pause
