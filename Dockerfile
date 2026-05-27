FROM python:3.12-slim

# تثبيت ffmpeg + Node.js (مطلوب لـ PO Token provider)
RUN apt-get update && apt-get install -y \
    ffmpeg curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# تثبيت bgutil PO Token provider
RUN npm install -g @imputnet/bgutil-ytdlp-pot-provider 2>/dev/null || true

WORKDIR /app

# تثبيت المكتبات Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تثبيت yt-dlp plugin للـ PO token
RUN pip install -U yt-dlp
RUN python -m yt_dlp_plugins_common --info 2>/dev/null || true

# نسخ باقي الملفات
COPY . .

ENV PORT=8080
EXPOSE 8080

# سكريبت بدء التشغيل
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
