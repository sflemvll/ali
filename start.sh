#!/bin/bash

# شغّل bgutil PO token server في الخلفية
if command -v bgutil-ytdlp-pot-provider &> /dev/null; then
    echo "Starting bgutil PO token server..."
    bgutil-ytdlp-pot-provider &
    sleep 2
fi

# شغّل التطبيق الرئيسي
exec python main.py
