#!/bin/bash

# شغّل خادم PO Token في الخلفية (يولّد توكنات تتجاوز حظر يوتيوب للسيرفرات)
if [ -f /opt/bgutil/server/build/main.js ]; then
    echo "Starting bgutil PO token server on :4416 ..."
    node /opt/bgutil/server/build/main.js --port 4416 &
    sleep 3
fi

# شغّل التطبيق الرئيسي
exec python main.py
