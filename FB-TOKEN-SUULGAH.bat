@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\User\Downloads\khiye-app\auto-news-poster"
python tools\fb_page_token.py --clipboard
echo.
pause
