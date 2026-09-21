@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "C:\Users\User\Downloads\khiye-app\auto-news-poster"
echo Token-oo Copy hiisen bol shuud ajillana. Esvel doorh asuultad paste hiigeed Enter dar.
python tools\fb_page_token.py --clipboard
echo.
echo ---- Duuslaa. Tsonhyg haahyn tuld durynh negen towch dar ----
pause
