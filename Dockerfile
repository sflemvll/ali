FROM python:3.12-slim

# تثبيت ffmpeg (مطلوب لدمج الفيديو والصوت وتحويل MP3)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت المكتبات أولاً (cache layer للسرعة)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "main.py"]
