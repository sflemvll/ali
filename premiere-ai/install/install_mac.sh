#!/usr/bin/env bash
# تثبيت لوحة مساعد بريمير الذكي على macOS
set -e

echo "============================================"
echo "  تثبيت لوحة مساعد بريمير الذكي (macOS)"
echo "============================================"

# 1) السماح بتشغيل الإضافات غير الموقّعة
for V in 9 10 11 12; do
    defaults write "com.adobe.CSXS.$V" PlayerDebugMode 1 2>/dev/null || true
done
echo "[1/2] تم تفعيل PlayerDebugMode لإصدارات CEP 9-12"

# 2) ربط اللوحة بمجلد إضافات CEP
SRC="$(cd "$(dirname "$0")/../extension" && pwd)"
DST="$HOME/Library/Application Support/Adobe/CEP/extensions/com.alamani.premiereai"

mkdir -p "$HOME/Library/Application Support/Adobe/CEP/extensions"
rm -rf "$DST"
ln -s "$SRC" "$DST"
echo "[2/2] تم ربط اللوحة:"
echo "     $DST  ->  $SRC"

echo
echo "خلص التثبيت. الخطوات الباقية:"
echo "  1) شغّل السيرفر:  premiere-ai/install/start_server.sh"
echo "  2) افتح بريمير:   Window > Extensions > مساعد الذكاء الاصطناعي"
