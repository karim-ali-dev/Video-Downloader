#!/data/data/com.termux/files/usr/bin/env bash
# Video Downloader - Android (Termux) install script
# For Linux/Android Termux

set -e

echo ">>> جاري تحديث الحزم..."
pkg update -y
pkg install -y python ffmpeg git curl

echo ">>> تثبيت yt-dlp..."
pip install -U yt-dlp

echo ">>> تنزيل سكريبت التشغيل..."
curl -sL https://raw.githubusercontent.com/karim-ali-dev/Video-Downloader/main/run_android.py -o run_android.py

chmod +x run_android.py

cat > ~/.bashrc <<'EOF'
alias video-downloader='python $HOME/run_android.py'
EOF

echo ""
echo "================================================"
echo "  تم التثبيت بنجاح!"
echo "  للاستخدام اكتب:  video-downloader"
echo "  أو:  python run_android.py"
echo "================================================"
