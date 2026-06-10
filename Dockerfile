FROM python:3.12-slim

# ffmpeg (دمج الصوت/الفيديو) + Node.js (مولّد PO Token)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg nodejs npm git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# مكتبات Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# خادم توليد PO Token (الحل الرسمي لحظر يوتيوب على سيرفرات الداتا سنتر)
RUN git clone --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm install \
    && npx tsc

# نسخ باقي الملفات
COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["bash", "start.sh"]
