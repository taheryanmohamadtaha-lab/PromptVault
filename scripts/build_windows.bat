@echo off
chcp 65001 >nul
REM ساخت نسخه‌ی ویندوز روی کامپیوتر خودتان (نیاز به نصب Python 3.12 دارد).
REM فقط دوبار کلیک کنید. خروجی: پوشه‌ی dist\PromptVault\PromptVault.exe
cd /d "%~dp0\.."
python -m pip install -r requirements-dev.txt || goto :error
set QT_QPA_PLATFORM=offscreen
python -m pytest -q || goto :error
set QT_QPA_PLATFORM=
pyinstaller --noconfirm --clean PromptVault.spec || goto :error
echo.
echo ساخت با موفقیت تمام شد:  dist\PromptVault\PromptVault.exe
pause
exit /b 0
:error
echo.
echo خطا رخ داد. متن بالا را برای پشتیبانی بفرستید.
pause
exit /b 1
